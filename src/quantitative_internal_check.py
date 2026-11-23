"""Identify stable PCM pauses with independent Kokoro position drafts."""

import argparse
from collections import Counter, defaultdict
from itertools import accumulate
import json
from math import isclose
import os
from pathlib import Path

from audio.synthesize import PUNCTUATION, SAMPLE_RATE, SAMPLES_PER_DURATION_FRAME
from src.quantitative_alignment_audit import validated_slots
from src.quantitative_offset import compare, edge
from src.quantitative_report import FILES, VOICES, check_inventory, index
from src.quantitative_waveform_reference import waveform_reference
from src.stage6_listening import digest, read_clip, read_json, read_rows, write_json


RESULTS = Path('results/quantitative-report')
DURATIONS = Path('audio/derived/synthesis-durations.jsonl')
ORIGIN_OFFSETS_FRAMES = (-2, -1, 0)
PUNCTUATION_MARGIN_FRAMES = 1
TAKE_FIELDS = ('recording_id', 'passage_id', 'speaker', 'kind', 'variety', 'style', 'seed', 'speed',
               'sample_rate', 'text_sha256', 'text_revision', 'text_source_url', 'text_license',
               'model_revision', 'model_license', 'intended_pinyin', 'intended_model_phonemes')


def generator_windows(draft, passage, take, sample_count):
    fields = ('recording_id', 'text_sha256', 'audio_sha256', 'model_revision')
    slots = passage['slots']
    spans = draft['slot_spans_samples']
    frames = draft['token_frames']
    phones = take['intended_model_phonemes']
    frame = draft['frame_samples']
    if (any(draft[key] != take[key] for key in fields) or draft['sample_count'] != sample_count
            or frame != SAMPLES_PER_DURATION_FRAME or len(spans) != len(slots)
            or len(frames) != len(phones) + 2 or any(type(value) is not int or value < 1 for value in frames)):
        raise ValueError('Kokoro duration draft is inconsistent with the pinned take')
    edges = {position * frame: token - 1 for token, position in enumerate(accumulate(frames, initial=0))}
    if (abs(max(edges) - sample_count) >= frame
            or any(a not in edges or b not in edges or not 0 <= edges[a] < edges[b] <= len(phones)
                   for a, b in spans) or any(x[1] > y[0] for x, y in zip(spans, spans[1:]))):
        raise ValueError('Invalid generator-token sample coordinates')

    windows = []
    for left, right in zip(slots, slots[1:]):
        if left['clause_index'] == right['clause_index']:
            continue
        left_index = left['slot_index']
        start, stop = spans[left_index][1], spans[right['slot_index']][0]
        marks = left['marks_after']
        if not marks or phones[edges[start]:edges[stop]] != marks.translate(PUNCTUATION):
            raise ValueError('A generator gap does not correspond to the frozen punctuation')
        windows.append({'after_slot': left_index, 'start_sample': start, 'end_sample': stop,
                        'marks': marks, 'left_char': left['char'], 'right_char': right['char']})
    return windows


def label_pauses(reference, windows):
    """Use only energy-defined quiet runs and Kokoro's nominal coordinate range."""
    rate = reference['sample_rate']
    frame = SAMPLES_PER_DURATION_FRAME
    margin = PUNCTUATION_MARGIN_FRAMES * frame
    labels = []
    for pause in reference['pauses']:
        centers = [round((start + stop) * rate / 2000) for start, stop in
                   zip(pause['start_range_ms'], pause['end_range_ms'])]
        candidates = [[window['after_slot'] for window in windows
                       if window['start_sample'] + shift * frame - margin <= centers[0]
                       and centers[-1] <= window['end_sample'] + shift * frame + margin]
                      for shift in ORIGIN_OFFSETS_FRAMES]
        unique = len(candidates[0]) == 1 and all(group == candidates[0] for group in candidates)
        labels.append({**pause, 'candidates_by_origin': candidates,
                       'after_slot': candidates[0][0] if unique else None,
                       'status': 'labeled' if unique else 'ambiguous_origin_or_boundary'})

    if reference['internal_pause_count_matches']:
        for row, window in zip(labels, windows):
            if row['after_slot'] is not None and row['after_slot'] != window['after_slot']:
                row.update(after_slot=None, status='conflicts_with_v4_rank')
    counts = Counter(row['after_slot'] for row in labels if row['after_slot'] is not None)
    for row in labels:
        if counts[row['after_slot']] > 1:
            row.update(after_slot=None, status='competing_pcm_pauses')
    assigned = [row for row in labels if row['after_slot'] is not None]
    if any(x['after_slot'] > y['after_slot'] for x, y in zip(assigned, assigned[1:])):
        for row in assigned:
            row.update(after_slot=None, status='order_conflict')
    return labels


