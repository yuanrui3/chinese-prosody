"""Evaluate a fixed advance-of-thought bonus on separately annotated adjacent lines."""

from collections import Counter
from random import Random
from statistics import fmean, median

from .ending_function_metrics import adjusted, errors
from .quantitative_pattern_endings import comparisons, concord, groups_for
from .quantitative_top_score_calibration import complete_cases


CATEGORIES = ("advance", "restate", "parallel", "uncertain")
STATES = ("correct", "tied", "wrong")
ROLES = {"advance": "advance", "parallel": "nonadvance", "restate": "nonadvance", "uncertain": None}
DRAWS = 999
SEED = 20261122


def agreement(rows):
    matrix = {a: dict.fromkeys(CATEGORIES, 0) for a in CATEGORIES}
    flags = []
    for row in rows:
        a, b = row["coder1"], row["coder2"]
        if a not in ROLES or b not in ROLES:
            raise ValueError(f"Unknown thought relation at {row['id']}")
        matrix[a][b] += 1
        flags.append(ROLES[a] if ROLES[a] == ROLES[b] else None)
    n = len(rows)
    exact = sum(matrix[a][a] for a in CATEGORIES)
    expected_numerator = sum(
        sum(matrix[a].values()) * sum(matrix[b][a] for b in CATEGORIES) for a in CATEGORIES
    )
    denom = n * n - expected_numerator
    return (
        {
            "n": n,
            "exact": exact,
            "matrix": matrix,
            "kappa": (exact * n - expected_numerator) / denom if denom else None,
            "exact_fraction": exact / n if n else None,
            "eligible": sum(r is not None for r in flags),
            "abstain": flags.count(None),
        },
        flags,
    )


def status(pair, pred):
    high, low = pair
    delta = pred[high] - pred[low]
    if abs(delta) <= 1e-10:
        return "tied"
    return "correct" if delta > 0 else "wrong"


def transitions(pairs, pred):
    counts = {label: dict.fromkeys(STATES, 0) for label in STATES}
    for pair in pairs:
        counts[status(pair, pred["current"])][status(pair, pred["augmented"])] += 1
    return counts


def summarize(pool_by_work, pooled, pred, roles):
    """Pools are kept distinct; comparisons inside a work need not have independent units."""
    pairs = [pair for group in pool_by_work.values() for pair in group]
    by_work = {w: {"pairs": len(ps), "methods": {}} for w, ps in pool_by_work.items()}
    informative = [w for w, group in pool_by_work.items() if group]
    methods = {}
    for method, values in pred.items():

        def accuracy(ps):
            if method == "role_only" and any(roles[i] is None for pair in ps for i in pair):
                return None
            return concord(ps, values)

        per_work = []
        for w, ps in pool_by_work.items():
            score = accuracy(ps)
            by_work[w]["methods"][method] = score
            if ps:
                per_work.append(score)
        macro = fmean(per_work) if per_work and None not in per_work else None
        methods[method] = {"macro": macro, "within_pooled": accuracy(pairs), "pooled_all": accuracy(pooled)}
    different = [
        (a, b) for a, b in pairs if roles[a] is not None and roles[b] is not None and roles[a] != roles[b]
    ]
    high_advance = sum(roles[a] == "advance" for a, _ in different)
    return {
        "within_pairs": len(pairs),
        "informative_works": informative,
        "pooled_pairs": len(pooled),
        "advance_7_pairs": high_advance,
        "nonadvance_7_pairs": len(different) - high_advance,
        "transitions": transitions(pairs, pred),
        "methods": methods,
        "by_work": by_work,
    }


def permutation(rows, groups, fixed_pairs, roles, pred, primary):
    """Reassign only high-grade eligible role indicators within work; keep the primary pairs fixed."""
    fixed = [ps for ps in fixed_pairs.values() if ps]
    result = {
        "draws": 0,
        "seed": SEED,
        "observed_gain": None,
        "median_gain": None,
        "at_least_observed": None,
        "p_upper": None,
    }
    if not fixed:
        return result
    current = primary["methods"]["current"]["macro"]
    observed = primary["methods"]["augmented"]["macro"] - current
    blocks = [
        [i for i in ii if rows[i]["score"] in (6, 7) and roles[i] is not None] for ii in groups.values()
    ]
    rng = Random(SEED)
    gains = []
    for _ in range(DRAWS):
        signals = list(pred["role_only"])
        for indices in blocks:
            shuffled = [signals[i] for i in indices]
            rng.shuffle(shuffled)
            for i, v in zip(indices, shuffled):
                signals[i] = v
        forecasts = adjusted(pred["current"], signals)
        gains.append(fmean(concord(ps, forecasts) for ps in fixed) - current)
    tail = sum(gain >= observed - 1e-12 for gain in gains)
    result.update(
        draws=DRAWS,
        observed_gain=observed,
        median_gain=median(gains),
        at_least_observed=tail,
        p_upper=(1 + tail) / (1 + DRAWS),
    )
    return result


def study(rows, roles, with_control):
    scores = [r["score"] for r in rows]
    current = [r["current"] for r in rows]
    signals = [int(r == "advance") for r in roles]
    pred = {
        "always6": [6.0] * len(rows),
        "current": current,
        "augmented": adjusted(current, signals),
        "role_only": signals,
    }
    groups = groups_for(rows)
    per_work = comparisons(rows, groups)
    pooled = comparisons(rows, {"all": range(len(rows))})["all"]
    eligible = {w: [i for i in indices if roles[i] is not None] for w, indices in groups.items()}
    filters = {
        "all": lambda a, b: True,
        "eligible": lambda a, b: roles[a] is not None and roles[b] is not None,
        "primary": lambda a, b: roles[a] is not None and roles[b] is not None and roles[a] != roles[b],
    }
    filters["tied_eligible"] = lambda a, b: current[a] == current[b] and filters["eligible"](a, b)
    filters["tied_opposite"] = lambda a, b: current[a] == current[b] and filters["primary"](a, b)
    numeric = {name: v for name, v in pred.items() if name != "role_only"}
    report = {
        "n": len(rows),
        "works": len(groups),
        "eligible_count": sum(map(len, eligible.values())),
        "scores_by_role": {
            r or "abstain": dict(Counter(y for role, y in zip(roles, scores) if role == r))
            for r in ("advance", "nonadvance", None)
        },
        "error": {"all": errors(scores, groups, numeric), "eligible": errors(scores, eligible, numeric)},
    }
    for name, select in filters.items():
        pairs = {w: [p for p in ps if select(*p)] for w, ps in per_work.items()}
        report[name] = summarize(pairs, [p for p in pooled if select(*p)], pred, roles)
        if name == "primary" and with_control:
            report["permutation"] = permutation(rows, groups, pairs, roles, pred, report[name])
    return report, pred["augmented"]


def benchmark(rows):
    """Compare the three forecasts on exactly the same complete, source-adjacent targets."""
    rows, incomplete = complete_cases(rows)
    if incomplete:
        raise ValueError(
            "Supply only eligible complete targets, reporting incomplete exclusions in the source audit"
        )
    agreement_stats, roles = agreement(rows)
    consensus, predictions = study(rows, roles, with_control=True)
    sensitivity = {
        key: study(rows, [ROLES[r[key]] for r in rows], with_control=False)[0] for key in ("coder1", "coder2")
    }
    return {
        "agreement": agreement_stats,
        "consensus": consensus,
        "sensitivity": sensitivity,
        "rows": [
            {**row, "role": role, "augmented": pred} for row, role, pred in zip(rows, roles, predictions)
        ],
    }
