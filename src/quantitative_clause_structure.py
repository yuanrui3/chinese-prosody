"""Test the directional 四六 clause-share contrast on two matched prose cohorts."""

import argparse
from collections import Counter
from hashlib import sha256
from itertools import product
import json
from math import comb
import os
from pathlib import Path
from random import Random
from statistics import mean

from data.phonology.annotate import syllable_slots
from data.pilot.build import apply_edit, matches_witness
from src.expansion_design import authors
from src.pilot_validation import matched_pairs, write_json
from src.quantitative_report import DRAW_COUNT, FILES, PERIODS, SEED, check_inventory, index
from src.stage6_listening import digest, read_json, read_rows
from src.text_metrics import clauses, metric_results


CODE = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path('model-development/quantitative-onset-transfer/results/onset-transfer')
COHORTS = {
    'historical_increment': ('historical-increment', 'historical-increment.json', 4),
    'v4': ('quantitative-report', 'voice-report.json', 2),
}
TARGET_LENGTHS = (4, 6)
EPSILON = 1e-12


def text_digest(text):
    return sha256(text.encode('utf-8')).hexdigest()


def recover_witness(passage):
    text = passage['text']
    inserted = passage.get('insert_punctuation_after', {})
    if passage.get('edit'):
        raise ValueError('This comparison expects the source wording preserved')
    removed = set()
    for before, (position, mark) in enumerate(sorted(inserted.items(), key=lambda pair: int(pair[0]))):
        offset = int(position) + before
        if not 0 < offset < len(text) or text[offset] != mark:
            raise ValueError('Declared punctuation does not match the annotated excerpt')
        removed.add(offset)
    witness = ''.join(char for offset, char in enumerate(text) if offset not in removed)
    if not matches_witness(witness, passage) or apply_edit(witness, passage) != text:
        raise ValueError('Restored witness differs from the pinned edition anchors')
    return witness


def expected_share(han_count, clause_count):
    """Expected 四六 share among uniform positive ordered compositions."""
    if not 1 <= clause_count <= han_count:
        raise ValueError('A clause composition needs positive lengths')
    if clause_count == 1:
        return float(han_count in TARGET_LENGTHS)
    eligible = comb(han_count - 1, clause_count - 1)
    hits = sum(comb(han_count - length - 1, clause_count - 2) for length in TARGET_LENGTHS
               if han_count - length >= clause_count - 1)
    return hits / eligible


def randomized_share(han_count, clause_count, rng):
    # The cut-location bijection makes each positive composition equally likely.
    cuts = [0, *sorted(rng.sample(range(1, han_count), clause_count - 1)), han_count]
    return sum(right - left in TARGET_LENGTHS for left, right in zip(cuts, cuts[1:])) / clause_count


def structure(passage):
    lengths = [len(line) for line in clauses(passage)]
    estimate = metric_results(passage)['clause_46_share']
    return {'han_count': sum(lengths), 'clause_count': estimate.eligible, 'lengths_han': lengths,
            'four_or_six_clauses': sum(length in TARGET_LENGTHS for length in lengths),
            'share': estimate.value, 'uniform_cut_expected_share': expected_share(sum(lengths), estimate.eligible)}


def label_swap(differences):
    observed = mean(differences)
    permuted = [mean(sign * delta for sign, delta in zip(signs, differences))
                for signs in product((-1, 1), repeat=len(differences))]
    peak = max(permuted)
    return {'assignments': len(permuted), 'one_sided_p': sum(value >= observed - EPSILON for value in permuted)
            / len(permuted), 'smallest_attainable_p': sum(value >= peak - EPSILON for value in permuted)
            / len(permuted)}


def evaluate(rows, pairs, *, draws, seed, variant='annotated'):
    members = [(rows[left][variant], rows[right][variant]) for _, left, right in pairs]
    contrasts = [a['share'] - b['share'] for a, b in members]
    expected = mean(a['uniform_cut_expected_share'] - b['uniform_cut_expected_share'] for a, b in members)
    observed = mean(contrasts)
    rng = Random(seed)
    simulated = sorted(mean(randomized_share(a['han_count'], a['clause_count'], rng)
                            - randomized_share(b['han_count'], b['clause_count'], rng) for a, b in members)
                       for _ in range(draws))
    return {
        'pairs': [{'pair_id': pair_id, 'period': rows[left]['period'], 'topic': rows[left]['match_topic'],
                   'parallel_passage_id': rows[left]['passage_id'], 'comparison_passage_id': rows[right]['passage_id'],
                   'parallel_numerator_denominator': [a['four_or_six_clauses'], a['clause_count']],
                   'comparison_numerator_denominator': [b['four_or_six_clauses'], b['clause_count']],
                   'parallel_minus_comparison': delta}
                  for (pair_id, left, right), (a, b), delta in zip(pairs, members, contrasts)],
        'mean_share_parallel': mean(a['share'] for a, _ in members),
        'mean_share_comparison': mean(b['share'] for _, b in members),
        'mean_parallel_minus_comparison': observed,
        'parallel_higher': sum(delta > EPSILON for delta in contrasts),
        'ties': sum(abs(delta) <= EPSILON for delta in contrasts),
        'comparison_higher': sum(delta < -EPSILON for delta in contrasts),
        'uniform_cuts': {'draws': draws, 'seed': seed, 'analytic_mean_contrast': expected,
                         'observed_minus_analytic_mean': observed - expected,
                         'simulated_mean_contrast': mean(simulated),
                         'null_contrast_025_975': [simulated[int(q * (draws - 1))] for q in (0.025, 0.975)],
                         'one_sided_p': (1 + sum(value >= observed - EPSILON for value in simulated)) / (1 + draws)},
        'within_pair_label_swaps': label_swap(contrasts),
    }


