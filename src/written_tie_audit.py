"""Trace the eleven tied written forecasts from source, through features, to the archived prediction."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path

import numpy as np

from . import quantitative_editorial_grammar as grammar
from .quantitative_ending_functions import check, digest, read
from .quantitative_fresh_triples import MODEL_SHA
from .quantitative_pattern_endings import bounded, incomplete, index, save, target_key

ANCHOR = ("calA2", "calA2-U07")


def values(column):
    """Represent missing features as JSON null and preserve distinct numeric values exactly."""
    return [float(v) if np.isfinite(v) else None for v in column]


def layer_profile(model, feature_rows):
    """Decompose the production standardized linear rule into per-unit and per-column evidence."""
    raw = grammar.context.feature_matrix(feature_rows, model["names"])
    means = np.asarray(model["means"])
    scales = np.asarray(model["scales"])
    weights = np.asarray(model["weights"])
    seen = np.isfinite(raw)
    imputed = np.where(seen, raw, means)
    standardized = np.where(seen, raw - means, 0.0) / scales
    weighted = standardized * weights
    columns = {}
    for j, name in enumerate(model["names"]):
        fields = {}
        for key, data in (
            ("raw", raw),
            ("imputed", imputed),
            ("standardized", standardized),
            ("weighted", weighted),
        ):
            fields[key] = list(dict.fromkeys(values(data[:, j])))
        columns[name] = {
            **fields,
            "missing_count": int((~seen[:, j]).sum()),
            "training_mean": float(means[j]),
            "training_scale": float(scales[j]),
            "training_observed": int(model["observed"][j]),
            "weight": float(weights[j]),
        }
    evidence = []
    for i in range(len(raw)):
        evidence.append(
            {
                k: values(a[i])
                for k, a in (
                    ("raw", raw),
                    ("imputed", imputed),
                    ("standardized", standardized),
                    ("weighted", weighted),
                )
            }
        )
    return columns, evidence


def audit(root):
    previous = root / "results/top-score-calibration-20261122"
    original = root / "results/grammatical-training-expansion-20261122/results"
    forecast_path = previous / "results/results.json"
    witness_path = previous / "inputs/witness.json"
    model_path = original / "fresh-expanded-results.json"
    forecast = read(forecast_path)
    witness = read(witness_path)
    frozen = read(model_path)["models"]["context_grammar"]
    check(digest(model_path) == forecast["model_sha256"] == MODEL_SHA, "Frozen model checksum differs")
    check(digest(witness_path) == forecast["hashes"]["witness.json"], "Archived witness hash differs")
    check(frozen["names"] == list(grammar.MODEL_COLS["context_grammar"]), "Model feature order differs")
    lexicons, lexhash = grammar.context.base.lexicon_data(root)
    check(lexhash == read(original / "summary.json")["lexicon_sha256"], "Historical dictionary hashes differ")
    archive = index(forecast["benchmark"]["fresh"]["rows"], target_key)
    lines = grammar.context.describe(witness, lexicons)
    for line in lines:
        if incomplete(line.row):
            line.complete = False
    check(
        len(archive) == 95 and set(archive) == {line.key for line in lines}, "Expected all 95 original units"
    )
    contexts = grammar.context.in_context(lines)
    features, frames = grammar.matrix_rows(lines, lines, contexts)
    unbounded = grammar.context.predict(frozen, features)
    errors = [abs(bounded(p) - archive[line.key]["current"]) for p, line in zip(unbounded, lines)]
    check(max(errors) < 1e-12, "Archived predictions differ beyond floating summation noise")
    target = archive[ANCHOR]["current"]
    group = [i for i, ln in enumerate(lines) if archive[ln.key]["current"] == target]
    check(len(group) == 11, "The archived full-precision tie group changed")
    columns, evidence = layer_profile(frozen, [features[i] for i in group])
    tied = []
    for i, detail in zip(group, evidence):
        line = lines[i]
        original_row = archive[line.key]
        check(line.row["text"] == original_row["text"], f"Different text at {line.key}")
        forward_sum = math.fsum([frozen["intercept"], *detail["weighted"]])
        check(abs(forward_sum - unbounded[i]) < 1e-12, "Feature decomposition disagrees with the scorer")
        measured = grammar.context.base.measure(line.row["text"], lexicons, detail=True)
        tied.append(
            {
                "id": line.row["id"],
                "work_id": line.row["work_id"],
                "author": line.row["author"],
                "title": line.row["title"],
                "text": line.row["text"],
                "score": original_row["score"],
                "archived_current": original_row["current"],
                "unbounded": unbounded[i],
                "sum_check": forward_sum,
                "groups": list(line.groups),
                "group_lengths": measured["group_lengths"],
                "historical_support": measured["historical_support"],
                "end_rhyme_candidates": {tier: sorted(opts) for tier, opts in line.rhymes.items()},
                "neighbor_ids": contexts[line.key][1],
                "cross_line_rhyme_support": contexts[line.key][2],
                "grammar_slots": frames[line.key][2],
                **detail,
            }
        )
    n = len(group)
    summary = {
        "verified_rows": len(errors),
        "exact_replays": errors.count(0),
        "max_replay_error": max(errors),
        "n_tied": n,
        "target_score": target,
        "score_counts": dict(sorted(Counter(r["score"] for r in tied).items())),
        "work_count": len({r["work_id"] for r in tied}),
        "raw_vectors": len({tuple(r["raw"]) for r in tied}),
        "imputed_vectors": len({tuple(r["imputed"]) for r in tied}),
        "weighted_vectors": len({tuple(r["weighted"]) for r in tied}),
        "unbounded_scores": sorted({r["unbounded"] for r in tied}),
        "clipped_rows": sum(r["unbounded"] != bounded(r["unbounded"]) for r in tied),
        "group_lengths": [list(v) for v in sorted({tuple(r["group_lengths"]) for r in tied})],
        "all_missing_features": [name for name, c in columns.items() if c["missing_count"] == n],
        "partly_missing_features": [name for name, c in columns.items() if 0 < c["missing_count"] < n],
        "zero_weight_features": [name for name, c in columns.items() if c["weight"] == 0],
    }
    for layer in ("raw", "imputed", "weighted"):
        summary[f"{layer}_varying"] = [name for name, c in columns.items() if len(c[layer]) > 1]
    return {
        "summary": summary,
        "columns_in_array_order": frozen["names"],
        "intercept": frozen["intercept"],
        "feature_audit": columns,
        "ties": tied,
        "source_hashes": {
            "witness": digest(witness_path),
            "predictions": digest(forecast_path),
            "frozen_model": MODEL_SHA,
            "lexicons": lexhash,
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root, out = args.root.resolve(strict=True), args.out.resolve()
    check(out.is_relative_to(root) and not out.exists(), "Choose an unused output file in the project")
    result = audit(root)
    save(out, result)
    print(json.dumps(result["summary"], ensure_ascii=False))
    print("Raw feature values", {k: v["raw"] for k, v in result["feature_audit"].items()})
