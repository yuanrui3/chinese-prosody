"""Compare fixed forecasts against masked whole-sentence editorial ratings."""

from collections import Counter
from math import comb, isfinite
from pathlib import Path
import sys

from .semantic_turn_pairs import normalized, phrases
from .semantic_turn_relation import PROBES
from .semantic_turn_test import indexed, lexical, shuffle_test, table
from .semicolon_turn_sources import closing_pair
from .yu_review_transfer import by_work, digest, prediction, read, summarize, write


MODELS = ("always_six", "current", "qwen_turn", "lexical")


def verified_votes(records):
    votes = indexed(records)
    for row in votes.values():
        flags = row["flags"]
        if (len(flags) != 2 or any(type(x) is not bool for x in flags)
                or type(row["consensus"]) is not bool or row["consensus"] != all(flags)):
            raise ValueError("Malformed dual-prompt vote")
    return {i: r["consensus"] for i, r in votes.items()}


def ordering_changes(rows):
    changes = Counter()
    for group in by_work(rows).values():
        for seven in (r for r in group if r["grade"] == 7):
            for six in (r for r in group if r["grade"] == 6):
                def outcome(model):
                    a, b = seven[model], six[model]
                    return "win" if a > b else "loss" if a < b else "tie"
                changes[outcome("current") + "_to_" + outcome("qwen_turn")] += 1
    return dict(sorted(changes.items()))


def evaluate(run):
    for name, expected in read(run / "inputs/source-seal.json").items():
        if digest(run / "inputs" / name) != expected:
            raise ValueError(f"Changed frozen input: {name}")
    units = indexed(read(run / "inputs/corpus.json"))
    target = {i: r for i, r in units.items() if r["target"]}
    packet = read(run / "inputs/pair-packet.json")
    pairs, donors = indexed(packet["true"]), indexed(packet["foils"])
    rel = read(run / "private/semantic-relation.json")
    if (digest(run / "inputs/pair-packet.json") != rel["packet_sha256"]
            or digest(run / "seals/relation-card.json") != rel["card_sha256"]):
        raise ValueError("Changed classifier or pair packet")
    real, foil, probes = [verified_votes(rel[name]) for name in ("true", "foils", "probes")]
    base = read(run / "results/baseline.json")
    editorial = read(run / "private/editorial.json")
    if not (target.keys() == pairs.keys() == real.keys() == editorial.keys()
            and foil.keys() == donors.keys() <= target.keys() and units.keys() == base.keys()
            and probes.keys() == {i for i, _, _ in PROBES}):
        raise ValueError("Source, reference, classifier or forecast IDs differ")
    rows = []
    for i, unit in target.items():
        reference, pair = editorial[i], closing_pair(unit["text"])
        if (pair is None or pairs[i] != {"id": i, **pair} or not isfinite(base[i])
                or not 1 <= base[i] <= 7 or type(reference["score"]) is not int
                or not 1 <= reference["score"] <= 7 or not reference["reason"].strip()
                or not reference["quote"].strip() or reference["quote"] not in unit["text"]):
            raise ValueError(f"Invalid target or reference: {i}")
        if i in donors:
            d = donors[i]
            source = units[d["donor_id"]]
            if (source["id"] == i or source["work_id"] != unit["work_id"]
                    or d["first"] != pair["first"] or len(normalized(d["second"])) != pair["width"]
                    or normalized(d["second"]) in {p[3] for p in phrases(unit["text"])}
                    or d["second"] not in {p[2] for p in phrases(source["text"])}):
                raise ValueError(f"Invalid same-work replacement: {i}")
        cue = lexical(pair["first"], pair["second"])
        rows.append(dict(**unit, grade=reference["score"], quote=reference["quote"],
                         reason=reference["reason"], first=pair["first"], second=pair["second"],
                         width=pair["width"], route=pair["route"], qwen_flag=real[i], lexical_flag=cue,
                         current=base[i], qwen_turn=prediction(base[i], real[i]),
                         lexical=prediction(base[i], cue), always_six=6.0))
    stats = {model: summarize(rows, model) for model in MODELS}
    observed = stats["qwen_turn"]["ordering"]
    controls = table({i: real[i] for i in foil}, foil)
    discordant = controls["first_only"] + controls["second_only"]
    controls["paired_exact_two_sided_p"] = min(1., 2 * sum(comb(discordant, k) for k in
        range(min(controls["first_only"], controls["second_only"]) + 1)) / 2**discordant)
    grade_counts = {}
    for grade in sorted({r["grade"] for r in rows}):
        group = [r for r in rows if r["grade"] == grade]
        grade_counts[grade] = dict(n=len(group), flagged=sum(r["qwen_flag"] for r in group),
                                  lexical=sum(r["lexical_flag"] for r in group))
    report = dict(models=stats, by_grade=grade_counts, true_and_donor=controls,
                  ordering_changes=ordering_changes(rows), widths=dict(Counter(r["width"] for r in rows)),
                  probes={i: dict(expected=expected, observed=probes[i]) for i, _, expected in PROBES},
                  shuffle=shuffle_test(rows, observed))
    write(run / "private/joined.json", rows)
    write(run / "results/comparison.json", report)


if __name__ == "__main__":
    evaluate(Path(sys.argv[1]))
