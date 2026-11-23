"""Revisit the stable quiet intervals on the exact original two-voice WAVs."""

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path

from src.quantitative_alignment_audit import validated_slots
from src.quantitative_pause_match import MATCH_SETTINGS, MAX_RESUME_ERROR_MS, match_pause, worst_edge_error
from src.quantitative_report import FILES, VOICES, check_inventory, index
from src.quantitative_waveform_reference import WAVEFORM_REFERENCE_SETTINGS, waveform_reference
from src.stage6_listening import digest, read_clip, read_json, read_rows, write_json
from src.stage7_cli import write_output


RESULTS = Path('results/quantitative-report')


def char_context(passage, right):
    slots = passage['slots']
    return {'left_char': slots[right - 1]['char'], 'right_char': slots[right]['char'],
            'surface': ''.join(slot['char'] + slot['marks_after']
                               for slot in slots[max(0, right - 3):right + 3]),
            'marks_after_left': slots[right - 1]['marks_after']}


def check_pause(passage, pause, funasr, linked):
    slots = passage['slots']
    breaks = {right['slot_index'] for left, right in zip(slots, slots[1:])
              if left['clause_index'] != right['clause_index']}
    funasr_match, ch = [match_pause(pause, {number: 1000 * row['start_s'] for number, row in model.items()}, breaks)
                        for model in (funasr, linked)]
    right = funasr_match['right_slot']
    result = {'funasr': funasr_match, 'charsiu': ch, 'context': None,
              'phone_flanks_status': 'no_unique_funasr_slot', 'phone_left_end_error_ms': None}
    if right is None:
        return result
    result['context'] = char_context(passage, right)
    left, next_slot = linked.get(right - 1), linked.get(right)
    if left is None or next_slot is None:
        return {**result, 'phone_flanks_status': 'missing_phone_link'}
    onset_error = worst_edge_error(1000 * left['end_s'], pause['start_range_ms'])
    if ch['right_slot'] != right:
        status = 'phone_match_differs_or_abstains'
    elif next_slot['event_index'] != left['event_index'] + 1:
        status = 'intervening_acoustic_event'
    elif onset_error > MAX_RESUME_ERROR_MS:
        status = 'phone_end_far_from_quiet_start'
    else:
        status = 'corroborated'
    return {**result, 'phone_flanks_status': status, 'phone_left_end_error_ms': onset_error}


def summarize(recordings):
    counts = {}
    paired = defaultdict(set)
    for voice in VOICES:
        listed = [row for row in recordings if row['voice'] == voice]
        pauses = [pause for row in listed for pause in row['checked_pauses']]
        counts[voice] = {'recordings': len(listed), 'stable_pauses': len(pauses),
                         'funasr_statuses': dict(Counter(pause['funasr']['status'] for pause in pauses)),
                         'corroborated_statuses': dict(Counter(pause['funasr']['status'] for pause in pauses
                                                              if pause['phone_flanks_status'] == 'corroborated'))}
        for row in listed:
            for pause in row['checked_pauses']:
                if pause['funasr']['status'] == 'clause_boundary':
                    key = row['passage_id'], pause['funasr']['right_slot']
                    paired[key].add(voice)
    return {'by_voice': counts, 'shared_clause_candidates': [[pid, right] for (pid, right), voices in sorted(paired.items())
                                                           if voices == set(VOICES)]}


