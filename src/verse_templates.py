"""Tonal verse profiles and ordered alignment for annotated parallel clauses."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite


TONES = frozenset('PZ')
FIVE_CHARACTER_TYPES = {'A': 'ZZPPZ', 'B': 'PPZZP', 'C': 'PPPZZ', 'D': 'ZZZPP'}
SEVEN_CHARACTER_TYPES = {
    name: ('ZZ' if pattern[0] == 'P' else 'PP') + pattern
    for name, pattern in FIVE_CHARACTER_TYPES.items()
}
PATTERNS = {5: FIVE_CHARACTER_TYPES, 7: SEVEN_CHARACTER_TYPES}


def bamboo_window(width, phase):
    """Return an exact window of Qigong's PPZZ sequence."""
    if width <= 0 or phase not in range(4):
        raise ValueError('A window needs positive width and a zero-based phase of 0–3')
    return ''.join('PPZZ'[(phase + index) % 4] for index in range(width))


@dataclass(frozen=True)
class Alignment:
    cost: float
    path: tuple[tuple[int | None, int | None], ...]
    optimal_paths: int


def _minimum_path(m, n, match_cost, gap_cost):
    if not isfinite(gap_cost) or gap_cost <= 0:
        raise ValueError('Gap cost must be finite and positive')
    costs = [[0.0] * (n + 1) for _ in range(m + 1)]
    counts = [[1] * (n + 1) for _ in range(m + 1)]
    previous = [[None] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        costs[i][0], previous[i][0] = i * gap_cost, (i - 1, 0)
    for j in range(1, n + 1):
        costs[0][j], previous[0][j] = j * gap_cost, (0, j - 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            choices = (
                (costs[i - 1][j - 1] + match_cost(i - 1, j - 1), (i - 1, j - 1)),
                (costs[i - 1][j] + gap_cost, (i - 1, j)),
                (costs[i][j - 1] + gap_cost, (i, j - 1)),
            )
            cost, predecessor = min(choices, key=lambda choice: choice[0])
            costs[i][j], previous[i][j] = cost, predecessor
            counts[i][j] = sum(counts[x][y] for value, (x, y) in choices if isclose(value, cost))
    path = []
    i, j = m, n
    while i or j:
        x, y = previous[i][j]
        path.append((x if x < i else None, y if y < j else None))
        i, j = x, y
    return Alignment(costs[m][n], tuple(reversed(path)), counts[m][n])


def weighted_tone_edit(observed, template, *, mismatch_weights=None, gap_cost=1.0):
    """Align a resolved P/Z line to a template with tone-flexible slots (X)."""
    if set(observed) - TONES or not template or set(template) - (TONES | {'X'}):
        raise ValueError('Observed tones require resolved P/Z labels and templates accept P/Z/X')
    weights = (1.0,) * len(template) if mismatch_weights is None else tuple(mismatch_weights)
    if len(weights) != len(template) or any(not isfinite(weight) or weight < 0 for weight in weights):
        raise ValueError('Provide one nonnegative finite mismatch weight per template position')

    def mismatch(i, j):
        return weights[j] if template[j] not in ('X', observed[i]) else 0.0

    return _minimum_path(len(observed), len(template), mismatch, gap_cost)


@dataclass(frozen=True)
class RegulatedFit:
    line_types: str
    first_line_rhymes: bool
    mismatches: tuple[tuple[int, ...], ...]

    @property
    def cost(self):
        return sum(map(len, self.mismatches))


def match_regulated_poem(lines, *, profile='strict', first_line_rhymes=None):
    """Return all best tonal fits to level-rhyme four- and eight-line forms.

    The literal odd-position mask exempts positions 1 and 3, plus 5 in a
    seven-character line. Rhyme-group membership and additional constraints
    such as 孤平 are external to this tonal-only comparison.
    """
    lines = tuple(lines)
    width = len(lines[0]) if lines else 0
    if len(lines) not in (4, 8) or width not in PATTERNS or any(len(line) != width for line in lines):
        raise ValueError('Expected four or eight lines of uniformly five or seven positions')
    if any(set(line) - TONES for line in lines):
        raise ValueError('Template matching requires resolved historical P/Z labels')
    if profile not in ('strict', 'literal_odd'):
        raise ValueError('Unknown tonal template profile')
    if first_line_rhymes is not None and not isinstance(first_line_rhymes, bool):
        raise ValueError('Specify a Boolean first-line rhyme branch or allow both')

    required = tuple(i for i in range(width) if profile == 'strict' or i % 2 or i == width - 1)
    branches = (False, True) if first_line_rhymes is None else (first_line_rhymes,)
    fits = []
    for body in ('ABCD', 'CDAB'):
        for rhyming in branches:
            initial = body[-1] + body[1:] if rhyming else body
            pattern = initial + (body if len(lines) == 8 else '')
            mismatches = tuple(
                tuple(i for i in required if line[i] != PATTERNS[width][name][i])
                for line, name in zip(lines, pattern)
            )
            fits.append(RegulatedFit(pattern, rhyming, mismatches))
    best = min(fit.cost for fit in fits)
    return tuple(fit for fit in fits if fit.cost == best)


@dataclass(frozen=True)
class ParallelToken:
    syllables: int
    pos: str | None = None
    role: str | None = None
    semantic: str | None = None
    tones: tuple[str | None, ...] = ()

    def __post_init__(self):
        if self.syllables < 1 or self.tones and len(self.tones) != self.syllables:
            raise ValueError('Token width must be positive and agree with supplied tone slots')
        if set(self.tones) - (TONES | {None}):
            raise ValueError('Token tones must be P, Z, or explicitly missing')


@dataclass(frozen=True)
class ParallelFit:
    alignment: Alignment
    length_similarity: float
    normalized_cost: float
    gaps: int
    agreement_counts: dict[str, tuple[int, int]]


def _agreement(left, right):
    evidence = {}
    for field in ('pos', 'role', 'semantic'):
        a, b = getattr(left, field), getattr(right, field)
        known = a is not None and b is not None
        evidence[field] = (int(known and a == b), int(known))
    # Positional pairing only makes sense for equally wide tokens.
    tones = [(a, b) for a, b in zip(left.tones, right.tones) if a is not None and b is not None]
    if left.syllables != right.syllables:
        tones = []
    evidence['tone_opposition'] = (sum(a != b for a, b in tones), len(tones))
    return evidence


def align_parallel_tokens(left, right, *, weights=None, gap_cost=0.6):
    """Align annotated tokens with a frozen, explicit set of active dimensions."""
    left, right = tuple(left), tuple(right)
    if not left or not right:
        raise ValueError('Both sides require at least one token')
    weights = {'pos': 0.30, 'role': 0.30} if weights is None else weights
    if not weights or set(weights) - {'pos', 'role', 'semantic', 'tone_opposition'} or any(
        not isfinite(weight) or weight <= 0 for weight in weights.values()
    ):
        raise ValueError('Provide positive finite weights for supported active dimensions')

    def cost(i, j):
        evidence = _agreement(left[i], right[j])
        value = 0.0
        for field, weight in weights.items():
            agreement, eligible = evidence[field]
            required = left[i].syllables if field == 'tone_opposition' else 1
            if eligible != required:
                raise ValueError(f'Missing or incomparable active annotation: {field}')
            value += weight * (1 - agreement / eligible)
        return value

    alignment = _minimum_path(len(left), len(right), cost, gap_cost)
    counts = {field: (0, 0) for field in ('pos', 'role', 'semantic', 'tone_opposition')}
    gaps = 0
    for i, j in alignment.path:
        if i is None or j is None:
            gaps += 1
            continue
        for field, (matches, eligible) in _agreement(left[i], right[j]).items():
            old_matches, old_eligible = counts[field]
            counts[field] = old_matches + matches, old_eligible + eligible
    n_left = sum(token.syllables for token in left)
    n_right = sum(token.syllables for token in right)
    length_similarity = min(n_left, n_right) / max(n_left, n_right)
    normalized = alignment.cost / (gap_cost * (len(left) + len(right)))
    return ParallelFit(alignment, length_similarity, normalized, gaps, counts)
