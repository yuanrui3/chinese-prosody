"""Re-decode exact waveform windows for unresolved rhyme links on Gilbreth."""

import argparse
from array import array
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import wave

from audio.align import MODEL_REVISION, MandarinDecoder
from src.minimal_ending_analysis import sound_key
from src.minimal_pitch_control import write_wav
from src.pilot_validation import read_jsonl, write_json
from src.rhyme_final_recovery import (
    ALIGNMENTS, MANIFEST, MAX_FLANK_DISTANCE, MIN_FINAL_CONFIDENCE, PHONE_DRAFTS, SYLLABLES,
    link_evidence, observation_key, observations, recover, recurrence, summarize, transition,
)
from src.stage6_listening import digest, read_clip


VIEW_CONFIG = (
    ('left_context', 0.85, 0.20, 0.11, 0.24),
    ('right_context', 0.20, 0.85, 0.23, 0.12),
    ('padded_full_take', None, None, 0.32, 0.26),
)
MAX_BOUNDARY_DIFFERENCE_S = 0.04
ABSOLUTE_TIME_FIELDS = ('start_s', 'end_s', 'final_start_s', 'final_end_s')


def final_overlap(left, right):
    return max(0.0, min(left['final_end_s'], right['final_end_s'])
               - max(left['final_start_s'], right['final_start_s']))


def register_unchanged(current, cached, addressed, expected_segments, endpoints):
    """Accept unique segmental and temporal matches outside the test endings."""
    proposed = {}
    for slot, (index, _) in addressed.items():
        if slot in endpoints:
            continue
        reference = cached[index]
        hits = []
        for j, row in enumerate(current):
            overlap = final_overlap(reference, row)
            reference_length = reference['final_end_s'] - reference['final_start_s']
            length = row['final_end_s'] - row['final_start_s']
            if (observation_key(row) == expected_segments[slot]
                    and row['final_confidence'] >= MIN_FINAL_CONFIDENCE
                    and overlap >= min(reference_length, length) / 2
                    and abs(row['final_start_s'] - reference['final_start_s']) <= 0.10):
                hits.append(j)
        if len(hits) == 1:
            proposed[slot] = hits[0]

    # Each raw final can belong to at most one unchanged slot. Remove any
    # crossing registrations before using the remaining independent anchors.
    counts = Counter(proposed.values())
    return {
        slot: index for slot, index in proposed.items() if counts[index] == 1
        and all((other_slot - slot) * (other_index - index) > 0
                for other_slot, other_index in proposed.items() if other_slot != slot)
    }


def decode_view(decoder, folder, pcm, rate, left, right, prefix, suffix):
    path = folder / 'view.wav'
    prefix_samples, suffix_samples = round(prefix * rate), round(suffix * rate)
    copied = array('h', [0]) * prefix_samples + pcm[left:right] + array('h', [0]) * suffix_samples
    write_wav(path, copied, rate)
    with wave.open(str(path), 'rb') as stream:
        frames = stream.readframes(stream.getnframes())
        if stream.getframerate() != rate or len(frames) != 2 * len(copied):
            raise ValueError('Re-decode view has the wrong audio format or duration')
        checked = array('h')
        checked.frombytes(frames)
        if sys.byteorder != 'little':
            checked.byteswap()
        if checked[prefix_samples:prefix_samples + right - left] != pcm[left:right]:
            raise ValueError('Re-decode view differs from the corresponding source PCM')
    samples = decoder.decode(path)
    relative = observations([vars(phone) for phone in samples], len(copied) / rate)
    offset = (left - prefix_samples) / rate
    real_start, real_end = prefix_samples / rate, (prefix_samples + right - left) / rate
    return [
        {**row, **{key: row[key] + offset for key in ABSOLUTE_TIME_FIELDS}}
        for row in relative if real_start - 1e-7 <= row['start_s'] and row['end_s'] <= real_end + 1e-7
    ]


def view_bounds(slot, cached, addressed, sample_count, rate, preceding_s, following_s):
    if preceding_s is None:
        return 0, sample_count
    left = max((i for i in addressed if 0 < slot - i <= MAX_FLANK_DISTANCE), default=None)
    right = min((i for i in addressed if 0 < i - slot <= MAX_FLANK_DISTANCE), default=None)
    start_s = cached[addressed[left][0]]['start_s'] if left is not None else 0
    end_s = cached[addressed[right][0]]['end_s'] if right is not None else sample_count / rate
    return max(0, round((start_s - preceding_s) * rate)), min(sample_count, round((end_s + following_s) * rate))


def consensus(attempts):
    accepted = [attempt for attempt in attempts if 'observation' in attempt]
    if len(accepted) < 2:
        return None, 'insufficient_anchored_views'
    rows = [attempt['observation'] for attempt in accepted]
    for index, row in enumerate(rows):
        for other in rows[index + 1:]:
            if row['decoder']['final'] != other['decoder']['final']:
                return None, 'conflicting_final_labels'
            shorter = min(row['final_end_s'] - row['final_start_s'],
                          other['final_end_s'] - other['final_start_s'])
            if (final_overlap(row, other) < 0.60 * shorter
                    or any(abs(row[key] - other[key]) > MAX_BOUNDARY_DIFFERENCE_S
                           for key in ('final_start_s', 'final_end_s'))):
                return None, 'conflicting_final_intervals'
    # Keep one actual decoder observation, including its onset and tone, rather
    # than writing an artificial average or using the prescribed final.
    return max(rows, key=lambda row: row['final_confidence']), 'redecode_consensus'