def analyze(root):
    paths = {key: root / FILES[key] for key in ('passages', 'takes', 'syllables')}
    paths.update({key: root / RESULTS / filename for key, filename in
                  (('v4', 'report-v4.json'), ('secondary', 'secondary-alignment.json'),
                   ('generator', 'internal-pause-check.json'))})
    hashes = {key: digest(path) for key, path in paths.items()}
    v4, second, prior = (read_json(paths[key]) for key in ('v4', 'secondary', 'generator'))
    if (any(v4['source_sha256'][key] != hashes[key] for key in ('passages', 'takes', 'syllables'))
            or v4['secondary_alignment']['alignment_sha256'] != hashes['secondary']
            or any(prior['source_sha256'][name] != hashes[key] for name, key in
                   (('v4', 'v4'), ('secondary_alignment', 'secondary'), ('passages', 'passages'), ('takes', 'takes')))
            or prior['summary']['stable_pcm_pauses'] != 13 or prior['summary']['labeled_pauses'] != 0
            or json.loads(json.dumps(WAVEFORM_REFERENCE_SETTINGS)) != v4['waveform_offset']['waveform_settings']):
        raise ValueError('Expected the original v4 take, waveform and unresolved interval inventories')
    passages = index(read_rows(paths['passages']), lambda row: row['passage_id'])
    check_inventory(passages)
    takes = index(read_rows(paths['takes']), lambda row: row['recording_id'])
    intervals = index(second['takes'], lambda row: row['recording_id'])
    v4_wavs = index(v4['waveform_offset']['waveforms'], lambda row: row['recording_id'])
    generator_wavs = index(prior['recordings'], lambda row: row['recording_id'])
    expected = {(pid, voice) for pid in passages for voice in VOICES}
    take_keys = {(take['passage_id'], take['speaker']) for take in takes.values()}
    if (len(passages) != 8 or len(takes) != len(expected) or take_keys != expected
            or not takes.keys() == intervals.keys() == v4_wavs.keys() == generator_wavs.keys()):
        raise ValueError('Expected eight original works covered by the same two voices')
    events = defaultdict(list)
    for row in read_rows(paths['syllables']):
        take = takes[row['recording_id']]
        if any(row[key] != take[key] for key in ('recording_id', 'audio_sha256', 'passage_id')):
            raise ValueError('Phone observations differ from the verified originals')
        events[row['recording_id']].append(row)
    output = []
    for rid, take in takes.items():
        passage = passages[take['passage_id']]
        rate, pcm = read_clip(root, take, take['sample_rate'])
        reference = waveform_reference(pcm, rate)
        before = v4_wavs[rid]
        if (any(reference[key] != before[key] for key in reference)
                or before['audio_sha256'] != take['audio_sha256']
                or generator_wavs[rid]['stable_pcm_pauses'] != len(reference['pauses'])):
            raise ValueError(f'{rid}: remeasured PCM edges differ from the original interval inventory')
        funasr = validated_slots(intervals[rid], passage, take, 1000 * len(pcm) / rate)
        linked = index([event for event in events[rid] if event['duration_ms'] is not None],
                       lambda row: row['slot_index'])
        checked = [{**pause, **check_pause(passage, pause, funasr, linked)} for pause in reference['pauses']]
        output.append({'recording_id': rid, 'audio_sha256': take['audio_sha256'], 'passage_id': take['passage_id'],
                       'work_id': passage['work_id'], 'title': passage['title'], 'voice': take['speaker'],
                       'checked_pauses': checked})
    if sum(len(row['checked_pauses']) for row in output) != 13:
        raise ValueError('Expected to revisit every one of the 13 original intervals')
    if hashes != {key: digest(path) for key, path in paths.items()}:
        raise ValueError('One of the archived evidence files changed during remeasurement')
    return {'source_sha256': hashes, 'settings': MATCH_SETTINGS, 'waveform_settings': WAVEFORM_REFERENCE_SETTINGS,
            **summarize(output), 'recordings': output,
            '音律美': {'evidence': 'waveform-based timing with draft text correspondences'},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None}}


def render(result):
    lines = ['# Original recordings and the 13 quiet intervals', '',
             'Every interval was remeasured on the original checksummed audio. The matching rule tests all adjacent '
             'Han positions before using their punctuation. It compares the waveform resume edge to the unshifted '
             'FunASR start and requires a clear nearest match. Charsiu corroboration requires the same position, '
             'adjacent decoded phone events, and agreement at the quiet interval’s other edge.', '',
             '| Passage | Voice | Quiet interval (ms) | FunASR position | Adjacent text | Charsiu check |',
             '| --- | --- | --- | --- | --- | --- |']
    status_labels = {'clause_boundary': 'Written clause break', 'within_clause': 'Within a clause',
                     'ambiguous': 'Ambiguous', 'unmatched': 'Unmatched'}
    for row in result['recordings']:
        for pause in row['checked_pauses']:
            context = pause['context']['surface'] if pause['context'] else ''
            lines.append(f"| {row['title']} ({row['passage_id']}) | {row['voice']} | "
                         f"{pause['start_ms']:.0f}–{pause['end_ms']:.0f} | "
                         f"{status_labels[pause['funasr']['status']]} | {context} | "
                         f"{pause['phone_flanks_status'].replace('_', ' ')} |")
    lines += ['', 'Waveform edges describe low-energy intervals. The text correspondences remain alignment drafts.',
              'These are 音律美 timing diagnostics. 顺口 requires independent first-read data.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--markdown', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve(strict=True)
    paths = [args.output] + ([args.markdown] if args.markdown else [])
    if (args.output.suffix != '.json' or (args.markdown and args.markdown.suffix != '.md')
            or any(path.resolve().parent != root / RESULTS or path.exists() or path.is_symlink() for path in paths)):
        parser.error('Choose new report files in the private quantitative results')
    result = analyze(root)
    if args.markdown:
        write_output(args.markdown, render(result))
    write_json(args.output, result)
    print(json.dumps(result['by_voice'], ensure_ascii=False))


if __name__ == '__main__':
    main()
