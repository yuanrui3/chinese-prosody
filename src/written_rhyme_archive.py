"""Bridge the earlier eight-work editorial reading to the written-rhyme comparison."""

import argparse
from collections import Counter, defaultdict
from math import isclose
from pathlib import Path
from statistics import fmean

from .quantitative_ending_functions import digest, read
from .yu_review_baseline import save_sealed

ARCHIVE = 'yu-review-transfer-20261124-HK72rUtZ'
CORPUS_SHA = '16ebc4a558f17304537f98e357e5593bfb38abce24e319acfb553ab397ccfc23'
GRADE_PREFIX = 'ebe678f99c0a'
FORECAST_PREFIX = 'b226fc273d5f'


def checked_inputs(root):
    old = root / 'results' / ARCHIVE
    seal = read(old / 'inputs/source-seal.json')
    for name in ('corpus.json', 'sources.json', 'reading.json'):
        if digest(old / 'inputs' / name) != seal[name]:
            raise ValueError(f'Invalid original source seal for {name}')
    if seal['corpus.json'] != CORPUS_SHA:
        raise ValueError('Unexpected historical corpus')
    report = read(old / 'results/comparison.json')
    for filename, stem, prefix in [('private/editorial.json', 'editorial', GRADE_PREFIX),
                                   ('results/baseline.json', 'baseline', FORECAST_PREFIX)]:
        checksum = digest(old / filename)
        old_seal = (old / 'seals' / f'{stem}.sha256').read_text().split()[0]
        if not checksum.startswith(prefix) or old_seal != checksum or report['hashes'][filename] != checksum:
            raise ValueError(f'Original comparison and source disagree about {filename}')
    return old, seal, report


def prepare(root, run):
    old, original_seal, _ = checked_inputs(root)
    sources = read(old / 'inputs/sources.json')['works']
    cards = {c['work_id']: c for c in sources}
    corpus = read(old / 'inputs/corpus.json')
    reading = read(old / 'inputs/reading.json')
    grades = read(old / 'private/editorial.json')
    if len(corpus) != 208 or len(cards) != 8 or len({c['author'] for c in sources}) != 8:
        raise ValueError('Unexpected earlier work or row roster')
    for c in sources:
        if digest(old / 'inputs/editions' / f"{c['revision']}.wiki") != c['wiki_sha256']:
            raise ValueError(f"Changed earlier witness: {c['title']}")
    original_ids = [(r['id'], r['work_id'], r['paragraph'], r['text'], r['target']) for r in corpus]
    read_ids = [(r['id'], p['work_id'], p['paragraph'], r['text'], r['target'])
                for p in reading for r in p['sentences']]
    if len({r['id'] for r in corpus}) != len(corpus) or original_ids != read_ids:
        raise ValueError('Old reading and scored context differ')
    targets = {r['id'] for r in corpus if r['target']}
    if set(grades) != targets or Counter(r['work_id'] for r in corpus if r['target']) != dict.fromkeys(cards, 8):
        raise ValueError('Old targets differ from the sealed judgments')
    rows = [{**r, 'genre': 'prose', 'author': cards[r['work_id']]['author']} for r in corpus]
    # Preserve the original section + paragraph identity as two fields. The
    # original predictor combined them; the partitions and ordering are identical.
    if any(r['paragraph'] != r['section'] for r in rows):
        raise ValueError('Cannot reproduce the original editorial sections')
    inputs = run / 'inputs'
    inputs.mkdir(parents=True, exist_ok=True)
    source_info = {'study': 'retrospective-secondary', 'archive': ARCHIVE, 'original_seal': original_seal,
                   'original_editorial_sha256': digest(old / 'private/editorial.json'),
                   'original_baseline_sha256': digest(old / 'results/baseline.json'),
                   'works': [{**c, 'form': c['genre'], 'genre': 'prose'} for c in sources]}
    save_sealed(inputs / 'corpus.json', rows)
    save_sealed(inputs / 'sources.json', source_info)
    save_sealed(inputs / 'source-seal.json', {n: digest(inputs / n) for n in ('corpus.json', 'sources.json')})
    save_sealed(inputs / 'ratings.json', [{'id': ident, 'score': grades[ident]['score']} for ident in sorted(targets)])
    return source_info


def original_maes(old, rows, full, scores):
    errors = defaultdict(list)
    for r in rows:
        if r['target']:
            i = r['id']
            errors[r['work_id']].append((abs(scores[i] - full[i]), abs(scores[i] - 6.0)))
    computed = {name: fmean(fmean(e[col] for e in block) for block in errors.values())
                for col, name in enumerate(('current', 'always_six'))}
    for name, measured in computed.items():
        if not isclose(measured, old['models'][name]['mae'], abs_tol=1e-12, rel_tol=0):
            raise ValueError(f'Failed to replay the earlier {name} absolute error.')
    return computed


def verify(root, run):
    old, _, comparison = checked_inputs(root)
    rows = read(run / 'inputs/corpus.json')
    target_ids = {r['id'] for r in rows if r['target']}
    full = read(old / 'results/baseline.json')
    if set(full) != {r['id'] for r in rows}:
        raise ValueError('Original predictions must include the complete work contexts')
    original_grades = read(old / 'private/editorial.json')
    grades = {r['id']: r['score'] for r in read(run / 'inputs/ratings.json')}
    if grades != {i:g['score'] for i, g in original_grades.items()}:
        raise ValueError('Archived grade join differs')
    predictions = read(run / 'results/forecasts.json')['predictions']
    if {r['id'] for r in predictions} != target_ids or len(predictions) != len(target_ids):
        raise ValueError('Retrospective forecast target roster differs')
    for r in predictions:
        if r['predictions']['with_rhyme'] != full[r['id']]:
            raise ValueError(f"Earlier forecast not reproduced exactly at {r['id']}")
    old_errors = original_maes(comparison, rows, full, grades)
    analysis = read(run / 'results/evaluation.json')['groups']['all']['work_equal_mae']
    for name, method in [('current', 'with_rhyme'), ('always_six', 'always_6')]:
        if not isclose(analysis[method], old_errors[name], abs_tol=1e-12, rel_tol=0):
            raise ValueError(f'New {method} has inconsistent MAE.')
    result = {'study': 'retrospective-secondary', 'archive': ARCHIVE, 'replayed_targets': len(target_ids),
              'earlier_work_equal_mae': old_errors, 'new_work_equal_mae': analysis,
              'original_comparison_sha256': digest(old / 'results/comparison.json'),
              'new_evaluation_sha256': digest(run / 'results/evaluation.json')}
    save_sealed(run / 'results/archive-replay.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'verify'))
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path, help='Dedicated retrospective subdirectory')
    args = parser.parse_args()
    if args.phase == 'prepare':
        prepare(args.root, args.run)
        print('Prepared the earlier eight-work, 64-target written comparison.')
    else:
        print(verify(args.root, args.run))
