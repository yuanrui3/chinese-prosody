"""Test fixed rhythm and wording changes at independently annotated ends of parallel constructions."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import groupby, zip_longest
import json
from pathlib import Path
from random import Random
import re
from statistics import fmean, median
from tempfile import TemporaryDirectory

from . import quantitative_editorial_grammar as grammar
from .quantitative_fresh_triples import MODEL_SHA, TRAIN_SHA
from .quantitative_grammar_expansion import normalized_text

SEED = 20261124
CUES = "是以 是故 然則 至於 若夫 乃知 始知 豈知 故 然 遂 乃 獨 豈".split()
VARIANTS = str.maketrans("则于岂独", "則於豈獨")
METHODS = ("always6", "current", "plus_rhythm", "plus_wording", "plus_both")
BREAK = re.compile(r"[、，,；;：:。.!！?？\n]+")


def han_text(text):
    return "".join(filter(grammar.context.base.han, text))


def arm(text):
    lengths = [len(han_text(p)) for p in BREAK.split(text) if han_text(p)]
    word = han_text(text)
    if not word:
        raise ValueError("Every annotated arm needs Han text")
    cue_word = word.translate(VARIANTS)
    return (tuple(lengths), word[0], word[-1], next((c for c in CUES if cue_word.startswith(c)), ""))


def distance(a, b):
    pairs = list(zip_longest(a, b, fillvalue=0))
    return sum(abs(x - y) for x, y in pairs) / sum(max(x, y) for x, y in pairs)


def signals(arms):
    profiles = [a[0] for a in arms]
    last_step = distance(profiles[-2], profiles[-1])
    earlier = median(distance(a, b) for a, b in zip(profiles[:-2], profiles[1:-1]))
    rhythm = profiles[-1] not in profiles[:-1] and last_step > earlier
    a, b, c = arms[-3:]
    broken = [name for idx, name in ((1, "opening"), (2, "closing")) if a[idx] == b[idx] != c[idx]]
    cue = c[3] if c[3] and c[3] not in (a[3], b[3]) else ""
    return {
        "rhythm": rhythm,
        "wording": bool(broken or cue),
        "broken_anchors": broken,
        "new_cue": cue,
        "profiles": [list(p) for p in profiles],
        "last_distance": last_step,
        "earlier_median_distance": earlier,
    }


def index(rows, field):
    indexed = {field(r): r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError("Duplicate key in frozen inputs")
    return indexed


def target_key(row):
    return row["work_id"], row["id"]


def incomplete(row):
    return bool(row.get("incomplete") or row.get("missing") or row.get("lacuna") or "□" in row["text"])


def screen(rows, annotations, old):
    originals = index(rows, target_key)
    order = {key: i for i, key in enumerate(originals)}
    seen_sections = [k for k, _ in groupby(rows, key=lambda r: (r["work_id"], r["section"]))]
    if len(seen_sections) != len(set(seen_sections)):
        raise ValueError("Source section is not contiguous")
    reserved = {normalized_text(r) for r in old}
    candidates = defaultdict(list)
    omitted = []
    for num, r in enumerate(annotations):
        work = r["work_id"]
        members = r["members"]
        if (
            len(members) < 3
            or members[-1]["id"] != r["target_id"]
            or not r["boundary"]
            or not r["explanation"]
        ):
            raise ValueError(f"Invalid run boundary: {r}")
        spans = []
        pos = None
        reused_or_incomplete = False
        for m in members:
            k = (work, m["id"])
            row = originals[k]
            if row["section"] != r["section"] or not m["quote"]:
                raise ValueError(f"Member outside source section: {k}")
            text = row["text"]
            start_at = pos[1] if pos and pos[0] == order[k] else 0
            start = text.find(m["quote"], start_at)
            if start < 0 or (pos and order[k] < pos[0]):
                raise ValueError(f'Out-of-order or unmatched quotation: {k}, {m["quote"]}')
            if pos:
                last_row, last_end = pos
                if last_row == order[k]:
                    gap = text[last_end:start]
                else:
                    gap = (
                        rows[last_row]["text"][last_end:]
                        + "".join(x["text"] for x in rows[last_row + 1 : order[k]])
                        + text[:start]
                    )
                if han_text(gap):
                    raise ValueError(f"Unquoted intervening words in run at {k}: {gap}")
            pos = order[k], start + len(m["quote"])
            spans.append([m["id"], start, pos[1]])
            reused_or_incomplete |= incomplete(row) or normalized_text(row) in reserved
        if reused_or_incomplete:
            omitted.append(
                {
                    "work_id": work,
                    "id": r["target_id"],
                    "reason": "incomplete or previously used member unit",
                }
            )
            continue
        quotes = [m["quote"] for m in members]
        feature = signals([arm(q) for q in quotes])
        candidate = {
            "work_id": work,
            "id": r["target_id"],
            "ordinal": num,
            "section": r["section"],
            "spans": spans,
            "quotes": quotes,
            "unit_final": not han_text(text[pos[1] :]),
            "explanation": r["explanation"],
            "boundary": r["boundary"],
            **feature,
        }
        candidates[work, r["target_id"]].append(candidate)
    chosen = []
    for k, options in candidates.items():
        ordered = sorted(options, key=lambda r: (-r["spans"][-1][-1], -len(r["quotes"]), r["ordinal"]))
        chosen.append(ordered[0])
        omitted.extend(
            {"work_id": k[0], "id": k[1], "run": r["ordinal"], "reason": "shared target; rightmost rule"}
            for r in ordered[1:]
        )
    return {
        "annotations": len(annotations),
        "ends": sorted(chosen, key=lambda r: order[target_key(r)]),
        "omitted": omitted,
    }


def bounded(v):
    return min(7.0, max(1.0, v))


def forecasts(raw, rhythm, wording):
    return {
        "always6": 6.0,
        "current": bounded(raw),
        "plus_rhythm": bounded(raw + 0.25 * rhythm),
        "plus_wording": bounded(raw + 0.25 * wording),
        "plus_both": bounded(raw + 0.25 * (rhythm + wording)),
    }


def concord(pairs, pred):
    if not pairs:
        return None
    return fmean(0.5 if abs(pred[a] - pred[b]) <= 1e-10 else float(pred[a] > pred[b]) for a, b in pairs)


def groups_for(rows):
    works = defaultdict(list)
    for i, r in enumerate(rows):
        works[r["work_id"]].append(i)
    return works


def comparisons(rows, groups):
    return {
        w: [(a, b) for a in ix if rows[a]["score"] == 7 for b in ix if rows[b]["score"] == 6]
        for w, ix in groups.items()
    }


def metrics(rows):
    groups = groups_for(rows)
    pairs = comparisons(rows, groups)
    pooled_pairs = comparisons(rows, {"all": range(len(rows))})["all"]
    result = {
        "ends": len(rows),
        "works": len(groups),
        "scores": dict(Counter(r["score"] for r in rows)),
        "mixed_works": [w for w, v in pairs.items() if v],
        "within_work_pairs": sum(map(len, pairs.values())),
        "pooled_pairs": len(pooled_pairs),
        "by_work": {},
        "methods": {},
    }
    for w, ii in groups.items():
        result["by_work"][w] = {
            "n": len(ii),
            "scores": dict(Counter(rows[i]["score"] for i in ii)),
            "pairs": len(pairs[w]),
            "auc": {},
        }
    for m in METHODS:
        p = [r["predictions"][m] for r in rows]
        eligible = [i for i, r in enumerate(rows) if r["score"] in (6, 7)]
        work_auc = []
        work_mae = []
        high_mae = []
        for w, ii in groups.items():
            a = concord(pairs[w], p)
            result["by_work"][w]["auc"][m] = a
            if a is not None:
                work_auc.append(a)
            work_mae.append(fmean(abs(p[i] - rows[i]["score"]) for i in ii))
            hi = [i for i in ii if rows[i]["score"] in (6, 7)]
            if hi:
                high_mae.append(fmean(abs(p[i] - rows[i]["score"]) for i in hi))
        confusion = Counter(
            ("true7" if rows[i]["score"] == 7 else "true6") + ("_call7" if p[i] >= 6.5 else "_call6")
            for i in eligible
        )
        result["methods"][m] = {
            "within_work_auc": fmean(work_auc) if work_auc else None,
            "pooled_auc": concord(pooled_pairs, p),
            "macro_mae": fmean(work_mae) if work_mae else None,
            "macro_mae_6_7": fmean(high_mae) if high_mae else None,
            "confusion": dict(confusion),
        }
    counts = defaultdict(Counter)
    for r in rows:
        counts[f'{int(r["rhythm"])}{int(r["wording"])}'][r["score"]] += 1
    result["scores_by_rhythm_wording"] = dict(counts)
    return result


def controls(rows, observed):
    groups = groups_for(rows)
    pairs = {w: p for w, p in comparisons(rows, groups).items() if p}
    if not pairs:
        return {"draws": 0, "reason": "No work contains both 6 and 7"}
    original = observed["methods"]["current"]["within_work_auc"]
    gain = observed["methods"]["plus_both"]["within_work_auc"] - original
    bonuses = [0.25 * (r["rhythm"] + r["wording"]) for r in rows]
    encoded = [[arm(q) for q in r["quotes"]] for r in rows]
    output = {}
    high_groups = [[i for i in groups[w] if rows[i]["score"] in (6, 7)] for w in pairs]
    for mode in ("within_work_6_7_bonus", "within_work_all_bonus", "within_run_arm_order"):
        rng = Random(SEED)
        shuffled = []
        for _ in range(999):
            b = list(bonuses)
            if mode != "within_run_arm_order":
                for ii in high_groups if mode == "within_work_6_7_bonus" else groups.values():
                    v = [b[i] for i in ii]
                    rng.shuffle(v)
                    for i, new in zip(ii, v):
                        b[i] = new
            else:
                for i, seq in enumerate(encoded):
                    permuted = list(seq)
                    rng.shuffle(permuted)
                    z = signals(permuted)
                    b[i] = 0.25 * (z["rhythm"] + z["wording"])
            pred = [bounded(r["raw_current"] + v) for r, v in zip(rows, b)]
            shuffled.append(fmean(concord(p, pred) for p in pairs.values()) - original)
        output[mode] = {
            "draws": 999,
            "observed_gain": gain,
            "median_shuffled_gain": median(shuffled),
            "at_least_observed": sum(v >= gain - 1e-12 for v in shuffled),
        }
    return output


def run(root, inputs, output, screen_only):
    if (
        output.exists()
        or not inputs.resolve().is_relative_to(root)
        or not output.resolve().is_relative_to(root)
    ):
        raise ValueError("Choose an unused output and inputs inside the Gilbreth research project")
    hashes = {}

    def load(path, expected=None):
        data = path.read_bytes()
        h = sha256(data).hexdigest()
        hashes[str(path.relative_to(root))] = h
        if expected and h != expected:
            raise ValueError(f"Frozen checksum differs for {path.name}")
        return json.loads(data)

    archive = root / "results/grammatical-training-expansion-20261122"
    old = load(archive / "results/enriched-reference.json", TRAIN_SHA)
    for path in (
        archive / "inputs/train-b.json",
        archive / "inputs/holdout.json",
        root / "results/grammatical-patterns-20261122/inputs/fresh-witness.json",
        root / "results/editorial-context-20261122/inputs/fresh-witness.json",
        root / "results/dong-shaorong-holdout-20261122/witness.json",
        root / "results/fresh-three-line-transfer-20261122/inputs/witness.json",
    ):
        old.extend(load(path))
    rows = load(inputs / "witness.json")
    cards = load(inputs / "works.json")
    works = index(cards, lambda r: r["work_id"])
    if set(works) != {r["work_id"] for r in rows} or len({c["author"] for c in cards}) != len(cards):
        raise ValueError("Witness must have independent credited authors and a card for every work")
    if any(any(r[k] != works[r["work_id"]][k] for k in ("title", "author")) or "score" in r for r in rows):
        raise ValueError("Source metadata or label masking failed")
    for field in ("author", "title", "work_id"):
        if {c[field] for c in cards} & {r.get(field) for r in old}:
            raise ValueError(f"Prior work overlaps by {field}")
    info = screen(rows, load(inputs / "runs.json"), old)
    info["witness_sha256"] = hashes[str((inputs / "witness.json").relative_to(root))]
    if screen_only:
        save(output, info)
        return
    if info != load(inputs / "ending-screen.json"):
        raise ValueError("Sealed endpoint/feature mapping changed")
    if not info["ends"]:
        raise ValueError("No fresh endpoints")
    frozen = load(archive / "results/fresh-expanded-results.json", MODEL_SHA)["models"]["context_grammar"]
    lex, lexhash = grammar.context.base.lexicon_data(root)
    if lexhash != load(archive / "results/summary.json")["lexicon_sha256"] or frozen["names"] != list(
        grammar.MODEL_COLS["context_grammar"]
    ):
        raise ValueError("Historical lexicons or feature order changed")
    lines = grammar.context.describe(rows, lex)
    for line in lines:
        if incomplete(line.row):
            line.complete = False
    x, _ = grammar.matrix_rows(lines, lines, grammar.context.in_context(lines))
    raw = dict(zip([l.key for l in lines], grammar.context.predict(frozen, x)))
    packet = index(load(inputs / "packet.json"), lambda r: r["id"])
    labels = index(load(inputs / "verdict.json"), lambda r: r["id"])
    keys = index(load(inputs / "key.json"), target_key)
    if (
        set(packet) != set(labels)
        or set(keys) != set(raw)
        or len(keys) != len(packet)
        or {r["masked_id"] for r in keys.values()} != set(packet)
    ):
        raise ValueError("Frozen rating packet and key differ")
    for r in rows:
        mid = keys[target_key(r)]["masked_id"]
        item = packet[mid]
        label = labels[mid]
        if item["text"] != r["text"] or label["work_id"] != item["work_id"] or not label["reason"].strip():
            raise ValueError("Rating mapped to different source text")
        if incomplete(r):
            if label["score"] is not None:
                raise ValueError(f"Lacuna scored at {mid}")
        elif (
            not grammar.context.valid_score(label["score"])
            or not label["quote"]
            or label["quote"] not in r["text"]
        ):
            raise ValueError(f"Invalid rating evidence at {mid}")
    witness = index(rows, target_key)
    out = []
    for end in info["ends"]:
        k = target_key(end)
        mid = keys[k]["masked_id"]
        lab = labels[mid]
        out.append(
            {
                **end,
                "text": witness[k]["text"],
                "masked_id": mid,
                "score": lab["score"],
                "rating_reason": lab["reason"],
                "raw_current": raw[k],
                "predictions": forecasts(raw[k], end["rhythm"], end["wording"]),
            }
        )
    strata = {
        name: metrics([e for e in out if works[e["work_id"]]["stratum"] == name])
        for name in sorted({c["stratum"] for c in cards})
    }
    main = metrics(out)
    result = {
        "methods": list(METHODS),
        "summary": main,
        "by_stratum": strata,
        "unit_final_only": metrics([r for r in out if r["unit_final"]]),
        "without_mixed_compositions": metrics(
            [r for r in out if not works[r["work_id"]].get("mixed_composition", False)]
        ),
        "controls": controls(out, main),
        "stratum_controls": {
            name: controls([r for r in out if works[r["work_id"]]["stratum"] == name], stats)
            for name, stats in strata.items()
        },
        "ends": out,
        "works": cards,
        "screen": info,
        "lexicon_sha256": lexhash,
        "sha256": hashes,
        "seed": SEED,
        "bonus_per_flag": 0.25,
    }
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "result"
        stage.mkdir()
        save(stage / "results.json", result)
        headline = [
            "GILBRETH | PATTERN ENDINGS",
            f"{len(rows)} source units | {len(works)} works | {len(out)} distinct endings",
            f'Editorial scores: {dict(sorted(main["scores"].items()))}',
            f'Mixed works: {len(main["mixed_works"])} | within-work 7/6 pairs: {main["within_work_pairs"]}',
            "Method          Within AUC  Pooled AUC  All MAE",
        ]
        for m in METHODS:
            s = main["methods"][m]
            vals = [
                "   n/a" if s[k] is None else f"{s[k]:6.3f}"
                for k in ("within_work_auc", "pooled_auc", "macro_mae")
            ]
            headline.append(f"{m:14s} {vals[0]}      {vals[1]}     {vals[2]}")
        (stage / "summary.txt").write_text("\n".join(headline) + "\n")
        reading = [
            "Written 音律美 | frozen pattern-ending comparison | same complete target unit for each forecast."
        ]
        for r in out:
            pred = r["predictions"]
            reading.extend(
                [
                    "",
                    f'《{works[r["work_id"]]["title"]}》 {r["id"]} ({r["masked_id"]})  {r["text"]}',
                    " → ".join(r["quotes"]),
                    f'Written rating {r["score"]} | current {pred["current"]:.2f} | plus ending change {pred["plus_both"]:.2f} | always 6',
                    f'Rhythm change {r["rhythm"]} | wording change {r["wording"]} | ends full unit {r["unit_final"]}',
                    r["boundary"],
                    r["rating_reason"],
                ]
            )
        (stage / "reading-comparison.txt").write_text("\n".join(reading) + "\n")
        stage.rename(output)


def save(path, obj):
    with path.open("x", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "inputs", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--screen", action="store_true")
    args = parser.parse_args()
    run(args.root.resolve(strict=True), args.inputs.resolve(), args.output.resolve(), args.screen)
