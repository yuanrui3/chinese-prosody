"""Fill unlinked text slots with bounded, unique Charsiu waveform events."""

from bisect import bisect_left
from collections import Counter
from itertools import accumulate
from math import isfinite

from audio.align import lexical_key, match_cost


MIN_IOU = 0.50
MAX_CENTER_DISTANCE_S = 0.08
LEXICALLY_COMPATIBLE = {'segment_and_tone', 'segment_only'}


def _regions(qwen_intervals, length):
    if qwen_intervals is None or len(qwen_intervals) != length:
        raise ValueError('Expected one Qwen interval or null per character')
    result = []
    for item in qwen_intervals:
        if item is None:
            result.append(None)
            continue
        if len(item) != 2:
            raise ValueError(f'Invalid Qwen interval: {item!r}')
        start, end = item
        if not (isfinite(start) and isfinite(end) and 0 <= start < end):
            raise ValueError(f'Invalid Qwen interval: {item!r}')
        result.append((start, end))
    return result


def _geometry(first, second):
    left, right = first
    start, end = second
    intersection = max(0, min(right, end) - max(left, start))
    iou = intersection / (max(right, end) - min(left, start))
    center_distance = abs((left + right) - (start + end)) / 2
    return iou, center_distance


def _agrees(iou, center_distance):
    return iou >= MIN_IOU - 1e-12 and center_distance <= MAX_CENTER_DISTANCE_S + 1e-12


def _region(record):
    return record['start_s'], record['end_s']


def _inventory(text, links):
    slots, heard, baseline = {}, [], {}
    for slot, syllable, status, basis in links:
        if status == 'matched' and (slot is None or syllable is None):
            raise ValueError('Matched link requires a text slot and a heard syllable')
        if slot is not None:
            index = slot['slot_index']
            if index in slots:
                raise ValueError(f'Repeated Charsiu slot {index}')
            slots[index] = slot, status
        if syllable is None:
            continue
        first, last = syllable.phones[0].start_s, syllable.phones[-1].end_s
        if not (isfinite(first) and isfinite(last) and 0 <= first < last):
            raise ValueError('Invalid Charsiu syllable interval')
        if heard and heard[-1][0]['end_s'] > first + 1e-12:
            raise ValueError('Charsiu heard intervals overlap or are out of order')
        event = {'event': len(heard), 'start_s': first, 'end_s': last, 'duration_s': last - first}
        heard.append((event, syllable))
        if status == 'matched':
            baseline[index] = {**event, 'match_basis': basis}

    if sorted(slots) != list(range(len(text))):
        raise ValueError('Charsiu links do not account for all source characters')
    anchors = [record['event'] for _, record in sorted(baseline.items())]
    if any(left >= right for left, right in zip(anchors, anchors[1:])):
        raise ValueError('Charsiu baseline links are not strictly ordered')
    return slots, heard, baseline


def _lexical_basis(slot, syllable):
    lookup = slot.get('readings', {}).get('mandarin', {})
    chosen = lookup.get('selected')
    readings = [chosen] if chosen else lookup.get('candidates', [])
    _, basis = match_cost({lexical_key(reading['reading']) for reading in readings}, syllable)
    return basis


def _anchor_agrees(reference, anchor):
    return reference is not None and _agrees(*_geometry(reference, _region(anchor)))


def _crossings(proposals):
    order = [proposals[index][0]['event'] for index in sorted(proposals)]
    prior = [-1, *accumulate(order, max)]
    later = [*reversed(list(accumulate(reversed(order), min))), float('inf')]
    return {index for index, event, lo, hi in zip(sorted(proposals), order, prior, later[1:])
            if event <= lo or event >= hi}


def rescue_links(text, links, qwen_intervals=None, *, mode='compatible', require_anchor_agreement=False):
    """Return Charsiu links plus optional rescues and site-level diagnostics.

    Qwen intervals are in seconds in text order. ``compatible`` requires
    matching segments, allowing a tone difference. ``qwen_only`` also permits
    a phonological mismatch after the same acoustic and ordering checks.
    ``baseline`` retains only the original matches. Event indices count heard
    syllables, including insertions and substitutions, and skip omitted slots.
    """
    if mode not in ('baseline', 'compatible', 'qwen_only'):
        raise ValueError(f'Unexpected rescue mode {mode!r}')
    slots, heard, baseline = _inventory(text, links)
    audit = {'mode': mode, 'minimum_iou': MIN_IOU, 'maximum_center_distance_s': MAX_CENTER_DISTANCE_S,
             'require_anchor_agreement': require_anchor_agreement, 'baseline_matches': len(baseline),
             'heard_events': len(heard), 'accepted_rescues': 0, 'geometry_candidate_basis': {},
             'accepted_basis': {}, 'status_counts': {}, 'sites': []}
    if mode == 'baseline':
        return baseline, audit

    regions = _regions(qwen_intervals, len(text))
    anchors = sorted(baseline)
    contenders = Counter()
    geometry_basis = Counter()
    candidates = {}
    by_site = {}

    for index in range(len(text)):
        if index in baseline:
            continue
        slot, status = slots[index]
        site = {'slot_index': index, 'char': text[index], 'prior_status': status, 'status': 'no_qwen_interval'}
        by_site[index] = site
        region = regions[index]
        if region is None:
            continue
        offset = bisect_left(anchors, index)
        if offset in (0, len(anchors)):
            site['status'] = 'unbracketed'
            continue
        lo, hi = anchors[offset - 1], anchors[offset]
        left, right = baseline[lo], baseline[hi]
        site['baseline_anchor_slots'] = [lo, hi]
        if require_anchor_agreement and not (_anchor_agrees(regions[lo], left) and _anchor_agrees(regions[hi], right)):
            site['status'] = 'anchor_disagreement'
            continue

        choices = []
        for event, syllable in heard[left['event'] + 1:right['event']]:
            iou, distance = _geometry(region, _region(event))
            if _agrees(iou, distance):
                basis = _lexical_basis(slot, syllable)
                choices.append((event, basis, iou, distance))
                contenders[event['event']] += 1
                geometry_basis[basis] += 1
        site['events_considered'] = [item[0]['event'] for item in choices]
        site['status'] = 'no_geometric_match' if not choices else 'multiple_geometric_matches'
        if len(choices) == 1:
            candidates[index] = choices[0]

    proposals = {}
    for index, (event, basis, iou, distance) in candidates.items():
        site = by_site[index]
        site.update(heard_event=event['event'], lexical_basis=basis, iou=iou, center_distance_s=distance)
        if contenders[event['event']] != 1:
            site['status'] = 'shared_heard_event'
        elif mode == 'compatible' and basis not in LEXICALLY_COMPATIBLE:
            site['status'] = 'lexical_mismatch'
        else:
            proposals[index] = event, basis

    crossing = _crossings(proposals)
    aligned = dict(baseline)
    accepted_basis = Counter()
    for index, (event, basis) in proposals.items():
        if index in crossing:
            by_site[index]['status'] = 'crossing_match'
        else:
            aligned[index] = {**event, 'match_basis': f'qwen_rescue_{basis}'}
            by_site[index]['status'] = 'rescued'
            accepted_basis[basis] += 1

    sites = list(by_site.values())
    audit.update(accepted_rescues=sum(accepted_basis.values()), geometry_candidate_basis=dict(geometry_basis),
                 accepted_basis=dict(accepted_basis), status_counts=dict(Counter(site['status'] for site in sites)),
                 sites=sites)
    return aligned, audit
