"""Evaluate frozen pause detectors on independent works with sample-locked noise."""

import argparse
import json
from math import isclose
import os
from pathlib import Path
from statistics import mean

from src import (
    quantitative_noise_aware_detector,
    quantitative_pause_detector,
    quantitative_pause_noise,
    quantitative_waveform_reference,
)
from src.quantitative_pause_detector_controls import (
    ALL_VOICES, EDGE_TOLERANCE_MS, FRAME_MS, GUARDS_MS, POSITIVE_MIN_MS, REPLICATION,
    SAMPLE_RATE, files_to_check, load_cohort,
)
from src.stage6_listening import digest, read_clip, write_json
from src.stage7_cli import write_output


METHODS = ('strict', 'relative', 'noise_aware')
LEVELS = quantitative_pause_noise.NOISE_DB_RELATIVE
POSITIVE = tuple(guard for guard in GUARDS_MS if guard >= POSITIVE_MIN_MS)
NEGATIVE = tuple(guard for guard in GUARDS_MS if guard < POSITIVE_MIN_MS)


def ratio(count, total):
    return count / total if total else None


def is_usable(result):
    return result['outcome'] == 'hit' and result['usable_resume']


def tight_resume(result):
    return is_usable(result) and result['absolute_edge_error_ms'][1] <= EDGE_TOLERANCE_MS


def edge_mae(results):
    errors = [row['absolute_edge_error_ms'] for row in results]
    return [mean(values) for values in zip(*errors)] if errors else None


def summarize_trials(positive, negative):
    hits = [row for row in positive if row['outcome'] == 'hit']
    usable = [row for row in hits if is_usable(row)]
    tight = sum(tight_resume(row) for row in usable)
    both_tight = sum(row['both_edges_within_tolerance'] for row in hits)
    return {
        'positive_trials': len(positive),
        'detections': len(hits),
        'usable_resumptions': len(usable),
        'usable_resumptions_within_20ms': tight,
        'usable_resumption_fraction_within_20ms': ratio(tight, len(usable)),
        'positive_trial_fraction_with_usable_resumption_within_20ms': ratio(tight, len(positive)),
        'detected_with_both_edges_within_20ms': both_tight,
        'detected_fraction_with_both_edges_within_20ms': ratio(both_tight, len(hits)),
        'mean_absolute_start_end_error_ms_on_detections': edge_mae(hits),
        'mean_absolute_start_end_error_ms_on_usable_resumptions': edge_mae(usable),
        'negative_trials': len(negative),
        'false_matches_at_negative_sites': sum(row['outcome'] == 'false_pause' for row in negative),
    }


def index_trials(cases):
    indexed = {}
    conditions = {(level, guard) for level in LEVELS for guard in GUARDS_MS}
    for case in cases:
        if case['status'] != 'scored':
            continue
        trials = {(row['noise_target_db_relative_to_clean_p90'], row['guard_ms']): row['results']
                  for row in case['trials']}
        if len(trials) != len(case['trials']) or trials.keys() != conditions:
            raise ValueError('Every scored take must contribute each noise and guard condition once')
        for (level, guard), results in trials.items():
            key = level, guard, case['work_id'], case['voice']
            if key in indexed or set(results) != set(METHODS):
                raise ValueError('Expect one paired trial per work, voice, and condition')
            indexed[key] = results
    return indexed


