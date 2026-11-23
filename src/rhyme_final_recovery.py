"""Recover draft rhyme links from existing waveform-decoded phone runs."""

import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
from statistics import mean, median

from audio.align import FINAL, MODEL_REVISION, Phone, heard_syllables
from src.minimal_ending_analysis import sound_key, usable_slots, verify_bundle
from src.pilot_validation import read_jsonl, write_json
from src.stage6_listening import digest


MANIFEST = 'audio/manifests/synthetic.jsonl'
ALIGNMENTS = 'audio/derived/alignment/alignments.jsonl'
PHONE_DRAFTS = 'audio/derived/alignment/phone-drafts.jsonl'
SYLLABLES = 'audio/derived/features/syllables.jsonl'
RESULT = 'results/minimal-endings/rhyme-alignment.json'
MIN_FINAL_CONFIDENCE = 0.50
MAX_FLANK_DISTANCE = 4


def observations(phone_rows, duration):
    phones = [Phone(**row) for row in phone_rows]
    for index, phone in enumerate(phones):
        if not (0 <= phone.start_s < phone.end_s <= duration + 1e-7 and 0 <= phone.confidence <= 1):
            raise ValueError('Invalid decoded phone interval or confidence')
        if index and phone.start_s < phones[index - 1].end_s - 1e-7:
            raise ValueError('Decoded phone runs overlap')
    result = []
    for syllable in heard_syllables(phones):
        onset, final = syllable.key
        final_run = next(phone for phone in syllable.phones if FINAL.fullmatch(phone.label))
        start, end = syllable.phones[0].start_s, syllable.phones[-1].end_s
        result.append({
            'decoder': {'onset': onset, 'final': final, 'tone': syllable.tone},
            'raw_final_label': final_run.label,
            'start_s': start, 'end_s': end, 'duration_ms': 1000 * (end - start),
            'final_start_s': final_run.start_s, 'final_end_s': final_run.end_s,
            'final_duration_ms': 1000 * (final_run.end_s - final_run.start_s),
            'final_confidence': final_run.confidence,
            'confidence': mean(phone.confidence for phone in syllable.phones),
        })
    return result


def observation_key(row):
    decoder = row['decoder']
    return decoder['onset'], decoder['final']


def link_evidence(events, decoded, slot_count):
    by_span = {(row['start_s'], row['end_s']): index for index, row in enumerate(decoded)}
    addressed, used = {}, set()
    if len(by_span) != len(decoded):
        raise ValueError('Decoded syllable intervals are not unique')
    for row in events:
        slot = row['slot_index']
        if slot is not None and not 0 <= slot < slot_count:
            raise ValueError('Aligned slot outside pinned passage')
        if row['start_s'] is None and row['end_s'] is None:
            if row['status'] != 'omission':
                raise ValueError('Unheard alignment event is not an omission')
            continue
        index = by_span.get((row['start_s'], row['end_s']))
        if index is None or index in used or row['observed_phone_draft'] != decoded[index]['decoder']:
            raise ValueError('Alignment does not trace uniquely to the cached waveform decode')
        used.add(index)
        if slot is not None:
            if slot in addressed:
                raise ValueError('Duplicate linked slot')
            addressed[slot] = (index, row['status'])
    if used != set(range(len(decoded))):
        raise ValueError('Alignment and cached waveform decode have different syllable counts')
    return addressed


def trusted_context(addressed, decoded, expected_segments, endpoints):
    return {
        slot: index
        for slot, (index, status) in addressed.items()
        if slot not in endpoints and status == 'matched'
        and observation_key(decoded[index]) == expected_segments[slot]
        and decoded[index]['final_confidence'] >= MIN_FINAL_CONFIDENCE
    }


