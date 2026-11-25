"""Reproduce the same-spelling reading comparison attributed to Shen Yue."""

import argparse
from itertools import groupby, product
from pathlib import Path

from . import quantitative_editorial_transfer as text_model
from .critical_preferences import digest
from .yu_review_baseline import predict, save_sealed


def level_run_limits(options):
    def longest(pattern):
        return max((len(list(g)) for tone, g in groupby(pattern) if tone == "平"), default=0)
    runs = [longest(pattern) for pattern in product(*options)]
    return min(runs), max(runs)


def probe(root, run):
    probe_run = run / "reading-probe"
    inputs = probe_run / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    text = "駕雌霓之連蜷。"
    variants = {"checked": "入", "level": "平"}
    corpus = [dict(id=k, work_id=k, section="excerpt", paragraph=1, order=1, target=True, text=text)
              for k in variants]
    save_sealed(inputs / "corpus.json", corpus)
    scores, metadata = predict(root, probe_run, digest(inputs / "corpus.json"),
                               root / "results/ai-jiangnan-complete-20261123-N0QpQKI1")
    lex, _ = text_model.lexicon_data(root)
    _, groups = text_model.annotate_groups(text, lex)
    slots = groups[0]
    if len(groups) != 1 or [s["char"] for s in slots].count("霓") != 1:
        raise ValueError("Changed reading-probe span")
    observed = {}
    for label, tone in variants.items():
        options = []
        for s in slots:
            candidates = s["readings"]["guangyun"]["candidates"]
            allowed = [c for c in candidates if s["char"] != "霓" or c["tone"] == tone]
            cats = sorted({c["pingze"] for c in allowed if c.get("pingze")})
            if not cats:
                raise ValueError(f"Missing categories at {s['char']}")
            options.append(cats)
        observed[label] = dict(tone=tone, category_options=options, longest_level_run=level_run_limits(options))
    if abs(scores["checked"] - scores["level"]) > 1e-10:
        raise ValueError("Context isolation failed for identical strings")
    save_sealed(probe_run / "result.json", dict(text=text, scores=scores, conditional=observed,
                dictionary_candidates=[s["readings"]["guangyun"] for s in slots if s["char"] == "霓"],
                metadata=metadata, reason="Separate same-spelling diagnostic. The dictionary postdates the reported reading."))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("run", type=Path)
    a = parser.parse_args()
    probe(a.root, a.run)
