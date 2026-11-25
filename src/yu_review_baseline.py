"""Apply the Yu Xin checkpoint's frozen written scorer to a new complete sentence sequence."""

import argparse
from itertools import groupby
import json
from math import isfinite
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import quantitative_ending_functions as frozen
from .quantitative_grammar_expansion import normalized_text


def predict(root, run, expected_corpus_hash, checkpoint):
    inputs = run / "inputs/corpus.json"
    if frozen.digest(inputs) != expected_corpus_hash:
        raise ValueError("Corpus differs from the frozen edition sequence")
    witness = frozen.read(inputs)
    archive = root / "results/grammatical-training-expansion-20261122"
    training = archive / "results/enriched-reference.json"
    provenance = frozen.read(checkpoint / "prototype_provenance.json")
    if frozen.digest(training) != provenance["training_reference_sha256"]:
        raise ValueError("Different training reference from the Yu Xin checkpoint")

    # The earlier workbook ran on the full punctuation-ended sequence. Validate that
    # every archived score is exactly reproduced before applying it to other authors.
    original = checkpoint / "units.json"
    if frozen.digest(original) != provenance["units_sha256"]:
        raise ValueError("Yu Xin replay witness changed")
    replay = [
        dict(r, work_id="yu-xin-ai-jiangnan-fu", section=f"{r['section']}/{r['paragraph']}")
        for r in frozen.read(original)
    ]
    old_values, _ = frozen.model(root, archive, replay)
    old_scores = {r["id"]: old_values[frozen.prev.target_key(r)] for r in replay}
    if old_scores != frozen.read(checkpoint / "prototype.json"):
        raise ValueError("Could not reproduce the checkpoint's sentence scores exactly")

    # Fresh contexts follow the edition paragraphs. The corpus has both targets and
    # unsampled neighbors; scoring only target rows would change the trained features.
    rows = [dict(r, section=f"{r['section']}/{r['paragraph']}") for r in witness]
    ids = [r["id"] for r in rows]
    if not rows or len(set(ids)) != len(ids):
        raise ValueError("Corpus has missing rows or duplicate anonymous IDs")
    contexts = [key for key, _ in groupby(rows, key=lambda r: (r["work_id"], r["section"]))]
    if len(contexts) != len(set(contexts)):
        raise ValueError("Noncontiguous edition paragraph")
    trained = {normalized_text(r) for r in frozen.read(training)}
    if any(normalized_text(r) in trained for r in rows if r["target"]):
        raise ValueError("A fresh target matches a model-training sentence")
    predictions, lexicons = frozen.model(root, archive, rows)
    if lexicons != provenance["lexicons"]:
        raise ValueError("Different source dictionaries from the Yu Xin checkpoint")
    scores = {r["id"]: predictions[frozen.prev.target_key(r)] for r in rows}
    if not all(isfinite(x) and 1 <= x <= 7 for x in scores.values()):
        raise ValueError("Invalid frozen model prediction")
    metadata = {
        "model": provenance["model"],
        "model_bundle_sha256": frozen.digest(archive / "results/fresh-expanded-results.json"),
        "training_reference_sha256": frozen.digest(training),
        "lexicons": lexicons,
        "input_sha256": expected_corpus_hash,
        "checkpoint_exact_replay_rows": len(replay),
        "n_rows": len(rows),
        "n_targets": sum(r["target"] for r in rows),
        "n_contexts": len(contexts),
        "preset_top_cutoff": provenance["preset_top_cutoff"],
    }
    return scores, metadata


def save_sealed(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    with NamedTemporaryFile(dir=path.parent) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            os.link(tmp.name, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError(f"Existing {path.name} differs from this run")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("corpus_sha256")
    args = parser.parse_args()
    os.umask(0o077)
    scores, metadata = predict(args.root, args.run, args.corpus_sha256, args.checkpoint)
    outputs = args.run / "results"
    outputs.mkdir(exist_ok=True)
    save_sealed(outputs / "baseline.json", scores)
    metadata["baseline_sha256"] = frozen.digest(outputs / "baseline.json")
    save_sealed(outputs / "baseline-provenance.json", metadata)
