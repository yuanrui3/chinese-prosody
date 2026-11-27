"""Seal a fresh Tang corpus and anonymously sample five sentences per work before scoring."""

import argparse
from collections import Counter
from itertools import groupby
import json
from pathlib import Path
from random import Random
import re
from shutil import copyfile

from .masked_rhyme_sources import FIELD, GENRES, PROJECT, base_title, catalogue_rows, parse, reserve
from .semantic_turn_sources import fetch_works, title_genre
from .yu_review_sources import digest, save


WORKS_PER_GENRE = 8
TARGETS = 5
SEED = 772643
LAST_STUDY = 'masked-rhyme-f8xpyOCv'
DESIGN_VOLUMES = {282, 395, 406, 537, 595, 632, 633, 641, 656, 723}


# These anthology volumes include a chronological spread within the Tang.
# For each work we still require affirmative period evidence under its own
# author's heading. The collection itself also contains Five Dynasties writing.
TANG_MARK = re.compile(
    r'武德|貞觀|永徽|顯慶|龍朔|麟德|乾封|咸亨|儀鳳|垂拱|天授|長壽|萬歲通天|'
    r'聖曆|久視|長安(?:中|末|初|[一二三四]年)|神龍|景龍|景雲|先天|開元|天寶|'
    r'至德|乾元|寶應|廣德|永泰|大曆|建中|興元|貞元|永貞|元和|長慶|'
    r'寶曆|大和|太和|開成|會昌|大中(?:中|末|初|時|朝|[一二三四五六七八九十]+年)|'
    r'(?:高祖|太宗|高宗|中宗|睿宗|玄宗|元宗|肅宗|代宗|德宗|順宗|憲宗|穆宗|'
    r'敬宗|文宗|武宗|宣宗)(?:朝|時|初|末|即位)')
LATER_COURT = re.compile(r'後唐|後晉|後漢|後周|後蜀|南唐|前蜀|吳越王|梁開平|周顯德|漢乾祐|周太祖|周世宗|入宋')
DISPUTED_AUTHORS = {'王樸', '徐鉉'}
DISPUTED_TITLES = {'奏進欽天曆表', '謝詔撰元宗實錄表'}


def period_evidence(raw_catalog, author, page, title, volume):
    if not 120 <= volume <= 799 or author in DISPUTED_AUTHORS or base_title(title) in DISPUTED_TITLES:
        raise ValueError('out of period or disputed source')
    headings = list(re.finditer(r'^([=]+)[ \t]*([^=\n]+?)[ \t]*\1[ \t]*$', raw_catalog, re.M))
    for i, head in enumerate(headings):
        text = head[2].strip()
        linked = re.fullmatch(r'\[\[Author:([^|\]]+)(?:\|[^\]]+)?\]\]', text, re.I)
        if (linked[1] if linked else text) != author:
            continue
        stop = next((h.start() for h in headings[i+1:] if len(h[1]) <= len(head[1])), len(raw_catalog))
        block = raw_catalog[head.end():stop]
        if '{{:' + page + '}}' not in block:
            continue
        # Only the anthology's author note is eligible as evidence. Exclude
        # dates in a literary title, a different author's note, or body text.
        bio_extent = headings[i+1].start() if i+1 < len(headings) else stop
        bio = raw_catalog[head.end():min(stop, bio_extent)].partition('{{:')[0].strip()
        match = TANG_MARK.search(bio)
        if match and not LATER_COURT.search(bio):
            passage = re.split('[。；]', bio[:match.start()])[-1] + match[0] + re.split('[。；]', bio[match.end():])[0]
            return dict(marker=match[0], text=passage.strip(), author=author)
    raise ValueError('no author-specific Tang period evidence for this work in its volume')


