"""Check source independence and balance in the expanded pilot on Gilbreth."""

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import unicodedata

from src.pilot_validation import read_jsonl, write_json


TASKS = {'listening', 'read_aloud'}
PERIODS = {'sixth-century', 'early-tang'}


def authors(row):
    return {name for name in re.split(r'[、；,;，\s]+', unicodedata.normalize('NFKC', row['author'])) if name}


def validate(rows, original):
    known_works = {row['work_id'] for row in original}
    known_authors = set().union(*(authors(row) for row in original))
    seen_works, seen_authors, ids = set(), set(), set()
    pairs = defaultdict(list)
    coverage = defaultdict(Counter)
    if not known_works or not known_authors:
        raise ValueError('Independence requires the original reference inventory')
    for row in rows:
        author_set = authors(row)
        if (row['work_id'] in known_works | seen_works or not author_set
                or author_set & (known_authors | seen_authors)):
            raise ValueError(f"{row['passage_id']} reuses a source work or credited author")
        if row['passage_id'] in ids:
            raise ValueError('Duplicate expansion passage identifier')
        seen_works.add(row['work_id'])
        seen_authors.update(author_set)
        ids.add(row['passage_id'])
        pairs[row['pair_id']].append(row)
        slots = row['slots']
        if len(slots) != row['han_count']:
            raise ValueError(f"{row['passage_id']} has inconsistent annotation length")
        for slot in slots:
            for tier, reading in slot['readings'].items():
                coverage[tier][reading['status']] += 1

    assignments = Counter()
    result = []
    for pair, sides in sorted(pairs.items()):
        if len(sides) != 2 or {row['genre'] for row in sides} != {'parallel_prose', 'comparison_prose'}:
            raise ValueError(f'{pair} requires one parallel and one comparison passage')
        left, right = sides
        if any(left[field] != right[field] for field in ('period', 'task', 'match_topic')):
            raise ValueError(f'{pair} crosses periods, tasks, or matching topics')
        difference = abs(left['han_count'] - right['han_count'])
        if difference > 6:
            raise ValueError(f'{pair} exceeds the six-character matching margin')
        assignments[left['task'], left['period']] += 1
        result.append({'pair_id': pair, 'task': left['task'], 'period': left['period'],
                       'match_topic': left['match_topic'], 'han_counts': [row['han_count'] for row in sides]})
    expected = {(task, period): 1 for task in TASKS for period in PERIODS}
    if dict(assignments) != expected:
        raise ValueError('The expansion needs one pair in each historical period for each task')
    return {'passages': len(rows), 'independent_works': len(seen_works), 'credited_authors': len(seen_authors),
            'pair_count': len(pairs), 'pairs': result,
            'candidate_coverage': {tier: dict(counts) for tier, counts in coverage.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    data = args.root / 'data/pilot'
    summary = validate(read_jsonl(data / 'annotated.jsonl'), read_jsonl(args.reference))
    write_json(data / 'expansion-summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
