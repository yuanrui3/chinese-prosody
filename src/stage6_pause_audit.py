"""Re-decode the Stage 4 pause pairs against known waveform offsets."""

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
from statistics import median
from tempfile import NamedTemporaryFile
import wave


STAGE4 = Path("audio/manifests")
MANIFEST = STAGE4 / "stage6-pause-audit.jsonl"
PROBE_DIR = Path("audio/raw/stage6/pause-audit")
DRAFTS = Path("audio/derived/stage6/pause-audit")
RESULTS = Path("results/stage6/pause-audit.json")


def rows(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as output:
        staged = Path(output.name)
        try:
            output.write(data)
            output.close()
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_audio(root, member, directory):
    path = (root / member["audio_path"]).resolve(strict=True)
    if not path.is_relative_to(root / directory):
        raise ValueError(f"{member['recording_id']}: audio path outside {directory}")
    content = path.read_bytes()
    if sha256(content) != member["audio_sha256"]:
        raise ValueError(f"{member['recording_id']}: input changed")
    with wave.open(io.BytesIO(content)) as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getcomptype()) != (1, 2, "NONE"):
            raise ValueError(f"{member['recording_id']}: expected mono PCM-16")
        return content, stream.getframerate(), stream.readframes(stream.getnframes())


def prepare(root):
    recordings = {row["recording_id"]: row for row in rows(root / STAGE4 / "synthetic.jsonl")}
    probes = rows(root / STAGE4 / "pause-probes.jsonl")
    if not probes:
        raise ValueError("No Stage 4 pause probes")
    output = []
    for pair in probes:
        original, probe = pair["members"]
        source = recordings[original["recording_id"]]
        edit = pair["edit"]
        if (source["kind"] != "synthetic" or source["variety"] != "cmn"
                or source["passage_id"] != pair["passage_id"]
                or source["speaker"] != pair["speaker_preset"] or source["speed"] != pair["speed"]
                or any(source[key] != original[key] for key in ("audio_path", "audio_sha256"))
                or pair["comparison"] != "synthetic_pause_extension"
                or Path(probe["recording_id"]).name != probe["recording_id"]
                or probe["recording_id"] != pair["comparison_id"]):
            raise ValueError("Stage 4 lineage mismatch")
        _, rate, base_pcm = load_audio(root, original, Path("audio/raw"))
        content, edited_rate, edited_pcm = load_audio(root, probe, Path("audio/derived/listening/pause"))
        offset = 2 * edit["sample_offset"]
        length = 2 * edit["inserted_samples"]
        if (edit["method"] != "insert_zero_samples" or not 0 < offset < len(base_pcm)
                or edited_rate != rate or source["sample_rate"] != rate
                or edit["inserted_samples"] / rate != 0.120
                or edited_pcm[offset:offset + length] != bytes(length)
                or edited_pcm[:offset] + edited_pcm[offset + length:] != base_pcm):
            raise ValueError(f"{pair['comparison_id']}: expected a verified sample-exact 120 ms pause edit")
        destination = PROBE_DIR / f"{probe['recording_id']}.wav"
        write_bytes(root / destination, content)
        comparison = {
            "pair_id": pair["comparison_id"],
            "edit": edit,
            "sample_rate_hz": rate,
        }
        output.append({**source, "pause_audit": {**comparison, "role": "original"}})
        output.append({
            **source, **probe, "audio_path": str(destination),
            "duration_s": len(edited_pcm) / (2 * rate),
            "pause_audit": {
                **comparison, "role": "probe",
                "stage4_edited_audio_path": probe["audio_path"],
                "stage4_original_recording_id": source["recording_id"],
            },
        })
    if len({row["recording_id"] for row in output}) != len(output):
        raise ValueError("Pause pairs unexpectedly reuse a recording ID")
    manifest = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in output)
    write_bytes(root / MANIFEST, manifest.encode("utf-8"))
    print(f"Verified {len(probes)} sample-exact pause pairs. Manifest at {MANIFEST}")


def matched_slots(events):
    return {
        row["slot_index"]: row
        for row in events
        if row["slot_index"] is not None and row["status"] == "matched"
        and row["start_s"] is not None and row["end_s"] is not None
    }


def boundary(left, right, splice_start, splice_end, intervening_events):
    intervening = [
        row for row in intervening_events
        if left["event_index"] < row["event_index"] < right["event_index"]
        and row["start_s"] is not None
    ]
    return {
        "left_end_ms": 1000 * left["end_s"],
        "right_start_ms": 1000 * right["start_s"],
        "gap_ms": 1000 * (right["start_s"] - left["end_s"]),
        "contains_entire_splice": left["end_s"] <= splice_start <= splice_end <= right["start_s"],
        "intervening_drafted_events": len(intervening),
    }


def same_segments(original, probe):
    return all(
        original["observed_phone_draft"][key] == probe["observed_phone_draft"][key]
        for key in ("onset", "final")
    )