def pinned_rows(annotation, manifest):
    pins = read_json(manifest)
    sources = index(pins['sources'], lambda row: row['source_id'])
    specifications = index(pins['passages'], lambda row: row['passage_id'])
    annotated = index(read_rows(annotation), lambda row: row['passage_id'])
    if annotated.keys() != specifications.keys():
        raise ValueError('The annotated works differ from the pinned passage inventory')
    check_inventory(annotated)
    analyzed = []
    for pid, passage in sorted(annotated.items()):
        spec = specifications[pid]
        pinned = {**sources[spec['source_id']], **spec}
        if any(passage[key] != value for key, value in pinned.items()):
            raise ValueError(f'{pid}: the edition, excerpt, or pair differs from its source manifest')
        witness = recover_witness(passage)
        annotated_structure = structure(passage)
        edition_structure = (structure({**passage, 'slots': syllable_slots(witness), 'parallel_clause_groups': []})
                             if witness != passage['text'] else annotated_structure)
        analyzed.append({
            **{key: passage[key] for key in ('passage_id', 'work_id', 'pair_id', 'period', 'genre', 'match_topic',
                                            'source_id', 'source_url', 'revision_id', 'text_sha256', 'author',
                                            'selection_note')},
            'witness_sha256': text_digest(witness), 'added_marks': passage.get('insert_punctuation_after', {}),
            'annotated': annotated_structure, 'edition': edition_structure,
        })
    return analyzed


def verify_disjoint(first, second):
    for key in ('work_id', 'passage_id', 'source_id', 'revision_id', 'text_sha256', 'witness_sha256'):
        if {row[key] for row in first} & {row[key] for row in second}:
            raise ValueError(f'The two prose cohorts share {key}')
    if set().union(*(authors(row) for row in first)) & set().union(*(authors(row) for row in second)):
        raise ValueError('The two prose cohorts share a credited author')


def analyze(project):
    inputs = {label: (project / 'model-development' / folder / FILES['passages'],
                      CODE / 'data/pilot' / manifest) for label, (folder, manifest, _) in COHORTS.items()}
    hashes = {label: {'annotation': digest(annotation), 'manifest': digest(manifest)}
              for label, (annotation, manifest) in inputs.items()}
    cohorts = {label: pinned_rows(*paths) for label, paths in inputs.items()}
    verify_disjoint(*cohorts.values())
    results = {}
    for offset, (label, rows) in enumerate(cohorts.items()):
        pairs = matched_pairs(rows)
        periods = Counter(rows[left]['period'] for _, left, _ in pairs)
        if (dict(periods) != dict.fromkeys(PERIODS, COHORTS[label][2])
                or any((rows[left]['period'], rows[left]['match_topic'])
                       != (rows[right]['period'], rows[right]['match_topic']) for _, left, right in pairs)):
            raise ValueError('Expected the full period- and topic-matched comparison')
        result = evaluate(rows, pairs, draws=DRAW_COUNT, seed=SEED + offset)
        results[label] = {'works': len(rows), 'pairs_by_period': dict(periods), 'passages': rows, **result}
        if any(row['added_marks'] for row in rows):
            results[label]['edition_only_sensitivity'] = evaluate(rows, pairs, draws=DRAW_COUNT,
                                                                 seed=SEED + offset, variant='edition')
    if any(hashes[label] != {'annotation': digest(annotation), 'manifest': digest(manifest)}
           for label, (annotation, manifest) in inputs.items()):
        raise ValueError('An input annotation or manifest changed during the comparison')
    return {'schema_version': 1, 'source_sha256': hashes,
            'hypothesis': 'A higher share of four- or six-Han-character clauses in 骈文 than in matched prose.',
            'controls': {
                'uniform_cuts': 'Redraw each work’s internal cut positions with Han and clause counts fixed.',
                'label_swaps': 'Swap the genre labels independently within each observed period-topic pair.',
                'edition_sensitivity': 'Remove only documented project-added marks. Unpunctuated witnesses may contain one measured span.',
            },
            'scope': 'Independently sourced cohorts with selected excerpts and fixed genre labels. The v4 contrast was already described.',
            'cohorts': results,
            '音律美': {'evidence': 'written clause-length diagnostic'},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    output = args.output.resolve()
    if (output.parent != project / OUTPUT_DIR or output.suffix != '.json'
            or args.output.is_symlink() or output.exists()):
        parser.error('Choose a new JSON output in the onset-transfer results directory')
    os.umask(0o077)
    report = analyze(project)
    write_json(output, report)
    summary = {label: {key: result[key] for key in ('works', 'mean_parallel_minus_comparison', 'parallel_higher',
                                                     'ties', 'comparison_higher', 'uniform_cuts',
                                                     'within_pair_label_swaps')}
               for label, result in report['cohorts'].items()}
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