def joint_work_masks(indexed, works, level, guard):
    available = [work for work in works if all((level, guard, work, voice) in indexed for voice in ALL_VOICES)]
    by_method = {}
    for method in METHODS:
        outcomes = {work: [indexed[level, guard, work, voice][method] for voice in ALL_VOICES]
                    for work in available}
        if guard in POSITIVE:
            by_method[method] = {
                'detected_in_all_three_voices': [work for work, rows in outcomes.items()
                                                if all(row['outcome'] == 'hit' for row in rows)],
                'usable_resumption_in_all_three_voices': [work for work, rows in outcomes.items()
                                                         if all(is_usable(row) for row in rows)],
                'usable_resumption_within_20ms_in_all_three_voices': [work for work, rows in outcomes.items()
                                                                    if all(tight_resume(row) for row in rows)],
            }
        else:
            by_method[method] = {
                'false_match_in_any_voice': [work for work, rows in outcomes.items()
                                             if any(row['outcome'] == 'false_pause' for row in rows)],
            }
    report = {'works_available_in_all_three_voices': available, 'by_method': by_method}
    if guard in POSITIVE:
        shared = set.intersection(*(set(item['usable_resumption_in_all_three_voices'])
                                    for item in by_method.values()))
        report['works_with_usable_resumption_in_all_methods_and_voices'] = sorted(shared)
        report['mean_absolute_start_end_error_ms_on_common_works'] = {
            method: edge_mae([indexed[level, guard, work, voice][method]
                              for work in sorted(shared) for voice in ALL_VOICES])
            for method in METHODS
        }
    return report


def summarize(cases):
    works = sorted({row['work_id'] for row in cases})
    indexed = index_trials(cases)
    result = {}
    for level in LEVELS:
        label = 'clean' if level is None else str(level)
        result[label] = {
            'pooled': {method: summarize_trials(
                [rows[method] for (noise, guard, _, _), rows in indexed.items() if noise == level and guard in POSITIVE],
                [rows[method] for (noise, guard, _, _), rows in indexed.items() if noise == level and guard in NEGATIVE],
            ) for method in METHODS},
            'by_voice': {voice: {method: summarize_trials(
                [indexed[level, guard, work, voice][method] for guard in POSITIVE for work in works
                 if (level, guard, work, voice) in indexed],
                [indexed[level, guard, work, voice][method] for guard in NEGATIVE for work in works
                 if (level, guard, work, voice) in indexed],
            ) for method in METHODS} for voice in ALL_VOICES},
            'by_guard': {str(guard): joint_work_masks(indexed, works, level, guard) for guard in GUARDS_MS},
        }
    return result


def run(project, root):
    if root != project / REPLICATION:
        raise ValueError('Use the independent four-work pause replication cohort')
    paths = files_to_check(project, root)
    paths.update({
        'strict_detector': Path(quantitative_waveform_reference.__file__),
        'relative_detector': Path(quantitative_pause_detector.__file__),
        'noise_aware_detector': Path(quantitative_noise_aware_detector.__file__),
        'noise_controls': Path(quantitative_pause_noise.__file__),
        'evaluator': Path(__file__),
    })
    checksums = {name: digest(path) for name, path in paths.items()}
    passages, takes, _ = load_cohort(project, root)
    cases = []
    for (pid, voice), take in sorted(takes.items()):
        rate, pcm = read_clip(root, take, SAMPLE_RATE)
        if not isclose(len(pcm) / rate, take['duration_s'], abs_tol=1e-6, rel_tol=0):
            raise ValueError(f"{take['recording_id']}: duration disagrees with the checksum-bound WAV")
        cases.append({
            **{key: passages[pid][key] for key in ('work_id', 'author', 'pair_id', 'passage_id', 'period', 'genre')},
            'voice': voice,
            'recording_id': take['recording_id'],
            'source_audio_sha256': take['audio_sha256'],
            'source_samples': len(pcm),
            'sample_rate': rate,
            **quantitative_pause_noise.evaluate(pcm, rate, take['audio_sha256'], extra_detectors=(
                ('noise_aware', quantitative_noise_aware_detector.detect_noise_aware),)),
        })
    if checksums != {name: digest(path) for name, path in paths.items()}:
        raise ValueError('A pinned input or frozen detector changed during evaluation')
    return {
        'schema_version': 1, 'cohort': root.name, 'source_sha256': checksums,
        'works': sorted(row['work_id'] for row in passages.values()), 'voices': ALL_VOICES,
        'recordings': len(cases), 'scored_recordings': sum(row['status'] == 'scored' for row in cases),
        'design': {
            'levels_db_relative_to_clean_p90': LEVELS,
            'filter_weights': quantitative_pause_noise.NOISE_FILTER,
            'seed_namespace': quantitative_pause_noise.SEED_NAMESPACE,
            'frame_ms': FRAME_MS,
            'positive_guards_ms': POSITIVE,
            'negative_guards_ms': NEGATIVE,
            'edge_tolerance_ms': EDGE_TOLERANCE_MS,
        },
        'detector_settings': {
            'strict': quantitative_waveform_reference.WAVEFORM_REFERENCE_SETTINGS,
            'relative': quantitative_pause_detector.RELATIVE_PAUSE_SETTINGS,
            'noise_aware': quantitative_noise_aware_detector.NOISE_AWARE_SETTINGS,
        },
        'by_level': summarize(cases),
        'cases': cases,
        '音律美': {'evidence': 'held-out synthetic pause detection and timing under controlled noise'},
        '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None},
    }


