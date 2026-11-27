"""Audit the blind within-work ranking study and report work-level concordance."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from math import isclose, isfinite
from pathlib import Path
from random import Random
from statistics import fmean

METHODS = ('pairwise', 'current', 'always_6')
ENDPOINTS = {'seven_vs_five_six': (5, 6), 'seven_vs_five': (5,), 'seven_vs_six': (6,)}


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def check(test, message):
    if not test:
        raise ValueError(message)


def index(rows, key='id'):
    lookup = {r[key]: r for r in rows}
    check(len(lookup) == len(rows), f'Duplicate {key}')
    return lookup


def same(a, b):
    if a is None or b is None:
        return a is b
    return isclose(a, b, rel_tol=0., abs_tol=1e-10)


def mean(values):
    return fmean(values) if values else None


def source_packet(run, forecast):
    inputs = run / 'inputs'
    seal = read(inputs / 'source-seal.json')
    for name, expected in seal.items():
        check(digest(inputs / name) == expected, f'Changed sealed input {name}')
    check(forecast['hashes']['corpus'] == digest(inputs / 'corpus.json'), 'Forecast corpus changed')
    all_rows = read(inputs / 'corpus.json')
    targets = index([r for r in all_rows if r['target']])
    forecasts = index(forecast['predictions'])
    check(targets.keys() == forecasts.keys(), 'Forecast IDs differ from the source roster')
    packet = index(read(inputs / 'reading.json'), 'blind_id')
    key = read(inputs / 'reader-key.json')
    check(packet.keys() == key.keys() and set(key.values()) == targets.keys()
          and len(key) == len(targets), 'Incomplete or non-bijective blind key')
    for b, i in key.items():
        text, f = targets[i], forecasts[i]
        check(text['text'] == packet[b]['text'] and
              all(text[k] == f[k] for k in ('genre', 'work_id', 'author')), f'Changed target {i}')
        predictions = f['predictions']
        check(set(METHODS) == predictions.keys() and all(isfinite(v) for v in predictions.values())
              and predictions['always_6'] == 6., f'Invalid utility or baseline for {i}')
    source = read(inputs / 'sources.json')
    works = index(source['works'], 'work_id')
    check(len({w['author'] for w in works.values()}) == len(works), 'Author reused')
    blocks = defaultdict(list)
    period_pairs = defaultdict(list)
    for r in forecasts.values():
        check(r['author'] == works[r['work_id']]['author'] and r['genre'] == works[r['work_id']]['genre'],
              f'Changed author credit or genre at {r["id"]}')
        blocks[r['work_id']].append(r)
    check(blocks.keys() == works.keys(), 'Source work with no target')
    for wid, w in works.items():
        check(len(blocks[wid]) == w['targets'], f'Wrong number of targets in {wid}')
        period_pairs[w['period_pair']].append(wid)
        if (inputs / 'editions').is_dir():
            check(digest(inputs / 'editions' / f'{w["revision"]}.wiki') == w['wiki_sha256'],
                  f'Changed edition in {wid}')
    for members in period_pairs.values():
        check(len(members) == 2 and {works[w]['genre'] for w in members} == {'fu','prose'}
              and len({works[w]['period_evidence']['stratum'] for w in members}) == 1,
              'Incorrect period-matched pair')
    if (inputs / 'catalog').is_dir():
        for name, checksum in source.get('catalogs', {}).items():
            check(digest(inputs / 'catalog' / name) == checksum, f'Changed catalogue {name}')
    info = {
        'context_rows': len(all_rows), 'targets': len(targets), 'period_pairs': len(period_pairs),
        'screened': len(source['screened']), 'reserved': source['reserved'],
        'source_seal_sha256': digest(inputs / 'source-seal.json'),
        'raw_editions_present': (inputs / 'editions').is_dir(),
        'works': [{k: w[k] for k in ('work_id', 'author', 'title', 'genre', 'revision', 'source_url',
                                      'period_pair', 'period_evidence', 'targets')} for w in works.values()]}
    return forecasts, blocks, period_pairs, packet, key, info


def checked_grades(run, packet, key, role, suffix, agreement):
    path = Path((run / 'readers' / f'{role}.path').read_text().strip()) / 'ratings.tsv'
    check(digest(path) == agreement['reader_sha256'][int(bool(suffix))], 'Changed original reader submission')
    rated = index(read(run / 'inputs' / f'ratings{suffix}.json'))
    seen = set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.reader(stream, delimiter='\t', quoting=csv.QUOTE_NONE):
            check(len(row) == 4, 'Wrong number of fields in an original rating')
            b, grade, quote, reason = row
            check(b in key and b not in seen and grade in tuple('1234567') and quote.strip()
                  and quote in packet[b]['text'] and reason.strip(), f'Bad response for {b}')
            seen.add(b)
            i = key[b]
            check(rated[i] == dict(id=i, score=int(grade), quote=quote, reason=reason),
                  f'Joined rating differs from original for {b}')
    check(seen == key.keys() and rated.keys() == set(key.values()), 'Incomplete rating roster')
    return {i: r['score'] for i, r in rated.items()}


def paired_counts(rows, grades, lower):
    high = sorted((r for r in rows if grades[r['id']] == 7), key=lambda r:r['id'])
    low = sorted((r for r in rows if grades[r['id']] in lower), key=lambda r:r['id'])
    counts = {m: Counter() for m in METHODS}
    examples = {}
    for a in high:
        for b in low:
            comparisons = {}
            for m in METHODS:
                va, vb = a['predictions'][m], b['predictions'][m]
                result = 'wins' if va > vb else 'losses' if va < vb else 'ties'
                counts[m][result] += 1
                comparisons[m] = result
            kind = f'{comparisons["pairwise"]}_vs_{comparisons["current"]}'
            if kind not in examples:
                examples[kind] = {
                    'work_id': a['work_id'], 'seven_id': a['id'], 'lower_id': b['id'],
                    'lower_grade': grades[b['id']], 'seven_scores': a['predictions'],
                    'lower_scores': b['predictions']}
    pairs = len(high)*len(low)
    metrics = {}
    for m, c in counts.items():
        metrics[m] = {k:c[k] for k in ('wins','ties','losses')}
        metrics[m]['concordance'] = (c['wins'] + .5*c['ties']) / pairs if pairs else None
    return dict(n=len(rows), sevens=len(high), lower=len(low), pairs=pairs, methods=metrics), examples


def endpoint(blocks, grades, lower, official):
    works, examples = {}, {}
    for wid, rows in sorted(blocks.items()):
        works[wid], cases = paired_counts(rows, grades, lower)
        for kind, case in cases.items():
            examples.setdefault(kind, case)
    valid = [w for w in works.values() if w['pairs']]
    pairs = sum(w['pairs'] for w in valid)
    counts = dict(works=len(works), targets=sum(w['n'] for w in works.values()),
                  eligible_works=len(valid), sevens=sum(w['sevens'] for w in works.values()),
                  eligible_sevens=sum(w['sevens'] for w in valid), pairs=pairs)
    for k,v in counts.items():
        check(v == official[k], f'Incorrect endpoint denominator {k}')
    saved_works = index(official['per_work'], 'work_id')
    check(saved_works.keys() == works.keys(), 'Incorrect per-work roster')
    for wid, checked in works.items():
        saved = saved_works[wid]
        check(saved['targets'] == checked['n'] and all(saved[k] == checked[k] for k in ('lower','sevens','pairs')),
              f'Incorrect per-work pair counts for {wid}')
        for m, metrics in checked['methods'].items():
            check(all(same(value, saved['methods'][m][k]) for k,value in metrics.items()),
                  f'Incorrect per-work results for {wid}/{m}')
    results = {}
    for m in METHODS:
        values = {k:sum(w['methods'][m][k] for w in valid) for k in ('wins','ties','losses')}
        values['pair_pooled_concordance'] = (values['wins']+.5*values['ties'])/pairs if pairs else None
        values['work_equal_concordance'] = mean([w['methods'][m]['concordance'] for w in valid])
        for k,v in values.items():
            check(same(v,official['methods'][m][k]), f'Incorrect aggregate {m}/{k}')
        results[m] = values
    for m in ('current','always_6'):
        differences = [w['methods']['pairwise']['concordance'] - w['methods'][m]['concordance'] for w in valid]
        ci = official['paired'][m]
        check(same(mean(differences), ci['difference']), f'Incorrect paired difference for {m}')
        if valid:
            lo, hi = ci['paired_95']
            check(min(differences)-1e-10 <= lo <= hi+1e-10 and hi <= max(differences)+1e-10
                  and ci['valid_draws'] > 0, f'Invalid resampling interval for {m}')
        else:
            check(ci['valid_draws'] == 0 and ci['paired_95'] is None, 'Undefined interval reported')
    counts.update(eligible_comparators=sum(w['lower'] for w in valid), methods=results,
                  paired=official['paired'], shuffle=official['shuffle'])
    return counts, works, examples


def percentile(values, frac):
    x = frac * (len(values)-1)
    lo = int(x)
    return values[lo]+(x-lo)*(values[min(lo+1,len(values)-1)]-values[lo])


def period_bootstrap(pairs, works, draws=10000, seed=19027):
    """Resample matched pairs before excluding works without a grade contrast."""
    blocks = []
    for _, members in sorted(pairs.items()):
        contrasts = [w['methods'] for w in (works[i] for i in members) if w['pairs']]
        n = len(contrasts)
        deltas = [sum(v['pairwise']['concordance']-v[m]['concordance'] for v in contrasts)
                  for m in ('current','always_6')]
        blocks.append((n,*deltas))
    rng = Random(seed)
    samples = [[], []]
    for _ in range(draws):
        n, d_current, d_six = map(sum, zip(*rng.choices(blocks, k=len(blocks))))
        if n:
            samples[0].append(d_current/n)
            samples[1].append(d_six/n)
    n, *totals = map(sum, zip(*blocks))
    summary = {}
    for m, total, sample in zip(('current','always_6'), totals, samples):
        sample.sort()
        summary[m] = {'difference': total/n if n else None,
                      'paired_95': [percentile(sample,q) for q in (.025,.975)] if sample else None}
    return {'unit':'intact period pair', 'seed':seed, 'draws':draws, 'valid_draws':len(samples[0]), **summary}


def summarize(root, run):
    results, inputs = run/'results', run/'inputs'
    forecasts_path = results/'forecasts.json'
    f = read(forecasts_path)
    forecasts, blocks, pairs, packet, key, source = source_packet(run, f)
    agreement = read(results/'reading-agreement.json')
    check(agreement['forecasts_sha256'] == digest(forecasts_path) and
          agreement['packet_sha256'] == digest(inputs/'reading.json'), 'Reader input hashes differ')
    training_dir = root/'results/grammatical-training-expansion-20261122/results'
    training_path = training_dir/'enriched-reference.json'
    check(digest(training_path) == f['hashes']['training'], 'Changed training grades')
    model_path = training_dir/'fresh-expanded-results.json'
    check(digest(model_path) == f['hashes']['fit'] and
          f['models']['current'] == read(model_path)['models']['context_grammar'], 'Changed baseline model')
    training_counts = defaultdict(Counter)
    for r in read(training_path):
        training_counts[r['work_id']][r['score']] += 1
    training_pairs = {wid:c[7]*(c[5]+c[6]) for wid,c in training_counts.items()}
    check(training_pairs == {wid:v['pairs'] for wid,v in f['training']['by_work'].items()}
          and sum(training_pairs.values()) == f['training']['pairs'], 'Incorrect training-pair counts')
    summary = {'source':source, 'forecast_sha256':digest(forecasts_path), 'training':f['training'],
               'training_pairs_recounted':training_pairs}
    readers = []
    for label, role, suffix in [('primary','primary',''),('secondary','second','-second')]:
        grades = checked_grades(run, packet, key, role, suffix, agreement)
        readers.append(grades)
        analysis = read(results/f'evaluation{suffix}.json')
        check(analysis['hashes']['forecast'] == digest(forecasts_path) and
              analysis['hashes']['ratings'] == digest(inputs/f'ratings{suffix}.json'),
              f'Changed {role} evaluation inputs')
        joined = index(analysis['joined'])
        check(joined.keys() == forecasts.keys() and all(joined[i]['score'] == grades[i] and
              all(joined[i][k] == forecasts[i][k] for k in ('predictions','work_id','genre'))
              for i in forecasts), f'{role} evaluation used a different grade, score or work')
        one = {'groups':{}, 'decision':analysis.get('decision')}
        for genre in ('all','fu','prose'):
            grouped = {w:rows for w,rows in blocks.items() if genre == 'all' or rows[0]['genre'] == genre}
            out = {}
            for name, lower in ENDPOINTS.items():
                values, works, examples = endpoint(grouped,grades,lower,analysis['groups'][genre][name])
                out[name] = values
                if genre == 'all' and name == 'seven_vs_five_six':
                    one.update(examples=examples, per_work=works, period_sensitivity=period_bootstrap(pairs,works))
            one['groups'][genre] = out
        summary[label] = one
    a, b = readers
    summary['agreement'] = {}
    for genre in ('all','fu','prose'):
        ids = [i for i,r in forecasts.items() if genre == 'all' or r['genre'] == genre]
        ref = agreement['agreement'][genre]
        exact = sum(a[i] == b[i] for i in ids)
        one = sum(abs(a[i]-b[i])<=1 for i in ids)
        check((len(ids),exact,one) == (ref['n'],ref['exact'],ref['within_one']), 'Reader agreement mismatch')
        summary['agreement'][genre] = {'n':len(ids), 'exact':exact, 'within_one':one,
                                       'both_seven':sum(a[i] == b[i] == 7 for i in ids),
                                       'primary_seven':sum(a[i] == 7 for i in ids),
                                       'secondary_seven':sum(b[i] == 7 for i in ids)}
    return summary


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.root, args.run), ensure_ascii=False, allow_nan=False))
