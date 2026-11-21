#!/usr/bin/env python3
"""Acquire and normalize pinned classical verse collections in project scratch."""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unicodedata
from urllib.request import Request, urlopen


REVISION = "b8594f81a89752241442f2ce267d6f66f96704ee"
REPOSITORY = "https://github.com/chinese-poetry/chinese-poetry"
ARCHIVE = "https://codeload.github.com/chinese-poetry/chinese-poetry/tar.gz/" + REVISION
ARCHIVE_PREFIX = "chinese-poetry-" + REVISION + "/"


COLLECTIONS = {
    "quan-tang-shi": ("shi", "Tang and Five Dynasties", [
        f"全唐诗/poet.tang.{offset}.json" for offset in range(0, 58000, 1000)
    ]),
    "tang-shi-300": ("shi", "Tang and Five Dynasties", ["全唐诗/唐诗三百首.json"]),
    "quan-song-ci": ("ci", "Song", [
        f"宋词/ci.song.{offset}.json" for offset in range(0, 22000, 1000)
    ]),
    "song-ci-300": ("ci", "Song", ["宋词/宋词三百首.json"]),
    "yuan-qu": ("qu", "Yuan corpus label", ["元曲/yuanqu.json"]),
}

FORM_TAGS = {
    "五言古诗": "古體", "七言古诗": "古體", "五言古詩": "古體", "七言古詩": "古體",
    "五言律诗": "近體", "七言律诗": "近體", "五言律詩": "近體", "七言律詩": "近體",
}


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def copy_atomic(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            shutil.copyfileobj(source, output)
            output.close()
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def stage_members(stream, wanted, raw):
    missing = {path for path in wanted if not (raw / path).is_file()}
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            if not member.name.startswith(ARCHIVE_PREFIX):
                continue
            path = member.name[len(ARCHIVE_PREFIX):]
            if member.isfile() and path in missing:
                with archive.extractfile(member) as content:
                    copy_atomic(content, raw / path)
                missing.remove(path)
                if not missing:
                    return
    if missing:
        raise ValueError(f"Pinned archive is missing required members: {sorted(missing)}")


def metadata_text(value):
    if isinstance(value, str) and value.strip():
        return unicodedata.normalize("NFC", value.strip())
    return None


def normalize_entry(entry, collection, path, index):
    genre, period, _ = COLLECTIONS[collection]
    raw_lines = entry.get("paragraphs")
    if not isinstance(raw_lines, list) or any(not isinstance(line, str) for line in raw_lines):
        raise ValueError(f"Invalid paragraphs at {path} record {index}")
    lines = [line for value in raw_lines if (line := metadata_text(value)) is not None]
    if not lines:
        raise ValueError(f"Empty poem or lyric at {path} record {index}")

    tags = entry.get("tags") or []
    if genre == "shi" and isinstance(tags, list):
        forms = {FORM_TAGS[tag] for tag in tags if isinstance(tag, str) and tag in FORM_TAGS}
        verse_form = next(iter(forms)) if len(forms) == 1 else None
    else:
        verse_form = None
    title = metadata_text(entry.get("title"))
    tune = metadata_text(entry.get("rhythmic"))
    path_stem = Path(path).stem
    return {
        "id": f"{collection}:{path_stem}:{index}",
        "corpus": collection,
        "title": title,
        "author": metadata_text(entry.get("author")),
        "genre": genre,
        "period": period,
        "tune": tune,
        "verse_form": verse_form,
        "verse_form_basis": "upstream form tag" if verse_form else None,
        "lines": lines,
        "text_sha256": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
        "source": {
            "repository": REPOSITORY,
            "revision": REVISION,
            "path": path,
            "record_ordinal": index,
            "upstream_id": metadata_text(entry.get("id")),
        },
    }


def records(raw, collection):
    _, _, paths = COLLECTIONS[collection]
    for path in paths:
        with (raw / path).open(encoding="utf-8-sig") as stream:
            entries = json.load(stream)
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"Expected nonempty record sequence at {path}")
        for index, entry in enumerate(entries, 1):
            if not isinstance(entry, dict):
                raise ValueError(f"Expected an object at {path} record {index}")
            yield normalize_entry(entry, collection, path, index)


def write_collection(raw, output, collection):
    destination = output / f"{collection}.jsonl"
    count = 0
    form_counts = {}
    with tempfile.NamedTemporaryFile(mode="w", dir=output, encoding="utf-8", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            for row in records(raw, collection):
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
                if row["verse_form"]:
                    form = row["verse_form"]
                    form_counts[form] = form_counts.get(form, 0) + 1
            stream.close()
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    _, _, paths = COLLECTIONS[collection]
    manifest = {
        "corpus": collection,
        "source_repository": REPOSITORY,
        "source_revision": REVISION,
        "citation": f"{REPOSITORY}/tree/{REVISION}",
        "source_archive": ARCHIVE,
        "rights_notice": f"{REPOSITORY}/blob/{REVISION}/LICENSE",
        "rights_notice_sha256": digest(raw / "LICENSE"),
        "source_sha256": {path: digest(raw / path) for path in paths},
        "records": count,
        "verse_form_counts": form_counts,
        "sha256": digest(destination),
    }
    payload = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    copy_atomic(BytesIO(payload), output / f"{collection}.manifest.json")
    print(f"{collection}: {count} records, {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Gilbreth project scratch root")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--collection", action="append", choices=COLLECTIONS)
    acquisition = parser.add_mutually_exclusive_group()
    acquisition.add_argument("--archive", type=Path, help="use a local copy of the pinned tar.gz")
    acquisition.add_argument("--normalize-only", action="store_true", help="reuse staged members")
    args = parser.parse_args()

    selected = list(COLLECTIONS) if args.all else list(dict.fromkeys(args.collection))
    raw = args.root / "data" / "raw" / "collections" / REVISION
    output = args.root / "data" / "collections"
    wanted = {path for collection in selected for path in COLLECTIONS[collection][2]} | {"LICENSE"}
    missing = sorted(path for path in wanted if not (raw / path).is_file())
    if missing:
        if args.normalize_only:
            parser.error(f"Missing staged members: {missing}")
        if args.archive:
            with args.archive.open("rb") as archive:
                stage_members(archive, wanted, raw)
        else:
            request = Request(ARCHIVE, headers={"User-Agent": "shunkou-research/0.1 (corpus acquisition)"})
            with urlopen(request, timeout=90) as archive:
                stage_members(archive, wanted, raw)
    output.mkdir(parents=True, exist_ok=True)
    for collection in selected:
        write_collection(raw, output, collection)


if __name__ == "__main__":
    main()
