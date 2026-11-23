"""Measure relative delay and low-energy gaps from the rendered phrasing WAVs."""

import argparse
from collections import defaultdict
from itertools import product
import json
import math
import os
from pathlib import Path
from random import Random
from statistics import mean, median

from src.pilot_validation import write_json
from src.stage6_listening import digest, read_clip, read_json


MANIFEST = Path('results/recitation-phrasing/stimuli.json')
OUTPUT = Path('results/recitation-phrasing/audio-check.json')
ROLES = ('two_two', 'one_one_two')
DBFS_THRESHOLDS = (-50, -45, -40)
PRIMARY_DBFS = -45
QUIET_FRAME_S = 0.005
GAP_CONTEXT_S = 0.040
TEMPLATE_S = 0.020
NULL_SEED = 20261122
NULL_DRAWS = 20000


def make_template(samples, start, end, rate):
    """Select a loud, short source block from the central half of a syllable."""
    quarter = (end - start) // 4
    left, right = start + quarter, end - quarter
    width = min(max(1, round(TEMPLATE_S * rate)), right - left)
    if width < max(1, round(0.008 * rate)):
        return None
    hop = max(1, round(0.004 * rate))
    candidates = range(left, right - width + 1, hop)
    offset = max(candidates, key=lambda i: sum(value * value for value in samples[i:i + width]))
    chunk = samples[offset:offset + width]
    if max(abs(value) for value in chunk) < 32768 * 10 ** (-40 / 20):
        return None
    return offset, chunk.tobytes()


