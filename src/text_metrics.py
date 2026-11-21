"""Text prosody descriptors for edition-pinned clauses with historical readings."""

from dataclasses import asdict, dataclass
from itertools import groupby
from operator import eq, ne
from statistics import fmean, pvariance, stdev
from typing import Optional


METRIC_LABELS = {
    'clause_mean_slots': 'Mean clause length in syllable slots',
    'clause_sd_slots': 'Sample SD of clause lengths in syllable slots',
    'clause_variance_slots': 'Population variance of clause lengths in squared slots',
    'clause_npvi': 'Clause length normalized pairwise variability index',
    'clause_46_share': 'Share of four- or six-slot clauses',
    'internal_boundary_rate': 'Share of internal positions with a punctuation boundary',
    'ping_share': 'Historical 平 share',
    'syllable_pz_alternation': 'Historical 平仄 contrast at adjacent syllables within clauses',
    'foot_pz_alternation': 'Historical 平仄 contrast at successive even slots within clauses',
    'clause_end_pz_alternation': 'Historical 平仄 contrast at successive clause ends',
    'adjacent_han_repeat': 'Exact adjacent character recurrence within clauses',
    'adjacent_initial_repeat': 'Exact reconstructed initial recurrence within clauses',
    'adjacent_final_repeat': 'Exact reconstructed final recurrence within clauses',
    'clause_end_rhyme_repeat': 'Exact group recurrence at successive clause ends',
    'parallel_length_similarity': 'Length similarity of independently annotated paired sides',
    'parallel_end_pz_opposition': 'Historical 平仄 contrast at annotated paired-side ends',
    'parallel_end_zp_share': 'Share of annotated paired-side ends ordered 仄 then 平',
}

WITHIN_CLAUSE = 'within_clause'
CLAUSE_ORDER = 'clause_order'
TONE_STRATIFIED = 'tone_stratified'
METRIC_NULLS = {key: frozenset() for key in METRIC_LABELS}
METRIC_NULLS.update({
    'clause_npvi': frozenset({CLAUSE_ORDER}),
    'ping_share': frozenset({TONE_STRATIFIED}),
    'syllable_pz_alternation': frozenset({WITHIN_CLAUSE, TONE_STRATIFIED}),
    'foot_pz_alternation': frozenset({WITHIN_CLAUSE, TONE_STRATIFIED}),
    'clause_end_pz_alternation': frozenset({WITHIN_CLAUSE, CLAUSE_ORDER, TONE_STRATIFIED}),
    'adjacent_han_repeat': frozenset({WITHIN_CLAUSE}),
    'adjacent_initial_repeat': frozenset({WITHIN_CLAUSE}),
    'adjacent_final_repeat': frozenset({WITHIN_CLAUSE}),
    'clause_end_rhyme_repeat': frozenset({WITHIN_CLAUSE, CLAUSE_ORDER}),
    'parallel_length_similarity': frozenset({CLAUSE_ORDER}),
    'parallel_end_pz_opposition': frozenset({WITHIN_CLAUSE, CLAUSE_ORDER, TONE_STRATIFIED}),
    'parallel_end_zp_share': frozenset({WITHIN_CLAUSE, CLAUSE_ORDER, TONE_STRATIFIED}),
})


@dataclass(frozen=True)
class MetricEstimate:
    value: Optional[float]
    eligible: int
    usable: int
    lower: Optional[float]
    upper: Optional[float]
    bounded: int


def clauses(passage):
    """Return clauses in position order, using the existing editorial boundaries."""
    return [list(group) for _, group in groupby(passage['slots'], key=lambda slot: slot['clause_index'])]


def reading_values(slot, tier, field):
    """Return the projected field of each admissible reading when all have values."""
    if field == 'pingze' and tier in slot.get('null_pingze', {}):
        label = slot['null_pingze'][tier]
        if label not in ('平', '仄'):
            raise ValueError(f'Invalid historical binary-tone label {label!r}')
        return frozenset((label,))
    reading = slot.get('readings', {}).get(tier, {})
    selected = reading.get('selected')
    candidates = (selected,) if selected is not None else reading.get('candidates', ())
    labels = frozenset(candidate.get(field) for candidate in candidates)
    return frozenset() if None in labels else labels


def slot_label(slot, tier, field):
    """Return a context-reviewed or unanimous label without choosing a heteronym."""
    labels = reading_values(slot, tier, field)
    return next(iter(labels)) if len(labels) == 1 else None


def estimates_from_values(values):
    values = list(values)
    count = len(values)
    value = fmean(values) if count else None
    return MetricEstimate(value, count, count, value, value, count)


def length_spread(lengths, estimator, minimum):
    if len(lengths) < minimum:
        return MetricEstimate(None, len(lengths), 0, None, None, 0)
    value = estimator(lengths)
    return MetricEstimate(value, len(lengths), len(lengths), value, value, len(lengths))


