"""Test noisy clause assignment against sample-defined joins and independent onset bands."""

import argparse
from array import array
from collections import Counter
import json
import os
from pathlib import Path
from statistics import median

from audio.synthesize import SAMPLE_RATE
from src.quantitative_noise_aware_detector import NOISE_AWARE_SETTINGS, detect_noise_aware
from src.quantitative_pause_benchmark import align, anchored_edges, clause_breaks, guard_pause
from src.quantitative_pause_detector import RELATIVE_PAUSE_SETTINGS, detect_relative
from src.quantitative_pause_detector_controls import load_cohort, pcm_checksum, sample_count
from src.quantitative_pause_detector_joins import GAPS_MS, assignment
from src.quantitative_pause_match import MATCH_SETTINGS, worst_edge_error
from src.quantitative_pause_noise import (
    NOISE_DB_RELATIVE, NOISE_FILTER, add_bounded_noise, compound, noise_profile, noise_seed,
    power_of, reference_power, relative_level, scaled_noise,
)
from src.quantitative_report import check_inventory, index
from src.quantitative_waveform_reference import WAVEFORM_REFERENCE_SETTINGS, waveform_reference
from src.recitation_second_aligner import MODEL, REVISION, WEIGHTS_SHA256, MandarinTimestampPredictor
from src.stage6_listening import digest, read_clip, read_json, write_json
from src.stage7_cli import write_output


EXPERIMENT = Path('model-development/quantitative-pause-replication')
TIGHT_MS = 20
DETECTORS = {'fixed': waveform_reference, 'relative': detect_relative, 'noise_aware': detect_noise_aware}


def paired_variants(left, right):
    carrier = left + right
    cut = len(left)
    max_guard = sample_count(SAMPLE_RATE, max(GAPS_MS))
    reference = reference_power(carrier, SAMPLE_RATE)
    seed = noise_seed(pcm_checksum(carrier))
    profile = noise_profile(len(carrier) + max_guard, seed)
    for level in NOISE_DB_RELATIVE:
        noise = scaled_noise(profile, reference, level)
        noisy_carrier, applied, limited = add_bounded_noise(carrier, noise[:cut] + noise[cut + max_guard:])
        guard, _, limited_guard = add_bounded_noise(array('h', [0]) * max_guard, noise[cut:cut + max_guard])
        for gap in GAPS_MS:
            count = sample_count(SAMPLE_RATE, gap)
            segment = guard[:count]
            pcm = compound(noisy_carrier, cut, segment)
            yield pcm, cut, cut + count, {
                'gap_ms': gap, 'level_db_relative_to_clean_p90': level, 'seed': seed,
                'clean_reference_power': reference,
                'realized_carrier_noise_db_relative_to_clean_p90': relative_level(power_of(applied), reference),
                'realized_guard_noise_db_relative_to_clean_p90': relative_level(power_of(segment), reference),
                'limited_carrier_noise_samples': limited, 'limited_noise_samples_in_max_guard': limited_guard,
                'noisy_carrier_pcm16le_sha256': pcm_checksum(noisy_carrier),
            }


def resumption_error(score, reference):
    if reference is None or not score['resume_usable']:
        return None
    return worst_edge_error(score['guard_interval']['end_ms'], reference['end_range_ms'])


