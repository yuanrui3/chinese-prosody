"""Measure independent waveform pause and syllable evidence at fixed text junctions."""

import argparse
from collections import Counter
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from statistics import median

from audio.align import MODEL_REVISION, VOCAB_REVISION, MandarinDecoder, heard_syllables, link_slots
from src.quantitative_native_pause_eval import read_wav
from src.quantitative_noise_aware_detector import detect_noise_aware
from src.quantitative_pause_match import MATCH_SETTINGS, match_pause


HAN = re.compile(r'[\u3400-\u9fff\U00020000-\U000323af]')
CONTEXT_RADIUS = 3
MIN_CONTEXT = 2
BRIDGE_MS = 20


@lru_cache(maxsize=None)
def readings(char):
    from pypinyin import Style, pinyin

    return [{'reading': item} for group in pinyin(char, style=Style.TONE3, heteronym=True,
                                                  neutral_tone_with_five=True, errors='ignore') for item in group]


def decode_slots(decoder, media, text, *, timing=None, rescue_mode=None):
    if rescue_mode == 'qwen_coarse':
        return {
            index: {'start_s': interval[0], 'end_s': interval[1],
                    'duration_s': interval[1] - interval[0], 'event': index, 'match_basis': 'qwen_coarse'}
            for index, interval in enumerate(timing)
            if interval is not None
        }, None
    slots = [{'slot_index': i, 'readings': {'mandarin': {'candidates': readings(char)}}}
             for i, char in enumerate(text)]
    phones = decoder.decode(media)
    links = link_slots(slots, heard_syllables(phones))
    if rescue_mode is not None:
        from src.quantitative_preboundary_link_rescue import rescue_links

        return rescue_links(text, links, timing, mode=rescue_mode, require_anchor_agreement=True)
    result = {}
    for event, (slot, syllable, status, basis) in enumerate(links):
        if status == 'matched':
            left, right = syllable.phones[0].start_s, syllable.phones[-1].end_s
            result[slot['slot_index']] = {'start_s': left, 'end_s': right, 'duration_s': right - left,
                                         'event': event, 'match_basis': basis}
    return result, None


def observed_pauses(samples, rate, aligned):
    detected = detect_noise_aware(samples, rate, bridge_weak_ms=BRIDGE_MS)
    starts = {i: 1000 * item['start_s'] for i, item in aligned.items()}
    observations = {}
    for pause in detected['pauses']:
        # The baseline searches all linked characters before consulting reference labels.
        assigned = match_pause(pause, starts, set())
        if (post := assigned['right_slot']) is not None:
            left, right = aligned[post - 1], aligned[post]
            if right['event'] == left['event'] + 1:
                duration = pause['end_ms'] - pause['start_ms']
                observations[post] = max(observations.get(post, 0), duration)
    return detected, observations


def junctions(record):
    positive = record.get('positive_ordinals', record.get('boundaries'))
    negative = record.get('negative_ordinals', record.get('controls'))
    if not positive or not negative or (set(positive) & set(negative)):
        raise ValueError(f"{record['id']}: expected distinct positive and negative text-only junctions")
    return sorted([(index, True) for index in positive] + [(index, False) for index in negative])


