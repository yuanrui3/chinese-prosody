"""Train a within-work preference model of written musical beauty and evaluate frozen rankings."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from . import work_weighted_scores as earlier
from .written_rhyme_readers import verify_inputs
from .yu_review_baseline import save_sealed

baseline = earlier.baseline
context = earlier.context
frozen = earlier.frozen
METHODS = ('pairwise', 'current', 'always_6')
ENDPOINTS = {'seven_vs_five_six': (5, 6), 'seven_vs_five': (5,), 'seven_vs_six': (6,)}
PENALTY = 0.10
DRAWS = 10000
SHUFFLES = 999
SEED = 20261129


def standardized(model, rows):
    raw = context.feature_matrix(rows, model['names'])
    return np.where(np.isfinite(raw), raw - model['means'], 0.) / model['scales']


def training_pairs(x, grades, works):
    """Orient every eligible pair seven-first. Give each work equal total mass."""
    if len(x) != len(grades) or len(x) != len(works):
        raise ValueError('Training feature, label and work counts must match')
    labels = np.asarray(grades)
    work_ids = np.asarray(works)
    blocks, weights, counts = [], [], {}
    for work in sorted(set(works)):
        inside = work_ids == work
        high = np.flatnonzero(inside & (labels == 7))
        low = np.flatnonzero(inside & np.isin(labels, (5, 6)))
        count = int(len(high) * len(low))
        counts[work] = {'units': int(inside.sum()), 'sevens': len(high),
                        'fives': int(np.sum(inside & (labels == 5))),
                        'sixes': int(np.sum(inside & (labels == 6))), 'pairs': count}
        if count:
            blocks.append((x[high, None, :] - x[low][None, :, :]).reshape(count, x.shape[1]))
            weights.append(np.full(count, 1. / count))
    if not blocks:
        raise ValueError('No training work contains a 7 and a 5 or 6')
    return np.vstack(blocks), np.concatenate(weights) / len(blocks), counts


def fit_ranker(differences, mass):
    """Newton descent for the strictly convex work-balanced logistic objective."""
    n_features = differences.shape[1]
    beta = np.zeros(n_features)
    identity = np.eye(n_features)
    def loss(b):
        return mass @ np.logaddexp(0., -(differences @ b)) + .5 * PENALTY * (b @ b)
    for step in range(100):
        margin = differences @ beta
        error = np.exp(-np.logaddexp(0., margin))
        gradient = PENALTY * beta - differences.T @ (mass * error)
        largest = float(np.max(np.abs(gradient)))
        if largest <= 1e-9:
            return beta, {'iterations': step, 'max_abs_gradient': largest, 'objective': float(loss(beta))}
        curvature = mass * error * (1. - error)
        hessian = PENALTY * identity + differences.T @ (curvature[:, None] * differences)
        direction = np.linalg.solve(hessian, gradient)
        start = loss(beta)
        fraction = 1.
        while loss(beta - fraction * direction) > start + 1e-15:
            fraction *= .5
            if fraction < 1e-12:
                raise RuntimeError('Failed to find a descent step in pairwise logistic fit')
        beta -= fraction * direction
    raise RuntimeError('Pairwise logistic fit failed to converge')


def verify_gpu(model, test, rank_scores, current_scores, delta, mass, beta):
    import torch
    device = 'cuda'
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA allocation required')
    def tensor(x):
        return torch.as_tensor(x, dtype=torch.float64, device=device)
    raw = tensor(context.feature_matrix(test, model['names']))
    x = torch.where(torch.isfinite(raw), raw - tensor(model['means']), 0.) / tensor(model['scales'])
    fitted_beta = tensor(beta)
    candidate = (x @ fitted_beta).cpu().numpy()
    released = (model['intercept'] + x @ tensor(model['weights'])).clamp(1, 7).cpu().numpy()
    baseline.assert_close(candidate, rank_scores, 'GPU ranking utility')
    baseline.assert_close(released, current_scores, 'GPU release scores')
    differences = tensor(delta)
    gradient = PENALTY * fitted_beta - differences.T @ (tensor(mass) * torch.sigmoid(-(differences @ fitted_beta)))
    residual = float(gradient.abs().max().item())
    if residual > 1.1e-9:
        raise ValueError('GPU fit stationarity check failed')
    return {'device': torch.cuda.get_device_name(), 'gradient_max': residual,
            'max_prediction_errors': {'pairwise': float(np.max(np.abs(candidate - rank_scores))),
                                      'current': float(np.max(np.abs(released - current_scores)))}}


def forecast(root, run, gpu=False):
    inputs, results = run / 'inputs', run / 'results'
    verify_inputs(inputs)
    archive = root / 'results/grammatical-training-expansion-20261122/results'
    train_file = archive / 'enriched-reference.json'
    model_file = archive / 'fresh-expanded-results.json'
    if frozen.digest(train_file) != frozen.prev.TRAIN_SHA or frozen.digest(model_file) != frozen.prev.MODEL_SHA:
        raise ValueError('Reference training works or release model changed')
    reference, rows = frozen.read(train_file), frozen.read(inputs / 'corpus.json')
    baseline.validate_corpus(rows, reference)
    current = frozen.read(model_file)['models']['context_grammar']
    lexicons, lex_hash = context.base.lexicon_data(root)
    if lex_hash != frozen.read(archive / 'summary.json')['lexicon_sha256'] or current['names'] != list(baseline.FULL):
        raise ValueError('Released dictionaries or feature order changed')
    train = earlier.features(reference, lexicons)
    work_ids = [r['work_id'] for r in reference]
    grades = [r['score'] for r in reference]
    replay = context.fit_model(train, grades, current['names'])
    for key in ('intercept', 'means', 'scales', 'weights', 'observed'):
        baseline.assert_close(replay[key], current[key], 'reference ' + key)
    delta, mass, counts = training_pairs(standardized(current, train), grades, work_ids)
    beta, optimizer = fit_ranker(delta, mass)
    fit = {k: current[k] for k in ('names', 'means', 'scales')}
    fit.update(weights=beta.tolist(), intercept=0., penalty=PENALTY)
    test = earlier.features(rows, lexicons)
    candidate = standardized(current, test) @ beta
    released = np.clip(context.predict(current, test), 1., 7.)
    preds = [{**{k: r[k] for k in ('id','work_id','author','genre')},
              'predictions': {'pairwise': float(candidate[i]), 'current': float(released[i]), 'always_6': 6.}}
             for i,r in enumerate(rows) if r['target']]
    margins = delta @ beta
    result = {'targets': len(preds), 'predictions': preds, 'models': {'pairwise': fit, 'current': current},
              'training': {'works': len(counts), 'units': len(train), 'pairs': len(mass),
                           'eligible_works': sum(v['pairs'] > 0 for v in counts.values()), 'by_work': counts,
                           'unit_work_pair_mass': '1 / (number of eligible works * pairs in this work)',
                           'work_equal_training_concordance': float(mass @ ((margins > 0) + .5 * (margins == 0))),
                           'optimizer': optimizer, 'penalty': PENALTY},
              'hashes': {'corpus': frozen.digest(inputs / 'corpus.json'), 'training': frozen.prev.TRAIN_SHA,
                         'fit': frozen.prev.MODEL_SHA, 'lexicons': lex_hash, 'scoring_code': frozen.digest(Path(__file__))}}
    if gpu:
        result['cuda'] = verify_gpu(current, test, candidate, released, delta, mass, beta)
    results.mkdir(parents=True, exist_ok=True)
    save_sealed(results/'forecasts.json', result)
    return result


def work_comparisons(rows, lower, shuffles, rng):
    y = np.array([r['score'] for r in rows])
    p = np.array([[r['predictions'][m] for m in METHODS] for r in rows])
    higher = p[:, None, :] > p[None, :, :]
    equal = p[:, None, :] == p[None, :, :]
    valid = (y[:, None] == 7) & np.isin(y, lower)[None, :]
    n = int(valid.sum())
    wins, ties = higher[valid].sum(axis=0), equal[valid].sum(axis=0)
    work = {'work_id': rows[0]['work_id'], 'genre': rows[0]['genre'], 'targets': len(y),
            'sevens': int(np.sum(y == 7)), 'lower': int(np.isin(y, lower).sum()), 'pairs': n,
            'methods': {m: {'wins': int(wins[i]), 'ties': int(ties[i]), 'losses': int(n-wins[i]-ties[i]),
                            'concordance': float((wins[i] + .5 * ties[i]) / n) if n else None}
                        for i,m in enumerate(METHODS)}}
    if not n:
        return work, None
    # Random permutations preserve every grade count, including two sentences sharing a 7.
    ys = y[np.argsort(rng.random((shuffles, len(y))), axis=1)]
    selected = (ys[:, :, None] == 7) & np.isin(ys, lower)[:, None, :]
    null = np.einsum('sij,ijm->sm', selected.astype(float), higher + .5*equal) / n
    return work, null


def endpoint(rows, lower, seed, draws, shuffles, gpu=False):
    by_work = defaultdict(list)
    for row in rows:
        by_work[row['work_id']].append(row)
    rng = np.random.default_rng(seed)
    works, nulls = [], []
    for wid in sorted(by_work):
        work, null = work_comparisons(by_work[wid], lower, shuffles, rng)
        works.append(work)
        if null is not None:
            nulls.append(null)
    eligible = [w for w in works if w['pairs']]
    pairs = sum(w['pairs'] for w in eligible)
    matrices = np.array([[w['methods'][m]['concordance'] for m in METHODS] for w in works], dtype=float)
    methods, paired, shuffle = {}, {}, {}
    for j,m in enumerate(METHODS):
        cnt = {k:sum(w['methods'][m][k] for w in works) for k in ('wins','ties','losses')}
        methods[m] = dict(cnt, work_equal_concordance=float(np.nanmean(matrices[:,j])) if pairs else None,
                          pair_pooled_concordance=(cnt['wins']+.5*cnt['ties'])/pairs if pairs else None)
    strata = defaultdict(list)
    for i,w in enumerate(works):
        strata[w['genre']].append(i)
    # Sample all works in their original genre strata. Works lacking an eligible
    # comparison have zero weight in the estimand and remain in the coverage count.
    indexes = np.column_stack([rng.choice(v, size=(draws,len(v))) for _,v in sorted(strata.items())])
    samples = matrices[indexes]
    denom = np.isfinite(samples[:,:,0]).sum(axis=1)
    keep = denom > 0
    boot = np.nansum(samples[keep],axis=1) / denom[keep,None]
    if gpu and keep.any():
        import torch
        # Rebuild observed work scores from line forecasts and grades on the GPU.
        gpu_work = []
        for w in works:
            subset = by_work[w['work_id']]
            pp = torch.tensor([[r['predictions'][m] for m in METHODS] for r in subset],
                              dtype=torch.float64, device='cuda')
            yy = torch.tensor([r['score'] for r in subset], device='cuda')
            dif = pp[yy == 7].unsqueeze(1) - pp[torch.isin(yy, yy.new_tensor(lower))].unsqueeze(0)
            gpu_work.append(((dif > 0).double() + .5 * (dif == 0).double()).mean(dim=(0,1)))
        sample = torch.stack(gpu_work)[torch.as_tensor(indexes[keep],device='cuda')].nanmean(dim=1)
        baseline.assert_close(sample.cpu().numpy(), boot, 'GPU ranking bootstrap')
    average_null = np.mean(nulls, axis=0) if pairs else None
    for j,m in enumerate(METHODS):
        score = methods[m]['work_equal_concordance']
        if pairs:
            scores = average_null[:,j]
            # The integer work counts can yield equivalent analytical scores a few ulps apart.
            p = float((1 + np.count_nonzero(scores >= score - 1e-12))/(1 + shuffles))
            shuffle[m] = {'mean':float(scores.mean()), 'one_sided_plus_one':p,
                          'informative':bool(np.ptp(scores) > 1e-12)}
        else:
            shuffle[m] = {'mean':None, 'one_sided_plus_one':None, 'informative':False}
        if j:
            interval = np.quantile(boot[:,0]-boot[:,j], (.025,.975)).tolist() if keep.any() else None
            paired[m] = {'difference': methods['pairwise']['work_equal_concordance']-score if pairs else None,
                         'paired_95':interval, 'valid_draws':int(keep.sum())}
    return {'works':len(works), 'eligible_works':len(eligible), 'targets':len(rows), 'pairs':pairs,
            'sevens':sum(w['sevens'] for w in works), 'eligible_sevens':sum(w['sevens'] for w in eligible),
            'methods':methods, 'paired':paired, 'shuffle':shuffle, 'per_work':works}


def compare(predictions, ratings, gpu=False, draws=DRAWS, shuffles=SHUFFLES):
    scores = {r['id']:r['score'] for r in ratings}
    if (not scores or len(scores) != len(ratings) or len(scores) != len(predictions)
            or scores.keys() != {r['id'] for r in predictions}
            or not all(context.valid_score(g) for g in scores.values())):
        raise ValueError('One grade 1–7 is required for every forecast')
    rows = [{**r,'score':scores[r['id']]} for r in predictions]
    if any(not np.isfinite([r['predictions'][m] for m in METHODS]).all()
           or r['predictions']['always_6'] != 6 for r in rows):
        raise ValueError('Nonfinite predictions or invalid constant comparator')
    groups = {}
    for i,group in enumerate(('all','fu','prose')):
        subset = [r for r in rows if group == 'all' or r['genre'] == group]
        if subset:
            groups[group] = {name: endpoint(subset, lower, SEED + 10*i+j, draws, shuffles, gpu)
                             for j,(name,lower) in enumerate(ENDPOINTS.items())}
    primary = groups['all']['seven_vs_five_six']
    criteria = {'lower_bounds_above_both': all(d['paired_95'] is not None and d['paired_95'][0] > 0
                                              for d in primary['paired'].values()),
                'two_informative_works_each_genre': all(
                    g in groups and groups[g]['seven_vs_five_six']['eligible_works'] >= 2 for g in ('fu','prose'))}
    return {'joined':rows, 'groups':groups, 'decision':{'criteria':criteria,'passes':all(criteria.values())},
            'ranking':'Within-work 7 over lower grade; exact ties receive half credit.',
            'bootstrap_draws':draws, 'shuffles':shuffles, 'seed':SEED, 'cuda_checked':gpu,
            'grade_counts':dict(sorted(Counter(scores.values()).items()))}


def evaluate(run, ratings_file, output_file, gpu=False):
    for name in (ratings_file, output_file):
        if not name or Path(name).name != name or not name.endswith('.json'):
            raise ValueError('Use plain JSON filenames within the study inputs and outputs')
    inputs, results = run/'inputs', run/'results'
    verify_inputs(inputs)
    file = results/'forecasts.json'
    predictions = frozen.read(file)
    if predictions['hashes']['corpus'] != frozen.digest(inputs/'corpus.json'):
        raise ValueError('Changed forecast corpus')
    labels = inputs/ratings_file
    analysis = compare(predictions['predictions'], frozen.read(labels), gpu)
    analysis['hashes'] = {'forecast':frozen.digest(file), 'ratings':frozen.digest(labels)}
    save_sealed(results/output_file, analysis)
    return analysis


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('predict','evaluate'))
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path)
    parser.add_argument('--gpu', action='store_true')
    parser.add_argument('--ratings', default='ratings.json')
    parser.add_argument('--output', default='evaluation.json')
    args = parser.parse_args()
    if not args.run.resolve().is_relative_to(args.root.resolve()):
        parser.error('Use a run directory on the Gilbreth project volume')
    if args.phase == 'predict':
        result = forecast(args.root, args.run, args.gpu)
        print('Frozen targets', result['targets'], 'training pairs', result['training']['pairs'])
    else:
        result = evaluate(args.run, args.ratings, args.output, args.gpu)
        print(result['decision'])
