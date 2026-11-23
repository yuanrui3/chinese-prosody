"""Transfer the historical duration descriptors between two matched prose cohorts."""

import argparse
from collections import Counter
import json
from math import isclose
import os
from pathlib import Path

from audio.synthesize import REVISION as KOKORO_REVISION, SAMPLE_RATE
from src.expansion_design import authors
from src.historical_increment import FEATURES, TIERS, compare, descriptors
from src.pilot_validation import holm_adjust, write_json
from src.quantitative_onset_collect import CODE, HISTORICAL, TRAINING as V4_REPORT
from src.quantitative_onset_collect import verify_inventory, verify_takes as verify_calibration_takes
from src.quantitative_report import DRAW_COUNT, FILES, GENRES, PERIODS, SEED, VOICES, index
from src.quantitative_second_alignment import pinned_passages, verify_takes as verify_holdout_takes
from src.stage6_listening import digest, read_clip, read_json
from src.timing_benchmark import check_split


CALIBRATION = Path('model-development/quantitative-onset-transfer')
HOLDOUT = Path('model-development/quantitative-report')
OUTPUT_DIR = CALIBRATION / 'results/onset-transfer'
SERIES = tuple((tier, feature) for tier in TIERS for feature in FEATURES)


def collect_durations(root, passages, takes):
    """Use complete PCM duration, including any silence, as the reference."""
    rows = {voice: [] for voice in VOICES}
    for pid, passage in sorted(passages.items()):
        text_descriptors = {tier: descriptors(passage, tier) for tier in TIERS}
        for voice in VOICES:
            take = takes[pid, voice]
            rate, pcm = read_clip(root, take, SAMPLE_RATE)
            actual_seconds = len(pcm) / rate
            if not pcm or not isclose(actual_seconds, take['duration_s'], rel_tol=0, abs_tol=1e-6):
                raise ValueError(f'{pid}: manifest duration differs from the PCM sample count')
            rows[voice].append({
                **{key: passage[key] for key in ('passage_id', 'work_id', 'period', 'genre', 'pair_id',
                                                'text_sha256', 'source_url')},
                'authors': sorted(authors(passage)), 'recording_id': take['recording_id'],
                'condition': (take['model_revision'], voice, take['speed'], rate),
                'audio_sha256': take['audio_sha256'], 'sample_count': len(pcm), 'slots': len(passage['slots']),
                'duration_ms': 1000 * actual_seconds, 'descriptors': text_descriptors,
            })
    return rows


def verify_v4(reference, rows):
    profiles = index(reference['passages'], lambda row: row['witness']['passage_id'])
    if tuple(reference['conditions']['voice_ids']) != VOICES:
        raise ValueError('The v4 report has a different voice inventory')
    for voice, clip_rows in rows.items():
        if profiles.keys() != {row['passage_id'] for row in clip_rows}:
            raise ValueError('The test inventory differs from the complete v4 inventory')
        for row in clip_rows:
            profile = profiles[row['passage_id']]
            timing = profile['音律美']['recorded_timing'][voice]
            if (any(row[key] != profile['witness'][key] for key in ('work_id', 'period', 'genre', 'text_sha256'))
                    or any(row[key] != timing[key] for key in ('recording_id', 'audio_sha256'))
                    or not isclose(row['duration_ms'], timing['duration_ms'], rel_tol=0, abs_tol=1e-6)):
                raise ValueError('A test clip is not the exact waveform measured in v4')


def run_comparisons(calibration, holdout, *, draws=DRAW_COUNT, seed=SEED):
    results = {voice: [] for voice in VOICES}
    for voice in VOICES:
        check_split(calibration[voice], holdout[voice])
    for series, (tier, feature) in enumerate(SERIES):
        random_seed = seed + 1009 * series
        for voice in VOICES:
            result = compare(calibration[voice], holdout[voice], tier, feature, draws, random_seed)
            results[voice].append({'shuffle_seed': random_seed, **result})
    holm_adjust([row for voice in VOICES for row in results[voice] if row['tier'] == TIERS[0]])
    return results


def check_cohort(rows, expected_stratum_size):
    expected = {(period, genre): expected_stratum_size for period in PERIODS for genre in GENRES}
    if dict(Counter((row['period'], row['genre']) for row in rows.values())) != expected:
        raise ValueError('Expected the complete period- and genre-balanced cohort')


