"""Test a fixed two-part cadence hypothesis from the author's written Yu Xin review."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from random import Random
import re
from statistics import fmean

from data.phonology.annotate import han


BONUS = 0.75
MODELS = ("always_six", "current", "balanced", "repeated_pace")
HINGES = frozenset("而則以於于為爲無非")


def signals(text):
    parts, boundaries = [], []
    for fragment in re.split(r"([，,、：:；;。！？.!?])", text):
        if fragment in {"；", ";"}:
            boundaries.append(len(parts))
        chars = "".join(c for c in fragment if han(c))
        if chars:
            parts.append(chars)
    n = len(parts)
    info = {"phrases": n, "balanced": False, "repeated_pace": False,
            "route": None, "lengths": None}
    if n not in (2, 4) or any(b != n // 2 for b in boundaries):
        return info
    left = "".join(parts[:n // 2])
    right = "".join(parts[n // 2:])
    info["balanced"] = abs(len(left) - len(right)) <= 2
    if n == 4:
        candidates = [("four_phrases", list(map(len, parts)))]
    else:
        candidates = [("shared_hinge", [i, len(left)-i, i, len(right)-i])
                      for i, (a, b) in enumerate(zip(left, right), 1)
                      if a == b and a in HINGES]
    for route, lengths in candidates:
        a, b, c, d = lengths
        if min(lengths) >= 2 and abs(a-c) <= 2 and abs(b-d) <= 1 and (a-b)*(c-d) > 0:
            info.update(repeated_pace=True, route=route, lengths=lengths)
            break
    return info


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def discovery(checkpoint):
    grades = read(checkpoint / "author-review.json")["ratings"]
    source = read(checkpoint / "units.json")
    selected = []
    for unit in source:
        grade = grades[unit["id"]]["author"]
        if grade is not None:
            selected.append({**unit, "grade": grade, **signals(unit["text"])})
    if Counter(r["grade"] for r in selected) != {6: 11, 7: 11}:
        raise ValueError("The frozen author's review must contain eleven 6s and eleven 7s.")
    return {
        "review_hash": digest(checkpoint / "author-review.json"),
        "counts": {s: {g: sum(r["grade"] == g and (s == "all" or r["section"] == s)
                              and r["repeated_pace"] for r in selected) for g in (6, 7)}
                   for s in ("all", "序", "賦")},
        "selected": selected,
    }


def prepare(run):
    corpus = read(run / "inputs/corpus.json")
    out = {r["id"]: signals(r["text"]) for r in corpus}
    if len(out) != len(corpus):
        raise ValueError("Duplicate sentence ID in the corpus.")
    write(run / "private/signals.json", out)


def prediction(base, flag):
    return min(7, base + BONUS) if flag else base


def by_work(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["work_id"]].append(row)
    return dict(groups)


def compare(group, model):
    seven = [r[model] for r in group if r["grade"] == 7]
    six = [r[model] for r in group if r["grade"] == 6]
    counts = Counter((a > b) - (a < b) for a in seven for b in six)
    n = len(seven) * len(six)
    return {"pairs": n, "correct": counts[1], "tied": counts[0], "inverted": counts[-1],
            "ordering": (counts[1] + counts[0] / 2) / n if n else None}


def summarize(rows, model):
    groups = by_work(rows)
    work = {}
    for key, group in groups.items():
        work[key] = {
            **compare(group, model), "n": len(group),
            "mae": fmean(abs(r[model] - r["grade"]) for r in group),
            "sevens": sum(r["grade"] == 7 for r in group),
            "sixes": sum(r["grade"] == 6 for r in group),
            "caught": sum(r[model] >= 6.5 and r["grade"] == 7 for r in group),
            "false_on_sixes": sum(r[model] >= 6.5 and r["grade"] == 6 for r in group),
            "false_on_lower": sum(r[model] >= 6.5 and r["grade"] < 7 for r in group),
        }
    def order(works):
        usable = [w["ordering"] for w in works if w["ordering"] is not None]
        return fmean(usable) if usable else None
    counts = ("n", "pairs", "correct", "tied", "inverted", "sevens", "sixes",
              "caught", "false_on_sixes", "false_on_lower")
    return {**{k: sum(w[k] for w in work.values()) for k in counts},
            "ordering": order(work.values()), "mae": fmean(w["mae"] for w in work.values()),
            "informative_works": sum(w["pairs"] > 0 for w in work.values()),
            "by_work": work, "leave_one_out": {
                k: order(v for j, v in work.items() if j != k) for k in work}}


def shuffled_tail(rows, observed):
    if observed is None:
        return None
    rng = Random(20261124)
    groups, strata = by_work(rows), defaultdict(list)
    for r in rows:
        category = r["phrases"] if r["phrases"] in (2, 4) else 0
        strata[(r["work_id"], category)].append(r)
    at_least = 0
    for _ in range(999):
        for group in strata.values():
            flags = [r["matched"] for r in group]
            rng.shuffle(flags)
            for r, flag in zip(group, flags):
                r["permuted"] = prediction(r["current"], flag)
        orders = [compare(g, "permuted")["ordering"] for g in groups.values()]
        at_least += fmean(x for x in orders if x is not None) >= observed - 1e-12
    for r in rows:
        r.pop("permuted", None)
    return {"draws": 999, "at_least": at_least, "p": (at_least+1)/1000}


def evaluate(run):
    units = read(run / "inputs/corpus.json")
    baseline = read(run / "results/baseline.json")
    flags = read(run / "private/signals.json")
    editorial = read(run / "private/editorial.json")
    targets = [u for u in units if u["target"]]
    all_ids = {u["id"] for u in units}
    if (len(all_ids) != len(units) or set(baseline) != all_ids or set(flags) != all_ids
            or set(editorial) != {u["id"] for u in targets}):
        raise ValueError("The corpus, forecasts, features and editorial packet do not align.")
    rows = []
    for u in targets:
        i = u["id"]
        grade = editorial[i]["score"]
        base = baseline[i]
        if (type(grade) is not int or not 1 <= grade <= 7 or not editorial[i]["reason"].strip()
                or not isfinite(base) or not 1 <= base <= 7):
            raise ValueError(f"Invalid reference or baseline for {i}")
        f = flags[i]
        rows.append({**u, "grade": grade, "reason": editorial[i]["reason"], "always_six": 6.0,
                     "matched": f["repeated_pace"], "phrases": f["phrases"], "route": f["route"],
                     "current": base, "balanced": prediction(base, f["balanced"]),
                     "repeated_pace": prediction(base, f["repeated_pace"])})
    stats = {m: summarize(rows, m) for m in MODELS}
    report = {
        "distribution": dict(sorted(Counter(r["grade"] for r in rows).items())),
        "coverage": dict(Counter(r["route"] or "unmatched" for r in rows)),
        "coverage_by_grade": {g: sum(r["grade"] == g and r["matched"] for r in rows)
                              for g in sorted({r["grade"] for r in rows})},
        "balanced_count": sum(flags[r["id"]]["balanced"] for r in rows),
        "models": stats, "shuffle": shuffled_tail(rows, stats["repeated_pace"]["ordering"]),
        "hashes": {f: digest(run / f) for f in ("inputs/corpus.json", "inputs/reading.json",
                   "results/baseline.json", "private/signals.json", "private/editorial.json",
                   "code/research/yu-review-transfer.md")}}
    write(run / "results/comparison.json", report)
    write(run / "private/joined.json", rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("discovery", "prepare", "evaluate"))
    p.add_argument("run", type=Path)
    p.add_argument("--checkpoint", type=Path)
    args = p.parse_args()
    if args.action == "discovery":
        result = discovery(args.checkpoint)
        write(args.run / "private/discovery.json", result)
        print(result["counts"])
    elif args.action == "prepare":
        prepare(args.run)
    else:
        evaluate(args.run)
