"""Audit secondary elapsed spans against locally matched phone timings."""

from math import isfinite
from statistics import median

from src.recitation_second_aligner import FRAME_MS, MODEL, REVISION, WEIGHTS_SHA256, map_intervals


TOLERANCE_MS = 3 * FRAME_MS
ANCHOR_DISTANCE = 2
SPAN_FIELDS = ('articulation_ms', 'bracketed_elapsed_ms', 'secondary_elapsed_ms',
               'secondary_anchored_elapsed_ms')


def validated_slots(row, passage, take, duration_ms):
    identity = ('recording_id', 'passage_id', 'audio_sha256', 'text_sha256')
    if (any(row[field] != take[field] for field in identity)
            or row['sample_count'] != round(duration_ms * take['sample_rate'] / 1000)):
        raise ValueError('Secondary alignment differs from the verified recording')
    if row['status'] != 'aligned':
        if (row['slots'] or row['status'] not in ('timestamp_count_differs_from_han_count',
                'invalid_timestamp_order_or_bounds', 'timestamp_prediction_rejected', 'nonfinite_timestamp')):
            raise ValueError('Invalid failed alignment row')
        return {}
    slots = row['slots']
    characters = [slot['char'] for slot in passage['slots']]
    intervals = [item['model_timestamp_ms'] for item in slots]
    if any(not isfinite(value) for interval in intervals for value in interval):
        raise ValueError('Secondary alignment has a nonfinite timestamp')
    clip_ms = 1000 * row['sample_count'] / take['sample_rate']
    expected, status = map_intervals(intervals, characters, clip_ms)
    if status != 'aligned' or slots != expected:
        raise ValueError('Secondary alignment has invalid positions or timestamps')
    return {slot['slot_index']: slot for slot in slots}


def midpoint(row):
    return (row['start_s'] + row['end_s']) / 2


def endpoint_support(number, secondary, linked, agreement_ms):
    if number in linked:
        return 'direct' if agreement_ms[number] <= TOLERANCE_MS else 'unsupported'
    position = midpoint(secondary[number])
    # Use the closest matched phone on either side, including across a punctuation mark.
    for direction in (-1, 1):
        nearby = (number + direction * offset for offset in range(1, ANCHOR_DISTANCE + 1))
        anchor = next((item for item in nearby if item in linked), None)
        if (anchor is None or agreement_ms[anchor] > TOLERANCE_MS
                or direction * (midpoint(linked[anchor]) - position) <= 0):
            return 'unsupported'
    return 'bracketed'


def add_elapsed(profile, passage, take, voice, secondary, events):
    linked = {event['slot_index']: event for event in events if event['duration_ms'] is not None}
    ms_errors = {number: round(1000 * abs(midpoint(event) - midpoint(secondary[number])), 9)
                 for number, event in linked.items() if number in secondary}
    clause_slots = {}
    for slot in passage['slots']:
        clause_slots.setdefault(slot['clause_index'], []).append(slot['slot_index'])
    same_endpoint_errors = []
    for clause in profile['clauses']:
        numbers = clause_slots[clause['clause_index']]
        first, last = numbers[0], numbers[-1]
        raw, supported, support = None, None, None
        if secondary:
            raw = round(1000 * (secondary[last]['end_s'] - secondary[first]['start_s']), 9)
            prior = clause['bracketed_elapsed_ms'][voice]
            if prior is not None and all(value is not None for value in clause['bracketed_elapsed_ms'].values()):
                same_endpoint_errors.append(abs(prior - raw))
            support = [endpoint_support(number, secondary, linked, ms_errors) for number in (first, last)]
            if 'unsupported' not in support:
                supported = raw
        clause.setdefault('secondary_elapsed_ms', {})[voice] = raw
        clause.setdefault('secondary_anchored_elapsed_ms', {})[voice] = supported
        clause.setdefault('secondary_endpoint_support', {})[voice] = support
    return {'recording_id': take['recording_id'], 'timestamped_han': len(secondary),
            'expected_han': len(passage['slots'])}, ms_errors, same_endpoint_errors


