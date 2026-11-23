"""Freeze work-local binary64 forecast ties, then evaluate blinded carry and cadence judgments."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import groupby
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

from . import adjacent_thought_transfer as carry
from . import exact_tie_carry_metrics as metrics

old, base = carry.old, carry.base
read, digest, check = old.read, old.digest, old.check
PROTOCOL = "6f9e08c808371a5b4a366823b687d4162e540348628d07d63afcd22de8b28c13"
SEED = 20261128


def prior_rows(root):
    results = root / "results"
    prior = old.base_reference(results)
    paths = list(old.OLDER)
    paths.extend(tag + "/inputs/witness.json" for tag, _ in old.COHORTS)
    paths.extend(tag + "/inputs/witness.json" for tag in (carry.LAST, "adjacent-thought-transfer-20261122"))
    for name in paths:
        prior.extend(read(results / name))
    return prior


def validate_sources(rows, cards):
    base.index(rows, base.target_key)
    works = base.index(cards, lambda c: c["work_id"])
    check(set(works) == {r["work_id"] for r in rows}, "Missing or unused work card")
    for wid, card in works.items():
        items = [r for r in rows if r["work_id"] == wid]
        check(
            all(all(r[k] == card[k] for k in ("title", "author")) for r in items),
            f"Inconsistent source {wid}",
        )
        order = [r["order"] for r in items]
        check(order == sorted(set(order)), f"Source order {wid}")
        hashes = card["paragraph_hashes"]
        sections = [sec for sec, _ in groupby(items, key=lambda r: r["section"])]
        check(len(sections) == len(hashes) and set(sections) == set(hashes), f"Interrupted section {wid}")
        for section, expected in hashes.items():
            text = "".join(r["text"] for r in items if r["section"] == section)
            check(sha256(text.encode()).hexdigest() == expected, f"Source hash changed in {wid} {section}")
    check(len([k for k, _ in groupby(rows, key=lambda r: r["work_id"])]) == len(works), "Interrupted work")


def select_targets(rows, scores, protected):
    normalized = [base.normalized_text(r) for r in rows]
    freq = Counter(normalized)
    blocks = defaultdict(list)
    reasons = Counter()
    for i, row in enumerate(rows):
        if not i or any(row[k] != rows[i - 1][k] for k in ("work_id", "section")):
            reasons["section_opening"] += 1
        elif base.incomplete(row) or base.incomplete(rows[i - 1]):
            reasons["incomplete_edge"] += 1
        elif normalized[i] in protected or normalized[i - 1] in protected:
            reasons["previously_used_edge_text"] += 1
        elif freq[normalized[i]] > 1:
            reasons["duplicate_target_text"] += 1
        else:
            blocks[row["work_id"], float(scores[base.target_key(row)]).hex()].append(i)
    retained = {k: ix for k, ix in blocks.items() if len(ix) >= 2}
    mask = sum(1 << i for ix in retained.values() for i in ix)
    targets = [
        dict(index=i, work_id=rows[i]["work_id"], id=rows[i]["id"], group=k[1], current=float.fromhex(k[1]))
        for k, ix in retained.items()
        for i in ix
    ]
    return dict(
        source_units=len(rows),
        eligible=sum(map(len, blocks.values())),
        distinct_groups=len(retained),
        works_with_ties=len({w for w, _ in retained}),
        exclusions=dict(reasons),
        mask=hex(mask),
        targets=sorted(targets, key=lambda r: r["index"]),
    )


def make_packets(rows, mask):
    selected = {i for i in range(len(rows)) if mask & (1 << i)}
    ordering = list(dict.fromkeys(r["work_id"] for r in rows))
    Random(SEED).shuffle(ordering)
    editorial = []
    mapping = {}
    for number, w in enumerate(ordering, 1):
        work_code = f"W{number:02d}"
        subset = [(i, r) for i, r in enumerate(rows) if r["work_id"] == w]
        for s, (_, items) in enumerate(groupby(subset, key=lambda t: t[1]["section"]), 1):
            block = list(items)
            if not any(i in selected for i, _ in block):
                continue
            units = []
            for j, (i, r) in enumerate(block, 1):
                mid = f"{work_code}-{s:02d}-{j:03d}"
                units.append(dict(id=mid, text=r["text"], rate=i in selected))
                if i in selected:
                    mapping[i] = dict(index=i, id=r["id"], work_id=w, editor_id=mid)
            editorial.append(dict(section=f"{work_code}-{s:02d}", units=units))
    shuffled = sorted(selected)
    Random(SEED + 1).shuffle(shuffled)
    links = []
    for j, i in enumerate(shuffled, 1):
        lid = f"E{j:03d}"
        mapping[i]["link_id"] = lid
        links.append(dict(id=lid, prior=rows[i - 1]["text"], target=rows[i]["text"]))
    return {
        "editor-packet.json": editorial,
        "links.json": links,
        "key.json": [mapping[i] for i in sorted(mapping)],
    }


def screen(root, run, out):
    folder = run / "inputs"
    rows, cards = read(folder / "witness.json"), read(folder / "works.json")
    validate_sources(rows, cards)
    prior = prior_rows(root)
    authors, titles = [{r.get(f) for r in prior} for f in ("author", "title")]
    excluded = []
    for c in cards:
        if c["author"] in authors or c["title"] in titles:
            excluded.append(c["work_id"])
        authors.add(c["author"])
        titles.add(c["title"])
    # Keep source indices fixed for the anonymous reader handoff, even if an author overlaps.
    fresh = [(i, r) for i, r in enumerate(rows) if r["work_id"] not in excluded]
    items = [r for _, r in fresh]
    scores, lexhash = old.previous.model(root, root / "results" / old.ARCHIVE, items)
    result = select_targets(items, scores, {base.normalized_text(r) for r in prior})
    for target in result["targets"]:
        target["index"] = fresh[target["index"]][0]
    mask = sum(1 << t["index"] for t in result["targets"])
    result.update(
        mask=hex(mask),
        sources_submitted=len(rows),
        works_submitted=len(cards),
        excluded_works=excluded,
        model_sha256=base.MODEL_SHA,
        lexicon_sha256=lexhash,
        protocol_sha256=PROTOCOL,
        witness_sha256=digest(folder / "witness.json"),
        cards_sha256=digest(folder / "works.json"),
    )
    for name, data in make_packets(rows, mask).items():
        base.save(out / name, data)
    result["packet_sha256"] = {n: digest(out / n) for n in ("editor-packet.json", "links.json", "key.json")}
    base.save(out / "screen.json", result)
    print(
        f"{len(rows)} source units, {result['eligible']} eligible, {len(result['targets'])} targets, "
        f"{result['distinct_groups']} groups in {result['works_with_ties']} works"
    )
    print("MASK", result["mask"])


def run_test(run, seal, out):
    folder = run / "inputs"
    result = read(seal / "screen.json")
    check(result["protocol_sha256"] == PROTOCOL and result["model_sha256"] == base.MODEL_SHA, "Wrong screen")
    check(
        digest(seal / "screen.json") == (folder / "screen.sha256").read_text().split()[0],
        "Original screen changed",
    )
    check(
        digest(folder / "witness.json") == result["witness_sha256"]
        and digest(folder / "works.json") == result["cards_sha256"],
        "Source changed",
    )
    for n, h in result["packet_sha256"].items():
        check(digest(seal / n) == h, f"Mask changed: {n}")
    links = read(seal / "links.json")
    coders = [carry.labels_for(links, folder, n) for n in ("links-one.json", "links-two.json")]
    labels = base.index(read(folder / "editorial.json"), lambda x: x["id"])
    keys = base.index(read(seal / "key.json"), lambda x: x["index"])
    check(set(labels) == {k["editor_id"] for k in keys.values()}, "Missing/extra written ratings")
    rows = read(folder / "witness.json")
    records = []
    for t in result["targets"]:
        i = t["index"]
        k = keys[i]
        code = k["link_id"]
        v = labels[k["editor_id"]]
        a, b = [c[code] for c in coders]
        text = rows[i]["text"]
        check(
            type(v["score"]) is int
            and 1 <= v["score"] <= 7
            and v["quote"]
            and v["quote"] in text
            and v["reason"].strip(),
            f"Invalid editorial evidence {k['editor_id']}",
        )
        records.append(
            dict(
                **t,
                author=rows[i]["author"],
                title=rows[i]["title"],
                prior=rows[i - 1]["text"],
                text=text,
                score=v["score"],
                editorial_reason=v["reason"],
                coder1=a["role"],
                coder2=b["role"],
                reason1=a["reason"],
                reason2=b["reason"],
            )
        )
    check(len(keys) == len(records), "Incomplete target mapping")
    m = metrics.benchmark(records)
    pairs = [
        (h, l)
        for h in m["rows"]
        if h["score"] == 7
        for l in m["rows"]
        if l["score"] == 6 and h["work_id"] != l["work_id"] and h["group"] == l["group"]
    ]
    cross = Counter(
        "correct"
        if h["augmented"] > l["augmented"]
        else "wrong"
        if h["augmented"] < l["augmented"]
        else "tied"
        for h, l in pairs
    )
    base.save(
        out / "results.json",
        dict(
            benchmark=m,
            cross_work_only=dict(n=len(pairs), **cross),
            screen_sha256=digest(seal / "screen.json"),
            sources=read(folder / "works.json"),
            inputs={
                n: digest(folder / n)
                for n in ("editorial.json", "links-one.json", "links-two.json", "protocol.txt")
            },
        ),
    )
    p = m["primary"]
    lines = [
        "GILBRETH | EXACT SAME-WORK TIES",
        f"{m['n_targets']} targets | {m['n_groups']} full-precision groups | {m['n_works']} works",
        f"7/6 comparisons: {p['n_pairs']} | informative works: {len(p['informative_works'])} | informative groups: {p['informative_groups']}",
        f"Correctly broken {p['correct']} | wrongly broken {p['wrong']} | still tied {p['tied']}",
        "Work-weighted 7-above-6 ordering",
    ]
    for method, s in p["methods"].items():
        lines.append(f"{method:<12s} {old.previous.display(s['macro'])}")
    lines.append(f"Within-group shuffles: {m['permutation']}")
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    reading = [
        "Fresh written 音律美 | groups defined by the exact hexadecimal current-model score",
        "The reference is an independent AI editorial rating. Always giving 6 ties all comparisons.",
        "",
    ]
    for (w, g), chunk in groupby(
        sorted(m["rows"], key=lambda r: (r["work_id"], r["group"], r["index"])),
        key=lambda r: (r["work_id"], r["group"]),
    ):
        members = list(chunk)
        reading.append(
            f"《{members[0]['title']}》 {members[0]['author']} | {repr(members[0]['current'])} | {g}"
        )
        for r in members:
            reading.extend(
                [
                    f"{r['id']}  {r['prior']} → {r['text']}",
                    f"Written {r['score']} | roles {r['coder1']} / {r['coder2']} | adjusted {r['augmented']:.6f}",
                    r["editorial_reason"],
                    "Relation: " + r["reason1"],
                    "Second annotation: " + r["reason2"],
                    "",
                ]
            )
    (out / "reading-comparison.txt").write_text("\n".join(reading) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("screen", "test"))
    for k in ("root", "run", "out"):
        parser.add_argument("--" + k, type=Path, required=True)
    parser.add_argument("--seal", type=Path)
    a = parser.parse_args()
    root, run, out = [p.resolve() for p in (a.root, a.run, a.out)]
    check(
        run.is_relative_to(root) and out.is_relative_to(root) and not out.exists(),
        "Choose a new output in this project",
    )
    check(digest(run / "inputs/protocol.txt") == PROTOCOL, "Protocol differs")
    with TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "data"
        stage.mkdir()
        if a.phase == "screen":
            screen(root, run, stage)
        else:
            run_test(run, a.seal or run / "screen", stage)
        stage.rename(out)
