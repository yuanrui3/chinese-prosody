"""Aggregate sealed challenge, editorial semantic, and musicality endpoints separately."""
from collections import Counter, defaultdict
from pathlib import Path
import sys

from .semantic_turn_relation import canonical, file_hash, seal
from .semantic_turn_test import shuffle_test, table
from .semicolon_turn_test import verified_votes
from .reversal_sources import exact
from .yu_review_transfer import prediction, read, summarize


def confusion(expected, flags):
    return table({i:v for i,v in expected.items() if v is not None},
                 {i:flags[i] for i,v in expected.items() if v is not None})


def evaluate(run):
    key=read(run/"private/key.json")
    revised=read(run/"private/revised.json")
    if (revised["packet_sha256"]!=file_hash(run/"inputs/inference.json")
            or revised["detector_sha256"]!=file_hash(run/"seals/detector.json")):
        raise ValueError("Wrong revised model or packet")
    prev=read(run/"previous/private/semantic-relation.json")
    if prev["packet_sha256"]!=file_hash(run/"previous/inputs/pair-packet.json"):
        raise ValueError("Wrong prior detector packet")
    old=verified_votes(prev["true"])
    new={i:r["flag"] for i,r in revised["records"].items()}
    inputs={r["id"]:r["text"] for r in read(run/"inputs/inference.json")}
    if not inputs.keys()==key.keys()==new.keys()==old.keys():
        raise ValueError("Mismatched packets")
    rel={}
    controls={}
    agreement={}
    judges=read(run/"private/semantic-reference.json")
    truth={i:r["turn"] for i,r in judges.items()}
    for name,flags in (("old",old),("revised",new)):
        groups=defaultdict(dict)
        for oid,(side,i) in key.items():
            if i in groups[side]:
                raise ValueError("Duplicate study key")
            groups[side][i]=flags[oid]
        rel[name]=groups
        rev,cont=groups["flip"],groups["continue"]
        controls[name]=dict(pairs=table(rev,cont),sensitivity=sum(rev.values()),
                            false_positives=sum(cont.values()),n=len(rev))
        agreement[name]=confusion(truth,groups["true"])
    pair_change={k:[rel[m]["flip"][k] and not rel[m]["continue"][k] for m in ("old","revised")] for k in rel["old"]["flip"]}
    corpus=read(run/"inputs/corpus.json")
    base=read(run/"results/baseline.json")
    grades=read(run/"private/editorial.json")
    targets={u["id"]:u for u in corpus if u["target"]}
    assert targets.keys()==grades.keys()==judges.keys()==rel["revised"]["true"].keys()
    assert set(base)=={u["id"] for u in corpus}
    for i,(side,ident) in key.items():
        if side=="true" and inputs[i]!=targets[ident]["text"]:
            raise ValueError("Sentence identity changed")
    rows=[]
    for i,u in targets.items():
        g=grades[i]
        if not(g["quote"] in u["text"] and 1<=g["score"]<=7 and g["reason"]):
            raise ValueError(i)
        f=rel["revised"]["true"][i]
        rows.append(dict(**u,grade=g["score"],exact=exact(u["text"]),current=base[i],always_six=6.,
                         revised=prediction(base[i],f),previous=prediction(base[i],rel["old"]["true"][i]),
                         qwen_flag=f,route="semicolon_closings",reference=truth[i]))
    names=("current","always_six","previous","revised")
    models={n:summarize(rows,n) for n in names}
    literal=[r for r in rows if r["exact"]]
    result=dict(works=len(set(r["work_id"] for r in rows)),challenge=controls,pair_change=pair_change,
                natural_semantics=agreement,ambiguous=sum(x is None for x in truth.values()),
                models=models,exact={n:summarize(literal,n) for n in names} if literal else {},
                shuffle=shuffle_test(rows,models["revised"]["ordering"]),
                flags_by_grade={g:dict(n=sum(r["grade"]==g for r in rows),flagged=sum(r["grade"]==g and r["qwen_flag"] for r in rows))
                                for g in sorted(set(r["grade"] for r in rows))},
                donors={m:table({i:d["true"][i] for i in d["foils"]},d["foils"]) for m,d in rel.items()})
    seal(run/"private/joined.json",canonical(rows))
    seal(run/"results/comparison.json",canonical(result))


if __name__=="__main__":
    evaluate(Path(sys.argv[1]))
