"""Seal Tang assigned-rhyme fu and dynasty-matched parallel prose by different authors."""

import argparse
from collections import Counter
from itertools import zip_longest
import json
from pathlib import Path
import re
from shutil import copyfile

from .semantic_turn_sources import catalogue, fetch_works, title_genre
from .semicolon_turn_sources import reserve_previous
from .yu_review_sources import SENTENCES, balanced, digest, norm, save


DEV = {"fu": 4, "prose": 4}
GOAL = {"fu": 16, "prose": 14}
GENRES = {"表", "啟", "箋", "牋"}
FIELD = r"\|\s*%s\s*=\s*([^\n|}]+)"
RUBRIC = re.compile(r'以[「『“]([^」』”]+)[」』”]為韻')
DESIGN_TITLES = """至人用心若鏡賦 慶雲抱日賦 塤篪相須賦 鄒子吹律賦 律中黃鍾賦 賦賦 六藝賦
漢文帝罷露台賦 石韞玉賦 兩階舞干羽賦 謝加正議大夫表""".split()
DESIGN_AUTHORS = """紇干俞 范鳴鶴 張季友 賈謩 成表微 楊汝士 滕邁 陳越石 韋處元 李淑 蘇冕 席夔 許康佐 許堯佐
封希顏 閻伯璵 平冽 裴度 歐陽詹 李程 王起 白居易""".split()
PROJECT = Path(__file__).resolve().parents[1]


def base_title(name):
    return re.split(r'[（(]', name, 1)[0].strip()


def reserve(root, run):
    authors, titles, spans, files, variants = reserve_previous(root, (run,))
    def key(value):
        return norm(value).translate(variants)
    authors.update(key(x) for x in DESIGN_AUTHORS)
    titles.update(key(x) for x in DESIGN_TITLES)
    for name in ('critic-reading-cases.json', 'critic-reading-addendum.json'):
        path = PROJECT / 'research' / name
        objects = json.loads(path.read_text())
        for case in objects:
            authors.add(key(case['author']))
            titles.add(key(case['work']))
            spans.add(key(case['text']))
        files['code/research/' + name] = digest(path.read_bytes())
    # Reserve titles even when their earlier retrieval was just a screening
    # step. Catalogue-only mentions are not an evaluation of the work.
    for previous in sorted((root / 'results').glob('*/inputs/fetched-revisions.json')):
        if run in previous.parents or previous.parent.parent.name.startswith('masked-rhyme'):
            continue
        data = previous.read_bytes()
        titles.update(key(base_title(name)) for name in json.loads(data))
        files[str(previous.relative_to(root))] = digest(data)
    if key('劉知幾') in authors:
        authors.update(key(name) for name in ('劉子元', '劉子玄'))
    return authors, titles, spans, files, key


def parse(raw, page, genre):
    def field(name):
        match = re.search(FIELD % name, raw, re.I)
        if not match:
            raise ValueError('missing source field')
        return match[1].strip()
    title, author, period, collector = (field(k) for k in ('title', 'author', 'times', 'from'))
    if period != '唐' or not re.fullmatch(r'[\u3400-\u9fff]{2,5}', author) or author in ('佚名', '無名氏'):
        raise ValueError('unresolved author or dynasty')
    if base_title(title) != base_title(page) or not re.fullmatch(r'全唐文/卷\d+', collector):
        raise ValueError('heading/collection mismatch')
    rubric = RUBRIC.search(title)
    if genre == 'fu' and (not rubric or len(norm(rubric[1])) < 3 or norm(rubric[1]) in ('以題為韻', '題中之字')):
        raise ValueError('no explicit assigned rhyming characters')
    if genre == 'prose' and (rubric or '為韻' in title):
        raise ValueError('rhymed title')
    blocks = re.findall(r'<onlyinclude>(.*?)</onlyinclude>', raw, re.S)
    if len(blocks) != 1 or re.search(r'[{}\[\]<>□�]', blocks[0]):
        raise ValueError('missing or marked-up body')
    if re.search(r'(?:並序|并序|有序|附序|序曰|(?:其[詞辭]|[詩歌銘頌]|亂|賦)曰[：:])', title + blocks[0]):
        raise ValueError('preface, quotation, or mixed form')
    groups = []
    for line in blocks[0].splitlines():
        line = ''.join(line.split())
        if line:
            units = SENTENCES.findall(line)
            if ''.join(units) != line or not all(norm(s) for s in units):
                raise ValueError('unresolved sentence punctuation')
            groups.append(units)
    sentences = [s for units in groups for s in units]
    if len(sentences) < 8 or max(map(len, groups), default=0) < 4:
        raise ValueError('insufficient editorial endings or paragraph context')
    if genre == 'prose' and sum(balanced(s) for s in sentences) < 3:
        raise ValueError('insufficient paired phrasing')
    return author, title, collector, groups, norm(rubric[1]) if rubric else ''


def catalogue_rows(folder, volumes):
    # Existing copies are immutable revision snapshots. Prefer the same oldid
    # deterministically when more than one earlier experiment kept the volume.
    result = catalogue(folder, volumes)
    pools = []
    for v in volumes:
        if v in result:
            names = re.findall(r'^\s*\{\{:([^{}]+)\}\}\s*$', result[v].read_text(), re.M)
            pools.append(names)
    return list(dict.fromkeys(name for level in zip_longest(*pools) for name in level if name))


