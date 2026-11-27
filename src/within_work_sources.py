"""Select the prospective held-out works for same-work ranking, without reading grades."""

import argparse
from collections import defaultdict
import json
from pathlib import Path

from . import work_weighted_sources as matched


LAST = 'equal-work-FvEkoQYG'
TARGETS = 8
VOLUME_OFFSET = 33


def reserve_logged_candidates(inputs, authors, titles, key):
    """Include catalogue-screened candidates that never reached the separate witness download."""
    source = json.loads((inputs / 'sources.json').read_bytes())
    names = set()
    for row in source['screened']:
        # The two earlier screen formats record [genre, page, reason] or [page, reason].
        names.add(row[-2])
    by_page = defaultdict(set)
    for basename, expected in source['catalogs'].items():
        path = inputs / 'catalog' / basename
        if matched.digest(path.read_bytes()) != expected:
            raise ValueError(f'Changed previously screened catalogue: {path}')
        for page, author, _, _ in matched.indexed_titles(path, int(basename.split('-')[0])):
            if page in names:
                by_page[page].add(author)
    titles.update(key(matched.base_title(name)) for name in names)
    authors.update(key(who) for group in by_page.values() for who in group)


def previous(root, run):
    reserved = matched.previous(root, run, minimum_span=6)
    matched.reserve_archive(root, LAST, reserved)
    authors, titles, spans, files, key, revisions, missing = reserved
    for study in (matched.LAST, LAST):
        archive = root / 'results' / study
        for inputs in (archive / 'inputs', archive / 'screening-original' / 'inputs'):
            reserve_logged_candidates(inputs, authors, titles, key)
    # Include short, exact targets and intact paragraph text throughout the prior sentence corpora.
    for path in sorted((root / 'results').glob('*/inputs/corpus.json')):
        if run in path.parents:
            continue
        data = json.loads(path.read_bytes())
        if not isinstance(data, list):
            continue
        paragraphs = defaultdict(list)
        for row in data:
            if not isinstance(row, dict) or not isinstance(row.get('text'), str):
                continue
            text = key(row['text'])
            if len(text) >= 6:
                spans.add(text)
            if 'work_id' in row and ('paragraph' in row or 'section' in row):
                paragraphs[row['work_id'], row.get('paragraph', row.get('section'))].append(text)
        spans.update(''.join(section) for section in paragraphs.values())
        files[str(path.relative_to(root))] = matched.digest(path.read_bytes())
    return reserved


def acquire(root, run):
    matched.acquire(root, run, count=TARGETS, reserve=previous, volume_offset=VOLUME_OFFSET, check_exact=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    acquire(args.root, args.run)