def check_case(model, left, right, clean_rows):
    ordinal = len(left['passage']['slots'])
    breaks = clause_breaks(left['passage']['slots']) | {ordinal} | {
        ordinal + position for position in clause_breaks(right['passage']['slots'])}
    identity = {'work_id': right['passage']['work_id'], 'passage_id': right['passage']['passage_id'],
                'pair_id': right['passage']['pair_id'], 'voice': right['take']['speaker'],
                'left_audio_sha256': left['take']['audio_sha256'], 'right_audio_sha256': right['take']['audio_sha256'],
                'left_recording_id': left['take']['recording_id'], 'right_recording_id': right['take']['recording_id']}
    rows = []
    for pcm, guard_start, guard_stop, condition in paired_variants(left['pcm'], right['pcm']):
        checksum = pcm_checksum(pcm)
        if condition['level_db_relative_to_clean_p90'] is None:
            key = identity['work_id'], identity['voice'], condition['gap_ms']
            prior = clean_rows[key]
            if (prior['pcm16le_sha256'] != checksum or prior['guard_samples'] != [guard_start, guard_stop]
                    or prior['expected_right_slot'] != ordinal
                    or any(prior[name] != identity[name] for name in ('left_audio_sha256', 'right_audio_sha256'))):
                raise ValueError('Clean join differs from the sample-exact replication')
        starts, status = align(model, pcm, left['characters'] + right['characters'])
        reference = anchored_edges(right['fixed_reference'], guard_start, guard_stop)
        scores = {}
        for name, detect in DETECTORS.items():
            pause = guard_pause(detect(pcm, SAMPLE_RATE), guard_start, guard_stop)
            result = assignment(name, pause, starts, breaks, ordinal)
            point = resumption_error(result, reference)
            band = (None if point is None else max(worst_edge_error(edge, reference['end_range_ms'])
                                                    for edge in pause['end_range_ms']))
            scores[name] = {**result, 'worst_resumption_error_ms': point,
                            'worst_resumption_band_error_ms': band}
        if condition['level_db_relative_to_clean_p90'] is None:
            for name in ('fixed', 'relative'):
                if scores[name]['outcome'] != prior[name]['outcome']:
                    raise ValueError('Baseline assignment changed on an exact clean replay')
        rows.append({**identity, **condition, 'pcm16le_sha256': checksum,
                     'guard_samples': [guard_start, guard_stop], 'expected_right_slot': ordinal,
                     'alignment_status': status, 'clean_donor_edges': reference, 'scores': scores,
                     'known_edges': assignment('fixed', reference, starts, breaks, ordinal)})
    return rows


def metrics(items, method):
    scores = [row['scores'][method] for row in items]
    errors = [score['worst_resumption_error_ms'] for score in scores
              if score['worst_resumption_error_ms'] is not None]
    outcomes = Counter(score['outcome'] for score in scores)
    return {'trials': len(items), 'stable_clean_references': sum(row['clean_donor_edges'] is not None for row in items),
            'quiet_guards': sum(score['guard_interval'] is not None for score in scores),
            'usable_resumptions': sum(score['resume_usable'] for score in scores),
            'resumptions_with_exact_reference_band': len(errors),
            'resumptions_within_tolerance': sum(error <= TIGHT_MS for error in errors),
            'resumption_bands_within_tolerance': sum(score['worst_resumption_band_error_ms'] is not None
                                                    and score['worst_resumption_band_error_ms'] <= TIGHT_MS
                                                    for score in scores),
            'median_worst_resumption_error_ms': median(errors) if errors else None,
            'correct': outcomes['correct'], 'wrong': outcomes['wrong_clause'] + outcomes['wrong_within_clause'],
            'outcomes': dict(outcomes)}


def summarize(rows, voices):
    report = {}
    for level in NOISE_DB_RELATIVE:
        selected = [row for row in rows if row['level_db_relative_to_clean_p90'] == level]
        per_voice = {voice: [row for row in selected if row['voice'] == voice] for voice in voices}
        methods = {}
        for method in DETECTORS:
            def trials_for(items, criterion):
                return {(row['work_id'], row['gap_ms']) for row in items if criterion(row['scores'][method])}

            methods[method] = {
                'overall': metrics(selected, method),
                'by_voice': {voice: metrics(items, method) for voice, items in per_voice.items()},
                'correct_in_all_voices': sorted(set.intersection(*[
                    trials_for(items, lambda score: score['outcome'] == 'correct') for items in per_voice.values()])),
                'usable_in_all_voices': sorted(set.intersection(*[
                    trials_for(items, lambda score: score['resume_usable']) for items in per_voice.values()])),
                'within_tolerance_in_all_voices': sorted(set.intersection(*[
                    trials_for(items, lambda score: score['worst_resumption_error_ms'] is not None
                               and score['worst_resumption_error_ms'] <= TIGHT_MS) for items in per_voice.values()])),
            }
        report['clean' if level is None else str(level)] = {
            'methods': methods, 'known_edge_assignments': {voice: dict(Counter(row['known_edges']['outcome']
                                                                             for row in items))
                                                              for voice, items in per_voice.items()}}
    return report


