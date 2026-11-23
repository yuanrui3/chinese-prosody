"""Test clause-boundary assignment at sample-known joins of held-out works."""

import argparse
from collections import Counter
from importlib.metadata import version
import json
from math import isfinite
import os
from pathlib import Path

from audio.synthesize import SAMPLE_RATE
from src.quantitative_join_control import (
    EXPERIMENT as JOIN_EXPERIMENT, GAP_MS, OBSERVATIONS, TRANSFER, checked_donor, compose_pcm,
)
from src.quantitative_onset_collect import HISTORICAL, TRAINING, verify_inventory, verify_takes
from src.quantitative_onset_transfer import WAVEFORM_SETTINGS, freeze, paired_inputs
from src.quantitative_pause_match import MATCH_SETTINGS, match_pause
from src.quantitative_report import FILES, VOICES, check_inventory, index
from src.quantitative_waveform_reference import waveform_reference
from src.recitation_second_aligner import FRAME_MS, MandarinTimestampPredictor, map_intervals
from src.stage6_listening import digest, read_json, write_json
from src.stage7_cli import write_output


JOIN_REPORT = JOIN_EXPERIMENT / 'results/join-control/report.json'


def guard_pause(reference, guard_start, guard_stop):
    """Choose only a stable PCM quiet interval covering the sample-defined guard."""
    frame = round(SAMPLE_RATE * WAVEFORM_SETTINGS['frame_ms'] / 1000)
    pauses = [pause for pause in reference['pauses']
              if pause['start_sample'] <= guard_start + frame and pause['end_sample'] >= guard_stop - frame]
    if len(pauses) > 1:
        raise ValueError('Multiple disjoint quiet intervals cannot cover the same guard')
    return pauses[0] if pauses else None


def anchored_edges(right_reference, guard_start, guard_stop):
    """Provide a known splice and a PCM-only resumption window to isolate assignment."""
    observed = right_reference['speech_start_range_ms']
    if observed is None:
        return None
    left_ms, right_ms = (1000 * sample / SAMPLE_RATE for sample in (guard_start, guard_stop))
    return {'start_range_ms': [left_ms, left_ms], 'end_range_ms': [right_ms + edge for edge in observed]}


def clause_breaks(slots):
    return {i for i, (a, b) in enumerate(zip(slots, slots[1:]), 1)
            if a['clause_index'] != b['clause_index']}


def align(model, pcm, characters):
    try:
        times = model.timestamps(pcm, SAMPLE_RATE, characters)
    except AssertionError:
        return {}, 'timestamp_prediction_rejected'
    if not all(isfinite(value) for interval in times for value in interval):
        return {}, 'nonfinite_timestamp'
    rows, status = map_intervals(times, characters, len(pcm) * 1000 / SAMPLE_RATE)
    return {row['slot_index']: round(row['start_s'] * 1000, 9) for row in rows}, status


def score_case(pause, starts, breaks, expected):
    if pause is None or not starts:
        return {'positive': None, 'masked': None, 'outcome': 'undetected' if pause is None else 'unaligned'}
    positive = match_pause(pause, starts, breaks)
    masked = match_pause(pause, starts, breaks - {expected})
    if positive['right_slot'] is None:
        outcome = 'abstained'
    elif positive['status'] == 'clause_boundary' and positive['right_slot'] == expected:
        outcome = 'correct'
    else:
        outcome = ('wrong_clause' if positive['status'] == 'clause_boundary' else 'wrong_within_clause')
    return {'positive': positive, 'masked': masked, 'outcome': outcome}


