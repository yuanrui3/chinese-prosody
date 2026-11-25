"""Describe the binary flag by itself and the literal four-character template."""

from pathlib import Path
import re
from statistics import fmean
import sys

from .semantic_turn_pairs import normalized
from .semantic_turn_relation import canonical, seal
from .semicolon_turn_sensitivity import strict_shape
from .yu_review_transfer import by_work, compare, read, summarize


def describe(run):
    rows = read(run / "private/joined.json")
    works = {w: compare(g, "qwen_flag") for w, g in by_work(rows).items()}
    informative = [v["ordering"] for v in works.values() if v["pairs"]]
    alone = dict(by_work=works, ordering=fmean(informative) if informative else None,
                 **{k: sum(v[k] for v in works.values()) for k in ("pairs", "correct", "tied", "inverted")})
    seal(run / "results/flag-alone.json", canonical(alone))
    four = [r for r in rows if r["width"] == 4 and strict_shape(r)[0]]
    literal = [r for r in four if strict_shape(r)[1] and
               all(len(normalized(p)) == 4 for p in re.split("[，,；;]", r["text"]))]
    output = {name: dict(n=len(subset), works=len(by_work(subset)),
                         models={m: summarize(subset, m) for m in ("always_six", "current", "qwen_turn")}
                         if subset else {}) for name, subset in (("four_character_endings", four),
                                                                 ("four_by_four_phrases", literal))}
    seal(run / "results/four-character-endings.json", canonical(output))


if __name__ == "__main__":
    describe(Path(sys.argv[1]))
