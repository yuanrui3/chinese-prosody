"""Evaluate cadence completion on fresh, exact-score ties in written parallel prose."""

import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
import re
from statistics import fmean
from tempfile import TemporaryDirectory

from . import contrast_answer_test as previous
from .contrast_answer_relation import classify
from .contrast_answer_sources import PUNCT, prose_lines, snapshot

read, save, digest, check = previous.read, previous.save, previous.digest, previous.check
metrics, ties = previous.metrics, previous.ties
ROOT_PROTOCOL = "cadence-completion.md"

# Exact wiki titles and attributed authors were chosen before model scoring.
SOURCES = {
    "崔融": ["代宰相上尊號表", "代百官請上尊號第二表"],
    "蘇頲": ["代家君讓侍中表", "太陽虧為宰臣乞退表"],
    "李嶠": ["代百寮請立周七廟表", "為朝集使等上尊號表"],
    "上官儀": ["為朝臣賀涼州瑞石表", "為于侍中請赴山陵表"],
    "宋之問": ["為定王武攸暨請降王位表", "早秋上陽宮侍宴序"],
    "張九齡": ["敕安西節度王斛斯書", "敕新羅王金興光書"],
    "徐彥伯": ["同韋子遊神泉詩序"], "張鷟": ["滄州弓高縣實性寺釋迦像碑"],
    "李邕": ["謝賜遊曲江宴表", "國清寺碑（並序）"], "虞世南": ["破邪論序", "孔子廟堂碑"],
    "王績": ["答刺史杜之松書", "重答杜使君書"], "許敬宗": ["賀杭州等龍見並慶雲朱草表", "請收敘廢黜宮僚表"],
    "蕭穎士": ["為揚州李長史賀立皇太子表", "陪李采訪泛舟蓬池宴李文部序"],
    "陳子昂": ["為喬補闕論突厥表", "為河內王等論軍功表"], "魏元忠": ["請解職表"],
    "張衡": ["南都賦", "西京賦"], "司馬相如": ["上林賦", "子虛賦"], "潘岳": ["西征賦", "秋興賦"],
    "嵇康": ["琴賦"], "馬融": ["長笛賦"], "謝莊": ["月賦"], "揚雄": ["羽獵賦", "甘泉賦"],
    "枚乘": ["七發"], "阮籍": ["清思賦"], "宋玉": ["高唐賦", "神女賦"],
}
PROMPTS = (
    "判定古文相鄰兩句是否完成一個相應的節奏。先按語意分節，比對兩處：一是中間或較早的句法槽（例如方位、動作、否定／肯定）；二是收尾的構式。下句須在相應位置以不同字詞接住上句，收成一對。僅字數相等、題材相同、同押韻、整句重抄或單句內部對偶均不足。不要評分或評美。兩處皆可指出選A，否則選B。只輸出字母。",
    "只判篇章節奏的形式。在上、下兩句各找出較早的一拍和結尾的一拍。下句以變化的措辭重現這兩拍的語法／節奏次序，形成配對的收束，才選B。若僅有同長、列舉、押韻、一處相似，或對偶只在一句之內，選A。疑而不能指出兩處亦選A。只寫A或B。",
)
PROBES = (
    dict(id="motivating", prior="茂陵謝病，非無封禪之文；", target="彭澤遺榮，先有《歸來》之作。"),
    dict(id="constructed_match", prior="春風吹柳，初見溪邊之綠；", target="秋雨敲桐，已聞院外之聲。"),
    dict(id="constructed_count", prior="春風吹柳，初見溪邊之綠；", target="城外車行，客子明朝北去。"),
    dict(id="constructed_copy", prior="春風吹柳，初見溪邊之綠；", target="春風吹柳，初見溪邊之綠。"),
)
# Roles are deliberately small and transparent. Treat these as spelling cues, not parsed senses.
FAMILIES = ("有無", "初先始既已猶尚方正復更", "非不未莫弗勿毋", "在於于乎", "其此彼斯茲是",
            "亦乃則遂故因", "雖若縱苟", "上下降升", "南北東西左右前後內外", "入出進退往來",
            "日月星辰", "山水江海天地", "春夏秋冬", "朝暮晨夕", "古今昔", "一二三四五六七八九十百千萬")
