"""Stress-test frozen pause detectors with paired, checksum-bound background noise."""

import argparse
from array import array
from hashlib import sha256
import json
from math import ceil, isclose, log10, sqrt
import os
from pathlib import Path
from random import Random
from statistics import mean

from src import quantitative_pause_detector, quantitative_waveform_reference
from src.quantitative_pause_detector_controls import (
    ALL_VOICES, FRAME_MS, GUARDS_MS, METHODS, POSITIVE_MIN_MS, SAMPLE_RATE,
    files_to_check, find_cut, load_cohort, pcm_checksum, sample_count, score_site,
)
from src.stage6_listening import digest, read_clip, write_json
from src.stage7_cli import write_output


NOISE_DB_RELATIVE = (None, -36, -24)
NOISE_FILTER = (1, 2, 3, 2, 1)
SEED_NAMESPACE = 'quantitative-pause-noise-v1'
REFERENCE_PERCENTILE = 90


def noise_seed(audio_sha256):
    material = f'{SEED_NAMESPACE}:{audio_sha256}'.encode()
    return int.from_bytes(sha256(material).digest()[:8], byteorder='big')


def noise_profile(sample_total, seed):
    """Generate one centered, FIR-smoothed waveform shared by paired variants."""
    rng = Random(seed)
    uniform = [rng.getrandbits(16) - 32768 for _ in range(sample_total + len(NOISE_FILTER) - 1)]
    smooth = [sum(weight * value for weight, value in zip(NOISE_FILTER, uniform[i:i + len(NOISE_FILTER)]))
              for i in range(sample_total)]
    center = mean(smooth)
    return [value - center for value in smooth]


def reference_power(samples, rate):
    frame = sample_count(rate, FRAME_MS)
    powers = [mean(sample * sample for sample in samples[i:i + frame])
              for i in range(0, len(samples) - frame + 1, frame)]
    return sorted(powers)[ceil(len(powers) * REFERENCE_PERCENTILE / 100) - 1] if powers else 0


def power_of(samples):
    return mean(value * value for value in samples) if samples else 0


def relative_level(power, reference):
    return 10 * log10(power / reference) if power else None


def add_bounded_noise(source, proposed):
    """Constrain only the additive term when a clean PCM sample is near full scale."""
    if len(source) != len(proposed):
        raise ValueError('Noise length must match the clean waveform')
    applied = array('i')
    mixed = array('h')
    limited = 0
    for sample, noise in zip(source, proposed):
        safe = max(-32768 - sample, min(32767 - sample, noise))
        limited += int(safe != noise)
        mixed.append(sample + safe)
        applied.append(safe)
    if any(value - noise != sample for sample, value, noise in zip(source, mixed, applied)):
        raise ValueError('Subtracting the applied noise must restore all clean PCM samples')
    return mixed, applied, limited


def scaled_noise(profile, reference, level):
    if level is None:
        return [0] * len(profile)
    power = mean(value * value for value in profile)
    if power <= 0 or reference <= 0:
        raise ValueError('The background level requires nonzero reference and noise power')
    scale = sqrt(reference * 10 ** (level / 10) / power)
    return [round(value * scale) for value in profile]


def compound(carrier, cut, guard_noise):
    """Insert only guard noise and verify exact recovery of the noisy carrier."""
    clip = carrier[:cut] + guard_noise + carrier[cut:]
    stop = cut + len(guard_noise)
    if (clip[cut:stop] != guard_noise or len(clip) != len(carrier) + len(guard_noise)
            or clip[:cut] + clip[stop:] != carrier):
        raise ValueError('Removing the guard must restore the exact noisy carrier')
    return clip


def guard_threshold_check(guard, rate, reference, strict_floor, relative_floor):
    """Check the actual inserted frames against the frozen detector thresholds."""
    frame = sample_count(rate, FRAME_MS)
    powers = [power_of(guard[i:i + frame]) for i in range(0, len(guard) - frame + 1, frame)]
    return {
        'complete_guard_frames': len(powers),
        'primary_quiet_floor_db_relative_to_clean_p90': {
            'strict': relative_level(strict_floor, reference),
            'relative': relative_level(relative_floor, reference),
        },
        'quiet_fraction_of_guard_frames': {
            'strict': sum(power <= strict_floor for power in powers) / len(powers) if powers else None,
            'relative': sum(power <= relative_floor for power in powers) / len(powers) if powers else None,
        },
    }


