"""Measure the change in written scores after giving each training work equal weight."""

import argparse
from collections import Counter, defaultdict
from math import isfinite
from pathlib import Path

import numpy as np

from . import written_rhyme_ablation as baseline
from .yu_review_baseline import save_sealed

context = baseline.context
grammar = baseline.grammar
frozen = baseline.frozen
METHODS = ('equal_work', 'current', 'always_6')
CUTOFF = 6.50
SEED = 20261128
DRAWS = 10000
SHUFFLES = 999
COUNTS = ('hits', 'misses', 'false_positives', 'true_negatives', 'false_positives_among_sixes', 'actual_sixes')
CONTRASTS = ('sd', 'mean_within_work_sd', 'hits', 'recall', 'false_positive_rate', 'mae')


def equal_work_fit(rows, scores, work_ids, names):
    """Use the original ridge penalty and give each work total weight N / works."""
    sizes = Counter(work_ids)
    if not sizes or len(rows) != len(scores) or len(work_ids) != len(rows):
        raise ValueError('Require one training work ID and score per feature row')
    mass = len(rows) / len(sizes)
    weights = np.array([mass / sizes[w] for w in work_ids])
    y = np.asarray(scores, dtype=float)
    raw = context.feature_matrix(rows, names)
    seen = np.isfinite(raw)
    column_mass = weights @ seen
    means = np.divide(weights @ np.where(seen, raw, 0.), column_mass,
                      out=np.zeros(len(names)), where=column_mass > 0)
    centered = np.where(seen, raw - means, 0.)
    variance = np.divide(weights @ (centered ** 2), column_mass,
                         out=np.zeros(len(names)), where=column_mass > 0)
    # Set exactly constant observed columns to their observed value to prevent
    # scaling artificial differences caused by summing fractional row weights.
    for j in range(len(names)):
        observed = raw[seen[:, j], j]
        if len(observed) and np.min(observed) == np.max(observed):
            means[j] = observed[0]
            centered[:, j] = 0.
            variance[j] = 0.
    scales = np.where(variance > 0, np.sqrt(variance), 1.)
    x = centered / scales
    intercept = float(np.average(y, weights=weights))
    coefficients = np.linalg.solve(x.T @ (weights[:, None] * x) + context.base.RIDGE * np.eye(len(names)),
                                   x.T @ (weights * (y - intercept)))
    return {'names': list(names), 'means': means.tolist(), 'scales': scales.tolist(),
            'weights': coefficients.tolist(), 'observed': seen.sum(axis=0).tolist(),
            'observed_weight': column_mass.tolist(), 'intercept': intercept}


def features(witness, lexicons):
    lines = context.describe(witness, lexicons)
    for line in lines:
        line.complete = not frozen.prev.incomplete(line.row)
    return grammar.matrix_rows(lines, lines, context.in_context(lines))[0]


