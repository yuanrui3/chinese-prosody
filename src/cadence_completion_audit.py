"""Apply the edition check fixed during blind reading to the already sealed results."""

from collections import Counter
from hashlib import sha256
from pathlib import Path
import re
import sys

from . import cadence_completion as study

read, save, metrics = study.read, study.save, study.metrics


def summarize(rows):
    blocks = metrics.exact_groups(rows)
    current = [r["current"] for r in rows]
    methods = {}
    for name in ("primary", "shape", "anchored"):
        flags = [r[name] for r in rows]
        ranking, pairs = metrics.ranking(rows, blocks, flags, metrics.adjusted(current, flags), "primary")
        methods[name] = ranking
    flags = [r["primary"] for r in rows]
    predictions = metrics.adjusted(current, flags)
    same_shape = {w: [(a,b) for a,b in ps if rows[a]["shape"] == rows[b]["shape"]] for w,ps in pairs.items()}
    same = metrics.decisions([p for ps in same_shape.values() for p in ps], predictions)
    matched_foils = Counter((r["primary"],r["foil_primary"]) for r in rows if "foil_primary" in r)
    return dict(n=len(rows), groups=len(blocks), works=len({r["work_id"] for r in rows}), methods=methods,
                same_length_signal=same, same_length_signal_works=sum(bool(p) for p in same_shape.values()),
                matched_foils={f"{int(a)}/{int(b)}":n for (a,b),n in matched_foils.items()},
                shuffle=metrics.shuffle_control(rows,blocks,pairs,flags,flags,methods["primary"]["methods"]["augmented"]["macro"]))


def main(run):
    s=read(run/"screen/screen.json")
    results=read(run/"results/results.json")
    witness=read(run/"screen/rows.json")
    keys={k["index"]:k for k in read(run/"screen/key.json")}
    # The anonymous reader identified these edition issues before seeing the outputs.
    composite={k["work_id"] for k in keys.values() if k["editor_id"].startswith("W05-")}
    assert len(composite)==1
    coda=set()
    for wid,c in s["works"].items():
        raw=(run/"inputs/editions"/f"{c['revision']}.wiki").read_text()
        if re.search("其詞曰[：:]",raw):
            prefix=re.split("其詞曰[：:]",raw,maxsplit=1)[0]
            allowed={sha256(p.encode()).hexdigest() for p in study.paragraphs(prefix)}
            coda.update((wid,section) for section,h in c["paragraph_hashes"].items() if h not in allowed)
    def is_coda(r):
        item=witness[r["index"]]
        return (r["work_id"],item["section"]) in coda

    rows=results["rows"]
    subsets={"no_composite":[r for r in rows if r["work_id"] not in composite],
             "no_coda":[r for r in rows if not is_coda(r)],
             "prose":[r for r in rows if r["work_id"] not in composite and not is_coda(r)]}
    output={k:summarize(v) for k,v in subsets.items()}
    output["removed_coda_ids"]=[r["id"] for r in rows if is_coda(r)]
    output["composite_ids"]=[r["id"] for r in rows if r["work_id"] in composite]
    output["qc_note_sha256"]=study.digest(run/"inputs/editorial-qc-note.txt")
    output["original_result_sha256"]=study.digest(run/"results/results.json")
    save(run/"results/edition-audit.json",output)
    for name in subsets:
        v=output[name]; m=v["methods"]["primary"]
        print(name, v["n"],m["n_pairs"],m["correct"],m["wrong"],m["tied"],m["methods"]["augmented"],v["shuffle"]["p_upper"])


if __name__=="__main__":
    main(Path(sys.argv[1]))
