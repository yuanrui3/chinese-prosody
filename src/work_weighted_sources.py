"""Seal period-matched Tang regulated fu and discursive prose for the equal-work test."""

import argparse
from collections import Counter, defaultdict, deque
from itertools import zip_longest
import json
from pathlib import Path
import re
from shutil import copyfile

from .masked_rhyme_sources import FIELD, base_title, parse
from .semantic_turn_sources import catalogue, fetch_works, parse_candidate, title_genre
from .written_rhyme_sources import DESIGN_VOLUMES, blind_packet, period_evidence, reservations
from .yu_review_sources import balanced, digest, save


LAST = 'written-rhyme-DvfWnBBA'
TARGETS = 6
PAIRS = 8
DISCURSIVE = {'論', '議', '記'}
GAP = r'[闕阙缺脫脱佚泐]'
COUNT = r'[數数若干一二兩两三四五六七八九十百千廿卅零〇0-9０-９]+'
LACUNA = re.compile(
    rf'[□■▢�]|{GAP}{COUNT}[字句行段葉页頁]|'
    rf'[（(〔【](?:此處|此处|此|原本|原|上|下|中|本)?(?:文)?{GAP}'
    rf'(?:文|佚|略)?(?:{COUNT})?(?:[字句行段葉页頁])?[。.]?[）)〕】]')
MIDDLE = ('至德', '乾元', '寶應', '廣德', '永泰', '大曆', '建中', '興元', '貞元', '永貞', '元和',
          '肅宗', '代宗', '德宗', '順宗', '憲宗')
LATE = ('長慶', '寶曆', '大和', '太和', '開成', '會昌', '大中', '穆宗', '敬宗', '文宗', '武宗', '宣宗')
EARLY = ('武德', '貞觀', '永徽', '顯慶', '龍朔', '麟德', '乾封', '咸亨', '儀鳳', '垂拱', '天授',
         '長壽', '萬歲通天', '聖曆', '久視', '長安', '神龍', '景龍', '景雲', '先天', '開元', '天寶',
         '高祖', '太宗', '高宗', '中宗', '睿宗', '玄宗', '元宗')


def stratum(marker):
    for label, names in (('through-Xuanzong', EARLY), ('Suzong-through-Xianzong', MIDDLE),
                         ('Muzong-through-Xuanzong-II', LATE)):
        if marker.startswith(names):
            return label
    raise ValueError(f'unmapped Tang court marker: {marker}')


def reserve_archive(root, study, reserved):
    authors, titles, spans, files, key, revisions, missing = reserved
    archive = root / 'results' / study
    for directory in (archive / 'inputs', archive / 'screening-original' / 'inputs'):
        seal = directory / 'source-seal.json'
        hashes = json.loads(seal.read_bytes())
        for name, expected in hashes.items():
            if digest((directory / name).read_bytes()) != expected:
                raise ValueError(f'Changed previous source input: {directory}/{name}')
        files[str(seal.relative_to(root))] = digest(seal.read_bytes())
        roster = json.loads((directory / 'sources.json').read_bytes())['works']
        if len({w['author'] for w in roster}) != 16:
            raise ValueError(f'Incomplete previous work roster in {directory}')
        for w in roster:
            authors.add(key(w['author']))
            titles.add(key(base_title(w['title'])))
        spans.update(key(r['text']) for r in json.loads((directory / 'corpus.json').read_bytes()))
        for name, revision in json.loads((directory / 'fetched-revisions.json').read_bytes()).items():
            titles.add(key(base_title(name)))
            revisions.add(revision)
            witness = directory / 'editions' / f'{revision}.wiki'
            match = re.search(FIELD % 'author', witness.read_text(), re.I)
            if match and re.fullmatch(r'[\u3400-\u9fff]{2,5}', match[1].strip()):
                authors.add(key(match[1].strip()))


def previous(root, run, minimum_span=12):
    reserved = reservations(root, run)
    reserve_archive(root, LAST, reserved)
    authors, titles, spans, files, key, revisions, missing = reserved
    if key('房元齡') in authors:
        authors.update(key(x) for x in ('房玄齡', '房喬'))
    return authors, titles, {s for s in spans if len(s) >= minimum_span}, files, key, revisions, missing


