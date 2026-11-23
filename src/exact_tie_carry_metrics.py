"""Evaluate the fixed thought-development bonus inside exact same-work forecast ties."""

from collections import Counter, defaultdict
from random import Random
from statistics import fmean, median

from .ending_function_metrics import adjusted
from .quantitative_top_score_calibration import complete_cases, evaluate, ratio
from .written_carry_metrics import DRAWS, ROLES, SEED, agreement


def exact_groups(rows):
    """Check a one-to-one correspondence between work-local group IDs and binary scores."""
    blocks = defaultdict(list)
    scores = {}
    names = {}
    for i, row in enumerate(rows):
        work, label = row["work_id"], row["group"]
        if not isinstance(label, str) or not label:
            raise ValueError("Every target needs a tie group")
        key = work, label
        value = float(row["current"]).hex()
        if scores.setdefault(key, value) != value or names.setdefault((work, value), label) != label:
            raise ValueError(f"Tie group disagrees with full-precision forecast: {key}")
        blocks[key].append(i)
    return blocks


def decisions(pairs, values):
    correct = sum(values[h] > values[l] for h, l in pairs)
    wrong = sum(values[h] < values[l] for h, l in pairs)
    tied = len(pairs) - correct - wrong
    units = {i for pair in pairs for i in pair}
    return {
        "n_pairs": len(pairs), "n_units": len(units), "correct": correct, "wrong": wrong, "tied": tied,
        "accuracy": ratio(correct + 0.5 * tied, len(pairs)),
        "fraction_resolved": ratio(correct + wrong, len(pairs)),
        "accuracy_among_resolved": ratio(correct, correct + wrong),
    }


def ranking(rows, blocks, roles, values, subset):
    groups = []
    by_work_pairs = defaultdict(list)
    for (work, label), members in blocks.items():
        sevens = [i for i in members if rows[i]["score"] == 7]
        sixes = [i for i in members if rows[i]["score"] == 6]
        pairs = [(h, l) for h in sevens for l in sixes]
        if subset != "primary":
            pairs = [(h, l) for h, l in pairs if roles[h] is not None and roles[l] is not None]
        if subset == "opposite":
            pairs = [(h, l) for h, l in pairs if roles[h] != roles[l]]
        by_work_pairs[work].extend(pairs)
        groups.append({
            "work_id": work, "group": label, "score_hex": float(rows[members[0]]["current"]).hex(),
            "n_targets": len(members), "ratings": dict(Counter(rows[i]["score"] for i in members)),
            **decisions(pairs, values),
        })
    by_work = {w: decisions(pairs, values) for w, pairs in by_work_pairs.items()}
    pool = decisions([pair for pairs in by_work_pairs.values() for pair in pairs], values)
    informative = [w for w in by_work if by_work[w]["n_pairs"]]
    macro = fmean(by_work[w]["accuracy"] for w in informative) if informative else None
    baseline = 0.5 if informative else None
    result = {
        **pool, "informative_works": informative, "informative_groups": sum(g["n_pairs"] > 0 for g in groups),
        "methods": {"always6": {"macro": baseline, "pooled": baseline},
                    "current": {"macro": baseline, "pooled": baseline},
                    "augmented": {"macro": macro, "pooled": pool["accuracy"]}},
        "by_work": by_work, "by_group": groups,
    }
    return result, by_work_pairs


def shuffle_control(rows, blocks, pairs_by_work, flags, roles, observed):
    """Keep true 7/6 pairs fixed and randomize eligible flags only within each work-score block."""
    result = dict(seed=SEED, draws=0, observed_gain=None, median_gain=None, at_least_observed=None, p_upper=None)
    pairs = [ps for ps in pairs_by_work.values() if ps]
    if not pairs:
        return result
    current = [row["current"] for row in rows]
    exchangeable = [[i for i in ii if roles[i] is not None and rows[i]["score"] in (6, 7)]
                    for ii in blocks.values()]
    rng = Random(SEED)
    gains = []
    for _ in range(DRAWS):
        permuted = flags.copy()
        for indices in exchangeable:
            values = [flags[i] for i in indices]
            rng.shuffle(values)
            for i, value in zip(indices, values):
                permuted[i] = value
        predictions = adjusted(current, permuted)
        scores = [decisions(ps, predictions)["accuracy"] for ps in pairs]
        gains.append(fmean(scores) - 0.5)
    gain = observed - 0.5
    tail = sum(x >= gain - 1e-12 for x in gains)
    result.update(draws=DRAWS, observed_gain=gain, median_gain=median(gains), at_least_observed=tail,
                  p_upper=(tail + 1) / (DRAWS + 1))
    return result


def benchmark(rows):
    """Score all rated targets; primary includes uncertain and disputed targets with zero bonus."""
    rows, missing = complete_cases(rows)
    if missing:
        raise ValueError("Provide complete scored targets and record missing units in the source manifest")
    blocks = exact_groups(rows)
    coding, roles = agreement(rows)
    current = [r["current"] for r in rows]
    flags = [int(role == "advance") for role in roles]
    augmented = adjusted(current, flags)
    primary, pairs = ranking(rows, blocks, roles, augmented, "primary")
    result = {
        "n_targets": len(rows), "n_works": len({w for w, _ in blocks}), "n_groups": len(blocks),
        "ratings": dict(Counter(row["score"] for row in rows)), "agreement": coding,
        "primary": primary, "sensitivity": {},
        "permutation": shuffle_control(rows, blocks, pairs, flags, roles, primary["methods"]["augmented"]["macro"]),
        "thresholds": {m: evaluate(rows, [x >= 6.5 for x in vals]) for m, vals in
                       (("always6", [6.0] * len(rows)), ("current", current), ("augmented", augmented))},
        "rows": [{**row, "role": role, "augmented": score} for row, role, score in zip(rows, roles, augmented)],
    }
    for subset in ("consensus_only", "opposite"):
        result[subset] = ranking(rows, blocks, roles, augmented, subset)[0]
    for coder in ("coder1", "coder2"):
        labels = [ROLES[r[coder]] for r in rows]
        pred = adjusted(current, [int(role == "advance") for role in labels])
        result["sensitivity"][coder] = ranking(rows, blocks, labels, pred, "primary")[0]
    return result
