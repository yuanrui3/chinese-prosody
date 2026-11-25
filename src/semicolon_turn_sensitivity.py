"""Check complete comma-delimited closings, four-phrase periods and document forms."""

from collections import Counter
from pathlib import Path
import re
import sys

from .semantic_turn_pairs import normalized
from .semicolon_turn_test import MODELS
from .yu_review_transfer import read, summarize, write


def strict_shape(row):
    left, right = re.split("[；;]", row["text"])
    parts = [list(filter(None, (normalized(p) for p in re.split("[，,]", arm)))) for arm in (left, right)]
    complete = (all(len(p) >= 2 for p in parts) and parts[0][-1] == normalized(row["first"])
                and parts[1][-1] == normalized(row["second"]))
    return complete, complete and all(len(p) == 2 for p in parts)


def sensitivity(run):
    rows = read(run / "private/joined.json")
    works = {w["work_id"]: w for w in read(run / "inputs/sources.json")["works"]}
    clean = [r for r in rows if strict_shape(r)[0]]
    groups = {
        "complete_comma_closings": clean,
        "two_comma_phrases_per_arm": [r for r in clean if strict_shape(r)[1]],
        "memorials_and_formal_petitions": [r for r in clean if works[r["work_id"]]["genre"] in set("表啟箋牋")],
    }
    return {name: dict(n=len(group), works=len({r["work_id"] for r in group}),
                       grades=dict(Counter(r["grade"] for r in group)),
                       models={m: summarize(group, m) for m in MODELS} if group else {})
            for name, group in groups.items()}


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    write(folder / "results/shape-sensitivity.json", sensitivity(folder))