def build_rows(wid, author, genre, groups, key, count=TARGETS):
    rows = []
    for paragraph, group in enumerate(groups, 1):
        for text in group:
            index = len(rows) + 1
            rows.append(dict(id=f'{wid}-S{index:03}', work_id=wid, order=index, text=text, genre=genre,
                             author=author, section=f'P{paragraph:02}', paragraph=f'P{paragraph:02}', target=False))
    normalized = [key(r['text']) for r in rows]
    counts = Counter(normalized)
    candidates = [i for i, s in enumerate(normalized) if len(s) >= 6 and counts[s] == 1]
    if len(candidates) < count:
        label = 'six' if count == 6 else str(count)
        raise ValueError(f'fewer than {label} unique complete sentences of six or more characters')
    for j in range(count):
        rows[candidates[(2*j+1) * len(candidates) // (2*count)]]['target'] = True
    return rows


def read_work(raw, name, genre):
    if genre == 'fu':
        author, title, edition, groups, _ = parse(raw, name, 'fu')
    else:
        if title_genre(name) not in DISCURSIVE or re.search(r'為韻|並序|并序|并詩|並詩|并銘|並銘', name):
            raise ValueError('outside discursive prose forms')
        author, title, edition, groups = parse_candidate(raw, name)
        if title_genre(title) not in DISCURSIVE or '為韻' in title:
            raise ValueError('unsupported discursive edition title')
        if sum(map(len, groups)) < 8 or max(map(len, groups), default=0) < 4:
            raise ValueError('insufficient editorial endings or paragraph context')
    if any(LACUNA.search(sentence) for group in groups for sentence in group):
        raise ValueError('explicit lacuna in the source text')
    return author, title, edition, groups


def indexed_titles(catalog, volume):
    """Traverse the actual author block before issuing any per-work network request."""
    raw = catalog.read_text()
    heads = list(re.finditer(r'^([=]+)[ \t]*([^=\n]+?)[ \t]*\1[ \t]*$', raw, re.M))
    result = []
    for i, head in enumerate(heads):
        name = head[2].strip()
        match = re.fullmatch(r'\[\[Author:([^|\]]+)(?:\|[^\]]+)?\]\]', name, re.I)
        author = match[1] if match else name
        if not re.fullmatch(r'[\u3400-\u9fff]{2,5}', author):
            continue
        end = next((h.start() for h in heads[i+1:] if len(h[1]) <= len(head[1])), len(raw))
        block = raw[head.end():end]
        for page in re.findall(r'^\s*\{\{:([^{}]+)\}\}\s*$', block, re.M):
            form = title_genre(page)
            if form in DISCURSIVE or form == '賦':
                result.append((page, author, volume, 'fu' if form == '賦' else 'prose'))
    return result


def acquire(root, run, *, count=TARGETS, reserve=previous, volume_offset=183, check_exact=False):
    out = run / 'inputs'
    catalogs, editions = out / 'catalog', out / 'editions'
    for p in (catalogs, editions):
        p.mkdir(parents=True, exist_ok=True)
    if (out / 'source-seal.json').exists():
        raise FileExistsError('Use the sealed packet or a fresh run folder')
    authors, titles, protected, prior, key, old_revs, missing = reserve(root, run)
    reserved = dict(authors=len(authors), titles=len(titles), long_spans=sum(len(s) >= 12 for s in protected), revisions=len(old_revs))
    # Long spans may include whole paragraphs from earlier studies.
    long_spans = {s for s in protected if len(s) >= 12}
    existing = {}
    for p in sorted((root / 'results').glob('*/inputs/catalog/*.wiki')):
        if run not in p.parents and p.stem.split('-')[0].isdecimal():
            existing.setdefault(int(p.stem.split('-')[0]), p)
    manifest_file = out / 'fetched-revisions.json'
    fetched = json.loads(manifest_file.read_bytes()) if manifest_file.exists() else {}
    pending = defaultdict(lambda: {'fu': deque(), 'prose': deque()})
    pairs, log, seen = [], [], set()
    rotation = [120 + (volume_offset + 131*i) % 680 for i in range(680)]
    volumes = [v for v in rotation if v not in DESIGN_VOLUMES]
    for start in range(0, len(volumes), 50):
        chunk = volumes[start:start+50]
        for v in chunk:
            if v in existing and not list(catalogs.glob(f'{v}-*.wiki')):
                copyfile(existing[v], catalogs / existing[v].name)
        paths = catalogue(catalogs, chunk)
        raw_catalogs = {v:p.read_text() for v,p in paths.items()}
        volumes_rows = [indexed_titles(paths[v], v) for v in chunk if v in paths]
        options = []
        for level in zip_longest(*volumes_rows):
            for candidate in level:
                if candidate is None:
                    continue
                page, author, v, genre = candidate
                if page in seen or key(author) in authors or key(base_title(page)) in titles:
                    continue
                seen.add(page)
                try:
                    period = period_evidence(raw_catalogs[v], author, page, page, v)
                    period.update(catalog_revision=int(paths[v].stem.split('-')[1]), stratum=stratum(period['marker']))
                    options.append((page, author, v, genre, period))
                except ValueError as exc:
                    log.append([page, str(exc)])
        for offset in range(0, len(options), 15):
            batch = options[offset:offset+15]
            mobile = [name for name, author, _, _, _ in batch if key(author) not in authors]
            if mobile:
                fetch_works(editions, mobile, fetched)
            for name, expected_author, v, genre, period in batch:
                try:
                    if key(expected_author) in authors or key(base_title(name)) in titles:
                        raise ValueError('author or title already retained')
                    revision = fetched.get(name)
                    if revision is None or revision in old_revs:
                        raise ValueError('missing or reserved witness revision')
                    path = editions / f'{revision}.wiki'
                    author, title, edition, groups = read_work(path.read_text(), name, genre)
                    if author != expected_author or int(edition.split('卷')[-1]) != v:
                        raise ValueError('catalogue author or edition disagrees with work')
                    sentences = [key(t) for g in groups for t in g]
                    arms = {key(a) for g in groups for t in g for a in t.split('；')}
                    if check_exact and any(t in protected for t in sentences if len(t) >= 6):
                        raise ValueError('identical earlier sentence')
                    if any(t in p for t in set(sentences) | arms if len(t) >= 12 for p in long_spans):
                        raise ValueError('previous long sentence or semicolon arm')
                    build_rows('screen', author, genre, groups, key, count)
                    card = dict(author=author, title=title, page=name, genre=genre, form=title_genre(title),
                                period_evidence=period, dynasty='唐', edition=edition, revision=revision,
                                wiki_sha256=digest(path.read_bytes()), source_url=f'https://zh.wikisource.org/w/index.php?oldid={revision}',
                                sentences=len(sentences), targets=count,
                                rights='Ancient text public domain. Chinese Wikisource contributors CC BY-SA 4.0.')
                    authors.add(key(author))
                    titles.add(key(base_title(title)))
                    long_spans.update(''.join(key(t) for t in group) for group in groups)
                    if check_exact:
                        protected.update(sentences)
                    pool = pending[period['stratum']]
                    pool[genre].append((card, groups))
                    if pool['fu'] and pool['prose']:
                        pair = [pool[g].popleft() for g in ('fu', 'prose')]
                        pairs.append(pair)
                        print('Matched pair', len(pairs), period['stratum'], [r[0]['author'] for r in pair], flush=True)
                    reason = 'eligible ' + period['stratum']
                except ValueError as exc:
                    reason = str(exc)
                log.append([name, reason])
                if len(pairs) == PAIRS:
                    break
            if len(pairs) == PAIRS:
                break
        if len(pairs) == PAIRS:
            break
    if len(pairs) != PAIRS:
        save(out / 'incomplete-source-screen.json', log)
        raise ValueError(f'Only {len(pairs)} era-matched author pairs')
    works, corpus = [], []
    for pair_id, pair in enumerate(pairs, 1):
        for card, groups in pair:
            wid = f'W{len(works)+1:02}'
            rows = build_rows(wid, card['author'], card['genre'], groups, key, count)
            works.append(dict(card, work_id=wid, period_pair=pair_id,
                              sentences_with_length_matched_clauses=sum(balanced(r['text']) for r in rows)))
            corpus.extend(rows)
    reading, blind_key = blind_packet(corpus)
    for name, data in [('corpus.json', corpus), ('reading.json', reading), ('reader-key.json', blind_key)]:
        save(out / name, data)
    save(out / 'sources.json', dict(works=works, screened=log, reserved=reserved, earlier_files=prior,
                                    unavailable_previous_editions=missing, catalogs={
                                        p.name:digest(p.read_bytes()) for p in sorted(catalogs.glob('*.wiki'))}))
    names = ('corpus.json', 'reading.json', 'reader-key.json', 'sources.json', 'fetched-revisions.json')
    save(out / 'source-seal.json', {n:digest((out / n).read_bytes()) for n in names})
    print(f'Sealed {len(pairs)} matched pairs, {len(reading)} targets, {len(corpus)} context rows.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    acquire(args.root, args.run)
