"""Prepare the blind listening pilot and summarize submitted paired choices."""

import argparse
from array import array
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import secrets
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
import wave


VOICE = "zf_001"
SPEED = 1.0
PAIR_PASSAGES = {
    "M02": {"SD03", "SD04"},
    "M06": {"ET05", "ET06"},
    "P01": {"NS01", "NS02"},
}
PAUSE_PASSAGE = "SD01"
STIMULUS_DIR = Path("audio/stage6/listening")
PRIVATE_DIR = Path("results/stage6/listening")


def read_rows(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    with NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as stream:
        staged = Path(stream.name)
        try:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.close()
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_comparisons(root, voice, speed):
    manifests = root / "audio/manifests"
    matched = read_rows(manifests / "listening-pairs.jsonl")
    edited = read_rows(manifests / "pause-probes.jsonl")
    selected = []
    for pair_id, passage_ids in PAIR_PASSAGES.items():
        rows = [
            row for row in matched
            if row["pair_id"] == pair_id and row["speaker_preset"] == voice
            and row["speed"] == speed
        ]
        expected_kind = "historical_wording_variant" if pair_id == "P01" else "period_matched_prose"
        if (len(rows) != 1 or rows[0]["comparison"] != expected_kind
                or len(rows[0]["members"]) != 2
                or {member["passage_id"] for member in rows[0]["members"]} != passage_ids):
            raise ValueError(f"Expected one {pair_id} comparison with its reviewed passages")
        selected.append(rows[0])

    pause = [
        row for row in edited
        if row["passage_id"] == PAUSE_PASSAGE and row["speaker_preset"] == voice
        and row["speed"] == speed
    ]
    if (len(pause) != 1 or pause[0]["comparison"] != "synthetic_pause_extension"
            or len(pause[0]["members"]) != 2):
        raise ValueError(f"Expected one {PAUSE_PASSAGE} timing comparison")
    selected.append(pause[0])
    return selected


def read_clip(root, member, expected_rate):
    path = (root / member["audio_path"]).resolve(strict=True)
    if not path.is_relative_to(root / "audio") or digest(path) != member["audio_sha256"]:
        raise ValueError(f"{member['recording_id']}: Stage 4 path or checksum mismatch")
    with wave.open(str(path), "rb") as stream:
        rate = stream.getframerate()
        if (stream.getnchannels(), stream.getsampwidth(), stream.getcomptype(), rate) != (
            1, 2, "NONE", expected_rate
        ):
            raise ValueError(f"{member['recording_id']}: expected Stage 4 mono PCM-16")
        samples = array("h", stream.readframes(stream.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    return rate, samples


def active_level(samples, rate):
    window = max(1, round(0.020 * rate))
    energy = [
        sum(sample * sample for sample in samples[start:start + window])
        for start in range(0, len(samples) - window + 1, window)
    ]
    if not energy or max(energy) == 0:
        raise ValueError("Cannot level match an empty or silent clip")
    threshold = max(energy) * 0.01
    active = [value for value in energy if value >= threshold]
    return math.sqrt(sum(active) / (len(active) * window))


def level_gains(left, right, rate, edit):
    target = 32767 * 10 ** (-24 / 20)
    ceiling = 32767 * 10 ** (-1 / 20)
    if edit is not None:
        start, count = edit["sample_offset"], edit["inserted_samples"]
        if (edit["method"] != "insert_zero_samples" or count <= 0 or not 0 < start < len(left)
                or right[start:start + count] != array("h", [0]) * count
                or right[:start] + right[start + count:] != left):
            raise ValueError("Pause comparison changed samples outside its documented insertion")
        gain = min(target / active_level(left, rate), ceiling / max(map(abs, left)))
        return gain, gain

    levels = [active_level(clip, rate) for clip in (left, right)]
    safe_levels = [
        ceiling * level / max(map(abs, clip)) for clip, level in zip((left, right), levels)
    ]
    target = min(target, *safe_levels)
    return tuple(target / level for level in levels)


def write_clip(path, rate, samples, gain):
    scaled = array("h", (round(sample * gain) for sample in samples))
    if sys.byteorder != "little":
        scaled.byteswap()
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        stream.writeframes(scaled.tobytes())


def recording_provenance(recording, passage, voice, speed):
    if (recording["kind"] != "synthetic" or recording["variety"] != "cmn"
            or recording["speaker"] != voice or recording["speed"] != speed
            or recording["model_license"] != "Apache-2.0"
            or passage["work_rights"] != "Public domain"
            or passage["license"] != "CC-BY-SA-4.0"
            or recording["text_license"] != passage["license"]
            or recording["text_sha256"] != passage["text_sha256"]
            or recording["text_revision"] != passage["revision_id"]
            or recording["text_source_url"] != passage["source_url"]):
        raise ValueError(f"{recording['recording_id']}: source lineage, rights or condition mismatch")
    return {
        key: passage[key] for key in (
            "passage_id", "work_id", "title", "author", "genre", "period", "revision_id",
            "source_url", "work_rights", "license", "attribution", "text_sha256",
        )
    } | {"criticism": passage.get("criticism")}


def make_trial(root, folder, comparison, trial_id, recordings, passages, rng):
    edit = comparison.get("edit")
    left, right = comparison["members"]
    source_rows = [recordings[left["recording_id"]]]
    source_rows.append(source_rows[0] if edit is not None else recordings[right["recording_id"]])
    clips = []
    for member, source in zip((left, right), source_rows):
        if member["recording_id"] == source["recording_id"] and any(
            member[field] != source[field] for field in ("audio_path", "audio_sha256")
        ):
            raise ValueError(f"{source['recording_id']}: conflicting Stage 4 audio lineage")
        if member.get("passage_id", source["passage_id"]) != source["passage_id"]:
            raise ValueError(f"{source['recording_id']}: conflicting Stage 4 text lineage")
        passage = passages[source["passage_id"]]
        provenance = recording_provenance(source, passage, comparison['speaker_preset'], comparison['speed'])
        rate, samples = read_clip(root, member, source["sample_rate"])
        clips.append((member, source, provenance, rate, samples))

    if clips[0][3] != clips[1][3]:
        raise ValueError("Paired recordings must use the same sample rate")
    rate = clips[0][3]
    gains = level_gains(clips[0][4], clips[1][4], rate, edit)
    choices = list(zip(clips, gains))
    rng.shuffle(choices)
    blind = {"trial_id": trial_id}
    private = {
        "trial_id": trial_id,
        "comparison_id": comparison["comparison_id"],
        "comparison": comparison["comparison"],
        "wording_edit": comparison.get("source_edit"),
        "timing_edit": edit,
    }
    for side, (clip, gain) in zip("AB", choices):
        member, source, provenance, rate, samples = clip
        filename = f"{trial_id}-{side}.wav"
        target = folder / filename
        write_clip(target, rate, samples, gain)
        blind[side] = filename
        private[side] = {
            "stage4_member": member,
            "stage4_synthesis": source,
            "text_provenance": provenance,
            "sample_rate": rate,
            "duration_s": len(samples) / rate,
            "gain_db": 20 * math.log10(gain),
            "sha256": digest(target),
        }
    return blind, private


def check_staged(folder, key):
    survey = read_json(folder / "survey.json")
    if survey != key["survey"]:
        raise ValueError("Blind survey and private survey key disagree")
    expected = {"survey.json"}
    for trial in key["trials"]:
        for side in "AB":
            filename = f"{trial['trial_id']}-{side}.wav"
            expected.add(filename)
            path = folder / filename
            if path.is_symlink() or digest(path) != trial[side]["sha256"]:
                raise ValueError(f"Staged file failed verification: {filename}")
    if {path.name for path in folder.iterdir()} != expected:
        raise ValueError("Blind stimulus folder has unexpected files")
    return survey


def prepare(root, seed, *, voice=VOICE, speed=SPEED, prefix='L'):
    if len(prefix) != 1 or not 'A' <= prefix <= 'Z':
        raise ValueError('Trial prefix must be one uppercase ASCII letter')
    folder = root / STIMULUS_DIR
    private = root / PRIVATE_DIR
    private.mkdir(parents=True, exist_ok=True)
    private.chmod(0o700)
    folder.parent.mkdir(parents=True, exist_ok=True)
    with (private / ".prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        key_path = private / "unblinding.json"
        if folder.exists():
            key = read_json(key_path)
            if seed is not None and seed != key["seed"]:
                raise ValueError("A survey already exists with a different seed")
            if any(
                row['trial_id'] != f'{prefix}{number:02d}'
                or any(row[side]['stage4_synthesis']['speaker'] != voice
                       or row[side]['stage4_synthesis']['speed'] != speed for side in 'AB')
                for number, row in enumerate(key['trials'], 1)
            ):
                raise ValueError('The saved survey uses a different trial label, voice, or speed')
            return check_staged(folder, key)
        prior = read_json(key_path) if key_path.exists() else None
        if prior is not None:
            if seed is not None and seed != prior["seed"]:
                raise ValueError("A saved survey key already exists with a different seed")
            seed = prior["seed"]
        elif seed is None:
            seed = secrets.randbits(128)

        rng = random.Random(seed)
        selected = selected_comparisons(root, voice, speed)
        rng.shuffle(selected)
        recordings = {
            row["recording_id"]: row
            for row in read_rows(root / "audio/manifests/synthetic.jsonl")
        }
        passages = {
            row["passage_id"]: row for row in read_rows(root / "data/pilot/annotated.jsonl")
        }
        survey_id = prior["survey"]["survey_id"] if prior else secrets.token_hex(8)
        survey = {"schema_version": 1, "survey_id": survey_id, "trials": []}
        key = {
            "schema_version": 1,
            "seed": seed,
            "survey": survey,
            "processing": (
                "Mono PCM-16 WAV with fresh headers. Active RMS uses full 20 ms frames "
                "within 20 dB of the strongest frame. Target -24 dBFS active RMS when "
                "possible while retaining 1 dB peak headroom. The timing pair shares "
                "the exact gain determined from its unedited clip."
            ),
            "trials": [],
        }
        with TemporaryDirectory(dir=folder.parent, prefix=".staging-") as temporary:
            staged = Path(temporary) / "listening"
            staged.mkdir()
            for number, row in enumerate(selected, 1):
                blind, details = make_trial(
                    root, staged, row, f"{prefix}{number:02d}", recordings, passages, rng
                )
                survey["trials"].append(blind)
                key["trials"].append(details)
            if prior is not None and key != prior:
                raise ValueError("Rebuilt stimuli differ from the saved survey key")
            write_json(staged / "survey.json", survey)
            check_staged(staged, key)
            write_json(key_path, key)
            staged.replace(folder)
        return survey


def summarize(survey, rows):
    votes = {row["trial_id"]: dict.fromkeys(("A", "B", "tie", "skip"), 0)
             for row in survey["trials"]}
    seen = set()
    for row in rows:
        trial_id, choice = row["trial_id"], row["choice"]
        participant = row["participant_id"]
        if (row["survey_id"] != survey["survey_id"] or trial_id not in votes
                or choice not in votes[trial_id] or not isinstance(participant, str)
                or not participant.strip()):
            raise ValueError("Response must identify this survey, a valid trial and choice, and a participant")
        if (participant, trial_id) in seen:
            raise ValueError("Collect at most one response per participant and trial")
        seen.add((participant, trial_id))
        votes[trial_id][choice] += 1

    output = []
    for trial_id, counts in votes.items():
        a, b = counts["A"], counts["B"]
        log_odds = math.log(a / b) if a and b else None
        status = "finite" if a and b else "separated" if a or b else "no_decisive_choices"
        output.append({
            "trial_id": trial_id,
            "counts": counts,
            "decisive_choices": a + b,
            "A_win_share_among_decisive": a / (a + b) if a or b else None,
            "bradley_terry_A_vs_B_log_odds_conditional_on_decisive": log_odds,
            "bradley_terry_status": status,
        })
    return {
        "survey_id": survey["survey_id"],
        "participant_count": len({participant for participant, _ in seen}),
        "trials": output,
        "scope": (
            "One comparison per disconnected pair of stimuli. Ties and skips are counted "
            "separately. Conditional log odds apply within a pair."
        ),
    }


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare", help="Stage anonymous stimuli under the project root")
    setup.add_argument("--root", type=Path, required=True)
    setup.add_argument("--seed", type=int)
    setup.add_argument('--voice', default=VOICE)
    setup.add_argument('--speed', type=float, default=SPEED)
    setup.add_argument('--prefix', default='L')
    score = commands.add_parser("score", help="Summarize blind participant choices")
    score.add_argument("--root", type=Path, required=True)
    score.add_argument("--responses", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if args.command == "prepare":
        survey = prepare(root, args.seed, voice=args.voice, speed=args.speed, prefix=args.prefix)
        print(f"Verified {len(survey['trials'])} blind pairs for survey {survey['survey_id']}")
    else:
        survey = read_json(root / STIMULUS_DIR / "survey.json")
        print(json.dumps(summarize(survey, read_rows(args.responses)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
