"""Validate pause measurements made from one WAV at a time on the phrasing controls."""

import argparse
from collections import Counter, defaultdict
import json
from math import isfinite
import os
from pathlib import Path
from statistics import mean, median

from src.pilot_validation import write_json
from src.recitation_pcm_alignment import OUTPUT as PCM_ALIGNMENT
from src.recitation_phrasing_analysis import (DBFS_THRESHOLDS, MANIFEST, PRIMARY_DBFS, QUIET_FRAME_S,
                                              ROLES, quiet_runs, shuffle_summary)
from src.recitation_second_aligner_analysis import (FORCED_ALIGNMENT, OUTPUT as ALIGNER_COMPARISON,
                                                   index_rows, midpoint, usable_spans)
from src.stage6_listening import digest, read_clip, read_json


OUTPUT = MANIFEST.with_name('single-take-pauses.json')
THRESHOLD_ORDER = (PRIMARY_DBFS, *[level for level in DBFS_THRESHOLDS if level != PRIMARY_DBFS])


def gap_features(samples, rate, spans):
    if len(spans) != 4 or any(span is None for span in spans):
        return None
    duration = len(samples) / rate
    if any(not (isfinite(span['start_s']) and isfinite(span['end_s'])
                and 0 <= span['start_s'] < span['end_s'] <= duration) for span in spans):
        return None
    if any(left['end_s'] > right['start_s'] for left, right in zip(spans, spans[1:])):
        return None
    centers = [round(midpoint(span) * rate) for span in spans]
    windows = list(zip(centers, centers[1:]))
    if any(right - left < max(1, round(QUIET_FRAME_S * rate)) for left, right in windows):
        return None
    observations = [quiet_runs(samples, left, right, rate) for left, right in windows]
    return {str(level): [window[level] for window in observations] for level in DBFS_THRESHOLDS}


def absolute_errors(predicted, expected):
    if len(predicted) != 3 or len(expected) != 3:
        raise ValueError('Expected three internal boundary measurements')
    return [abs(value - target) for value, target in zip(predicted, expected)]


def choose_threshold(rows):
    if not rows:
        raise ValueError('Threshold selection requires at least one training work')
    errors = {level: defaultdict(list) for level in DBFS_THRESHOLDS}
    for row in rows:
        for level, work_errors in errors.items():
            work_errors[row['work_id']].append(mean(absolute_errors(row['quiet_ms_by_dbfs'][str(level)],
                                                                   row['reference_ms'])))
    return min(THRESHOLD_ORDER, key=lambda level: mean(map(mean, errors[level].values())))


def agreement(rows, field):
    attempts = [(row, row[field]) for row in rows]
    measured = [(row, values) for row, values in attempts if values is not None and None not in values]
    differences = [absolute_errors(values, row['reference_ms']) for row, values in measured]
    by_work = defaultdict(list)
    for (row, _), errors in zip(measured, differences):
        by_work[row['work_id']].append(mean(errors))
    return {'measured_pairs': len(measured), 'measured_works': len(by_work),
            'both_edited_directions': sum(values[0] > 0 > values[1] for _, values in measured),
            'median_change_ms': list(map(median, zip(*(values for _, values in measured)))) if measured else None,
            'median_absolute_error_ms': list(map(median, zip(*differences))) if differences else None,
            'work_mean_absolute_error_ms': mean(map(mean, by_work.values())) if by_work else None,
            'unedited_boundary_over_one_frame': sum(errors[2] > 20 for errors in differences)}