def recover(index, trusted, decoded, expected_segments, endpoints, *, occupied=()):
    last_slot = len(expected_segments) - 1
    left = max((slot for slot in trusted if 0 < index - slot <= MAX_FLANK_DISTANCE), default=None)
    right = min((slot for slot in trusted if 0 < slot - index <= MAX_FLANK_DISTANCE), default=None)
    method = 'strict_neighbor_bracket'
    if right is None and index == last_slot and left == index - 1 and index - 2 in trusted:
        # A final slot may be bounded by the recording edge only after two
        # consecutive unedited matches agreeing in both written and heard order.
        if trusted[left] != trusted[index - 2] + 1:
            return None, 'terminal_context_disagrees'
        right, right_heard = len(expected_segments), len(decoded)
        method = 'terminal_context'
    elif right is not None:
        right_heard = trusted[right]
    if left is None or right is None:
        return None, 'missing_strict_flanks'
    left_heard = trusted[left]
    if right_heard - left_heard != right - left:
        return None, 'ambiguous_interior_count'
    for slot in range(left + 1, right):
        observation = decoded[left_heard + slot - left]
        if slot not in endpoints and observation_key(observation) != expected_segments[slot]:
            return None, 'intervening_context_disagrees'
    candidate = left_heard + index - left
    if candidate in occupied:
        return None, 'competing_original_slot'
    if decoded[candidate]['final_confidence'] < MIN_FINAL_CONFIDENCE:
        return None, 'low_final_confidence'
    return (candidate, left, right), method


def masked_context_check(trusted, decoded, expected_segments, endpoints, occupied):
    """Check positional recovery after withholding a known unchanged link and its key."""
    agreement = {'tested': len(trusted), 'recovered': 0, 'agrees': 0, 'abstains': 0, 'disagrees': 0}
    for slot, original_index in trusted.items():
        unmasked = {index: raw_index for index, raw_index in trusted.items() if index != slot}
        candidate, _ = recover(slot, unmasked, decoded, expected_segments, endpoints | {slot},
                               occupied=occupied - {original_index})
        if candidate is None:
            agreement['abstains'] += 1
        else:
            agreement['recovered'] += 1
            agreement['agrees' if candidate[0] == original_index else 'disagrees'] += 1
    return agreement


def take_endpoints(member, decoded, events, features, target, anchor):
    readings = member['intended_pinyin']
    addressed = link_evidence(events, decoded, len(readings))
    expected_segments = [sound_key(reading)[:2] for reading in readings]
    endpoints = {target, anchor}
    context = trusted_context(addressed, decoded, expected_segments, endpoints)
    available = usable_slots(features)
    occupied = {addressed[slot][0] for slot in available if slot not in endpoints}
    result = {key: member[key] for key in ('recording_id', 'audio_path', 'audio_sha256')}
    result['masked_known_link_check'] = masked_context_check(context, decoded, expected_segments, endpoints, occupied)
    locations = {}
    for name, index in (('target', target), ('anchor', anchor)):
        original = available.get(index)
        if original is not None:
            raw_index, status = addressed[index]
            observation = decoded[raw_index]
            if (status != original['status'] or original['status'] != 'matched'
                    or original['observed_phone_draft'] != observation['decoder']
                    or (original['start_s'], original['end_s']) != (observation['start_s'], observation['end_s'])):
                raise ValueError('Original usable link and cached waveform evidence differ')
            before, after, method, flanks = observation, observation, 'original_link', None
        else:
            before = None
            candidate, method = recover(index, context, decoded, expected_segments, endpoints, occupied=occupied)
            if candidate is not None:
                raw_index, left, right = candidate
                flanks = [left, right]
                after = decoded[raw_index]
            else:
                after, flanks = None, None
        if after is not None:
            locations[name] = raw_index
        result[name] = {'slot_index': index, 'method': method, 'flank_slots': flanks,
                        'before': before, 'after': after}
    if len(locations) == 2 and locations['target'] == locations['anchor']:
        for name in locations:
            endpoint = result[name]
            if endpoint['before'] is None:
                endpoint.update(after=None, method='competing_endpoint', flank_slots=None)
    return result


def recurrence(take, stage):
    a, b = (take[name][stage] for name in ('target', 'anchor'))
    return a['decoder']['final'] == b['decoder']['final'] if a is not None and b is not None else None


def transition(base, edit):
    if base is None or edit is None:
        return 'unavailable'
    if base == edit:
        return 'unchanged'
    return 'gained' if edit else 'lost'


