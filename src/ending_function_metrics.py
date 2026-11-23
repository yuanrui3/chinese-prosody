"""Evaluate a fixed rhetorical-function adjustment on scored, work-held-out endings."""

from collections import Counter, defaultdict
from math import isfinite
from random import Random
from statistics import fmean, median

from .quantitative_pattern_endings import bounded, concord


CATEGORIES = ('argument', 'list', 'mixed', 'uncertain')
PURE = ('argument', 'list')
SEED = 20261122
DRAWS = 999


def agreement(one, two):
    """Unweighted agreement and a consensus pure-role signal, in input order."""
    if len(one) != len(two) or any(role not in CATEGORIES for role in (*one, *two)):
        raise ValueError('Expected aligned argument/list/mixed/uncertain labels from both annotators')
    n = len(one)
    matrix = {first: dict.fromkeys(CATEGORIES, 0) for first in CATEGORIES}
    roles = []
    for a, b in zip(one, two):
        matrix[a][b] += 1
        roles.append(a if a == b and a in PURE else None)
    exact = sum(matrix[role][role] for role in CATEGORIES)
    margins_one, margins_two = Counter(one), Counter(two)
    expected_num = sum(margins_one[r] * margins_two[r] for r in CATEGORIES)
    denominator = n * n - expected_num
    n_pure = n - roles.count(None)
    return {
        'n': n, 'categories': list(CATEGORIES), 'matrix': matrix, 'exact': exact,
        'observed_agreement': exact / n if n else None,
        'kappa': (n * exact - expected_num) / denominator if denominator else None,
        'agreed_pure': n_pure, 'agreed_pure_fraction': n_pure / n if n else None,
        'roles': roles,
    }


def pair_summary(pairs, roles, forecasts):
    cross = [(high, low) for high, low in pairs if roles[high] != roles[low]]
    argument_7 = sum(roles[high] == 'argument' for high, _ in cross)
    return {
        'pairs': len(pairs), 'argument_7_pairs': argument_7, 'list_7_pairs': len(cross) - argument_7,
        'same_role_pairs': len(pairs) - len(cross),
        'methods': {method: concord(pairs, pred) for method, pred in forecasts.items()},
    }


def rankings(scores, roles, forecasts, groups, cross_role):
    def pairs(indices):
        highs = [i for i in indices if scores[i] == 7 and roles[i] in PURE]
        lows = [i for i in indices if scores[i] == 6 and roles[i] in PURE]
        return [(a, b) for a in highs for b in lows if not cross_role or roles[a] != roles[b]]

    work_pairs = {w: pairs(indices) for w, indices in groups.items()}
    by_work = {w: pair_summary(ps, roles, forecasts) for w, ps in work_pairs.items()}
    within = pair_summary([pair for ps in work_pairs.values() for pair in ps], roles, forecasts)
    pooled = pair_summary(pairs(range(len(scores))), roles, forecasts)
    informative = [w for w, ps in work_pairs.items() if ps]
    methods = {
        method: {
            'macro': fmean(by_work[w]['methods'][method] for w in informative) if informative else None,
            'within_pooled': within['methods'][method], 'pooled_all': pooled['methods'][method],
        }
        for method in forecasts
    }
    return {
        'within_pairs': within['pairs'], 'argument_7_pairs': within['argument_7_pairs'],
        'list_7_pairs': within['list_7_pairs'], 'same_role_pairs': within['same_role_pairs'],
        'informative_works': informative, 'by_work': by_work, 'pooled_all': pooled, 'methods': methods,
    }, {w: work_pairs[w] for w in informative}


def threshold(scores, pred, indices):
    cells = dict.fromkeys(('tp', 'fp', 'tn', 'fn'), 0)
    for i in indices:
        positive = scores[i] == 7
        called = pred[i] >= 6.5
        key = ('tp' if positive else 'fp') if called else ('fn' if positive else 'tn')
        cells[key] += 1
    return cells


