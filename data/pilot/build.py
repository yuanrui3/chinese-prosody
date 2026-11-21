#!/usr/bin/env python3
"""Materialize reviewed excerpts from pinned Wikisource revisions on Gilbreth."""

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen


MANIFEST = Path(__file__).with_name("passages.json")
WIKISOURCE_API = "https://zh.wikisource.org/w/api.php"


class WikiText(HTMLParser):
    """Read text nodes, skipping citation markers and pronunciation glosses."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skipped_tags = []

    def handle_starttag(self, tag, attrs):
        if self.skipped_tags:
            if tag == self.skipped_tags[-1]:
                self.skipped_tags.append(tag)
            return
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag in {"script", "style", "rt", "rp"} or classes & {"reference", "mw-ref"}:
            self.skipped_tags.append(tag)

    def handle_endtag(self, tag):
        if self.skipped_tags and tag == self.skipped_tags[-1]:
            self.skipped_tags.pop()

    def handle_data(self, data):
        if not self.skipped_tags:
            self.parts.append(data)

    def text(self):
        return normalized_text("".join(self.parts))


def normalized_text(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text))


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as staged:
        try:
            staged.write(value)
            staged.flush()
            Path(staged.name).replace(path)
        finally:
            Path(staged.name).unlink(missing_ok=True)


def parsed_revision(source, cache_dir):
    revision_id = source["revision_id"]
    path = cache_dir / f"{source['source_id']}-{revision_id}.json"
    if path.exists():
        raw = path.read_bytes()
    else:
        parameters = urlencode(dict(
            action="parse", oldid=revision_id, prop="revid|text", format="json",
            formatversion=2, disablelimitreport=1,
        ))
        request = Request(
            f"{WIKISOURCE_API}?{parameters}",
            headers={"User-Agent": "ShunkouResearchPilot/0.1 (classical Chinese corpus research; 9 pinned revisions)"},
        )
        with urlopen(request, timeout=25) as response:
            raw = response.read()
    parsed = json.loads(raw).get("parse", {})
    if parsed.get("revid") != revision_id or not isinstance(parsed.get("text"), str):
        raise ValueError(f"{source['source_id']}: expected revision {revision_id} and parsed HTML")
    parser = WikiText()
    parser.feed(parsed["text"])
    parser.close()
    if not path.exists():
        atomic_write(path, raw)
    return parser.text()


def apply_edit(text, passage):
    edit = passage.get("edit")
    if edit is None:
        return text
    if text.count(edit["from"]) != 1:
        raise ValueError(f"{passage['passage_id']}: contextual replacement must match exactly once")
    return text.replace(edit["from"], edit["to"], 1)


def matches_witness(text, passage):
    return (
        len(text) == passage["witness_codepoints"]
        and text.startswith(passage["start_anchor"])
        and text.endswith(passage["end_anchor"])
    )


def verify(text, passage):
    if not matches_witness(text, passage):
        raise ValueError(f"{passage['passage_id']}: source span disagrees with anchors or length")
    text = apply_edit(text, passage)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != passage["text_sha256"]:
        raise ValueError(f"{passage['passage_id']}: source text differs from the reviewed SHA-256")
    han_count = sum(unicodedata.name(ch, "").startswith("CJK UNIFIED IDEOGRAPH") for ch in text)
    if han_count != passage["han_count"]:
        raise ValueError(f"{passage['passage_id']}: incorrect Han character count")
    return text


def excerpt(page, passage):
    starts = re.finditer(re.escape(passage["start_anchor"]), page)
    candidates = [
        page[start.start(): start.start() + passage["witness_codepoints"]]
        for start in starts
    ]
    matches = [candidate for candidate in candidates if matches_witness(candidate, passage)]
    if len(matches) != 1:
        raise ValueError(f"{passage['passage_id']}: expected one matching source span, found {len(matches)}")
    return verify(matches[0], passage)


def build(root, snapshot_path):
    destination = root / "data" / "pilot"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["schema_version"] != 1:
        raise ValueError(f"Unsupported schema version {manifest['schema_version']}")
    sources = {source["source_id"]: source for source in manifest["sources"]}
    pages = {}
    snapshot = None
    if snapshot_path:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if set(snapshot) != {row["passage_id"] for row in manifest["passages"]}:
            raise ValueError("Reviewed snapshot must include precisely the manifest passage IDs")
    rows = []
    for passage in manifest["passages"]:
        source = sources[passage["source_id"]]
        if snapshot is None:
            if source["source_id"] not in pages:
                pages[source["source_id"]] = parsed_revision(source, destination / "raw")
            text = excerpt(pages[source["source_id"]], passage)
        else:
            text = verify(normalized_text(snapshot[passage["passage_id"]]), passage)
        rows.append({**source, **passage, "text": text})
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path = destination / "passages.jsonl"
    atomic_write(path, payload.encode("utf-8"))
    mode = "reviewed snapshot" if snapshot is not None else "pinned Wikisource revisions"
    print(f"{len(rows)} passages from {mode} -> {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Project scratch root on Gilbreth")
    parser.add_argument("--snapshot", type=Path, help="Offline JSON witness spans checked against the pinned manifest")
    args = parser.parse_args()
    build(args.root, args.snapshot)


if __name__ == "__main__":
    main()