def evaluate(model, archived, left, right, left_slots, right_slots):
    pcm, guard_stop, checksum = compose_pcm(left['pcm'], right['pcm'], SAMPLE_RATE)
    guard_start = len(left['pcm'])
    expected = len(left_slots)
    if (archived['composite_pcm16le_sha256'] != checksum
            or archived['left_recording_id'] != left['observed']['recording_id']
            or archived['right_recording_id'] != right['observed']['recording_id']
            or archived['left_audio_sha256'] != left['observed']['audio_sha256']
            or archived['right_audio_sha256'] != right['observed']['audio_sha256']
            or archived['left_sample_count'] != guard_start or archived['right_sample_count'] != len(right['pcm'])
            or archived['right_start_sample'] != guard_stop or archived['right_slot_index'] != expected
            or archived['sample_rate_hz'] != SAMPLE_RATE or guard_stop - guard_start != GAP_MS * SAMPLE_RATE // 1000):
        raise ValueError('The checked PCM splice no longer matches the archived held-out trial')
    reference = waveform_reference(pcm, SAMPLE_RATE)
    pause = guard_pause(reference, guard_start, guard_stop)
    starts, status = align(model, pcm, left['characters'] + right['characters'])
    breaks = clause_breaks(left_slots) | {expected} | {expected + i for i in clause_breaks(right_slots)}
    known_edges = anchored_edges(right['reference'], guard_start, guard_stop)
    return {
        **{field: archived[field] for field in ('pair_id', 'work_id', 'passage_id', 'voice', 'period', 'genre',
                                                'left_recording_id', 'right_recording_id')},
        'composite_pcm16le_sha256': checksum,
        'guard_samples': [guard_start, guard_stop],
        'expected_right_slot': expected,
        'clause_breaks': sorted(breaks),
        'alignment_status': status,
        'archived_right_start_reproduced': starts.get(expected) == archived['model_start_ms'],
        'other_stable_intervals': len(reference['pauses']) - int(pause is not None),
        'quiet_candidate_rejections': reference['quiet_candidate_rejections'],
        'observed_guard_interval': pause,
        'known_guard_and_resume': {'observed_guard_interval': known_edges,
                                   **score_case(known_edges, starts, breaks, expected)},
        **score_case(pause, starts, breaks, expected),
    }


def evaluate_native(model, donor, slots):
    starts, status = align(model, donor['pcm'], donor['characters'])
    breaks = clause_breaks(slots)
    observations = [{**pause, 'assignment': match_pause(pause, starts, breaks)}
                    for pause in donor['reference']['pauses']]
    return {
        **{key: donor['observed'][key] for key in ('work_id', 'passage_id', 'voice', 'recording_id', 'audio_sha256')},
        'alignment_status': status,
        'archived_first_start_reproduced': starts.get(0) == donor['observed']['model_start_ms'],
        'stable_pauses': len(observations),
        'observations': observations,
    }


def summarize_native(rows):
    by_voice = {}
    targets = {}
    for voice in VOICES:
        takes = [row for row in rows if row['voice'] == voice]
        statuses = Counter()
        labeled = set()
        for take in takes:
            for pause in take['observations']:
                result = pause['assignment']
                statuses[result['status']] += 1
                if result['status'] == 'clause_boundary':
                    labeled.add((take['work_id'], result['right_slot']))
        targets[voice] = labeled
        by_voice[voice] = {'takes': len(takes), 'aligned_takes': sum(row['alignment_status'] == 'aligned'
                                                                  for row in takes),
                           'stable_pauses': sum(row['stable_pauses'] for row in takes),
                           'assignments': {status: statuses[status] for status in
                                           ('clause_boundary', 'within_clause', 'ambiguous', 'unmatched')},
                           'distinct_clause_boundaries_assigned': len(labeled)}
    shared = set.intersection(*(targets[voice] for voice in VOICES))
    return {'by_voice': by_voice, 'shared_assigned_positions': [
        {'work_id': work, 'right_slot': slot} for work, slot in sorted(shared)]}


def summarize_voice(rows):
    masks = [row['masked'] for row in rows if row['masked'] is not None]
    counts = Counter(row['outcome'] for row in rows)
    return {'trials': len(rows), 'observed_pauses': sum(row['observed_guard_interval'] is not None for row in rows),
            'detected_and_aligned': len(masks), 'outcomes': {
                key: counts[key] for key in ('correct', 'wrong_clause', 'wrong_within_clause',
                                             'abstained', 'undetected', 'unaligned')},
            'false_clause_labels_with_true_break_masked': sum(row['status'] == 'clause_boundary' for row in masks),
            'retained_true_position_as_within_clause': sum(
                row['masked']['status'] == 'within_clause' and row['masked']['right_slot'] == row['expected_right_slot']
                for row in rows if row['masked'] is not None)}


def summarize(rows):
    by_work = {}
    for row in rows:
        paired = by_work.setdefault(row['work_id'], {})
        if row['voice'] in paired:
            raise ValueError('More than one controlled join for the same target work and voice')
        paired[row['voice']] = row
    if any(set(voices) != set(VOICES) for voices in by_work.values()):
        raise ValueError('Expected the same controlled works in both voices')
    shared = sorted(work for work, pair in by_work.items() if all(row['masked'] is not None for row in pair.values()))
    agree = sorted(work for work in shared if all(row['outcome'] == 'correct' for row in by_work[work].values()))
    return {'works': len(by_work),
            'by_voice': {voice: summarize_voice([row[voice] for row in by_work.values()]) for voice in VOICES},
            'shared_detected_and_aligned_works': shared, 'shared_correctly_labeled_works': agree}


def run(project, cache):
    corpus = project / TRANSFER
    inputs = {'training': project / TRAINING, 'observations': corpus / OBSERVATIONS,
              'annotations': corpus / FILES['passages'], 'manifest': corpus / FILES['takes'],
              'historical_manifest': project / HISTORICAL / FILES['takes'], 'join_archive': project / JOIN_REPORT}
    hashes = {name: digest(path) for name, path in inputs.items()}
    archived = read_json(inputs['join_archive'])
    training = freeze(read_json(inputs['training']))
    if (archived['source_sha256'] != {key: value for key, value in hashes.items() if key != 'join_archive'}
            or archived['inserted_silence_ms'] != GAP_MS
            or archived['waveform_settings'] != WAVEFORM_SETTINGS or archived['model'] != training['model']
            or archived['model_frame_ms'] != FRAME_MS or version('funasr') != training['model']['funasr_version']):
        raise ValueError('The controlled join archive differs from the pinned inputs or timing model')
    observed = paired_inputs(read_json(inputs['observations']), training, hashes['training'])
    passages = verify_inventory(project, corpus)
    takes, _ = verify_takes(project, corpus, passages)
    controls = index(archived['rows'], lambda row: (row['work_id'], row['voice']))
    if (set(observed) != {row['work_id'] for row in passages.values()}
            or controls.keys() != {(work, voice) for work in observed for voice in VOICES}
            or archived['composites'] != len(controls)):
        raise ValueError('Expected all held-out works in both voices')

    model = MandarinTimestampPredictor(cache)
    rows, native = [], []
    for pair in check_inventory(passages).values():
        for voice in VOICES:
            donors = [checked_donor(corpus, row, takes[row['passage_id'], voice],
                                    observed[row['work_id']][voice]) for row in pair]
            native.extend(evaluate_native(model, donor, item['slots']) for donor, item in zip(donors, pair))
            for left, right in ((0, 1), (1, 0)):
                target = controls[pair[right]['work_id'], voice]
                rows.append(evaluate(model, target, donors[left], donors[right],
                                     pair[left]['slots'], pair[right]['slots']))
    if hashes != {name: digest(path) for name, path in inputs.items()}:
        raise ValueError('A source manifest or alignment report changed during the benchmark')
    return {'schema_version': 1, 'source_sha256': hashes, 'model': training['model'],
            'waveform_settings': WAVEFORM_SETTINGS, 'match_settings': MATCH_SETTINGS, 'inserted_silence_ms': GAP_MS,
            'training_works': sorted(training['training_works']),
            'interpretation': 'Held-out controlled joins in the same synthesizer. Accuracy applies to '
                              'the sample-known join and its masked-label challenge.',
            '音律美': {'evidence': 'controlled clause-boundary timing diagnostic'},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None},
            'summary': summarize(rows), 'rows': rows,
            'known_guard_and_resume_summary': summarize([{**row, **row['known_guard_and_resume']} for row in rows]),
            'native_transfer': {'summary': summarize_native(native), 'rows': native}}


