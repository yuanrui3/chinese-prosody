"""Describe prose rhythm with edition-pinned or candidate historical readings."""

import hashlib
from itertools import groupby
import re

from data.phonology.annotate import annotate_passage, syllable_slots
from data.phonology.historical import GUANGYUN_REVISION, GUANGYUN_URL, PINGSHUI_REVISION, PINGSHUI_URL
from src.text_metrics import clauses, slot_label, text_metric_support


PRIMARY_TIER = 'guangyun'
HISTORICAL_REFERENCES = {
    'guangyun': {'title': '廣韻', 'revision_id': GUANGYUN_REVISION, 'source_url': GUANGYUN_URL},
    'pingshui': {'title': '平水韻', 'revision_id': PINGSHUI_REVISION, 'source_url': PINGSHUI_URL},
}
WITNESS_FIELDS = (
    'source_id', 'work_id', 'title', 'author', 'date', 'period', 'wiki_title', 'revision_id',
    'source_url', 'work_rights', 'license', 'attribution', 'genre', 'pair_id', 'subset', 'start_anchor',
    'end_anchor', 'edit', 'criticism',
)
PARAGRAPH_BREAK = re.compile(r'\r?\n[^\S\r\n]*\r?\n(?:[^\S\r\n]*\r?\n)*')


def annotate_text(text, *, guangyun=None, pingshui=None, mandarin=None, variants=None,
                  pinned_passage=None, passage_id=None):
    """Return Stage 3-compatible slots, preserving the exact supplied string."""
    checksum = hashlib.sha256(text.encode('utf-8')).hexdigest()
    if pinned_passage is not None:
        pinned_id = pinned_passage['passage_id']
        if passage_id is not None and passage_id != pinned_id:
            raise ValueError('Passage identifier differs from the pinned annotation')
        if text != pinned_passage['text'] or checksum != pinned_passage['text_sha256']:
            raise ValueError(f'Input text differs from the pinned edition for {pinned_id}')
        expected = syllable_slots(text)
        slots = pinned_passage['slots']
        if len(slots) != len(expected) or any(
            any(actual.get(key) != value for key, value in slot.items())
            for actual, slot in zip(slots, expected)
        ):
            raise ValueError(f'Pinned syllable offsets or boundaries are stale for {pinned_id}')
        return {**pinned_passage, 'annotation_source': 'pinned_pilot'}

    lexicons = {'guangyun': guangyun, 'pingshui': pingshui, 'mandarin': mandarin, 'cantonese': None}
    record = {
        'passage_id': passage_id or f'text-{checksum[:12]}',
        'text_sha256': checksum,
        'text': text,
        'annotation_source': 'candidate_lookup',
        'loaded_tiers': [tier for tier, index in lexicons.items() if index is not None],
    }
    return annotate_passage(record, {tier: index or {} for tier, index in lexicons.items()}, variants or {}, ())


def paragraph_spans(text):
    """Yield offsets for nonempty spans split at blank lines."""
    start = 0
    for break_match in PARAGRAPH_BREAK.finditer(text):
        end = break_match.start()
        if text[start:end].strip():
            yield start, end
        start = break_match.end()
    if text[start:].strip():
        yield start, len(text)


def score_components(slots, parallel_groups=()):
    passage = {'slots': slots, 'parallel_clause_groups': parallel_groups}
    return {tier: text_metric_support(passage, tier) for tier in HISTORICAL_REFERENCES}


def add_observation(observations, metric, lines, strength, severity, reason):
    observations.append({
        'metric': metric,
        'clause_indices': [line[0]['clause_index'] for line in lines],
        'severity': severity,
        'evidence': strength,
        'historical_tier': PRIMARY_TIER if metric in (
            'parallel_end_pz_opposition', 'clause_end_pz_alternation', 'clause_end_rhyme_repeat'
        ) else None,
        'reason': reason,
    })


def annotated_pair_observations(lines, parallel_groups, observations):
    by_index = {line[0]['clause_index']: line for line in lines}
    for left, right in parallel_groups:
        sides = [[by_index[index] for index in side] for side in (left, right)]
        affected = sides[0] + sides[1]
        a, b = (sum(len(line) for line in side) for side in sides)
        if a != b:
            add_observation(observations, 'parallel_length_similarity', affected, 'reviewed_pair',
                            abs(a - b) / max(a, b), f'The two annotated parallel sides have {a} and {b} Han slots.')
        tone_a, tone_b = (slot_label(side[-1][-1], PRIMARY_TIER, 'pingze') for side in sides)
        if tone_a is not None and tone_a == tone_b:
            add_observation(observations, 'parallel_end_pz_opposition', affected, 'reviewed_pair', 1.0,
                            f'Both annotated parallel sides end in historical {tone_a} in the 廣韻 categories.')


