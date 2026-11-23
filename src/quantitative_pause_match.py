"""Assign stable quiet intervals to adjacent written positions using the resume edge."""

from src.recitation_second_aligner import FRAME_MS


MAX_RESUME_ERROR_MS = 3 * FRAME_MS
MIN_WINNER_MARGIN_MS = 2 * FRAME_MS
MATCH_SETTINGS = {'max_resume_error_ms': MAX_RESUME_ERROR_MS, 'minimum_margin_ms': MIN_WINNER_MARGIN_MS,
                  'model_timestamp_shift_ms': 0, 'search_domain': 'all adjacent Han positions'}


def worst_edge_error(timestamp, edge_range):
    return round(max(abs(timestamp - edge) for edge in edge_range), 9)


def match_pause(pause, starts_ms, clause_breaks):
    """Screen adjacent positions before checking whether the winner has punctuation."""
    first_quiet = pause['start_range_ms'][0]
    candidates = []
    for right, start in starts_ms.items():
        previous = starts_ms.get(right - 1)
        if right > 0 and previous is not None and previous < min(first_quiet, start):
            candidates.append((worst_edge_error(start, pause['end_range_ms']), right))
    candidates.sort()
    result = {'status': 'unmatched', 'right_slot': None, 'closest_right_slot': None,
              'worst_resume_error_ms': None, 'margin_ms': None}
    if not candidates:
        return result
    error, right = candidates[0]
    margin = round(candidates[1][0] - error, 9) if len(candidates) > 1 else None
    result.update(closest_right_slot=right, worst_resume_error_ms=error, margin_ms=margin)
    if error > MAX_RESUME_ERROR_MS:
        return result
    if margin is not None and margin < MIN_WINNER_MARGIN_MS:
        return {**result, 'status': 'ambiguous'}
    return {**result, 'right_slot': right, 'status': 'clause_boundary' if right in clause_breaks else 'within_clause'}
