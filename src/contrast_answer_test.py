"""Screen new exact-score ties and compare the frozen contrasting-answer rule."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from random import Random
from statistics import fmean
from tempfile import TemporaryDirectory

from . import exact_tie_transfer as ties
from . import exact_tie_carry_metrics as metrics
from .contrast_answer_sources import prose_lines
from hashlib import sha256

read, save, digest, check = ties.read, ties.base.save, ties.digest, ties.check
PROTOCOL = "5b4d8f0d79fb9bae7afcd2bffdd962c67c8b4ab571318243b02960e0f72d64d5"
SEED = 20261123


def choose(groups, budget=96):
    rng = Random(SEED)
    by_work = defaultdict(list)
    for (work, score), ids in sorted(groups.items()):
        members = sorted(ids)
        if len(members) > 8:
            members = sorted(rng.sample(members, 8))
        by_work[work].append(members)
    order = list(by_work)
    rng.shuffle(order)
    for w in order:
        rng.shuffle(by_work[w])
    selected = []
    while any(by_work.values()):
        for w in order:
            if by_work[w]:
                g = by_work[w].pop()
                if len(selected) + len(g) <= budget:
                    selected.extend(g)
    return sorted(selected)


def screen(root, run, out, *, extra_reference=(), protocol=PROTOCOL, paragraphs_from=prose_lines, donor_filter=None):
    inp = run / "inputs"
    all_rows, cards = [read(inp / name) for name in ("witness.json", "works.json")]
    ties.validate_sources(all_rows, cards)
    prior = ties.prior_rows(root) + read(root / "results/exact-tie-targets-20261122/inputs/witness.json")
    for archive in extra_reference:
        prior.extend(read(root / "results" / archive / "inputs/witness.json"))
    protected = {ties.base.normalized_text(r) for r in prior}
    authors = {r.get("author") for r in prior}
    titles = {r.get("title") for r in prior}
    for source in (run / "code/data/pilot").glob("*.json"):
        book = read(source)
        if isinstance(book, dict):
            for c in book.get("sources", []):
                authors.add(c.get("author"))
                titles.add(c.get("title"))
    counts = Counter(r["work_id"] for r in all_rows)
    works = {}
    omitted = {}
    for c in sorted(cards, key=lambda v: (-counts[v["work_id"]], v["title"])):
        source = inp / "editions" / f"{c['revision']}.wiki"
        check(digest(source) == c["wiki_sha256"], "Edition hash mismatch")
        para = paragraphs_from(source.read_text())
        check([sha256(p.encode()).hexdigest() for p in para] == list(c["paragraph_hashes"].values()), "Paragraph mismatch")
        author = {"周宏讓": "周弘讓"}.get(c["author"], c["author"])
        if author in authors or c["title"] in titles:
            omitted[c["work_id"]] = "earlier author/title or shorter work by same author"
        else:
            works[c["work_id"]] = c
        authors.add(author)
        titles.add(c["title"])
    rows = [r for r in all_rows if r["work_id"] in works]
    scores, lex = ties.old.previous.model(root, root / "results" / ties.old.ARCHIVE, rows)
    result = ties.select_targets(rows, scores, protected)
    groups = defaultdict(list)
    for t in result["targets"]:
        groups[t["work_id"], t["group"]].append(t["index"])
    selected = choose(groups)
    mask = sum(1 << i for i in selected)
    packets = ties.make_packets(rows, mask)
    rng = Random(SEED + 9)
    foils = []
    for key in packets["key.json"]:
        i = key["index"]
        r = rows[i]
        donors = [p for p in rows[:i-1] if (p["work_id"], p["section"]) == (r["work_id"], r["section"])
                  and not ties.base.incomplete(p) and ties.base.normalized_text(p) not in
                  {ties.base.normalized_text(rows[i-1]), ties.base.normalized_text(r)}]
        if donor_filter is not None:
            donors = [p for p in donors if donor_filter(p["text"], rows[i-1]["text"])]
        if donors:
            foils.append(dict(id=key["link_id"], prior=rng.choice(donors)["text"], target=r["text"]))
    for n, v in {**packets, "foils.json": foils, "rows.json": rows}.items():
        save(out / n, v)
    selected_set = set(selected)
    summary = dict(protocol=protocol, model=ties.base.MODEL_SHA, lexicon=lex,
                   submitted=len(all_rows), submitted_works=len(cards), fresh=len(rows), fresh_works=len(works),
                   eligible=result["eligible"], all_groups=len(groups), all_targets=len(result["targets"]),
                   selected=len(selected), works=works, omitted=omitted, exclusions=result["exclusions"],
                   targets=[t for t in result["targets"] if t["index"] in selected_set],
                   hashes={p.name: digest(p) for p in sorted(out.iterdir())})
    save(out / "screen.json", summary)
    print({k:v for k,v in summary.items() if k in ("submitted","submitted_works","fresh","fresh_works","eligible","all_groups","all_targets","selected")})


def evaluate(run, out):
    seal = run / "screen"
    s = read(seal / "screen.json")
    check(digest(seal / "screen.json") == (run / "inputs/screen.sha256").read_text().split()[0], "Screen changed")
    for name, expected in s["hashes"].items():
        check(digest(seal / name) == expected, name)
    witness = read(seal / "rows.json")
    keys = {k["index"]: k for k in read(seal / "key.json")}
    grades = ties.base.index(read(run / "inputs/editorial.json"), lambda r:r["id"])
    check(set(grades) == {k["editor_id"] for k in keys.values()}, "Rating coverage mismatch")
    rel = read(run / "relation.json")
    check(rel["links_sha256"] == s["hashes"]["links.json"] and rel["foils_sha256"] == s["hashes"]["foils.json"], "Relation packet mismatch")
    tested = ties.base.index(rel["true"], lambda r:r["id"])
    check(set(tested) == {k["link_id"] for k in keys.values()}, "Feature coverage mismatch")
    rows = []
    for row in s["targets"]:
        i = row["index"]
        key = keys[i]
        g = grades[key["editor_id"]]
        r = witness[i]
        check(g["score"] in range(1,8) and g["quote"] and g["quote"] in r["text"] and g["reason"].strip(), "Invalid grade")
        signal = tested[key["link_id"]]
        rows.append(dict(**row, prior=witness[i-1]["text"], text=r["text"], score=g["score"], editorial=g["reason"],
                         link_id=key["link_id"], flags=signal["flags"], genre=s["works"][row["work_id"]]["genre"]))
    blocks = metrics.exact_groups(rows)
    def compare(flags):
        values = metrics.adjusted([r["current"] for r in rows], flags)
        return metrics.ranking(rows, blocks, flags, values, "primary")
    flags = [int(all(r["flags"])) for r in rows]
    main, pairs = compare(flags)
    macro = main["methods"]["augmented"]["macro"]
    controls = metrics.shuffle_control(rows, blocks, pairs, flags, flags, macro)
    foils = {v["id"]: all(v["flags"]) for v in rel["foils"]}
    paired = Counter((bool(flag), foils[r["link_id"]]) for r,flag in zip(rows, flags) if r["link_id"] in foils)
    result = dict(screen_sha256=digest(seal/"screen.json"), model=s["model"], editor_sha256=digest(run/"inputs/editorial.json"),
                  relation_sha256=digest(run/"relation.json"), grades=dict(Counter(r["score"] for r in rows)),
                  positives=sum(flags), prompt_agree=sum(a==b for a,b in (r["flags"] for r in rows)),
                  primary=main, shuffled=controls, per_prompt=[compare([int(r["flags"][k]) for r in rows])[0] for k in (0,1)],
                  paired_foil={f"true={a} foil={b}":v for (a,b),v in paired.items()}, rows=rows)
    informative=main["informative_works"]
    result["leave_one_work_out"]={w:fmean(main["by_work"][v]["accuracy"] for v in informative if v!=w) for w in informative if len(informative)>1}
    save(out / "results.json", result)
    lines = ["GILBRETH | CONTRASTING ANSWERS IN WRITTEN CADENCE",
             f"{len(rows)} targets | {len(blocks)} groups | {len(set(r['work_id'] for r in rows))} works",
             f"{main['n_pairs']} same-work 7/6 pairs in {len(informative)} works",
             f"Correct {main['correct']} | inverted {main['wrong']} | tied {main['tied']}",
             str({k:v["macro"] for k,v in main["methods"].items()}),
             f"Positive flags {sum(flags)} | shuffled upper tail {controls['p_upper']}"]
    (out/"summary.txt").write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
    reading=[]
    for r, flag in zip(rows, flags):
        reading.append(f"《{s['works'][r['work_id']]['title']}》 {r['id']}   {r['prior']} → {r['text']}\nWritten {r['score']} | frozen {r['current']!r} | bonus {0.25*flag} | {r['editorial']}")
    (out/"readings.txt").write_text("\n\n".join(reading)+"\n")


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("phase", choices=("screen","evaluate"))
    p.add_argument("root", type=Path)
    p.add_argument("run", type=Path)
    a=p.parse_args()
    check(digest(a.run/"inputs/protocol.md")==PROTOCOL, "Protocol changed")
    dest=a.run / ("screen" if a.phase=="screen" else "results")
    if dest.exists():
        raise FileExistsError(dest)
    with TemporaryDirectory(dir=a.run) as tmp:
        out=Path(tmp)/"out"
        out.mkdir()
        if a.phase=="screen":
            screen(a.root,a.run,out)
        else:
            evaluate(a.run,out)
        out.rename(dest)
