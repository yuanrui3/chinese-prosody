"""Work-held-out Tang prose with equal-width phrases, sampled without semantic labels."""

import argparse
import ast
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from time import sleep
from urllib.error import HTTPError

from .contrast_answer_sources import get
from .semantic_turn_pairs import normalized, select_pair
from .yu_review_sources import CANDIDATES, body, digest, norm, reservations, save


def editions_query(**params):
    for attempt in range(5):
        try:
            return get(**params)
        except HTTPError as error:
            if error.code not in (429, 502, 503, 504) or attempt == 4:
                raise
            delay = error.headers.get('Retry-After', '')
            sleep(max(2**attempt, int(delay) if delay.isdigit() else 10))


def exposure(root, excluded_runs=()):
    authors, titles, old, provenance = reservations(root, excluded_runs)
    for records in CANDIDATES.values():
        for author, works in records:
            authors.add(norm(author))
            titles.update(norm(w[0]) for w in works)
    past = root / 'results/cadence-completion-20261123'
    frozen = (past / 'code/src/cadence_completion.py').read_text()
    source_dict = next(ast.literal_eval(n.value) for n in ast.parse(frozen).body
                       if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                       and n.targets[0].id == 'SOURCES')
    for author, works in source_dict.items():
        authors.add(norm(author))
        titles.update(norm(w) for w in works)
    for works in json.loads((past / 'inputs/candidate-index.json').read_text()).values():
        titles.update(norm(w) for w in works)
    # Some earlier benchmarks split at semicolons. Rejoin earlier witnesses by
    # original work and paragraph to catch identical targets across that boundary.
    paths = [root / x for x in provenance if x.endswith(('witness.json', 'units.json'))]
    paths += list(root.glob('results/yu-review-transfer-*/inputs/corpus.json'))
    for path in paths:
        items = json.loads(path.read_text())
        if not isinstance(items, list):
            continue
        groups = defaultdict(list)
        for item in items:
            if isinstance(item, dict) and isinstance(item.get('text'), str):
                key = (item.get('work_id'), item.get('paragraph', item.get('section')))
                groups[key].append(normalized(item['text']))
        old.update(''.join(v) for v in groups.values() if v)
        provenance[str(path.relative_to(root))] = digest(path.read_bytes())
    return authors, titles, old, provenance


def catalogue(folder, volumes):
    """Cache the actual table-of-contents revision used to select each ordered list."""
    paths = {}
    missing = []
    for v in volumes:
        found = list(folder.glob(f'{v}-*.wiki'))
        if len(found) > 1:
            raise ValueError('Ambiguous frozen catalog revision')
        if found:
            paths[v] = found[0]
        else:
            missing.append(v)
    for off in range(0, len(missing), 15):
        query = '|'.join(f'全唐文/卷{n:04}' for n in missing[off:off+15])
        for p in editions_query(titles=query):
            if 'revisions' not in p:
                continue
            r = p['revisions'][0]
            v = int(p['title'].split('卷')[-1])
            paths[v] = folder / f'{v}-{r["revid"]}.wiki'
            paths[v].write_text(r['slots']['main']['*'])
    return paths


def title_genre(title):
    label = re.sub(r'\s*[（(].*', '', title)
    if not label or label.endswith(('墓表','阡表','年表','世表','詩集序')):
        return ''
    if label.endswith('書') and not re.match(r'^(?:上|與|答|寄|報|復|致|代|為|謝|賜)', label):
        return ''
    return label[-1]


def fetch_works(folder, names, manifest):
    missing = [n for n in names if n not in manifest]
    if missing:
        for p in editions_query(titles='|'.join(missing)):
            if 'revisions' in p:
                r = p['revisions'][0]
                manifest[p['title']] = r['revid']
                (folder / f'{r["revid"]}.wiki').write_text(r['slots']['main']['*'])
        save(folder.parent / 'fetched-revisions.json', manifest)


def parse_candidate(raw, title):
    author = re.search(r'\|\s*author\s*=\s*([^\n|}]+)', raw, re.I)
    header = re.search(r'\|\s*title\s*=\s*([^\n|}]+)', raw, re.I)
    if not author or not header:
        raise ValueError('missing author or title')
    a, t = author[1].strip(), header[1].strip()
    if not re.fullmatch(r'[\u3400-\u9fff]{2,5}', a):
        raise ValueError('ambiguous or collective attribution')
    if t not in (title, re.sub(r'\s*[（(].*','',title)):
        raise ValueError('edition heading differs from page title')
    paragraphs, edition = body(raw, t, a)
    if re.search(r'(?:詩|歌|頌|銘)(?:云|曰)[：:]|(?:其詞|其辭|亂)曰|其[一二三四][：:]', ''.join(''.join(g) for g in paragraphs)):
        raise ValueError('verse or separate document signalled')
    return a, t, edition, paragraphs