def forecast(root, run, gpu=False):
    archive = root / 'results/grammatical-training-expansion-20261122/results'
    reference_path = archive / 'enriched-reference.json'
    model_path = archive / 'fresh-expanded-results.json'
    if frozen.digest(reference_path) != frozen.prev.TRAIN_SHA or frozen.digest(model_path) != frozen.prev.MODEL_SHA:
        raise ValueError('The training reference or release model has changed')
    corpus = run / 'inputs/corpus.json'
    rows, reference = frozen.read(corpus), frozen.read(reference_path)
    baseline.validate_corpus(rows, reference)
    lexicons, lex_hash = context.base.lexicon_data(root)
    if lex_hash != frozen.read(archive / 'summary.json')['lexicon_sha256']:
        raise ValueError('The release lexicons have changed')
    train, test = features(reference, lexicons), features(rows, lexicons)
    grades = [r['score'] for r in reference]
    work_ids = [r['work_id'] for r in reference]
    current = frozen.read(model_path)['models']['context_grammar']
    if current['names'] != list(baseline.FULL):
        raise ValueError('Release model columns have changed')
    replay = context.fit_model(train, grades, baseline.FULL)
    for key in ('intercept', 'means', 'scales', 'weights', 'observed'):
        baseline.assert_close(replay[key], current[key], 'release refit ' + key)
    models = {'equal_work': equal_work_fit(train, grades, work_ids, baseline.FULL), 'current': current}
    pred = {m: np.clip(context.predict(fit, test), 1., 7.) for m, fit in models.items()}
    old_fit = np.clip(context.predict(replay, test), 1., 7.)
    baseline.assert_close(old_fit, pred['current'], 'release predictions')
    sizes = Counter(work_ids)
    mass = len(reference) / len(sizes)
    result = {'models': models, 'training': {
        'units': len(train), 'works': len(sizes), 'work_sizes': dict(sizes), 'each_work_mass': mass,
        'row_weight_by_work': {w: mass / n for w, n in sizes.items()}, 'sum_row_weights': len(train),
        'full_replay_max_absolute_error': float(np.max(np.abs(old_fit - pred['current']))),
        'ridge': context.base.RIDGE, 'fit_weighting': 'Observed training-feature moments, response mean and ridge loss use the same row weights.'},
        'hashes': {'corpus': frozen.digest(corpus), 'fit': frozen.prev.MODEL_SHA, 'training': frozen.prev.TRAIN_SHA,
                   'lexicons': lex_hash, 'scoring_code': frozen.digest(Path(__file__))},
        'predictions': [{**{k: r[k] for k in ('id', 'work_id', 'author', 'genre')},
                         'predictions': {**{m: float(p[i]) for m, p in pred.items()}, 'always_6': 6.}}
                        for i, r in enumerate(rows) if r['target']]}
    result['targets'] = len(result['predictions'])
    if gpu:
        result['cuda'] = baseline.cuda_prediction_check(models, test, pred)
    output = run / 'results'
    output.mkdir(parents=True, exist_ok=True)
    save_sealed(output / 'forecasts.json', result)
    return result


def work_stats(y, p):
    """One row per work for each sufficient statistic, all three models paired."""
    seven = y[:, None] == 7
    calls = p >= CUTOFF
    return {'mean': p.mean(axis=0), 'within_sd': p.std(axis=0), 'minimum': p.min(axis=0), 'maximum': p.max(axis=0),
            'mae': np.abs(p - y[:, None]).mean(axis=0), 'hits': (calls & seven).sum(axis=0),
            'misses': (~calls & seven).sum(axis=0), 'false_positives': (calls & ~seven).sum(axis=0),
            'true_negatives': (~calls & ~seven).sum(axis=0), 'false_positives_among_sixes': (calls & (y[:, None] == 6)).sum(axis=0),
            'actual_sixes': np.full(len(METHODS), (y == 6).sum())}


def ratio(num, denominator):
    return np.divide(num, denominator, out=np.full(num.shape, np.nan), where=denominator > 0)


def aggregate(stats, indexes):
    """Return draws by method. Give each sampled work equal mass for moments and MAE."""
    means = stats['mean'][indexes]
    overall = means.mean(axis=1)
    within = stats['within_sd'][indexes]
    variance = (within ** 2 + (means - overall[:, None, :]) ** 2).mean(axis=1)
    output = {'mean': overall, 'sd': np.sqrt(variance), 'mean_within_work_sd': within.mean(axis=1),
              'minimum': stats['minimum'][indexes].min(axis=1), 'maximum': stats['maximum'][indexes].max(axis=1),
              'mae': stats['mae'][indexes].mean(axis=1)}
    for metric in COUNTS:
        output[metric] = stats[metric][indexes].sum(axis=1)
    hits, fp = output['hits'], output['false_positives']
    output['actual_sevens'] = hits + output['misses']
    output['predicted_sevens'] = hits + fp
    output['recall'] = ratio(hits, output['actual_sevens'])
    output['precision'] = ratio(hits, output['predicted_sevens'])
    output['false_positive_rate'] = ratio(fp, fp + output['true_negatives'])
    return output


def method_metrics(values, i):
    return {m: {k: a[i, j].item() if np.isfinite(a[i, j]) else None for k, a in values.items()}
            for j, m in enumerate(METHODS)}


def gained_and_lost(by_work, competitor):
    gained, lost = [], []
    for work, group in sorted(by_work.items()):
        for row in group:
            if row['score'] == 7:
                a = row['predictions']['equal_work'] >= CUTOFF
                b = row['predictions'][competitor] >= CUTOFF
                if a != b:
                    (gained if a else lost).append([work, row['id']])
    return {'gained': len(gained), 'lost': len(lost), 'gained_works': len({w for w, _ in gained}),
            'lost_works': len({w for w, _ in lost}), 'gained_ids': gained, 'lost_ids': lost}


