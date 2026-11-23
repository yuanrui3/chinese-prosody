"""Compare forced alignment across the three unchanged phrasing WAVs per clause."""

import argparse
from collections import Counter
import json
from math import isfinite
import os
from pathlib import Path
from statistics import mean, median

from src.pilot_validation import write_json
from src.recitation_phrasing_analysis import MANIFEST, ROLES
from src.recitation_pcm_alignment import OUTPUT as PCM_ALIGNMENT
from src.stage6_listening import digest, read_json


FORCED_ALIGNMENT = MANIFEST.with_name('forced-alignment.json')
OUTPUT = MANIFEST.with_name('second-aligner-comparison.json')
TAKES = ('carrier', *ROLES)


def index_rows(rows, key):
    index = {row[key]: row for row in rows}
    if len(index) != len(rows):
        raise ValueError(f'Duplicate {key} in alignment data')
    return index


def milliseconds(seconds):
    return round(1000 * seconds, 6)


def difference(left, right):
    return None if left is None or right is None else round(left - right, 6)


def midpoint(span):
    return None if span is None else (span['start_s'] + span['end_s']) / 2


def span_gap(right, left):
    return right['start_s'] - left['end_s']


def usable_spans(root, member, take, indices, rate):
    path = (root / member['audio_path']).resolve(strict=True)
    if (not path.is_relative_to(root / 'audio') or take['audio_sha256'] != member['audio_sha256']
            or digest(path) != member['audio_sha256']):
        raise ValueError('Forced alignment does not match the verified WAV')
    if take['status'] != 'aligned':
        return [None] * len(indices)
    slots = index_rows(take['slots'], 'slot_index')
    spans = [slots.get(index) for index in indices]
    duration = member['sample_count'] / rate
    previous_end = 0
    for span in spans:
        if span is None:
            continue
        start, end = (span[key] for key in ('start_s', 'end_s'))
        if not (previous_end <= start + 1e-7 and 0 <= start < end <= duration + 1e-7):
            raise ValueError('Forced spans are disordered or outside the verified WAV')
        previous_end = end
    return spans


def differences(left, right, method):
    return [None if a is None or b is None else milliseconds(method(a, b)) for a, b in zip(left, right)]


def separation(spans, method):
    return differences(spans[1:], spans[:-1], method)


