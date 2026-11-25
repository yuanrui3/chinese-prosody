"""Score one complete paired sentence per input line with a sealed Gilbreth detector."""
import argparse
import json
from pathlib import Path
import sys

from . import reversal_detector
from .semantic_turn_relation import card, file_hash
from .semicolon_turn_sources import closing_pair
from .semicolon_turn_sensitivity import strict_shape
from .yu_review_transfer import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("detector", type=Path, help="Path to seals/detector.json in the study archive")
    args = parser.parse_args()
    fit = read(args.detector)
    if fit["code"] != file_hash(Path(reversal_detector.__file__)) or fit["model"] != card()["revision"]:
        parser.error("The model or classifier code differs from the fitted detector")
    sentences = [line.strip() for line in sys.stdin if line.strip()]
    if not sentences:
        parser.error("Supply one paired sentence per line")
    for k, sentence in enumerate(sentences, 1):
        pair = closing_pair(sentence)
        if not pair or not strict_shape(pair)[0]:
            parser.error(f"Line {k} needs one semicolon and two distinct equal-length closing phrases with lead-ins")
    items = [(str(k), sentence) for k, sentence in enumerate(sentences, 1)]
    rows = reversal_detector.run_model(items)
    for ident, sentence in items:
        r = rows[ident]
        print(json.dumps(dict(line=int(ident), text=sentence, reversal=r["margin"] > fit["threshold"],
                              paraphrase=r["paraphrase"], margin=r["margin"], threshold=fit["threshold"]),
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