def shuffle_hits(by_work, seed, repeats=SHUFFLES):
    rng = np.random.default_rng(seed)
    draws = np.zeros((repeats, len(METHODS)), dtype=int)
    observed = np.zeros(len(METHODS), dtype=int)
    for work, rows in sorted(by_work.items()):
        gold = np.array([r['score'] == 7 for r in rows], dtype=int)
        calls = np.array([[r['predictions'][m] >= CUTOFF for m in METHODS] for r in rows], dtype=int)
        observed += gold @ calls
        permutations = np.stack([rng.permutation(gold) for _ in range(repeats)])
        draws += permutations @ calls
    return {m: {'observed_hits': int(observed[j]), 'mean_null_hits': float(draws[:, j].mean()),
                'one_sided_plus_one': (1 + int((draws[:, j] >= observed[j]).sum())) / (1 + repeats),
                'informative': bool(draws[:, j].max() != draws[:, j].min())} for j, m in enumerate(METHODS)}


def gpu_verify(raw, idx, simulated):
    """Replay cluster resampling on the GPU directly from item-level targets and forecasts."""
    import torch
    work_stats_gpu = []
    for y, p in raw:
        pred = torch.as_tensor(p, dtype=torch.float64, device='cuda')
        gold = torch.as_tensor(y[:, None], device='cuda')
        called = pred >= CUTOFF
        work_stats_gpu.append(torch.stack([
            pred.mean(dim=0), pred.std(dim=0, unbiased=False), (pred-gold).abs().mean(dim=0),
            (called & (gold == 7)).sum(dim=0), (gold == 7).sum().expand(len(METHODS)),
            (called & (gold < 7)).sum(dim=0), (gold < 7).sum().expand(len(METHODS))]))
    selected = torch.stack(work_stats_gpu)[torch.as_tensor(idx, device='cuda')]
    means, sd, mae, hits, positives, fp, negatives = selected.unbind(dim=2)
    center = means.mean(dim=1, keepdim=True)
    total_hits = hits.sum(dim=1)
    replay = {'sd': (sd.square() + (means-center).square()).mean(dim=1).sqrt(),
              'mean_within_work_sd': sd.mean(dim=1), 'mae': mae.mean(dim=1), 'hits': total_hits,
              'recall': total_hits / positives.sum(dim=1), 'false_positive_rate': fp.sum(dim=1) / negatives.sum(dim=1)}
    for metric, array in replay.items():
        if not np.allclose(array.cpu().numpy(), simulated[metric], atol=1e-10, rtol=0., equal_nan=True):
            raise ValueError(f'CUDA sample replay disagrees for {metric}')


def group_result(rows, name, gpu=False):
    by_work = defaultdict(list)
    for r in rows:
        by_work[r['work_id']].append(r)
    works = sorted(by_work)
    raw = [(np.array([r['score'] for r in by_work[w]]),
            np.array([[r['predictions'][m] for m in METHODS] for r in by_work[w]], dtype=float)) for w in works]
    parts = [work_stats(y, p) for y, p in raw]
    stats = {k: np.stack([part[k] for part in parts]) for k in parts[0]}
    whole = np.arange(len(works))
    point = aggregate(stats, whole[None, :])
    methods = method_metrics(point, 0)
    each = aggregate(stats, whole[:, None])
    per_work = [{'work_id': w, 'genre': by_work[w][0]['genre'], 'count': len(by_work[w]),
                 'methods': method_metrics(each, i)} for i, w in enumerate(works)]
    strata = defaultdict(list)
    for i, w in enumerate(works):
        strata[by_work[w][0]['genre']].append(i)
    seed = SEED + ('all', 'fu', 'prose').index(name)
    rng = np.random.default_rng(seed)
    idx = np.column_stack([rng.choice(ids, (DRAWS, len(ids))) for _, ids in sorted(strata.items())])
    simulated = aggregate(stats, idx)
    if gpu:
        gpu_verify(raw, idx, simulated)
    comparisons = {}
    for j, competitor in enumerate(METHODS[1:], 1):
        comparisons[competitor] = {}
        for metric in CONTRASTS:
            deltas = simulated[metric][:, 0] - simulated[metric][:, j]
            usable = deltas[np.isfinite(deltas)]
            delta = point[metric][0, 0] - point[metric][0, j]
            comparisons[competitor][metric] = {
                'difference': float(delta) if np.isfinite(delta) else None,
                'paired_95': np.quantile(usable, (.025, .975)).tolist() if len(usable) else None,
                'valid_draws': len(usable)}
    return {'works': len(works), 'targets': len(rows), 'per_work': per_work, 'methods': methods,
            'rating_counts': dict(sorted(Counter(r['score'] for r in rows).items())),
            'equal_work_minus': comparisons, 'cuda_verified': gpu,
            'changed_sevens': {m: gained_and_lost(by_work, m) for m in METHODS[1:]},
            'within_work_shuffle': {'draws': SHUFFLES, 'seed': seed + 1000,
                                    'methods': shuffle_hits(by_work, seed + 1000)}}