def acquire(root, run):
    output = run / 'inputs'
    catalogs, editions = output / 'catalog', output / 'editions'
    for p in (catalogs, editions):
        p.mkdir(parents=True, exist_ok=True)
    if (output / 'source-seal.json').exists():
        raise FileExistsError('Source packet already sealed')
    authors, titles, spans, previous, key = reserve(root, run)
    state = dict(authors=len(authors), titles=len(titles), spans=len(spans))
    reserved_spans = {s for s in spans if len(s) >= 12}
    existing = {}
    for previous_catalog in sorted((root / 'results').glob('*/inputs/catalog/*.wiki')):
        if run in previous_catalog.parents:
            continue
        stem = previous_catalog.name.split('-')[0]
        if stem.isdecimal():
            existing.setdefault(int(stem), previous_catalog)
    written = output / 'fetched-revisions.json'
    revisions = json.loads(written.read_text()) if written.exists() else {}
    selected, rows, log = [], [], []
    counts, screened = Counter(), set()
    # Rotate through the whole Tang anthology, interleaving volumes before
    # taking a second entry from the same volume. Selection sees no lexicon.
    priority = [622, 631, 630, 624, 625, 623, 635]
    rotating = [90 + (17 + 173*i) % 810 for i in range(810)]
    volumes = list(dict.fromkeys(v for v in priority + rotating if v not in (282, 395, 406, 537, 595, 632, 633, 641, 656, 723)))
    for offset in range(0, len(volumes), 45):
        chunk = volumes[offset:offset+45]
        for v in chunk:
            if v in existing and not list(catalogs.glob(f'{v}-*.wiki')):
                path = existing[v]
                copyfile(path, catalogs / path.name)
        names = catalogue_rows(catalogs, chunk)
        classified = {
            'fu': [n for n in names if title_genre(n) == '賦' and '序' not in n.split('賦', 1)[-1]],
            'prose': [n for n in names if title_genre(n) in GENRES]
        }
        # Explicitly marked fu first, preserving catalogue order within strata.
        classified['fu'].sort(key=lambda n: '為韻' not in n)
        for genre, pool in classified.items():
            pool = [n for n in pool if key(base_title(n)) not in titles and n not in screened]
            for start in range(0, len(pool), 15):
                if counts[genre] >= GOAL[genre]:
                    break
                batch = pool[start:start+15]
                fetch_works(editions, batch, revisions)
                for name in batch:
                    if counts[genre] >= GOAL[genre]:
                        break
                    screened.add(name)
                    try:
                        if name not in revisions:
                            raise ValueError('source unavailable')
                        rev = revisions[name]
                        path = editions / f'{rev}.wiki'
                        a, t, edition, groups, assigned = parse(path.read_text(), name, genre)
                        if key(a) in authors or key(base_title(t)) in titles:
                            raise ValueError('author or work already used')
                        # Require no earlier complete long sentence or long
                        # semicolon arm embedded at this work's sentence ends.
                        arms = {key(arm) for g in groups for s in g for arm in [s, *s.split('；')]}
                        if any(arm in s for arm in arms if len(arm) >= 12 for s in reserved_spans):
                            raise ValueError('previously used wording')
                        counts[genre] += 1
                        idx = counts[genre]
                        split = 'development' if idx <= DEV[genre] else 'test'
                        wid = ('F' if genre == 'fu' else 'P') + f'{idx:02}'
                        card = dict(work_id=wid, genre=genre, split=split, author=a, title=t, page=name,
                                    edition=edition, form=title_genre(name), dynasty='唐', revision=rev,
                                    source_url=f'https://zh.wikisource.org/w/index.php?oldid={rev}',
                                    sha256=digest(path.read_bytes()), assigned_rhyme_chars=assigned,
                                    rights='Ancient work public domain. Chinese Wikisource contributors CC BY-SA 4.0.')
                        selected.append(card)
                        for p, group in enumerate(groups, 1):
                            for j, text in enumerate(group, 1):
                                rows.append(dict(work_id=wid, genre=genre, split=split, author=a, section=f'P{p:02}',
                                                 id=f'{wid}-P{p:02}-S{j:03}', text=text,
                                                 rubric_literal_final=norm(text)[-1] in set(assigned)))
                        authors.add(key(a))
                        titles.add(key(base_title(t)))
                        reserved_spans.update(''.join(key(s) for s in g) for g in groups)
                        why = f'accepted {wid} {a}'
                        print(why, t, flush=True)
                    except ValueError as error:
                        why = str(error)
                    log.append([genre, name, why])
        print('screened', len(log), 'selected', dict(counts), flush=True)
        if all(counts[k] >= n for k, n in GOAL.items()):
            break
    save(output / 'sources.json', dict(works=selected, screened=log, reserved=state,
                                      earlier_files=previous, catalogue_revisions={
                                          p.name:digest(p.read_bytes()) for p in sorted(catalogs.glob('*.wiki'))}))
    if not all(counts[k] > DEV[k] for k in GOAL):
        raise ValueError(f'Insufficient eligible sources: {dict(counts)}')
    save(output / 'rows.json', rows)
    files = ('rows.json', 'sources.json', 'fetched-revisions.json')
    save(output / 'source-seal.json', {f:digest((output / f).read_bytes()) for f in files})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    acquire(args.root, args.run)
