"""Apply cited historical reading decisions to exact occurrences in a text witness."""

from functools import lru_cache
import json
from pathlib import Path

from data.phonology.annotate import annotation, passage_decisions
from src.text_metrics import reading_values


CATALOG = Path(__file__).resolve().parents[1] / 'data/phonology/documented-readings.json'
HISTORICAL_TIERS = ('guangyun', 'pingshui')


@lru_cache(maxsize=1)
def reading_catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


def apply_historical_readings(passage, decisions=None):
    automatic = decisions is None
    notes = []
    if automatic:
        decisions = []
        for entry in reading_catalog():
            if any(k in entry and entry[k] != passage.get(k) for k in ('passage_id', 'text_sha256')):
                continue
            anchor = entry['anchor']
            start = passage['text'].find(anchor)
            if start < 0:
                continue
            if passage['text'].find(anchor, start + 1) >= 0:
                notes.append(f'Repeated quotation {anchor!r}. A longer occurrence-specific review is needed.')
            else:
                decisions.append(entry)
    if not isinstance(decisions, (list, tuple)):
        raise ValueError('Historical reading reviews must be a JSON array')
    locations = passage_decisions(passage, decisions)
    if any(tier not in HISTORICAL_TIERS for _, tier in locations):
        raise ValueError('Historical reading reviews require the guangyun or pingshui tier')
    if not locations and not notes:
        return passage
    slots = passage['slots'].copy()
    positions = {slot['offset']: i for i, slot in enumerate(slots)}
    for (offset, tier), decision in locations.items():
        i = positions[offset]
        slot = slots[i]
        current = slot['readings'].get(tier, {'candidates': [], 'lookup': 'none'})
        if automatic and not current['candidates']:
            notes.append(f"{decision['anchor']} · {slot['char']} @ {offset}: no {tier} dictionary candidates "
                         f"available for this occurrence. Source: {decision['source']}")
            continue
        try:
            reviewed = annotation(current['candidates'], current['lookup'], decision)
            if current.get('selected') is not None and current['selected'] != reviewed['selected']:
                raise ValueError('Conflicts with the existing witness review')
        except ValueError as exc:
            if not automatic:
                raise
            notes.append(f"{decision['anchor']} · {slot['char']} @ {offset} ({tier}): {exc}")
            continue
        reviewed['evidence'].update({k: decision[k] for k in ('anchor', 'offset', 'witness', 'cited_reading')
                                     if k in decision})
        if current.get('selected') is not None:
            sources = [current['evidence'], *current.get('additional_evidence', [])]
            if reviewed['evidence'] in sources:
                continue
            reviewed = {**current, 'additional_evidence': [*sources[1:], reviewed['evidence']]}
        slots[i] = {**slot, 'readings': {**slot['readings'], tier: reviewed}}
    return {**passage, 'slots': slots, 'historical_reading_notes': notes}


def tone_profile(slots, tier):
    """Bound the longest run of level syllables over all admissible readings."""
    pattern = []
    forced = possible = lower = upper = 0
    complete = True
    for slot in slots:
        values = reading_values(slot, tier, 'pingze')
        complete = complete and bool(values)
        pattern.append(next(iter(values)) if len(values) == 1 else '?')
        forced = forced + 1 if values == {'平'} else 0
        possible = possible + 1 if '平' in values else 0
        lower, upper = max(lower, forced), max(upper, possible)
    return {'pattern': ''.join(pattern), 'longest_level_run': [lower, upper] if complete else None}