def extract(record, wave_root, decoder, *, draft=None, rescue_mode=None):
    text = ''.join(HAN.findall(record['transcript']))
    # Pass only the characters and pronunciation alternatives to the waveform decoder/linker.
    declared = record.get('characters')
    if declared is not None and text != ''.join(declared):
        raise ValueError(f"{record['id']}: the unpunctuated transcript differs from the declared characters")
    if not text or any(not 0 < index < len(text) for index, _ in junctions(record)):
        raise ValueError(f"{record['id']}: a junction lies outside the internal Han positions")
    path = (wave_root / record['path']).resolve(strict=True)
    if not path.is_relative_to(wave_root):
        raise ValueError('The original recording must stay inside the manifest directory')
    rate, samples, digest = read_wav(path, downmix=True)
    if digest != record['wav_sha256']:
        raise ValueError(f"{record['id']}: original WAV checksum differs from its pinned copy")
    if draft is not None and draft['characters'] != text:
        raise ValueError(f"{record['id']}: second alignment used different characters")
    timing = draft['intervals_s'] if draft else None
    aligned, rescue_audit = decode_slots(decoder, path, text, timing=timing, rescue_mode=rescue_mode)
    detector, pauses = observed_pauses(samples, rate, aligned)

    rows = []
    for ordinal, label in junctions(record):
        left, right = aligned.get(ordinal - 1), aligned.get(ordinal)
        pre_duration = context_duration = pause_ms = None
        consecutive = left is not None and right is not None and right['event'] == left['event'] + 1
        exclusion = None
        if consecutive:
            pre_duration = left['duration_s']
            local = [aligned[i]['duration_s'] for i in range(ordinal - 1 - CONTEXT_RADIUS,
                                                            ordinal + CONTEXT_RADIUS)
                     if i in aligned and i != ordinal - 1]
            if len(local) >= MIN_CONTEXT:
                context_duration = median(local)
            else:
                exclusion = 'insufficient_local_duration_context'
            if detector['status'] == 'ok':
                pause_ms = pauses.get(ordinal, 0)
            else:
                exclusion = 'pause_detector_unavailable'
        elif left is None or right is None:
            exclusion = 'both_unlinked' if left is None and right is None else (
                'left_unlinked' if left is None else 'right_unlinked')
        else:
            exclusion = 'nonconsecutive_heard_events'
        rows.append({'recording_id': record['recording_id'], 'speaker': record['speaker'], 'work': record['work'],
                     'genre': record.get('genre', 'modern_mandarin_ambiguity_control'), 'label': label,
                     'ordinal': ordinal, 'left_char': text[ordinal - 1], 'right_char': text[ordinal],
                     'pre_duration_s': pre_duration, 'context_duration_s': context_duration, 'pause_ms': pause_ms,
                     'exclusion': exclusion,
                     'qwen_identity_at_junction': any(item and item['match_basis'].startswith('qwen_rescue')
                                                     for item in (left, right))})
    info = {'recording_id': record['recording_id'], 'wav_sha256': digest, 'path': record['path'],
            'characters': text, 'aligned': aligned, 'detector_status': detector['status'],
            'detector_mode': detector['mode'], 'raw_pause_count': len(detector['pauses']),
            'assigned_pause_ms_by_ordinal': pauses, 'rescue_audit': rescue_audit}
    return rows, info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qwen-draft', type=Path, help='Project-local character identity intervals from Qwen')
    parser.add_argument('--rescue-mode', choices=('baseline', 'compatible', 'qwen_only', 'qwen_coarse'))
    args = parser.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):
        parser.error('Run waveform feature extraction on Gilbreth under Slurm')
    project = args.project.resolve(strict=True)
    manifest = args.manifest.resolve(strict=True)
    if not manifest.is_relative_to(project) or not args.output.resolve().is_relative_to(project):
        parser.error('Keep the corpus and scored output in the Gilbreth project')
    raw = manifest.read_bytes()
    records = json.loads(raw)['recordings']
    if not records or len({r['recording_id'] for r in records}) != len(records):
        raise ValueError('A unique, nonempty WAV manifest is required')
    draft = None
    if args.qwen_draft is not None:
        if not args.qwen_draft.resolve().is_relative_to(project):
            parser.error('Keep Qwen alignment drafts on Gilbreth')
        draft = json.loads(args.qwen_draft.read_text(encoding='utf-8'))
        if (draft['manifest_sha256'] != sha256(raw).hexdigest()
                or set(draft['recordings']) != {record['recording_id'] for record in records}):
            parser.error('The second-alignment draft belongs to a different recording manifest')
    if args.rescue_mode in ('compatible', 'qwen_only', 'qwen_coarse') and draft is None:
        parser.error('Qwen modes require a matched alignment draft')
    decoder = None if args.rescue_mode == 'qwen_coarse' else MandarinDecoder(project, offline=True)
    rows, info = [], []
    for record in records:
        candidate_draft = draft['recordings'][record['recording_id']] if draft else None
        candidates, decoded = extract(record, manifest.parent, decoder, draft=candidate_draft,
                                      rescue_mode=args.rescue_mode)
        rows.extend(candidates)
        info.append(decoded)
    output = {'manifest_sha256': sha256(raw).hexdigest(), 'charsiu_model_revision': MODEL_REVISION if decoder else None,
              'charsiu_vocabulary_revision': VOCAB_REVISION if decoder else None,
              'frame_s': decoder.step_s if decoder else draft['timestamp_grid_ms'] / 1000,
              'context_radius': CONTEXT_RADIUS, 'minimum_context': MIN_CONTEXT,
              'pause_settings': {**MATCH_SETTINGS, 'bridge_ms': BRIDGE_MS}, 'rows': rows, 'recordings': info,
              'rescue_mode': args.rescue_mode, 'qwen_model_revision': draft['qwen_model_revision'] if draft else None}
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(output, handle, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'recordings': len(info), 'junctions': len(rows),
                      'pause_observed': sum(row['pause_ms'] is not None and row['pause_ms'] > 0 for row in rows),
                      'detector_modes': dict(Counter(row['detector_mode'] for row in info)),
                      'exclusions': dict(Counter(row['exclusion'] for row in rows if row['exclusion'])),
                      'rescued_links': sum(row['rescue_audit']['accepted_rescues'] for row in info
                                           if row['rescue_audit'])}))


if __name__ == '__main__':
    main()