def compare_pair(root, pair, pcm, forced):
    indices = pair['slot_indices']
    if len(indices) != 4 or len(set(indices)) != 4:
        raise ValueError('Expected four distinct character slots')
    if (pair['pair_id'] != pcm['pair_id'] or pair['clause_text'] != pcm['clause_text']
            or pair['pair_id'] != forced['pair_id']):
        raise ValueError('The timing rows describe different clauses')
    if pcm['status'] != 'aligned':
        return {'pair_id': pair['pair_id'], 'status': 'no_exact_pcm_reference'}

    rate = pcm['sample_rate']
    members = dict(zip(TAKES, (pair['sham'], *(pair['variants'][role] for role in ROLES))))
    concentrated, split = ROLES
    a, b = members[concentrated], members[split]
    if (a['sample_count'] != b['sample_count']
            or any(member['text_sha256'] != pair['source']['text_sha256'] or member['sample_rate'] != rate
                   for member in members.values())):
        raise ValueError('Expected identical treatment text, sample rate, and duration')
    if set(forced['takes']) != set(TAKES):
        raise ValueError('Expected one recorded alignment attempt per version')
    spans = {role: usable_spans(root, member, forced['takes'][role], indices, rate)
             for role, member in members.items()}

    raw_shifts, gap_changes, edge_gap_changes, anchor_residuals = {}, {}, {}, {}
    shifts_reference = {}
    gaps_reference = {}
    for role in ROLES:
        aligned = pcm['variants'][role]
        if [slot['slot_index'] for slot in aligned['syllables']] != indices:
            raise ValueError('PCM syllable rows differ from the expected character slots')
        shifts_reference[role] = [milliseconds(slot['core_displacement_samples'] / rate)
                                  for slot in aligned['syllables']]
        gaps_reference[role] = [gap['added_ms'] for gap in aligned['gaps']]
        raw_shifts[role] = differences(spans[role], spans['carrier'], lambda x, y: midpoint(x) - midpoint(y))
        anchor_residuals[role] = [difference(raw_shifts[role][i], shifts_reference[role][i]) for i in (0, 3)]
        gap_changes[role] = [difference(nxt, prev) for prev, nxt in zip(raw_shifts[role], raw_shifts[role][1:])]
        edge_gap_changes[role] = [difference(edited, baseline) for edited, baseline in
                                  zip(separation(spans[role], span_gap), separation(spans['carrier'], span_gap))]

    pair_core_shifts = differences(spans[split], spans[concentrated], lambda x, y: midpoint(x) - midpoint(y))
    pair_core_reference = [difference(x, y) for x, y in zip(shifts_reference[split], shifts_reference[concentrated])]
    pair_gap_change = [difference(nxt, prev) for prev, nxt in zip(pair_core_shifts, pair_core_shifts[1:])]
    pair_edge_gap_change = [difference(x, y) for x, y in zip(separation(spans[split], span_gap),
                                                              separation(spans[concentrated], span_gap))]
    pair_reference = pcm['split_minus_concentrated_ms']
    row = {
        'pair_id': pair['pair_id'], 'clause_text': pair['clause_text'],
        'status': 'measured' if None not in pair_gap_change else 'missing_character_spans',
        'take_status': {role: take['status'] for role, take in forced['takes'].items()},
        'carrier_relative': {
            'model_midpoint_shifts_ms': raw_shifts, 'pcm_core_shifts_ms': shifts_reference,
            'first_and_last_anchor_residuals_ms': anchor_residuals,
            'model_landmark_spacing_changes_ms': gap_changes,
            'model_span_gap_changes_ms': edge_gap_changes, 'pcm_pause_changes_ms': gaps_reference,
        },
        'split_minus_concentrated': {
            'model_midpoint_shifts_ms': pair_core_shifts, 'pcm_core_shifts_ms': pair_core_reference,
            'model_landmark_spacing_changes_ms': pair_gap_change,
            'model_span_gap_changes_ms': pair_edge_gap_change, 'pcm_pause_changes_ms': pair_reference,
        },
    }
    if pair['clause_text'] == '日暮途遠':
        target = 2
        baseline = pair['syllables'][target]
        cores = {role: [sample / rate for sample in pcm['variants'][role]['syllables'][target]['variant_exact_core_samples']]
                 for role in ROLES}
        intervals = {role: spans[role][target] for role in TAKES}
        shifted_model = {role: raw_shifts[role][target] for role in ROLES}
        shifted_pcm = {role: shifts_reference[role][target] for role in ROLES}
        row['guide_tu'] = {
            'slot_index': indices[target], 'character': '途', 'model_forced_spans': intervals,
            'source_draft_interval_s': [baseline['start_s'], baseline['end_s']],
            'pcm_copied_core_s': cores,
            'model_midpoint_shifts_from_carrier_ms': shifted_model,
            'pcm_core_shifts_from_carrier_ms': shifted_pcm,
            'model_midpoint_shift_error_ms': {role: difference(shifted_model[role], shifted_pcm[role])
                                              for role in ROLES},
            'model_span_pcm_core_overlap_ms': {role: None if intervals[role] is None else milliseconds(max(
                0, min(intervals[role]['end_s'], right) - max(intervals[role]['start_s'], left)))
                for role, (left, right) in cores.items()},
            'model_split_minus_concentrated_midpoint_ms': pair_core_shifts[target],
            'pcm_split_minus_concentrated_core_ms': pair_core_reference[target],
            'interpretation': 'The character is supplied in the alignment transcript. Its assigned timing '
                              'does not establish its pronounced vowel or reading.',
        }
    return row