LINKERS = "之以而於于其為爲者所乎與如若則乃焉矣也"


def arms(text):
    return tuple(part for s in re.split(r"[，、；。！？：,;:!?]",text)
                 if (part := ties.base.normalized_text({"text":s})))


def profile(text):
    return tuple(map(len, arms(text)))


def matched_slot(x, y):
    return x == y or any(x in f and y in f for f in FAMILIES)


def signals(prior, target):
    a, b = arms(prior), arms(target)
    shape = len(a) >= 2 and tuple(map(len,a)) == tuple(map(len,b))
    if not shape or a == b or len(a[-1]) < 2:
        return dict(shape=shape, anchored=False, closing=[], earlier=[])
    last = len(a)-1
    # Require a nonidentical closing foot and an aligned marker (or changed role)
    # in its final two slots. The earlier cue may occur anywhere before that foot.
    close = []
    for j in range(len(a[-1])-2,len(a[-1])):
        x,y = a[-1][j],b[-1][j]
        if (x==y and x in LINKERS) or (x!=y and matched_slot(x,y)):
            close.append((x,y))
    early = [(x,y) for i,(arm1,arm2) in enumerate(zip(a,b))
             for j,(x,y) in enumerate(zip(arm1,arm2))
             if (i<last or j<len(arm1)-2) and matched_slot(x,y)]
    different = a[-1][-2:] != b[-1][-2:]
    return dict(shape=True, anchored=bool(early and close and different), closing=close, earlier=early)


def paragraphs(raw):
    selected=[]
    for p in prose_lines(re.split(r"(?:銘曰|頌曰|其辭曰|辭曰)[：:]", raw, maxsplit=1)[0]):
        units=PUNCT.findall(p)
        if len(units)<3 or sum("兮" in u for u in units)>len(units)/3:
            continue
        paired=sum(len(q)>=2 and abs(q[-1]-q[-2])<=1 for q in map(profile,units))
        if paired>=2:
            selected.append(p)
    return selected


def acquire(folder):
    by_title={t:a for a,works in SOURCES.items() for t in works}
    def genre(t):
        if t.endswith("賦") or t=="七發":
            return "parallel rhapsody or seven-part exposition"
        return "Tang "+next((s for s in ("表","書","碑","序") if s in t[-5:]),"prose")
    snapshot(folder, {t:genre(t) for t in by_title}, paragraphs, by_title)


