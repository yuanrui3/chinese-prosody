"""Work-held-out test of written 音律美 descriptors using intact neighboring lines."""

import argparse
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from itertools import groupby, zip_longest
import json
import math
from pathlib import Path
from random import Random
from statistics import fmean, median

import numpy as np

if __package__:
    from . import quantitative_editorial_transfer as base
else:
    import quantitative_editorial_transfer as base


RHYME = tuple(f'{tier}_cross_line_rhyme' for tier in base.HISTORICAL_REFERENCES)
PARALLEL = ('neighbor_group_shape', 'neighbor_positional_echo', 'internal_arm_balance')
MODELS = {'baseline': base.FEATURES, 'rhyme': base.FEATURES + RHYME,
          'parallelism': base.FEATURES + PARALLEL, 'context': base.FEATURES + RHYME + PARALLEL}
SEED = 20261122


@dataclass
class Line:
    row: dict
    base: dict
    groups: tuple
    rhymes: dict
    complete: bool

    @property
    def key(self):
        return self.row['work_id'], self.row['id']


def describe(rows, lexicons):
    lines = []
    for row in rows:
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ('id', 'work_id', 'section')):
            raise ValueError('Every line needs a work_id, section, and id.')
        detail = base.measure(row['text'], lexicons, detail=True, historical_readings=row.get('historical_readings'))
        ends = detail['historical_endings']
        groups = tuple(''.join(filter(base.han, ending['group_text'])) for ending in ends)
        rhymes = {tier: base.reading_values(ends[-1], tier, 'rhyme') for tier in base.HISTORICAL_REFERENCES}
        lines.append(Line(row, detail['features'], groups, rhymes, '□' not in row['text']))
    if len({line.key for line in lines}) != len(lines):
        raise ValueError('Duplicate work_id and id within input')
    return lines


def shape_and_echo(left, right):
    """Align punctuation groups in order; unmatched tails count against similarity."""
    aligned = list(zip_longest(left, right, fillvalue=''))
    size = sum(max(len(a), len(b)) for a, b in aligned)
    shared = sum(min(len(a), len(b)) for a, b in aligned)
    matches = sum(x == y for a, b in aligned for x, y in zip(a, b))
    return shared / size, matches / size


def arm_balance(groups):
    """Compare the visible halves of an even group sequence or of a single 兮 frame."""
    if len(groups) > 1 and len(groups) % 2 == 0:
        mid = len(groups) // 2
        return shape_and_echo(groups[:mid], groups[mid:])[0]
    if len(groups) == 1 and groups[0].count('兮') == 1:
        left, right = groups[0].split('兮')
        if left and right:
            return min(len(left), len(right)) / max(len(left), len(right))
    return None


def rhyme_agreement(left, right):
    """Estimate equality only if every admissible combination gives the same outcome."""
    if not left or not right:
        return None
    if left.isdisjoint(right):
        return 0.0
    return 1.0 if len(left) == len(right) == 1 else None


def in_context(lines, rng=None):
    """Shuffle whole rows within each contiguous work/section for the order control."""
    result = {}
    for _, grouped in groupby(lines, key=lambda line: (line.row['work_id'], line.row['section'])):
        section = list(grouped)
        if rng:
            rng.shuffle(section)
        for i, line in enumerate(section):
            local = [(j, section[j]) for j in range(max(0, i - 2), min(len(section), i + 3))
                     if j != i and section[j].complete]
            adjacent = [other for j, other in local if abs(j - i) == 1]
            matches = [shape_and_echo(line.groups, other.groups) for other in adjacent]
            features = {**line.base,
                        'neighbor_group_shape': max((shape for shape, _ in matches), default=None),
                        'neighbor_positional_echo': max((echo for _, echo in matches), default=None),
                        'internal_arm_balance': arm_balance(line.groups)}
            support = {}
            for tier in base.HISTORICAL_REFERENCES:
                outcomes = [rhyme_agreement(line.rhymes[tier], other.rhymes[tier]) for _, other in local]
                usable = [x for x in outcomes if x is not None]
                features[f'{tier}_cross_line_rhyme'] = fmean(usable) if usable else None
                support[tier] = {'eligible': len(local), 'resolved': len(usable)}
            result[line.key] = (features, [other.row['id'] for _, other in local], support)
    return result


