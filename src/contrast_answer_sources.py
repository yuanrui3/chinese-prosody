"""Acquire and freeze the edition witnesses for the contrasting-answer experiment."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

INDEX = 2573077
EXTRA = {"與陳伯之書": "letter", "答東阿王書": "letter", **dict.fromkeys(
    ("景福殿賦", "江賦", "海賦 (木華)", "蜀都賦 (左思)", "西都賦", "魯靈光殿賦"), "parallel rhapsody")}
API = "https://zh.wikisource.org/w/api.php?"
PUNCT = re.compile(r'[^。！？；]+[。！？；]+[」』”’]*|[^。！？；]+$')


def get(**params):
    url = API + urlencode(dict(action="query", format="json", prop="revisions", rvslots="main",
                               rvprop="ids|content", **params))
    req = Request(url, headers={"User-Agent": "ChineseProsodyResearch/1.0 (github.com/yuanrui3/chinese-prosody)"})
    with urlopen(req, timeout=45) as response:
        return list(json.load(response)["query"]["pages"].values())


def anthology(index):
    genres = {}
    section = None
    for line in index.splitlines():
        if line.startswith("=="):
            section = re.search(r"卷([二三四五六七八九])[　\s]*([^=]+)", line)
        if section and line.startswith("#[["):
            title = line[3:].split("]]")[0].split("|")[0]
            genres[title] = section[2].strip()
    return genres


def prose_lines(raw):
    # Header templates can be nested. Scan to the matching closing braces.
    start = re.search(r"\{\{header\b", raw, flags=re.I)
    if not start:
        return []
    depth = 0
    for brace in re.finditer(r"\{\{|\}\}", raw[start.start():]):
        depth += 1 if brace[0] == "{{" else -1
        if not depth:
            raw = raw[start.start() + brace.end():]
            break
    raw = re.sub(r"<!--.*?-->|<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", "", raw, flags=re.S | re.I)
    paragraphs = []
    for line in raw.splitlines():
        line = re.sub(r"\[\[(?!Category:|分類:)([^\[\]]+)\]\]", lambda m: m[1].split("|")[-1], line, flags=re.I)
        line = re.sub(r"<[^>]+>|\{\{gap\}\}|'''?", "", line, flags=re.I)
        if re.search(r"(亂曰|亂辭曰|其歌曰|歌曰|繫曰|系曰|詩曰)[：:]", line):
            # The remainder of this work is outside the fixed prose selection.
            line = re.split(r"(?:亂曰|亂辭曰|其歌曰|歌曰|繫曰|系曰|詩曰)[：:]", line)[0]
            stop = True
        else:
            stop = False
        text = "".join(line.split())
        if text and re.search("[。！？；]", text) and not re.search(r'[{}\[\]<>|=□]', text):
            paragraphs.append(text)
        if stop:
            break
    return paragraphs


def snapshot(folder, titles=None, paragraphs_from=prose_lines, expected_authors=None):
    dest = folder / "editions"
    dest.mkdir(exist_ok=True)
    if titles is None:
        index = get(revids=str(INDEX))[0]["revisions"][0]["slots"]["main"]["*"]
        (dest / "anthology-index.txt").write_text(index)
        titles = anthology(index)
        titles.update(EXTRA)
    names = list(titles)
    manifest, rows, missing = [], [], []
    for step in range(0, len(names), 12):
        for page in get(titles="|".join(names[step:step + 12])):
            title = page["title"]
            if "revisions" not in page:
                missing.append([title, "no revision"])
                continue
            rev = page["revisions"][0]
            rid, raw = rev["revid"], rev["slots"]["main"]["*"]
            (dest / f"{rid}.wiki").write_text(raw)
            author = re.search(r"\|\s*author\s*=\s*([^\n|}]+)", raw, flags=re.I)
            if not author or not (paras := paragraphs_from(raw)):
                missing.append([title, "no attributed clean paragraphs"])
                continue
            name = author[1].strip().strip("[]")
            if expected_authors is not None and name != expected_authors[title]:
                missing.append([title, f"edition credits {name}; specified author differs"])
                continue
            wid = f"w{rid}"
            hashes = {}
            order = 0
            for pn, para in enumerate(paras, 1):
                section = f"p{pn:02d}"
                units = PUNCT.findall(para)
                if "".join(units) != para:
                    raise ValueError(f"Unit split lost source characters in {title}")
                hashes[section] = hashlib.sha256(para.encode()).hexdigest()
                for unit in units:
                    order += 1
                    rows.append(dict(id=f"{wid}-{order:03d}", work_id=wid, order=order, section=section,
                                     text=unit, author=name, title=title,
                                     incomplete=not re.search(r"[。！？；][」』”’]*$", unit)))
            manifest.append(dict(work_id=wid, author=name, title=title, revision=rid, genre=titles[title],
                                 source_url=f"https://zh.wikisource.org/w/index.php?oldid={rid}",
                                 rights="Ancient text public domain; Chinese Wikisource contributors, CC BY-SA 4.0",
                                 wiki_sha256=hashlib.sha256(raw.encode()).hexdigest(), paragraph_hashes=hashes))
    for f, v in (("witness.json", rows), ("works.json", manifest), ("source-exclusions.json", missing)):
        (folder / f).write_text(json.dumps(v, ensure_ascii=False, indent=2))
    print("Acquired", len(manifest), "works,", len(rows), "units. Unavailable:", missing, flush=True)


if __name__ == "__main__":
    import sys
    snapshot(Path(sys.argv[1]))