def nearby_shift(before, after, slots, splice, extension):
    errors = {"pre_splice": [], "post_splice": []}
    for slot, original in before.items():
        if slot in slots or slot not in after or not same_segments(original, after[slot]):
            continue
        if original["end_s"] <= splice:
            group, expected_shift = "pre_splice", 0
        elif original["start_s"] >= splice:
            group, expected_shift = "post_splice", extension
        else:
            continue
        shifted = after[slot]
        errors[group].extend(1000 * abs(shifted[edge] - original[edge] - expected_shift)
                             for edge in ("start_s", "end_s"))
    return {key: {"matched_edges": len(values), "median_absolute_error_ms": median(values) if values else None}
            for key, values in errors.items()}


def pair_summary(original, probe, events, frame_ms):
    audit = original["pause_audit"]
    rate, edit = audit["sample_rate_hz"], audit["edit"]
    splice = edit["sample_offset"] / rate
    extension = edit["inserted_samples"] / rate
    slot = edit["after_slot_index"]
    slots = (slot, slot + 1)
    before_rows = events[original["recording_id"]]
    after_rows = events[probe["recording_id"]]
    before, after = matched_slots(before_rows), matched_slots(after_rows)
    details = {
        "pair_id": audit["pair_id"],
        "passage_id": original["passage_id"],
        "speaker": original["speaker"],
        "speed": original["speed"],
        "after_slot_index": slot,
        "sample_offset": edit["sample_offset"],
        "inserted_samples": edit["inserted_samples"],
        "expected_extension_ms": 1000 * extension,
        "outside_target_edges": nearby_shift(before, after, slots, splice, extension),
        "draft_gap_extension_ms": None,
        "draft_gap_absolute_error_ms": None,
        "within_two_frames": None,
    }
    if not all(index in before and index in after and same_segments(before[index], after[index])
               for index in slots):
        return {**details, "status": "flanking_segments_not_stably_matched"}
    base = boundary(before[slot], before[slot + 1], splice, splice, before_rows)
    variant = boundary(after[slot], after[slot + 1], splice, splice + extension, after_rows)
    if (not base["contains_entire_splice"] or not variant["contains_entire_splice"]
            or base["intervening_drafted_events"] or variant["intervening_drafted_events"]):
        return {**details, "status": "draft_gap_does_not_isolate_splice", "original": base, "probe": variant}
    difference = variant["gap_ms"] - base["gap_ms"]
    error = abs(difference - 1000 * extension)
    return {
        **details, "status": "measured", "original": base, "probe": variant,
        "draft_gap_extension_ms": difference, "draft_gap_absolute_error_ms": error,
        "within_two_frames": error <= 2 * frame_ms + 1e-6,
    }


def analyze(root):
    source = rows(root / MANIFEST)
    drafts = {row["recording_id"]: row for row in rows(root / DRAFTS / "phone-drafts.jsonl")}
    events = defaultdict(list)
    for row in rows(root / DRAFTS / "alignments.jsonl"):
        events[row["recording_id"]].append(row)
    if not source or {row["recording_id"] for row in source} != set(drafts) or set(drafts) != set(events):
        raise ValueError("Pause manifest and draft recording coverage differs")
    frame_ms_set = {1000 * row["frame_s"] for row in drafts.values()}
    model_revisions = {row["model_revision"] for row in drafts.values()}
    if len(frame_ms_set) != 1 or len(model_revisions) != 1:
        raise ValueError("Audit requires one decoder model and frame step")
    frame_ms = next(iter(frame_ms_set))
    groups = defaultdict(dict)
    for row in source:
        identifier = row["recording_id"]
        if any(drafts[identifier][key] != row[key] for key in ("audio_path", "audio_sha256")):
            raise ValueError(f"{identifier}: acoustic draft came from different audio")
        if any(event["audio_sha256"] != row["audio_sha256"] for event in events[identifier]):
            raise ValueError(f"{identifier}: alignment came from different audio")
        audit = row["pause_audit"]
        groups[audit["pair_id"]][audit["role"]] = row
    pairs = [
        pair_summary(pair["original"], pair["probe"], events, frame_ms)
        for pair in groups.values()
    ]
    measured = [pair for pair in pairs if pair["status"] == "measured"]
    result = {
        "scope": ("Technical recovery of a fixed synthetic pause intervention on Stage 4-selected quiet "
                  "sites. Reuses the alignment model that nominated the eligible sites. Observed segments "
                  "are model drafts, and the audit contains no new perception or production judgments."),
        "model_revision": next(iter(model_revisions)),
        "decoder_frame_ms": frame_ms,
        "pair_count": len(pairs),
        "status_counts": dict(Counter(pair["status"] for pair in pairs)),
        "within_two_frames_count": sum(pair["within_two_frames"] for pair in measured),
        "median_draft_gap_absolute_error_ms": (
            median(pair["draft_gap_absolute_error_ms"] for pair in measured) if measured else None
        ),
        "pairs": pairs,
    }
    write_bytes(root / RESULTS, (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({key: result[key] for key in (
        "pair_count", "status_counts", "decoder_frame_ms", "within_two_frames_count",
        "median_draft_gap_absolute_error_ms",
    )}))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "analyze"])
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    {"prepare": prepare, "analyze": analyze}[args.command](args.root.resolve(strict=True))


if __name__ == "__main__":
    main()