def sequence_observations(lines, observations):
    def show_change(groups, metric, minimum, describe):
        for (before, old), (after, new) in zip(groups, groups[1:]):
            if before is None or after is None or len(old) < minimum:
                continue
            reason, severity = describe(before, after, old, new)
            if reason:
                add_observation(observations, metric, old + new[:1], 'local_pattern', severity, reason)

    length_groups = [(length, list(group)) for length, group in groupby(lines, key=len)]

    def length_change(before, after, old, new):
        difference = abs(after - before)
        following = (f'one {after}-slot clause' if len(new) == 1
                     else f'{len(new)} consecutive {after}-slot clauses')
        reason = f'{len(old)} consecutive {before}-slot clauses are followed by {following}.'
        return reason if difference >= 2 else None, difference / max(before, after)

    show_change(length_groups, 'clause_npvi', 2, length_change)

    rhyme_groups = [(rhyme, list(group)) for rhyme, group in groupby(
        lines, key=lambda line: slot_label(line[-1], PRIMARY_TIER, 'rhyme')
    )]
    show_change(rhyme_groups, 'clause_end_rhyme_repeat', 3, lambda before, after, old, _new: (
        f'After {len(old)} endings in historical rhyme group {before}, the next ending has group {after}.', 1.0
    ))

    tones = [slot_label(line[-1], PRIMARY_TIER, 'pingze') for line in lines]
    for index in range(3, len(lines)):
        a, b, c, d = tones[index - 3:index + 1]
        if None not in (a, b, c, d) and a != b and b != c and c == d:
            add_observation(observations, 'clause_end_pz_alternation', lines[index - 3:index + 1],
                            'local_pattern', 1.0,
                            f'Three alternating historical endings are followed by another {d} ending.')


def score_passage(passage):
    """Score a validated annotation with global clause indices and source spans."""
    text = passage['text']
    all_lines = clauses(passage)
    all_pairs = passage.get('parallel_clause_groups', ())
    references = {
        tier: {**source, 'available': any(slot.get('readings', {}).get(tier, {}).get('candidates')
                                         for slot in passage['slots'])}
        for tier, source in HISTORICAL_REFERENCES.items()
    }
    pinned = passage.get('annotation_source') == 'pinned_pilot'
    witness = {field: passage[field] for field in WITNESS_FIELDS if field in passage} if pinned else None
    report = {
        'passage_id': passage['passage_id'],
        'text_sha256': passage['text_sha256'],
        'text': text,
        'reference': {
            'annotation_source': passage.get('annotation_source', 'provided_annotation'),
            'historical': references,
            'primary_historical_tier': PRIMARY_TIER,
            'witness': witness,
            'offsets': 'Zero-based Unicode code point offsets with exclusive ends.',
            'segmentation': 'Blank lines separate paragraphs. Stage 3 punctuation and single newlines delimit clauses.',
            'document_scope': 'Stage 5 metrics applied to the entire text. Document adjacency can cross paragraphs.',
        },
        'metrics': score_components(passage['slots'], all_pairs),
        'paragraphs': [],
        'observations': [],
    }
    pending = iter(all_lines)
    line = next(pending, None)
    for paragraph_index, (start, end) in enumerate(paragraph_spans(text)):
        lines = []
        while line and line[0]['offset'] < end:
            lines.append(line)
            line = next(pending, None)
        indices = {line[0]['clause_index'] for line in lines}
        pairs = [(left, right) for left, right in all_pairs if indices.issuperset(left + right)]
        paragraph = {
            'paragraph_index': paragraph_index,
            'start': start,
            'end': end,
            'text': text[start:end],
            'metrics': score_components([slot for line in lines for slot in line], pairs),
            'clauses': [],
        }
        for position, slots in enumerate(lines):
            clause_start = slots[0]['offset'] if position else start
            clause_end = lines[position + 1][0]['offset'] if position + 1 < len(lines) else end
            paragraph['clauses'].append({
                'clause_index': slots[0]['clause_index'],
                'start': clause_start,
                'end': clause_end,
                'text': text[clause_start:clause_end],
                'slots': slots,
                'metrics': score_components(slots),
            })
        report['paragraphs'].append(paragraph)
        sequence_observations(lines, report['observations'])
    annotated_pair_observations(all_lines, all_pairs, report['observations'])
    report['observations'].sort(key=lambda item: (item['evidence'] != 'reviewed_pair', -item['severity'],
                                                   item['clause_indices'], item['metric']))
    for rank, item in enumerate(report['observations'], 1):
        item['rank'] = rank
    return report


def score_text(text, **options):
    """Annotate and score arbitrary text or an exact passage from the pilot."""
    return score_passage(annotate_text(text, **options))
