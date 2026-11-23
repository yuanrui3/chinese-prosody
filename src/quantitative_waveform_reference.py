"""Locate low-energy boundaries in unchanged PCM without an alignment draft."""


WAVEFORM_REFERENCE_SETTINGS = {
    'frame_ms': 5,
    'primary_quiet_dbfs': -50,
    'quiet_thresholds_dbfs': (-55, -50, -45),
    'clear_activity_dbfs': -40,
    'minimum_edge_activity_ms': 10,
    'minimum_clear_activity_ms': 30,
    'activity_context_ms': 80,
    'minimum_internal_quiet_ms': 100,
    'maximum_sensitivity_width_ms': 15,
}


def runs(flags):
    """Return half-open runs of selected frames."""
    start = None
    for index, on in enumerate(flags):
        if on and start is None:
            start = index
        elif not on and start is not None:
            yield start, index
            start = None
    if start is not None:
        yield start, len(flags)


def waveform_reference(samples, rate):
    """Measure stable PCM activity edges and internal quiet intervals.

    These are energy landmarks, with no lexical or phonetic labels. Sample
    coordinates are half-open boundaries on the frame grid.
    """
    if rate <= 0:
        raise ValueError('Sample rate must be positive')
    settings = WAVEFORM_REFERENCE_SETTINGS
    frame = max(1, round(rate * settings['frame_ms'] / 1000))
    frame_ms = 1000 * frame / rate

    def duration(width):
        return width * frame_ms

    def stable(values):
        return duration(max(values) - min(values)) <= settings['maximum_sensitivity_width_ms']

    powers = [sum(value * value for value in samples[start:start + frame]) / frame
              for start in range(0, len(samples) - frame + 1, frame)]
    quiet = {level: [power <= 32768 ** 2 * 10 ** (level / 10) for power in powers]
             for level in settings['quiet_thresholds_dbfs']}
    strong_floor = 32768 ** 2 * 10 ** (settings['clear_activity_dbfs'] / 10)
    strong = [(start, end) for start, end in runs([power > strong_floor for power in powers])
              if duration(end - start) >= settings['minimum_clear_activity_ms']]
    rejected = {'insufficient_adjacent_activity': 0, 'threshold_sensitive': 0}
    result = {'status': 'no_clear_activity', 'sample_rate': rate, 'sample_count': len(samples),
              'speech_start_ms': None, 'speech_end_ms': None,
              'speech_start_range_ms': None, 'speech_end_range_ms': None,
              'speech_start_sample': None, 'speech_end_sample': None,
              'quiet_candidates': 0, 'quiet_candidate_rejections': rejected, 'pauses': []}
    if not strong:
        return result

    primary = settings['primary_quiet_dbfs']
    active = {level: [(start, end) for start, end in runs([not value for value in flags])
                      if duration(end - start) >= settings['minimum_edge_activity_ms']]
              for level, flags in quiet.items()}
    edge_checks = [('start', {level: intervals[0][0] for level, intervals in active.items()}, strong[0][0]),
                   ('end', {level: intervals[-1][1] for level, intervals in active.items()}, strong[-1][1])]
    for name, edges, strong_edge in edge_checks:
        centers = list(edges.values())
        if stable(centers) and duration(max(abs(edge - strong_edge) for edge in centers)) <= settings['activity_context_ms']:
            result[f'speech_{name}_ms'] = duration(edges[primary])
            result[f'speech_{name}_sample'] = edges[primary] * frame
            result[f'speech_{name}_range_ms'] = [duration(min(centers)), duration(max(centers))]
    edge_count = sum(result[f'speech_{name}_ms'] is not None for name in ('start', 'end'))
    result['status'] = ('unresolved_edges', 'partial', 'ok')[edge_count]

    def nearby_activity(start, end):
        return any(duration(min(right, end) - max(left, start)) >= settings['minimum_clear_activity_ms']
                   for left, right in strong)

    quiet_runs = {level: list(runs(flags)) for level, flags in quiet.items()}
    context = round(settings['activity_context_ms'] / frame_ms)
    for left, right in quiet_runs[primary]:
        if left == 0 or right == len(powers) or duration(right - left) < settings['minimum_internal_quiet_ms']:
            continue
        result['quiet_candidates'] += 1
        if not (nearby_activity(left - context, left) and nearby_activity(right, right + context)):
            rejected['insufficient_adjacent_activity'] += 1
            continue
        center = (left + right) // 2
        alternate = [next(((start, end) for start, end in spans if start <= center < end), None)
                     for spans in quiet_runs.values()]
        if None in alternate:
            rejected['threshold_sensitive'] += 1
            continue
        starts, ends = map(list, zip(*alternate))
        if not (stable(starts) and stable(ends)):
            rejected['threshold_sensitive'] += 1
            continue
        result['pauses'].append({'start_sample': left * frame, 'end_sample': right * frame,
                                 'start_ms': duration(left), 'end_ms': duration(right),
                                 'start_range_ms': [duration(min(starts)), duration(max(starts))],
                                 'end_range_ms': [duration(min(ends)), duration(max(ends))]})
    return result
