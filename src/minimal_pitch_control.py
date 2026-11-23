"""Check an engineered, local pitch-contour contrast on existing synthetic WAVs."""

import argparse
from array import array
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
from statistics import median
import sys
from tempfile import NamedTemporaryFile
import wave

from audio.features import PITCH_CEILING_HZ, PITCH_FLOOR_HZ, PITCH_STEP_S, Waveform
from src.minimal_ending_analysis import usable_slots
from src.pilot_validation import read_jsonl, write_json
from src.stage6_listening import read_clip
from src.stage6_production import digest


MIN_SECONDS = 0.100
MIN_VOICED = 8
FADE_SECONDS = 0.008
EARLY = (0.20, 0.45)
LATE = (0.55, 0.80)
FALL_END_ST = 2.5
FLAT_LIMIT_ST = 1.25
MIN_FALL_ST = 1.50
ROLES = ('flat', 'falling')


def target_positions(waveform, start, end):
    return [(float((time - start) / (end - start)), float(time), frequency)
            for time, frequency in zip(waveform.frame_centers, waveform.frequencies)
            if frequency is not None and start <= time < end]


def pitch_readout(points):
    early = [pitch for relative, _, pitch in points if EARLY[0] <= relative <= EARLY[1]]
    late = [pitch for relative, _, pitch in points if LATE[0] <= relative <= LATE[1]]
    center = [pitch for relative, _, pitch in points if EARLY[1] < relative < LATE[0]]
    return {'voiced_frames': len(points), 'early_frames': len(early), 'late_frames': len(late),
            'central_f0_hz': median(center) if center else None,
            'late_minus_early_st': 12 * math.log2(median(late) / median(early))
            if min(len(early), len(late)) >= 2 else None}


def voiced_core(points, rate, left, right):
    """Find the longest contiguous run from the untouched baseline pitch track."""
    runs = []
    for point in points:
        if not runs or point[1] - runs[-1][-1][1] > PITCH_STEP_S + 1e-6:
            runs.append([])
        runs[-1].append(point)
    run = max(runs, key=len, default=[])
    if len(run) < MIN_VOICED:
        return None
    return (max(left, round((run[0][1] - PITCH_STEP_S / 2) * rate)),
            min(right, round((run[-1][1] + PITCH_STEP_S / 2) * rate)))


def pitch_in_band(center):
    return (PITCH_FLOOR_HZ <= center * 2 ** (-FALL_END_ST / 12)
            <= center * 2 ** (FALL_END_ST / 12) <= PITCH_CEILING_HZ)


def edit_pitch(sound, points, start, end, center, role):
    from parselmouth.praat import call

    manipulation = call(sound, 'To Manipulation', PITCH_STEP_S, PITCH_FLOOR_HZ, PITCH_CEILING_HZ)
    tier = call(manipulation, 'Extract pitch tier')
    call(tier, 'Remove points between', start, end)
    for relative, time, _ in points:
        st = 0.0 if role == 'flat' else FALL_END_ST * max(-1, min(1, 2 - 4 * relative))
        call(tier, 'Add point', time, center * 2 ** (st / 12))
    call([tier, manipulation], 'Replace pitch tier')
    return call(manipulation, 'Get resynthesis (overlap-add)')


def splice(source, altered, start, end, fade_frames):
    if len(altered) != len(source):
        raise ValueError('Praat returned a different sample count')
    result = array('h', source)
    for index in range(start, end):
        offset = min(index - start, end - 1 - index)
        fraction = min(1, offset / fade_frames)
        blend = (1 - math.cos(math.pi * fraction)) / 2
        value = round((1 - blend) * source[index] + blend * float(altered[index]) * 32768)
        if not -32768 <= value <= 32767:
            raise ValueError('Pitch-control splice would clip PCM')
        result[index] = value
    if result[:start] != source[:start] or result[end:] != source[end:] or len(result) != len(source):
        raise AssertionError('Pitch edit changed samples outside the target')
    return result