def errors(scores, groups, forecasts):
    def summary(indices):
        high = [i for i in indices if scores[i] in (6, 7)]
        methods = {}
        for method, pred in forecasts.items():
            if method == 'function_only':
                continue
            methods[method] = {
                'mae': fmean(abs(pred[i] - scores[i]) for i in indices) if indices else None,
                'threshold': threshold(scores, pred, indices), 'threshold_6_7': threshold(scores, pred, high),
            }
        return {'n': len(indices), 'score_counts': dict(Counter(scores[i] for i in indices)), 'methods': methods}

    by_work = {w: summary(indices) for w, indices in groups.items()}
    result = summary([i for indices in groups.values() for i in indices])
    for method, cells in result['methods'].items():
        means = [work['methods'][method]['mae'] for work in by_work.values() if work['n']]
        cells['macro_mae'] = fmean(means) if means else None
    result['by_work'] = by_work
    return result


def adjusted(current, signals):
    return [bounded(p + 0.25 * s) for p, s in zip(current, signals)]


def permutation(groups, fixed_pairs, scores, roles, current, signals, primary):
    control = {
        'seed': SEED, 'draws': 0, 'observed_gain': None, 'median_gain': None,
        'at_least_observed': None, 'p_upper': None,
    }
    if not fixed_pairs:
        return control
    baseline = primary['methods']['current']['macro']
    observed_gain = primary['methods']['augmented']['macro'] - baseline
    blocks = [[i for i in indices if roles[i] in PURE and scores[i] in (6, 7)] for indices in groups.values()]
    rng = Random(SEED)
    gains = []
    for _ in range(DRAWS):
        moved = list(signals)
        for block in blocks:
            local = [signals[i] for i in block]
            rng.shuffle(local)
            for i, signal in zip(block, local):
                moved[i] = signal
        shuffled = adjusted(current, moved)
        gains.append(fmean(concord(ps, shuffled) for ps in fixed_pairs.values()) - baseline)
    tail = sum(delta >= observed_gain - 1e-12 for delta in gains)
    control.update(draws=DRAWS, observed_gain=observed_gain, median_gain=median(gains),
                   at_least_observed=tail, p_upper=(1 + tail) / (1 + DRAWS))
    return control


def study(rows, roles, shuffle=False):
    """Study one aligned role assignment. None denotes abstention on a disputed endpoint."""
    if len(rows) != len(roles) or any(role not in (*CATEGORIES, None) for role in roles):
        raise ValueError('Expected one valid role or None for each ending')
    scores = [r['score'] for r in rows]
    if any(type(s) is not int or not 1 <= s <= 7 for s in scores):
        raise ValueError('Expected a complete written score from 1 through 7')
    current = [float(r['current']) for r in rows]
    if any(not isfinite(v) or not 1 <= v <= 7 for v in current):
        raise ValueError('Current forecasts must be finite and clipped to [1, 7]')
    groups = defaultdict(list)
    counts = defaultdict(Counter)
    for i, row in enumerate(rows):
        groups[row['work_id']].append(i)
        counts[roles[i] or 'abstain'][scores[i]] += 1
    signal_value = {'argument': 1, 'list': -1}
    signals = [signal_value.get(role, 0) for role in roles]
    forecasts = {'always6': [6.0] * len(rows), 'current': current,
                 'augmented': adjusted(current, signals), 'function_only': signals}
    primary, fixed_pairs = rankings(scores, roles, forecasts, groups, cross_role=True)
    ordinary, _ = rankings(scores, roles, forecasts, groups, cross_role=False)
    pure_groups = {w: [i for i in indices if roles[i] in PURE] for w, indices in groups.items()}
    return {
        'n': len(rows), 'n_works': len(groups), 'n_pure': sum(map(len, pure_groups.values())),
        'scores_by_role': {r: dict(counts[r]) for r in (*CATEGORIES, 'abstain')},
        'primary': primary, 'ordinary': ordinary,
        'error': {'all': errors(scores, groups, forecasts), 'pure': errors(scores, pure_groups, forecasts)},
        'permutation': permutation(groups, fixed_pairs, scores, roles, current, signals, primary) if shuffle else None,
    }
