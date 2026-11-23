"""Measure same-text synthetic tone and final edits from verified WAVs."""

import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
from statistics import median

from audio.align import lexical_key
from audio.features import Waveform
from src.pilot_validation import read_jsonl, write_json
from src.stage6_listening import read_clip


ROLES = ('base', 'sham', 'tone', 'rhyme')
EDIT_COMPONENTS = {'base': [], 'sham': [], 'tone': [2], 'rhyme': [1]}
SHARED = ('passage_id', 'text_sha256', 'text_revision', 'text_source_url',
          'speaker', 'speed', 'seed', 'model_revision', 'sample_rate',
          'kind', 'style', 'variety')
SLOT_METRICS = ('duration_ms', 'f0_slope_st', 'f1_hz', 'f2_hz')


def sound_key(pinyin):
    (onset, final), tone = lexical_key(pinyin)
    return onset, final, tone


def verify_bundle(root, bundle):
    if set(bundle) != set(ROLES):
        raise ValueError('Expected exactly one of each experimental role')
    base = bundle['base']
    config = base['experimental_ending']
    original = base['intended_pinyin']
    target, anchor = config['target_slot_index'], config['anchor_slot_index']
    if not (0 <= target < len(original) - 1 and 0 <= anchor < len(original) and anchor != target):
        raise ValueError('Invalid target or anchor slot')
    timing = {}
    for role, member in bundle.items():
        edit = member['experimental_ending']
        if (edit['role'] != role or any(member[key] != base[key] for key in SHARED) or
                any(edit[key] != config[key] for key in ('target_slot_index', 'anchor_slot_index',
                                                        'voice_embedding_index'))):
            raise ValueError(f'{role}: experiment condition or source mismatch')
        if member['kind'] != 'synthetic' or member['variety'] != 'cmn':
            raise ValueError(f'{role}: expected a synthetic Mandarin stimulus')
        readings = member['intended_pinyin']
        if len(readings) != len(original):
            raise ValueError(f'{role}: written slot count changed')
        changed = [index for index, (left, right) in enumerate(zip(original, readings)) if left != right]
        if changed != ([target] if role in ('tone', 'rhyme') else []):
            raise ValueError(f'{role}: input does not change only the intended slot')
        original_key, key = sound_key(original[target]), sound_key(readings[target])
        stated = edit['candidate_key']
        if len(stated) != 3 or key != (stated[0], stated[1], str(stated[2])):
            raise ValueError(f'{role}: declared candidate and pronunciation differ')
        changed_components = [index for index, (left, right) in enumerate(zip(original_key, key)) if left != right]
        if changed_components != EDIT_COMPONENTS[role]:
            raise ValueError(f'{role}: expected one edited phonological component')
        rate, pcm = read_clip(root, member, base['sample_rate'])
        duration = len(pcm) / rate
        if not pcm or not math.isclose(duration, member['duration_s'], abs_tol=1e-6, rel_tol=0):
            raise ValueError(f'{role}: WAV duration and manifest differ')
        timing[role] = 1000 * duration
    if bundle['sham']['audio_sha256'] != base['audio_sha256']:
        raise ValueError('Same-input sham is not byte-identical to its original WAV')
    anchor_final = sound_key(original[anchor])[1]
    if ((sound_key(original[target])[1] == anchor_final) ==
            (sound_key(bundle['rhyme']['intended_pinyin'][target])[1] == anchor_final)):
        raise ValueError('Rhyme intervention does not change final recurrence with the anchor')
    return target, anchor, timing


def usable_slots(rows):
    by_slot = defaultdict(list)
    for row in rows:
        if (row['slot_index'] is not None and row['status'] in ('matched', 'reviewed')
                and row['duration_ms'] is not None):
            by_slot[row['slot_index']].append(row)
    return {slot: group[0] for slot, group in by_slot.items() if len(group) == 1}


def f0_slope(row):
    early, late = row['f0_early_st'], row['f0_late_st']
    return late - early if early is not None and late is not None else None


def central_formants(path, start, end):
    waveform = Waveform(path)
    span = (end - start) / 3
    voiced = [float(time) for time, frequency in zip(waveform.frame_centers, waveform.frequencies)
              if frequency is not None and start + span <= time <= end - span]
    if len(voiced) < 3:
        return None, None, 0
    track = waveform.sound.to_formant_burg(time_step=0.01, max_number_of_formants=5,
                                           maximum_formant=5000, window_length=0.025,
                                           pre_emphasis_from=50)
    pairs = [(track.get_value_at_time(1, time), track.get_value_at_time(2, time)) for time in voiced]
    valid = [(f1, f2) for f1, f2 in pairs if math.isfinite(f1) and math.isfinite(f2) and 0 < f1 < f2 < 5000]
    if len(valid) < 3:
        return None, None, len(valid)
    return median(f1 for f1, _ in valid), median(f2 for _, f2 in valid), len(valid)


