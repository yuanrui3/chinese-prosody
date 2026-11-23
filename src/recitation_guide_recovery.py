"""Recover a conservatively bracketed syllable split by a short phone-label island."""

from math import isclose, isfinite

from audio.align import FINAL, MIN_FINAL_S, MODEL_REVISION, lexical_key


TIME_TOLERANCE_S = 1e-7
MAX_ISLAND_FRAMES = 3
LINEAGE_FIELDS = ('recording_id', 'passage_id', 'audio_path', 'audio_sha256')


def same_time(first, second):
    return isclose(first, second, rel_tol=0, abs_tol=TIME_TOLERANCE_S)


def observed_key(event):
    evidence = (event or {}).get('observed_phone_draft') or {}
    return evidence.get('onset'), evidence.get('final')


def observed_final(label):
    return label[:-1].replace('u:', 'v'), label[-1]


def same_final_event(event, phone):
    final, tone = observed_final(phone['label'])
    return (observed_key(event) == ('', final) and event['observed_phone_draft']['tone'] == tone
            and same_time(event['start_s'], phone['start_s']) and same_time(event['end_s'], phone['end_s']))


def recover_fragmented_clause(take, slots, linked, draft, events):
    """Return temporary timing links and provenance, or abstain on ambiguous brackets.

    The strict flanks must surround exactly one written slot and two cached
    events. Raw runs must show the intended onset, a sub-threshold fragment of
    the intended final, a brief alternative final, and a second run of the
    first final with the same tone. This repairs timing, not pronunciation.
    """
    if draft['model_revision'] != MODEL_REVISION or any(draft.get(key) != take[key] for key in LINEAGE_FIELDS):
        raise ValueError('Fragment recovery requires the pinned draft for the exact source waveform')
    frame_s = draft['frame_s']
    if not same_time(frame_s, 0.01):
        raise ValueError('Fragment recovery requires the pinned 10 ms phone grid')

    keys = {slot['slot_index']: lexical_key(take['intended_pinyin'][slot['slot_index']])[0] for slot in slots}
    mismatches = [slot for slot in slots if observed_key(linked.get(slot['slot_index'])) != keys[slot['slot_index']]]
    if len(mismatches) != 1:
        return None
    target = mismatches[0]
    index = target['slot_index']
    if index - 1 not in keys or index + 1 not in keys:
        return None
    onset, final = keys[index]
    left, right = linked[index - 1], linked[index + 1]
    if not onset or right['event_index'] != left['event_index'] + 3:
        return None

    by_event = {event['event_index']: event for event in events}
    if len(by_event) != len(events) or any(event.get(key) != take[key]
                                          for event in by_event.values() for key in LINEAGE_FIELDS):
        raise ValueError('Fragment recovery requires unique alignment events for the same waveform')
    neighbors = [by_event.get(anchor['event_index']) for anchor in (left, right)]
    for cached, source in zip(neighbors, (left, right)):
        if (not cached or cached['status'] != 'matched' or cached['slot_index'] != source['slot_index']
                or cached['observed_phone_draft'] != source['observed_phone_draft']
                or not same_time(cached['start_s'], source['start_s']) or not same_time(cached['end_s'], source['end_s'])):
            return None
    left_event = left['event_index']
    insertion, substitution = by_event.get(left_event + 1), by_event.get(left_event + 2)
    if (not insertion or insertion['status'] != 'insertion' or insertion['slot_index'] is not None
            or not substitution or substitution['status'] != 'substitution' or substitution['slot_index'] != index):
        return None

    start, end = left['end_s'], right['start_s']
    runs = [phone for phone in draft['phones']
            if phone['end_s'] > start + TIME_TOLERANCE_S and phone['start_s'] < end - TIME_TOLERANCE_S]
    if (len(runs) != 4 or not same_time(runs[0]['start_s'], start) or not same_time(runs[-1]['end_s'], end)
            or any(not same_time(a['end_s'], b['start_s']) for a, b in zip(runs, runs[1:]))
            or any(run['end_s'] <= run['start_s'] or not isfinite(run['confidence'])
                   or not 0 <= run['confidence'] <= 1 for run in runs)):
        return None
    onset_run, first, island, last = runs
    if onset_run['label'] != onset or any(not FINAL.fullmatch(run['label']) for run in runs[1:]):
        return None
    first_key, island_key, last_key = (observed_final(run['label']) for run in (first, island, last))
    first_final_s, island_s, last_final_s = (run['end_s'] - run['start_s'] for run in (first, island, last))
    if (first_key != last_key or first_key[0] != final or island_key[0] == final or island_key[1] != last_key[1]
            or first_final_s >= MIN_FINAL_S - TIME_TOLERANCE_S or last_final_s < MIN_FINAL_S - TIME_TOLERANCE_S
            or island_s > MAX_ISLAND_FRAMES * frame_s + TIME_TOLERANCE_S
            or first_final_s + last_final_s + TIME_TOLERANCE_S < island_s + frame_s
            or not same_final_event(insertion, island) or not same_final_event(substitution, last)):
        return None

    recovery = {
        'method': 'bracketed_fragmented_final_timing_draft',
        'model_revision': draft['model_revision'], 'frame_s': frame_s, 'audio_sha256': draft['audio_sha256'],
        'slot_index': index, 'character': target['char'], 'anchor_slot_indices': [index - 1, index + 1],
        'start_s': start, 'end_s': end, 'raw_phones': runs,
        'original_alignment_events': [insertion, substitution],
        'fragment_support_s': first_final_s + last_final_s, 'competing_final_s': island_s,
    }
    return {
        **linked,
        index: {
            **substitution, 'char': target['char'], 'status': 'recovered_timing_draft',
            'start_s': start, 'end_s': end, 'event_index': insertion['event_index'],
            'last_event_index': substitution['event_index'], 'duration_ms': 1000 * (end - start),
            'supported_segments': [onset_run['label'], last_key[0]],
        },
    }, recovery
