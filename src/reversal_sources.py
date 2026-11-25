"""Acquire fresh Tang witnesses for the reversal transfer experiment."""
from collections import Counter
from itertools import zip_longest
from pathlib import Path
import re
import sys

from .semantic_turn_sources import catalogue, fetch_works, parse_candidate, title_genre
from .semantic_turn_pairs import normalized, prepare
from .semicolon_turn_sources import closing_pair, eligible_sentences, reserve_previous
from .semicolon_turn_sensitivity import strict_shape
from .yu_review_sources import digest, save
from .yu_review_transfer import read


def exact(text):
    return bool(re.fullmatch(r"[^，,；;。！？]+[，,][^，,；;。！？]+[；;][^，,；;。！？]+[，,][^，,；;。！？]+[。！？]", text)
                and all(len(normalized(x)) == 4 for x in re.split("[，,；;]", text)))


def spaced(items, n):
    return [items[(2*j+1)*len(items)//(2*n)] for j in range(n)]


def acquire(root, run, superseded=None):
    out = run/"inputs"
    if (out/"source-seal.json").exists():
        raise FileExistsError("Source packet already sealed")
    catalog, editions = out/"catalog", out/"editions"
    for p in (catalog, editions):
        p.mkdir(exist_ok=True)
    excluded=(run, superseded) if superseded else (run,)
    authors, titles, protected, prior, variants = reserve_previous(root, excluded)
    def key(s):
        return normalized(s).translate(variants)
    if key("劉知幾") in authors:
        authors.update(key(s) for s in ("劉子元","劉子玄"))
    for pat in ("semicolon-author-heldout-*", "semicolon-turn-*"):
        for p in (root/"results").glob(pat+"/inputs/fetched-revisions.json"):
            titles.update(key(s) for s in read(p))
            prior[str(p.relative_to(root))] = digest(p.read_bytes())
            history = read(p.parent/"corpus.json")
            protected.update(key(r["text"]) for r in history)
    volumes = [110+(83+149*k)%762 for k in range(240)]
    cats = catalogue(catalog, volumes)
    pools = []
    for v in volumes:
        if v in cats:
            names = re.findall(r"^\s*\{\{:([^{}]+)\}\}\s*$", cats[v].read_text(), re.M)
            pools.append([n for n in names if title_genre(n) in set("表啟箋牋序書檄") and key(n) not in titles])
    names = list(dict.fromkeys(n for level in zip_longest(*pools) for n in level if n))[:1000]
    fetched = out/"fetched-revisions.json"
    manifest = read(fetched) if fetched.exists() else {}
    chosen, reserve, log = [], [], []
    def admit(item):
        a,t,_,_,groups,_,_=item
        chosen.append(item)
        authors.add(key(a))
        titles.add(key(t))
        protected.update("".join(key(s) for s in g) for g in groups)
    def assess(name):
        rid=manifest.get(name)
        if rid is None:
            return "unavailable"
        a,t,_,groups=parse_candidate((editions/f"{rid}.wiki").read_text(),name)
        if key(a) in authors or key(t) in titles:
            return "reserved"
        units=[s for g in groups for s in g]
        elig=[i for i in eligible_sentences(groups,protected,variants)
              if strict_shape(dict(text=units[i],**{k:closing_pair(units[i])[k] for k in ("first","second")}))[0]]
        if len(elig)<3:
            return "fewer than three"
        literal=[i for i in elig if exact(units[i])]
        item=(a,t,name,rid,groups,elig,literal)
        if literal:
            admit(item)
            return "selected"
        reserve.append(item)
        return "reserve"
    for start in range(0,len(names),15):
        batch=names[start:start+15]
        fetch_works(editions,batch,manifest)
        for n in batch:
            try:
                reason=assess(n)
            except ValueError as exc:
                reason=str(exc)
            log.append((n,reason))
            if len(chosen)==7:
                break
        if start%90==0 or len(chosen)==7:
            print(len(log),len(chosen),len(reserve),flush=True)
        if len(chosen)==7:
            break
    for item in reserve:
        if len(chosen)>=7:
            break
        a,t,_,_,groups,elig,_=item
        units=[s for g in groups for s in g]
        if key(a) not in authors and key(t) not in titles and not any(key(units[i]) in p for i in elig for p in protected):
            admit(item)
    if not chosen:
        raise ValueError("Empty source frame")
    corpus, works=[],[]
    for k,(a,t,name,rid,groups,elig,literal) in enumerate(chosen,1):
        wid=f"W{k:02}"
        targets=set(spaced(literal,min(6,len(literal))))
        remaining=[i for i in elig if i not in literal]
        targets.update(spaced(remaining,min(6-len(targets),len(remaining))))
        idx=0
        for j,g in enumerate(groups,1):
            for s in g:
                para=f"P{j:02}"
                corpus.append(dict(id=f"{wid}S{idx+1:03}",work_id=wid,paragraph=para,section=para,
                                   order=idx+1,text=s,target=idx in targets))
                idx+=1
        works.append(dict(work_id=wid,title=t,author=a,genre=title_genre(name),revision=rid,
                          source_url=f"https://zh.wikisource.org/w/index.php?oldid={rid}",
                          rights="Ancient work public domain. Wikisource contributors CC BY-SA 4.0.",
                          sha256=digest((editions/f"{rid}.wiki").read_bytes()),exact=len(set(literal)&targets),n=len(targets)))
    save(out/"sources.json",dict(works=works,screened=log,frame=len(names),prior=prior))
    save(out/"corpus.json",corpus)
    prepare(run)
    save(out/"source-seal.json",{n:digest((out/n).read_bytes()) for n in ("corpus.json","sources.json","pair-packet.json")})
    print("sealed",len(works),sum(w["n"] for w in works),sum(w["exact"] for w in works),flush=True)


if __name__=="__main__":
    acquire(*(Path(x) for x in sys.argv[1:]))