def slot_readout(row, path=None):
    if row is None:
        return {field: None for field in (*SLOT_METRICS, 'decoder', 'confidence', 'voiced_frames',
                                          'alignment_status', 'start_s', 'end_s')} | {'formant_frames': 0}
    f1, f2, frames = central_formants(path, row['start_s'], row['end_s']) if path is not None else (None, None, 0)
    phone = row.get('observed_phone_draft') or {}
    decoder = [phone.get(field) for field in ('onset', 'final', 'tone')]
    return {
        'duration_ms': row['duration_ms'], 'f0_slope_st': f0_slope(row), 'f1_hz': f1, 'f2_hz': f2,
        'decoder': decoder if all(value is not None for value in decoder) else None,
        'confidence': row.get('confidence'), 'voiced_frames': row['voiced_frames'], 'formant_frames': frames,
        'alignment_status': row['status'], 'start_s': row['start_s'], 'end_s': row['end_s'],
    }


def compare_values(left, right, fields):
    return {field: right[field] - left[field] if left[field] is not None and right[field] is not None else None
            for field in fields}


def recurrence(target, anchor):
    left, right = target['decoder'], anchor['decoder']
    return left[1] == right[1] if left is not None and right is not None else None


def take_readout(root, member, slots, gaps, target, anchor, duration):
    slot = slot_readout(slots.get(target), root / member['audio_path'])
    reference = slot_readout(slots.get(anchor))
    expected_key = list(sound_key(member['intended_pinyin'][target]))
    observed_key = slot['decoder']
    if observed_key is not None:
        observed_key[2] = str(observed_key[2])
    return {
        'recording_id': member['recording_id'], 'clip_duration_ms': duration,
        'target': slot, 'anchor': reference, 'expected_target_key': expected_key,
        'target_decoder_matches_input': observed_key == expected_key if observed_key is not None else None,
        'adjacent': {label: slot_readout(slots.get(index)) for label, index in (('previous', target - 1),
                                                                               ('next', target + 1))},
        'gap_before_ms': gaps.get(target - 1, {}).get('gap_ms'),
        'gap_after_ms': gaps.get(target, {}).get('gap_ms'),
    }


def measure_pairs(root, bundle, syllables, gaps):
    target, anchor, timing = verify_bundle(root, bundle)
    measurements = {
        role: take_readout(root, member, usable_slots(syllables[member['recording_id']]),
                           gaps[member['recording_id']], target, anchor, timing[role])
        for role, member in bundle.items() if role != 'sham'
    }
    base = measurements['base']
    for family in ('tone', 'rhyme'):
        edit = measurements[family]
        delta = compare_values(base['target'], edit['target'], SLOT_METRICS)
        delta.update(compare_values(base, edit, ('clip_duration_ms', 'gap_before_ms', 'gap_after_ms')))
        for neighbor in ('previous', 'next'):
            change = compare_values(base['adjacent'][neighbor], edit['adjacent'][neighbor],
                                    ('duration_ms', 'f0_slope_st'))
            delta.update({f'{neighbor}_{field}': value for field, value in change.items()})
        result = {'family': family, 'passage_id': bundle['base']['passage_id'], 'target_slot_index': target,
                  'anchor_slot_index': anchor, 'sham_wav_exact': True,
                  'base': base, 'edited': edit, 'deltas_edited_minus_base': delta}
        if family == 'tone':
            change = delta['f0_slope_st']
            falling_is_edit = edit['expected_target_key'][2] == '4'
            result['falling_minus_other_f0_slope_st'] = (
                change if falling_is_edit else -change
            ) if change is not None else None
        else:
            a, b = (recurrence(take['target'], take['anchor']) for take in (base, edit))
            anchor_final = sound_key(bundle['base']['intended_pinyin'][anchor])[1]
            intended = 'gained' if edit['expected_target_key'][1] == anchor_final else 'lost'
            result['decoded_final_recurrence_with_anchor'] = {
                'base': a, 'edited': b, 'transition': 'unavailable' if a is None or b is None else
                'unchanged' if a == b else 'gained' if b else 'lost', 'intended_transition': intended}
        yield result