def evaluate(run, out):
    folder = run/"screen"
    s = read(folder/"screen.json")
    check(s["protocol"] == digest(run/"inputs/protocol.md"), "Screen protocol mismatch")
    check(s["model"] == ties.base.MODEL_SHA, "Model mismatch")
    for name, expected in s["hashes"].items():
        check(digest(folder/name) == expected, name)
    for path in (folder/"screen.json", run/"inputs/editorial.json", run/"relation.json"):
        check(digest(path) == (path.parent/(path.stem+".sha256")).read_text().split()[0], "Seal mismatch: "+path.name)
    rel = read(run/"relation.json")
    check(rel["links_sha256"] == s["hashes"]["links.json"] and rel["foils_sha256"] == s["hashes"]["foils.json"], "Wrong packets")
    check(rel["prompts"] == list(PROMPTS), "Unexpected prompts")
    keys = {k["index"]: k for k in read(folder/"key.json")}
    index = ties.base.index
    labels = index(read(run/"inputs/editorial.json"), lambda r:r["id"])
    check(set(labels) == {r["editor_id"] for r in keys.values()}, "Rating coverage mismatch")
    src = read(folder/"rows.json")
    def checked_side(side, name):
        inputs = index(read(folder/name), lambda r:r["id"])
        outputs = index(rel[side], lambda r:r["id"])
        check(set(outputs) == set(inputs), "Relation coverage mismatch")
        for ident,r in outputs.items():
            check(all(r[k] == inputs[ident][k] for k in ("prior","target")), "Wrong edge")
            check(len(r["flags"])==2 and all(type(f) is bool for f in r["flags"]), "Invalid decision")
        return outputs
    true = checked_side("true","links.json")
    foils = checked_side("foils","foils.json")
    rows = []
    counts = Counter()
    for t in s["targets"]:
        i = t["index"]
        key = keys[i]
        label = labels[key["editor_id"]]
        a,b = src[i-1]["text"],src[i]["text"]
        pred = true[key["link_id"]]
        check((a,b)==(pred["prior"],pred["target"]), "Alignment mismatch")
        check(type(label["score"]) is int and 1<=label["score"]<=7 and label["quote"] and label["quote"] in b
              and label["reason"].strip(), "Invalid written rating")
        cues = signals(a,b)
        entry = dict(**t, prior=a, text=b, score=label["score"], quote=label["quote"], reason=label["reason"],
                     **cues, flags=pred["flags"], primary=all(pred["flags"]), link_id=key["link_id"])
        if key["link_id"] in foils:
            f=foils[key["link_id"]]
            check(profile(a)==profile(f["prior"]), "Unmatched donor length")
            entry.update(foil=f["prior"], foil_primary=all(f["flags"]), foil_anchored=signals(f["prior"],b)["anchored"])
            counts[entry["primary"], entry["foil_primary"]] += 1
        rows.append(entry)
    blocks=metrics.exact_groups(rows)
    current=[r["current"] for r in rows]
    methods=dict(primary=[r["primary"] for r in rows], length=[r["shape"] for r in rows],
                 anchored=[r["anchored"] for r in rows],
                 prompt_one=[r["flags"][0] for r in rows], prompt_two=[r["flags"][1] for r in rows])
    scores={}
    for name,flags in methods.items():
        scores[name],pairs=metrics.ranking(rows,blocks,flags,metrics.adjusted(current,flags),"primary")
    main=scores["primary"]
    shuffle=metrics.shuffle_control(rows,blocks,pairs,methods["primary"],methods["primary"],main["methods"]["augmented"]["macro"])
    works=main["informative_works"]
    loo={w:fmean(main["by_work"][v]["accuracy"] for v in works if v!=w) for w in works if len(works)>1}
    save(out/"results.json",dict(scores=scores, shuffled=shuffle, leave_one_work_out=loo, rows=rows,
         matched_predecessors={f"{int(a)}/{int(b)}":n for (a,b),n in counts.items()}, probes=rel["probes"],
         seals={p.name:digest(p) for p in (folder/"screen.json",run/"inputs/editorial.json",run/"relation.json")}))
    lines=[f"{len(rows)} targets in {len(blocks)} exact-score groups; {main['n_pairs']} 7/6 pairs in {len(works)} works"]
    for name,item in scores.items():
        lines.append(f"{name}: {item['correct']} correct, {item['wrong']} inverted, {item['tied']} tied; work-weighted {item['methods']['augmented']['macro']}")
    (out/"summary.txt").write_text("\n".join(lines)+"\n")
    (out/"readings.txt").write_text("\n\n".join(
        f"《{s['works'][r['work_id']]['title']}》{r['id']}   {r['prior']} → {r['text']}\n"
        f"Written {r['score']}, current {r['current']!r}, completion bonus {0.25*r['primary']}, always 6\n{r['reason']}"
        for r in rows)+"\n")
    print("\n".join(lines))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase",choices=("screen","relation","evaluate"))
    parser.add_argument("root",type=Path)
    parser.add_argument("run",type=Path)
    args=parser.parse_args()
    root, run=args.root.resolve(),args.run.resolve()
    protocol=digest(run/"inputs/protocol.md")
    check(protocol=="936e7f0cb07d94442e48ab9d747c2e479dd1e2ce5de55921831cbdba611916b5", "Protocol changed")
    if args.phase=="relation":
        classify(run,PROMPTS,PROBES)
        (run/"relation.sha256").write_text(digest(run/"relation.json")+"\n")
        return
    dest=run/("screen" if args.phase=="screen" else "results")
    if dest.exists():
        raise FileExistsError(dest)
    with TemporaryDirectory(dir=run) as tmp:
        out=Path(tmp)/"out"
        out.mkdir()
        if args.phase=="screen":
            previous.screen(root,run,out,extra_reference=("contrast-answer-20261123",),protocol=protocol,
                            paragraphs_from=paragraphs,donor_filter=lambda a,b:profile(a)==profile(b))
            (out/"screen.sha256").write_text(digest(out/"screen.json")+"\n")
        else:
            evaluate(run,out)
        out.rename(dest)


if __name__=="__main__":
    main()
