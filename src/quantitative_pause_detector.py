"""Detect low-energy PCM intervals using a recording-relative energy reference."""

from math import ceil

from src.quantitative_waveform_reference import runs


RELATIVE_PAUSE_SETTINGS = {
    'frame_ms': 5,
    'reference_power_percentile': 90,
    'primary_quiet_relative_db': -30,
    'quiet_relative_thresholds_db': (-35, -30, -25),
    'clear_activity_relative_db': -20,
    'activity_context_ms': 160,
    'minimum_clear_activity_ms': 30,
    'minimum_internal_quiet_ms': 100,
    'maximum_resumption_range_ms': 40,
}


def detect_relative(samples, rate):
    """Return quiet cores and separate eligibility for waveform resumption edges."""
    if rate <= 0:
        raise ValueError('Sample rate must be positive')
    settings = RELATIVE_PAUSE_SETTINGS
    frame = max(1, round(rate * settings['frame_ms'] / 1000))
    frame_ms = 1000 * frame / rate
    powers = [sum(int(value) ** 2 for value in samples[start:start + frame]) / frame
              for start in range(0, len(samples) - frame + 1, frame)]
    rank = ceil(len(powers) * settings['reference_power_percentile'] / 100)
    relative_power = sorted(powers)[rank - 1] if powers else 0
    result = {'status': 'no_clear_activity', 'sample_rate': rate, 'sample_count': len(samples),
              'reference_frame_power': relative_power, 'quiet_candidates': 0,
              'quiet_candidate_rejections': {'insufficient_adjacent_activity': 0}, 'pauses': []}
    if relative_power <= 0:
        return result
    result['status'] = 'ok'

    quiet_runs = {level: list(runs([power <= relative_power * 10 ** (level / 10) for power in powers]))
                  for level in settings['quiet_relative_thresholds_db']}
    strong_floor = relative_power * 10 ** (settings['clear_activity_relative_db'] / 10)
    strong = [power > strong_floor for power in powers]
    context = int(settings['activity_context_ms'] / frame_ms)

    def enough_activity(frames):
        return sum(frames) * frame_ms >= settings['minimum_clear_activity_ms']

    for left, right in quiet_runs[settings['primary_quiet_relative_db']]:
        if left == 0 or right == len(powers) or (right - left) * frame_ms < settings['minimum_internal_quiet_ms']:
            continue
        result['quiet_candidates'] += 1
        if not (enough_activity(strong[max(0, left - context):left])
                and enough_activity(strong[right:right + context])):
            result['quiet_candidate_rejections']['insufficient_adjacent_activity'] += 1
            continue
        middle = (left + right) // 2
        variants = [next(((lo, hi) for lo, hi in spans if lo <= middle < hi), None)
                    for spans in quiet_runs.values()]
        starts, ends = zip(*(span for span in variants if span is not None))
        resumption_range = [min(ends) * frame_ms, max(ends) * frame_ms]
        # At the recording end there is no observed resumption on that threshold.
        eligible = (None not in variants and max(ends) < len(powers)
                    and (max(ends) - min(ends)) * frame_ms <= settings['maximum_resumption_range_ms'])
        result['pauses'].append({'start_sample': left * frame, 'end_sample': right * frame,
                                 'start_ms': left * frame_ms, 'end_ms': right * frame_ms,
                                 'start_range_ms': [min(starts) * frame_ms, max(starts) * frame_ms],
                                 'end_range_ms': resumption_range, 'resumption_eligible': eligible})
    return result
