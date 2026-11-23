"""Compare the spectral shape of independently located draft final intervals."""

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from statistics import median

from audio.align import lexical_key
from src.pilot_validation import read_jsonl, write_json
from src.stage6_listening import read_clip


DEFAULT_RECOVERY = Path('results/minimal-endings/rhyme-alignment.json')
DEFAULT_OUTPUT = Path('results/minimal-endings/rhyme-spectral.json')
BANDS = {'central': (0.30, 0.60), 'late': (0.65, 0.90)}
FRAME_S = 0.025
HOP_S = 0.010
MIN_FRAMES = 2
MEL_BANDS = 24
COEFFICIENTS = 12
FREQUENCY_HZ = (200, 6000)


def mel_weights(rate, fft_length):
    import numpy as np

    def mel(hertz):
        return 2595 * np.log10(1 + hertz / 700)

    frequencies = mel(np.fft.rfftfreq(fft_length, 1 / rate))
    edges = np.linspace(*map(mel, FREQUENCY_HZ), MEL_BANDS + 2)
    left, center, right = edges[:-2, None], edges[1:-1, None], edges[2:, None]
    triangles = np.maximum(0, np.minimum((frequencies - left) / (center - left),
                                        (right - frequencies) / (right - center)))
    weights = triangles.sum(axis=1, keepdims=True)
    if np.any(weights == 0) or rate / 2 < FREQUENCY_HZ[1]:
        raise ValueError('Spectral feature requires Stage 4 sampling resolution')
    return triangles / weights


def final_shape(pcm, rate, observation, weights):
    import numpy as np
    from scipy.fft import dct

    profile = {band: (None, 0) for band in BANDS}
    if observation is None:
        return profile
    start, end = observation['final_start_s'], observation['final_end_s']
    if (not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (start, end))
            or not 0 <= start < end <= len(pcm) / rate + 1e-6):
        raise ValueError('Draft final interval is outside its checked waveform')
    first, last = math.ceil(start * rate), min(len(pcm), math.floor(end * rate))
    width, hop = round(FRAME_S * rate), round(HOP_S * rate)
    if last - first < width:
        return profile
    signal = np.asarray(pcm, dtype=np.float64)[first:last] / 32768
    frame_starts = np.arange(0, len(signal) - width + 1, hop)
    frames = np.asarray([signal[index:index + width] for index in frame_starts])
    frames -= frames.mean(axis=1, keepdims=True)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    if rms.max() < 10 ** (-70 / 20):
        return profile
    valid = rms >= max(10 ** (-70 / 20), rms.max() / 100)
    fft_length = 2 ** (width - 1).bit_length()
    power = np.abs(np.fft.rfft(frames * np.hanning(width), n=fft_length)) ** 2
    mel_power = power @ weights.T
    peak = np.maximum(mel_power.max(axis=1, keepdims=True), np.finfo(float).tiny)
    normalized_db = 10 * np.log10(np.maximum(mel_power / peak, 1e-7))
    coarse = dct(normalized_db, type=2, norm='ortho', axis=1)[:, 1:COEFFICIENTS + 1]
    centers = (frame_starts + width / 2) / (last - first)
    for band, (lower, upper) in BANDS.items():
        keep = valid & (centers >= lower) & (centers <= upper)
        count = int(keep.sum())
        profile[band] = (np.median(coarse[keep], axis=0) if count >= MIN_FRAMES else None, count)
    return profile


def distance(left, right):
    import numpy as np

    return float(np.sqrt(np.mean((left - right) ** 2))) if left is not None and right is not None else None


def intended_change(base, rhyme):
    target = base['experimental_ending']['target_slot_index']
    anchor = base['experimental_ending']['anchor_slot_index']

    def final(take, slot):
        return lexical_key(take['intended_pinyin'][slot])[0][1]

    before, after = (final(take, target) == final(base, anchor) for take in (base, rhyme))
    if before == after:
        raise ValueError('Expected a prescribed final-agreement change')
    return 'gained' if after else 'lost'


