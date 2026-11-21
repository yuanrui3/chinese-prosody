"""Verify staged pilot artifacts and index comparable waveform pairs."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import median
import wave

from align import lexical_key, read_rows, write_rows


def validate_recording(root, recording):
    media = (root / recording['audio_path']).resolve(strict=True)
    if not media.is_relative_to(root / 'audio' / 'raw' / 'synthetic'):
        raise ValueError(f'Unexpected synthetic path: {media}')
    with wave.open(str(media), 'rb') as stream:
        frames = stream.getnframes()
        if (frames <= 0 or stream.getnchannels() != 1 or stream.getsampwidth() != 2
                or stream.getframerate() != recording['sample_rate']
                or abs(frames / stream.getframerate() - recording['duration_s']) > 1e-6):
            raise ValueError(f'WAV header disagrees with manifest: {media}')
    with media.open('rb') as source:
        sha = hashlib.file_digest(source, 'sha256').hexdigest()
    if sha != recording['audio_sha256']:
        raise ValueError(f'WAV checksum disagrees with manifest: {media}')


def pair_records(passages, recordings):
    groups = defaultdict(list)
    for passage in passages:
        if passage['pair_id']:
            groups[passage['pair_id']].append(passage)
    indexed = {(row['passage_id'], row['speaker'], row['speed']): row for row in recordings}
    conditions = sorted({(row['speaker'], row['speed']) for row in recordings})
    for identifier, sides in sorted(groups.items()):
        if len(sides) != 2:
            raise ValueError(f'{identifier}: pair must have exactly two source members')
        left, right = sides
        for voice, speed in conditions:
            a = indexed.get((left['passage_id'], voice, speed))
            b = indexed.get((right['passage_id'], voice, speed))
            if not a or not b:
                continue
            variant = left['subset'] == 'critic_probe'
            yield {'comparison_id': f'{identifier}/{voice}/{speed}', 'pair_id': identifier,
                   'comparison': 'historical_wording_variant' if variant else 'period_matched_prose',
                   'speaker_preset': voice, 'speed': speed, 'kind': 'synthetic',
                   'members': [{key: row[key] for key in ('recording_id', 'passage_id', 'audio_path', 'audio_sha256')}
                               for row in (a, b)],
                   'source_edit': (left.get('edit') or right.get('edit')) if variant else None,
                   'preparation': 'full_pilot_waveform', 'listening_review': 'pending'}


def nullable_median(values):
    retained = [value for value in values if value is not None]
    return median(retained) if retained else None


def observed_prompt_agreement(rows, recordings):
    counts = Counter()
    for row in rows:
        observed, slot = row.get('observed_phone_draft'), row.get('slot_index')
        if row['status'] != 'matched' or not observed or slot is None:
            continue
        key, tone = lexical_key(recordings[row['recording_id']]['intended_pinyin'][slot])
        if key != (observed['onset'], observed['final']):
            counts['segment_difference'] += 1
        elif tone != observed['tone']:
            counts['tone_difference'] += 1
        else:
            counts['segment_and_tone_agreement'] += 1
    return dict(counts)


def check(root):
    passages = read_rows(root / 'data/pilot/annotated.jsonl')
    manifests = root / 'audio/manifests'
    recordings = read_rows(manifests / 'synthetic.jsonl')
    summaries = read_rows(root / 'audio/derived/features/recordings.jsonl')
    gaps = read_rows(root / 'audio/derived/features/gaps.jsonl')
    rows = read_rows(root / 'audio/derived/features/syllables.jsonl')
    by_id = {recording['recording_id']: recording for recording in recordings}
    if (len(by_id) != len(recordings) or len(summaries) != len(by_id)
            or {summary['recording_id'] for summary in summaries} != by_id.keys()):
        raise ValueError('Audio and feature manifests disagree on the set of recordings')
    for recording in recordings:
        validate_recording(root, recording)
    pairs = list(pair_records(passages, recordings))
    summary = {'recordings': len(recordings), 'passages': len({row['passage_id'] for row in recordings}),
               'duration_total_s': round(sum(row['duration_s'] for row in recordings), 2),
               'events_by_status': dict(Counter(row['status'] for row in rows)),
               'syllable_slots_expected': sum(row['slots_expected'] for row in summaries),
               'syllable_slots_measured': sum(row['slots_measured'] for row in summaries),
               'reviewed_pronunciations': sum(row['pronunciations_recorded'] for row in summaries),
               'eligible_gaps': len(gaps), 'f0_measured_syllables': sum(row['f0_median_hz'] is not None for row in rows),
               'candidate_quiet_gaps_150_ms': sum(150 in gap['quiet_candidate_ms_thresholds'] for gap in gaps),
               'candidate_quiet_gaps_at_punctuation': sum(150 in gap['quiet_candidate_ms_thresholds']
                                                           and gap['boundary_after'] > 0 for gap in gaps),
               'observed_prompt_agreement_matched_slots': observed_prompt_agreement(rows, by_id),
               'listening_pairs': dict(Counter(pair['comparison'] for pair in pairs)),
               'median_recording_guangyun_ping_ze_ratio': nullable_median(
                   row['ping_ze_duration']['guangyun']['geomean_ping_ze_ratio'] for row in summaries),
               'groups': {}}
    by_condition = defaultdict(list)
    for row in summaries:
        stimulus = by_id[row['recording_id']]
        by_condition[f"{stimulus['speaker']}/{stimulus['speed']:.1f}"].append(row)
    for condition, members in sorted(by_condition.items()):
        summary['groups'][condition] = {'recordings': len(members),
                                        'median_duration_s': nullable_median(row['waveform_duration_s'] for row in members),
                                        'measured_slots': sum(row['slots_measured'] for row in members)}
    write_rows(manifests / 'listening-pairs.jsonl', pairs)
    write_rows(root / 'audio/derived/pilot-summary.jsonl', [summary])
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    check(parser.parse_args().root.resolve(strict=True))
