"""Recheck the prior study inventory for titles and exact target wording on Gilbreth."""

from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote


PRIOR_STUDY = 'critical-preferences-5JRVYyHR'
LATER_STUDIES = (PRIOR_STUDY, 'documented-readings-5QJhKL2r', 'sun-critic-screen-jPKfc1gh')
TEXT_SUFFIXES = {'.json', '.txt', '.md', '.wiki', '.jsonl'}
EXCLUDED_DIRECTORIES = {'code', 'exposure', 'audio-24', '__pycache__', 'cache'}
SOURCE_DIRECTORIES = {'editions', 'witnesses'}
VARIANT_CHARACTERS = {
    '茍': '苟', '飜': '翻', '黒': '黑', '兹': '兹',
    '于': '于', '於': '于', '鳯': '凤', '徤': '健',
}


def translation_table(prior):
    # Replay the same per-character conversion with the archived OpenCC library.
    sys.path.insert(0, str(prior / 'opencc-lib'))
    from opencc import OpenCC

    converter = OpenCC('t2s')
    table = {code: converter.convert(chr(code)) for code in range(0x3400, 0xa000)}
    table.update(str.maketrans(VARIANT_CHARACTERS))
    return table


def normalize(text, table):
    decoded = html.unescape(unquote(text))
    converted = unicodedata.normalize('NFKC', decoded).translate(table)
    return re.sub(r'[^\u3400-\u9fff]', '', converted)


def inventory_files(root, prior):
    inventory = json.loads((prior / 'inventory.json').read_text())
    for relative_path, kind, _, checksum in inventory:
        if relative_path.startswith('stage-docs/'):
            path = prior / relative_path.removeprefix('stage-docs/')
        else:
            path = root / relative_path
        yield path, kind, checksum

    for study in LATER_STUDIES:
        for path in (root / 'results' / study).rglob('*'):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            if EXCLUDED_DIRECTORIES.intersection(path.parts):
                continue
            kind = 'later-source' if SOURCE_DIRECTORIES.intersection(path.parts) else 'later-study'
            yield path, kind, None


def decode_document(raw, suffix):
    text = raw.decode('utf-8-sig')
    if suffix == '.json':
        return json.dumps(json.loads(text), ensure_ascii=False)
    if suffix == '.jsonl':
        return ' '.join(json.dumps(json.loads(line), ensure_ascii=False)
                        for line in text.splitlines() if line.strip())
    return text


def document_hits(text, case_terms, kind, path, root):
    """Return the first matching alternative for each field, with the sealed 16-character context."""
    for field, alternatives in case_terms.items():
        for term in alternatives:
            start = text.find(term)
            if start >= 0:
                excerpt = text[max(0, start - 16):start + len(term) + 16]
                yield [field, kind, str(path.relative_to(root)), excerpt]
                break


def main():
    root, run = map(Path, sys.argv[1:])
    prior = root / 'results' / PRIOR_STUDY / 'exposure'
    table = translation_table(prior)
    cases = json.loads((run / 'inputs/packet.json').read_text())
    # Preserve the sealed inventory order, including any repeated files.
    files = list(inventory_files(root, prior))
    terms = {}
    for case in cases:
        titles = [case['work'], *case.get('aliases', [])]
        terms[case['id']] = {
            'title': list({normalize(title, table) for title in titles}),
            'passage': [normalize(case['text'], table)],
            'author': [normalize(case['author'], table)],
        }

    hits = {case_id: [] for case_id in terms}
    errors = []
    scanned = Counter()
    for path, kind, checksum in files:
        try:
            raw = path.read_bytes()
            if checksum and hashlib.sha256(raw).hexdigest() != checksum:
                errors.append([str(path), 'hash differs'])
            text = decode_document(raw, path.suffix)
        except (OSError, ValueError) as exc:
            errors.append([str(path), str(exc)])
            continue

        normalized = normalize(text, table)
        scanned[kind] += 1
        for case_id, case_terms in terms.items():
            hits[case_id].extend(document_hits(normalized, case_terms, kind, path, root))

    report = {'inventory': dict(scanned), 'errors': errors, 'hits': hits}
    (run / 'results/exposure.json').write_text(json.dumps(report, ensure_ascii=False))
    print('exposure', scanned, 'omissions/hash changes', len(errors))
    for case_id, matches in hits.items():
        counts = Counter((field, kind) for field, kind, *_ in matches if field != 'author')
        print(case_id, dict(counts))


if __name__ == '__main__':
    main()