def compare(predictions, ratings, gpu=False):
    labels = {r['id']: r['score'] for r in ratings}
    ids = {r['id'] for r in predictions}
    if (not labels or len(labels) != len(ratings) or ids != labels.keys() or len(ids) != len(predictions)
            or any(not context.valid_score(y) for y in labels.values())):
        raise ValueError('Expected one integer 1–7 judgment per frozen target')
    joined = [{**r, 'score': labels[r['id']]} for r in predictions]
    if any(not isfinite(r['predictions'][m]) or not 1 <= r['predictions'][m] <= 7 for r in joined for m in METHODS):
        raise ValueError('Forecasts must be finite scores in [1,7]')
    groups = {'all': group_result(joined, 'all', gpu)}
    for genre in ('fu', 'prose'):
        subset = [r for r in joined if r['genre'] == genre]
        if subset:
            groups[genre] = group_result(subset, genre, gpu)
    all_ = groups['all']
    fit, current, six = (all_['methods'][m] for m in METHODS)
    gates = {'larger_overall_sd': fit['sd'] > current['sd'],
             'larger_mean_within_work_sd': fit['mean_within_work_sd'] > current['mean_within_work_sd'],
             'more_hits_than_both': fit['hits'] > max(current['hits'], six['hits']),
             'new_hits_in_two_works': all_['changed_sevens']['current']['gained_works'] >= 2,
             'no_additional_pooled_false_positives': fit['false_positives'] <= current['false_positives'],
             'no_worse_mae_than_both': fit['mae'] <= min(current['mae'], six['mae'])}
    return {'groups': groups, 'decision': {'criteria': gates, 'passes': all(gates.values())},
            'bootstrap': {'draws': DRAWS, 'seed_base': SEED, 'stratify_by': 'genre', 'unit': 'work'},
            'cutoff': CUTOFF, 'joined': joined}


def evaluate(run, ratings_file, output_file, gpu=False):
    for name in (ratings_file, output_file):
        if not name or Path(name).name != name or not name.endswith('.json'):
            raise ValueError('Supply bare JSON filenames within inputs and results')
    inputs, results = run / 'inputs', run / 'results'
    forecasts = results / 'forecasts.json'
    pred = frozen.read(forecasts)
    ratings = inputs / ratings_file
    if pred['hashes']['corpus'] != frozen.digest(inputs / 'corpus.json'):
        raise ValueError('Forecasts do not match the sealed source corpus')
    output = compare(pred['predictions'], frozen.read(ratings), gpu)
    output['hashes'] = {'forecast': frozen.digest(forecasts), 'ratings': frozen.digest(ratings)}
    save_sealed(results / output_file, output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('predict', 'evaluate'))
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path)
    parser.add_argument('--gpu', action='store_true')
    parser.add_argument('--ratings', default='ratings.json')
    parser.add_argument('--output', default='evaluation.json')
    args = parser.parse_args()
    if not args.run.resolve().is_relative_to(args.root.resolve()):
        parser.error('Keep the corpus and results on the Gilbreth project volume')
    if args.phase == 'predict':
        out = forecast(args.root, args.run, args.gpu)
        print(f"Sealed forecasts on {out['targets']} targets.")
    else:
        out = evaluate(args.run, args.ratings, args.output, args.gpu)
        print(out['decision'])
