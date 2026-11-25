"""Seal primary-source comparisons and apply the archived written musicality scorer."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import product
import json
from math import isclose
from pathlib import Path
from statistics import fmean

from . import quantitative_editorial_transfer as text_model
from .yu_review_baseline import predict, save_sealed


METHODS = ("current", "length", "always6")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def han_count(s):
    return sum(text_model.han(c) for c in s)


def index_packet(packet):
    rows = packet["versions"]
    versions = {v["id"]: v for v in rows}
    if len(versions) != len(rows) or not rows:
        raise ValueError("Version IDs must be unique")
    for v in rows:
        if han_count(v["text"]) != len(v["pinyin"].split()) or not v["source"]:
            raise ValueError(f"Incomplete version: {v['id']}")
    links = set()
    pair_ids = set()
    for p in packet["pairs"]:
        edge = frozenset([p["a"], p["b"]])
        if len(edge) != 2 or edge in links or p["id"] in pair_ids:
            raise ValueError("Duplicate comparison")
        if any(versions[k]["family"] != p["family"] for k in edge):
            raise ValueError("Cross-family comparison")
        if p["endpoint"] not in {"primary", "literary", "unranked", "calibration"}:
            raise ValueError("Missing source classification")
        if (p["preferred"] is None and p["endpoint"] != "unranked"
                or p["preferred"] is not None and
                (p["preferred"] not in edge or p["endpoint"] == "unranked")):
            raise ValueError("Invalid ranked evidence")
        links.add(edge)
        pair_ids.add(p["id"])
    return versions


def seal(run, packet_path):
    packet = read(packet_path)
    versions = index_packet(packet)
    out = run / "inputs"
    out.mkdir(exist_ok=True)
    corpus = [dict(id=k, work_id=k, section="excerpt", paragraph=1, order=1,
                   text=v["text"], target=True) for k, v in versions.items()]
    save_sealed(out / "corpus.json", corpus)
    save_sealed(out / "critic-packet.json", packet)
    protocol = run / "code/research/critic-preferences.md"
    save_sealed(out / "critic-seal.json", {
        "corpus": digest(out / "corpus.json"), "packet": digest(out / "critic-packet.json"),
        "protocol": digest(protocol), "analysis": digest(Path(__file__)),
    })


def fit_length(rows):
    x = [han_count(r["text"]) for r in rows]
    y = [r["score"] for r in rows]
    mx, my = fmean(x), fmean(y)
    slope = sum((n - mx) * (s - my) for n, s in zip(x, y)) / sum((n - mx) ** 2 for n in x)
    return my - slope * mx, slope


def direction(a, b):
    return 0 if isclose(a, b, abs_tol=1e-10, rel_tol=0) else (1 if a > b else -1)


def compare(packet, scores):
    results = []
    for p in packet["pairs"]:
        a, b = p["a"], p["b"]
        order = {m: direction(scores[a][m], scores[b][m]) for m in METHODS}
        preferred = p["preferred"]
        factor = 1 if preferred == a else -1
        credit = {m: (1 + sign * factor) / 2 for m, sign in order.items()} if preferred else {}
        results.append({**p, "a_over_b": order, "pair_credit": credit})
    return results


def summarize(rows):
    summary = {}
    for method in METHODS:
        families = defaultdict(list)
        counts = Counter()
        for row in rows:
            c = row["pair_credit"][method]
            families[row["family"]].append(c)
            counts[{1: "correct", 0.5: "tied", 0: "reversed"}[c]] += 1
        means = [fmean(vals) for vals in families.values()]
        value = fmean(means) if means else None
        # All label reversals within the same anecdote move together.
        null = [fmean(c if bit else 1 - c for bit, c in zip(bits, means))
                for bits in product((False, True), repeat=len(means))] if means else []
        summary[method] = dict(families=len(means), comparisons=len(rows), counts=dict(counts),
                               credit=value, label_flip_upper_tail=(
                                   sum(x >= value - 1e-12 for x in null) / len(null) if null else None))
    return summary


def evaluate(root, run):
    inputs = run / "inputs"
    frozen = read(inputs / "critic-seal.json")
    for key, path in {"packet": inputs / "critic-packet.json", "corpus": inputs / "corpus.json",
                      "protocol": run / "code/research/critic-preferences.md",
                      "analysis": Path(__file__)}.items():
        if digest(path) != frozen[key]:
            raise ValueError(f"Changed after freeze: {key}")
    packet = read(inputs / "critic-packet.json")
    versions = index_packet(packet)
    current, provenance = predict(root, run, frozen["corpus"], root / "results/ai-jiangnan-complete-20261123-N0QpQKI1")
    old = root / "results/grammatical-training-expansion-20261122/results/enriched-reference.json"
    training = read(old)
    intercept, slope = fit_length(training)
    lexicons, _ = text_model.lexicon_data(root)
    scores = {}
    for k, v in versions.items():
        count = han_count(v["text"])
        scores[k] = dict(current=current[k], length=max(1, min(7, intercept + slope * count)),
                         always6=6, count=count, detail=text_model.measure(v["text"], lexicons, detail=True))
    pairs = compare(packet, scores)
    endpoint_summaries = {key: summarize([p for p in pairs if p["endpoint"] == key])
                          for key in ("primary", "literary", "calibration")}
    outputs = run / "results"
    outputs.mkdir(exist_ok=True)
    save_sealed(outputs / "critic-scores.json", dict(scores=scores, pairs=pairs, summary=endpoint_summaries,
                replay=provenance, length_fit=dict(n=len(training), intercept=intercept, slope=slope), seals=frozen))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["seal", "score"])
    parser.add_argument("root", type=Path)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    if args.phase == "seal":
        seal(args.run, args.run / "code/research/critic-variants.json")
    else:
        evaluate(args.root, args.run)
