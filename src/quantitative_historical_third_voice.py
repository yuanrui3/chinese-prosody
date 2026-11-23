"""Repeat the historical duration contrast in the third synthetic voice."""

import argparse
import json
from math import isclose
import os
from pathlib import Path

from audio.synthesize import ASSET_SHA256, REVISION as KOKORO_REVISION, SAMPLE_RATE
from src.expansion_design import authors
from src.historical_increment import FEATURES, TIERS, compare, descriptors
from src.pilot_validation import holm_adjust, write_json
from src.quantitative_historical_transfer import CALIBRATION, HOLDOUT, OUTPUT_DIR, SERIES, V4_REPORT, check_cohort
from src.quantitative_onset_collect import CODE, HISTORICAL, verify_inventory
from src.quantitative_onset_collect import verify_takes as verify_calibration_takes
from src.quantitative_onset_voice_check import EXPERIMENT as THIRD_CALIBRATION, THIRD_VOICE, verify_third_takes
from src.quantitative_report import DRAW_COUNT, FILES, SEED, VOICES
from src.quantitative_second_alignment import pinned_passages, verify_takes as verify_holdout_takes
from src.stage6_listening import digest, read_clip, read_json
from src.timing_benchmark import check_split


EXPERIMENT = Path('model-development/quantitative-historical-third-voice')
DESTINATION = Path('results/historical-third-voice')


def measure(root, passages, takes):
    rows = []
    for pid, passage in sorted(passages.items()):
        take = takes[pid]
        rate, pcm = read_clip(root, take, SAMPLE_RATE)
        seconds = len(pcm) / rate
        if not pcm or not isclose(seconds, take['duration_s'], rel_tol=0, abs_tol=1e-6):
            raise ValueError(f'{pid}: manifest duration differs from the PCM sample count')
        rows.append({**{field: passage[field] for field in
                         ('work_id', 'passage_id', 'period', 'genre', 'pair_id', 'text_sha256', 'source_url')},
                     'authors': sorted(authors(passage)), 'recording_id': take['recording_id'],
                     'condition': (take['model_revision'], THIRD_VOICE, take['speed'], rate),
                     'audio_sha256': take['audio_sha256'], 'sample_count': len(pcm), 'slots': len(passage['slots']),
                     'duration_ms': 1000 * seconds, 'descriptors': {tier: descriptors(passage, tier) for tier in TIERS}})
    return rows


def compare_third(calibration, holdout, *, draws=DRAW_COUNT):
    check_split(calibration, holdout)
    results = []
    for i, (tier, feature) in enumerate(SERIES):
        seed = SEED + 1009 * i
        result = compare(calibration, holdout, tier, feature, draws, seed)
        results.append({'shuffle_seed': seed, **result})
    holm_adjust([result for result in results if result['tier'] == TIERS[0]])
    return results


