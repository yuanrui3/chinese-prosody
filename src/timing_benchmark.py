"""Test a fixed synthetic timing baseline on works outside its calibration set."""

import argparse
from collections import defaultdict
import hashlib
import json
from math import isclose
import os
from pathlib import Path
from statistics import mean

from src.expansion_design import authors
from src.pilot_validation import read_jsonl
from src.stage6_listening import digest, read_clip, write_json
from src.text_metrics import clauses


ANNOTATIONS = Path('data/pilot/annotated.jsonl')
MANIFEST = Path('audio/manifests/synthetic.jsonl')
VOICE = 'zm_010'
SPEED = 0.9


def recordings(root, *, expansion):
    passages = {row['passage_id']: row for row in read_jsonl(root / ANNOTATIONS)}
    selected = {}
    for take in read_jsonl(root / MANIFEST):
        if (take['speaker'], take['speed']) != (VOICE, SPEED):
            continue
        passage_id = take['passage_id']
        passage = passages[passage_id]
        if passage['subset'] != 'matched' or (expansion and passage['task'] != 'listening'):
            continue
        text_sha = hashlib.sha256(passage['text'].encode('utf-8')).hexdigest()
        if (passage_id in selected or not text_sha == passage['text_sha256'] == take['text_sha256']
                or passage['revision_id'] != take['text_revision'] or take['kind'] != 'synthetic'
                or take['variety'] != 'cmn' or take['style'] != 'controlled_read_speech'):
            raise ValueError(f'Incompatible or duplicated timing input for {passage_id}')
        sample_rate, samples = read_clip(root, take, take['sample_rate'])
        seconds = len(samples) / sample_rate
        slots = len(passage['slots'])
        if not samples or not slots or not isclose(seconds, take['duration_s'], abs_tol=1e-6):
            raise ValueError(f'Invalid duration or text slot count for {passage_id}')
        selected[passage_id] = {
            'passage_id': passage_id, 'work_id': passage['work_id'], 'authors': sorted(authors(passage)),
            'text_sha256': text_sha, 'audio_sha256': take['audio_sha256'],
            'condition': (take['model_revision'], take['speaker'], take['speed'], take['sample_rate']),
            'slots': slots, 'clause_breaks': len(clauses(passage)) - 1, 'duration_ms': seconds * 1000,
        }
    if expansion and set(selected) != {
        row['passage_id'] for row in passages.values() if row['task'] == 'listening'
    }:
        raise ValueError('The holdout must include all of the expansion listening excerpts')
    if not selected:
        raise ValueError('No matched recordings at the requested voice and speed')
    return list(selected.values())


def by_work(rows):
    works = defaultdict(list)
    for row in rows:
        works[row['work_id']].append(row)
    return works


def check_split(calibration, holdout):
    for key in ('work_id', 'passage_id', 'text_sha256', 'audio_sha256'):
        if {row[key] for row in calibration} & {row[key] for row in holdout}:
            raise ValueError(f'Calibration and holdout share {key}')
    if ({author for row in calibration for author in row['authors']} &
            {author for row in holdout for author in row['authors']}):
        raise ValueError('Calibration and holdout share an author')
    if len({row['condition'] for row in calibration + holdout}) != 1:
        raise ValueError('Expected one common synthesis condition')


def fit(calibration):
    # Average within each work before averaging across works.
    grouped = by_work(calibration)

    def average(fn):
        return mean(mean(fn(row) for row in group) for group in grouped.values())

    def density(row):
        return row['clause_breaks'] / row['slots']

    def rate(row):
        return row['duration_ms'] / row['slots']

    center_x, center_y = average(density), average(rate)
    variance = average(lambda row: (density(row) - center_x) ** 2)
    if variance == 0:
        raise ValueError('Calibration requires at least two clause-break densities')
    slope = average(lambda row: (density(row) - center_x) * (rate(row) - center_y)) / variance
    return {
        'slot_count': {'ms_per_slot': center_y, 'ms_per_clause_break': 0.0},
        'slot_count_and_clause_breaks': {'ms_per_slot': center_y - slope * center_x,
                                        'ms_per_clause_break': slope},
    }


def evaluate(holdout, fitted):
    results = {}
    for name, coefficients in fitted.items():
        rows = []
        for row in holdout:
            prediction = (row['slots'] * coefficients['ms_per_slot'] +
                          row['clause_breaks'] * coefficients['ms_per_clause_break'])
            if prediction <= 0:
                raise ValueError('Fitted synthetic duration outside its physical range')
            rows.append({**row, 'predicted_ms': prediction, 'absolute_error_ms': abs(prediction - row['duration_ms'])})
        errors = {work: mean(row['absolute_error_ms'] for row in group)
                  for work, group in by_work(rows).items()}
        results[name] = {'work_mean_absolute_error_ms': mean(errors.values()),
                         'absolute_error_ms_by_work': errors, 'predictions': rows}
    baseline, candidate = results['slot_count'], results['slot_count_and_clause_breaks']
    changes = {work: candidate['absolute_error_ms_by_work'][work] - error
               for work, error in baseline['absolute_error_ms_by_work'].items()}
    summary = {
        'work_mean_absolute_error_ms': {name: row['work_mean_absolute_error_ms'] for name, row in results.items()},
        'works_with_lower_error_from_clause_breaks': sum(delta < 0 for delta in changes.values()),
    }
    return results, changes, summary


def benchmark(base):
    original = base / 'listening-rounds/mandarin-male'
    expansion = base / 'pilot-expansions/independent-works'
    calibration = recordings(original, expansion=False)
    holdout = recordings(expansion, expansion=True)
    check_split(calibration, holdout)
    fitted = fit(calibration)
    results, changes, summary = evaluate(holdout, fitted)
    summary.update(calibration_passages=len(calibration), calibration_works=len(by_work(calibration)),
                   holdout_passages=len(holdout), holdout_works=len(by_work(holdout)))
    output = base / 'results/model-development/synthetic-timing.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, {
        'endpoint': 'complete synthetic waveform duration, in milliseconds',
        'input_sha256': {label: {str(file): digest(root / file) for file in (ANNOTATIONS, MANIFEST)}
                         for label, root in (('calibration', original), ('holdout', expansion))},
        'fit': fitted, 'calibration': calibration, 'holdout_results': results,
        'change_in_absolute_error_ms_by_work': changes, 'summary': summary,
    })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(benchmark(args.root.resolve(strict=True)), allow_nan=False))


if __name__ == '__main__':
    main()