def reservations(root, run):
    authors, titles, spans, files, key = reserve(root, run)
    old = root / 'results' / LAST_STUDY / 'inputs'
    seal = json.loads((old / 'source-seal.json').read_bytes())
    for name, expected in seal.items():
        if digest((old / name).read_bytes()) != expected:
            raise ValueError(f'Changed previous masked-rhyme source packet: {name}')
    previous = json.loads((old / 'sources.json').read_bytes())['works']
    if len({w['author'] for w in previous}) != 30:
        raise ValueError('Expected all thirty previously selected authors')
    authors.update(key(w['author']) for w in previous)
    titles.update(key(base_title(w['title'])) for w in previous)
    spans.update(key(r['text']) for r in json.loads((old / 'rows.json').read_bytes()))
    files[str((old / 'source-seal.json').relative_to(root))] = digest((old / 'source-seal.json').read_bytes())
    critic_path = PROJECT / 'research/critic-variants.json'
    critic = json.loads(critic_path.read_bytes())
    for family in critic['families'].values():
        authors.update(key(a) for a in family['authors'])
        titles.add(key(family['title']))
    spans.update(key(x['text']) for x in critic['versions'])
    files['code/research/critic-variants.json'] = digest(critic_path.read_bytes())

    # Retain revision and title reservations even when a screened header lacks an
    # individual credit. Exclude positively identified screened authors as well.
    reserved_revisions, unavailable_headers = set(), []
    for index in sorted((root / 'results').glob('*/inputs/fetched-revisions.json')):
        if run in index.parents:
            continue
        files[str(index.relative_to(root))] = digest(index.read_bytes())
        for name, revision in json.loads(index.read_bytes()).items():
            titles.add(key(base_title(name)))
            path = index.parent / 'editions' / f'{revision}.wiki'
            reserved_revisions.add(revision)
            if not path.exists():
                unavailable_headers.append(str(path.relative_to(root)))
                continue
            match = re.search(FIELD % 'author', path.read_text(), re.I)
            if match and re.fullmatch(r'[\u3400-\u9fff]{2,5}', match[1].strip()):
                authors.add(key(match[1].strip()))
    # Two attested spellings for the previous test writer 徐寅.
    authors.update(key(v) for v in ('徐寅', '徐夤'))
    return authors, titles, spans, files, key, reserved_revisions, unavailable_headers