def feature_matrix(rows, names):
    return np.asarray([[row[k] for k in names] for row in rows], dtype=float)


def fit_model(rows, scores, names):
    """Same training-only centering, mean imputation and ridge penalty as the original."""
    raw = feature_matrix(rows, names)
    seen = np.isfinite(raw)
    count = seen.sum(axis=0)
    means = np.nansum(raw, axis=0) / np.maximum(count, 1)
    centered = np.where(seen, raw - means, 0.0)
    sd = np.sqrt((centered ** 2).sum(axis=0) / np.maximum(count, 1))
    scale = np.where(sd > 0, sd, 1.0)
    x = centered / scale
    intercept = float(np.mean(scores))
    weights = np.linalg.solve(x.T @ x + base.RIDGE * np.eye(len(names)), x.T @ (np.asarray(scores) - intercept))
    return {'names': names, 'means': means.tolist(), 'scales': scale.tolist(), 'weights': weights.tolist(),
            'intercept': intercept, 'observed': count.tolist()}


def predict(model, rows):
    raw = feature_matrix(rows, model['names'])
    centered = np.where(np.isfinite(raw), raw - model['means'], 0.0)
    return (model['intercept'] + centered / model['scales'] @ model['weights']).tolist()


def valid_score(value):
    return type(value) is int and 1 <= value <= 7


def score_summary(rows, constants):
    labeled = [row for row in rows if row['predictions']['baseline']['raw'] is not None
               and valid_score(row.get('editorial_score'))]
    models = {}
    y = [row['editorial_score'] for row in labeled]
    predictions = {name: [row['predictions'][name] for row in labeled] for name in MODELS}
    for name, value in constants.items():
        predictions[name] = [{'raw': value, 'score': math.floor(value + 0.5)}] * len(y)
    for name, pred in predictions.items():
        err = [abs(p['raw'] - target) for p, target in zip(pred, y)]
        rnd = [abs(p['score'] - target) for p, target in zip(pred, y)]
        models[name] = {'mae_raw': fmean(err) if err else None, 'mae_rounded': fmean(rnd) if rnd else None,
                        'exact': rnd.count(0), 'within_one': sum(distance <= 1 for distance in rnd)}
    return {'n_lines': len(rows), 'n_evaluated': len(labeled), 'models': models}


def shuffled_context(lines, model, output, repeats):
    """Falsify local order dependence on the frozen model; retain each target's text and score."""
    if repeats < 1:
        raise ValueError('At least one shuffle required')
    work_indices = defaultdict(list)
    labeled = [(i, row) for i, row in enumerate(output) if valid_score(row.get('editorial_score'))
               and row['predictions']['context']['raw'] is not None]
    for i, row in labeled:
        work_indices[row['work_id']].append(i)
    if not labeled:
        return {}
    true_error = {work: fmean(abs(output[i]['predictions']['context']['raw'] - output[i]['editorial_score'])
                              for i in indexes) for work, indexes in work_indices.items()}
    draws = defaultdict(list)
    rng = Random(SEED)
    for _ in range(repeats):
        permuted = in_context(lines, rng)
        raw = predict(model, [permuted[line.key][0] for line in lines])
        for work, ids in work_indices.items():
            draws[work].append(fmean(abs(raw[i] - output[i]['editorial_score']) for i in ids))
    return {work: {'observed_mae': true_error[work], 'mean_shuffled_mae': fmean(values),
                   'fraction_shuffles_at_least_as_good': sum(v <= true_error[work] for v in values) / repeats}
            for work, values in draws.items()}