def evaluate(samples, rate, audio_sha256, *, extra_detectors=()):
    """Apply any additional named detector to the same PCM as the frozen baselines."""
    cut = find_cut(samples, rate)
    reference = reference_power(samples, rate)
    if cut is None or reference <= 0:
        return {'status': 'unscored_input', 'cut_sample': cut, 'clean_reference_power': reference,
                'seed': None, 'trials': []}
    seed = noise_seed(audio_sha256)
    max_guard = sample_count(rate, max(GUARDS_MS))
    profile = noise_profile(len(samples) + max_guard, seed)
    strict_floor = 32768 ** 2 * 10 ** (quantitative_waveform_reference.WAVEFORM_REFERENCE_SETTINGS[
        'primary_quiet_dbfs'] / 10)
    relative_scale = 10 ** (quantitative_pause_detector.RELATIVE_PAUSE_SETTINGS['primary_quiet_relative_db'] / 10)
    trials = []
    for level in NOISE_DB_RELATIVE:
        proposed = scaled_noise(profile, reference, level)
        guard_proposal = proposed[cut:cut + max_guard]
        speech_proposal = proposed[:cut] + proposed[cut + max_guard:]
        carrier, applied, speech_limited = add_bounded_noise(samples, speech_proposal)
        guard, _, guard_limited = add_bounded_noise(array('h', [0]) * max_guard, guard_proposal)
        carrier_db = relative_level(power_of(applied), reference)
        carrier_sha256 = pcm_checksum(carrier)
        for duration in GUARDS_MS:
            count = sample_count(rate, duration)
            guard_prefix = guard[:count]
            clip = compound(carrier, cut, guard_prefix)
            fixed = quantitative_waveform_reference.waveform_reference(clip, rate)
            relative = quantitative_pause_detector.detect_relative(clip, rate)
            results = {'strict': score_site(fixed['pauses'], cut, count, rate),
                       'relative': score_site(relative['pauses'], cut, count, rate)}
            for name, detect in extra_detectors:
                if name in results:
                    raise ValueError(f'Duplicate pause detector name: {name}')
                results[name] = score_site(detect(clip, rate)['pauses'], cut, count, rate)
            guard_power = power_of(guard_prefix)
            trials.append({
                'noise_target_db_relative_to_clean_p90': level,
                'realized_carrier_noise_db_relative_to_clean_p90': carrier_db,
                'realized_guard_noise_db_relative_to_clean_p90': relative_level(guard_power, reference),
                'realized_guard_noise_pcm16_power': guard_power if count else None,
                'guard_threshold_check': guard_threshold_check(
                    guard_prefix, rate, reference, strict_floor, relative['reference_frame_power'] * relative_scale),
                'limited_carrier_noise_samples': speech_limited,
                'limited_noise_samples_in_maximum_guard': guard_limited,
                'guard_ms': duration, 'exact_guard_samples': [cut, cut + count],
                'noisy_carrier_pcm16le_sha256': carrier_sha256,
                'pcm16le_sha256': pcm_checksum(clip), 'exact_noisy_carrier_recovery': True,
                'results': results,
            })
    return {'status': 'scored', 'cut_sample': cut, 'clean_reference_power': reference,
            'seed': seed, 'trials': trials}


def summarize(cases):
    result = {}
    scored = [row for row in cases if row['status'] == 'scored']
    for level in NOISE_DB_RELATIVE:
        key = 'clean' if level is None else str(level)
        by_guard = {}
        for guard in GUARDS_MS:
            rows = [trial for case in scored for trial in case['trials']
                    if (trial['noise_target_db_relative_to_clean_p90'], trial['guard_ms']) == (level, guard)]
            by_guard[str(guard)] = {}
            for method in METHODS:
                results = [row['results'][method] for row in rows]
                errors = [row['absolute_edge_error_ms'] for row in results if row['absolute_edge_error_ms'] is not None]
                by_guard[str(guard)][method] = {
                    'trials': len(rows), 'hits': sum(row['outcome'] == 'hit' for row in results),
                    'usable_resume_hits': sum(row['outcome'] == 'hit' and row['usable_resume'] for row in results),
                    'false_pauses': sum(row['outcome'] == 'false_pause' for row in results),
                    'mean_absolute_edge_error_ms': [mean(values) for values in zip(*errors)] if errors else None,
                }
        realized = [trial['realized_carrier_noise_db_relative_to_clean_p90'] for case in scored
                    for trial in case['trials'] if trial['guard_ms'] == 0
                    and trial['noise_target_db_relative_to_clean_p90'] == level
                    and trial['realized_carrier_noise_db_relative_to_clean_p90'] is not None]
        result[key] = {'by_guard': by_guard, 'realized_carrier_noise_db_range':
                       [min(realized), max(realized)] if realized else None}
    return {'recordings': len(cases), 'scored_recordings': len(scored), 'by_level': result}