def locate_templates(templates, samples, total_shift):
    """Find unique same-source speech anchors without using any splice metadata."""
    raw = samples.tobytes()
    lags = []
    for start, chunk in templates:
        first, last = 2 * start, 2 * (start + total_shift)
        hits = []
        hit = raw.find(chunk, first, last + len(chunk))
        while hit >= 0:
            if hit % 2 == 0:
                hits.append(hit // 2 - start)
            hit = raw.find(chunk, hit + 1, last + len(chunk))
        if len(hits) != 1:
            return None
        lags.append(hits[0])
    return lags if lags == sorted(lags) else None


def quiet_runs(samples, left, right, rate):
    """Longest continuous low-energy run for each fixed RMS threshold."""
    floor = {dbfs: (32768 * 10 ** (dbfs / 20)) ** 2 for dbfs in DBFS_THRESHOLDS}
    current = dict.fromkeys(DBFS_THRESHOLDS, 0)
    longest = dict.fromkeys(DBFS_THRESHOLDS, 0)
    frame = max(1, round(QUIET_FRAME_S * rate))
    for start in range(left, right - frame + 1, frame):
        energy = sum(value * value for value in samples[start:start + frame]) / frame
        for dbfs, threshold in floor.items():
            current[dbfs] = current[dbfs] + frame if energy <= threshold else 0
            longest[dbfs] = max(longest[dbfs], current[dbfs])
    return {dbfs: 1000 * length / rate for dbfs, length in longest.items()}


def per_gap(samples, bounds, templates, lags, rate):
    result = {dbfs: [] for dbfs in DBFS_THRESHOLDS}
    margin = round(rate * GAP_CONTEXT_S)
    for index, ((_, end), (start, _)) in enumerate(zip(bounds, bounds[1:])):
        left_anchor, left_chunk = templates[index]
        right_anchor, _ = templates[index + 1]
        left = max(left_anchor + len(left_chunk) // 2, end - margin) + lags[index]
        right = min(right_anchor, start + margin) + lags[index + 1]
        if not 0 <= left < right <= len(samples) or right - left < round(rate * QUIET_FRAME_S):
            return None
        for dbfs, value in quiet_runs(samples, left, right, rate).items():
            result[dbfs].append(value)
    return result


def placement_matches(concentrated, divided):
    return (concentrated[0] == concentrated[2] == divided[2] == 0
            and concentrated[1] > 0 and min(divided[:2]) > 0
            and abs(divided[0] - divided[1]) <= 1)


def verify_carrier(original, carrier, tapers, rate):
    """Verify the zero-duration sham against the untapered source PCM."""
    if len(carrier) != len(original):
        raise ValueError('Common carrier duration differs from the untapered source')
    if tapers and [taper['after_slot'] for taper in tapers] != [1, 2]:
        raise ValueError('The common carrier needs one shared window at each manipulated boundary')
    last = modified = width = energy_change = 0
    for taper in tapers:
        start, end = taper['source_start_sample'], taper['source_end_sample']
        point = taper['source_sample_index']
        if not last <= start < point < end <= len(original) or original[last:start] != carrier[last:start]:
            raise ValueError('Common carrier changes PCM outside the documented taper windows')
        for before, after in zip(original[start:end], carrier[start:end]):
            if abs(after) > abs(before) or before * after < 0:
                raise ValueError('Common carrier amplifies or reverses untapered source PCM')
            modified += before != after
            energy_change += before * before - after * after
        last = end
        width += end - start
    if original[last:] != carrier[last:]:
        raise ValueError('Common carrier changes PCM outside the documented taper windows')
    source_energy = sum(sample * sample for sample in original)
    if source_energy == 0:
        raise ValueError('Cannot audit a silent source waveform')
    return {'taper_windows': len(tapers), 'taper_window_total_ms': 1000 * width / rate,
            'modified_samples': modified, 'removed_source_energy_pct': 100 * energy_change / source_energy}


def measurement(root, pair):
    source = pair['source']
    source_root = Path(source['root']).resolve(strict=True)
    rate, original = read_clip(source_root, source, source['sample_rate'])
    sham = pair.get('sham')
    if sham is None:
        base = original
    else:
        _, base = read_clip(root, sham, rate)
        if sham['sample_count'] != len(base):
            raise ValueError('Common carrier sample count differs from its manifest')
    slots = pair['syllables']
    result = {
        'pair_id': pair['pair_id'], 'passage_id': pair['passage_id'],
        'work_id': pair.get('work_id') or source.get('work_id') or pair['passage_id'],
        'clause_index': pair['clause_index'], 'clause_text': pair['clause_text'],
        'common_carrier': verify_carrier(original, base, sham['tapers'] if sham else [], rate),
    }
    if len(slots) != 4 or [slot['slot_index'] for slot in slots] != pair['slot_indices']:
        raise ValueError('Expected the four reviewed source syllables in character order')
    bounds = [(round(slot['start_s'] * rate), round(slot['end_s'] * rate)) for slot in slots]
    if (any(not 0 <= left < right <= len(base) for left, right in bounds)
            or any(a[1] > b[0] for a, b in zip(bounds, bounds[1:]))):
        raise ValueError('Source syllable bounds exceed the waveform or overlap')
    templates = [make_template(base, left, right, rate) for left, right in bounds]
    if any(template is None for template in templates):
        return {**result, 'status': 'insufficient_source_speech_anchor'}

    versions = {}
    for role in ROLES:
        take = pair['variants'][role]
        _, variant = read_clip(root, take, rate)
        shift = len(variant) - len(base)
        if shift <= 0:
            return {**result, 'status': 'nonpositive_duration_change'}
        lag = locate_templates(templates, variant, shift)
        if lag is None:
            return {**result, 'status': 'nonunique_or_disordered_speech_anchor'}
        if lag[0] != 0 or lag[-1] != shift:
            return {**result, 'status': 'timing_change_outside_anchored_clause'}
        versions[role] = (variant, lag, [right - left for left, right in zip(lag, lag[1:])])
    delays = [versions[role][2] for role in ROLES]
    if sum(delays[0]) != sum(delays[1]):
        return {**result, 'status': 'different_pause_budgets'}

    source_quiet = per_gap(original, bounds, templates, [0] * 4, rate)
    base_quiet = per_gap(base, bounds, templates, [0] * 4, rate)
    variant_quiet = {role: per_gap(variant, bounds, templates, lag, rate)
                     for role, (variant, lag, _) in versions.items()}
    acoustic = None
    if source_quiet is not None and base_quiet is not None and None not in variant_quiet.values():
        acoustic = {}
        for dbfs, natural in base_quiet.items():
            level = {role: variant_quiet[role][dbfs] for role in ROLES}
            differences = [b - a for a, b in zip(*(level[role] for role in ROLES))]
            increments = {role: [b - a for a, b in zip(natural, measured)] for role, measured in level.items()}
            acoustic[str(dbfs)] = {
                'source_quiet_ms': source_quiet[dbfs],
                'carrier_quiet_ms': natural,
                'variant_quiet_ms': level,
                'relative_to_carrier_ms': increments,
                'two_boundary_contrast_ms': differences[0] - differences[1],
                'supports_redistribution': differences[0] > 0 and differences[1] < 0,
                'third_gap_difference_ms': differences[2],
            }
    return {
        **result, 'status': 'measured',
        'source_to_variant_duration_change_ms': 1000 * sum(delays[0]) / rate,
        'waveform_anchor_delay_ms': {role: [1000 * value / rate for value in delay]
                                     for role, delay in zip(ROLES, delays)},
        'waveform_anchors_support_placement': placement_matches(*delays),
        'quiet_runs_by_dbfs': acoustic,
    }


def shuffle_summary(by_work):
    work_contrasts = [mean(values) for values in by_work.values()]
    count = len(work_contrasts)
    if not count:
        return None
    if count <= 16:
        signs = product((-1, 1), repeat=count)
        method = 'exact work-block label swaps'
    else:
        random = Random(NULL_SEED)
        signs = (tuple(random.choice((-1, 1)) for _ in range(count)) for _ in range(NULL_DRAWS))
        method = 'seeded work-block label swaps'
    null = sorted(sum(value * sign for value, sign in zip(work_contrasts, assignment)) / count
                  for assignment in signs)
    observed = sum(work_contrasts) / count
    above = sum(value >= observed - 1e-9 for value in null)
    return {
        'method': method, 'works': count, 'swaps': len(null),
        'observed_mean_contrast_ms': observed, 'null_median_ms': median(null),
        'null_95th_percentile_ms': null[math.ceil(0.95 * len(null)) - 1],
        'upper_tail_fraction': above / len(null) if count <= 16 else (above + 1) / (len(null) + 1),
    }


def summarize(rows):
    matched = [row for row in rows if row['status'] == 'measured']
    quiet = [row for row in matched if row['quiet_runs_by_dbfs'] is not None]
    carriers = [row['common_carrier'] for row in rows]
    levels = {}
    for threshold in DBFS_THRESHOLDS:
        field = str(threshold)
        by_work = defaultdict(list)
        readings = [row['quiet_runs_by_dbfs'][field] for row in quiet]
        for row, info in zip(quiet, readings):
            by_work[row['work_id']].append(info['two_boundary_contrast_ms'])
        levels[field] = {
            'measured_pairs': len(readings),
            'supports_redistribution': sum(item['supports_redistribution'] for item in readings),
            'median_natural_quiet_ms_by_gap': [median(item['source_quiet_ms'][index] for item in readings)
                                               for index in range(3)] if readings else None,
            'median_carrier_quiet_ms_by_gap': [median(item['carrier_quiet_ms'][index] for item in readings)
                                               for index in range(3)] if readings else None,
            'median_sham_change_ms_by_gap': [median(item['carrier_quiet_ms'][i] - item['source_quiet_ms'][i]
                                                  for item in readings) for i in range(3)] if readings else None,
            'median_added_quiet_ms_by_gap': {
                role: [median(item['relative_to_carrier_ms'][role][index] for item in readings) for index in range(3)]
                for role in ROLES
            } if readings else None,
            'median_absolute_third_gap_difference_ms': median(abs(item['third_gap_difference_ms'])
                                                            for item in readings) if readings else None,
            'label_swap_control': shuffle_summary(by_work),
        }
    return {
        'pairs': len(rows), 'anchor_measured_pairs': len(matched), 'anchor_abstentions': len(rows) - len(matched),
        'anchors_support_placement': sum(row['waveform_anchors_support_placement'] for row in matched),
        'median_added_duration_ms': median(row['source_to_variant_duration_change_ms']
                                           for row in matched) if matched else None,
        'common_carrier': {
            'verified_pairs': len(carriers),
            'tapered_pairs': sum(item['taper_windows'] > 0 for item in carriers),
            'maximum_taper_window_total_ms': max(item['taper_window_total_ms'] for item in carriers),
            'median_removed_source_energy_pct': median(item['removed_source_energy_pct'] for item in carriers),
            'maximum_removed_source_energy_pct': max(item['removed_source_energy_pct'] for item in carriers),
        },
        'primary_quiet_threshold_dbfs': PRIMARY_DBFS,
        'quiet_abstentions': len(rows) - len(quiet), 'quiet_metrics_by_dbfs': levels,
    }


def analyze(root):
    path = root / MANIFEST
    stimuli = read_json(path)
    pairs = stimuli['pairs']
    if not pairs or len({pair['pair_id'] for pair in pairs}) != len(pairs):
        raise ValueError('Expected a nonempty set of unique phrasing pairs')
    rows = [measurement(root, pair) for pair in pairs]
    summary = summarize(rows)
    write_json(root / OUTPUT, {
        'source_manifest_sha256': digest(path),
        'measurement': 'common-carrier waveform anchors and longest within-gap low-energy runs',
        'settings': {'quiet_frame_ms': 1000 * QUIET_FRAME_S, 'gap_context_ms': 1000 * GAP_CONTEXT_S,
                     'speech_template_ms': 1000 * TEMPLATE_S, 'label_swap_seed': NULL_SEED},
        'summary': summary, 'pairs': rows,
    })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(analyze(args.root.resolve(strict=True)), allow_nan=False))


if __name__ == '__main__':
    main()