def render_comparison(totals, observed_label):
    lines = [f'| Voice | Trials | {observed_label} | Available with alignment | Correct label | Other clause '
             '| Wrong within clause | Abstained with alignment | False clause label with true break masked |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for voice, row in totals['by_voice'].items():
        values = [row['trials'], row['observed_pauses'], row['detected_and_aligned']]
        values.extend(row['outcomes'][key] for key in ('correct', 'wrong_clause', 'wrong_within_clause', 'abstained'))
        values.append(row['false_clause_labels_with_true_break_masked'])
        lines.append(f"| {voice} | " + ' | '.join(map(str, values)) + ' |')
    lines.extend(['', f"Both voices had waveform evidence and an alignment for "
                  f"{len(totals['shared_detected_and_aligned_works'])} of {totals['works']} joins. "
                  f"Both assigned the exact boundary in "
                  f"{len(totals['shared_correctly_labeled_works'])} of those jointly measurable works.", '',
                  ])
    return lines


def render(result):
    totals = result['summary']
    lines = ['# Held-out clause-boundary assignment at controlled joins', '',
             f"The benchmark replayed both orders of the matched pairs in two Kokoro voices across "
             f"{totals['works']} held-out target works. Each join is defined by the exact donor sample "
             f"coordinates and a {result['inserted_silence_ms']} ms zero guard.", '',
             '## Full pause detection and assignment', '']
    lines.extend(render_comparison(totals, 'Stable guard detected'))
    lines.extend(['## Assignment with the known splice and waveform resumption', '',
                  'To isolate assignment, the same matcher uses the sample-defined start of the zero guard and the '
                  'right donor’s stable waveform onset translated by the exact placement. It still has to choose '
                  'the correct written position among all adjacent Han starts. This conditional check bypasses '
                  'the automatic quiet-run detector.', ''])
    lines.extend(render_comparison(result['known_guard_and_resume_summary'], 'Stable donor resume'))
    lines.extend([
                  'The masked challenge removes the true break from the written boundary list while keeping the PCM '
                  'and candidate timestamps fixed. Other quiet intervals have unresolved identities. This verifies '
                  'timing at synthetic joins.', '',
                  '## Native transfer coverage', '',
                  'The same matcher ran on the original held-out donor WAVs. These counts measure coverage. '
                  'Native clause identity requires independent labels.', '',
                  '| Voice | Original WAVs | Stable pauses | Clause labels | Within clause | Ambiguous | Unmatched |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: |'])
    native = result['native_transfer']['summary']
    for voice, item in native['by_voice'].items():
        values = [item['takes'], item['stable_pauses'], *item['assignments'].values()]
        lines.append(f"| {voice} | " + ' | '.join(map(str, values)) + ' |')
    lines.extend(['', f"The two voices assigned {len(native['shared_assigned_positions'])} of the same clause "
                  'positions. Agreement between voices is a consistency check.', '',
                  '音律美 timing diagnostics and 顺口 first-read evidence remain separate.', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--markdown', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    project, cache = [path.resolve(strict=True) for path in (args.project, args.model_cache)]
    output, markdown = args.output.resolve(), args.markdown.resolve() if args.markdown else None
    destinations = [output] + ([markdown] if markdown else [])
    if (not cache.is_relative_to(project) or len(set(destinations)) != len(destinations)
            or any(path.exists() or not path.is_relative_to(project) for path in destinations)):
        parser.error('Expected the cached model and new distinct result files under the Gilbreth project')
    report = run(project, cache)
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
    if markdown:
        write_output(markdown, render(report))
    write_json(output, report)
    print(json.dumps({'controlled': report['summary'], 'known_guard_and_resume': report['known_guard_and_resume_summary'],
                      'native_transfer': report['native_transfer']['summary']},
                     ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
