"""Compare pause and articulation-duration evidence on held-out junctions."""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from statistics import fmean, pstdev


def read_candidates(manifest):
    source = manifest['rows'] if isinstance(manifest, dict) else manifest
    rows = []
    exclusions = Counter()
    for index, original in enumerate(source):
        ids = {key: original.get(key) for key in ('recording_id', 'work', 'speaker')}
        label = original.get('label')
        pause = original.get('pause_ms')
        ratio = original.get('duration_ratio')
        before = original.get('pre_duration_s')
        context = original.get('context_duration_s')

        def number(name, value, *, positive=False):
            if value is None:
                return None
            if (type(value) not in (float, int) or not math.isfinite(value)
                    or value < 0 or (positive and value == 0)):
                raise ValueError(f'Row {index + 1}: invalid {name} {value!r}')
            return value

        pause = number('pause_ms', pause)
        ratio = number('duration_ratio', ratio, positive=True)
        before = number('pre_duration_s', before, positive=True)
        context = number('context_duration_s', context, positive=True)
        if label is not None and (type(label) not in (bool, int) or label not in (0, 1)):
            raise ValueError(f'Row {index + 1}: label must be boolean, 0, 1, or null')
        missing = []
        missing.extend(key for key, value in ids.items() if not isinstance(value, str) or not value.strip())
        if label is None:
            missing.append('label')
        if pause is None:
            missing.append('pause_ms')
        if ratio is None and (before is None or context is None):
            missing.append('duration_ratio')
        if missing:
            exclusions.update(missing)
            continue

        rows.append({**ids, 'row': index + 1, 'label': int(label), 'genre': original.get('genre'),
                     'pause': math.log1p(pause),
                     'duration': math.log(ratio) if ratio is not None else math.log(before) - math.log(context)})
    return rows, {'input_rows': len(source), 'paired_feature_rows': len(rows),
                  'excluded_rows': len(source) - len(rows), 'missing_by_field': dict(exclusions)}


def logistic(value):
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1 + exp_value)


def fit_logistic(rows, features, ridge):
    columns = [[row[key] for row in rows] for key in features]
    centers = [fmean(column) for column in columns]
    scales = [pstdev(column) or 1 for column in columns]

    def predictors(row):
        return [1.0] + [(row[key] - center) / scale for key, center, scale in zip(features, centers, scales)]

    design = [predictors(row) for row in rows]
    targets = [row['label'] for row in rows]
    prevalence = fmean(targets)
    weights = [math.log(prevalence / (1 - prevalence))] + [0.0] * len(features)

    # The trace of the standardized design's Gram matrix bounds the loss curvature.
    step = 1 / (0.25 * sum(value * value for vector in design for value in vector) + ridge)
    for _ in range(5000):
        gradient = [0.0] + [ridge * weight for weight in weights[1:]]
        for vector, target in zip(design, targets):
            residual = logistic(sum(a * b for a, b in zip(weights, vector))) - target
            for j, value in enumerate(vector):
                gradient[j] += residual * value
        changes = [step * derivative for derivative in gradient]
        weights = [weight - change for weight, change in zip(weights, changes)]
        if max(map(abs, changes)) < 1e-9:
            break

    def predict(row):
        return logistic(sum(a * b for a, b in zip(weights, predictors(row))))

    return predict


def metrics(labels, scores):
    n = len(labels)
    if n == 0:
        return {'n': 0, 'positives': 0, 'average_precision': None, 'auc': None, 'brier': None}
    positives = sum(labels)
    negatives = n - positives
    counts = defaultdict(Counter)
    for label, score in zip(labels, scores):
        counts[score][label] += 1

    # Process tied scores together, retaining the precision-recall curve's step areas.
    prior_true = prior_false = 0
    precision_area = auc_pairs = 0.0
    for _, counts_at_score in sorted(counts.items(), reverse=True):
        true, false = counts_at_score[1], counts_at_score[0]
        auc_pairs += true * (negatives - prior_false - false / 2)
        prior_true += true
        prior_false += false
        precision_area += true * prior_true / (prior_true + prior_false)
    return {'n': n, 'positives': positives,
            'average_precision': precision_area / positives if positives else None,
            'auc': auc_pairs / (positives * negatives) if positives and negatives else None,
            'brier': fmean((label - score) ** 2 for label, score in zip(labels, scores))}