def ping_share(slots, tier):
    candidate_sets = [reading_values(slot, tier, 'pingze') for slot in slots]
    known = [candidates == {'平'} for candidates in candidate_sets if len(candidates) == 1]
    bounded = [candidates for candidates in candidate_sets if candidates]
    return MetricEstimate(fmean(known) if known else None, len(slots), len(known),
                          fmean(candidates == {'平'} for candidates in bounded) if bounded else None,
                          fmean('平' in candidates for candidates in bounded) if bounded else None,
                          len(bounded))


def relation_rate(sequences, labels, relation):
    """Count resolved adjacent outcomes and bound each disjoint path jointly."""
    successes = usable = eligible = bounded = lower = upper = 0
    for sequence in sequences:
        eligible += max(0, len(sequence) - 1)
        previous = {}
        for slot in sequence:
            choices = labels(slot)
            if not choices:
                # Missing labels break adjacency and leave the neighboring edges unbounded.
                if previous:
                    lower += min(bounds[0] for bounds in previous.values())
                    upper += max(bounds[1] for bounds in previous.values())
                previous = {}
                continue
            if not previous:
                previous = dict.fromkeys(choices, (0, 0))
                continue
            bounded += 1
            outcomes = {relation(before, after) for before in previous for after in choices}
            if len(outcomes) == 1:
                successes += next(iter(outcomes))
                usable += 1
            previous = {
                after: (min(lo + relation(before, after) for before, (lo, _) in previous.items()),
                        max(hi + relation(before, after) for before, (_, hi) in previous.items()))
                for after in choices
            }
        if previous:
            lower += min(bounds[0] for bounds in previous.values())
            upper += max(bounds[1] for bounds in previous.values())
    return MetricEstimate(successes / usable if usable else None, eligible, usable,
                          lower / bounded if bounded else None, upper / bounded if bounded else None,
                          bounded)


def parallel_sides(passage, lines):
    by_index = {line[0]['clause_index']: line for line in lines}
    return [([slot for index in left for slot in by_index[index]],
             [slot for index in right for slot in by_index[index]])
            for left, right in passage.get('parallel_clause_groups', ())]


def metric_results(passage, tier='guangyun'):
    """Compute values plus eligibility and sensitivity to admissible readings.

    Point estimates use resolved outcomes. Bounds use the larger set of positions
    with all candidate labels available. Stage 3 pair proposals have disjoint endpoints.
    """
    lines = clauses(passage)
    slots = [slot for line in lines for slot in line]
    lengths = [len(line) for line in lines]
    ends = [line[-1] for line in lines]
    paired = parallel_sides(passage, lines)
    paired_ends = [(left[-1], right[-1]) for left, right in paired]

    def tone(slot):
        return reading_values(slot, tier, 'pingze')

    def initial(slot):
        return reading_values(slot, tier, 'initial')

    def final(slot):
        return reading_values(slot, tier, 'final')

    def rhyme(slot):
        return reading_values(slot, tier, 'rhyme')

    return {
        'clause_mean_slots': estimates_from_values(lengths),
        'clause_sd_slots': length_spread(lengths, stdev, minimum=2),
        'clause_variance_slots': length_spread(lengths, pvariance, minimum=1),
        'clause_npvi': estimates_from_values(200 * abs(left - right) / (left + right)
                                             for left, right in zip(lengths, lengths[1:])),
        'clause_46_share': estimates_from_values(length in (4, 6) for length in lengths),
        'internal_boundary_rate': estimates_from_values(slot.get('boundary_after', 0) > 0 for slot in slots[:-1]),
        'ping_share': ping_share(slots, tier),
        'syllable_pz_alternation': relation_rate(lines, tone, ne),
        'foot_pz_alternation': relation_rate((line[1::2] for line in lines), tone, ne),
        'clause_end_pz_alternation': relation_rate((ends,), tone, ne),
        'adjacent_han_repeat': relation_rate(lines, lambda slot: (slot['char'],), eq),
        'adjacent_initial_repeat': relation_rate(lines, initial, eq),
        'adjacent_final_repeat': relation_rate(lines, final, eq),
        'clause_end_rhyme_repeat': relation_rate((ends,), rhyme, eq),
        'parallel_length_similarity': estimates_from_values(min(len(left), len(right)) / max(len(left), len(right))
                                                           for left, right in paired),
        'parallel_end_pz_opposition': relation_rate(paired_ends, tone, ne),
        'parallel_end_zp_share': relation_rate(paired_ends, tone, lambda left, right: (left, right) == ('仄', '平')),
    }


def text_metrics(passage, tier='guangyun'):
    """Return the passage-level point estimates used by validation and comparison."""
    return {name: estimate.value for name, estimate in metric_results(passage, tier).items()}


def text_metric_support(passage, tier='guangyun'):
    """Return serializable estimates with the point and sensitivity denominators."""
    return {name: asdict(estimate) for name, estimate in metric_results(passage, tier).items()}
