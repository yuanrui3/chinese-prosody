"""Frozen Qwen paraphrase followed by counterbalanced entailment decisions."""
from argparse import ArgumentParser
from pathlib import Path
from statistics import fmean

from .semantic_turn_relation import canonical, card, file_hash, seal, snapshot
from .semicolon_turn_controls import ITEMS
from .semantic_turn_test import indexed
from .yu_review_transfer import read


NOTES = """你是文言文校讀者。把原句的兩半各譯為一句具體的白話。說清誰或何事，起初怎樣以為、後來實際如何。若只是兩件事分別陳述，就忠實保留兩件事。不可補造原文沒有的期待。用「前：…。後：…。」回答，不作修辭評價。"""
DECISION = """根據古文和供參考的白話，判斷後半是否推翻前半對同一件事情的預期、認定或原有狀態。另舉一例、比喻、前後相承、證實先前之言、對不同對象用反義詞，都屬「未翻轉」。例如：以為門閉，推之即開，是翻轉；以為門閉，推而不動，是未翻轉。若不確定，選未翻轉。"""
OPTIONS = ("A=翻轉，B=未翻轉。只答一個字母。", "A=未翻轉，B=翻轉。只答一個字母。")


def run_model(items):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    revision = snapshot()
    for name,sha in card()["weights_sha256"].items():
        if file_hash(revision/name)!=sha:
            raise ValueError("Unexpected model weights")
    tok=AutoTokenizer.from_pretrained(revision,local_files_only=True,padding_side="left")
    model=AutoModelForCausalLM.from_pretrained(revision,local_files_only=True,torch_dtype=torch.bfloat16).to("cuda").eval()
    def batch(instruction, contents):
        prompts=[tok.apply_chat_template([dict(role="system",content=instruction),dict(role="user",content=s)],
                                        tokenize=False,add_generation_prompt=True) for s in contents]
        return tok(prompts,return_tensors="pt",padding=True).to(model.device)
    labels=[tok.encode(s,add_special_tokens=False) for s in ("A","B")]
    if any(len(ids)!=1 for ids in labels):
        raise ValueError("Choice tokens changed")
    cols=[ids[0] for ids in labels]
    output={}
    with torch.inference_mode():
        for start in range(0,len(items),8):
            chunk=items[start:start+8]
            originals=[s for _,s in chunk]
            inputs=batch(NOTES,originals)
            generated=model.generate(**inputs,max_new_tokens=100,do_sample=False,pad_token_id=tok.pad_token_id)
            notes=tok.batch_decode(generated[:,inputs["input_ids"].shape[1]:],skip_special_tokens=True)
            if any(not n.strip() for n in notes):
                raise ValueError("Empty paraphrase")
            cases=[f"古文：{s}\n參考譯文：{n}\n判定：" for s,n in zip(originals,notes)]
            votes=[]
            for k,prompt in enumerate(OPTIONS):
                x=batch(DECISION+prompt,cases)
                logits=model(**x,logits_to_keep=1,use_cache=False).logits[:,-1,cols].float().cpu()
                votes.append([(a-b) if k==0 else (b-a) for a,b in logits.tolist()])
            for (i,_),note,a,b in zip(chunk,notes,*votes):
                if i in output:
                    raise ValueError("Duplicate input ID")
                output[i]=dict(paraphrase=note,margins=[a,b],margin=fmean((a,b)))
    return output


def calibrated(dev):
    """Prefer complete pairs, then individual accuracy, then a threshold near zero."""
    margins=sorted(set(v["margin"] for v in dev.values()))
    candidates={0.,margins[0]-0.5,margins[-1]+0.5}
    candidates.update((a+b)/2 for a,b in zip(margins,margins[1:]))
    def result(t):
        # Strictly greater than the threshold is a positive decision.
        pairs=[(dev[f"D{k}R"]["margin"]>t,dev[f"D{k}C"]["margin"]<=t) for k in range(len(ITEMS))]
        return sum(a and b for a,b in pairs), sum(a+b for a,b in pairs),-abs(t),t
    return max(candidates,key=result)


def main(step,run):
    if step=="develop":
        items=[(f"D{i}{suffix}",stem+end+"。") for i,(stem,a,b) in enumerate(ITEMS)
               for suffix,end in (("R",a),("C",b))]
        outputs=run_model(items)
        fit=dict(records=outputs,threshold=calibrated(outputs),code=file_hash(Path(__file__)),model=card()["revision"])
        seal(run/"seals/detector.json",canonical(fit))
        return
    fit=read(run/"seals/detector.json")
    if fit["code"]!=file_hash(Path(__file__)) or fit["model"]!=card()["revision"]:
        raise ValueError("Detector differs from development seal")
    cases=read(run/"inputs/inference.json")
    out=run_model([(r["id"],r["text"]) for r in cases])
    for r in out.values():
        r["flag"]=r["margin"]>fit["threshold"]
    seal(run/"private/revised.json",canonical(dict(records=out,threshold=fit["threshold"],
         detector_sha256=file_hash(run/"seals/detector.json"),packet_sha256=file_hash(run/"inputs/inference.json"))))


if __name__=="__main__":
    p=ArgumentParser()
    p.add_argument("step",choices=("develop","apply"))
    p.add_argument("run",type=Path)
    a=p.parse_args()
    main(a.step,a.run)
