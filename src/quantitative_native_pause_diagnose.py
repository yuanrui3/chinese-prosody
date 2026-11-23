"""Audit frozen native-pause misses against recorded detector gates and original PCM."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from src.quantitative_native_pause_eval import EPSILON, overlap_ratio, read_wav
from src.quantitative_noise_aware_detector import NOISE_AWARE_SETTINGS, detect_noise_aware, power_ratio
from src.quantitative_waveform_reference import runs


def quiet_run_replay(samples, rate, stored):
    """Recover the primary-cutoff runs, including those the frozen detector rejected."""
    detector = detect_noise_aware(samples, rate)
    if detector != stored:
        raise ValueError('Frozen detector output differs from the evaluation')
    if detector['status'] != 'ok':
        return []

    settings = NOISE_AWARE_SETTINGS
    frame = max(1, round(rate * settings['frame_ms'] / 1000))
    frame_ms = 1000 * frame / rate
    powers = [sum(int(value) ** 2 for value in samples[start:start + frame]) / frame
              for start in range(0, len(samples) - frame + 1, frame)]
    clear_level = detector['reference_frame_power'] * power_ratio(settings['clear_activity_relative_db'])
    decision_powers = powers
    if detector['mode'] == 'noise_aware':
        if len(powers) >= 3:
            decision_powers = [powers[0], *(median(values) for values in zip(powers, powers[1:], powers[2:])),
                               powers[-1]]
        clear_level = max(clear_level, detector['background_frame_power']
                          * power_ratio(settings['clear_activity_above_background_db']))
    cutoff = detector['quiet_cutoff_powers'][1]
    clear = [power > clear_level for power in powers]
    flank = int(settings['activity_context_ms'] / frame_ms)
    archived = {(row['start_sample'], row['end_sample']): index for index, row in enumerate(detector['pauses'])}
    reconstructed = []
    for left, right in runs([power <= cutoff for power in decision_powers]):
        duration = (right - left) * frame_ms
        before = sum(clear[max(0, left - flank):left]) * frame_ms
        after = sum(clear[right:right + flank]) * frame_ms
        samples_span = left * frame, right * frame
        index = archived.get(samples_span)
        if left == 0 or right == len(powers):
            gate = 'recording_edge'
        elif duration < settings['minimum_internal_quiet_ms']:
            gate = 'below_minimum_duration'
        elif min(before, after) < settings['minimum_clear_activity_ms']:
            gate = 'insufficient_adjacent_activity'
        else:
            gate = 'accepted'
        if (index is not None) != (gate == 'accepted'):
            raise ValueError(f'Reconstructed gate {gate} differs at samples {samples_span}')
        reconstructed.append({'start_s': samples_span[0] / rate, 'end_s': samples_span[1] / rate,
                              'duration_ms': duration, 'clear_activity_before_after_ms': [before, after],
                              'gate': gate, 'detector_pause_index': index})
    gates = Counter(row['gate'] for row in reconstructed)
    if (gates['accepted'] != len(archived)
            or gates['accepted'] + gates['insufficient_adjacent_activity'] != detector['quiet_candidates']
            or gates['insufficient_adjacent_activity']
            != detector['quiet_candidate_rejections']['insufficient_adjacent_activity']):
        raise ValueError('Replayed and archived candidate counts differ')
    return reconstructed


def explain(miss, quiet, row, min_iou):
    ref = miss['start_s'], miss['end_s']
    detector = row['detector']
    scored = set(row['scored_detector_pause_indices'])
    matched = {pair['detector_pause_index']: pair['reference_index'] for pair in row['pause_matches']}
    overlapping, intersections = [], []
    for run in quiet:
        span = run['start_s'], run['end_s']
        left, right = max(ref[0], span[0]), min(ref[1], span[1])
        if left >= right:
            continue
        intersections.append((left, right))
        details = {**run, 'overlap_ms': 1000 * (right - left), 'iou': overlap_ratio(ref, span)}
        index = run['detector_pause_index']
        if index is not None:
            original = detector['pauses'][index]
            details.update(scored=index in scored, assigned_reference_index=matched.get(index),
                           resumption_eligible=original['resumption_eligible'],
                           end_range_ms=original['end_range_ms'])
        overlapping.append(details)

    qualified = [run for run in overlapping if run['iou'] >= min_iou - EPSILON]
    accepted = [run for run in qualified if run['gate'] == 'accepted']
    if detector['status'] != 'ok':
        reason = 'recording_abstention'
    elif any(run['scored'] for run in accepted):
        reason = 'one_to_one_assignment'
    elif accepted:
        reason = 'qualified_prediction_outside_score_mask'
    elif any(run['gate'] == 'insufficient_adjacent_activity' for run in qualified):
        reason = 'insufficient_adjacent_activity'
    elif any(run['gate'] == 'recording_edge' for run in qualified):
        reason = 'recording_edge_exclusion'
    elif not overlapping:
        reason = 'no_quiet_frames'
    elif all(run['gate'] == 'below_minimum_duration' for run in overlapping):
        reason = 'fragmented_subminimum_quiet' if len(overlapping) > 1 else 'single_subminimum_quiet'
    else:
        reason = 'quiet_core_below_matching_iou'
    interruptions = [1000 * (right[0] - left[1]) for left, right in zip(intersections, intersections[1:])]
    return {
        'reference': miss, 'diagnosis': reason, 'best_iou': max((run['iou'] for run in overlapping), default=0),
        'quiet_fraction_of_reference': sum(run['overlap_ms'] for run in overlapping) / (1000 * (ref[1] - ref[0])),
        'internal_above_cutoff_breaks': len(interruptions), 'longest_internal_break_ms': max(interruptions, default=0),
        'overlapping_quiet_runs': overlapping,
    }


def audit(evaluation, audio_root):
    min_iou = evaluation['settings']['minimum_match_iou']
    if evaluation['settings']['detector'] != json.loads(json.dumps(NOISE_AWARE_SETTINGS)):
        raise ValueError('Frozen detector settings differ from the evaluation')

    groups = defaultdict(Counter)
    recordings = []
    for row in evaluation['recordings']:
        path = (audio_root / row['path']).resolve(strict=True)
        if not path.is_relative_to(audio_root):
            raise ValueError(f"{row['id']}: WAV is outside the supplied audio root")
        rate, samples, wav_hash = read_wav(path)
        if wav_hash != row['wav_sha256']:
            raise ValueError(f"{row['id']}: WAV digest differs from the evaluation")
        quiet = quiet_run_replay(samples, rate, row['detector'])
        matched = {pair['reference_index'] for pair in row['pause_matches']}
        misses = [{'reference_index': index, **explain(ref, quiet, row, min_iou)}
                  for index, ref in enumerate(row['reference_pauses']) if index not in matched]
        groups[row['speaker']].update(miss['diagnosis'] for miss in misses)
        recordings.append({'id': row['id'], 'speaker': row['speaker'], 'detector_mode': row['detector']['mode'],
                           'detector_status': row['detector']['status'], 'misses': misses})
    pooled = Counter()
    for counts in groups.values():
        pooled.update(counts)
    miss_count = sum(pooled.values())
    if miss_count != evaluation['pooled']['detection']['missed_reference_pauses']:
        raise ValueError('Diagnostic miss count differs from the evaluation')
    return {'missed_reference_pauses': miss_count, 'reason_counts': dict(pooled),
            'by_speaker': {speaker: dict(counts) for speaker, counts in sorted(groups.items())},
            'timing': evaluation['pooled']['timing'], 'recordings': recordings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--audio-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.evaluation.read_bytes()
    result = audit(json.loads(source), args.audio_root.resolve(strict=True))
    result['evaluation_sha256'] = sha256(source).hexdigest()
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'missed_reference_pauses': result['missed_reference_pauses'],
                      'reason_counts': result['reason_counts'], 'by_speaker': result['by_speaker']},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
