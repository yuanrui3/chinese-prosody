"""Test the function of an ending on new, source-anchored written readings."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

from . import quantitative_pattern_endings as prev

SEED = 20261125


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def endpoints(rows, candidates, prior):
    by_key = prev.index(rows, prev.target_key)
    order = {key: i for i, key in enumerate(by_key)}
    reserved = {prev.normalized_text(r) for r in prior}
    options = defaultdict(list)
    omitted = []
    for r in candidates:
        key = prev.target_key(r)
        row = by_key[key]
        quote = r["quote"]
        end = row["text"].rfind(quote)
        check(quote and end >= 0, f"Unmatched target {key}")
        if prev.han_text(row["text"][end + len(quote) :]):
            omitted.append([*key, "internal ending followed by additional clauses in scoring unit"])
            continue
        check(r["section"] == row["section"] and len(r["prior_quotes"]) >= 2, f"Missing context {key}")
        pos = (-1, 0)
        invalid = False
        for part in r["prior_quotes"] + [{"id": r["id"], "quote": quote}]:
            k = r["work_id"], part["id"]
            src = by_key[k]
            ix = order[k]
            start = src["text"].find(part["quote"], pos[1] if ix == pos[0] else 0)
            check(
                src["section"] == row["section"] and ix >= pos[0] and start >= 0 and part["quote"],
                f"Quotation outside ordered context {key}: {part}",
            )
            pos = ix, start + len(part["quote"])
            invalid |= prev.incomplete(src) or prev.normalized_text(src) in reserved
        if invalid:
            omitted.append([*key, "incomplete or prior full unit"])
        else:
            options[key].append((end + len(quote), len(quote), r))
    keep = []
    for key, variants in options.items():
        keep.append(max(variants, key=lambda x: x[:2])[2])
        omitted.extend([[*key, "shares scored unit"]] * (len(variants) - 1))
    return sorted(keep, key=lambda r: order[prev.target_key(r)]), omitted


def packets(rows, ends):
    works = list(dict.fromkeys(r["work_id"] for r in rows))
    Random(SEED).shuffle(works)
    anonymous, keys, roles = [], [], []
    targets = {prev.target_key(r): r["quote"] for r in ends}
    for number, work in enumerate(works, 1):
        w = f"P{number:02}"
        sections = {}
        for j, r in enumerate((r for r in rows if r["work_id"] == work), 1):
            sec = sections.setdefault(r["section"], len(sections) + 1)
            mid = f"{w}-{j:03}"
            anonymous.append(
                dict(work_id=w, id=mid, section=f"{w}-s{sec}", text=r["text"], incomplete=prev.incomplete(r))
            )
            keys.append(dict(work_id=work, id=r["id"], masked_id=mid))
            if prev.target_key(r) in targets:
                roles.append(dict(id=mid, quote=targets[prev.target_key(r)]))
    return {
        "packet.json": anonymous,
        "key.json": keys,
        "role-packet.json": {"units": anonymous, "targets": roles},
    }


def archived(root, inputs):
    archive = root / "results/grammatical-training-expansion-20261122"
    old = archive / "results/enriched-reference.json"
    check(digest(old) == prev.TRAIN_SHA, "Frozen training checksum mismatch")
    prior = read(old)
    for path in (
        archive / "inputs/train-b.json",
        archive / "inputs/holdout.json",
        *(
            root / "results" / p
            for p in (
                "grammatical-patterns-20261122/inputs/fresh-witness.json",
                "editorial-context-20261122/inputs/fresh-witness.json",
                "dong-shaorong-holdout-20261122/witness.json",
                "fresh-three-line-transfer-20261122/inputs/witness.json",
                "pattern-ending-transfer-20261122/inputs/witness.json",
            )
        ),
    ):
        prior.extend(read(path))
    cards = read(inputs / "works.json")
    for field in ("title", "author"):
        check(len({r[field] for r in cards}) == len(cards), f"Duplicated source {field}")
        check(not ({r[field] for r in cards} & {p.get(field) for p in prior}), f"Previously tested {field}")
    return archive, prior


def model(root, archive, rows):
    path = archive / "results/fresh-expanded-results.json"
    check(digest(path) == prev.MODEL_SHA, "Different frozen model")
    frozen = read(path)["models"]["context_grammar"]
    grammar = prev.grammar
    lex, lexhash = grammar.context.base.lexicon_data(root)
    check(
        lexhash == read(archive / "results/summary.json")["lexicon_sha256"]
        and frozen["names"] == list(grammar.MODEL_COLS["context_grammar"]),
        "Model vocabulary mismatch",
    )
    lines = grammar.context.describe(rows, lex)
    for line in lines:
        if prev.incomplete(line.row):
            line.complete = False
    x, _ = grammar.matrix_rows(lines, lines, grammar.context.in_context(lines))
    return {l.key: prev.bounded(v) for l, v in zip(lines, grammar.context.predict(frozen, x))}, lexhash


def display(value):
    return "n/a" if value is None else f"{value:.3f}"


def analyze(root, inputs, output, screen_only=False):
    archive, prior = archived(root, inputs)
    rows = read(inputs / "witness.json")
    cards = read(inputs / "works.json")
    works = prev.index(cards, lambda c: c["work_id"])
    check(
        set(works) == {r["work_id"] for r in rows}
        and all(all(r[k] == works[r["work_id"]][k] for k in ("author", "title")) for r in rows),
        "Witness metadata mismatch",
    )
    for card in cards:
        paragraphs = card.get("paragraph_hashes") or {p["section"]: p["sha256"] for p in card["paragraphs"]}
        for section, expected in paragraphs.items():
            body = "".join(
                r["text"] for r in rows if r["work_id"] == card["work_id"] and r["section"] == section
            )
            check(
                sha256(body.encode()).hexdigest() == expected,
                f"Paragraph digest differs: {card['title']} {section}",
            )
    ends, omitted = endpoints(rows, read(inputs / "endings.json"), prior)
    masked = packets(rows, ends)
    for name, expected in masked.items():
        check(read(inputs / name) == expected, f"Changed masked input {name}")
    if screen_only:
        print(
            "Verified source and freshness:",
            len(rows),
            "units",
            len(ends),
            "endings",
            len(omitted),
            "excluded",
        )
        return
    from .ending_function_metrics import agreement, study

    key = prev.index(masked["key.json"], prev.target_key)
    packet = prev.index(masked["packet.json"], lambda r: r["id"])
    labels = prev.index(read(inputs / "editorial.json"), lambda r: r["id"])
    check(set(packet) == set(labels), "Incomplete written review")
    for mid, u in packet.items():
        v = labels[mid]
        check(
            v["work_id"] == u["work_id"]
            and v["reason"].strip()
            and (
                (v["score"] is None)
                if u["incomplete"]
                else (prev.grammar.context.valid_score(v["score"]) and v["quote"] and v["quote"] in u["text"])
            ),
            f"Rating {mid}",
        )
    forecasts, lexhash = model(root, archive, rows)
    target_ids = {t["id"] for t in masked["role-packet.json"]["targets"]}
    coders = [
        prev.index(read(inputs / name), lambda r: r["id"]) for name in ("role-one.json", "role-two.json")
    ]
    check(all(set(c) == target_ids for c in coders), "Incomplete function review")
    result = []
    for end in ends:
        k = prev.target_key(end)
        mid = key[k]["masked_id"]
        unit = packet[mid]
        prefix = "".join(
            r["text"] for r in packet.values() if r["section"] == unit["section"] and r["id"] < mid
        )
        prefix += unit["text"][: unit["text"].rfind(end["quote"])]
        votes = []
        for c in coders:
            v = c[mid]
            check(
                v["role"] in ("argument", "list", "mixed", "uncertain")
                and v["target_quote"]
                and v["target_quote"] in end["quote"]
                and v["prior_quote"]
                and v["prior_quote"] in prefix
                and v["reason"].strip(),
                f"Unanchored role {mid}: {v}",
            )
            votes.append(v["role"])
        role = votes[0] if votes[0] == votes[1] and votes[0] in ("argument", "list") else None
        current = forecasts[k]
        result.append(
            dict(
                **end,
                masked_id=mid,
                text=unit["text"],
                score=labels[mid]["score"],
                editorial_reason=labels[mid]["reason"],
                votes=votes,
                role=role,
                current=current,
                with_role=prev.bounded(current + {"argument": 0.25, "list": -0.25}.get(role, 0)),
            )
        )
    one, two = [list(v) for v in zip(*(r["votes"] for r in result))]
    agree = agreement(one, two)
    stats = study(result, agree["roles"], shuffle=True)
    audit = dict(
        summary=stats,
        agreement=agree,
        sensitivity=[study(result, c) for c in (one, two)],
        ends=result,
        omitted=omitted,
        works=cards,
        source_units=len(rows),
        model_sha256=prev.MODEL_SHA,
        training_sha256=prev.TRAIN_SHA,
        lexicon_sha256=lexhash,
        input_sha256={p.name: digest(p) for p in sorted(inputs.iterdir()) if p.is_file()},
    )
    main = stats["primary"]
    out = [
        "GILBRETH | ARGUMENT AND LIST ENDINGS",
        f"{len(cards)} works | {len(rows)} units | {len(ends)} endings | {stats['n_pure']} agreed pure",
        f"Role agreement {agree['exact']}/{agree['n']} | kappa {display(agree['kappa'])}",
        "Method          Within cross-role   Within any role   MAE all",
    ]
    for m in ("always6", "current", "augmented"):
        score = main["methods"][m]["macro"]
        ordinary = stats["ordinary"]["methods"][m]["macro"]
        mae = stats["error"]["all"]["methods"][m]["macro_mae"]
        out.append(f"{m:12s}    {display(score):>7}  {display(ordinary):>16}    {mae:.3f}")
    out.append(
        f"Primary pairs {main['within_pairs']} in {len(main['informative_works'])} works | argument higher {main['argument_7_pairs']}"
    )
    out.append(f"Shuffled roles: {stats['permutation']}")
    reading = []
    for r in result:
        reading.extend(
            [
                f"《{works[r['work_id']]['title']}》 {r['id']}  {r['text']}",
                f"Marked ending: {r['quote']} | roles: {' / '.join(r['votes'])}",
                f"Written {r['score']} | current {r['current']:.2f} | with function {r['with_role']:.2f} | always 6",
                r["editorial_reason"],
                "",
            ]
        )
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp) / "result"
        stage.mkdir()
        prev.save(stage / "results.json", audit)
        (stage / "summary.txt").write_text("\n".join(out) + "\n")
        (stage / "reading-comparison.txt").write_text("\n".join(reading))
        check(not output.exists(), "Output exists")
        stage.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "inputs", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--screen", action="store_true")
    args = parser.parse_args()
    analyze(args.root, args.inputs, args.output, args.screen)
