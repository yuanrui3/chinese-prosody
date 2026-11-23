"""Check absolute alignment timing using PCM activity edges and work-held-out shifts."""

from collections import defaultdict
from statistics import mean, median

from src.quantitative_alignment_audit import midpoint, validated_slots
from src.quantitative_waveform_reference import WAVEFORM_REFERENCE_SETTINGS, waveform_reference
from src.stage6_listening import read_clip


FIXED_SHIFT_MS = -80
MIN_TRAINING_WORKS = 2
EDGE_FAMILIES = {'clip_start': 'clip', 'clip_end': 'clip', 'pause_start': 'internal', 'pause_end': 'internal'}


def edge(row, field):
    return round(1000 * row[field], 9) if row is not None else None


def observe(passage, reference, secondary, linked):
    """Match the clip edges and only fully count-matched internal pause sequences."""
    slots = passage['slots']
    last = slots[-1]['slot_index']
    observations = []

    def add(kind, index, field, value, band):
        observations.append({'kind': kind, 'slot_index': index, 'char': slots[index]['char'],
                             'edge_ms': value, 'reference_range_ms': band,
                             'funasr_ms': edge(secondary.get(index), field),
                             'charsiu_ms': edge(linked.get(index), field)})

    add('clip_start', 0, 'start_s', reference['speech_start_ms'], reference['speech_start_range_ms'])
    add('clip_end', last, 'end_s', reference['speech_end_ms'], reference['speech_end_range_ms'])
    breaks = [left['slot_index'] for left, right in zip(slots, slots[1:])
              if left['clause_index'] != right['clause_index']]
    pauses = reference['pauses']
    rank_eligible = len(breaks) == len(pauses) and not any(reference['quiet_candidate_rejections'].values())
    if rank_eligible:
        for index, pause in zip(breaks, pauses):
            add('pause_start', index, 'end_s', pause['start_ms'], pause['start_range_ms'])
            add('pause_end', index + 1, 'start_s', pause['end_ms'], pause['end_range_ms'])
    return observations, len(breaks), rank_eligible


def learn_shift(rows, excluded_work, landmark, excluded_voice=None):
    """Use an equal-weight median across works, balancing available voices within each."""
    by_work_voice = defaultdict(list)
    for row in rows:
        if (row['work_id'] != excluded_work and row['voice'] != excluded_voice
                and landmark in (row['kind'], EDGE_FAMILIES[row['kind']])):
            by_work_voice[row['work_id'], row['voice']].append(row['funasr_ms'] - row['edge_ms'])
    by_work = defaultdict(list)
    for (work, _), residuals in by_work_voice.items():
        by_work[work].append(median(residuals))
    if len(by_work) < MIN_TRAINING_WORKS:
        return None
    return -median(median(values) for values in by_work.values())


def errors(rows, prediction):
    observed = [row for row in rows if row[prediction] is not None]
    by_work = defaultdict(list)
    for row in observed:
        value = row[prediction]
        low, high = row['reference_range_ms']
        by_work[row['work_id']].append((value - row['edge_ms'], max(low - value, 0, value - high),
                                       not 0 <= value <= row['clip_ms']))
    return {'edges': len(observed), 'works': len(by_work),
            'work_weighted_mae_ms': mean(mean(abs(signed) for signed, _, _ in values)
                                         for values in by_work.values()) if by_work else None,
            'median_signed_error_ms': median(row[prediction] - row['edge_ms'] for row in observed)
                                      if observed else None,
            'work_weighted_distance_outside_reference_range_ms': mean(
                mean(distance for _, distance, _ in values) for values in by_work.values()) if by_work else None,
            'outside_clip': sum(outside for values in by_work.values() for _, _, outside in values)}


