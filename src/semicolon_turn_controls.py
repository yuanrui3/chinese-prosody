"""Diagnostic controls specified after the primary comparison, with the classifier frozen."""

from argparse import ArgumentParser
from pathlib import Path

from .semantic_turn_relation import canonical, seal
from .semantic_turn_test import table
from .semicolon_turn_sources import closing_pair
from .semicolon_turn_test import verified_votes
from .yu_review_transfer import digest, read


# The first three phrases are identical within each constructed pair. The two
# alternatives reverse or confirm the same expectation at the same final beat.
ITEMS = (
    ("昨日臨津，眾謂舟沉；今朝問渡，", "親見舟還", "但見殘桅"),
    ("城頭夜望，疑為援騎；營外晨看，", "乃是胡兵", "果是王師"),
    ("春巡原上，咸憂禾槁；秋按田間，", "乃見盈倉", "惟見空囷"),
    ("昨披獄牘，群稱有罪；今按真憑，", "始雪其冤", "益明其辜"),
    ("客行山際，但聞泉咽；客到巖陰，", "乃識人歌", "果見泉流"),
    ("初循圖籍，道通南郭；再尋故跡，", "路斷深崖", "路入南城"),
    ("壇前問卜，卜者言凶；事定詢人，", "合門蒙福", "舉室遭殃"),
    ("隔簾聽響，認作疏鐘；推窗細辨，", "始知砧杵", "正是鐘聲"),
)


def prepare(run):
    task = run / "diagnostic"
    for sub in ("inputs", "seals", "private"):
        (task / sub).mkdir(parents=True, exist_ok=True)
    packet = {"true": [], "foils": []}
    for k, (stem, turn, continuation) in enumerate(ITEMS, 1):
        for side, ending in (("true", turn), ("foils", continuation)):
            pair = closing_pair(stem + ending + "。")
            if not pair or pair["width"] != 4 or pair["second"] != ending:
                raise ValueError(f"Unequal control at position {k}")
            packet[side].append({"id": f"C{k:02}", **pair})
    for original in read(run / "inputs/pair-packet.json")["true"]:
        # Hold words and both marked spans fixed. Only the semicolon glyph changes.
        marked = original["marked"].replace("；", "，").replace(";", ",")
        if marked == original["marked"]:
            raise ValueError("Missing semicolon")
        packet["true"].append(dict(id=original["id"], marked=marked))
    path = task / "inputs/pair-packet.json"
    seal(path, canonical(packet))
    seal(task / "seals/pair-packet.sha256", f"{digest(path)}  inputs/pair-packet.json\n".encode())
    seal(task / "seals/relation-card.json", (run / "seals/relation-card.json").read_bytes())


def report(run):
    task = run / "diagnostic"
    result = read(task / "private/semantic-relation.json")
    original = read(run / "private/semantic-relation.json")
    if (result["card_sha256"] != original["card_sha256"]
            or result["packet_sha256"] != digest(task / "inputs/pair-packet.json")):
        raise ValueError("Diagnostic inputs differ")
    yes, no = verified_votes(result["true"]), verified_votes(result["foils"])
    authentic = verified_votes(original["true"])
    if len(no) != len(ITEMS) or yes.keys() != (no.keys() | authentic.keys()):
        raise ValueError("Control IDs differ")
    paired = table({i: yes[i] for i in no}, no)
    # The four probe outcomes distinguish both-correct from both-flagged.
    decisions = {i: {"turn": yes[i], "continuation": no[i]} for i in sorted(no)}
    result = dict(constructed=paired, both_classified_correctly=paired["first_only"],
                  controls=decisions, original_semicolon_and_same_words_comma=table(
                      authentic, {i: yes[i] for i in authentic}))
    seal(run / "results/construct-check.json", canonical(result))


if __name__ == "__main__":
    p = ArgumentParser()
    p.add_argument("step", choices=("prepare", "report"))
    p.add_argument("run", type=Path)
    args = p.parse_args()
    (prepare if args.step == "prepare" else report)(args.run)