def coverage(rows, voices):
    def masks(row, key):
        values = {voice: row[key][voice] is not None for voice in voices}
        return {**values, 'both': all(values.values())}

    result = {}
    for key in SPAN_FIELDS:
        result[key] = {voice: sum(masks(row, key)[voice] for row in rows) for voice in (*voices, 'both')}
    result['anchor_supported_among_incomplete'] = {
        voice: sum(masks(row, 'secondary_anchored_elapsed_ms')[voice] and not masks(row, 'articulation_ms')[voice]
                   for row in rows) for voice in (*voices, 'both')}

    # Availability from either method, without pooling durations across methods.
    joint = [{voice: row['bracketed_elapsed_ms'][voice] is not None
              or row['secondary_anchored_elapsed_ms'][voice] is not None for voice in voices} for row in rows]
    result['either_elapsed_support'] = {voice: sum(row[voice] for row in joint) for voice in voices}
    result['either_elapsed_support']['both'] = sum(all(row.values()) for row in joint)
    result['new_over_original_brackets'] = {
        voice: amount - result['bracketed_elapsed_ms'][voice]
        for voice, amount in result['either_elapsed_support'].items()}
    return {'total_clauses': len(rows), **result}


def audit(data, source_sha, profiles, passages, takes, events, voices):
    if (data['manifest_sha256'] != source_sha['takes'] or data['passages_sha256'] != source_sha['passages']
            or data['frame_ms'] != FRAME_MS or
            any(data['model'][key] != value for key, value in
                {'name': MODEL, 'revision': REVISION, 'weights_sha256': WEIGHTS_SHA256}.items())):
        raise ValueError('Secondary alignment does not match the pinned model and report inputs')
    rows = {row['recording_id']: row for row in data['takes']}
    if len(rows) != len(data['takes']) or set(rows) != {take['recording_id'] for take in takes.values()}:
        raise ValueError('Secondary alignment needs exactly one row for each recording')
    by_work, by_voice = {}, {}
    for voice in voices:
        by_voice[voice] = {'takes': [], 'midpoint_error': [], 'shared_elapsed_error': []}
    for profile in profiles:
        pid = profile['witness']['passage_id']
        passage = passages[pid]
        for voice in voices:
            take = takes[pid, voice]
            ident = take['recording_id']
            duration = profile['音律美']['recorded_timing'][voice]['duration_ms']
            secondary = validated_slots(rows[ident], passage, take, duration)
            info, errors, spans = add_elapsed(profile, passage, take, voice, secondary, events[ident])
            by_voice[voice]['takes'].append({**info, 'status': rows[ident]['status']})
            by_voice[voice]['midpoint_error'].extend(errors.values())
            by_voice[voice]['shared_elapsed_error'].extend(spans)
        by_work[pid] = coverage(profile['clauses'], voices)
    summaries = {}
    for voice, measurements in by_voice.items():
        midpoints = measurements['midpoint_error']
        spans = measurements['shared_elapsed_error']
        summaries[voice] = {'takes': measurements['takes'], 'shared_han_midpoints': len(midpoints),
                            'han_midpoints_within_tolerance': sum(ms <= TOLERANCE_MS for ms in midpoints),
                            'median_absolute_midpoint_error_ms': median(midpoints) if midpoints else None,
                            'original_shared_elapsed_compared': len(spans),
                            'median_absolute_original_shared_elapsed_difference_ms': median(spans) if spans else None}
    all_clauses = [row for profile in profiles for row in profile['clauses']]
    return {'model': data['model'], 'frame_ms': FRAME_MS, 'anchor_tolerance_ms': TOLERANCE_MS,
            'max_slot_distance_per_side': ANCHOR_DISTANCE, 'comparison_by_voice': summaries,
            'coverage': coverage(all_clauses, voices), 'coverage_by_passage': by_work}