def compare(rows, voices):
    eligible = [row for row in rows if row['edge_ms'] is not None and row['funasr_ms'] is not None]
    folds = sorted({(row['work_id'], row['voice'], landmark) for row in eligible
                    for landmark in (row['kind'], EDGE_FAMILIES[row['kind']])})
    shifts = {(work, voice, landmark): {
        'pooled_ms': learn_shift(eligible, work, landmark),
        'other_voice_ms': learn_shift(eligible, work, landmark, excluded_voice=voice),
    } for work, voice, landmark in folds}
    for row in eligible:
        shift = shifts[row['work_id'], row['voice'], EDGE_FAMILIES[row['kind']]]
        raw = row['funasr_ms']
        row['fixed_minus_80_ms'] = raw + FIXED_SHIFT_MS
        row['held_out_pooled_ms'] = raw + shift['pooled_ms'] if shift['pooled_ms'] is not None else None
        row['held_out_other_voice_ms'] = raw + shift['other_voice_ms'] if shift['other_voice_ms'] is not None else None
        landmark_shift = shifts[row['work_id'], row['voice'], row['kind']]['pooled_ms']
        row['held_out_same_landmark_ms'] = raw + landmark_shift if landmark_shift is not None else None
    scores = {}
    for voice in voices:
        for landmark in (*EDGE_FAMILIES, 'clip', 'internal'):
            selected = [row for row in eligible if row['voice'] == voice
                        and landmark in (row['kind'], EDGE_FAMILIES[row['kind']])]
            result = {'waveform_edges': sum(row['voice'] == voice and row['edge_ms'] is not None
                           and landmark in (row['kind'], EDGE_FAMILIES[row['kind']]) for row in rows),
                      'raw': errors(selected, 'funasr_ms')}
            for name in ('fixed_minus_80_ms', 'held_out_pooled_ms', 'held_out_other_voice_ms',
                         'held_out_same_landmark_ms', 'charsiu_ms'):
                common = [row for row in selected if row[name] is not None]
                result[name] = {'raw_on_same_edges': errors(common, 'funasr_ms'), 'estimate': errors(common, name)}
            scores.setdefault(voice, {})[landmark] = result
    return scores, [{'work_id': work, 'voice': voice, 'landmark': landmark, **shifts[work, voice, landmark]}
                    for work, voice, landmark in folds]


def midpoint_check(original, secondary):
    # Paired difference is descriptive. Neither model's midpoint supplies PCM truth.
    return [round(1000 * (midpoint(secondary[number]) - midpoint(original[number])), 9)
            for number in original if number in secondary]


def analyze(root, secondary_data, profiles, passages, takes, events, voices):
    secondary_rows = {row['recording_id']: row for row in secondary_data['takes']}
    waveforms, observations = [], []
    differences = defaultdict(list)
    for profile in profiles:
        pid = profile['witness']['passage_id']
        passage = passages[pid]
        for voice in voices:
            take = takes[pid, voice]
            rid = take['recording_id']
            rate, pcm = read_clip(root, take, take['sample_rate'])
            clip_ms = len(pcm) * 1000 / rate
            secondary = validated_slots(secondary_rows[rid], passage, take, clip_ms)
            linked = {row['slot_index']: row for row in events[rid] if row['duration_ms'] is not None}
            reference = waveform_reference(pcm, rate)
            local, boundaries, rank_eligible = observe(passage, reference, secondary, linked)
            identity = {'recording_id': rid, 'passage_id': pid, 'work_id': passage['work_id'], 'voice': voice,
                        'audio_sha256': take['audio_sha256'], 'clip_ms': clip_ms}
            observations.extend({**identity, **row} for row in local)
            differences[voice].extend(midpoint_check(linked, secondary))
            waveforms.append({**identity, 'expected_clause_breaks': boundaries,
                              'internal_pause_count_matches': rank_eligible, **reference})
    scores, shifts = compare(observations, voices)
    return {'waveform_settings': WAVEFORM_REFERENCE_SETTINGS, 'fixed_shift_ms': FIXED_SHIFT_MS,
            'min_training_works': MIN_TRAINING_WORKS, 'waveforms': waveforms, 'edges': observations,
            'metrics_by_voice': scores, 'held_out_shifts': shifts,
            'model_midpoint_difference': {voice: {
                'linked_positions': len(differences[voice]),
                'median_funasr_minus_charsiu_ms': median(differences[voice]) if differences[voice] else None,
                'raw_median_absolute_ms': median(map(abs, differences[voice])) if differences[voice] else None,
                'fixed_shift_median_absolute_ms': median(abs(ms + FIXED_SHIFT_MS) for ms in differences[voice])
                                                  if differences[voice] else None,
            } for voice in voices}}