def timing_summary(values, reference, tolerance):
    measured = [value for value in values if value is not None]
    errors = [abs(value - expected) for value, expected in zip(values, reference) if value is not None]
    return {'measured': len(measured), 'abstentions': len(values) - len(measured),
            'median_ms': median(measured) if measured else None,
            'median_absolute_error_ms': median(errors) if errors else None,
            'within_tolerance': sum(error <= tolerance + 1e-6 for error in errors)}


def summarize(rows, frame_ms):
    compared = [row for row in rows if 'split_minus_concentrated' in row]
    contrasts = [row['split_minus_concentrated'] for row in compared]
    result = {'pairs': len(rows), 'status_counts': dict(Counter(row['status'] for row in rows)),
              'take_status_counts': dict(Counter(value for row in compared for value in row['take_status'].values())),
              'all_three_takes_aligned': sum(all(status == 'aligned' for status in row['take_status'].values())
                                             for row in compared),
              'frame_ms': frame_ms, 'spacing_tolerance_ms': 2 * frame_ms, 'approaches': {}}
    for field in ('model_landmark_spacing_changes_ms', 'model_span_gap_changes_ms'):
        measurements = [value[field] for value in contrasts]
        reference = [value['pcm_pause_changes_ms'] for value in contrasts]
        result['approaches'][field] = {
            'two_boundary_pairs': sum(None not in values[:2] for values in measurements),
            'both_pcm_directions': sum(None not in values[:2] and all(values[i] * expected[i] > 0 for i in (0, 1))
                                       for values, expected in zip(measurements, reference)),
            'boundaries': [{'after_slot': i + 1, **timing_summary([values[i] for values in measurements],
                                         [values[i] for values in reference], 2 * frame_ms)}
                           for i in range(3)],
        }
    result['midpoint_displacements'] = timing_summary(
        [value for row in compared for role in ROLES for value in row['carrier_relative']['model_midpoint_shifts_ms'][role]],
        [value for row in compared for role in ROLES for value in row['carrier_relative']['pcm_core_shifts_ms'][role]],
        frame_ms,
    )
    anchors = [abs(residual) for row in compared for role in ROLES
               for residual in row['carrier_relative']['first_and_last_anchor_residuals_ms'][role]
               if residual is not None]
    result['anchor_residuals'] = {'measured': len(anchors),
                                  'mean_absolute_ms': mean(anchors) if anchors else None,
                                  'max_absolute_ms': max(anchors) if anchors else None}
    result['guide_tu'] = next((row['guide_tu'] for row in compared if 'guide_tu' in row), None)
    return result


def analyze(root, forced_path):
    manifest = root / MANIFEST
    pcm_path = root / PCM_ALIGNMENT
    forced = read_json(forced_path)
    pcm = read_json(pcm_path)
    fingerprint = digest(manifest)
    frame_ms = forced['frame_ms']
    if (forced.get('stimuli_sha256', forced.get('manifest_sha256')) != fingerprint
            or pcm['stimuli_sha256'] != fingerprint or not isfinite(frame_ms) or frame_ms <= 0):
        raise ValueError('Alignment input belongs to a different experiment or has invalid frame timing')
    pairs = index_rows(read_json(manifest)['pairs'], 'pair_id')
    pcm_rows = index_rows(pcm['pairs'], 'pair_id')
    forced_rows = index_rows(forced['pairs'], 'pair_id')
    if not pairs or pairs.keys() != pcm_rows.keys() or pairs.keys() != forced_rows.keys():
        raise ValueError('Alignment files must account for every manifest pair')
    rows = [compare_pair(root, pair, pcm_rows[key], forced_rows[key]) for key, pair in pairs.items()]
    summary = summarize(rows, frame_ms)
    write_json(root / OUTPUT, {'stimuli_sha256': fingerprint, 'pcm_alignment_sha256': digest(pcm_path),
                               'forced_alignment_sha256': digest(forced_path), 'model': forced['model'],
                               'summary': summary, 'pairs': rows})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--alignment', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve(strict=True)
    print(json.dumps(analyze(root, args.alignment or root / FORCED_ALIGNMENT), ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