def work_rows(wid, author, genre, groups, key):
    flat = [sentence for group in groups for sentence in group]
    keys = [key(sentence) for sentence in flat]
    frequency = Counter(keys)
    eligible = [i for i, sentence in enumerate(keys) if len(sentence) >= 6 and frequency[sentence] == 1]
    if len(eligible) < TARGETS:
        raise ValueError('fewer than five unique complete sentences of six or more characters')
    chosen = {eligible[(2 * i + 1) * len(eligible) // (2 * TARGETS)] for i in range(TARGETS)}
    rows = []
    for number, group in enumerate(groups, 1):
        section = f'P{number:02}'
        for sentence in group:
            i = len(rows)
            rows.append(dict(id=f'{wid}-S{i+1:03}', work_id=wid, order=i+1, author=author, genre=genre,
                             section=section, paragraph=section, text=sentence, target=i in chosen))
    return rows


def blind_packet(rows):
    items = []
    for _, group in groupby(rows, lambda r: (r['work_id'], r['section'])):
        members = list(group)
        for i, r in enumerate(members):
            if r['target']:
                items.append((r['id'], dict(before=[n['text'] for n in members[max(0, i-2):i]],
                                             text=r['text'], after=[n['text'] for n in members[i+1:i+3]])))
    Random(SEED).shuffle(items)
    reading, key = [], {}
    for index, (ident, data) in enumerate(items, 1):
        blind = f'B{index:03}'
        reading.append(dict(blind_id=blind, **data))
        key[blind] = ident
    return reading, key


def acquire(root, run):
    output = run / 'inputs'
    catalogs, editions = output / 'catalog', output / 'editions'
    for folder in (catalogs, editions):
        folder.mkdir(parents=True, exist_ok=True)
    if (output / 'source-seal.json').exists():
        raise FileExistsError('Replay the sealed inputs or use a new output folder')
    authors, titles, spans, prior, key, reserved_revs, missing = reservations(root, run)
    counts_before = dict(authors=len(authors), titles=len(titles), spans=len(spans), revisions=len(reserved_revs))
    protected = {s for s in spans if len(s) >= 12}
    existing = {}
    for path in sorted((root / 'results').glob('*/inputs/catalog/*.wiki')):
        v = path.name.split('-')[0]
        if run not in path.parents and v.isdecimal():
            existing.setdefault(int(v), path)
    fetched_path = output / 'fetched-revisions.json'
    fetched = json.loads(fetched_path.read_bytes()) if fetched_path.exists() else {}
    seen, works, corpus, screened = set(), [], [], []
    counts = Counter()
    # Interleave the principal assigned-rhyme volumes with an anthology-wide
    # permutation. This order is independent of the phonological dictionary.
    priority = [626, 628, 629, 634, 636, 638, 639, 640, 643, 646, 647, 649, 653, 659, 662]
    rotating = [90 + (114 + 197*i) % 810 for i in range(810)]
    volumes = list(dict.fromkeys(v for v in priority + rotating if 120 <= v <= 799 and v not in DESIGN_VOLUMES))
    for offset in range(0, len(volumes), 45):
        chunk = volumes[offset:offset+45]
        for v in chunk:
            if v in existing and not list(catalogs.glob(f'{v}-*.wiki')):
                copyfile(existing[v], catalogs / existing[v].name)
        names = catalogue_rows(catalogs, chunk)
        pools = {'fu': [n for n in names if title_genre(n) == '賦'],
                 'prose': [n for n in names if title_genre(n) in GENRES]}
        pools['fu'].sort(key=lambda n: '為韻' not in n)
        for genre, pool in pools.items():
            available = [n for n in pool if key(base_title(n)) not in titles and n not in seen]
            for off in range(0, len(available), 15):
                if counts[genre] == WORKS_PER_GENRE:
                    break
                batch = available[off:off+15]
                fetch_works(editions, batch, fetched)
                for name in batch:
                    if counts[genre] == WORKS_PER_GENRE:
                        break
                    seen.add(name)
                    try:
                        revision = fetched.get(name)
                        if revision is None or revision in reserved_revs:
                            raise ValueError('missing or earlier edition revision')
                        path = editions / f'{revision}.wiki'
                        author, title, edition, groups, _ = parse(path.read_text(), name, genre)
                        if key(author) in authors or key(base_title(title)) in titles:
                            raise ValueError('previous author or work')
                        volume = int(edition.split('卷')[-1])
                        candidates = list(catalogs.glob(f'{volume}-*.wiki'))
                        if len(candidates) != 1:
                            raise ValueError('missing volume biography')
                        volume_path = candidates[0]
                        period = period_evidence(volume_path.read_text(), author, name, title, volume)
                        period['catalog_revision'] = int(volume_path.stem.split('-')[1])
                        sentences = [key(s) for group in groups for s in group]
                        arms = {key(arm) for group in groups for s in group for arm in s.split('；')}
                        if any(arm in old for arm in set(sentences) | arms if len(arm) >= 12 for old in protected):
                            raise ValueError('prior long sentence or semicolon arm')
                        wid = f'W{len(works)+1:02}'
                        rows = work_rows(wid, author, genre, groups, key)
                        works.append(dict(work_id=wid, author=author, title=title, page=name,
                                          genre=genre, form=title_genre(name), dynasty='唐', period_evidence=period, edition=edition,
                                          revision=revision, source_url=f'https://zh.wikisource.org/w/index.php?oldid={revision}',
                                          wiki_sha256=digest(path.read_bytes()), sentences=len(rows), targets=TARGETS,
                                          rights='Ancient text public domain. Chinese Wikisource contributors CC BY-SA 4.0.'))
                        corpus.extend(rows)
                        authors.add(key(author))
                        titles.add(key(base_title(title)))
                        protected.update(''.join(key(s) for s in group) for group in groups)
                        counts[genre] += 1
                        verdict = 'accepted ' + wid
                        print(verdict, genre, author, title, flush=True)
                    except ValueError as error:
                        verdict = str(error)
                    screened.append([genre, name, verdict])
        if all(counts[g] == WORKS_PER_GENRE for g in pools):
            break
    if any(counts[g] != WORKS_PER_GENRE for g in ('fu', 'prose')):
        save(output / 'incomplete-source-screen.json', screened)
        raise ValueError(f'Incomplete balanced sample: {dict(counts)}')
    reading, blind_key = blind_packet(corpus)
    save(output / 'corpus.json', corpus)
    save(output / 'reading.json', reading)
    save(output / 'reader-key.json', blind_key)
    save(output / 'sources.json', dict(works=works, screened=screened, reserved=counts_before,
                                      earlier_files=prior, unavailable_previous_editions=missing,
                                      catalogs={p.name: digest(p.read_bytes()) for p in sorted(catalogs.glob('*.wiki'))}))
    names = ('corpus.json', 'reading.json', 'reader-key.json', 'sources.json', 'fetched-revisions.json')
    save(output / 'source-seal.json', {name: digest((output / name).read_bytes()) for name in names})
    print(f'Sealed {len(works)} works, {len(reading)} targets, {len(corpus)} complete sentences', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path)
    options = parser.parse_args()
    acquire(options.root, options.run)
