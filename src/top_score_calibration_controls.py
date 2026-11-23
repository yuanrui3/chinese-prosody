"""Descriptive controls for a top-score cutoff frozen before fresh labels are read."""

from collections import defaultdict
from random import Random
from statistics import fmean, median

from .quantitative_top_score_calibration import CURRENT, call_seven, complete_cases, evaluate


DRAWS = 999
SEED = 20261122


def leave_one_work_out(rows, cutoff):
    """Drop one fresh work at a time. The chosen threshold stays fixed in every subset."""
    stats = {}
    for work in sorted({r["work_id"] for r in rows}):
        kept = [r for r in rows if r["work_id"] != work]
        metric = evaluate(kept, [call_seven(r["current"], cutoff) for r in kept])
        stats[work] = {
            "macro_recall7": metric["work_balanced"]["recall7"],
            "macro_false7_rate6": metric["work_balanced"]["false7_rate6"],
            "pooled_recall7": metric["pooled"]["recall7"],
            "pooled_false7_rate6": metric["pooled"]["false7_rate6"],
            "pooled_precision7": metric["pooled"]["precision7"],
        }
    ranges = {}
    for name in ("macro_recall7", "macro_false7_rate6", "pooled_recall7", "pooled_false7_rate6",
                 "pooled_precision7"):
        values = [work[name] for work in stats.values() if work[name] is not None]
        ranges[name] = {"min": min(values) if values else None, "max": max(values) if values else None,
                        "defined_subsets": len(values)}
    return {"by_omitted_work": stats, "ranges": ranges}


def tail(observed, draws):
    hits = sum(value >= observed - 1e-12 for value in draws) if draws else None
    return {"observed": observed, "median_shuffled": median(draws) if draws else None,
            "at_least_observed": hits, "p_upper": (hits + 1) / (len(draws) + 1) if draws else None}


def permutation_control(rows, cutoff):
    """Shuffle all complete written grades within the same work and hold both sets of calls fixed.

    Each statistic averages over works containing a 7. The one-sided tails ask whether the
    observed alignment with editorial sevens is better than random allocation within work.
    """
    complete, _ = complete_cases(rows)
    works = defaultdict(list)
    for r in complete:
        works[r["work_id"]].append(r)
    groups = []
    for work in sorted(works):
        group = works[work]
        labels = [r["score"] for r in group]
        sevens = labels.count(7)
        if sevens:
            calibrated = [call_seven(r["current"], cutoff) for r in group]
            current = [call_seven(r["current"], CURRENT) for r in group]
            groups.append((labels, calibrated, current, sevens))

    def statistics():
        recalls, gains = [], []
        for labels, calibrated, current, n7 in groups:
            hit = sum(new for score, new in zip(labels, calibrated) if score == 7)
            old = sum(flag for score, flag in zip(labels, current) if score == 7)
            recalls.append(hit / n7)
            gains.append((hit - old) / n7)
        return (fmean(recalls), fmean(gains)) if groups else (None, None)

    observed_recall, observed_gain = statistics()
    rng = Random(SEED)
    recalls, gains = [], []
    for _ in range(DRAWS if groups else 0):
        for labels, _, _, _ in groups:
            rng.shuffle(labels)
        recall, gain = statistics()
        recalls.append(recall)
        gains.append(gain)
    return {"draws": len(recalls), "seed": SEED, "works_with_sevens": len(groups),
            "calibrated_recall": tail(observed_recall, recalls),
            "recall_gain_vs_current": tail(observed_gain, gains),
            "leave_one_work_out": leave_one_work_out(complete, cutoff)}