def analyze_pair(root, comparison, manifests, weights):
    passage_id = comparison['passage_id']
    profiles, records = {}, {}
    frame_support = {}
    for role in ('base', 'rhyme'):
        take = comparison['takes'][role]
        member = manifests[take['recording_id']]
        if (member['passage_id'] != passage_id or member['experimental_ending']['role'] != role
                or any(member[k] != take[k] for k in ('audio_path', 'audio_sha256'))
                or any(member['experimental_ending'][f'{endpoint}_slot_index'] != take[endpoint]['slot_index']
                       for endpoint in ('target', 'anchor'))):
            raise ValueError(f'{passage_id}: recovery and WAV manifest disagree')
        records[role] = member
        rate, pcm = read_clip(root, member, member['sample_rate'])
        width = round(FRAME_S * rate)
        if rate not in weights:
            weights[rate] = mel_weights(rate, 2 ** (width - 1).bit_length())
        profiles[role] = {
            endpoint: final_shape(pcm, rate, take[endpoint]['after'], weights[rate])
            for endpoint in ('target', 'anchor')
        }
        frame_support[role] = {
            endpoint: {band: count for band, (_, count) in result.items()}
            for endpoint, result in profiles[role].items()
        }
    intended = intended_change(records['base'], records['rhyme'])
    if intended != comparison['intended_transition']:
        raise ValueError(f'{passage_id}: recovery and prescription disagree about the contrast')
    by_band = {}
    for band in BANDS:
        base_target, base_anchor = (profiles['base'][endpoint][band][0] for endpoint in ('target', 'anchor'))
        rhyme_target, rhyme_anchor = (profiles['rhyme'][endpoint][band][0] for endpoint in ('target', 'anchor'))
        base_distance = distance(base_target, base_anchor)
        rhyme_distance = distance(rhyme_target, rhyme_anchor)
        delta = rhyme_distance - base_distance if base_distance is not None and rhyme_distance is not None else None
        fixed_distance = distance(rhyme_target, base_anchor)
        fixed_delta = fixed_distance - base_distance if base_distance is not None and fixed_distance is not None else None
        by_band[band] = {
            'base_target_to_anchor': base_distance, 'edited_target_to_edited_anchor': rhyme_distance,
            'distance_change': delta,
            'supports_intended_direction': (delta < -1e-9 if intended == 'gained' else delta > 1e-9)
            if delta is not None else None,
            'distance_change_holding_base_anchor_fixed': fixed_delta,
            'anchor_drift': distance(base_anchor, rhyme_anchor),
        }
    return {'passage_id': passage_id, 'intended_change': intended, 'frame_support': frame_support, 'bands': by_band}


def summarize(pairs):
    summary = {}
    for band in BANDS:
        rows = [pair['bands'][band] for pair in pairs]
        values = [row['distance_change'] for row in rows if row['distance_change'] is not None]
        drift = [row['anchor_drift'] for row in rows if row['anchor_drift'] is not None]
        fixed = [row for row in pairs if row['bands'][band]['distance_change_holding_base_anchor_fixed'] is not None]
        fixed_wins = sum((row['bands'][band]['distance_change_holding_base_anchor_fixed']
                          * (-1 if row['intended_change'] == 'gained' else 1)) > 1e-9 for row in fixed)
        summary[band] = {
            'supported_pairs': len(values), 'missing_pairs': len(rows) - len(values),
            'intended_direction_supported': sum(row['supports_intended_direction'] is True for row in rows),
            'median_distance_change': median(values) if values else None,
            'median_anchor_drift': median(drift) if drift else None,
            'fixed_anchor_supported_pairs': len(fixed), 'fixed_anchor_intended_direction_supported': fixed_wins,
        }
    return summary


def analyze(root, recovery, output):
    recovery_bytes = recovery.read_bytes()
    recovery_content = json.loads(recovery_bytes)
    manifests = read_jsonl(root / 'audio/manifests/synthetic.jsonl')
    by_recording = {row['recording_id']: row for row in manifests}
    comparisons = recovery_content['comparisons']
    if (len(by_recording) != len(manifests) or not comparisons
            or len({row['passage_id'] for row in comparisons}) != len(comparisons)):
        raise ValueError('Expected unique WAVs and a nonempty comparison set')
    weights = {}
    pairs = [analyze_pair(root, row, by_recording, weights) for row in comparisons]
    summary = summarize(pairs)
    write_json(output, {
        'analysis': 'draft spectral distances on independently decoded final-run intervals',
        'recovery_sha256': sha256(recovery_bytes).hexdigest(), 'pairs': pairs, 'summary': summary,
        'settings': {'fractional_frame_center_bands': BANDS, 'frame_s': FRAME_S, 'hop_s': HOP_S,
                     'minimum_frames_per_band': MIN_FRAMES, 'frequency_hz': FREQUENCY_HZ, 'mel_bands': MEL_BANDS,
                     'cepstral_coefficients': [1, COEFFICIENTS], 'minimum_frame_dbfs': -70,
                     'maximum_frame_db_below_interval_peak_rms': 40},
    })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--recovery', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve(strict=True)
    print(json.dumps(analyze(root, args.recovery or root / DEFAULT_RECOVERY,
                             args.output or root / DEFAULT_OUTPUT), allow_nan=False))


if __name__ == '__main__':
    main()
