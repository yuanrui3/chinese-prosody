"""Calibrate the decision to report a 7 using frozen written-score predictions."""

from collections import Counter, defaultdict
from fractions import Fraction
from math import isfinite
from statistics import fmean


CURRENT = 6.5
LIMIT = Fraction(1, 5)
METHODS = ("always6", "current", "calibrated")
RATES = ("recall7", "false7_rate6", "false7_rate_lower", "precision7")


def complete_cases(rows):
    """Return complete scored rows and identify missing labels, preserving order."""
    complete = []
    excluded = []
    seen = set()
    for row in rows:
        key = row["work_id"], row["id"]
        if any(not isinstance(value, str) or not value for value in key) or key in seen:
            raise ValueError(f"Missing or duplicate work and unit identifier: {key}")
        seen.add(key)
        label = row["score"]
        if label is None:
            excluded.append(dict(work_id=key[0], id=key[1]))
            continue
        value = row["current"]
        if type(label) is not int or not 1 <= label <= 7:
            raise ValueError(f"Invalid written rating at {key}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 1 <= value <= 7:
            raise ValueError(f"Expected a bounded frozen prediction at {key}")
        complete.append(row)
    return complete, excluded


def call_seven(score, threshold):
    """None is an explicit no-call rule. Equal forecasts are never split."""
    return threshold is not None and score >= threshold


def ratio(num, den):
    return num / den if den else None


def cells(rows, calls):
    counts = Counter(row["score"] for row in rows)
    positive = Counter(row["score"] for row, called in zip(rows, calls) if called)
    n = len(rows)
    n_lower = n - counts[7] - counts[6]
    called = sum(positive.values())
    lower = called - positive[7] - positive[6]
    return {
        "n": n, "n7": counts[7], "n6": counts[6], "n_lower": n_lower,
        "called7": called, "true7": positive[7], "false7_from6": positive[6],
        "false7_from_lower": lower, "missed7": counts[7] - positive[7],
        "recall7": ratio(positive[7], counts[7]), "false7_rate6": ratio(positive[6], counts[6]),
        "false7_rate_lower": ratio(lower, n_lower), "precision7": ratio(positive[7], called),
    }


def evaluate(rows, calls):
    by_work = defaultdict(list)
    decisions = defaultdict(list)
    for row, called in zip(rows, calls):
        work = row["work_id"]
        by_work[work].append(row)
        decisions[work].append(called)
    work_cells = {work: cells(items, decisions[work]) for work, items in by_work.items()}
    work_rates = {}
    denominators = {}
    for field in RATES:
        defined = [item[field] for item in work_cells.values() if item[field] is not None]
        work_rates[field] = fmean(defined) if defined else None
        denominators[field] = len(defined)
    return {"pooled": cells(rows, calls), "work_balanced": work_rates,
            "contributing_works": denominators, "by_work": work_cells}


def within_limit(result):
    rates = [result[aggregation]["false7_rate6"] for aggregation in ("pooled", "work_balanced")]
    return all(rate is not None and rate <= float(LIMIT) + 1e-12 for rate in rates)


def _fit(rows):
    label_counts = {label: Counter(row["work_id"] for row in rows if row["score"] == label)
                    for label in (6, 7)}
    if not all(label_counts.values()):
        current = evaluate(rows, [call_seven(r["current"], CURRENT) for r in rows])
        threshold = None if label_counts[6] and not within_limit(current) else CURRENT
        return threshold, "missing calibration class", 0

    # Per-observation weights sum to one separately for true sixes and sevens.
    # Exact rational arithmetic preserves ties and the 1/5 boundary across work sizes.
    weights = {label: {w: Fraction(1, len(works) * count) for w, count in works.items()}
               for label, works in label_counts.items()}
    six_count = sum(label_counts[6].values())
    blocks = defaultdict(list)
    for row in rows:
        blocks[row["current"]].append(row)
    blocks.setdefault(CURRENT, [])
    recall, macro_fp = Fraction(0), Fraction(0)
    false_sixes = 0
    # No-call is a feasible alternative even for a group tied at the maximum possible score.
    best_key = (recall, -macro_fp, 0, False, float("inf"))
    best_threshold = None
    for cutoff in sorted(blocks, reverse=True):
        for row in blocks[cutoff]:
            label = row["score"]
            if label == 7:
                recall += weights[7][row["work_id"]]
            elif label == 6:
                macro_fp += weights[6][row["work_id"]]
                false_sixes += 1
        if macro_fp > LIMIT or Fraction(false_sixes, six_count) > LIMIT:
            # Lowering an inclusive threshold cannot remove existing false positives.
            break
        key = (recall, -macro_fp, -false_sixes, cutoff == CURRENT, cutoff)
        if key > best_key:
            best_key, best_threshold = key, cutoff
    return best_threshold, "fitted", len(blocks) + 1


def fit(rows):
    """Fit one common cutoff, using only complete labels in the supplied earlier works."""
    training, excluded = complete_cases(rows)
    cutoff, status, candidates = _fit(training)
    applied = [call_seven(r["current"], cutoff) for r in training]
    return {"threshold": cutoff, "status": status, "n_rows": len(training),
            "n_works": len({r["work_id"] for r in training}), "excluded": excluded,
            "n_distinct_candidate_rules_before_pruning": candidates,
            "limits": {"macro_false7_rate6": float(LIMIT), "pooled_false7_rate6": float(LIMIT)},
            "training": evaluate(training, applied)}


def assess(rows, cutoffs):
    by_method = {method: [] for method in METHODS}
    predictions = []
    for row in rows:
        work = row["work_id"]
        threshold = cutoffs[work]
        calls = {"always6": False, "current": call_seven(row["current"], CURRENT),
                 "calibrated": call_seven(row["current"], threshold)}
        for method, decision in calls.items():
            by_method[method].append(decision)
        predictions.append({**row, "calibrated_threshold": threshold, "call7": calls})
    return {"methods": {m: evaluate(rows, calls) for m, calls in by_method.items()}, "rows": predictions}


def decision(methods):
    before = methods["current"]
    after = methods["calibrated"]
    tp_change = after["pooled"]["true7"] - before["pooled"]["true7"]
    recall = after["work_balanced"]["recall7"]
    gain = recall - before["work_balanced"]["recall7"] if recall is not None else None
    measured = after["pooled"]["n6"] > 0 and after["pooled"]["n7"] > 0
    passed = measured and tp_change > 0 and gain > 1e-12 and within_limit(after)
    return {"status": ("passed" if passed else "failed") if measured else "undefined",
            "additional_sevens": tp_change, "macro_recall_gain": gain,
            "sixes_cap_met": within_limit(after) if after["pooled"]["n6"] else None}


def benchmark(earlier, fresh):
    """Leave one earlier work out per fold, freeze the full fit, then evaluate untouched works."""
    earlier, fresh = list(earlier), list(fresh)
    old_works = {r["work_id"] for r in earlier}
    new_works = {r["work_id"] for r in fresh}
    if old_works & new_works:
        raise ValueError("A work appears in both calibration and fresh evaluation")
    earlier_complete, earlier_excluded = complete_cases(earlier)
    fresh_complete, fresh_excluded = complete_cases(fresh)
    folds = {}
    for work in sorted(old_works):
        training = [r for r in earlier_complete if r["work_id"] != work]
        cutoff, status, _ = _fit(training)
        folds[work] = {"threshold": cutoff, "status": status, "n_training_rows": len(training),
                       "training_works": sorted({r["work_id"] for r in training})}
    oof = assess(earlier_complete, {w: f["threshold"] for w, f in folds.items()})
    oof.update(folds=folds, excluded=earlier_excluded)
    calibration = fit(earlier)
    held_out = assess(fresh_complete, dict.fromkeys(new_works, calibration["threshold"]))
    held_out.update(decision=decision(held_out["methods"]), excluded=fresh_excluded)
    return {
        "fit": calibration, "earlier_oof": oof, "fresh": held_out,
        "protocol": {
            "current_threshold": CURRENT, "inclusive": True, "no_call_threshold": None,
            "selection": "Maximize work-balanced recall subject to both true-six promotion rates <= 1/5.",
            "ties": "Minimize work-balanced then pooled six-promotion rates, prefer 6.5, then the largest cutoff.",
            "undefined": "Each class-specific average counts only works with its denominator. No denominator gives null.",
            "rate_support": "Precision includes false positives from every score below 7.",
        },
    }
