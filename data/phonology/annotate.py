"""Annotate passage JSONL without forcing a choice among heteronyms."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import tempfile
import unicodedata

if __package__:
    from .historical import fetch_historical, load_historical
    from .modern import fetch_modern, load_modern
else:
    from historical import fetch_historical, load_historical
    from modern import fetch_modern, load_modern


BOUNDARIES = {**dict.fromkeys(',，、', 1), **dict.fromkeys('.;!?。；！？', 2)}
TIERS = ('guangyun', 'pingshui', 'mandarin', 'cantonese')


def han(char):
    name = unicodedata.name(char, '')
    return char == '〇' or name.startswith(('CJK UNIFIED IDEOGRAPH-', 'CJK COMPATIBILITY IDEOGRAPH-'))


def syllable_slots(text):
    """Use zero-based Unicode offsets and punctuation-derived clause boundaries."""
    slots = []
    for offset, char in enumerate(text):
        if han(char):
            slots.append({'offset': offset, 'char': char, 'boundary_after': 0, 'marks_after': ''})
        elif slots:
            slots[-1]['marks_after'] += char
            degree = 3 if char == '\n' else BOUNDARIES.get(char, 0)
            slots[-1]['boundary_after'] = max(slots[-1]['boundary_after'], degree)
    clause = 0
    for index, slot in enumerate(slots):
        slot.update(slot_index=index, clause_index=clause)
        if slot['boundary_after']:
            clause += 1
    return slots


def candidates_for(char, index, variants):
    direct = index.get(char, [])
    if direct:
        return direct, 'exact'
    alternatives = [
        {**candidate, 'lookup_char': variant}
        for variant in variants.get(char, [])
        if variant != char
        for candidate in index.get(variant, [])
    ]
    return alternatives, 'traditional_variant' if alternatives else 'none'


def passage_decisions(record, decisions):
    """Reject stale or duplicate reviews before writing output."""
    locations = {}
    for decision in decisions:
        text = record['text']
        anchor = decision['anchor']
        offset = decision['offset']
        tier = decision['tier']
        start = text.find(anchor)
        if not anchor or start < 0 or text.find(anchor, start + 1) >= 0:
            raise ValueError(f"{record['passage_id']}: a review anchor must appear exactly once: {anchor!r}")
        if not 0 <= offset < len(anchor) or not han(anchor[offset]) or tier not in TIERS:
            raise ValueError(f"{record['passage_id']}: invalid reviewed character offset or tier")
        if not decision.get('source') or not decision.get('reason') or not decision.get('match'):
            raise ValueError(f"{record['passage_id']}: reviews require source, reason, and candidate selector")
        key = (start + offset, tier)
        if key in locations:
            raise ValueError(f"{record['passage_id']}: duplicate review for {key}")
        locations[key] = decision
    return locations


def annotation(candidates, method, decision):
    status = ('missing' if not candidates else 'ambiguous' if len(candidates) > 1
              else 'single_variant_candidate' if method == 'traditional_variant' else 'single_candidate')
    tier = {'status': status, 'lookup': method, 'candidates': candidates, 'selected': None}
    if decision:
        choices = [candidate for candidate in candidates
                   if all(candidate.get(key) == value for key, value in decision['match'].items())]
        if len(choices) != 1:
            raise ValueError(f"Review for {decision['anchor']!r} matches {len(choices)} candidates: {decision['match']}")
        tier.update(status='context_reviewed', selected=choices[0],
                    evidence={'source': decision['source'], 'reason': decision['reason']})
    return tier


def annotate_passage(record, lexicons, variants, decisions):
    locations = passage_decisions(record, decisions)
    slots = syllable_slots(record['text'])
    if not slots:
        raise ValueError(f"{record['passage_id']}: passage has no Han characters")
    for left, right in record.get('parallel_clause_groups', []):
        if (not left or not right or not 0 <= left[0] <= right[-1] <= slots[-1]['clause_index']
                or left + right != list(range(left[0], right[-1] + 1))):
            raise ValueError(f"{record['passage_id']}: invalid ordered parallel clause groups")
    for slot in slots:
        slot['readings'] = {}
        for tier in TIERS:
            candidates, method = candidates_for(slot['char'], lexicons[tier], variants)
            decision = locations.get((slot['offset'], tier))
            slot['readings'][tier] = annotation(candidates, method, decision)
    return {**record, 'annotation_schema': 1, 'slots': slots}


def annotate_file(input_path, output_path, lexicons, variants, overrides):
    decisions = defaultdict(list)
    for decision in overrides:
        decisions[decision['passage_id']].append(decision)
    seen = set()
    counts = {tier: Counter() for tier in TIERS}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_path.parent) as workspace:
        temporary = Path(workspace) / output_path.name
        with input_path.open(encoding='utf-8') as rows, temporary.open('w', encoding='utf-8') as output:
            for row in rows:
                if not row.strip():
                    continue
                record = json.loads(row)
                identifier = record['passage_id']
                if identifier in seen:
                    raise ValueError(f'Duplicate passage ID: {identifier}')
                seen.add(identifier)
                result = annotate_passage(record, lexicons, variants, decisions.get(identifier, []))
                for slot in result['slots']:
                    for tier, analysis in slot['readings'].items():
                        counts[tier][analysis['status']] += 1
                output.write(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
        if not seen or decisions.keys() - seen:
            raise ValueError(f'Empty input or unknown review passage IDs: {sorted(decisions.keys() - seen)}')
        temporary.replace(output_path)
    return {'passages': len(seen), 'slots': sum(counts['guangyun'].values()), 'coverage': counts}


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Gilbreth project root')
    parser.add_argument('--offline', action='store_true', help='Use previously cached source archives only')
    parser.add_argument('--overrides', type=Path, help='JSON array of reviewed context decisions')
    args = parser.parse_args()
    raw = args.root / 'data' / 'raw' / 'phonology'
    if not args.offline:
        fetch_historical(raw)
        fetch_modern(raw)
    historical = load_historical(raw)
    modern, variants = load_modern(raw)
    pilot = args.root / 'data' / 'pilot'
    overrides = json.loads(args.overrides.read_text(encoding='utf-8')) if args.overrides else []
    result = annotate_file(pilot / 'passages.jsonl', pilot / 'annotated.jsonl',
                           {**historical, **modern}, variants, overrides)
    result['raw_source_sha256'] = {
        path.name: sha256(path)
        for path in sorted(raw.iterdir()) if path.is_file()
    }
    with tempfile.TemporaryDirectory(dir=pilot) as workspace:
        summary = Path(workspace) / 'annotation-summary.json'
        summary.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        summary.replace(pilot / summary.name)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