def run(project, root, cache):
    if root != project / EXPERIMENT or not cache.is_relative_to(project):
        raise ValueError('Use the verified fresh works and the existing Gilbreth model cache')
    passages, takes, sources = load_cohort(project, root)
    sources = {**sources, 'clean_join_report': root / 'results/joins.json'}
    before = {key: digest(path) for key, path in sources.items()}
    old = read_json(sources['clean_join_report'])
    if (old['source_sha256'] != {key: before[key] for key in sources if key != 'clean_join_report'}
            or tuple(old['settings']['gap_ms']) != GAPS_MS):
        raise ValueError('Noisy joins must be tied to the original clean join and recording inventory')
    clean_rows = index(old['joins'], lambda row: (row['work_id'], row['voice'], row['gap_ms']))
    voices = sorted({voice for _, voice in takes})
    model = MandarinTimestampPredictor(cache)
    donors = {}
    for key, take in takes.items():
        passage = passages[key[0]]
        rate, pcm = read_clip(root, take, SAMPLE_RATE)
        donors[key] = {'passage': passage, 'take': take, 'pcm': pcm,
                       'fixed_reference': waveform_reference(pcm, rate),
                       'characters': ''.join(slot['char'] for slot in passage['slots'])}
    rows = []
    for pair in check_inventory(passages).values():
        for voice in voices:
            left, right = [donors[passage['passage_id'], voice] for passage in pair]
            rows.extend(check_case(model, left, right, clean_rows))
            rows.extend(check_case(model, right, left, clean_rows))
    if before != {key: digest(path) for key, path in sources.items()}:
        raise ValueError('An input changed during the noisy join experiment')
    return {'source_sha256': before, 'model': {'name': MODEL, 'revision': REVISION, 'weights_sha256': WEIGHTS_SHA256},
            'settings': {'tight_ms': TIGHT_MS, 'levels_db_relative_to_clean_p90': NOISE_DB_RELATIVE,
                         'filter': NOISE_FILTER, 'gap_ms': GAPS_MS, 'fixed': WAVEFORM_REFERENCE_SETTINGS,
                         'relative': RELATIVE_PAUSE_SETTINGS, 'noise_aware': NOISE_AWARE_SETTINGS,
                         'match': MATCH_SETTINGS}, 'held_out_works': len(passages), 'voice_ids': voices,
            'by_level': summarize(rows, voices), 'rows': rows,
            '音律美': {'evidence': 'controlled timing and boundary assignment under additive noise'},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None}}


def render(report):
    lines = ['# Clause assignment in noisy held-out waveform joins', '',
             'Each of four held-out works is the right donor in three gap durations and three Kokoro voices. '
             'All detectors receive the same waveform, with paired noise on the source samples and the inserted guard. '
             'The exact splice supplies the right Han ordinal. Stable clean donor waveform onsets supply independent '
             'timing bands when available.', '',
             '| Noise relative to clean P90 | Detector | Voice | Detected / total | Usable resume | '
             'Within 20 ms / clean references | Correct slot | Wrong slot |',
             '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for level, group in report['by_level'].items():
        for method, results in group['methods'].items():
            for voice, metrics in results['by_voice'].items():
                lines.append(f"| {level} | {method} | {voice} | {metrics['quiet_guards']}/{metrics['trials']} | "
                             f"{metrics['usable_resumptions']} | {metrics['resumptions_within_tolerance']}/"
                             f"{metrics['stable_clean_references']} | {metrics['correct']} | {metrics['wrong']} |")
    lines += ['', 'Timing within 20 ms means the estimated resumption is within that distance of both ends of the '
              'independent reference band. All-three intersections, abstentions, and timings are in the JSON report. '
              'These are stationary-noise controls for 音律美 timing research. 顺口 remains a separate first-read outcome.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project', 'root', 'model-cache', 'output', 'markdown'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve(strict=True)
    if (args.output.suffix != '.json' or args.markdown.suffix != '.md'
            or any(not path.resolve().is_relative_to(root / 'results') or path.exists() or path.is_symlink()
                   for path in (args.output, args.markdown))):
        parser.error('Use distinct new files under the private experiment results')
    report = run(args.project.resolve(strict=True), root, args.model_cache.resolve(strict=True))
    write_output(args.markdown, render(report))
    write_json(args.output, report)
    print(json.dumps({level: {name: item['overall'] for name, item in group['methods'].items()}
                      for level, group in report['by_level'].items()}, allow_nan=False))


if __name__ == '__main__':
    main()