def analyze(project, root):
    if root != project / EXPERIMENT:
        raise ValueError('Use the isolated historical third-voice experiment on Gilbreth')
    cal = project / THIRD_CALIBRATION
    known_cal, known_test = (project / folder for folder in (CALIBRATION, HOLDOUT))
    known_test_inputs = {field: known_test / FILES[field] for field in ('passages', 'takes')}
    inputs = {
        **{f'{split}_{field}': folder / FILES[field] for split, folder in
           (('known_calibration', known_cal), ('known_holdout', known_test),
            ('calibration', cal), ('holdout', root)) for field in ('passages', 'takes')},
        'original_comparison': project / OUTPUT_DIR / 'historical-duration-transfer.json',
        'original_v4': project / V4_REPORT,
        'original_v4_pins': known_test / 'results/quantitative-report/report.json',
        'third_onset_report': cal / 'results/third-voice/report.json',
        'archive_passages': project / HISTORICAL / FILES['passages'],
        'archive_takes': project / HISTORICAL / FILES['takes'],
        'historical_witness_pins': CODE / 'data/pilot/historical-increment.json',
        'historical_reading_pins': CODE / 'audio/historical_increment_readings.json',
        'v4_witness_pins': CODE / 'data/pilot/voice-report.json',
        'v4_reading_pins': CODE / 'audio/voice_report_readings.json',
    }
    hashes = {name: digest(path) for name, path in inputs.items()}
    original = read_json(inputs['original_comparison'])
    original_hashes = original['source_sha256']
    prior_third = read_json(inputs['third_onset_report'])
    if (tuple(original['conditions']['voice_ids']) != VOICES or THIRD_VOICE in VOICES
            or prior_third['new_voice'] != THIRD_VOICE
            or prior_third['source_sha256']['annotated'] != hashes['calibration_passages']
            or prior_third['source_sha256']['takes'] != hashes['calibration_takes']
            or original_hashes['holdout_v4_report'] != hashes['original_v4']
            or any(original_hashes[f'{split}_{field}'] != hashes[f'known_{split}_{field}']
                   for split in ('calibration', 'holdout') for field in ('passages', 'takes'))
            or any(hashes[f'{split}_passages'] != hashes[f'known_{split}_passages']
                   for split in ('calibration', 'holdout'))):
        raise ValueError('The third voice must use the same pinned works and conditions as the first comparison')
    calibration_passages = verify_inventory(project, cal)
    holdout_passages, readings, _ = pinned_passages(known_test, known_test_inputs)
    check_cohort(calibration_passages, 4)
    check_cohort(holdout_passages, 2)
    old_cal, _ = verify_calibration_takes(project, known_cal, calibration_passages)
    old_test = verify_holdout_takes(known_test, known_test_inputs['takes'], holdout_passages, readings)
    old_audio = {take['audio_sha256'] for take in (*old_cal.values(), *old_test.values())}
    calibration_takes = verify_third_takes(cal, calibration_passages, old_cal, old_audio)
    holdout_takes = verify_third_takes(root, holdout_passages, old_test,
                                      old_audio | {take['audio_sha256'] for take in calibration_takes.values()})
    calibration = measure(cal, calibration_passages, calibration_takes)
    holdout = measure(root, holdout_passages, holdout_takes)
    results = compare_third(calibration, holdout)
    if hashes != {name: digest(path) for name, path in inputs.items()}:
        raise ValueError('A pinned input changed during the duration comparison')
    return {'schema_version': 1, 'source_sha256': hashes, 'new_voice': THIRD_VOICE,
            'new_voice_asset_sha256': ASSET_SHA256[f'voices/{THIRD_VOICE}.pt'],
            'conditions': {'kind': 'synthetic', 'model_revision': KOKORO_REVISION, 'nominal_speed': 0.9,
                           'sample_rate': SAMPLE_RATE},
            'outcome': 'Complete synthetic WAV duration, including silence, in milliseconds',
            'scope': 'Exploratory replication in a new voice using the same two work cohorts and fixed descriptor definitions.',
            'comparison': {'permutations': DRAW_COUNT, 'shuffle_block': ['period', 'genre'],
                           'primary_holm_family': {'tier': TIERS[0], 'descriptors': FEATURES},
                           'sensitivity_tier': TIERS[1]},
            'calibration_works': len(calibration), 'holdout_works': len(holdout),
            'calibration': calibration, 'holdout': holdout, 'comparisons': results,
            '音律美': {'evidence': 'whole-clip duration diagnostic on matched synthetic prose'},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    project, root = (path.resolve(strict=True) for path in (args.project, args.root))
    output = args.output.resolve()
    if (output.parent != root / DESTINATION or output.suffix != '.json'
            or args.output.is_symlink() or output.exists()):
        parser.error('Choose a new JSON output in the historical-third-voice results directory')
    os.umask(0o077)
    report = analyze(project, root)
    write_json(output, report)
    summary = [{key: result[key] for key in ('tier', 'feature', 'status', 'holdout_works', 'baseline_mae_ms',
                                            'augmented_mae_ms', 'gain_ms', 'p_value', 'p_holm') if key in result}
               for result in report['comparisons']]
    print(json.dumps({'voice': report['new_voice'], 'comparisons': summary}, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
