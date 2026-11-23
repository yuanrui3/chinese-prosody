"""Evaluate the frozen waveform detector against independently timed Mandarin labels."""

import argparse
from array import array
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from statistics import mean
import sys
import wave

from src.quantitative_noise_aware_detector import (
    NOISE_AWARE_SETTINGS, WEAK_GAP_BRIDGE_SETTINGS, detect_noise_aware,
)


MIN_PAUSE_S = NOISE_AWARE_SETTINGS['minimum_internal_quiet_ms'] / 1000
MIN_IOU = 0.5
TOLERANCES_MS = (20, 50)
EPSILON = 1e-8


def read_wav(path, *, downmix=False):
    with path.open('rb') as source:
        audio_sha256 = sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            audio_sha256.update(chunk)
        source.seek(0)
        with wave.open(source, 'rb') as handle:
            channels = handle.getnchannels()
            if channels not in ((1, 2) if downmix else (1,)) or handle.getsampwidth() != 2:
                raise ValueError(f'{path}: expected mono 16-bit PCM WAV')
            rate = handle.getframerate()
            samples = array('h')
            samples.frombytes(handle.readframes(handle.getnframes()))
            if len(samples) != channels * handle.getnframes():
                raise ValueError(f'{path}: truncated WAV')
    if sys.byteorder != 'little':
        samples.byteswap()
    if channels == 2:
        samples = array('h', ((left + right) // 2 for left, right in zip(samples[::2], samples[1::2])))
    return rate, samples, audio_sha256.hexdigest()


def interval(row, duration, allow_point=False):
    start, end = row['start_s'], row['end_s']
    if (not all(isinstance(value, (int, float)) and isfinite(value) for value in (start, end))
            or not 0 <= start <= duration or not start <= end <= duration + EPSILON
            or (start == min(end, duration) and not allow_point)):
        raise ValueError(f'Invalid reference interval: {row}')
    return start, min(end, duration)


def midpoint_is_scored(span, score, excluded):
    midpoint = mean(span)
    return score[0] <= midpoint < score[1] and not any(start <= midpoint < end for start, end in excluded)


def pause_length_is_eligible(span):
    return span[1] - span[0] >= MIN_PAUSE_S - EPSILON


def overlap_ratio(left, right):
    overlap = min(left[1], right[1]) - max(left[0], right[0])
    return max(0, overlap) / (max(left[1], right[1]) - min(left[0], right[0]))


def match_intervals(references, predictions):
    """Return time-ordered one-to-one matches, maximizing count then minimizing end error."""
    n_predictions = len(predictions)
    actions = [bytearray(n_predictions + 1) for _ in range(len(references) + 1)]
    previous = [(0, 0)] * (n_predictions + 1)
    for i, ref in enumerate(references, 1):
        scores = [(0, 0)] * (n_predictions + 1)
        for j, pred in enumerate(predictions, 1):
            best, action = previous[j], 1
            if scores[j - 1] > best:
                best, action = scores[j - 1], 2
            if overlap_ratio(ref, pred) >= MIN_IOU - EPSILON:
                count, cost = previous[j - 1]
                paired = count + 1, cost - abs(ref[1] - pred[1])
                if paired >= best:
                    best, action = paired, 3
            scores[j], actions[i][j] = best, action
        previous = scores
    i, j = len(references), n_predictions
    matches = []
    while i and j:
        action = actions[i][j]
        if action == 3:
            matches.append((i - 1, j - 1))
        if action != 2:
            i -= 1
        if action != 1:
            j -= 1
    return matches[::-1]


def score_match(ref, pred, pred_row):
    errors = [1000 * (candidate - reference) for reference, candidate in zip(ref, pred)]
    band = pred_row['end_range_ms']
    reference_end_ms = 1000 * ref[1]
    return {
        'iou': overlap_ratio(ref, pred),
        'signed_start_end_error_ms': errors,
        'resumption_eligible': pred_row['resumption_eligible'],
        'reference_resume_inside_band': band[0] - EPSILON <= reference_end_ms <= band[1] + EPSILON,
        'worst_band_end_error_ms': max(abs(edge - reference_end_ms) for edge in band),
    }


def score_recording(row, audio_root, *, bridge_weak_ms=0):
    path = (audio_root / row['path']).resolve(strict=True)
    if not path.is_relative_to(audio_root):
        raise ValueError(f"{row['id']}: WAV must be within the supplied audio root")
    rate, samples, wav_hash = read_wav(path)
    duration = len(samples) / rate
    score = interval({'start_s': row.get('score_start_s', 0), 'end_s': row.get('score_end_s', duration)}, duration)
    excluded = [interval(entry, duration) for entry in row.get('excluded_intervals', [])]
    boundaries = sorted({*score, *(max(score[0], min(value, score[1])) for span in excluded for value in span)})
    score_duration = sum(end - start for start, end in zip(boundaries, boundaries[1:])
                         if midpoint_is_scored((start, end), score, excluded))
    refs = [(interval(entry, duration), entry) for entry in row['pauses']]
    references = sorted(((span, entry) for span, entry in refs
                         if midpoint_is_scored(span, score, excluded) and pause_length_is_eligible(span)),
                        key=lambda item: item[0])
    detected = detect_noise_aware(samples, rate, bridge_weak_ms=bridge_weak_ms)
    predictions = []
    for index, prediction in enumerate(detected['pauses']):
        span = (prediction['start_sample'] / rate, prediction['end_sample'] / rate)
        if midpoint_is_scored(span, score, excluded):
            predictions.append((span, index, prediction))
    predicted_spans = [span for span, _, _ in predictions]
    pause_matches = []
    for i, j in match_intervals([span for span, _ in references], predicted_spans):
        ref_span, _ = references[i]
        pred_span, detector_index, pred_row = predictions[j]
        pause_matches.append({'reference_index': i, 'detector_pause_index': detector_index,
                              **score_match(ref_span, pred_span, pred_row)})

    clauses = []
    timed = []
    seen_ordinals = set()
    for clause in row.get('clauses', []):
        ordinal = clause['after_char']
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1 or ordinal in seen_ordinals:
            raise ValueError(f"{row['id']}: invalid or repeated clause ordinal {ordinal}")
        seen_ordinals.add(ordinal)
        start, end = clause['start_s'], clause['end_s']
        status = 'untimed'
        if start is not None or end is not None:
            span = interval(clause, duration, allow_point=True)
            if not midpoint_is_scored(span, score, excluded):
                status = 'outside_scored_region'
            elif pause_length_is_eligible(span):
                status = 'eligible_gap_unmatched'
                timed.append((span, len(clauses)))
            else:
                status = 'no_eligible_gap'
        clauses.append({**clause, 'status': status})
    timed.sort()
    for i, j in match_intervals([span for span, _ in timed], predicted_spans):
        ref_span, clause_index = timed[i]
        pred_span, detector_index, pred_row = predictions[j]
        clauses[clause_index].update(status='eligible_gap_matched', detector_pause_index=detector_index,
                                     **score_match(ref_span, pred_span, pred_row))

    return {
        'id': row['id'], 'speaker': row['speaker'], 'work': row['work'], 'path': row['path'],
        'wav_sha256': wav_hash, 'duration_s': duration, 'score_window_s': score,
        'score_duration_s': score_duration, 'excluded_intervals_s': excluded,
        'reference_pauses': [entry for _, entry in references],
        'reference_pauses_below_minimum_in_scored_region': sum(
            midpoint_is_scored(span, score, excluded) and not pause_length_is_eligible(span) for span, _ in refs),
        'reference_pauses_outside_scored_region': sum(not midpoint_is_scored(span, score, excluded) for span, _ in refs),
        'scored_detector_pause_indices': [index for _, index, _ in predictions],
        'pause_matches': pause_matches, 'clauses': clauses, 'detector': detected,
    }


def ratio(count, total):
    return count / total if total else None


def summarize(rows):
    reference_count = sum(len(row['reference_pauses']) for row in rows)
    predicted_count = sum(len(row['scored_detector_pause_indices']) for row in rows)
    matches = [pair for row in rows for pair in row['pause_matches']]
    eligible = [pair for pair in matches if pair['resumption_eligible']]
    errors = [pair['signed_start_end_error_ms'] for pair in matches]
    inside_band = sum(pair['reference_resume_inside_band'] for pair in eligible)
    timing = {
        'eligible_resumptions': len(eligible),
        'eligible_resumption_fraction_of_reference_pauses': ratio(len(eligible), reference_count),
        'mean_absolute_start_end_error_ms_on_matches': [mean(map(abs, edge)) for edge in zip(*errors)] if errors else None,
        'mean_signed_start_end_error_ms_on_matches': [mean(edge) for edge in zip(*errors)] if errors else None,
        'reference_resume_inside_eligible_detector_band': inside_band,
        'reference_resume_inside_eligible_detector_band_fraction': ratio(inside_band, len(eligible)),
    }
    for tolerance in TOLERANCES_MS:
        limit = tolerance + EPSILON
        both_edges = sum(max(map(abs, pair['signed_start_end_error_ms'])) <= limit for pair in matches)
        eligible_center = sum(abs(pair['signed_start_end_error_ms'][1]) <= limit for pair in eligible)
        eligible_band = sum(pair['worst_band_end_error_ms'] <= limit for pair in eligible)
        timing[f'within_{tolerance}ms'] = {
            'matches_with_both_central_edges': both_edges,
            'eligible_resume_central_edge': eligible_center,
            'eligible_resume_full_band': eligible_band,
            'reference_pause_fraction_with_eligible_full_resume_band': ratio(eligible_band, reference_count),
            'eligible_resume_fraction_with_full_band': ratio(eligible_band, len(eligible)),
        }
    clauses = [clause for row in rows for clause in row['clauses']]
    clause_counts = Counter(clause['status'] for clause in clauses)
    assoc = clause_counts['eligible_gap_matched']
    gaps = assoc + clause_counts['eligible_gap_unmatched']
    return {
        'recordings': len(rows),
        'scored_duration_s': sum(row['score_duration_s'] for row in rows),
        'detector_statuses': dict(Counter(row['detector']['status'] for row in rows)),
        'detector_modes': dict(Counter(row['detector']['mode'] for row in rows)),
        'detection': {
            'reference_pauses': reference_count, 'predicted_pauses': predicted_count, 'matched_pauses': len(matches),
            'false_positive_pauses': predicted_count - len(matches), 'missed_reference_pauses': reference_count - len(matches),
            'precision': ratio(len(matches), predicted_count), 'recall': ratio(len(matches), reference_count),
            'f1': ratio(2 * len(matches), reference_count + predicted_count),
        },
        'timing': timing,
        'clause_gap_association': {
            'labels': len(clauses), 'statuses': dict(clause_counts), 'eligible_gaps': gaps,
            'matched_fraction_of_eligible_gaps': ratio(assoc, gaps),
            'matched_fraction_of_all_timed_in_scope_clauses': ratio(assoc, gaps + clause_counts['no_eligible_gap']),
        },
    }


def evaluate(reference, audio_root, *, bridge_weak_ms=0):
    audio_root = audio_root.resolve(strict=True)
    rows = []
    by_speaker = defaultdict(list)
    seen = set()
    for row in reference['recordings']:
        if not row['id'] or row['id'] in seen:
            raise ValueError(f"Empty or duplicate recording ID: {row['id']}")
        seen.add(row['id'])
        scored = score_recording(row, audio_root, bridge_weak_ms=bridge_weak_ms)
        rows.append(scored)
        by_speaker[scored['speaker']].append(scored)
    speakers = {speaker: summarize(group) for speaker, group in sorted(by_speaker.items())}
    macro = {}
    for metric in ('precision', 'recall', 'f1'):
        values = [speaker['detection'][metric] for speaker in speakers.values()
                  if speaker['detection'][metric] is not None]
        macro[metric] = mean(values) if values else None
        macro[f'{metric}_speakers'] = len(values)
    settings = {'detector': NOISE_AWARE_SETTINGS, 'minimum_reference_pause_s': MIN_PAUSE_S,
                'minimum_match_iou': MIN_IOU, 'edge_tolerances_ms': TOLERANCES_MS,
                'score_window_rule': 'midpoint in half-open score window and outside exclusions',
                'assignment': 'monotonic maximum pair count then minimum total absolute resumption error'}
    if bridge_weak_ms:
        settings['weak_gap_bridge'] = {**WEAK_GAP_BRIDGE_SETTINGS, 'maximum_bridge_ms': bridge_weak_ms,
                                       'applied_in_mode': 'noise_aware'}
    return {
        'settings': settings,
        'reference_metadata': {key: value for key, value in reference.items() if key != 'recordings'},
        'pooled': summarize(rows), 'by_speaker': speakers, 'speaker_macro_detection': macro,
        'recordings': rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--audio-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bridge-weak-ms', type=int,
                        choices=(0, WEAK_GAP_BRIDGE_SETTINGS['maximum_bridge_ms']), default=0,
                        help='Enable the experimental noise-aware bridge for brief weak interruptions')
    args = parser.parse_args()
    source = args.references.read_bytes()
    result = evaluate(json.loads(source), args.audio_root, bridge_weak_ms=args.bridge_weak_ms)
    result['references_sha256'] = sha256(source).hexdigest()
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(result['pooled'], ensure_ascii=False))


if __name__ == '__main__':
    main()
