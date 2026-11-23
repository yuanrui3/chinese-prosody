"""Test whether independently annotated thought development improves written 7-versus-6 ranking."""

import argparse
from collections import Counter, defaultdict
from itertools import groupby
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

from . import top_score_transfer as old
from . import written_carry_metrics as metrics

previous = old.previous
base = old.base
check, read, digest = old.check, old.read, old.digest
SEED = 20261127
PROTOCOL = "27a425ec341eefa4d6a23035a87d2eec6056890ebaa384138da89217112fe85c"
LAST = "top-score-calibration-20261122"


def link_packets(rows):
    """Make blinded true edges and a matched sample of same-section, earlier donor controls."""
    rng = Random(SEED)
    all_edges, possible = [], defaultdict(list)
    starts = []
    for (work, section), group in groupby(rows, key=lambda r: (r["work_id"], r["section"])):
        units = list(group)
        starts.append((work, units[0]["id"]))
        for i in range(1, len(units)):
            prior, target = units[i - 1 : i + 1]
            if base.incomplete(prior) or base.incomplete(target):
                continue
            all_edges.append((work, prior["id"], target["id"], True))
            donors = [
                r
                for r in units[: max(0, i - 2)]
                if not base.incomplete(r)
                and base.normalized_text(r) not in {base.normalized_text(prior), base.normalized_text(target)}
            ]
            if donors:
                possible[work].append((target, donors))
    for work, choices in possible.items():
        for target, donors in rng.sample(choices, min(2, len(choices))):
            all_edges.append((work, rng.choice(donors)["id"], target["id"], False))
    rng.shuffle(all_edges)
    witness = base.index(rows, base.target_key)
    links, key = [], []
    for i, (w, p, t, authentic) in enumerate(all_edges, 1):
        code = f"L{i:03d}"
        links.append(dict(id=code, prior=witness[w, p]["text"], target=witness[w, t]["text"]))
        key.append(dict(id=code, work_id=w, prior_id=p, target_id=t, authentic=authentic))
    return links, key, starts


def inspect_sources(root, run):
    cards, protected = old.fresh_sources(root, run)
    latest = read(root / "results" / LAST / "inputs/witness.json")
    for field in ("author", "title"):
        check(
            not ({c[field] for c in cards} & {r[field] for r in latest}), f"Reused calibration-test {field}"
        )
    protected.update(base.normalized_text(r) for r in latest)
    rows = read(run / "inputs/witness.json")
    links, key, starts = link_packets(rows)
    check(
        links == read(run / "inputs/links.json") and key == read(run / "inputs/link-key.json"),
        "Altered link packet",
    )
    by_key = base.index(rows, base.target_key)
    omitted = []
    allowed = []
    for e in key:
        if any(
            base.normalized_text(by_key[e["work_id"], e[k]]) in protected for k in ("prior_id", "target_id")
        ):
            omitted.append(e["id"])
        else:
            allowed.append(e)
    return cards, protected, rows, links, allowed, starts, omitted


def labels_for(links, folder, name):
    codes = base.index(read(folder / name), lambda r: r["id"])
    check(set(codes) == {e["id"] for e in links}, "Missing or extra relation judgments")
    for e in links:
        v = codes[e["id"]]
        check(
            v["role"] in metrics.CATEGORIES
            and v["prior_quote"]
            and v["prior_quote"] in e["prior"]
            and v["target_quote"]
            and v["target_quote"] in e["target"]
            and v["reason"].strip(),
            f"Unanchored role {name} {e['id']}",
        )
    return codes


def consensus(a, b):
    role = metrics.ROLES[a]
    return role if role == metrics.ROLES[b] else None


