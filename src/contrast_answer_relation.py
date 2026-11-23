"""Classify true and displaced predecessor pairs without seeing aesthetic ratings."""

import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from hashlib import sha256

REV = "a09a35458c702b33eeacc393d103063234e8bc28"
PROMPTS = (
    "你是古汉语篇章关系标注员。前句是否提出问题、预期、主张或视角，而后句就同一件事用反面情形作答、纠正或反驳？只有两层都成立才选A。两个景物或方向的对偶、并列罗列、无反转的顺承均选B。存疑选B。只输出一个字母。A=反向作答；B=其他。",
    "辨认相邻文句的关系。若下句仅与上句并排描写、正反相映或继续叙事，选A。若上句留下可辨认的问题、判断或期待，下句所说的反面情况正面回应它，选B。要能指出下句回答了上句什么。拿不准选A。只写A或B。"
)


def classify(run, prompts=PROMPTS, probes=()):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    folder=run/"screen"
    seal=json.loads((folder/"screen.json").read_bytes())
    check_files={}
    items=[]
    for name,side in (("links.json","true"),("foils.json","foils")):
        raw=(folder/name).read_bytes()
        check_files[name]=sha256(raw).hexdigest()
        if check_files[name]!=seal["hashes"][name]:
            raise ValueError("Unsealed text pairs")
        items.extend((side,r) for r in json.loads(raw))
    items.extend(("probes", r) for r in probes)
    path=Path(os.environ["HF_HOME"])/"hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots"/REV
    tok=AutoTokenizer.from_pretrained(path,local_files_only=True,padding_side="left")
    model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,torch_dtype=torch.bfloat16).to("cuda").eval()
    ids=[tok.encode(x,add_special_tokens=False) for x in "AB"]
    if any(len(ix)!=1 for ix in ids):
        raise ValueError("Option labels must each be one token")
    ids=[ix[0] for ix in ids]
    answers=[dict(id=r["id"],prior=r["prior"],target=r["target"],flags=[],a_minus_b=[]) for _,r in items]
    with torch.inference_mode():
        for p,instruction in enumerate(prompts):
            for offset in range(0,len(items),8):
                batch=items[offset:offset+8]
                ps=[tok.apply_chat_template([dict(role="system",content=instruction),
                    dict(role="user",content=f"上句：{r['prior']}\n下句：{r['target']}\n判定：")],
                    tokenize=False,add_generation_prompt=True) for _,r in batch]
                inputs=tok(ps,return_tensors="pt",padding=True).to(model.device)
                logits=model(**inputs,logits_to_keep=1,use_cache=False).logits[:,-1,ids].float().cpu()
                for j,(a,b) in enumerate(logits.tolist(),offset):
                    answers[j]["flags"].append(a>b if p==0 else b>a)
                    answers[j]["a_minus_b"].append(a-b)
    result=dict(checkpoint=REV,prompts=prompts,links_sha256=check_files["links.json"],foils_sha256=check_files["foils.json"])
    for side in (("true","foils","probes") if probes else ("true","foils")):
        result[side]=[v for (label,_),v in zip(items,answers) if label==side]
    with NamedTemporaryFile(dir=run,mode="w",delete=False) as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    try:
        os.link(f.name,run/"relation.json")
    finally:
        os.unlink(f.name)
    print("Sealed relation flags for",len(items),"true and displaced pairs")


if __name__=="__main__":
    classify(Path(sys.argv[1]))