def compare(predictions):
    labels = [row['label'] for row in predictions]
    pause = metrics(labels, [row['pause_only'] for row in predictions])
    duration = metrics(labels, [row['pause_and_duration'] for row in predictions])
    return {'pause_only': pause, 'pause_and_duration': duration,
            'difference': {key: duration[key] - pause[key] if pause[key] is not None else None
                           for key in ('average_precision', 'auc', 'brier')}}


def held_out(rows, keys, ridge, *, training_rows=None):
    source = rows if training_rows is None else training_rows
    test_groups = defaultdict(list)
    for row in rows:
        test_groups[tuple(row[key] for key in keys)].append(row)

    output = []
    fold_details = []
    for identities, test in sorted(test_groups.items()):
        # Exclude either shared identity for a joint work-and-speaker fold.
        train = [row for row in source if all(row[key] != value for key, value in zip(keys, identities))]
        record = {**dict(zip(keys, identities)), 'test_n': len(test), 'train_n': len(train),
                  'train_positives': sum(row['label'] for row in train)}
        fold_details.append(record)
        if not train or len({row['label'] for row in train}) != 2:
            record['status'] = 'no_two_class_training_set'
            continue
        baseline = fit_logistic(train, ('pause',), ridge)
        candidate = fit_logistic(train, ('pause', 'duration'), ridge)
        record['status'] = 'evaluated'
        for row in test:
            output.append({**{key: row[key] for key in ('row', 'recording_id', 'work', 'speaker', 'genre', 'label')},
                           'pause_only': baseline(row), 'pause_and_duration': candidate(row)})

    output.sort(key=lambda row: row['row'])
    groups = {}
    for key in ('work', 'speaker', 'genre'):
        subsets = defaultdict(list)
        for row in output:
            if row[key] is not None:
                subsets[str(row[key])].append(row)
        groups[key] = {value: compare(subset) for value, subset in sorted(subsets.items())}

    return {'metrics': compare(output), 'groups': groups, 'folds': fold_details, 'predictions': output,
            'scored_rows': len(output), 'unscored_rows': len(rows) - len(output)}


def evaluate(manifest, *, ridge=1.0, training=None):
    rows, coverage = read_candidates(manifest)
    if not math.isfinite(ridge) or ridge <= 0:
        raise ValueError('Ridge penalty must be positive and finite')
    if training is None:
        training_rows, training_coverage = None, None
    else:
        training_rows, training_coverage = read_candidates(training)
        if {row['work'] for row in training_rows} & {row['work'] for row in rows}:
            raise ValueError('External training and test sets must have disjoint works')
    return {'coverage': coverage, 'external_training_coverage': training_coverage, 'ridge': ridge,
            'feature_specification': {'pause': 'log(1 + detector pause in seconds × 1000)',
                                      'duration': 'log(preceding articulation / local reference duration)',
                                      'normalization': 'center and scale each predictor in its training fold'},
            'primary_joint': held_out(rows, ('work', 'speaker'), ridge, training_rows=training_rows),
            'secondary_work_only': held_out(rows, ('work',), ridge, training_rows=training_rows),
            'secondary_speaker_only': held_out(rows, ('speaker',), ridge, training_rows=training_rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', '--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--training', type=Path, help='Fit using these entirely separate works')
    args = parser.parse_args()
    training = json.loads(args.training.read_text(encoding='utf-8')) if args.training else None
    results = evaluate(json.loads(args.input.read_text(encoding='utf-8')), training=training)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(results, out, ensure_ascii=False, allow_nan=False, indent=2)
        out.write('\n')


if __name__ == '__main__':
    main()