def run(root, run_dir, output, screen=False):
    folder = run_dir / "inputs"
    check(digest(folder / "protocol.txt") == PROTOCOL, "Frozen protocol mismatch")
    cards, protected, witness, links, allowed, starts, omitted = inspect_sources(root, run_dir)
    size = len(witness)
    print(
        "Source screen:",
        len(cards),
        "works",
        size,
        "source units",
        len(starts),
        "section openings",
        sum(e["authentic"] for e in allowed),
        "authentic edges,",
        sum(not e["authentic"] for e in allowed),
        "swapped controls,",
        len(omitted),
        "reused edges",
    )
    if screen:
        return
    check(output.is_relative_to(root) and not output.exists(), "Choose a new output within the project")
    scored, skipped, lexhash = old.joined(
        folder, "editorial.json", root, root / "results" / old.ARCHIVE, protected, "fresh"
    )
    link_text = base.index(links, lambda r: r["id"])
    votes = [labels_for(links, folder, n) for n in ("links-one.json", "links-two.json")]
    judgments = []
    for e in allowed:
        code = e["id"]
        a, b = [v[code] for v in votes]
        judgments.append(
            dict(
                **e,
                prior_text=link_text[code]["prior"],
                target_text=link_text[code]["target"],
                coder1=a["role"],
                coder2=b["role"],
                reason1=a["reason"],
                reason2=b["reason"],
                role=consensus(a["role"], b["role"]),
            )
        )
    genuine = {(v["work_id"], v["target_id"]): v for v in judgments if v["authentic"]}
    rows = []
    for scored_unit in scored:
        v = genuine.get(base.target_key(scored_unit))
        if v is not None:
            rows.append(
                dict(
                    **scored_unit,
                    prior_id=v["prior_id"],
                    prior_text=v["prior_text"],
                    coder1=v["coder1"],
                    coder2=v["coder2"],
                    reason1=v["reason1"],
                    reason2=v["reason2"],
                    link_id=v["id"],
                )
            )
    check(len(rows) == len(genuine), "Authentic edge without editorial score")
    evidence = metrics.benchmark(rows)
    contrasts = Counter()
    paired = []
    for v in judgments:
        if not v["authentic"] and (actual := genuine.get((v["work_id"], v["target_id"]))):
            before, after = actual["role"] or "abstain", v["role"] or "abstain"
            contrasts[before, after] += 1
            paired.append(dict(actual=actual, control=v))
    matches = dict(
        n=len(paired),
        matrix={
            a: {b: contrasts[a, b] for b in ("advance", "nonadvance", "abstain")}
            for a in ("advance", "nonadvance", "abstain")
        },
        pairs=paired,
    )
    stats = evidence["consensus"]
    audit = dict(
        benchmark=evidence,
        swapped=matches,
        works=cards,
        source_units=size,
        section_openings=starts,
        reused_edges=omitted,
        skipped_scoring_units=skipped,
        model_sha256=base.MODEL_SHA,
        lexicon_sha256=lexhash,
        input_sha256={p.name: digest(p) for p in sorted(folder.iterdir()) if p.is_file()},
    )
    headline = [
        "GILBRETH | ADJACENT THOUGHT IN PARALLEL PROSE",
        f"{len(cards)} works | {size} units | {len(rows)} authentic edges | {stats['eligible_count']} consensus edges",
        "Method            Opposite roles    All eligible    All adjacent",
    ]
    for method in ("always6", "current", "augmented"):
        scores = [
            previous.display(stats[s]["methods"][method]["macro"]) for s in ("primary", "eligible", "all")
        ]
        headline.append(f"{method:<16} {scores[0]:>10} {scores[1]:>14} {scores[2]:>15}")
    main = stats["primary"]
    headline.extend(
        [
            f"Primary 7/6 pairs {main['within_pairs']} in {len(main['informative_works'])} works",
            f"Equal-score 7/6 pairs {stats['tied_eligible']['within_pairs']} | permutation tail {stats['permutation']['p_upper']}",
        ]
    )
    lines = ["Written 音律美 | True adjacent targets | fixed +0.25 for agreed advance", ""]
    for r in evidence["rows"]:
        lines.extend(
            [
                f"《{r['title']}》 {r['id']}  {r['prior_text']} → {r['text']}",
                f"Relation {r['coder1']} / {r['coder2']} | editorial {r['score']} | current {r['current']:.4f} | adjusted {r['augmented']:.4f} | always 6",
                r["reason"],
                "Relation evidence: " + r["reason1"],
                "Second annotation: " + r["reason2"],
                "",
            ]
        )
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp) / "result"
        stage.mkdir()
        base.save(stage / "results.json", audit)
        (stage / "summary.txt").write_text("\n".join(headline) + "\n")
        (stage / "reading-comparison.txt").write_text("\n".join(lines) + "\n")
        stage.rename(output)
    print("\n".join(headline))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "run", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--screen", action="store_true")
    args = parser.parse_args()
    run(args.root.resolve(), args.run.resolve(), args.out.resolve(), args.screen)
