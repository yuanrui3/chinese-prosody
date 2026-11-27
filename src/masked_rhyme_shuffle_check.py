"""Descriptive whole-work shuffle after the sealed within-section rhyme experiment."""

import argparse
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
from statistics import fmean

from src import masked_rhyme_recovery as study


def permute_work(work, draw):
    """Place each intact row at one new work position, preserving destination section boundaries."""
    rows = work.rows.copy()
    study.seeded('diagnostic-whole-work-shuffle', draw, work.id).shuffle(rows)
    return replace(work, rows=[replace(row, section=slot.section) for row, slot in zip(rows, work.rows)])


def short_sections(work, trials):
    result = {key: {'sections': 0, 'rows': 0, 'trials': 0} for key in ('1', '2', '3', '4+')}
    for _, values in groupby(work.rows, key=lambda row: row.section):
        segment = list(values)
        bucket = str(len(segment)) if len(segment) < 4 else '4+'
        result[bucket]['sections'] += 1
        result[bucket]['rows'] += len(segment)
        result[bucket]['trials'] += sum(row.id in trials for row in segment)
    return result


def summarize(overview, results):
    aggregate = {group: Counter() for group in ('1', '2', '3', '4+')}
    for result in results:
        for group, counts in result['section_sizes'].items():
            aggregate[group].update(counts)
    eligible = [r for r in results if r['eligible']]
    out = {'eligible_works': len(eligible), 'section_sizes': {k: dict(v) for k, v in aggregate.items()}}
    if not eligible:
        return out
    out['comparisons'] = {}
    for method in study.METHODS:
        means = {metric: fmean(fmean(r['whole_work'][method][metric]) for r in eligible)
                 for metric in ('accuracy', 'coverage')}
        out['comparisons'][method] = {
            'intact': {k: overview['intact'][method][k] for k in means},
            'within_section': {k: overview['shuffled'][method][k] for k in means}, 'whole_work': means,
        }
    return out


def run(root, input_file, output):
    raw = input_file.read_bytes()
    seal_path = output / 'seal.json'
    sealed = json.loads(seal_path.read_bytes())
    lex, hashes = study.lexicon_data(root)
    if (sha256(raw).hexdigest() != sealed['input_sha256'] or hashes != sealed['lexicon_sha256'] or
            sha256(Path(study.__file__).read_bytes()).hexdigest() != sealed['analysis_sha256'] or
            sealed['protocol'] != study.PROTOCOL):
        raise ValueError('The input, lexicons or primary analysis differ from the sealed experiment.')
    works = study.load_works(json.loads(raw), lex)
    primary = json.loads((output / 'summary.json').read_bytes())
    records = []
    for work in works.values():
        trials = sealed['trials'][work.id]
        results = {m: {k: [] for k in ('accuracy', 'coverage')} for m in study.METHODS}
        if trials:
            for draw in range(study.SHUFFLES):
                simulation = permute_work(work, draw)
                counts, _, _ = study.evaluate_work(simulation, trials)
                for method in study.METHODS:
                    metrics = study.rates(counts[method])
                    for key in results[method]:
                        results[method][key].append(metrics[key])
        records.append({'work_id': work.id, 'split': work.split, 'genre': work.genre,
                        'eligible': len(trials), 'section_sizes': short_sections(work, trials), 'whole_work': results})
    summary = {split: {genre: summarize(primary[split][genre], [r for r in records if r['split'] == split and r['genre'] == genre])
                       for genre in ('fu', 'prose')} for split in ('development', 'test')}
    result = {'primary_seal_sha256': sha256(seal_path.read_bytes()).hexdigest(),
              'diagnostic_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
              'definition': 'Permute intact ending rows and attached trials throughout each work; preserve positions, '
                            'section lengths and order, original foil, and work group frequencies. Shuffle labels '
                            'descriptively after the primary experiment using a separate deterministic seed namespace.',
              'short_section_limit': 'Within one row no neighbor exists. With two rows, the sole neighbor is '
                                     'unchanged by permutation and the run rule cannot fire. With three rows both '
                                     'neighbors always lie within radius two and form one possible consecutive '
                                     'support pair, independent of order. Both local and run predictions are therefore '
                                     'exactly invariant to within-section shuffles for every challenge in sections of '
                                     'one, two, or three rows. Longer homogeneous sections can also be invariant.',
              'shuffle_count': study.SHUFFLES, 'summary': summary, 'works': records}
    study.save_sealed(output / 'whole_work_shuffle.json', result)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('rows', type=Path)
    parser.add_argument('primary_output_dir', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.rows, args.primary_output_dir)['test'], ensure_ascii=False))
