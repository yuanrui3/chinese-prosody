#!/usr/bin/env python3
"""Extract checked work spans from pinned Wikisource anthology witnesses."""

import argparse
import hashlib
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from build import copy_atomic, digest


SOURCE = "https://zh.wikisource.org"
LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"
REGISTRY = Path(__file__).with_name("anthology_sources.json")
BLOCKS = {"br", "div", "h2", "h3", "h4", "li", "p", "td", "tr"}


class WitnessText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def witness(raw, entry, normalize_only):
    revision = entry["revision"]
    path = raw / f"{revision}.json"
    if not path.is_file():
        if normalize_only:
            raise FileNotFoundError(f"Missing staged Wikisource response: {path}")
        query = urlencode({
            "action": "parse", "oldid": revision, "prop": "text|revid",
            "format": "json", "formatversion": 2, "disableeditsection": 1,
        })
        url = f"{SOURCE}/w/api.php?{query}"
        request = Request(url, headers={"User-Agent": "shunkou-research/0.1 (classical text corpus)"})
        with urlopen(request, timeout=45) as response:
            payload = response.read()
        parse_witness(payload, entry)
        copy_atomic(BytesIO(payload), path)
    return parse_witness(path.read_bytes(), entry), digest(path)


def parse_witness(payload, entry):
    response = json.loads(payload)
    page = response.get("parse", {})
    if page.get("revid") != entry["revision"] or page.get("title") != entry["source_page"]:
        raise ValueError(f"Unexpected Wikisource revision or page for {entry['id']}")
    parser = WitnessText()
    parser.feed(page["text"])
    parser.close()
    text = unicodedata.normalize("NFC", "".join(parser.parts))
    # These witnesses mark commentary and alternate readings explicitly.
    return re.sub(r"〈[^〈〉]*〉|一作「[^」]*」", "", text).replace("\u200b", "")


def extract(text, entry):
    start, end, work_id = entry["start"], entry["end"], entry["id"]
    start_index = text.find(start)
    if start_index < 0 or text.find(start, start_index + len(start)) >= 0:
        raise ValueError(f"Nonunique or missing opening marker for {work_id}")
    rest = text[start_index:]
    if rest.count(end) != entry.get("end_occurrences", 1):
        raise ValueError(f"Unexpected closing marker count for {work_id}")
    span = rest[:rest.rfind(end) + len(end)]
    return [line.strip() for line in span.splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Gilbreth project scratch root")
    parser.add_argument("--normalize-only", action="store_true", help="reuse staged API responses")
    args = parser.parse_args()

    raw = args.root / "data" / "raw" / "anthologies"
    destination = args.root / "data" / "collections" / "anthology-seed.jsonl"
    entries = json.loads(REGISTRY.read_text(encoding="utf-8"))
    records = []
    for entry in entries:
        text, source_hash = witness(raw, entry, args.normalize_only)
        lines = extract(text, entry)
        source_fields = {"start", "end", "end_occurrences", "revision", "source_page"}
        metadata = {key: value for key, value in entry.items() if key not in source_fields}
        records.append({
            **metadata,
            "corpus": "anthology-seed",
            "lines": lines,
            "text_sha256": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
            "source": {
                "page": entry["source_page"],
                "revision": entry["revision"],
                "url": f"{SOURCE}/w/index.php?oldid={entry['revision']}",
                "raw_sha256": source_hash,
                "work_rights": "public domain in the United States",
                "transcription_license": LICENSE,
                "transcription_attribution": "Chinese Wikisource contributors",
            },
        })
    output = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
    copy_atomic(BytesIO(output.encode("utf-8")), destination)
    print(f"anthology-seed: {len(records)} records, {destination}")


if __name__ == "__main__":
    main()
