"""Predict written musicality before joining sequestered editorial judgments on Gilbreth."""

import argparse
from collections import Counter, defaultdict
from itertools import groupby
from math import isfinite
from pathlib import Path
from statistics import fmean

import numpy as np

from . import quantitative_ending_functions as frozen
from .quantitative_grammar_expansion import normalized_text
from .yu_review_baseline import save_sealed

grammar = frozen.prev.grammar
context = grammar.context
CROSS = context.RHYME
INTERNAL = tuple(f'{tier}_group_end_rhyme_repeat' for tier in context.base.HISTORICAL_REFERENCES)
FULL = grammar.MODEL_COLS['context_grammar']
COLUMNS = {
    'with_rhyme': FULL,
    'without_cross_line': tuple(k for k in FULL if k not in CROSS),
    'without_any_rhyme': tuple(k for k in FULL if k not in CROSS + INTERNAL),
}
METHODS = (*COLUMNS, 'always_6')
SEED = 20261127
TRAIN_DRAWS = 2000
TEST_DRAWS = 10000
QUANTILES = (.025, .975)
TOLERANCE = 1e-10


def assert_close(values, expected, label):
    if not np.allclose(values, expected, atol=TOLERANCE, rtol=0):
        raise ValueError(f'{label} numerical replay mismatch')


def slopes(fit):
    result = {}
    for name in CROSS:
        idx = fit['names'].index(name)
        result[name] = fit['weights'][idx] / fit['scales'][idx]
    result['both_rise_from_0_to_1'] = sum(result.values())
    return result


def coefficient_sensitivity(x, labels, rows, draws=TRAIN_DRAWS):
    indexes = defaultdict(list)
    for i, row in enumerate(rows):
        indexes[row['work_id']].append(i)
    names = sorted(indexes)
    def refit(work_indices):
        subset = [i for j in work_indices for i in indexes[names[j]]]
        model = context.fit_model([x[i] for i in subset], [labels[i] for i in subset], FULL)
        return slopes(model)
    omitted = {name: refit([i for i in range(len(names)) if i != held])
               for held, name in enumerate(names)}
    rng = np.random.default_rng(SEED)
    sims = defaultdict(list)
    # Whole works are sampled with multiplicity. A repeated work contributes its
    # original intact features, never an artificial boundary to a second copy.
    for work_indices in rng.integers(len(names), size=(draws, len(names))):
        for name, value in refit(work_indices).items():
            sims[name].append(value)
    return {'draws': draws, 'seed': SEED, 'work_sizes': {w: len(indexes[w]) for w in names},
            'omit_each_training_work': omitted, 'bootstrap': {
                n: {'percentile_95': np.quantile(values, QUANTILES).tolist(),
                    'median': float(np.median(values)),
                    'fraction_negative': float(np.mean(np.asarray(values) < 0))}
                for n, values in sims.items()}}


def validate_corpus(rows, reference):
    if not rows or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Empty witness or nonunique sentence ID')
    metadata = {r['work_id']: (r['author'], r['genre']) for r in rows}
    if (any(not r['author'] or r['genre'] not in {'fu', 'prose'}
            or (r['author'], r['genre']) != metadata[r['work_id']]
            or type(r['target']) is not bool or 'score' in r or 'editorial_score' in r for r in rows)
            or len({a for a, _ in metadata.values()}) != len(metadata)):
        raise ValueError('Require one independent author per work, label-free contexts and explicit targets')
    if set(metadata) != {r['work_id'] for r in rows if r['target']}:
        raise ValueError('Every held-out work needs a target')
    for field in ('work_id', 'author'):
        if {r[field] for r in rows} & {r.get(field) for r in reference}:
            raise ValueError(f'Training overlap in {field}')
    old = {normalized_text(r) for r in reference}
    if any(normalized_text(r) in old or frozen.prev.incomplete(r) for r in rows if r['target']):
        raise ValueError('Target has a lacuna or its text occurred in training')
    for key_type in (lambda r: r['work_id'], lambda r: (r['work_id'], r['section'])):
        blocks = [key for key, _ in groupby(rows, key_type)]
        if len(blocks) != len(set(blocks)):
            raise ValueError('Noncontiguous work or section')


def cuda_prediction_check(models, x, values):
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('A CUDA allocation is required for GPU verification')
    def tensor(v):
        return torch.as_tensor(v, dtype=torch.float64, device='cuda')
    errors = {}
    for method, fit in models.items():
        raw = tensor(context.feature_matrix(x, fit['names']))
        standardized = torch.where(torch.isfinite(raw), raw - tensor(fit['means']), 0.) / tensor(fit['scales'])
        predicted = torch.clamp(fit['intercept'] + standardized @ tensor(fit['weights']), 1., 7.).cpu().numpy()
        assert_close(predicted, values[method], method)
        errors[method] = float(np.max(np.abs(predicted - values[method])))
    return {'device': torch.cuda.get_device_name(), 'maximum_absolute_error': errors, 'tolerance': TOLERANCE}