def acquire(root, out):
    out.mkdir(parents=True, exist_ok=True)
    if (out/'source-seal.json').exists():
        raise FileExistsError('Use a new run directory or replay the sealed packet')
    catalog, editions = out/'catalog', out/'editions'
    for p in (catalog, editions):
        p.mkdir(exist_ok=True)
    manifest = json.loads((out/'fetched-revisions.json').read_text()) if (out/'fetched-revisions.json').exists() else {}
    authors, titles, protected, archive = exposure(root)
    earlier_spans = len(protected)
    rejected, accepted, fallback, seen, index = [], [], [], set(), {}
    for start in range(200,211):
        volumes = catalogue(catalog, list(range(start,850,11)))
        index.update({v:p.name for v,p in volumes.items()})
        for genres in ('表啟','書序檄'):
            for vol, cp in sorted(volumes.items()):
                doc = cp.read_text()
                edition_titles = re.findall(r'^\s*\{\{:([^{}]+)\}\}\s*$',doc,re.M)
                names = [n for n in edition_titles if title_genre(n) in set(genres)][:8]
                fetch_works(editions, names, manifest)
                for title in names:
                    if title in seen:
                        continue
                    seen.add(title)
                    rid = manifest.get(title)
                    if rid is None:
                        rejected.append((title,'unavailable')); continue
                    raw = (editions/f'{rid}.wiki').read_text()
                    try:
                        a,t,edition,paragraphs = parse_candidate(raw,title)
                    except ValueError as error:
                        rejected.append((title,str(error))); continue
                    if norm(a) in authors or norm(t) in titles or norm(title) in titles:
                        rejected.append((title,'reserved author or work')); continue
                    units = [s for group in paragraphs for s in group]
                    keys = [normalized(s) for s in units]
                    counts = Counter(keys)
                    eligible = [i for i,(s,key) in enumerate(zip(units,keys)) if select_pair(s)
                                and counts[key] == 1 and not any(key in prev for prev in protected)]
                    record = (a,t,title_genre(title),rid,edition,paragraphs,eligible)
                    if len(eligible) >= 8:
                        accepted.append(record)
                        authors.add(norm(a)); titles.add(norm(t))
                        protected.update(''.join(normalized(s) for s in group) for group in paragraphs)
                    elif len(eligible) >= 6:
                        fallback.append(record)
                        rejected.append((title,'fallback pool: six or seven targets',len(eligible)))
                    else:
                        rejected.append((title,'fewer than six eligible sentences',len(eligible)))
                    if len(accepted) == 8:
                        break
                if len(accepted) == 8:
                    break
            if len(accepted) == 8:
                break
        if len(accepted) == 8:
            break
        # Prefer full-size candidates. After a complete catalog stride and
        # both genre classes the six/seven fallback may supply remaining authors.
        for rec in fallback:
            a,t,_,_,_,paras,indices=rec
            if norm(a) in authors or norm(t) in titles:
                continue
            all_s=[s for group in paras for s in group]
            eligible=[i for i in indices if not any(normalized(all_s[i]) in p for p in protected)]
            if len(eligible)<6:
                continue
            accepted.append((*rec[:-1],eligible))
            authors.add(norm(a)); titles.add(norm(t))
            protected.update(''.join(normalized(s) for s in group) for group in paras)
            if len(accepted)==8:
                break
        if len(accepted)==8:
            break
    if len(accepted)<6:
        raise ValueError(f'Only {len(accepted)} eligible authors')
    works, corpus, reading = [], [], []
    for k,(a,t,genre,rid,edition,paragraphs,eligible) in enumerate(accepted,1):
        wid=f'W{k:02}'; n=min(8,len(eligible))
        chosen={eligible[(2*i+1)*len(eligible)//(2*n)] for i in range(n)}
        idx=0
        for j,group in enumerate(paragraphs,1):
            group_id=f'P{j:02}'; sentences=[]
            for s in group:
                ident=f'{wid}S{idx+1:03}'
                row=dict(id=ident,text=s,target=idx in chosen)
                sentences.append(row)
                corpus.append(dict(**row,work_id=wid,order=idx+1,paragraph=group_id,section=group_id))
                idx+=1
            reading.append(dict(work_id=wid,paragraph=group_id,sentences=sentences))
        works.append(dict(work_id=wid,author=a,title=t,genre=genre,edition=edition,revision=rid,
                          source_url=f'https://zh.wikisource.org/w/index.php?oldid={rid}',
                          rights='Ancient text public domain; Wikisource contributors, CC BY-SA 4.0',
                          wiki_sha256=digest((editions/f'{rid}.wiki').read_bytes()),
                          sentences=idx, eligible=len(eligible), targets=n))
    save(out/'sources.json',dict(works=works,exclusions=rejected,earlier_files=archive,
                                 protected_spans=earlier_spans,index_volumes=index))
    save(out/'corpus.json',corpus)
    save(out/'reading.json',reading)
    save(out/'source-seal.json',{n:digest((out/n).read_bytes()) for n in ('sources.json','corpus.json','reading.json')})
    print(json.dumps(works,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('folder',type=Path)
    args=parser.parse_args()
    acquire(args.root,args.folder)
