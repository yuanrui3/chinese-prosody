"""Seal and apply a two-prompt semantic annotation of marked classical Chinese phrases."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .contrast_answer_relation import REV


PROMPTS = (
    "請讀完整古文句。只辨其中標作甲、乙的兩處在全文中的意義關係。"
    "若甲、乙聚焦同一人事、結果或可辨的同一尺度，而且乙把甲已建立的態勢、預期或立場折向另一面，選A。"
    "必須能說清：哪一件事，在甲怎樣，在乙怎樣改觀。語意可以借上下文才顯出。"
    "僅分列兩個地方、並置兩幅景、詞義相反卻各說各的、同義重申或照原方向推進，均選B。"
    "全文別處有變化而這兩處未形成轉折，亦選B。存疑選B。只答A或B。",
    "讀句中的兩個標記，判斷乙是否使人改讀甲。"
    "A表示兩處可以並排或接續理解，或關係不足以確定。B表示同一事情或衡量角度上，"
    "甲原先讓人理解成一種情勢，乙作出明確的轉向、翻案或出人意表的落實。"
    "請先默想甲、乙共同談甚麼，再看乙怎樣把理解帶往別一方向。"
    "地名、方位、褒貶、反義字相對本身不算；其他地方的轉折也不算。只輸出一個字母。",
)

PROBES = (
    ("motivation", "斬將搴旗，【甲：出於料外】；堅城便地，【乙：盡落彀中】。", True),
    ("reversed_fortune", "【甲：初謂難全】，【乙：乃知可濟】。", True),
    ("unexpected_return", "【甲：已謂舟沉】，【乙：忽見帆歸】。", True),
    ("change_of_course", "【甲：向欲棄城】，【乙：今思固守】。", True),
    ("locations", "【甲：城東列柳】，【乙：郭西栽松】。", False),
    ("lexical_opposites", "【甲：北山積雪】，【乙：南浦生花】。", False),
    ("synonymous_parallel", "【甲：山色常青】，【乙：峰容長翠】。", False),
    ("continued_action", "【甲：晨過西津】，【乙：暮行東道】。", False),
)


def canonical(item):
    return (json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def file_hash(path):
    with path.open("rb") as f:
        h = sha256()
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
        return h.hexdigest()


def seal(path, data):
    with NamedTemporaryFile(dir=path.parent) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            os.link(tmp.name, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError(f"Previously sealed content differs: {path.name}")


def snapshot():
    return Path(os.environ["HF_HOME"]) / "hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots" / REV


def card():
    # Hub binaries are content-addressed by their LFS SHA-256. The classifier job
    # rehashes all four shards to verify the bytes behind these symlinks.
    directory = snapshot()
    shards = sorted(directory.glob("model-*.safetensors"))
    if len(shards) != 4 or any(not p.is_symlink() or len(p.resolve().name) != 64 for p in shards):
        raise ValueError("Unexpected cached checkpoint layout")
    files = {p.name: file_hash(p) for p in sorted(directory.iterdir()) if p not in shards}
    return dict(revision=REV, sha256=files, weights_sha256={p.name: p.resolve().name for p in shards},
                prompts=PROMPTS, probe_items=PROBES, positive_option=["A", "B"],
                rule="Both prompts must vote yes. A logit tie gives no positive vote.",
                code_sha256=file_hash(Path(__file__)))


def classify(run):
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    expected_card = (run / "seals/relation-card.json").read_bytes()
    current = card()
    if expected_card != canonical(current):
        raise ValueError("Classifier card changed after freeze")
    directory = snapshot()
    for name, h in current["weights_sha256"].items():
        if file_hash(directory / name) != h:
            raise ValueError(f"Checkpoint bytes differ: {name}")
    source = run / "inputs/pair-packet.json"
    h = file_hash(source)
    if h != (run / "seals/pair-packet.sha256").read_text().split()[0]:
        raise ValueError("Phrase-pair packet differs from its seal")
    packet = json.loads(source.read_bytes())
    hidden = {"score", "grade", "author", "title", "prediction", "editorial"}
    items = []
    for side in ("true", "foils"):
        ids = set()
        for r in packet[side]:
            if (hidden.intersection(r) or r["id"] in ids or
                    r["marked"].count("【甲：") != 1 or r["marked"].count("【乙：") != 1):
                raise ValueError("Malformed or unmasked phrase-pair input")
            ids.add(r["id"])
            items.append((side, r["id"], r["marked"]))
    items += [("probes", key, marked) for key, marked, expected in PROBES]
    tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(
        directory, local_files_only=True, torch_dtype=torch.bfloat16).to("cuda").eval()
    label_ids = [tokenizer.encode(c, add_special_tokens=False) for c in "AB"]
    if not all(len(ids) == 1 for ids in label_ids):
        raise ValueError("A and B must be single-token labels")
    cols = [ids[0] for ids in label_ids]
    rows = [dict(id=key, flags=[], a_minus_b=[]) for _, key, _ in items]
    with torch.inference_mode():
        for prompt_index, instruction in enumerate(PROMPTS):
            for start in range(0, len(items), 8):
                texts = [tokenizer.apply_chat_template([
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": marked + "\n判定："}],
                    tokenize=False, add_generation_prompt=True) for _, _, marked in items[start:start+8]]
                batch = tokenizer(texts, padding=True, return_tensors="pt").to(model.device)
                logits = model(**batch, logits_to_keep=1, use_cache=False).logits[:, -1, cols].float().cpu()
                for k, (a, b) in enumerate(logits.tolist(), start):
                    rows[k]["flags"].append(a > b if prompt_index == 0 else b > a)
                    rows[k]["a_minus_b"].append(a - b)
    result = dict(packet_sha256=h, card_sha256=sha256(expected_card).hexdigest(),
                  revision=REV, torch=torch.__version__, transformers=transformers.__version__,
                  hardware=torch.cuda.get_device_name(), batch_size=8, dtype="bfloat16")
    for side in ("true", "foils", "probes"):
        result[side] = [dict(r, consensus=all(r["flags"])) for item, r in zip(items, rows) if item[0] == side]
    path = run / "private/semantic-relation.json"
    seal(path, canonical(result))
    seal(run / "seals/relation.sha256", f"{file_hash(path)}  private/semantic-relation.json\n".encode())
    print("Sealed semantic classifications for", len(items), "items.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "classify"))
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "freeze":
        seal(args.run / "seals/relation-card.json", canonical(card()))
    else:
        classify(args.run)