def forecast(root, run, gpu=False):
    inputs, results = run / 'inputs', run / 'results'
    results.mkdir(parents=True, exist_ok=True)
    archive = root / 'results/grammatical-training-expansion-20261122/results'
    train_path, model_path = archive / 'enriched-reference.json', archive / 'fresh-expanded-results.json'
    if frozen.digest(train_path) != frozen.prev.TRAIN_SHA or frozen.digest(model_path) != frozen.prev.MODEL_SHA:
        raise ValueError('Frozen training reference or current model hash mismatch')
    reference, rows = frozen.read(train_path), frozen.read(inputs / 'corpus.json')
    validate_corpus(rows, reference)
    lexicons, lex_hash = context.base.lexicon_data(root)
    if lex_hash != frozen.read(archive / 'summary.json')['lexicon_sha256']:
        raise ValueError('Historical dictionaries differ from the frozen scorer')
    def features(witness):
        lines = context.describe(witness, lexicons)
        for line in lines:
            line.complete = not frozen.prev.incomplete(line.row)
        return grammar.matrix_rows(lines, lines, context.in_context(lines))[0]
    tx = features(reference)
    labels = [r['score'] for r in reference]
    models = {m: context.fit_model(tx, labels, cols) for m, cols in COLUMNS.items()}
    archived_model = frozen.read(model_path)['models']['context_grammar']
    if list(models['with_rhyme']['names']) != archived_model['names']:
        raise ValueError('Current model feature order mismatch')
    for key in ('intercept', 'weights', 'scales', 'means', 'observed'):
        assert_close(models['with_rhyme'][key], archived_model[key], 'current fit ' + key)
    x = features(rows)
    predictions = {m: np.clip(context.predict(fit, x), 1., 7.) for m, fit in models.items()}
    released = np.clip(context.predict(archived_model, x), 1., 7.)
    assert_close(predictions['with_rhyme'], released, 'release forecasts')
    replay_error = float(np.max(np.abs(predictions['with_rhyme'] - released)))
    predictions['with_rhyme'] = released
    targets = []
    for i, row in enumerate(rows):
        if row['target']:
            targets.append({**{k: row[k] for k in ('id', 'work_id', 'author', 'genre')},
                            'features': {k: x[i][k] for k in CROSS + INTERNAL},
                            'predictions': {**{m: float(p[i]) for m, p in predictions.items()}, 'always_6': 6.}})
    result = {'models': models, 'training': {
        'units': len(tx), 'works': len({r['work_id'] for r in reference}),
        'full_replay_max_absolute_error': replay_error, 'full_raw_rhyme_slopes': slopes(models['with_rhyme']),
        'coefficient_sensitivity': coefficient_sensitivity(tx, labels, reference)},
        'hashes': {'corpus': frozen.digest(inputs / 'corpus.json'), 'fit': frozen.prev.MODEL_SHA,
                   'training': frozen.prev.TRAIN_SHA, 'lexicons': lex_hash,
                   'scoring_code': frozen.digest(Path(__file__))},
        'targets': len(targets), 'predictions': targets}
    if gpu:
        result['cuda'] = cuda_prediction_check(models, x, predictions)
    save_sealed(results / 'forecasts.json', result)
    return result