def pause_edges(ident, labels, linked, secondary):
    for row in labels:
        index = row['after_slot']
        if index is None:
            continue
        specs = (('pause_start', index, 'end_s', 'start'), ('pause_end', index + 1, 'start_s', 'end'))
        for kind, slot, timestamp, ref in specs:
            yield {**ident, 'kind': kind, 'after_slot': index, 'slot_index': slot,
                   'edge_ms': row[f'{ref}_ms'], 'reference_range_ms': row[f'{ref}_range_ms'],
                   'funasr_ms': edge(secondary.get(slot), timestamp), 'charsiu_ms': edge(linked.get(slot), timestamp)}


def analyze(root, regenerated):
    paths = {'passages': root / FILES['passages'], 'takes': root / FILES['takes'],
             'syllables': root / FILES['syllables'], 'v4': root / RESULTS / 'report-v4.json',
             'secondary_alignment': root / RESULTS / 'secondary-alignment.json',
             'regenerated_takes': regenerated / FILES['takes'], 'generator_durations': regenerated / DURATIONS}
    source_hashes = {name: digest(path) for name, path in paths.items()}
    v4 = read_json(paths['v4'])
    secondary_source = read_json(paths['secondary_alignment'])
    if (any(v4['source_sha256'][key] != source_hashes[key] for key in ('passages', 'takes', 'syllables'))
            or v4['secondary_alignment']['alignment_sha256'] != source_hashes['secondary_alignment']
            or secondary_source['passages_sha256'] != source_hashes['passages']
            or secondary_source['manifest_sha256'] != source_hashes['takes']):
        raise ValueError('Inputs do not match the v4 waveform audit')

    passages = index(read_rows(paths['passages']), lambda row: row['passage_id'])
    check_inventory(passages)
    takes, copies, drafts = [index(read_rows(paths[key]), lambda row: row['recording_id'])
                            for key in ('takes', 'regenerated_takes', 'generator_durations')]
    waveforms = index(v4['waveform_offset']['waveforms'], lambda row: row['recording_id'])
    secondary = index(secondary_source['takes'], lambda row: row['recording_id'])
    if (len(passages) != 8 or set(v4['conditions']['voice_ids']) != set(VOICES)
            or len(takes) != len(passages) * len(VOICES)
            or {(row['passage_id'], row['speaker']) for row in takes.values()}
            != {(pid, voice) for pid in passages for voice in VOICES}
            or not takes.keys() == copies.keys() == drafts.keys() == waveforms.keys() == secondary.keys()):
        raise ValueError('Expected the same eight works and two voices in all inputs')

    linked_by_take = defaultdict(dict)
    for row in read_rows(paths['syllables']):
        take = takes[row['recording_id']]
        if row['audio_sha256'] != take['audio_sha256'] or row['passage_id'] != take['passage_id']:
            raise ValueError('A Charsiu draft does not describe the pinned take')
        if row['duration_ms'] is not None:
            linked = linked_by_take[take['recording_id']]
            if row['slot_index'] in linked:
                raise ValueError('A Charsiu slot contains multiple timing drafts')
            linked[row['slot_index']] = row

    results, observations = [], []
    for recording_id, take in takes.items():
        passage = passages[take['passage_id']]
        reference, copy, draft = waveforms[recording_id], copies[recording_id], drafts[recording_id]
        if (any(take[key] != copy[key] for key in TAKE_FIELDS) or take['sample_rate'] != SAMPLE_RATE
                or take['text_sha256'] != passage['text_sha256'] or reference['audio_sha256'] != take['audio_sha256']
                or reference['voice'] != take['speaker'] or reference['passage_id'] != take['passage_id']
                or reference['work_id'] != passage['work_id']):
            raise ValueError('The regeneration or waveform audit altered recording provenance')
        ident = {field: reference[field] for field in ('recording_id', 'passage_id', 'work_id', 'voice',
                                                      'audio_sha256', 'clip_ms')}
        rate, pcm = read_clip(root, take, SAMPLE_RATE)
        duration_ms = 1000 * len(pcm) / rate
        regenerated_rate, regenerated_pcm = read_clip(regenerated, copy, SAMPLE_RATE)
        if (len(pcm) != reference['sample_count'] or not isclose(duration_ms, reference['clip_ms'])
                or not isclose(take['duration_s'], len(pcm) / rate)
                or not isclose(copy['duration_s'], len(regenerated_pcm) / regenerated_rate)):
            raise ValueError('Waveform duration or recorded sample count does not match the manifest')
        measured = waveform_reference(pcm, rate)
        if any(value != reference[key] for key, value in measured.items()):
            raise ValueError('Recomputed PCM edge inventory differs from v4')

        same_audio = (copy['audio_sha256'] == take['audio_sha256'] and regenerated_pcm == pcm)
        result = {**ident, 'regenerated_sha256': copy['audio_sha256'], 'verified_exact_wav': same_audio,
                  'v4_rank_eligible': reference['internal_pause_count_matches'], 'stable_pcm_pauses': len(reference['pauses'])}
        results.append(result)
        if not same_audio:
            result.update(status='regenerated_audio_differs', pauses=[])
            continue
        windows = generator_windows(draft, passage, take, len(pcm))
        if len(windows) != reference['expected_clause_breaks']:
            raise ValueError('Expected the same punctuation boundaries as the v4 audit')
        tags = label_pauses(reference, windows)
        model = validated_slots(secondary[recording_id], passage, take, duration_ms)
        result.update(status='checked', punctuation_windows=windows, pauses=tags)
        observations.extend(pause_edges(ident, tags, linked_by_take[recording_id], model))

    labels = {(row['passage_id'], pause['after_slot'], row['voice']) for row in results for pause in row['pauses']
              if pause['after_slot'] is not None}
    paired = {(pid, slot) for pid, slot, voice in labels if all((pid, slot, member) in labels for member in VOICES)}
    native_scores, folds = compare(observations, VOICES)
    paired_scores, paired_folds = compare([dict(row) for row in observations
                                           if (row['passage_id'], row['after_slot']) in paired], VOICES)
    summary = {'takes': len(results), 'verified_exact_wavs': sum(row['verified_exact_wav'] for row in results),
               'stable_pcm_pauses': sum(row['stable_pcm_pauses'] for row in results), 'labeled_pauses': len(labels),
               'labeled_pauses_beyond_v4_rank': sum(pause['after_slot'] is not None for row in results
                                                  for pause in row['pauses'] if not row['v4_rank_eligible']),
               'shared_labeled_breaks': len(paired), 'labeled_pauses_by_voice':
               {voice: sum(member == voice for _, _, member in labels) for voice in VOICES},
               'label_statuses': dict(Counter(pause['status'] for row in results for pause in row['pauses']))}
    return {'scope': 'Native PCM energy boundaries with Kokoro-assisted punctuation labels. These are quantitative '
                     'timing diagnostics for 音律美, independent of the two tested aligners for label assignment. '
                     'The comparison does not score pronunciation or 顺口 and does not change report-v4 coverage.',
            'label_settings': {'nominal_origin_ms': -25, 'origin_sensitivity_frames': ORIGIN_OFFSETS_FRAMES,
                               'punctuation_margin_frames': PUNCTUATION_MARGIN_FRAMES},
            'source_sha256': source_hashes, 'summary': summary, 'recordings': results, 'edges': observations,
            'metrics_by_voice': native_scores, 'held_out_shifts': folds,
            'paired_label_metrics_by_voice': paired_scores, 'paired_label_held_out_shifts': paired_folds}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--regenerated', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve(strict=True)
    regenerated = args.regenerated.resolve(strict=True)
    output = args.output.resolve()
    if (root == regenerated or not output.is_relative_to(root / RESULTS)
            or output.suffix != '.json' or output.exists()):
        parser.error('Use an isolated regeneration and a new JSON path in the private quantitative results')
    result = analyze(root, regenerated)
    write_json(output, result)
    print(json.dumps(result['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
