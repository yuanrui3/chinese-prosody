"""Audit joint-held-out boundary scores on matched DEBATE reading variants."""

import argparse
from collections import Counter, defaultdict
import json
from math import isclose, isfinite
from pathlib import Path
from random import Random
from statistics import fmean, quantiles


PREDICTORS = ('pause_only', 'pause_and_duration')
PAIR_KEYS = ('work', 'speaker', 'ordinal')
PAIR_PREFIX = 'DEBATE-'


def matched_pairs(candidates, evaluation):
    rows = candidates['rows'] if isinstance(candidates, dict) else candidates
    predictions = {}
    for prediction in evaluation['primary_joint']['predictions']:
        index = prediction['row']
        if type(index) is not int or not 1 <= index <= len(rows) or index in predictions:
            raise ValueError(f'Invalid or duplicate prediction row {index!r}')
        source = rows[index - 1]
        if any(prediction[key] != source[key] for key in ('work', 'speaker', 'recording_id', 'label')):
            raise ValueError(f'Prediction identity differs from candidate row {index}')
        if any(not isfinite(prediction[key]) or not 0 <= prediction[key] <= 1 for key in PREDICTORS):
            raise ValueError(f'Invalid held-out probability at row {index}')
        predictions[index] = prediction

    groups = defaultdict(list)
    for index, source in enumerate(rows, 1):
        if isinstance(source.get('work'), str) and source['work'].startswith(PAIR_PREFIX):
            groups[tuple(source[key] for key in PAIR_KEYS)].append(index)
    if not groups:
        raise ValueError('No DEBATE candidate groups')

    for group, indices in sorted(groups.items()):
        if len(indices) != 2 or {rows[i - 1]['label'] for i in indices} != {0, 1}:
            raise ValueError(f'{group!r}: expected exactly one positive and one negative variant')
        negative, positive = sorted(indices, key=lambda i: rows[i - 1]['label'])
        if rows[negative - 1]['recording_id'] == rows[positive - 1]['recording_id']:
            raise ValueError(f'{group!r}: reading variants must come from distinct recordings')

        pair = {**dict(zip(PAIR_KEYS, group)), 'negative_row': negative, 'positive_row': positive}
        pause_durations = [rows[i - 1]['pause_ms'] for i in (negative, positive)]
        pair['both_pause_values_observed'] = all(duration is not None for duration in pause_durations)
        pair['neither_pause_detected'] = pause_durations == [0, 0]
        pair['complete'] = negative in predictions and positive in predictions
        if pair['complete']:
            for key in PREDICTORS:
                a, b = predictions[positive][key], predictions[negative][key]
                pair[key] = 0.5 if isclose(a, b, rel_tol=0, abs_tol=1e-12) else int(a > b)
            if pair['neither_pause_detected'] and pair['pause_only'] != 0.5:
                raise ValueError(f'{group!r}: pause-only scores must tie when both pause values are zero')
        yield pair


def summarize(pairs):
    complete = [pair for pair in pairs if pair['complete']]
    output = {'candidate_pairs': len(pairs), 'complete_pairs': len(complete),
              'both_pause_values_observed_pairs': sum(pair['both_pause_values_observed'] for pair in pairs)}
    for key in PREDICTORS:
        values = [pair[key] for pair in complete]
        outcomes = Counter(values)
        output[key] = {'wins': outcomes[1], 'ties': outcomes[0.5], 'losses': outcomes[0],
                       'concordance': fmean(values) if values else None}
    output['concordance_gain'] = (output['pause_and_duration']['concordance'] - output['pause_only']['concordance']
                                  if complete else None)
    return output


def crossed_bootstrap(pairs, *, draws, seed):
    """Resample crossed works and speakers, keeping paired OOF outcomes fixed."""
    cells = defaultdict(lambda: [0, 0.0])
    for pair in pairs:
        if pair['complete']:
            cell = cells[pair['work'], pair['speaker']]
            cell[0] += 1
            cell[1] += pair['pause_and_duration'] - pair['pause_only']
    works, speakers = [sorted({key[column] for key in cells}) for column in (0, 1)]
    result = {'work_clusters': len(works), 'speaker_clusters': len(speakers), 'draws': draws,
              'seed': seed, 'usable_draws': 0, 'concordance_gain_interval_95': None}
    if min(len(works), len(speakers)) < 2 or not draws:
        return result

    rng = Random(seed)
    gains = []
    for _ in range(draws):
        work_weights = Counter(rng.choices(works, k=len(works)))
        speaker_weights = Counter(rng.choices(speakers, k=len(speakers)))
        count = total = 0.0
        for (work, speaker), (n, gain) in cells.items():
            weight = work_weights[work] * speaker_weights[speaker]
            count += weight * n
            total += weight * gain
        if count:
            gains.append(total / count)
    result['usable_draws'] = len(gains)
    if len(gains) >= 2:
        cuts = quantiles(gains, n=40, method='inclusive')
        result['concordance_gain_interval_95'] = [cuts[0], cuts[-1]]
    return result


def audit(candidates, evaluation, *, draws=2000, seed=20261122):
    if draws < 0:
        raise ValueError('Bootstrap draws must be nonnegative')
    pairs = list(matched_pairs(candidates, evaluation))
    result = {'evaluation': 'primary_joint', 'pairing': list(PAIR_KEYS),
              'tie_credit': 0.5, 'bootstrap_note': 'Resample works and speakers independently and keep out-of-fold '
                                                   'predictions fixed. Intervals are descriptive.'}
    for key, subset in [('all_pairs', pairs), ('neither_pause_detected', [p for p in pairs if p['neither_pause_detected']])]:
        result[key] = {**summarize(subset), 'uncertainty': crossed_bootstrap(subset, draws=draws, seed=seed)}
    result['pairs'] = pairs
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', required=True, type=Path)
    parser.add_argument('--evaluation', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit(*(json.loads(path.read_text(encoding='utf-8')) for path in (args.candidates, args.evaluation)))
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(report, out, ensure_ascii=False, allow_nan=False, indent=2)
        out.write('\n')
    print(json.dumps({key: report[key] for key in ('all_pairs', 'neither_pause_detected')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