def compare(root, bundle, phone_drafts, alignments, features):
    target, anchor, durations = verify_bundle(root, bundle)
    takes = {}
    for role in ('base', 'rhyme'):
        member = bundle[role]
        recording = member['recording_id']
        draft = phone_drafts[recording]
        if draft['model_revision'] != MODEL_REVISION:
            raise ValueError('Unexpected phone decoder revision')
        for row in (draft, *alignments[recording], *features[recording]):
            if any(member[key] != row[key] for key in ('passage_id', 'audio_path', 'audio_sha256')):
                raise ValueError('Waveform provenance differs between manifest and decoded evidence')
        decoded = observations(draft['phones'], durations[role] / 1000)
        takes[role] = take_endpoints(member, decoded, alignments[recording], features[recording], target, anchor)
    expected = [sound_key(bundle[role]['intended_pinyin'][target])[1] ==
                sound_key(bundle[role]['intended_pinyin'][anchor])[1] for role in ('base', 'rhyme')]
    differences = {}
    for stage in ('before', 'after'):
        observed = {role: recurrence(takes[role], stage) for role in ('base', 'rhyme')}
        lhs, rhs = (takes[role]['target'][stage] for role in ('base', 'rhyme'))
        differences[stage] = {
            'recurrence': observed,
            'transition': transition(observed['base'], observed['rhyme']),
            'target_final_duration_delta_ms': rhs['final_duration_ms'] - lhs['final_duration_ms']
            if lhs is not None and rhs is not None else None,
        }
    return {'passage_id': bundle['base']['passage_id'], 'target_slot_index': target, 'anchor_slot_index': anchor,
            'intended_transition': transition(*expected), 'takes': takes, **differences}


def summarize(rows):
    result = {'rhyme_pairs': len(rows)}
    for stage in ('before', 'after'):
        transitions = Counter(row[stage]['transition'] for row in rows)
        durations = [row[stage]['target_final_duration_delta_ms'] for row in rows
                     if row[stage]['target_final_duration_delta_ms'] is not None]
        result[stage] = {
            'target_duration_pairs': len(durations),
            'median_signed_final_duration_delta_ms': median(durations) if durations else None,
            'median_absolute_final_duration_delta_ms': median(map(abs, durations)) if durations else None,
            'recurrence_pairs': len(rows) - transitions['unavailable'],
            'transitions': dict(transitions),
            'intended_recurrence_recovered': sum(row[stage]['transition'] == row['intended_transition'] for row in rows),
        }
    result['recovery_methods'] = dict(Counter(endpoint['method'] for row in rows for take in row['takes'].values()
                                              for endpoint in (take['target'], take['anchor'])))
    checks = Counter()
    for row in rows:
        for take in row['takes'].values():
            checks.update(take['masked_known_link_check'])
    result['masked_known_link_check'] = dict(checks)
    return result


def run(root, output=None):
    readings = read_jsonl(root / MANIFEST)
    phone_rows = read_jsonl(root / PHONE_DRAFTS)
    phones = {row['recording_id']: row for row in phone_rows}
    if not readings or len(phones) != len(phone_rows) or phones.keys() != {row['recording_id'] for row in readings}:
        raise ValueError('Synthetic and phone-draft recording inventories differ')
    tables = []
    for file in (ALIGNMENTS, SYLLABLES):
        grouped = defaultdict(list)
        for row in read_jsonl(root / file):
            grouped[row['recording_id']].append(row)
        if grouped.keys() != phones.keys():
            raise ValueError(f'{file}: recording inventory differs from phone drafts')
        tables.append(grouped)
    bundles = defaultdict(dict)
    for row in readings:
        role = row['experimental_ending']['role']
        members = bundles[row['passage_id']]
        if role in members:
            raise ValueError('Duplicate experimental role')
        members[role] = row
    comparisons = [compare(root, bundle, phones, *tables) for bundle in bundles.values()]
    summary = summarize(comparisons)
    write_json(output or root / RESULT, {
        'method': 'Independent decoded finals located using unchanged segmental context',
        'minimum_recovered_final_confidence': MIN_FINAL_CONFIDENCE,
        'max_flank_distance_slots': MAX_FLANK_DISTANCE,
        'source_sha256': {file: digest(root / file) for file in (MANIFEST, ALIGNMENTS, PHONE_DRAFTS, SYLLABLES)},
        'summary': summary, 'comparisons': comparisons,
    })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, help='Write the recovery report to this path')
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(run(args.root.resolve(strict=True), args.output), allow_nan=False))


if __name__ == '__main__':
    main()