def measure(root, pair, forced):
    indices = pair['slot_indices']
    if len(indices) != 4 or indices != list(range(indices[0], indices[0] + 4)):
        raise ValueError('Expected one contiguous four-character phrase')
    rate = pair['source']['sample_rate']
    takes = pair['variants']
    if (len({takes[role]['sample_count'] for role in ROLES}) != 1
            or any(takes[role]['text_sha256'] != pair['source']['text_sha256'] for role in ROLES)):
        raise ValueError('Treatment text and duration must match')
    results = {}
    for role in ROLES:
        take = takes[role]
        _, pcm = read_clip(root, take, rate)
        if len(pcm) != take['sample_count']:
            raise ValueError('Treatment sample count differs from the manifest')
        spans = usable_spans(root, take, forced['takes'][role], indices, rate)
        results[role] = gap_features(pcm, rate, spans)
    a, b = (results[role] for role in ROLES)
    delta = ({level: [right - left for left, right in zip(a[level], b[level])] for level in a}
             if a is not None and b is not None else None)
    return {'pair_id': pair['pair_id'], 'work_id': pair['work_id'], 'quiet_ms_by_take': results,
            'quiet_ms_by_dbfs': delta, 'fixed_rms_ms': delta[str(PRIMARY_DBFS)] if delta else None}


def compare(root):
    paths = {name: root / path for name, path in {'manifest': MANIFEST, 'forced': FORCED_ALIGNMENT,
             'pcm': PCM_ALIGNMENT, 'comparison': ALIGNER_COMPARISON}.items()}
    hashes = {name: digest(path) for name, path in paths.items()}
    inputs = {name: read_json(path) for name, path in paths.items()}
    comparison = inputs['comparison']
    if (any(inputs[name]['stimuli_sha256'] != hashes['manifest'] for name in ('forced', 'pcm', 'comparison'))
            or comparison['pcm_alignment_sha256'] != hashes['pcm']
            or comparison['forced_alignment_sha256'] != hashes['forced']):
        raise ValueError('The benchmarks refer to different recordings')
    pairs, forced, pcm, prior = (index_rows(inputs[name]['pairs'], 'pair_id') for name in paths)
    if not pairs or not (pairs.keys() == forced.keys() == pcm.keys() == prior.keys()):
        raise ValueError('The benchmarks do not contain identical pairs')

    rows = [measure(root, pair, forced[key]) for key, pair in pairs.items()]
    by_work = defaultdict(list)
    for row in rows:
        key = row['pair_id']
        if (pcm[key]['status'] != 'aligned' or not pcm[key]['supports_pause_distribution']
                or pcm[key]['work_id'] != row['work_id']):
            raise ValueError('Missing exact PCM reference for the recorded work')
        baselines = prior[key].get('split_minus_concentrated', {})
        row.update(reference_ms=pcm[key]['split_minus_concentrated_ms'], no_change_ms=[0, 0, 0],
                   funasr_midpoint_ms=baselines.get('model_landmark_spacing_changes_ms'),
                   funasr_span_gap_ms=baselines.get('model_span_gap_changes_ms'))
        by_work[row['work_id']].append(row)

    folds = {}
    for work, held_out in by_work.items():
        training = [row for row in rows if row['work_id'] != work and row['fixed_rms_ms'] is not None]
        folds[work] = choose_threshold(training) if training else None
        for row in held_out:
            row['held_out_rms_ms'] = (row['quiet_ms_by_dbfs'][str(folds[work])]
                                     if folds[work] is not None and row['quiet_ms_by_dbfs'] is not None else None)

    fixed_swaps = {work: [row['fixed_rms_ms'][0] - row['fixed_rms_ms'][1] for row in group
                         if row['fixed_rms_ms'] is not None] for work, group in by_work.items()}
    fields = ('no_change_ms', 'funasr_midpoint_ms', 'funasr_span_gap_ms', 'fixed_rms_ms', 'held_out_rms_ms')
    summary = {'pairs': len(rows), 'works': len(by_work),
               'methods': {field: agreement(rows, field) for field in fields},
               'held_out_threshold_counts': dict(Counter(folds.values())),
               'fixed_threshold_label_swap': shuffle_summary({work: values for work, values in fixed_swaps.items()
                                                             if values})}
    write_json(root / OUTPUT, {'hashes': hashes, 'summary': summary, 'held_out_thresholds_dbfs': folds, 'pairs': rows})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(compare(args.root.resolve(strict=True)), allow_nan=False))


if __name__ == '__main__':
    main()