def run(project, root):
    paths = files_to_check(project, root)
    paths.update({'strict_detector': Path(quantitative_waveform_reference.__file__),
                  'relative_detector': Path(quantitative_pause_detector.__file__)})
    checksums = {name: digest(path) for name, path in paths.items()}
    passages, takes, _ = load_cohort(project, root)
    cases = []
    for (pid, voice), take in sorted(takes.items()):
        rate, pcm = read_clip(root, take, SAMPLE_RATE)
        if not isclose(len(pcm) / rate, take['duration_s'], abs_tol=1e-6, rel_tol=0):
            raise ValueError(f"{take['recording_id']}: duration disagrees with the checked WAV")
        cases.append({
            **{key: passages[pid][key] for key in ('work_id', 'author', 'pair_id', 'passage_id', 'period', 'genre')},
            'voice': voice, 'recording_id': take['recording_id'], 'source_audio_sha256': take['audio_sha256'],
            'source_samples': len(pcm), 'sample_rate': rate, **evaluate(pcm, rate, take['audio_sha256']),
        })
    if checksums != {name: digest(path) for name, path in paths.items()}:
        raise ValueError('A pinned source or frozen detector changed during the noise benchmark')
    return {
        'schema_version': 1, 'source_sha256': checksums,
        'strict_waveform_settings': quantitative_waveform_reference.WAVEFORM_REFERENCE_SETTINGS,
        'relative_pause_settings': quantitative_pause_detector.RELATIVE_PAUSE_SETTINGS,
        'design': {'noise_target_db_relative_to_clean_p90': NOISE_DB_RELATIVE, 'filter_weights': NOISE_FILTER,
                   'prng': 'Python Random(MT19937), getrandbits(16)', 'seed_namespace': SEED_NAMESPACE,
                   'seed_derivation': 'first 64 bits of SHA-256(namespace:source WAV SHA-256)',
                   'frame_ms': FRAME_MS, 'clean_reference_percentile': REFERENCE_PERCENTILE,
                   'guard_ms': GUARDS_MS, 'positive_minimum_ms': POSITIVE_MIN_MS},
        'by_voice': {voice: summarize([row for row in cases if row['voice'] == voice]) for voice in ALL_VOICES},
        'by_work': {row['work_id']: summarize([case for case in cases if case['work_id'] == row['work_id']])
                    for row in passages.values()},
        'cases': cases, '音律美': {'evidence': 'background-noise sensitivity of controlled pause timing'},
        '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None},
    }


def render(report):
    lines = ['# Background-noise stress test for pause detection', '',
             'This test revisits the same four expansion works and three voices as the held-out acoustic controls. '
             'The detector settings stay frozen. Each recording receives a deterministic smoothed noise waveform '
             'at two levels relative to its clean 5 ms P90 power. The same noisy speech samples appear in every '
             'condition for that recording and level. The inserted interval contains background noise alone. '
             'The 0 ms sham and 60 ms insert are negative controls for a long pause.', '',
             '| Voice | Target noise (dB relative to clean P90) | Detector | Hits / positives | Usable resume / positives | '
             'False pauses / negative sites |',
             '| --- | --- | --- | ---: | ---: | ---: |']
    for voice, summary in report['by_voice'].items():
        for level, values in summary['by_level'].items():
            for method in METHODS:
                positive = [row[method] for ms, row in values['by_guard'].items() if int(ms) >= POSITIVE_MIN_MS]
                negative = [row[method] for ms, row in values['by_guard'].items() if int(ms) < POSITIVE_MIN_MS]
                total = sum(row['trials'] for row in positive)
                hits = sum(row['hits'] for row in positive)
                resume = sum(row['usable_resume_hits'] for row in positive)
                false = sum(row['false_pauses'] for row in negative)
                negatives = sum(row['trials'] for row in negative)
                lines.append(f'| {voice} | {level} | {method} | {hits}/{total} | {resume}/{total} | {false}/{negatives} |')
    return '\n'.join(lines + ['', 'The JSON records the realized background power of the speech and guard separately, '
                                'the fraction of guard frames below each detector threshold, and timing errors per work '
                                'and guard length. This stress test concerns waveform timing for 音律美. '
                                '顺口 requires separate first-read evidence.', ''])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('project', 'root', 'output', 'markdown'):
        parser.add_argument(f'--{key}', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    project, root = args.project.resolve(strict=True), args.root.resolve(strict=True)
    output, markdown = args.output.resolve(), args.markdown.resolve()
    if (output == markdown or output.suffix != '.json' or markdown.suffix != '.md'
            or any(path.exists() or not path.is_relative_to(root / 'results') for path in (output, markdown))):
        parser.error('Choose new JSON and Markdown files inside the isolated experiment results')
    report = run(project, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_output(markdown, render(report))
    write_json(output, report)
    print(json.dumps({voice: row['scored_recordings'] for voice, row in report['by_voice'].items()}))


if __name__ == '__main__':
    main()
