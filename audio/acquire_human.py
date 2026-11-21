"""Acquire rights-verified human reference tracks on Gilbreth."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen


REGISTRY = Path(__file__).with_name("human_reference_sources.json")


def inspect_mp3(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as audio:
        header = audio.read(10)
        has_frame_sync = len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
        if len(header) < 10 or not (header.startswith(b"ID3") or has_frame_sync):
            raise ValueError(f"{path.name}: response does not contain an MP3 header")
        audio.seek(0)
        for block in iter(lambda: audio.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest()


def acquire(row, root):
    raw = (root / "audio" / "raw" / "human").resolve()
    destination = (root / row["audio_path"]).resolve()
    destination.relative_to(raw)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not destination.exists():
        request = Request(row["audio_url"], headers={"User-Agent": "shunkou-stage4/1.0 (research audio)"})
        with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
            staged = Path(folder) / destination.name
            with urlopen(request, timeout=60) as response, staged.open("wb") as output:
                length = response.headers.get("Content-Length")
                shutil.copyfileobj(response, output)
            size, sha256 = inspect_mp3(staged)
            if length is not None and size != int(length):
                raise ValueError(f"{destination.name}: incomplete download ({size} of {length} bytes)")
            staged.replace(destination)
    else:
        size, sha256 = inspect_mp3(destination)

    return {**row, "size_bytes": size, "sha256": sha256}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Gilbreth project root")
    args = parser.parse_args()
    try:
        rows = json.loads(REGISTRY.read_text(encoding="utf-8"))
        records = [acquire(row, args.root) for row in rows]
        manifest = args.root / "audio" / "manifests" / "human-reference.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=manifest.parent) as folder:
            staged = Path(folder) / manifest.name
            with staged.open("w", encoding="utf-8") as output:
                for record in records:
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
            staged.replace(manifest)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Human reference acquisition failed: {error}\n")
    print(f"Recorded {len(records)} human reference track(s) in {manifest}")


if __name__ == "__main__":
    main()
