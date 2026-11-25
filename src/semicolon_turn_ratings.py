"""Transfer masked judgments only for a matching revision, full paragraph and position."""

from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path

from .semantic_turn_relation import canonical, seal
from .yu_review_transfer import digest, read


def keys(run):
    revision = {w["work_id"]: w["revision"] for w in read(run / "inputs/sources.json")["works"]}
    groups = defaultdict(list)
    for row in read(run / "inputs/corpus.json"):
        groups[row["work_id"], row["paragraph"]].append(row)
    result = {}
    for (work, para), rows in groups.items():
        paragraph = tuple(r["text"] for r in rows)
        for k, row in enumerate(rows):
            if row["target"]:
                result[row["id"]] = (revision[work], para, paragraph, k)
    return result


def transfer(old, run):
    earlier = old / "private/editorial.json"
    if digest(earlier) != (old / "seals/editorial.sha256").read_text().split()[0]:
        raise ValueError("Earlier masked judgments have changed")
    for path in (old, run):
        for name in ("sources.json", "corpus.json"):
            if digest(path / "inputs" / name) != read(path / "inputs/source-seal.json")[name]:
                raise ValueError(f"Changed source packet: {path.name}/{name}")
    ref = read(earlier)
    lookup = {key: i for i, key in keys(old).items()}
    fresh = keys(run)
    same = {i: lookup[key] for i, key in fresh.items() if key in lookup}
    seal(run / "private/transferred.json", canonical({i: ref[k] for i, k in same.items()}))
    seal(run / "private/transfer-key.json", canonical(dict(previous=old.name, reference_sha256=digest(earlier), ids=same)))
    print("Identical targets carried forward:", len(same), "New ratings needed:", sorted(fresh.keys() - same.keys()))


def finish(run):
    grades = read(run / "private/transferred.json")
    for path in sorted((run / "private").glob("editorial-W*.json")):
        batch = read(path)
        if grades.keys() & batch.keys():
            raise ValueError("Attempt to override a masked judgment")
        grades.update(batch)
    target = {r["id"]: r["text"] for r in read(run / "inputs/corpus.json") if r["target"]}
    if grades.keys() != target.keys():
        raise ValueError("Incomplete grading packet")
    for i, value in grades.items():
        if (type(value["score"]) is not int or not 1 <= value["score"] <= 7
                or not value["reason"].strip() or not value["quote"] or value["quote"] not in target[i]):
            raise ValueError(f"Invalid rating: {i}")
    path = run / "private/editorial.json"
    seal(path, canonical(grades))
    seal(run / "seals/editorial.sha256", f"{digest(path)}  private/editorial.json\n".encode())


if __name__ == "__main__":
    p = ArgumentParser()
    p.add_argument("step", choices=("transfer", "finish"))
    p.add_argument("run", type=Path)
    p.add_argument("--previous", type=Path)
    args = p.parse_args()
    if args.step == "transfer":
        if args.previous is None:
            p.error("transfer requires --previous")
        transfer(args.previous, args.run)
    else:
        finish(args.run)