def verify_sources(root, report):
    required = {MANIFEST, ALIGNMENTS, PHONE_DRAFTS}
    if not required <= report['source_sha256'].keys():
        raise ValueError('Strict recovery report is missing waveform-decode lineage')
    for relative, checksum in report['source_sha256'].items():
        if relative not in required | {SYLLABLES}:
            raise ValueError('Unexpected input in strict recovery provenance')
        if digest(root / relative) != checksum:
            raise ValueError(f'Strict recovery input changed: {relative}')


def redecode_take(decoder, folder, root, take, member, draft, events):
    slots = {name: take[name]['slot_index'] for name in ('target', 'anchor')}
    for name in slots:
        take[name]['strict_after'] = take[name]['after']
    unresolved = [name for name in slots if take[name]['after'] is None]
    if not unresolved:
        return
    if any(take[key] != member[key] or draft[key] != member[key] for key in ('audio_path', 'audio_sha256')):
        raise ValueError('Rhyme re-decode source waveform does not match strict recovery')
    if draft['model_revision'] != MODEL_REVISION or draft['passage_id'] != member['passage_id']:
        raise ValueError('Rhyme re-decode source decoder revision or witness differs')
    rate, pcm = read_clip(root, member, member['sample_rate'])
    cached = observations(draft['phones'], len(pcm) / rate)
    expected_segments = [sound_key(reading)[:2] for reading in member['intended_pinyin']]
    addressed = link_evidence(events, cached, len(expected_segments))
    endpoints = set(slots.values())
    views = {}
    for name in unresolved:
        index = slots[name]
        attempts = []
        for label, preceding_s, following_s, prefix, suffix in VIEW_CONFIG:
            left, right = view_bounds(index, cached, addressed, len(pcm), rate, preceding_s, following_s)
            key = (left, right, prefix, suffix)
            if key not in views:
                observed = decode_view(decoder, folder, pcm, rate, left, right, prefix, suffix)
                context = register_unchanged(observed, cached, addressed, expected_segments, endpoints)
                views[key] = observed, context
            observed, context = views[key]
            candidate, method = recover(index, context, observed, expected_segments, endpoints,
                                        occupied=context.values())
            attempt = {'view': label, 'source_sample_range': [left, right], 'method': method,
                       'trusted_unchanged_slots': len(context)}
            if candidate is not None:
                raw_index, left_slot, right_slot = candidate
                attempt.update(observation=observed[raw_index], flank_slots=[left_slot, right_slot])
            attempts.append(attempt)
        observation, status = consensus(attempts)
        take[name]['redecode'] = {'status': status, 'attempts': attempts}
        if observation is not None:
            take[name].update(after=observation, method=status, flank_slots=None)

    # An independently measured final cannot be assigned to two endpoints.
    a, b = (take[name]['after'] for name in ('target', 'anchor'))
    if a is not None and b is not None and final_overlap(a, b) > 1e-7:
        for name in unresolved:
            if take[name]['after'] is not None:
                take[name]['redecode']['status'] = 'competing_endpoint'
                take[name].update(after=None, method='competing_endpoint')


def run(root, recovery, output):
    report = json.loads(recovery.read_text(encoding='utf-8'))
    verify_sources(root, report)
    previous = report['summary']
    manifests = {row['recording_id']: row for row in read_jsonl(root / MANIFEST)}
    drafts = {row['recording_id']: row for row in read_jsonl(root / PHONE_DRAFTS)}
    alignments = defaultdict(list)
    for row in read_jsonl(root / ALIGNMENTS):
        alignments[row['recording_id']].append(row)
    decoder = MandarinDecoder(root, offline=True)
    with TemporaryDirectory(dir=root, prefix='rhyme-redecode-') as work:
        folder = Path(work)
        for comparison in report['comparisons']:
            take_rows = comparison['takes']
            comparison['strict_after'] = comparison['after']
            for take in take_rows.values():
                recording = take['recording_id']
                redecode_take(decoder, folder, root, take, manifests[recording], drafts[recording],
                              alignments[recording])
            heard = {role: recurrence(take, 'after') for role, take in take_rows.items()}
            left, right = (take_rows[role]['target']['after'] for role in ('base', 'rhyme'))
            comparison['after'] = {
                'recurrence': heard,
                'transition': transition(heard['base'], heard['rhyme']),
                'target_final_duration_delta_ms': right['final_duration_ms'] - left['final_duration_ms']
                if left is not None and right is not None else None,
            }
    summary = summarize(report['comparisons'])
    summary['strict_after'] = previous['after']
    summary['redecoded_endpoints'] = dict(Counter(
        endpoint['redecode']['status']
        for row in report['comparisons'] for take in row['takes'].values()
        for endpoint in (take['target'], take['anchor']) if 'redecode' in endpoint
    ))
    report.update(summary=summary, strict_recovery_sha256=digest(recovery), redecode_model_revision=MODEL_REVISION,
                  redecode_method='context-window stability check on one waveform decoder, two or more agreeing views')
    write_json(output, report)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--recovery', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.recovery.resolve() == args.output.resolve():
        parser.error('Keep the strict recovery report intact and use a new output path')
    os.umask(0o077)
    print(json.dumps(run(args.root.resolve(strict=True), args.recovery, args.output), allow_nan=False))


if __name__ == '__main__':
    main()
