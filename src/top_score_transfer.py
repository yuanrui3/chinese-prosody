"""Fit a top-score cutoff on two earlier corpora and apply the frozen cutoff to new authors."""

import argparse
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from . import quantitative_ending_functions as previous
from . import quantitative_top_score_calibration as calibration

read, digest, check = previous.read, previous.digest, previous.check
base = previous.prev
ARCHIVE = "grammatical-training-expansion-20261122"
COHORTS = (
    ("pattern-ending-transfer-20261122", "verdict.json"),
    ("ending-function-transfer-20261122", "editorial.json"),
)
OLDER = (
    "grammatical-patterns-20261122/inputs/fresh-witness.json",
    "editorial-context-20261122/inputs/fresh-witness.json",
    "dong-shaorong-holdout-20261122/witness.json",
    "fresh-three-line-transfer-20261122/inputs/witness.json",
)
PROTOCOL_SHA = "e34bd11928ff3bc0374577a130676159484396b1165adc56882ebab4735d00be"


def base_reference(results):
    archive = results / ARCHIVE
    enriched = archive / "results/enriched-reference.json"
    check(digest(enriched) == base.TRAIN_SHA, "Base training reference checksum mismatch")
    rows = read(enriched)
    for name in ("train-a.json", "train-b.json", "holdout.json"):
        rows.extend(read(archive / "inputs" / name))
    return rows


def joined(folder, label_name, root, archive, protected, cohort):
    rows = read(folder / "witness.json")
    keys = base.index(read(folder / "key.json"), base.target_key)
    labels = base.index(read(folder / label_name), lambda r: r["id"])
    packet = base.index(read(folder / "packet.json"), lambda r: r["id"])
    check(
        set(keys) == set(base.index(rows, base.target_key))
        and set(labels) == set(packet) == {entry["masked_id"] for entry in keys.values()}
        and len(keys) == len(packet),
        "Broken blinded mapping",
    )
    predictions, lexhash = previous.model(root, archive, rows)
    selected, excluded = [], []
    for row in rows:
        k = base.target_key(row)
        mid = keys[k]["masked_id"]
        m, label = packet[mid], labels[mid]
        check(
            m["text"] == row["text"]
            and m["work_id"] == label["work_id"]
            and label["reason"].strip()
            and (
                label["score"] is None
                if base.incomplete(row)
                else (
                    base.grammar.context.valid_score(label["score"])
                    and label["quote"]
                    and label["quote"] in row["text"]
                )
            ),
            f"Invalid reference rating at {k}",
        )
        reason = (
            "incomplete"
            if base.incomplete(row)
            else "exact normalized unit reused"
            if base.normalized_text(row) in protected
            else None
        )
        if reason:
            excluded.append(dict(work_id=k[0], id=k[1], reason=reason))
            continue
        selected.append(
            dict(
                work_id=k[0],
                id=k[1],
                score=label["score"],
                current=predictions[k],
                text=row["text"],
                author=row["author"],
                title=row["title"],
                cohort=cohort,
                masked_id=mid,
                quote=label["quote"],
                reason=label["reason"],
            )
        )
    return selected, excluded, lexhash


def source_hashes(folder, label):
    return {
        name: digest(folder / name)
        for name in ("witness.json", "works.json", "key.json", "packet.json", label)
    }


def fit_stage(root, run, output):
    res = root / "results"
    archive = res / ARCHIVE
    protected = {base.normalized_text(r) for r in base_reference(res)}
    earlier, excluded, hashes = [], [], {}
    seen_authors, seen_titles, seen_works = set(), set(), set()
    for tag, label in COHORTS:
        folder = res / tag / "inputs"
        raw = read(folder / "witness.json")
        cards = read(folder / "works.json")
        for field, seen in (("author", seen_authors), ("title", seen_titles), ("work_id", seen_works)):
            values = {c[field] for c in cards}
            check(
                len(values) == len(cards) and not values & seen and values == {r[field] for r in raw},
                f"Earlier overlap {field}",
            )
            seen.update(values)
        hashes[tag] = source_hashes(folder, label)
        values, skipped, lexhash = joined(folder, label, root, archive, protected, tag)
        earlier.extend(values)
        excluded.extend(skipped)
    params = calibration.fit(earlier)
    saved = dict(
        fit=params,
        earlier=earlier,
        excluded=excluded,
        sources_sha256=hashes,
        model_sha256=base.MODEL_SHA,
        training_sha256=base.TRAIN_SHA,
        lexicon_sha256=lexhash,
        calibration_code_sha256=digest(Path(calibration.__file__)),
        protocol_sha256=PROTOCOL_SHA,
    )
    base.save(output / "freeze.json", saved)
    text = (
        f"Frozen cutoff {params['threshold']} | {params['n_works']} earlier works | {params['n_rows']} eligible units | "
        f"{len(excluded)} excluded"
    )
    (output / "summary.txt").write_text(text + "\n")
    print(text)