def analyze(project):
    calibration_root, holdout_root = (project / path for path in (CALIBRATION, HOLDOUT))
    if any(path.resolve(strict=True) != path for path in (calibration_root, holdout_root)):
        raise ValueError('Use the two canonical experiment directories in the Gilbreth project')
    holdout_inputs = {name: holdout_root / FILES[name] for name in ('passages', 'takes')}
    inputs = {
        **{f'{split}_{name}': root / FILES[name] for split, root in
           (('calibration', calibration_root), ('holdout', holdout_root)) for name in ('passages', 'takes')},
        'historical_archive_passages': project / HISTORICAL / FILES['passages'],
        'historical_archive_takes': project / HISTORICAL / FILES['takes'],
        'holdout_v4_report': project / V4_REPORT,
        'holdout_original_report': holdout_root / 'results/quantitative-report/report.json',
        'calibration_source_pins': CODE / 'data/pilot/historical-increment.json',
        'calibration_readings': CODE / 'audio/historical_increment_readings.json',
        'holdout_source_pins': CODE / 'data/pilot/voice-report.json',
        'holdout_readings': CODE / 'audio/voice_report_readings.json',
    }
    hashes = {name: digest(path) for name, path in inputs.items()}
    calibration_passages = verify_inventory(project, calibration_root)
    holdout_passages, readings, holdout_hashes = pinned_passages(holdout_root, holdout_inputs)
    reference = read_json(project / V4_REPORT)
    if any(reference['source_sha256'][key] != value for key, value in holdout_hashes.items()):
        raise ValueError('The holdout inputs differ from the v4 checksums')
    check_cohort(calibration_passages, 4)
    check_cohort(holdout_passages, 2)

    calibration_takes, _ = verify_calibration_takes(project, calibration_root, calibration_passages)
    holdout_takes = verify_holdout_takes(holdout_root, holdout_inputs['takes'], holdout_passages, readings)
    all_takes = [*calibration_takes.values(), *holdout_takes.values()]
    if len({take['audio_sha256'] for take in all_takes}) != len(all_takes):
        raise ValueError('Every work and voice must have a distinct recorded waveform')
    calibration = collect_durations(calibration_root, calibration_passages, calibration_takes)
    holdout = collect_durations(holdout_root, holdout_passages, holdout_takes)
    verify_v4(reference, holdout)
    results = run_comparisons(calibration, holdout)
    if any(digest(path) != hashes[name] for name, path in inputs.items()):
        raise ValueError('An input manifest or report changed during the duration comparison')
    return {
        'schema_version': 1,
        'outcome': 'Complete synthetic WAV duration, including silence, in milliseconds',
        'source_sha256': hashes,
        'conditions': {'kind': 'synthetic', 'model_revision': KOKORO_REVISION, 'voice_ids': VOICES,
                       'nominal_speed': 0.9, 'sample_rate': SAMPLE_RATE},
        'comparison': {'baseline': 'character count with a fitted mean rate',
                       'candidate': 'character count with one historical descriptor adjusting the rate',
                       'permutations': DRAW_COUNT, 'shuffle_block': ['period', 'genre'],
                       'shared_shuffle_sequences_across_voices': True,
                       'primary_holm_family': {'tier': TIERS[0], 'descriptors': FEATURES, 'voices': VOICES},
                       'sensitivity_tier': TIERS[1]},
        'calibration_works': len(calibration_passages), 'holdout_works': len(holdout_passages),
        'calibration': calibration, 'holdout': holdout, 'comparisons_by_voice': results,
        '音律美': {'evidence': 'matched prose structure and synthetic whole-clip timing diagnostics'},
        '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    output = args.output.resolve()
    if (output.parent != project / OUTPUT_DIR or output.suffix != '.json'
            or args.output.is_symlink() or output.exists()):
        parser.error('Choose a new JSON output in the onset-transfer results directory')
    os.umask(0o077)
    report = analyze(project)
    write_json(output, report)
    summary = {voice: [{key: value for key, value in row.items() if key in (
        'tier', 'feature', 'status', 'holdout_works', 'baseline_mae_ms', 'augmented_mae_ms',
        'gain_ms', 'p_value', 'p_holm')} for row in rows] for voice, rows in report['comparisons_by_voice'].items()}
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
