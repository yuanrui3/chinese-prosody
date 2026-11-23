"""Compare feature coverage and held-out boundary scores on shared and rescued sites."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from src.quantitative_preboundary_duration import compare


def read(path, stem):
    return json.loads((path / f'{stem}.json').read_text(encoding='utf-8'))


def eligible(row):
    return all(row[key] is not None for key in ('pause_ms', 'pre_duration_s', 'context_duration_s'))


def summarize(rows):
    return {'sites': len(rows), 'positive_sites': sum(row['label'] for row in rows),
            'pause_available': sum(row['pause_ms'] is not None for row in rows),
            'both_available': sum(map(eligible, rows)),
            'eligible_positives': sum(row['label'] for row in rows if eligible(row)),
            'exclusions': dict(Counter(row['exclusion'] for row in rows if not eligible(row)))}


def coverage(rows):
    output = {'all': summarize(rows)}
    for key in ('genre', 'speaker', 'work'):
        groups = defaultdict(list)
        for row in rows:
            groups[row[key]].append(row)
        output[key] = {name: summarize(group) for name, group in sorted(groups.items())}
    return output


def predictions(result):
    return {row['row']: row for row in result['primary_joint']['predictions']}


def at_half(indices, scores, reference):
    selected = [scores[index] for index in indices if index in scores]
    positives = sum(reference[index - 1]['label'] for index in indices)
    predicted = [row for row in selected if row['pause_and_duration'] >= 0.5]
    true_positive = sum(row['label'] for row in predicted)
    return {'sites': len(indices), 'eligible_sites': len(selected), 'positive_sites': positives,
            'true_positives': true_positive, 'predicted_positives': len(predicted),
            'precision': true_positive / len(predicted) if predicted else None,
            'recall_including_abstentions': true_positive / positives if positives else None}


def evaluate(base_path, variants):
    base = read(base_path, 'candidates')
    base_scores = predictions(read(base_path, 'evaluation'))
    rows = base['rows']
    fields = ('recording_id', 'ordinal', 'label', 'genre', 'work', 'speaker', 'left_char', 'right_char')
    reference = [tuple(row[field] for field in fields) for row in rows]
    output = {'baseline': {'coverage': coverage(rows),
                           'threshold_0_5': at_half(range(1, len(rows) + 1), base_scores, rows)}}
    for name, path in variants.items():
        other = read(path, 'candidates')
        other_rows = other['rows']
        if (base['manifest_sha256'] != other['manifest_sha256']
                or reference != [tuple(row[field] for field in fields) for row in other_rows]):
            raise ValueError(f'Manifest or candidate sites changed in {name}')
        other_scores = predictions(read(path, 'evaluation'))
        shared = sorted(base_scores.keys() & other_scores.keys())
        new = sorted(other_scores.keys() - base_scores.keys())
        lost = sorted(base_scores.keys() - other_scores.keys())
        output[name] = {'coverage': coverage(other_rows),
                        'shared_baseline': compare([base_scores[index] for index in shared]),
                        'shared_rescue': compare([other_scores[index] for index in shared]),
                        'new_only': compare([other_scores[index] for index in new]),
                        'new_junctions_using_qwen_character_identity':
                            sum(other_rows[index - 1]['qwen_identity_at_junction'] for index in new),
                        'baseline_only': compare([base_scores[index] for index in lost]),
                        'threshold_0_5': at_half(range(1, len(rows) + 1), other_scores, rows),
                        'new_threshold_0_5': at_half(new, other_scores, rows)}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--variant', action='append', nargs=2, metavar=('NAME', 'DIR'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    variants = {name: Path(path) for name, path in args.variant}
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(evaluate(args.baseline, variants), handle, allow_nan=False, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    main()
