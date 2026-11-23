"""Test whether historical descriptors improve held-out synthetic duration."""

import argparse
from collections import Counter, defaultdict
import json
from math import fsum
import os
from pathlib import Path
import random
from statistics import mean

from src.expansion_design import authors
from src.pilot_validation import TIERS, holm_adjust, matched_pairs, read_jsonl, weights_by_work, write_json
from src.stage6_listening import digest
from src.text_metrics import ping_share, reading_values
from src.timing_benchmark import ANNOTATIONS, MANIFEST, by_work, check_split, recordings


DEVELOPMENT = ('listening-rounds/mandarin-male', 'pilot-expansions/independent-works')
FEATURES = ('level_tone_share', 'rhyme_group_concentration')
PERIODS = {'sixth-century', 'early-tang'}


def check_corpus(base, fresh):
    prior = read_jsonl(base / ANNOTATIONS) + read_jsonl(base / DEVELOPMENT[1] / ANNOTATIONS)
    works = {row['work_id'] for row in prior}
    contributors = set().union(*(authors(row) for row in prior))
    texts = {row['text_sha256'] for row in prior}
    identifiers = {row['passage_id'] for row in prior}
    passages = read_jsonl(fresh / ANNOTATIONS)
    for row in passages:
        names = authors(row)
        if (row['work_id'] in works or names & contributors or not names or row['text_sha256'] in texts
                or row['passage_id'] in identifiers or row['subset'] != 'matched' or not row.get('pair_id')
                or len(row['slots']) != row['han_count'] or not 20 <= row['han_count'] <= 36):
            raise ValueError(f"Invalid or reused benchmark source: {row['passage_id']}")
        works.add(row['work_id'])
        contributors.update(names)
        texts.add(row['text_sha256'])
        identifiers.add(row['passage_id'])
    periods = Counter()
    for identifier, left, right in matched_pairs(passages):
        a, b = passages[left], passages[right]
        if (a['period'] != b['period'] or a.get('match_topic') != b.get('match_topic')
                or not a.get('match_topic') or abs(a['han_count'] - b['han_count']) > 6):
            raise ValueError(f'{identifier}: period, topic, or length contrast disagrees with its match')
        periods[a['period']] += 1
    if set(periods) != PERIODS or len(set(periods.values())) != 1:
        raise ValueError('Expected equal numbers of independent pairs in the two periods')
    return passages, dict(periods)