def fresh_sources(root, run):
    folder = run / "inputs"
    rows = read(folder / "witness.json")
    cards = read(folder / "works.json")
    check(len(cards) == 6, "Six fresh works required for this pilot")
    joined_cards = base.index(cards, lambda r: r["work_id"])
    check(
        set(joined_cards) == {r["work_id"] for r in rows}
        and all(all(joined_cards[r["work_id"]][k] == r[k] for k in ("author", "title")) for r in rows),
        "Fresh source metadata mismatch",
    )
    for card in cards:
        work = [r for r in rows if r["work_id"] == card["work_id"]]
        hashes = card["paragraph_hashes"]
        check(
            set(hashes) == {r["section"] for r in work}
            and [r["order"] for r in work] == sorted({r["order"] for r in work}),
            "Source paragraph or order mismatch",
        )
        for section, expected in hashes.items():
            body = "".join(r["text"] for r in work if r["section"] == section)
            check(sha256(body.encode()).hexdigest() == expected, f"Changed paragraph in {card['title']}")
    masked = previous.packets(rows, [])
    for name in ("key.json", "packet.json"):
        check(read(folder / name) == masked[name], f"Altered neutral {name}")
    res = root / "results"
    prior = base_reference(res)
    for path in OLDER:
        prior.extend(read(res / path))
    for tag, _ in COHORTS:
        prior.extend(read(res / tag / "inputs/witness.json"))
    for field in ("author", "title"):
        values = {c[field] for c in cards}
        check(len(values) == len(cards) and not values & {r.get(field) for r in prior}, f"Reused {field}")
    return cards, {base.normalized_text(r) for r in prior}


def test_stage(root, run, output, freeze_path):
    from .top_score_calibration_controls import permutation_control

    folder = run / "inputs"
    expected = (folder / "freeze.sha256").read_text().split()[0]
    check(digest(freeze_path) == expected, "Earlier calibration freeze differs")
    frozen = read(freeze_path)
    check(
        frozen["protocol_sha256"] == PROTOCOL_SHA
        and frozen["model_sha256"] == base.MODEL_SHA
        and frozen["calibration_code_sha256"] == digest(Path(calibration.__file__)),
        "Frozen rule mismatch",
    )
    cards, protected = fresh_sources(root, run)
    fresh, excluded, lexhash = joined(
        folder, "editorial.json", root, root / "results" / ARCHIVE, protected, "fresh"
    )
    check(lexhash == frozen["lexicon_sha256"], "Fresh lexicon differs")
    stats = calibration.benchmark(frozen["earlier"], fresh)
    check(stats["fit"] == frozen["fit"], "Earlier full fit does not reproduce its signed-off operating point")
    controls = permutation_control(fresh, stats["fit"]["threshold"])
    result = dict(
        benchmark=stats,
        controls=controls,
        works=cards,
        excluded=excluded,
        earlier_excluded=frozen["excluded"],
        hashes=source_hashes(folder, "editorial.json"),
        earlier_freeze_sha256=expected,
        model_sha256=base.MODEL_SHA,
    )
    base.save(output / "results.json", result)
    summary = [
        "GILBRETH | WRITTEN TOP-SCORE CALIBRATION",
        f"Cutoff {calibration.CURRENT:.1f} -> {stats['fit']['threshold']} | earlier {stats['fit']['n_works']} works / {stats['fit']['n_rows']} units",
        f"Fresh: {len(cards)} works / {len(fresh)} eligible units / {len(excluded)} excluded",
        "Method        Caught 7s    Promoted 6s    Promoted lower    Precision",
    ]

    def fraction(n, d):
        return f"{n}/{d}" if d else "n/a"

    for m, metric in stats["fresh"]["methods"].items():
        c = metric["pooled"]
        summary.append(
            f"{m:<13} {fraction(c['true7'],c['n7']):<11} {fraction(c['false7_from6'],c['n6']):<14} "
            f"{fraction(c['false7_from_lower'],c['n_lower']):<17} {fraction(c['true7'],c['called7'])}"
        )
    balanced = stats["fresh"]["methods"]["calibrated"]["work_balanced"]
    summary += [
        f"Calibrated equal-work recall {previous.display(balanced['recall7'])} | false 7s among 6s {previous.display(balanced['false7_rate6'])}",
        f"Fresh dual-20% target plus recall gain: {stats['fresh']['decision']['status']}",
    ]
    (output / "summary.txt").write_text("\n".join(summary) + "\n")
    reading = [
        "Written 音律美 | a top-score decision on the entire original scoring unit",
        f"Original model scores are displayed to four decimals. Calls use full precision. Frozen cutoff {stats['fit']['threshold']}.",
        "Always giving 6 makes zero top-score calls.",
        "",
    ]
    for r in stats["fresh"]["rows"]:
        calls = r["call7"]
        reading += [
            f"《{r['title']}》 {r['author']}  {r['id']}  {r['text']}",
            f"Editorial {r['score']} | model {r['current']:.4f} | original calls 7: {calls['current']} | calibrated calls 7: {calls['calibrated']}",
            r["reason"],
            "",
        ]
    if excluded:
        reading += ["Excluded units", *[f"{r['work_id']} {r['id']}  {r['reason']}" for r in excluded]]
    (output / "reading-comparison.txt").write_text("\n".join(reading) + "\n")
    print("\n".join(summary))


def run_phase(phase, root, run, output, freeze_path=None):
    check(
        run.is_relative_to(root) and output.is_relative_to(root) and not output.exists(),
        "Choose a new output in the project",
    )
    check(digest(run / "inputs/protocol.txt") == PROTOCOL_SHA, "Protocol differs")
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp) / "stage"
        stage.mkdir()
        if phase == "fit":
            fit_stage(root, run, stage)
        else:
            test_stage(root, run, stage, freeze_path or run / "frozen/freeze.json")
        stage.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("fit", "test"))
    for name in ("root", "run", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--freeze", type=Path)
    args = parser.parse_args()
    run_phase(args.phase, args.root.resolve(), args.run.resolve(), args.output.resolve(), args.freeze)