def evaluate(reference, witness, lexicons, repeats=199):
    train = describe(reference, lexicons)
    test = describe(witness, lexicons)
    if {l.row['work_id'] for l in train} & {l.row['work_id'] for l in test}:
        raise ValueError('Hold out whole works')
    train_texts = {''.join(l.groups) for l in train}
    if any(''.join(l.groups) in train_texts for l in test):
        raise ValueError('Witness contains an exact reference Han string')
    scores = [l.row.get('score') for l in train]
    if any(not l.complete or not valid_score(s) for l, s in zip(train, scores)) or len(set(scores)) < 2:
        raise ValueError('Reference requires complete lines with variable 1–7 integer scores')
    if any('editorial_score' in l.row and not valid_score(l.row['editorial_score']) for l in test):
        raise ValueError('Unexpected witness editorial_score')
    ref_features = in_context(train)
    held_features = in_context(test)
    fit_x = [ref_features[l.key][0] for l in train]
    test_x = [held_features[l.key][0] for l in test]
    models = {name: fit_model(fit_x, scores, names) for name, names in MODELS.items()}
    predictions = {name: predict(model, test_x) for name, model in models.items()}
    rows = []
    for i, line in enumerate(test):
        features, neighbors, support = held_features[line.key]
        prediction = {}
        for name, values in predictions.items():
            raw = values[i] if line.complete else None
            prediction[name] = {'raw': raw, 'score': min(7, max(1, math.floor(raw + 0.5))) if raw is not None else None}
        rows.append({**line.row, 'predictions': prediction, 'context_features': {k: features[k] for k in RHYME + PARALLEL},
                     'neighbor_ids': neighbors, 'end_rhyme_candidates': {k: sorted(v) for k, v in line.rhymes.items()},
                     'cross_line_rhyme_support': support})
    by_work = defaultdict(list)
    for row in rows:
        by_work[row['work_id']].append(row)
    constants = {'constant_mean': fmean(scores), 'constant_median': median(scores)}
    return {'rows': rows, 'fits': models, 'training_constants': constants, 'summary': score_summary(rows, constants),
            'by_work': {k: score_summary(v, constants) for k, v in by_work.items()},
            'test_order_control': shuffled_context(test, models['context'], rows, repeats),
            'method': {'penalty': base.RIDGE, 'shuffle_seed': SEED, 'shuffle_count': repeats,
                       'target': 'written editorial 音律美 only', 'rhyme_window': 'two rows on either side in same section',
                       'rhyme': 'Exact group equality within each historical tier, averaged over decidable pairs.',
                       'parallelism': 'Adjacent punctuation-group shape and position-matched character echoes, plus within-line arm balance. Structural proxies only.',
                       'shuffle': 'Reorder intact held-out rows within sections and restore row identity before evaluation. Training fixed.'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'reference', 'witness', 'output'):
        parser.add_argument(f'--{key}', type=Path, required=True)
    parser.add_argument('--labels', type=Path, help='Optional array with work_id, id and frozen editorial score')
    parser.add_argument('--shuffles', type=int, default=199)
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        for path in (args.reference, args.witness, args.output, args.labels):
            if path and not path.resolve().is_relative_to(root):
                raise ValueError('Store inputs and output within the Gilbreth project')
        reference, ref_hash = base.load_rows(args.reference)
        witness, wit_hash = base.load_rows(args.witness)
        hashes = {'reference': ref_hash, 'witness': wit_hash}
        if args.labels:
            payload = args.labels.read_bytes()
            hashes['labels'] = sha256(payload).hexdigest()
            labels = json.loads(payload)
            index = {(x['work_id'], x['id']): x['score'] for x in labels}
            keys = {(row['work_id'], row['id']) for row in witness}
            if len(index) != len(labels) or set(index) - keys:
                raise ValueError('Unknown or duplicate editorial label IDs')
            witness = [{**row, 'editorial_score': index[key]} if key in index else row
                       for row in witness for key in [(row['work_id'], row['id'])]]
        lexicons, lexicon_hashes = base.lexicon_data(root)
        out = evaluate(reference, witness, lexicons, args.shuffles)
        out.update(input_sha256=hashes, lexicon_sha256=lexicon_hashes)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(out, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps({'by_work': out['by_work'], 'shuffle': out['test_order_control']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
