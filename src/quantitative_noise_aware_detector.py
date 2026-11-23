"""Find quiet speech intervals against an estimated background level."""

from math import ceil
from statistics import median

from src.quantitative_pause_detector import RELATIVE_PAUSE_SETTINGS, detect_relative
from src.quantitative_waveform_reference import runs


NOISE_AWARE_SETTINGS = {
    **RELATIVE_PAUSE_SETTINGS,
    'background_power_percentile': 10,
    'minimum_level_above_background_db': 15,
    'quiet_thresholds_above_background_db': (4, 5, 6),
    'clear_activity_above_background_db': 10,
    'median_window_frames': 3,
    'resumption_confirmation_ms': 20,
    'resumption_confirmation_frames': 2,
}

WEAK_GAP_BRIDGE_SETTINGS = {
    'maximum_bridge_ms': 20,
    'minimum_adjacent_quiet_ms': 20,
    'sustained_clear_raw_frames': 2,
}


def power_ratio(db):
    return 10 ** (db / 10)


def bridge_weak_gaps(intervals, clear_frames, frame_ms, maximum_bridge_ms):
    """Connect short weak interruptions between long enough original quiet runs."""
    if not intervals:
        return intervals
    settings = WEAK_GAP_BRIDGE_SETTINGS
    minimum_quiet = settings['minimum_adjacent_quiet_ms']
    sustained_clear = settings['sustained_clear_raw_frames']
    merged = [intervals[0]]
    for left, right in zip(intervals, intervals[1:]):
        gap_ms = (right[0] - left[1]) * frame_ms
        flank_ms = min(left[1] - left[0], right[1] - right[0]) * frame_ms
        if (gap_ms <= maximum_bridge_ms and flank_ms >= minimum_quiet
                and not any(stop - start >= sustained_clear
                            for start, stop in runs(clear_frames[left[1]:right[0]]))):
            merged[-1] = merged[-1][0], right[1]
        else:
            merged.append(right)
    return merged


def detect_noise_aware(samples, rate, *, bridge_weak_ms=0):
    """Return pause cores, with a separate flag for stable resumption timing."""
    if rate <= 0:
        raise ValueError('Sample rate must be positive')
    if not 0 <= bridge_weak_ms <= WEAK_GAP_BRIDGE_SETTINGS['maximum_bridge_ms']:
        raise ValueError('Weak-gap bridge duration must be between 0 and 20 ms')
    settings = NOISE_AWARE_SETTINGS
    frame = max(1, round(rate * settings['frame_ms'] / 1000))
    frame_ms = 1000 * frame / rate
    powers = [sum(int(value) ** 2 for value in samples[start:start + frame]) / frame
              for start in range(0, len(samples) - frame + 1, frame)]
    ordered = sorted(powers)
    background, level = (ordered[ceil(len(ordered) * settings[key] / 100) - 1] if ordered else 0
                         for key in ('background_power_percentile', 'reference_power_percentile'))
    relative_cutoffs = [level * power_ratio(db) for db in settings['quiet_relative_thresholds_db']]
    background_cutoffs = [background * power_ratio(db) for db in settings['quiet_thresholds_above_background_db']]
    if background_cutoffs[-1] <= relative_cutoffs[0]:
        return {**detect_relative(samples, rate), 'background_frame_power': background, 'mode': 'relative_fallback',
                'quiet_cutoff_powers': relative_cutoffs}

    cutoffs = [max(relative, noise) for relative, noise in zip(relative_cutoffs, background_cutoffs)]
    result = {'status': 'insufficient_level_above_background', 'sample_rate': rate, 'sample_count': len(samples),
              'reference_frame_power': level, 'background_frame_power': background, 'mode': 'noise_aware',
              'quiet_cutoff_powers': cutoffs, 'quiet_candidates': 0,
              'quiet_candidate_rejections': {'insufficient_adjacent_activity': 0}, 'pauses': []}
    if level < background * power_ratio(settings['minimum_level_above_background_db']):
        return result
    result['status'] = 'ok'

    # Suppress isolated frame excursions without averaging away an abrupt step.
    smoothed = powers if len(powers) < 3 else [
        powers[0], *(median(values) for values in zip(powers, powers[1:], powers[2:])), powers[-1],
    ]
    quiet_runs = [list(runs([power <= cutoff for power in smoothed])) for cutoff in cutoffs]
    clear_level = max(level * power_ratio(settings['clear_activity_relative_db']),
                      background * power_ratio(settings['clear_activity_above_background_db']))
    clear_frames = [power > clear_level for power in powers]
    if bridge_weak_ms:
        quiet_runs = [bridge_weak_gaps(intervals, clear_frames, frame_ms, bridge_weak_ms)
                      for intervals in quiet_runs]
    flank = int(settings['activity_context_ms'] / frame_ms)
    confirm = max(1, int(settings['resumption_confirmation_ms'] / frame_ms))

    for left, right in quiet_runs[1]:
        if left == 0 or right == len(powers) or (right - left) * frame_ms < settings['minimum_internal_quiet_ms']:
            continue
        result['quiet_candidates'] += 1
        before = sum(clear_frames[max(0, left - flank):left]) * frame_ms
        after = sum(clear_frames[right:right + flank]) * frame_ms
        if min(before, after) < settings['minimum_clear_activity_ms']:
            result['quiet_candidate_rejections']['insufficient_adjacent_activity'] += 1
            continue
        middle = (left + right) // 2
        variants = [next(((start, stop) for start, stop in intervals if start <= middle < stop), None)
                    for intervals in quiet_runs]
        starts, ends = zip(*(span for span in variants if span is not None))
        latest = max(ends)
        observed_rise = sum(power > cutoffs[-1] for power in powers[latest:latest + confirm])
        eligible = (None not in variants and latest < len(powers)
                    and (latest - min(ends)) * frame_ms <= settings['maximum_resumption_range_ms']
                    and observed_rise >= settings['resumption_confirmation_frames'])
        result['pauses'].append({'start_sample': left * frame, 'end_sample': right * frame,
                                 'start_ms': left * frame_ms, 'end_ms': right * frame_ms,
                                 'start_range_ms': [min(starts) * frame_ms, max(starts) * frame_ms],
                                 'end_range_ms': [min(ends) * frame_ms, latest * frame_ms],
                                 'resumption_eligible': eligible})
    return result
