"""Evaluate a prospective meaning-turn annotation against masked written musicality grades."""

from argparse import ArgumentParser
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from random import Random
from statistics import fmean

from .semantic_turn_pairs import normalized
from .semantic_turn_relation import PROBES
from .yu_review_transfer import by_work, compare, digest, prediction, read, summarize, write


OPPOSITES = "外內 外中 前後 始終 有無 得失 去來 進退 盛衰 榮辱 存亡 生死 開閉 高下 遠近 憂喜 成敗 古今 彼此 難易 上下".split()
NAMES = ("always_six", "current", "qwen_turn", "lexical", "second_reading")


def lexical(first, second):
    a, b = normalized(first)[-2:], normalized(second)[-2:]
    return any((x in a and y in b) or (y in a and x in b) for x, y in OPPOSITES)


def opaque(side, ident):
    return sha256(f"20261125/audit/{side}/{ident}".encode()).hexdigest()


def audit_packet(run):
    packet = read(run / "inputs/pair-packet.json")
    controls = sorted(packet["foils"], key=lambda r: opaque("take", r["id"]))[:20]
    key, rows = {}, []
    for side, cases in (("true", packet["true"]), ("foils", controls)):
        for r in cases:
            label = opaque(side, r["id"])[:12]
            if label in key:
                raise ValueError("Audit ID collision")
            key[label] = [side, r["id"]]
            rows.append({"id": label, "marked": r["marked"]})
    write(run / "private/audit-key.json", key)
    write(run / "inputs/audit-packet.json", sorted(rows, key=lambda r: r["id"]))


def shuffle_test(rows, observed):
    if observed is None:
        return None
    strata = defaultdict(list)
    for r in rows:
        strata[r["work_id"], r["route"]].append(r)
    works, rng = by_work(rows), Random(20261125)
    at_least = 0
    for _ in range(999):
        for stratum in strata.values():
            flags = [r["qwen_flag"] for r in stratum]
            rng.shuffle(flags)
            for r, flag in zip(stratum, flags):
                r["shuffle"] = prediction(r["current"], flag)
        work = [compare(g, "shuffle")["ordering"] for g in works.values()]
        at_least += fmean(x for x in work if x is not None) >= observed - 1.e-12
    for r in rows:
        del r["shuffle"]
    return {"draws": 999, "at_least": at_least, "p": (1+at_least)/1000}


def indexed(seq):
    result = {r["id"]: r for r in seq}
    if len(result) != len(seq):
        raise ValueError("Duplicate sentence IDs")
    return result


def table(first, second):
    if set(first) != set(second):
        raise ValueError("Different IDs in paired comparison")
    counts = Counter((first[i], second[i]) for i in first)
    return dict(n=len(first), both=counts[True, True], first_only=counts[True, False],
                second_only=counts[False, True], neither=counts[False, False])


def evaluate(run):
    units = indexed(read(run / "inputs/corpus.json"))
    targets = {i: u for i, u in units.items() if u["target"]}
    packet = read(run / "inputs/pair-packet.json")
    pairs = indexed(packet["true"])
    foil_ids = set(indexed(packet["foils"]))
    rel = read(run / "private/semantic-relation.json")
    base = read(run / "results/baseline.json")
    editorial = read(run / "private/editorial.json")
    blind = read(run / "private/audit-grades.json")
    key = read(run / "private/audit-key.json")
    audit = {"true": {}, "foils": {}}
    if set(blind) != set(key):
        raise ValueError("Missing audit grades")
    for k, (side, i) in key.items():
        vote = blind[k]["turn"]
        if type(vote) is not bool or not blind[k]["reason"].strip():
            raise ValueError(f"Invalid independent semantic annotation for {k}")
        audit[side][i] = vote
    votes = {side: indexed(rel[side]) for side in ("true", "foils", "probes")}
    if not (set(base) == set(units) and set(pairs) == set(targets) == set(editorial)
            == set(votes["true"]) == set(audit["true"]) and set(votes["foils"]) == foil_ids
            and set(audit["foils"]) <= foil_ids):
        raise ValueError("Corpus, packet, annotations and baseline do not align")
    for side in votes.values():
        for v in side.values():
            if (len(v["flags"]) != 2 or any(type(f) is not bool for f in v["flags"])
                    or v["consensus"] != all(v["flags"])):
                raise ValueError("Invalid dual-prompt decision")
    if rel["packet_sha256"] != digest(run / "inputs/pair-packet.json"):
        raise ValueError("Classifier packet differs")
    rows = []
    for i, u in targets.items():
        e, p, q = editorial[i], pairs[i], votes["true"][i]
        if (type(e["score"]) is not int or not 1 <= e["score"] <= 7 or not e["reason"].strip()
                or not e["quote"] or e["quote"] not in u["text"] or not 1 <= base[i] <= 7
                or p["text"] != u["text"]):
            raise ValueError(f"Invalid reference, input text or forecast for {i}")
        lit, secondary = lexical(p["first"], p["second"]), audit["true"][i]
        rows.append({**u, "grade": e["score"], "reason": e["reason"], "quote": e["quote"],
                     "route": p["route"], "width": p["width"], "first": p["first"],
                     "second": p["second"], "current": base[i], "always_six": 6.0,
                     "qwen_flag": q["consensus"], "audit_flag": secondary, "lexical_flag": lit,
                     "qwen_turn": prediction(base[i], q["consensus"]), "lexical": prediction(base[i], lit),
                     "second_reading": prediction(base[i], secondary)})
    stats = {m: summarize(rows, m) for m in NAMES}
    true = {i: v["consensus"] for i, v in votes["true"].items()}
    foils = {i: v["consensus"] for i, v in votes["foils"].items()}
    def matched(subset, donor):
        return table({i: subset[i] for i in donor}, donor)
    counts = {}
    for grade in sorted({r["grade"] for r in rows}):
        group = [r for r in rows if r["grade"] == grade]
        counts[grade] = {"n": len(group), **{k: sum(r[k] for r in group)
                         for k in ("qwen_flag", "audit_flag", "lexical_flag")}}
    report = {"models": stats, "coverage_by_grade": counts,
              "routes": dict(Counter(r["route"] for r in rows)),
              "votes": {k: dict(Counter(''.join('Y' if x else 'N' for x in v["flags"])
                                           for v in votes[k].values())) for k in votes},
              "qwen_and_audit": table(true, audit["true"]),
              "true_and_donor_qwen": matched(true, foils),
              "true_and_donor_audit": matched(audit["true"], audit["foils"]),
              "probes": {k: {"expected": expected, "flags": votes["probes"][k]["flags"]}
                         for k, _, expected in PROBES},
              "shuffle": shuffle_test(rows, stats["qwen_turn"]["ordering"])}
    write(run / "private/joined.json", rows)
    write(run / "results/comparison.json", report)


if __name__ == "__main__":
    p = ArgumentParser()
    p.add_argument("action", choices=("mask", "evaluate"))
    p.add_argument("run", type=Path)
    args = p.parse_args()
    (audit_packet if args.action == "mask" else evaluate)(args.run)