def write_wav(path, pcm, rate):
    little = array('h', pcm)
    if sys.byteorder != 'little':
        little.byteswap()
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            with wave.open(stream, 'wb') as wav:
                wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                wav.writeframes(little.tobytes())
            stream.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def control(root, base, slot, *, target, use_voiced_core, source_root=None):
    import parselmouth

    source_root = source_root or root
    pid, original_id = base['passage_id'], base['recording_id']
    result = {'passage_id': pid, 'source_recording_id': original_id, 'source_audio_sha256': base['audio_sha256'],
              'target_slot_index': target}
    if slot is None:
        return {**result, 'status': 'target_unlinked'}
    if slot['slot_index'] != target:
        raise ValueError('The linked syllable differs from the requested pitch target')
    rate, source = read_clip(source_root, base, base['sample_rate'])
    left, right = (round(slot[key] * rate) for key in ('start_s', 'end_s'))
    if not 0 <= left < right <= len(source):
        raise ValueError(f'{pid}: pitch-control target interval is outside the checked waveform')
    start, end = left / rate, right / rate
    result['target_sample_span'] = [left, right]
    if end - start < MIN_SECONDS - 1e-9:
        return {**result, 'status': 'target_too_short'}
    waveform = Waveform(source_root / base['audio_path'])
    points = target_positions(waveform, start, end)
    if use_voiced_core:
        span = voiced_core(points, rate, left, right)
        if span is None:
            return {**result, 'status': 'insufficient_contiguous_source_pitch'}
        left, right = span
        start, end = left / rate, right / rate
        result['edited_voiced_core_samples'] = [left, right]
        points = target_positions(waveform, start, end)
    result['source_pitch'] = pitch_readout(points)
    if len(points) < MIN_VOICED or result['source_pitch']['late_minus_early_st'] is None:
        return {**result, 'status': 'insufficient_source_pitch'}
    center = median(p for _, _, p in points)
    result['intended_center_hz'] = center
    if not pitch_in_band(center):
        return {**result, 'status': 'intended_pitch_outside_tracking_band'}
    fade = max(1, round(FADE_SECONDS * rate))
    try:
        edits = {}
        for role in ROLES:
            changed = edit_pitch(waveform.sound, points, start, end, center, role)
            if changed.sampling_frequency != rate or changed.n_channels != 1:
                raise ValueError('Praat returned a different waveform format')
            edits[role] = splice(source, changed.values[0], left, right, fade)
    except (parselmouth.PraatError, ValueError) as error:
        return {**result, 'status': 'resynthesis_unavailable', 'error': str(error)}

    directory = root / 'audio/raw/pitch-controls'
    if use_voiced_core:
        directory /= 'voiced-core'
    directory.mkdir(parents=True, exist_ok=True)
    takes = {}
    for role, edited in edits.items():
        path = directory / f'{pid}-{role}.wav'
        write_wav(path, edited, rate)
        take = {'audio_path': str(path.relative_to(root)), 'audio_sha256': digest(path),
                'recording_id': f'{pid}-{role}'}
        _, verified = read_clip(root, take, rate)
        if len(verified) != len(source) or verified[:left] != source[:left] or verified[right:] != source[right:]:
            raise ValueError(f'{pid}: on-disk pitch control failed sample preservation')
        measurements = pitch_readout(target_positions(Waveform(path), start, end))
        takes[role] = {**take, **measurements}
    result.update(takes=takes, duration_samples=len(source), unchanged_outside_target=True,
                  sample_rate=rate, fade_samples=fade)
    a, b = (takes[role]['late_minus_early_st'] for role in ROLES)
    if a is None or b is None:
        return {**result, 'status': 'insufficient_output_pitch'}
    delta = b - a
    valid = abs(a) <= FLAT_LIMIT_ST and b <= -MIN_FALL_ST and delta <= -MIN_FALL_ST
    return {**result, 'status': 'verified' if valid else 'outside_qa_band',
            'falling_minus_flat_slope_st': delta}


def run(root, *, use_voiced_core=False):
    inputs = read_jsonl(root / 'audio/manifests/synthetic.jsonl')
    bases = {row['recording_id']: row for row in inputs if row.get('experimental_ending', {}).get('role') == 'base'}
    if not bases or len({row['passage_id'] for row in bases.values()}) != len(bases):
        raise ValueError('Expected one base WAV per minimal-ending passage')
    syllables = defaultdict(list)
    for row in read_jsonl(root / 'audio/derived/features/syllables.jsonl'):
        rec_id = row['recording_id']
        if rec_id in bases:
            if row['audio_path'] != bases[rec_id]['audio_path'] or row['passage_id'] != bases[rec_id]['passage_id']:
                raise ValueError('Target alignment does not belong to its base WAV')
            syllables[rec_id].append(row)
    pairs = [control(root, row, usable_slots(syllables[rec_id]).get(row['experimental_ending']['target_slot_index']),
                     target=row['experimental_ending']['target_slot_index'],
                     use_voiced_core=use_voiced_core)
             for rec_id, row in bases.items()]
    measured = [row['falling_minus_flat_slope_st'] for row in pairs if 'falling_minus_flat_slope_st' in row]
    verified = [row['falling_minus_flat_slope_st'] for row in pairs if row['status'] == 'verified']
    summary = {'targets': len(pairs), 'statuses': dict(Counter(row['status'] for row in pairs)),
               'waveform_differences_measured': len(measured),
               'median_falling_minus_flat_st': median(measured) if measured else None,
               'median_verified_falling_minus_flat_st': median(verified) if verified else None}
    filename = 'pitch-control-voiced-core.json' if use_voiced_core else 'pitch-control.json'
    write_json(root / 'results/minimal-endings' / filename, {
        'kind': 'engineered_local_pitch_control',
        'use_voiced_core': use_voiced_core,
        'analysis_parameters': {'minimum_target_ms': 1000 * MIN_SECONDS, 'minimum_source_pitch_frames': MIN_VOICED,
                                'minimum_frames_per_measurement_band': 2, 'early_relative_band': EARLY,
                                'late_relative_band': LATE, 'intended_falling_endpoints_st': [FALL_END_ST, -FALL_END_ST],
                                'flat_maximum_absolute_slope_st': FLAT_LIMIT_ST,
                                'minimum_falling_magnitude_and_contrast_st': MIN_FALL_ST},
        'summary': summary, 'pairs': pairs,
    })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--voiced-core', action='store_true',
                        help='Use the longest contiguous voiced run from the original target')
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(run(args.root.resolve(strict=True), use_voiced_core=args.voiced_core), allow_nan=False))


if __name__ == '__main__':
    main()
