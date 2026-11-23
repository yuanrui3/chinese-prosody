"""Compare frozen pause detectors and clause assignment on independent waveform joins."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path

from audio.synthesize import SAMPLE_RATE
from src.quantitative_join_control import compose_pcm
from src.quantitative_pause_benchmark import align, anchored_edges, clause_breaks, guard_pause, score_case
from src.quantitative_pause_detector import RELATIVE_PAUSE_SETTINGS, detect_relative
from src.quantitative_pause_detector_controls import load_cohort
from src.quantitative_pause_match import MATCH_SETTINGS, match_pause
from src.quantitative_report import check_inventory
from src.quantitative_waveform_reference import WAVEFORM_REFERENCE_SETTINGS, waveform_reference
from src.recitation_second_aligner import MODEL, REVISION, WEIGHTS_SHA256, MandarinTimestampPredictor
from src.stage6_listening import digest, read_clip, write_json
from src.stage7_cli import write_output


GAPS_MS = (150, 250, 400)
DETECTORS = {'fixed': waveform_reference, 'relative': detect_relative}


def available(method, pause):
    return pause is not None and (method == 'fixed' or pause['resumption_eligible'])


def assignment(method, pause, starts, breaks, expected):
    scored = score_case(pause if available(method, pause) else None, starts, breaks, expected)
    if pause is not None and not available(method, pause):
        scored['outcome'] = 'uncertain_resume'
    return {'guard_interval': pause, 'resume_usable': available(method, pause), **scored}


def time_case(model, left, right, gap_ms):
    pcm, guard_stop, checksum = compose_pcm(left['pcm'], right['pcm'], SAMPLE_RATE, gap_ms)
    guard_start = len(left['pcm'])
    ordinal = len(left['passage']['slots'])
    starts, alignment_status = align(model, pcm, left['characters'] + right['characters'])
    breaks = clause_breaks(left['passage']['slots']) | {ordinal} | {
        ordinal + number for number in clause_breaks(right['passage']['slots'])}
    known_edges = anchored_edges(right['fixed_reference'], guard_start, guard_stop)
    scores = {}
    for name, detect in DETECTORS.items():
        reference = detect(pcm, SAMPLE_RATE)
        pause = guard_pause(reference, guard_start, guard_stop)
        scores[name] = assignment(name, pause, starts, breaks, ordinal)
    return {'left_recording_id': left['take']['recording_id'], 'right_recording_id': right['take']['recording_id'],
            'left_audio_sha256': left['take']['audio_sha256'], 'right_audio_sha256': right['take']['audio_sha256'],
            'work_id': right['passage']['work_id'], 'passage_id': right['passage']['passage_id'],
            'pair_id': right['passage']['pair_id'], 'voice': right['take']['speaker'], 'gap_ms': gap_ms,
            'pcm16le_sha256': checksum, 'guard_samples': [guard_start, guard_stop],
            'expected_right_slot': ordinal, 'alignment_status': alignment_status,
            **scores, 'known_edges': {'guard_interval': known_edges, 'resume_usable': known_edges is not None,
                                       **score_case(known_edges, starts, breaks, ordinal)}}


def native_case(model, donor):
    starts, status = align(model, donor['pcm'], donor['characters'])
    breaks = clause_breaks(donor['passage']['slots'])
    result = {}
    for name, reference in (('fixed', donor['fixed_reference']),
                            ('relative', detect_relative(donor['pcm'], SAMPLE_RATE))):
        result[name] = [{**pause, 'match': match_pause(pause, starts, breaks) if available(name, pause) else None}
                        for pause in reference['pauses']]
    return {'work_id': donor['passage']['work_id'], 'passage_id': donor['passage']['passage_id'],
            'voice': donor['take']['speaker'], 'audio_sha256': donor['take']['audio_sha256'], 'alignment_status': status,
            **result}


def metrics(rows, method):
    outcomes = Counter(row[method]['outcome'] for row in rows)
    return {'trials': len(rows), 'quiet_guards': sum(row[method]['guard_interval'] is not None for row in rows),
            'usable_resumptions': sum(row[method]['resume_usable'] for row in rows), **{
                key: outcomes[key] for key in ('correct', 'wrong_clause', 'wrong_within_clause', 'abstained',
                                               'uncertain_resume', 'undetected', 'unaligned')}}


def summarize(joins, native, voices):
    joined = {}
    for method in (*DETECTORS, 'known_edges'):
        sets = {voice: {(row['work_id'], row['gap_ms']) for row in joins
                        if row['voice'] == voice and row[method]['outcome'] == 'correct'} for voice in voices}
        visible = {voice: {(row['work_id'], row['gap_ms']) for row in joins if row['voice'] == voice
                           and row[method]['resume_usable'] and row['alignment_status'] == 'aligned'}
                   for voice in voices}
        joined[method] = {
            'by_voice': {voice: metrics([row for row in joins if row['voice'] == voice], method) for voice in voices},
            'by_gap_ms': {gap: metrics([row for row in joins if row['gap_ms'] == gap], method) for gap in GAPS_MS},
            'usable_in_all_voices': sorted(set.intersection(*visible.values())),
            'correct_in_all_voices': sorted(set.intersection(*sets.values())),
        }
    native_coverage = {}
    for method in DETECTORS:
        counts, present = {}, {}
        for voice in voices:
            pauses = [(row['work_id'], pause) for row in native if row['voice'] == voice for pause in row[method]]
            found = [(work, pause['match']) for work, pause in pauses if pause['match'] is not None]
            present[voice] = {(work, match['right_slot']) for work, match in found if match['status'] == 'clause_boundary'}
            counts[voice] = {'quiet_intervals': len(pauses), 'usable_resumptions': len(found),
                             'assignments': dict(Counter(match['status'] for _, match in found))}
        native_coverage[method] = {'by_voice': counts, 'clause_positions_in_all_voices':
                                   sorted(set.intersection(*present.values()))}
    return joined, native_coverage


def run(project, root, cache):
    if not root.is_relative_to(project) or not cache.is_relative_to(project):
        raise ValueError('Keep source recordings, models and derived artifacts on Gilbreth')
    passages, takes, sources = load_cohort(project, root)
    hashes = {key: digest(path) for key, path in sources.items()}
    pairs = check_inventory(passages)
    voices = sorted({voice for _, voice in takes})
    model = MandarinTimestampPredictor(cache)
    donors = {}
    for key, take in takes.items():
        passage = passages[key[0]]
        rate, pcm = read_clip(root, take, SAMPLE_RATE)
        donors[key] = {'passage': passage, 'take': take, 'pcm': pcm, 'fixed_reference': waveform_reference(pcm, rate),
                       'characters': ''.join(slot['char'] for slot in passage['slots'])}
    native = [native_case(model, donor) for donor in donors.values()]
    joins = []
    for pair in pairs.values():
        for voice in voices:
            left, right = [donors[passage['passage_id'], voice] for passage in pair]
            for gap in GAPS_MS:
                joins.append(time_case(model, left, right, gap))
                joins.append(time_case(model, right, left, gap))
    if hashes != {key: digest(path) for key, path in sources.items()}:
        raise ValueError('Source manifests changed during evaluation')
    joined, coverage = summarize(joins, native, voices)
    return {'source_sha256': hashes, 'model': {'name': MODEL, 'revision': REVISION, 'weights_sha256': WEIGHTS_SHA256},
            'settings': {'gap_ms': GAPS_MS, 'fixed': WAVEFORM_REFERENCE_SETTINGS, 'relative': RELATIVE_PAUSE_SETTINGS,
                         'match': MATCH_SETTINGS}, 'voice_ids': voices, 'held_out_works': len(passages),
            'joined_results': joined, 'native_transfer_coverage': coverage, 'joins': joins, 'native': native,
            '音律美': {'evidence': 'pause detection and controlled clause assignment'},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None}}


def render(report):
    lines = ['# Waveform pause detection and clause assignment on independent works', '',
             f"The same {report['held_out_works']} independent works were recorded in each voice. "
             'Both orders of each literary pair were joined at 150, 250 and 400 ms, preserving both donor waveforms.',
             'The known-edge control supplies the exact splice and an independently measured donor onset. '
             'The full pipelines estimate their edges without these coordinates.', '',
             '| Method | Voice | Trials | Quiet guards | Usable resumes | Correct | Wrong position |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for method, name in (('fixed', 'Fixed level'), ('relative', 'Relative level'), ('known_edges', 'Known edges')):
        current = report['joined_results'][method]
        for voice, row in current['by_voice'].items():
            lines.append(f"| {name} | {voice} | {row['trials']} | {row['quiet_guards']} | {row['usable_resumptions']} | "
                         f"{row['correct']} | {row['wrong_clause'] + row['wrong_within_clause']} |")
    lines.extend(['', '## Native coverage on the same untouched recordings', '',
                  '| Method | Voice | Quiet intervals | Usable resumes | Clause assignments |',
                  '| --- | --- | ---: | ---: | ---: |'])
    for method, result in report['native_transfer_coverage'].items():
        for voice, row in result['by_voice'].items():
            lines.append(f"| {method} | {voice} | {row['quiet_intervals']} | {row['usable_resumptions']} | "
                         f"{row['assignments'].get('clause_boundary', 0)} |")
    lines.extend(['', 'Native rows describe coverage. Accuracy was measured at synthetic joins with known locations.',
                  'These timing diagnostics support 音律美 research. 顺口 awaits separate first-read evidence.', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('project', 'root', 'model-cache', 'output', 'markdown'):
        parser.add_argument(f'--{key}', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve(strict=True)
    destinations = (args.output, args.markdown)
    if (args.output.suffix != '.json' or args.markdown.suffix != '.md'
            or any(not path.resolve().is_relative_to(root / 'results') or path.exists() or path.is_symlink()
                   for path in destinations)):
        parser.error('Use new private outputs under the experiment results')
    report = run(args.project.resolve(strict=True), root, args.model_cache.resolve(strict=True))
    write_output(args.markdown, render(report))
    write_json(args.output, report)
    print(json.dumps({key: value['by_voice'] for key, value in report['joined_results'].items()}, allow_nan=False))


if __name__ == '__main__':
    main()
