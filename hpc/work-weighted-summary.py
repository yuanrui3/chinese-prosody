"""Verify the work-weighted study from sealed forecasts and grades, and emit a compact report."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import isclose, sqrt
from pathlib import Path
from random import Random
from statistics import fmean, median, pstdev

METHODS = ('current', 'equal_work', 'always_6')
CUTOFF = 6.50
OLD_RUN = 'written-rhyme-DvfWnBBA'
OLD_FORECAST = '302e479ba2408af346b5dc952e1ec3b470f10c6b24468710d1b75a69223db76d'


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def check(test, message):
    if not test:
        raise ValueError(message)


def ratio(num, den):
    return num / den if den else None


def by_id(rows):
    result = {r['id']: r for r in rows}
    check(len(result) == len(rows), 'Duplicate ID')
    return result


def numbers_match(a, b):
    if a is None or b is None:
        return a is b
    return isclose(a, b, abs_tol=1e-9, rel_tol=0.0)


def metrics(blocks, method, grades):
    scores = [[r['predictions'][method] for r in block] for block in blocks]
    mean = fmean(fmean(w) for w in scores)
    sd = sqrt(fmean(fmean((s - mean) ** 2 for s in w) for w in scores))
    mae = fmean(fmean(abs(r['predictions'][method] - grades[r['id']]) for r in block)
                for block in blocks)
    pairs = [(r['predictions'][method], grades[r['id']]) for w in blocks for r in w]
    catches = sum(p >= CUTOFF and g == 7 for p, g in pairs)
    actual = sum(g == 7 for _, g in pairs)
    predicted = sum(p >= CUTOFF for p, _ in pairs)
    fp = predicted - catches
    return {'mean': mean, 'sd': sd, 'mean_within_work_sd': fmean(pstdev(w) for w in scores),
            'minimum': min(map(min, scores)), 'maximum': max(map(max, scores)), 'mae': mae,
            'hits': catches, 'misses': actual-catches, 'false_positives': fp,
            'true_negatives': len(pairs)-actual-fp,
            'false_positives_among_sixes': sum(p >= CUTOFF and g == 6 for p, g in pairs),
            'actual_sixes': sum(g == 6 for _, g in pairs), 'actual_sevens': actual,
            'predicted_sevens': predicted, 'recall': ratio(catches, actual),
            'precision': ratio(catches, predicted), 'false_positive_rate': ratio(fp, len(pairs)-actual)}


def diagnostics(blocks, method, grades):
    """Describe where true sevens landed, including them when no forecast reaches 6.50."""
    outcomes = {True: [], False: []}
    concordances = []
    for work in blocks:
        pos = [r['predictions'][method] for r in work if grades[r['id']] == 7]
        neg = [r['predictions'][method] for r in work if grades[r['id']] < 7]
        outcomes[True].extend(pos)
        outcomes[False].extend(neg)
        if pos and neg:
            concordances.append(fmean((p > n) + 0.5 * (p == n) for p in pos for n in neg))
    def dist(values):
        return {'n': len(values), 'median': median(values), 'minimum': min(values),
                'maximum': max(values)} if values else {'n': 0}
    max_score = max(max(r['predictions'][method] for r in w) for w in blocks)
    return {'max_minus_cutoff': max_score - CUTOFF, 'on_editorial_7': dist(outcomes[True]),
            'on_lower_grades': dist(outcomes[False]), 'informative_ranking_works': len(concordances),
            'within_work_seven_above_lower': fmean(concordances) if concordances else None}


def transitions(rows, labels):
    events = defaultdict(list)
    for r in rows:
        old = r['predictions']['current']
        new = r['predictions']['equal_work']
        if (old >= CUTOFF) == (new >= CUTOFF):
            continue
        gold = labels[r['id']]
        if new >= CUTOFF:
            event = 'new_hit' if gold == 7 else 'new_false_positive'
        else:
            event = 'lost_hit' if gold == 7 else 'removed_false_positive'
        events[event].append({'id': r['id'], 'work_id': r['work_id'], 'genre': r['genre'],
                              'score': gold, 'current': old, 'equal_work': new})
    result = {}
    for name in ('new_hit', 'lost_hit', 'new_false_positive', 'removed_false_positive'):
        rows = events[name]
        result[name] = {'n': len(rows), 'works': sorted({r['work_id'] for r in rows}), 'examples': rows[:6]}
    return result


def matched_pair_sensitivity(works, forecasts, labels, checked, draws=10000, seed=20261126):
    """Resample intact period-matched pairs. Both fits see the same works in each draw."""
    blocks = defaultdict(list)
    for row in forecasts.values():
        blocks[row['work_id']].append(row)
    cards = {w['work_id']: w for w in works}
    check(cards.keys() == blocks.keys() and len(cards) == len(works), 'Unmatched source works')
    pairs = defaultdict(list)
    for wid, w in cards.items():
        pairs[w['period_pair']].append(wid)
    pair_stats = []
    for _, members in sorted(pairs.items()):
        check(len(members) == 2 and {cards[wid]['genre'] for wid in members} == {'fu','prose'},
              'Each period pair must have exactly one work of each genre')
        vector = []
        for method in ('equal_work','current'):
            work_stats = []
            for wid in members:
                rows = blocks[wid]
                predictions = [r['predictions'][method] for r in rows]
                # Center near the observed scale before combining first and second moments.
                centered = [p - 6 for p in predictions]
                work_stats.append((fmean(centered), fmean(x*x for x in centered), pstdev(predictions),
                                   fmean(abs(r['predictions'][method] - labels[r['id']]) for r in rows)))
            vector.extend(map(fmean, zip(*work_stats)))
        pair_stats.append(vector)

    def differences(sample):
        m1, s1, w1, a1, m0, s0, w0, a0 = map(fmean, zip(*sample))
        return sqrt(max(0., s1-m1*m1)) - sqrt(max(0., s0-m0*m0)), w1-w0, a1-a0

    observed = differences(pair_stats)
    rng = Random(seed)
    distribution = [differences(rng.choices(pair_stats, k=len(pair_stats))) for _ in range(draws)]
    def percentile(sorted_values, q):
        offset = q * (len(sorted_values)-1)
        lo = int(offset)
        return sorted_values[lo] + (offset-lo) * (sorted_values[min(lo+1,len(sorted_values)-1)]-sorted_values[lo])
    contrasts = {}
    for index, name in enumerate(('sd','mean_within_work_sd','mae')):
        check(numbers_match(observed[index], checked['equal_work'][name]-checked['current'][name]),
              f'Matched-pair point estimate differs for {name}')
        values = sorted(draw[index] for draw in distribution)
        contrasts[name] = {'difference': observed[index], 'paired_95': [percentile(values,q) for q in (.025,.975)]}
    return {'draws': draws, 'seed': seed, 'unit': 'source period_pair', 'pairs': len(pairs),
            'equal_work_minus_current': contrasts}


def review(run, forecasts, label_name, evaluation_name):
    ratings_path = run/'inputs'/label_name
    path = run/'results'/evaluation_name
    analysis = read(path)
    labels = {key: row['score'] for key, row in by_id(read(ratings_path)).items()}
    joined = by_id(analysis['joined'])
    check(labels.keys() == forecasts.keys() == joined.keys(), 'Mismatched target sets')
    for key, r in joined.items():
        check(r['score'] == labels[key] and r['predictions'] == forecasts[key]['predictions']
              and r['work_id'] == forecasts[key]['work_id'] and r['genre'] == forecasts[key]['genre'],
              f'Evaluation row differs from sealed inputs at {key}')
    checks = analysis['hashes']
    check(checks['forecast'] == digest(run/'results/forecasts.json') and
          checks['ratings'] == digest(ratings_path), 'Mismatched evaluation hash')
    groups = {}
    for group, official in analysis['groups'].items():
        members = [r for r in forecasts.values() if group == 'all' or group == r['genre']]
        by_work = defaultdict(list)
        for r in members:
            by_work[r['work_id']].append(r)
        blocks = list(by_work.values())
        checked = {m: metrics(blocks, m, labels) for m in METHODS}
        for m in METHODS:
            for k, v in checked[m].items():
                check(numbers_match(v, official['methods'][m][k]), f'{evaluation_name}/{group}/{m}/{k}')
        groups[group] = {'works': len(blocks), 'targets': len(members),
                         'rating_counts': dict(sorted(Counter(labels[r['id']] for r in members).items())),
                         'methods': checked, 'paired_differences': official['equal_work_minus'],
                         'cutoff_crossings': transitions(members, labels),
                         'ranking_diagnostic': {m: diagnostics(blocks, m, labels) for m in METHODS}}
        if group == 'all':
            groups[group]['per_work'] = {
                w: {m: {k:v for k,v in metrics([block],m,labels).items()
                        if k in {'sd','minimum','maximum','mae','hits','misses','false_positives','actual_sevens'}}
                    for m in METHODS} for w, block in by_work.items()}
    return {'groups': groups, 'decision': analysis.get('decision'), 'hashes': checks,
            'evaluation_sha256': digest(path)}, labels


def verify_run(run):
    forecasts_path = run/'results/forecasts.json'
    f = read(forecasts_path)
    forecasts = by_id(f['predictions'])
    inputs = run/'inputs'
    for name, expected in read(inputs/'source-seal.json').items():
        check(digest(inputs/name) == expected, f'Changed source input {name}')
    check(f['hashes']['corpus'] == digest(inputs/'corpus.json'), 'Forecast corpus mismatch')
    rows = read(inputs/'corpus.json')
    targets = by_id([r for r in rows if r['target']])
    check(targets.keys() == forecasts.keys(), 'Missing or surplus forecasts')
    for i, r in forecasts.items():
        check(all(r[k] == targets[i][k] for k in ('work_id','genre')), f'Changed source context for {i}')
        check(r['predictions']['always_6'] == 6, 'Baseline must always give six')
    data = {'forecast_sha256': digest(forecasts_path), 'hashes': f['hashes'], 'training': f.get('training'),
            'context_sentences': len(rows), 'source_seal_sha256': digest(inputs/'source-seal.json')}
    labels = []
    for key, suffix in [('primary',''), ('secondary','-second')]:
        data[key], grades = review(run, forecasts, f'ratings{suffix}.json', f'evaluation{suffix}.json')
        labels.append(grades)
    agreement = {}
    for group in ('all', 'fu', 'prose'):
        diffs = [abs(labels[0][i] - labels[1][i]) for i,r in forecasts.items() if group in ('all',r['genre'])]
        if diffs:
            agreement[group] = {'n':len(diffs), 'exact':diffs.count(0),
                                'within_one':sum(d <= 1 for d in diffs), 'mean_absolute_difference':fmean(diffs)}
    data['reader_agreement'] = agreement
    return data, forecasts


def summarize(root, run):
    summary, forecasts = verify_run(run)
    reference = root / 'results/grammatical-training-expansion-20261122/results/enriched-reference.json'
    check(digest(reference) == summary['hashes']['training'], 'Changed training reference')
    labels_by_work = defaultdict(list)
    for row in read(reference):
        labels_by_work[row['work_id']].append(row['score'])
    counts = {work: Counter(labels) for work, labels in labels_by_work.items()}
    sizes = {work: sum(hist.values()) for work, hist in counts.items()}
    check(sizes == summary['training']['work_sizes'], 'Changed training-work sizes')
    summary['training']['label_shares'] = {
        str(grade): {
            'current': sum(hist[grade] for hist in counts.values()) / sum(sizes.values()),
            'equal_work': fmean(hist[grade] / sizes[work] for work, hist in counts.items())}
        for grade in range(1, 8)}
    summary['training']['work_grade_counts'] = counts
    summary['training']['intercepts'] = {
        method: fit['intercept'] for method, fit in read(run/'results/forecasts.json')['models'].items()}
    retro = run / 'retrospective'
    replay, ret_forecasts = verify_run(retro)
    old = root / 'results' / OLD_RUN
    old_path = old/'results/forecasts.json'
    check(digest(old_path) == OLD_FORECAST, 'Expected the corrected previous eighty-sentence forecasts')
    old_forecasts = by_id(read(old_path)['predictions'])
    check(len(ret_forecasts) == 80 and ret_forecasts.keys() == old_forecasts.keys(), 'Old eighty ID check')
    for i,r in ret_forecasts.items():
        check(r['predictions']['current'] == old_forecasts[i]['predictions']['with_rhyme'],
              f'Nonidentical current-model replay at {i}')
    for path in ('corpus.json','ratings.json','ratings-second.json'):
        check(digest(old/'inputs'/path) == digest(retro/'inputs'/path), f'Changed earlier {path}')
    source = read(run/'inputs/sources.json')
    grades = {i:r['score'] for i,r in by_id(read(run/'inputs/ratings.json')).items()}
    summary['period_pair_sensitivity'] = matched_pair_sensitivity(
        source['works'], forecasts, grades, summary['primary']['groups']['all']['methods'])
    summary['source'] = {k:source[k] for k in ('reserved','period_matching','matching') if k in source}
    summary['source'].update(works=source['works'], screened=len(source.get('screened', [])),
                             catalogs=len(source.get('catalogs', {})), earlier_files=len(source.get('earlier_files', {})))
    summary['retrospective'] = {'historical_forecasts_replayed': len(ret_forecasts),
                                'source_sha256':OLD_FORECAST,
                                'primary':replay['primary']['groups']['all']['methods'],
                                'secondary':replay['secondary']['groups']['all']['methods']}
    return summary


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.root,args.run), ensure_ascii=False, allow_nan=False))
