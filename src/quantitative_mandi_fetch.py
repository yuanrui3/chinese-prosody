"""Pin six ManDi Standard Mandarin prose recordings in a Gilbreth directory."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode
from urllib.request import urlopen


PROJECT_URL = "https://osf.io/fgv4w/"
API_URL = "https://api.osf.io/v2/nodes/fgv4w/files/osfstorage/"
LICENSE_URL = "https://osf.io/download/2k9dp/"
LICENSE = "CC BY-NC 3.0"
FOLDERS = {
    "wav": "61e1eee8c99ebd0387018081",
    "input": "61e1eec0bc925b031bd4c1c9",
    "output": "61e1eed295a0300336ed42be",
}
STRATA = (("BEI", "M"), ("CHD", "F"), ("JNN", "M"), ("TYN", "F"), ("WHN", "M"), ("XIA", "F"))
NAME = re.compile(r"([A-Z]{3})_(\d+)_(F|M)_CMN_NWS\.(wav|textgrid)", re.IGNORECASE)


def list_files(url: str):
    """Yield OSF file records, following folder children and pagination."""
    while url:
        with urlopen(url, timeout=60) as response:
            page = json.load(response)
        for record in page["data"]:
            if record["attributes"]["kind"] == "folder":
                related = record["relationships"]["files"]["links"]["related"]
                yield from list_files(related["href"])
            else:
                yield record
        url = page["links"].get("next")


def index_recordings(kind: str) -> dict:
    expected_suffix = "wav" if kind == "wav" else "textgrid"
    params = urlencode({"page[size]": 100})
    url = f"{API_URL}{FOLDERS[kind]}/?{params}"
    records = {}
    for record in list_files(url):
        filename = record["attributes"]["name"]
        match = NAME.fullmatch(filename)
        if match is None or match[4].lower() != expected_suffix:
            continue
        key = (match[1].upper(), int(match[2]), match[3].upper())
        if key in records:
            raise ValueError(f"Multiple ManDi {kind} files for {key}")
        records[key] = record
    return records


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def verify(path: Path, expected_sha256: str | None, expected_size: int | None) -> str:
    if expected_size is not None and path.stat().st_size != expected_size:
        raise ValueError(f"OSF file size mismatch for {path}")
    checksum = sha256(path)
    if expected_sha256 and checksum != expected_sha256.lower():
        raise ValueError(f"OSF SHA-256 mismatch for {path}")
    return checksum


def preserve_file(staged: Path, destination: Path, checksum: str) -> None:
    """Publish a complete file atomically, including when a run is concurrent."""
    try:
        os.link(staged, destination)
    except FileExistsError:
        if sha256(destination) != checksum:
            raise ValueError(f"Existing file differs from release: {destination}") from None


def download(url: str, destination: Path, expected_sha256=None, expected_size=None) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if expected_sha256 and destination.is_file():
        return verify(destination, expected_sha256, expected_size)

    with NamedTemporaryFile(dir=destination.parent) as staged:
        with urlopen(url, timeout=90) as response:
            shutil.copyfileobj(response, staged)
        staged.flush()
        path = Path(staged.name)
        checksum = verify(path, expected_sha256, expected_size)
        preserve_file(path, destination, checksum)
    return checksum


def fetch_file(record: dict, base: Path, kind: str) -> dict:
    attributes = record["attributes"]
    path = Path(kind) / attributes["name"]
    destination = base / path
    url = record["links"]["download"]
    hashes = (attributes.get("extra") or {}).get("hashes") or {}
    checksum = download(url, destination, hashes.get("sha256"), attributes.get("size"))
    return {
        "path": path.as_posix(),
        "source_path": attributes.get("materialized_path"),
        "osf_file_id": record["id"],
        "osf_version": attributes.get("current_version"),
        "osf_modified": attributes.get("date_modified"),
        "download_url": url,
        "bytes": destination.stat().st_size,
        "sha256": checksum,
    }


def fetch(base: Path) -> dict:
    with ThreadPoolExecutor(max_workers=len(FOLDERS)) as pool:
        sources = dict(zip(FOLDERS, pool.map(index_recordings, FOLDERS)))
    eligible = set.intersection(*(set(index) for index in sources.values()))
    selected = []
    missing = []
    for dialect, gender in STRATA:
        matches = sorted(key for key in eligible if key[0] == dialect and key[2] == gender)
        if matches:
            selected.append(matches[0])
        else:
            missing.append({"dialect": dialect, "gender_code": gender})
    if not selected:
        raise ValueError("No ManDi NWS recordings have the original WAV and both archived TextGrids")

    recordings = []
    for key in selected:
        dialect, _, gender = key
        files = {
            kind: fetch_file(index[key], base, kind)
            for kind, index in sources.items()
            if key in index
        }
        recording_id = Path(files["wav"]["path"]).stem
        recordings.append({
            "recording_id": recording_id,
            "speaker_id": recording_id.rsplit("_", 2)[0],
            "background_dialect": dialect,
            "gender_code": gender,
            "performed_variety": "CMN",
            "recording_style": "At-home smartphone read-aloud of the continuous passage",
            "work_id": "NWS",
            "text_edition": "Zhao dissertation, Appendix d, print p. 170 (ManDi Mandarin rendering)",
            "recording_license": LICENSE,
            "wav": files["wav"]["path"],
            "input_textgrid": files["input"]["path"],
            "output_textgrid": files.get("output", {}).get("path"),
            "source_files": files,
        })

    license_path = Path("OSF_LICENSE")
    license_checksum = download(LICENSE_URL, base / license_path)
    return {
        "corpus": "ManDi",
        "source": PROJECT_URL,
        "citation": "https://aclanthology.org/2022.lrec-1.213/",
        "license": {"label": LICENSE, "source": LICENSE_URL, "path": str(license_path), "sha256": license_checksum},
        "selection": {
            "rule": "Lowest speaker number in each listed dialect and gender stratum with WAV and both TextGrids",
            "strata": [{"dialect": dialect, "gender_code": gender} for dialect, gender in STRATA],
            "missing_strata": missing,
        },
        "recordings": recordings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = fetch(args.output)
    with NamedTemporaryFile(dir=args.output) as staged:
        staged.write((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
        staged.flush()
        path = Path(staged.name)
        preserve_file(path, args.output / "mandi_manifest.json", sha256(path))
    print(f"Pinned {len(manifest['recordings'])} ManDi recordings in {args.output}")


if __name__ == "__main__":
    main()