def render(report):
    lines = ['# Held-out noise-aware pause detection', '',
             f"Four independently sourced works were read in three synthetic voices. "
             f"{report['scored_recordings']} of {report['recordings']} recordings supplied an energetic cut. "
             'All three detectors received identical samples. The manufactured pause uses the same background '
             'noise as the adjacent speech, with exact sample coordinates for both edges.', '',
             '## Performance by voice and noise level', '',
             '| Noise (dB relative to clean P90) | Voice | Detector | Detected / positives | Usable resume / positives | '
             'Usable and within 20 ms / positives | Mean absolute error, start / resume (ms) | '
             'False matches / negative sites |',
             '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for level, group in report['by_level'].items():
        for voice, methods in group['by_voice'].items():
            for method, values in methods.items():
                trials = values['positive_trials']
                mae = values['mean_absolute_start_end_error_ms_on_usable_resumptions']
                error = ' / '.join(f'{point:.1f}' for point in mae) if mae is not None else '—'
                lines.append(f"| {level} | {voice} | {method} | {values['detections']}/{trials} | "
                             f"{values['usable_resumptions']}/{trials} | "
                             f"{values['usable_resumptions_within_20ms']}/{trials} | {error} | "
                             f"{values['false_matches_at_negative_sites']}/{values['negative_trials']} |")
    lines.extend(['', '## The same work in all three voices', '',
                  'Counts require a usable resumption within 20 ms in all three readings of a work.', '',
                  '| Noise | Guard (ms) | Strict | Relative | Noise-aware |',
                  '| --- | ---: | ---: | ---: | ---: |'])
    for level, group in report['by_level'].items():
        for guard in POSITIVE:
            masks = group['by_guard'][str(guard)]
            denominator = len(masks['works_available_in_all_three_voices'])
            cells = [f"{len(masks['by_method'][method]['usable_resumption_within_20ms_in_all_three_voices'])}"
                     f"/{denominator}" for method in METHODS]
            lines.append(f'| {level} | {guard} | ' + ' | '.join(cells) + ' |')
    lines.extend(['', 'A negative site is an unchanged waveform cut or a 60 ms insertion. False matches refer to these '
                  'sites. A usable resumption has a stable edge under the corresponding detector rule. The reported '
                  'timing errors compare that edge with the exact manufactured boundary.', '',
                  'These controlled timing diagnostics inform 音律美 research. 顺口 requires separate first-read '
                  'evidence. Participant testing is reserved for final validation.', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('project', 'root', 'output', 'markdown'):
        parser.add_argument(f'--{key}', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    project, root = args.project.resolve(strict=True), args.root.resolve(strict=True)
    output, markdown = args.output.resolve(), args.markdown.resolve()
    if (output.suffix != '.json' or markdown.suffix != '.md'
            or any(path.exists() or not path.is_relative_to(root / 'results') for path in (output, markdown))):
        parser.error('Choose new JSON and Markdown files under the isolated experiment results')
    report = run(project, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_output(markdown, render(report))
    write_json(output, report)
    print(json.dumps({'scored_recordings': report['scored_recordings'], 'by_level': {
        level: group['pooled'] for level, group in report['by_level'].items()
    }}, allow_nan=False))


if __name__ == '__main__':
    main()