def paired_work_sample(rows, name, gpu=False, draws=TEST_DRAWS):
    by_work = defaultdict(list)
    for row in rows:
        by_work[row['work_id']].append(row)
    table = []
    for work, group in sorted(by_work.items()):
        table.append({'work_id': work, 'genre': group[0]['genre'], 'count': len(group),
                      'mae': {m: fmean(abs(r['predictions'][m] - r['score']) for r in group) for m in METHODS}})
    errors = np.asarray([[w['mae'][m] for m in METHODS] for w in table])
    if not len(errors):
        raise ValueError(f'No eligible works for {name}')
    by_genre = defaultdict(list)
    for i, row in enumerate(table):
        by_genre[row['genre']].append(i)
    rng = np.random.default_rng(SEED + ('all', 'fu', 'prose').index(name) + 1)
    # Condition on the sampling design. Each resampled work contributes all
    # target outcomes, paired across both sides of every model comparison.
    idx = np.column_stack([rng.choice(ids, size=(draws, len(ids))) for _, ids in sorted(by_genre.items())])
    simulated = errors[idx].mean(axis=1)
    means = errors.mean(axis=0)
    result = {'works': len(table), 'targets': len(rows), 'per_work': table,
              'work_equal_mae': dict(zip(METHODS, means.tolist())), 'full_minus': {},
              'rating_counts': dict(sorted(Counter(r['score'] for r in rows).items()))}
    intervals = []
    for j, comparator in enumerate(METHODS[1:], 1):
        delta = errors[:, 0] - errors[:, j]
        difference = float(delta.mean())
        bounds = np.quantile(simulated[:, 0] - simulated[:, j], QUANTILES).tolist()
        intervals.append(bounds)
        result['full_minus'][comparator] = {'difference': difference, 'paired_95': bounds,
            'work_counts_lower_equal_higher_error': [int(np.sum(delta < 0)), int(np.sum(delta == 0)),
                                                     int(np.sum(delta > 0))]}
    if gpu:
        import torch
        device = 'cuda'
        # Rebuild each work's errors from the individual frozen forecasts and ratings.
        tmp = []
        for w in table:
            group = by_work[w['work_id']]
            forecasts = torch.tensor([[r['predictions'][m] for m in METHODS] for r in group], device=device, dtype=torch.float64)
            ratings = torch.tensor([r['score'] for r in group], device=device, dtype=torch.float64)
            tmp.append((forecasts - ratings[:, None]).abs().mean(dim=0))
        matrix = torch.stack(tmp)
        sample = matrix[torch.as_tensor(idx, device=device)].mean(dim=1)
        bounds = torch.quantile(sample[:, :1] - sample[:, 1:], torch.tensor(QUANTILES, device=device, dtype=torch.float64), dim=0)
        assert_close(matrix.mean(0).cpu().numpy(), means, 'GPU work-equal errors')
        assert_close(bounds.T.cpu().numpy(), intervals, 'GPU paired intervals')
        result['cuda_verified'] = True
    return result


def compare(predictions, ratings, gpu=False):
    labels = {r['id']: r['score'] for r in ratings}
    if (len(labels) != len(ratings) or len(predictions) != len({r['id'] for r in predictions})
            or labels.keys() != {r['id'] for r in predictions}
            or any(not context.valid_score(v) for v in labels.values())):
        raise ValueError('Expected exactly one integer 1–7 written judgment per frozen target')
    rows = [{**r, 'score': labels[r['id']]} for r in predictions]
    if any(not isfinite(r['predictions'][m]) or not 1 <= r['predictions'][m] <= 7 for r in rows for m in METHODS):
        raise ValueError('Invalid forecast')
    groups = {'all': paired_work_sample(rows, 'all', gpu)}
    for name in ('fu', 'prose'):
        group = [r for r in rows if r['genre'] == name]
        if group:
            groups[name] = paired_work_sample(group, name, gpu)
    comparisons = groups['all']['full_minus']
    conditions = {m: comparisons[m]['difference'] < 0 and comparisons[m]['paired_95'][1] < 0
                  for m in ('without_cross_line', 'always_6')}
    return {'groups': groups, 'decision': {'criteria': conditions, 'passes': all(conditions.values())},
            'held_out_bootstrap': {'draws': TEST_DRAWS, 'seed_base': SEED, 'stratify_by': 'genre',
                                   'unit': 'work', 'interval': 'paired percentile 95%'},
            'joined': rows}


def evaluate(run, ratings_file, output_file, gpu):
    for name in (ratings_file, output_file):
        if not name or Path(name).name != name or not name.endswith('.json'):
            raise ValueError('Supply bare JSON filenames within inputs and results')
    inputs, results = run / 'inputs', run / 'results'
    forecasts_path = results / 'forecasts.json'
    scores = frozen.read(forecasts_path)
    if scores['hashes']['corpus'] != frozen.digest(inputs / 'corpus.json'):
        raise ValueError('The corpus has changed since forecasts were frozen')
    ratings = frozen.read(inputs / ratings_file)
    output = compare(scores['predictions'], ratings, gpu)
    output['hashes'] = {'forecast': frozen.digest(forecasts_path), 'ratings': frozen.digest(inputs / ratings_file)}
    save_sealed(results / output_file, output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('predict', 'evaluate'))
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path)
    parser.add_argument('--gpu', action='store_true')
    parser.add_argument('--ratings', default='ratings.json')
    parser.add_argument('--output', default='evaluation.json')
    args = parser.parse_args()
    if not args.run.resolve().is_relative_to(args.root.resolve()):
        parser.error('Keep the study and results under the Gilbreth project root')
    if args.phase == 'predict':
        result = forecast(args.root, args.run, args.gpu)
        print(f"Sealed forecasts on {result['targets']} target sentences.")
    else:
        result = evaluate(args.run, args.ratings, args.output, args.gpu)
        print(result['groups']['all']['work_equal_mae'], result['decision'])


if __name__ == '__main__':
    main()
