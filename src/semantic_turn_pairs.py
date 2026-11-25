"""Choose one equal-width pair per sentence without using the words' semantic relation."""

from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import re
import sys
from unicodedata import normalize

from data.phonology.annotate import han
from .yu_review_transfer import read, write


PHRASE = re.compile(r"[^，,、：:；;。！？.!?]+")
SEMICOLON = re.compile(r"[；;]")


def normalized(text):
    return "".join(c for c in normalize("NFKC", text) if han(c))


def phrases(text):
    return [(m.start(), m.end(), m[0], clean) for m in PHRASE.finditer(text)
            if (clean := normalized(m[0]))]


def marked_pair(text, parts, i, j, route, replacement=None):
    start, end, first, _ = parts[i]
    start2, end2, second, clean = parts[j]
    if replacement is not None:
        second = replacement
    return {"text": text[:start2] + second + text[end2:], "i": i, "j": j,
            "route": route, "width": len(clean), "first": first, "second": second,
            "marked": (text[:start] + "【甲：" + first + "】" + text[end:start2]
                       + "【乙：" + second + "】" + text[end2:])}


def select_pair(text):
    parts = phrases(text)
    breaks = list(SEMICOLON.finditer(text))
    candidates = []
    if len(breaks) == 1:
        left = [i for i, p in enumerate(parts) if p[1] <= breaks[0].start()]
        right = [j for j, p in enumerate(parts) if p[0] >= breaks[0].end()]
        if left and right:
            candidates.append((left[-1], right[-1], "semicolon_closings"))
    candidates.extend((i-1, i, "adjacent") for i in range(len(parts)-1, 0, -1))
    for i, j, route in candidates:
        a, b = parts[i][3], parts[j][3]
        if len(a) == len(b) and len(a) >= 3 and a != b:
            return marked_pair(text, parts, i, j, route)
    return None


def prepare(run):
    corpus = read(run / "inputs/corpus.json")
    lookup = defaultdict(list)
    for u in corpus:
        for _, _, literal, normalized_part in phrases(u["text"]):
            lookup[(u["work_id"], len(normalized_part))].append((u, literal, normalized_part))
    true, foils = [], []
    for u in corpus:
        if not u["target"]:
            continue
        pair = select_pair(u["text"])
        if pair is None:
            raise ValueError(f'Ineligible target: {u["id"]}')
        true.append({"id": u["id"], **pair})
        seen_in_sentence = {p[3] for p in phrases(u["text"])}
        options = []
        for donor, variant, clean in lookup[u["work_id"], pair["width"]]:
            if donor["id"] == u["id"] or clean in seen_in_sentence:
                continue
            token = "|".join(("20261124", u["id"], donor["id"], variant)).encode()
            options.append((donor["paragraph"] != u["paragraph"], sha256(token).hexdigest(),
                            donor["id"], variant))
        if options:
            _, _, donor_id, variant = min(options)
            altered = marked_pair(u["text"], phrases(u["text"]), pair["i"], pair["j"],
                                  pair["route"], variant)
            foils.append({"id": u["id"], "donor_id": donor_id, **altered})
    if len(true) != len({r["id"] for r in true}) or not true:
        raise ValueError("Missing targets or duplicated sentence IDs")
    write(run / "inputs/pair-packet.json", {"true": true, "foils": foils})


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
