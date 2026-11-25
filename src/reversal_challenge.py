"""Fresh matched four-by-four stimuli and opaque, single-input inference packets."""
from hashlib import sha256
from pathlib import Path
import sys

from .semantic_turn_relation import canonical, card, file_hash, seal
from .semicolon_turn_sources import closing_pair
from .reversal_sources import exact
from .yu_review_transfer import read


# The first alternative overturns the prior claim. The second sustains it.
# Gold and the associated alternatives are withheld from both classifiers.
FRESH = (
    ("獨對寒爐，料灰已冷；侍童探處，","指上生疼","指上無溫"),
    ("商人按券，言金足重；市吏懸衡，","銖兩猶虧","銖兩無虧"),
    ("遠瞻宮額，舊題尚在；近拂浮塵，","字已全非","字尚如昔"),
    ("山民候汛，皆言水漲；守堰量痕，","較昨猶低","較昨猶高"),
    ("驛書先至，報兒登第；榜文新出，","其名竟闕","其名竟在"),
    ("故人相語，此橋已毀；行車及岸，","輪過橋頭","兩岸無梁"),
    ("田家望樹，疑梅已放；攀枝近看，","滿枝惟雪","滿枝皆花"),
    ("樓中置漏，謂時方午；庭前測影，","日已西沉","日正在中"),
    ("初拆封泥，皆云璽偽；更參舊印，","毫髮無殊","刀痕迥異"),
    ("昨傳邊信，謂關未啟；今臨塞口，","重門盡闢","重門尚閉"),
    ("醫工診脈，斷為寒證；復察其舌，","乃屬熱邪","乃屬陰寒"),
    ("工師指柱，謂心已蠹；斧斤初入，","木理猶堅","中藏朽屑"),
    ("先聞詔旨，將蠲舊賦；今觀縣牒，","催科如故","逋租悉免"),
    ("里人指壁，謂圖臥虎；持燭審形，","畫中乃豹","畫中是虎"),
    ("將軍出帳，誓無退意；俄傳令箭，","全軍後撤","全軍向前"),
    ("寺僧護卷，謂經已闕；展讀終篇，","首尾俱全","後幅全空"),
)


def prepare(run):
    packets=read(run/"inputs/pair-packet.json")
    payload=[]
    key={}
    def add(group,ident,text,marked):
        oid=sha256(("rev-transfer1/"+group+"/"+ident).encode()).hexdigest()[:20]
        if oid in key:
            raise ValueError("ID collision")
        key[oid]=[group,ident]
        payload.append(dict(id=oid,text=text,marked=marked))
    for k,(stem,r,c) in enumerate(FRESH):
        for side,end in (("flip",r),("continue",c)):
            text=stem+end+"。"
            if not exact(text) or closing_pair(text)["second"]!=end:
                raise ValueError(text)
            add(side,str(k),text,closing_pair(text)["marked"])
    for side in ("true","foils"):
        for row in packets[side]:
            add(side,row["id"],row["text"],row["marked"])
    payload.sort(key=lambda r:r["id"])
    seal(run/"inputs/inference.json",canonical([dict(id=r["id"],text=r["text"]) for r in payload]))
    seal(run/"private/key.json",canonical(key))
    old=run/"previous"
    for sub in ("inputs","seals","private"):
        (old/sub).mkdir(exist_ok=True,parents=True)
    path=old/"inputs/pair-packet.json"
    seal(path,canonical(dict(true=[dict(id=r["id"],marked=r["marked"]) for r in payload],foils=[])))
    seal(old/"seals/pair-packet.sha256",f"{file_hash(path)}  inputs/pair-packet.json\n".encode())
    seal(old/"seals/relation-card.json",canonical(card()))


if __name__=="__main__":
    prepare(Path(sys.argv[1]))
