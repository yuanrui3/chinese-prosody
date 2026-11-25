"""Descriptive sensitivity to source-marked quotations embedded in official prose."""

from argparse import ArgumentParser
from pathlib import Path

from data.phonology.annotate import han
from .semantic_turn_test import NAMES
from .yu_review_transfer import read, summarize, write


def quoted_sentences(units):
    marked, stack, previous = set(), [], None
    closers = {"「": "」", "『": "』", "“": "”", "‘": "’"}
    for u in units:
        if u["work_id"] != previous and stack:
            raise ValueError(f"Unclosed quotation at end of {previous}")
        previous = u["work_id"]
        for char in u["text"]:
            if char in closers:
                stack.append(closers[char])
            elif char in closers.values():
                if not stack or stack.pop() != char:
                    raise ValueError(f"Unmatched quotation mark in {u['id']}")
            elif stack and han(char):
                marked.add(u["id"])
    if stack:
        raise ValueError(f"Unclosed quotation at end of {previous}")
    return marked


def audit(run):
    marked = quoted_sentences(read(run / "inputs/corpus.json"))
    rows = read(run / "private/joined.json")
    kept = [r for r in rows if r["id"] not in marked]
    return {"excluded_ids": [r["id"] for r in rows if r["id"] in marked],
            "models": {name: summarize(kept, name) for name in NAMES}}


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("run", type=Path)
    run = parser.parse_args().run
    write(run / "results/quotation-audit.json", audit(run))