def descriptors(passage, tier):
    slots = passage['slots']
    tone = ping_share(slots, tier)
    groups = [reading_values(slot, tier, 'rhyme') for slot in slots]
    resolved = Counter(next(iter(values)) for values in groups if len(values) == 1)
    total = sum(resolved.values())
    usable = total * (total - 1) // 2
    repeats = sum(count * (count - 1) // 2 for count in resolved.values())
    # Count unordered position pairs. Singleton filtering retains the ambiguous
    # dictionary readings in the source annotations without selecting a reading.
    return {
        'level_tone_share': {'value': tone.value, 'usable': tone.usable,
                             'eligible': tone.eligible, 'bounds': [tone.lower, tone.upper]},
        'rhyme_group_concentration': {'value': repeats / usable if usable else None,
                                      'usable': usable, 'eligible': len(slots) * (len(slots) - 1) // 2,
                                      'resolved_slots': total},
    }


def measured_rows(root, *, expansion=False):
    passages = {row['passage_id']: row for row in read_jsonl(root / ANNOTATIONS)}
    rows = recordings(root, expansion=expansion)
    for row in rows:
        passage = passages[row['passage_id']]
        row.update(period=passage['period'], genre=passage['genre'], pair_id=passage['pair_id'],
                   descriptors={tier: descriptors(passage, tier) for tier in TIERS})
    return rows


def fit_rate(rows, values):
    weights = weights_by_work(rows)
    rates = [row['duration_ms'] / row['slots'] for row in rows]
    baseline = fsum(w * rate for w, rate in zip(weights, rates))
    center = fsum(w * x for w, x in zip(weights, values))
    variance = fsum(w * (x - center) ** 2 for w, x in zip(weights, values))
    if variance <= 1e-15:
        return baseline, None
    slope = fsum(w * (x - center) * (rate - baseline) for w, x, rate in zip(weights, values, rates)) / variance
    return baseline, (baseline - slope * center, slope)


def errors(rows, predictions):
    grouped = defaultdict(list)
    for row, prediction in zip(rows, predictions):
        grouped[row['work_id']].append(abs(row['duration_ms'] - prediction))
    per_work = {work: mean(absolute) for work, absolute in grouped.items()}
    return mean(per_work.values()), per_work


def permute(rows, values, rng):
    works = defaultdict(list)
    for index, row in enumerate(rows):
        works[row['work_id']].append(index)
    strata = defaultdict(list)
    for members in works.values():
        signature = tuple((rows[index]['period'], rows[index]['genre']) for index in members)
        strata[signature].append(members)
    shuffled = list(values)
    for groups in strata.values():
        for target, source in zip(groups, rng.sample(groups, len(groups))):
            for out, original in zip(target, source):
                shuffled[out] = values[original]
    return shuffled


def compare(calibration, holdout, tier, feature, draws, seed):
    def value(row):
        return row['descriptors'][tier][feature]['value']

    train = [row for row in calibration if value(row) is not None]
    test = [row for row in holdout if value(row) is not None]
    result = {'tier': tier, 'feature': feature, 'calibration_passages': len(train), 'holdout_passages': len(test),
              'calibration_works': len(by_work(train)), 'holdout_works': len(by_work(test)),
              'p_value': None, 'p_holm': None}
    if not train or not test:
        return {**result, 'status': 'insufficient_support'}
    x, held = list(map(value, train)), list(map(value, test))
    baseline, candidate = fit_rate(train, x)
    if candidate is None:
        return {**result, 'status': 'constant_calibration_feature'}

    def predictions(coefficients, values):
        intercept, slope = coefficients
        return [row['slots'] * (intercept + slope * score) for row, score in zip(test, values)]

    base_error, base_by_work = errors(test, predictions((baseline, 0), held))
    actual_predictions = predictions(candidate, held)
    model_error, model_by_work = errors(test, actual_predictions)
    gain = base_error - model_error
    rng = random.Random(seed)
    null_gains = []
    assignments = set()
    for _ in range(draws):
        train_values = permute(train, x, rng)
        test_values = permute(test, held, rng)
        _, shuffled_fit = fit_rate(train, train_values)
        if shuffled_fit is None:
            continue
        shuffled_error, _ = errors(test, predictions(shuffled_fit, test_values))
        null_gains.append(base_error - shuffled_error)
        assignments.add((tuple(train_values), tuple(test_values)))
    if not null_gains:
        raise ValueError('No usable permutations for this nonconstant predictor')
    null_gains.sort()
    changes = {work: base_by_work[work] - err for work, err in model_by_work.items()}
    return {
        **result, 'status': 'measured', 'baseline_mae_ms': base_error, 'augmented_mae_ms': model_error,
        'gain_ms': gain, 'works_improved': sum(delta > 1e-9 for delta in changes.values()),
        'nonpositive_duration_predictions': sum(value <= 0 for value in actual_predictions),
        'gain_ms_by_work': changes, 'fit': {'baseline_ms_per_slot': baseline,
                                           'augmented_intercept_and_slope': candidate},
        'p_value': (1 + sum(score >= gain - 1e-9 for score in null_gains)) / (1 + len(null_gains)),
        'draws_requested': draws, 'draws_used': len(null_gains), 'distinct_assignments_drawn': len(assignments),
        'null_gain_ms_05_95': [null_gains[int(q * (len(null_gains) - 1))] for q in (0.05, 0.95)],
        'null_gains_ms': null_gains,
    }


def benchmark(base, fresh, draws, seed):
    passages, periods = check_corpus(base, fresh)
    calibration = measured_rows(base / DEVELOPMENT[0]) + measured_rows(base / DEVELOPMENT[1], expansion=True)
    holdout = measured_rows(fresh)
    check_split(calibration, holdout)
    if len(calibration) != 9 or {row['passage_id'] for row in holdout} != {row['passage_id'] for row in passages}:
        raise ValueError('Expected the fixed nine development WAVs and complete fresh matched set')
    results = [compare(calibration, holdout, tier, feature, draws, seed + 1009 * index)
               for index, (tier, feature) in enumerate((t, f) for t in TIERS for f in FEATURES)]
    holm_adjust([row for row in results if row['tier'] == 'guangyun'])
    out = fresh / 'results/historical-increment/duration.json'
    write_json(out, {
        'draws': draws, 'seed': seed, 'pairs_by_period': periods, 'calibration': calibration, 'holdout': holdout,
        'inputs': {label: {str(file): digest(location / file) for file in (ANNOTATIONS, MANIFEST)}
                   for label, location in [('original', base / DEVELOPMENT[0]),
                                           ('expansion', base / DEVELOPMENT[1]), ('fresh', fresh)]},
        'comparisons': results,
    })
    return {'pairs_by_period': periods, 'fresh_works': len(holdout),
            'comparisons': [{key: value for key, value in row.items()
                             if key not in {'null_gains_ms', 'gain_ms_by_work', 'fit'}} for row in results]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--fresh', type=Path, required=True)
    parser.add_argument('--draws', type=int, default=999)
    parser.add_argument('--seed', type=int, default=20261121)
    parser.add_argument('--check-corpus', action='store_true')
    args = parser.parse_args()
    if args.draws < 1:
        parser.error('--draws must be positive')
    os.umask(0o077)
    base, fresh = args.root.resolve(strict=True), args.fresh.resolve(strict=True)
    if args.check_corpus:
        rows, periods = check_corpus(base, fresh)
        summary = {'fresh_works': len(rows), 'pairs_by_period': periods}
    else:
        summary = benchmark(base, fresh, args.draws, args.seed)
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