def summarize(pairs):
    summary = {}
    for family in ('tone', 'rhyme'):
        rows = [row for row in pairs if row['family'] == family]
        measures = {}
        for name in rows[0]['deltas_edited_minus_base']:
            values = [row['deltas_edited_minus_base'][name] for row in rows
                      if row['deltas_edited_minus_base'][name] is not None]
            measures[name] = {'pairs': len(values), 'median_signed_delta': median(values) if values else None,
                              'median_absolute_delta': median(map(abs, values)) if values else None,
                              'delta_range': [min(values), max(values)] if values else None}
        family_result = {
            'pairs': len(rows),
            'both_targets_aligned': sum(all(row[side]['target']['alignment_status'] is not None
                                            for side in ('base', 'edited')) for row in rows),
            'both_decoder_keys_match_input': sum(all(row[side]['target_decoder_matches_input'] is True
                                                      for side in ('base', 'edited')) for row in rows),
            'measures': measures,
        }
        if family == 'tone':
            oriented = [row['falling_minus_other_f0_slope_st'] for row in rows
                        if row['falling_minus_other_f0_slope_st'] is not None]
            family_result['falling_tone_check'] = {
                'pairs': len(oriented), 'more_negative_in_falling_take': sum(delta < 0 for delta in oriented),
                'median_falling_minus_other_st': median(oriented) if oriented else None,
            }
        else:
            family_result['decoded_final_recurrence'] = dict(Counter(
                row['decoded_final_recurrence_with_anchor']['transition'] for row in rows))
            family_result['intended_recurrence_recovered'] = sum(
                row['decoded_final_recurrence_with_anchor']['transition'] ==
                row['decoded_final_recurrence_with_anchor']['intended_transition'] for row in rows
            )
        summary[family] = family_result
    return summary


def analyze(root):
    analysis_root = root / 'audio/derived/features'
    manifests = read_jsonl(root / 'audio/manifests/synthetic.jsonl')
    takes = {row['recording_id']: row for row in read_jsonl(analysis_root / 'recordings.jsonl')}
    if not manifests or len(manifests) != len(takes) or {row['recording_id'] for row in manifests} != takes.keys():
        raise ValueError('Acoustic and experimental recording inventories disagree')
    syllables = defaultdict(list)
    gaps = defaultdict(dict)
    for row in read_jsonl(analysis_root / 'syllables.jsonl'):
        take = takes[row['recording_id']]
        if row['passage_id'] != take['passage_id'] or row['audio_path'] != take['audio_path']:
            raise ValueError('Syllable data and recording provenance disagree')
        syllables[row['recording_id']].append(row)
    for row in read_jsonl(analysis_root / 'gaps.jsonl'):
        take = takes[row['recording_id']]
        neighbors = gaps[row['recording_id']]
        if row['passage_id'] != take['passage_id'] or row['after_slot_index'] in neighbors:
            raise ValueError('Gap data have unsupported provenance or duplicate slot')
        neighbors[row['after_slot_index']] = row
    groups = defaultdict(dict)
    for row in manifests:
        role = row['experimental_ending']['role']
        group = groups[row['passage_id']]
        take = takes[row['recording_id']]
        if (role in group or take['passage_id'] != row['passage_id'] or take['audio_path'] != row['audio_path']
                or take['slots_expected'] != len(row['intended_pinyin'])
                or not math.isclose(take['waveform_duration_s'], row['duration_s'], abs_tol=1e-6, rel_tol=0)):
            raise ValueError('Acoustic and experimental manifests disagree')
        group[role] = row
    pairs = [pair for bundle in groups.values() for pair in measure_pairs(root, bundle, syllables, gaps)]
    summary = summarize(pairs)
    write_json(root / 'results/minimal-endings/analysis.json', {
        'passages': len(groups), 'shams_verified': len(groups), 'analysis': 'synthetic pronunciation intervention',
        'formants': 'Praat Burg, 5 formants up to 5000 Hz; median across at least 3 valid voiced frames in target central third',
        'pitch': 'late minus early F0 in semitones, using waveform pitch from the linked target',
        'pairs': pairs, 'summary': summary,
    })
    return {'passages': len(groups), 'shams_verified': len(groups), **{
        family: {'pairs': row['pairs'], 'both_targets_aligned': row['both_targets_aligned'],
                 'both_decoder_keys_match_input': row['both_decoder_keys_match_input'],
                 **{key: row['measures'][key] for key in ('clip_duration_ms', 'duration_ms',
                                                         'f0_slope_st', 'f1_hz', 'f2_hz')},
                 **({'decoded_final_recurrence': row['decoded_final_recurrence']} if family == 'rhyme' else {})}
        for family, row in summary.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(analyze(args.root.resolve(strict=True)), allow_nan=False))


if __name__ == '__main__':
    main()
