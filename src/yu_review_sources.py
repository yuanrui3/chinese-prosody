"""Freeze a work-held-out, full-sentence sample of Tang parallel prose from pinned editions."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from unicodedata import normalize

from .contrast_answer_sources import get


# Four distinct authors per genre, in priority order. Within each author use the
# first eligible witness. These choices do not read model or editorial grades.
CANDIDATES = {
    "表": (
        ("權德輿", (("中書門下賀南詔異牟尋授冊禮畢表", 485346), ("中書門下賀雲南軍破吐蕃劍山保定城表", 485359))),
        ("獨孤及", (("請降誕日置天興節表", 484956),)),
        ("錢珝", (("宰相諫罷討伐請不幸奉天表", 2632493),)),
        ("裴度", (("代李大夫請朝覲表", 497521),)),
        ("武元衡", (("賀連理棠樹合歡瓜白兔表", 1978154),)),
        ("苗晉卿", (("上肅宗辭攝塚宰表", 1979372),)),
        ("令狐楚", (("代鄭尚書賀登極表", 497553),)),
        ("鄭畋", (("擢官自陳表", 1975235),)),
    ),
    "啟": (
        ("顧雲", (("代青州掌記謝本府辟啟", 2632220), ("投顧端公啟", 1973891))),
        ("羅隱", (("投前夏口韋尚書啟", 1974657), ("投禮部鄭員外啟", 1974749))),
        ("黃滔", (("薛推先輩啟", 1979602), ("南海韋尚書啟", 2632481))),
        ("薛逢", (("上翰林韋學士啟", 1975882), ("上前鄭滑周尚書啟", 1973543))),
    ),
}
SENTENCES = re.compile(r'[^。！？]+[。！？]+[」』”’]*')
VERSE = re.compile(r'(?:其[詞辭]|[詩歌銘頌]|繫|亂)曰[：:]')
FRESHNESS_PATTERNS = (
    'results/*/inputs/*witness.json', 'results/*/inputs/works.json',
    'results/*/provenance/*works.json', 'results/*/inputs/*sources.json',
    'results/grammatical-training-expansion-*/inputs/train-?.json',
    'results/grammatical-training-expansion-*/inputs/holdout.json',
    'results/grammatical-training-expansion-*/results/enriched-reference.json',
    'results/*/witness.json', 'results/ai-jiangnan-complete-*/units.json',
    'results/cadence-completion-20261123/inputs/candidate-index.json',
    'results/cadence-completion-20261123/code/data/pilot/*.json',
    'results/exact-tie-targets-*/provenance/*witness.json',
)
N = 8


def norm(text):
    return re.sub(r'[^\u3400-\u9fff\U00020000-\U0003134f]', '', normalize('NFKC', text))


def digest(value):
    return sha256(value).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def reservations(root, excluded_runs=()):
    authors, titles, sentences, inputs = {'庾信'}, {'哀江南賦', '哀江南賦序'}, set(), {}
    paths = sorted({p for pat in FRESHNESS_PATTERNS for p in root.glob(pat)
                    if not any(run in p.parents for run in excluded_runs)})
    required = ('cadence-completion-20261123/inputs/witness.json',
                'contrast-answer-20261123/inputs/witness.json',
                'exact-tie-targets-20261122/inputs/witness.json',
                'grammatical-training-expansion-20261122/results/enriched-reference.json')
    if not all(any(str(p).endswith(name) for p in paths) for name in required):
        raise ValueError('Prior study archives incomplete')

    def visit(x):
        if isinstance(x, list):
            for item in x:
                visit(item)
        elif isinstance(x, dict):
            if isinstance(x.get('author'), str):
                authors.add(norm(x['author']))
            if isinstance(x.get('title'), str):
                titles.add(norm(x['title']))
            if isinstance(x.get('text'), str):
                sentences.add(norm(x['text']))
                sentences.update(norm(t) for t in re.split('[；。！？]', x['text']) if norm(t))
            for k, v in x.items():
                if k.startswith('Author:'):
                    authors.add(norm(k[7:]))
                if isinstance(v, (dict, list)):
                    visit(v)
    for p in paths:
        raw = p.read_bytes()
        visit(json.loads(raw))
        inputs[str(p.relative_to(root))] = digest(raw)
    return authors, titles, sentences, inputs


def body(raw, title, author):
    for key, expected in (('title', title), ('author', author), ('times', '唐')):
        m = re.search(r'\|\s*' + key + r'\s*=\s*([^\n|}]+)', raw, re.I)
        if not m or m[1].strip() != expected:
            raise ValueError(f'{title}: {key} differs from source card')
    edition = re.search(r'\|\s*from\s*=\s*(全唐文/卷[0-9]+)', raw)
    blocks = re.findall(r'<onlyinclude>(.*?)</onlyinclude>', raw, re.S)
    if len(blocks) != 1 or not edition or VERSE.search(blocks[0]) or re.search(r'[{}\[\]<>□�]', blocks[0]):
        raise ValueError(f'{title}: mixed or unresolved source')
    paragraphs = []
    for line in blocks[0].splitlines():
        text = ''.join(line.split())
        if text:
            units = SENTENCES.findall(text)
            if ''.join(units) != text:
                raise ValueError(f'{title}: sentence or trailing material unresolved')
            paragraphs.append(units)
    return paragraphs, edition[1]


def balanced(text):
    arms = [norm(v) for v in re.split('[，；：。！？]', text) if norm(v)]
    return any(len(a) >= 3 and abs(len(a) - len(b)) <= 1 for a, b in zip(arms, arms[1:]))


def acquire(root, folder):
    folder.mkdir(parents=True, exist_ok=True)
    editions = folder / 'editions'
    editions.mkdir(exist_ok=True)
    if (folder / 'source-seal.json').exists():
        raise FileExistsError('Use the frozen inputs, or specify a new directory for a rerun')
    authors, titles, old, paths = reservations(root)
    works, corpus, packet, exclusions = [], [], [], []
    for genre, candidates in CANDIDATES.items():
        for author, options in candidates:
            if sum(w['genre'] == genre for w in works) == 4:
                break
            for title, rid in options:
                if norm(author) in authors or norm(title) in titles:
                    exclusions.append([title, 'previous author or work'])
                    continue
                raw_path = editions / f'{rid}.wiki'
                if not raw_path.exists():
                    page = get(revids=str(rid))[0]
                    rev = page['revisions'][0]
                    if page['title'] != title or rev['revid'] != rid:
                        raise ValueError('Requested edition identity mismatch')
                    raw_path.write_text(rev['slots']['main']['*'])
                raw = raw_path.read_text()
                paras, edition = body(raw, title, author)
                units = [t for p in paras for t in p]
                counts = Counter(norm(t) for t in units)
                eligible = [
                    i for i,t in enumerate(units)
                    if len(norm(t)) >= 6 and counts[norm(t)] == 1
                    and not any(key in old for key in [norm(t)] + [norm(a) for a in t.split('；') if norm(a)])
                ]
                examples = [t for t in units if balanced(t)]
                if len(eligible) < N or len(examples) < 3:
                    exclusions.append([title, 'fewer than eight eligible units or three paired sentences'])
                    continue
                chosen = {eligible[(2*i+1)*len(eligible)//(2*N)] for i in range(N)}
                wid = f'W{len(works)+1:02}'
                idx = 0
                for pn, group in enumerate(paras, 1):
                    par = f'P{pn:02}'
                    block = []
                    for text in group:
                        ident = f'{wid}S{idx+1:03}'
                        target = idx in chosen
                        corpus.append(dict(id=ident, work_id=wid, paragraph=par, section=par, order=idx+1,
                                           text=text, target=target))
                        block.append(dict(id=ident, text=text, target=target))
                        idx += 1
                    packet.append(dict(work_id=wid, paragraph=par, sentences=block))
                works.append(dict(work_id=wid, author=author, title=title, edition=edition, genre=genre,
                                  revision=rid, source_url=f'https://zh.wikisource.org/w/index.php?oldid={rid}',
                                  rights='Ancient text public domain; Chinese Wikisource contributors, CC BY-SA 4.0',
                                  wiki_sha256=digest(raw.encode()), sentences=len(units), eligible=len(eligible),
                                  targets=N, balanced_examples=examples[:3]))
                authors.add(norm(author))
                titles.add(norm(title))
                old.update(norm(t) for t in units)
                break
    if len(works) != 8:
        raise ValueError(f'Only {len(works)} works passed: {exclusions}')
    save(folder/'sources.json', dict(works=works, exclusions=exclusions, earlier_files=paths))
    save(folder/'corpus.json', corpus)
    save(folder/'reading.json', packet)
    seal = {n: digest((folder/n).read_bytes()) for n in ('corpus.json', 'reading.json', 'sources.json')}
    save(folder/'source-seal.json', seal)
    print(json.dumps(seal), flush=True)
    for w in works:
        print(w['work_id'], w['author'], w['title'], w['revision'], w['sentences'], w['eligible'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    acquire(args.root, args.folder)

