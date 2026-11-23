"""Import a shared THCHS-30 test prompt for detector-blind waveform review."""

import argparse
from collections import defaultdict
from hashlib import sha256 as hash_bytes
from io import BytesIO
import json
from math import isfinite
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import wave

from src.quantitative_mandi_fetch import preserve_file, sha256


RELEASE = 'https://www.openslr.org/18/'
CITATION = 'https://arxiv.org/abs/1512.01882'
REVISION = 'c8b881592bd339e9cf0483e9d686c832d4e60361'
ARCHIVE = f'https://huggingface.co/datasets/changelinglab/thchs30-segment/resolve/{REVISION}/data'
SHARDS = {
    'test-00000-of-00002.parquet': 'e457baa861d270c3b461c67b6ef3ef8b0ac5cc1cda208ffdf6dbeeef597d3ade',
    'test-00001-of-00002.parquet': '9f5b824a3a79d7dc0be0cbcece7c5b8f9130465afd9dbae6aaef97e4c6014391',
}
AUTHOR = 'News-source author unspecified in release metadata'
EDITION = 'THCHS-30 release, original D-group test prompt transcript as stored in the pinned archive'
RIGHTS = 'Apache-2.0 corpus release, including the packaged recordings and transcripts'
HAN = re.compile(r'[\u3400-\u9fff]')
UTTERANCE = re.compile(r'(D[0-9]+)_([0-9]+)')
BREAK = re.compile(r'[，；：。！？、,;:.!?]')
METADATA = ('utt_id', 'speaker_id', 'text', 'duration', 'split')
SPEAKER_COUNT = 3
DURATION_BOUNDS = (4.0, 18.0)
CHARACTER_BOUNDS = (25, 50)


def select(metadata):
    """Choose the earliest eligible prompt, preferring explicit internal punctuation."""
    groups = defaultdict(dict)
    seen = set()
    for row in metadata:
        utterance = UTTERANCE.fullmatch(row['utt_id'])
        if row['split'] != 'test' or not utterance or utterance[1] != row['speaker_id']:
            raise ValueError(f"Unexpected THCHS-30 D-group test metadata: {row['utt_id']}")
        if row['utt_id'] in seen:
            raise ValueError(f"Repeated corpus utterance ID: {row['utt_id']}")
        seen.add(row['utt_id'])
        duration = row['duration']
        if not isfinite(duration) or not DURATION_BOUNDS[0] <= duration <= DURATION_BOUNDS[1]:
            continue
        text = row['text']
        if CHARACTER_BOUNDS[0] <= len(HAN.findall(text)) <= CHARACTER_BOUNDS[1]:
            speaker, prompt = utterance.groups()
            groups[int(prompt), text][speaker] = row

    eligible = []
    for (prompt, text), speakers in groups.items():
        if len(speakers) >= SPEAKER_COUNT:
            punctuated = sum(len(HAN.findall(span)) >= 4 for span in BREAK.split(text)) >= 2
            eligible.append((not punctuated, prompt, text, speakers))
    if not eligible:
        raise ValueError('No 25–50 Han D-group prompt has at least three 4–18 s readings of the exact transcript')
    plain, prompt, text, speakers = min(eligible, key=lambda candidate: candidate[:3])
    return prompt, text, not plain, [speakers[speaker] for speaker in sorted(speakers)[:SPEAKER_COUNT]]


def inspect_wav(data, utterance, metadata_duration):
    with wave.open(BytesIO(data), 'rb') as handle:
        rate = handle.getframerate()
        if (handle.getnchannels(), handle.getsampwidth(), handle.getcomptype(), rate) != (1, 2, 'NONE', 16000):
            raise ValueError(f'{utterance}: expected mono 16 kHz 16-bit PCM WAV')
        frames = handle.getnframes()
        if len(handle.readframes(frames)) != frames * 2:
            raise ValueError(f'{utterance}: truncated WAV')
    duration = frames / rate
    if abs(duration - metadata_duration) > 0.02:
        raise ValueError(f'{utterance}: archive and WAV durations disagree')
    return duration


def write_immutable(data, output):
    digest = hash_bytes(data).hexdigest()
    with NamedTemporaryFile(dir=output.parent) as staged:
        staged.write(data)
        staged.flush()
        preserve_file(Path(staged.name), output, digest)
    return digest


def metadata_rows(shards):
    for name, shard in shards.items():
        for group in range(shard.num_row_groups):
            table = shard.read_row_group(group, columns=list(METADATA))
            for index, row in enumerate(table.to_pylist()):
                yield {**row, 'shard': name, 'group': group, 'index': index}


def prepare(shards, output):
    prompt, text, punctuated, selected = select(metadata_rows(shards))
    work = f'THCHS30-D-{prompt}'
    recordings = []
    for row in selected:
        utterance = row['utt_id']
        shard = shards[row['shard']]
        audio = shard.read_row_group(row['group'], columns=['audio'])['audio'][row['index']].as_py()
        data = audio['bytes']
        if not data:
            raise ValueError(f'{utterance}: the pinned parquet row lacks embedded WAV bytes')
        duration = inspect_wav(data, utterance, row['duration'])
        path = Path('wav') / f'{utterance}.wav'
        recordings.append({
            'id': f'THCHS30-{utterance}', 'speaker': row['speaker_id'], 'work': work, 'path': path.as_posix(),
            'visual_start_s': 0.0, 'visual_end_s': duration, 'author': AUTHOR, 'edition': EDITION, 'rights': RIGHTS,
            'wav_sha256': write_immutable(data, output / path), 'source_utterance_id': utterance,
            'source_parquet': f"{ARCHIVE}/{row['shard']}", 'performed_variety': 'Standard Mandarin',
            'recording_style': 'Quiet-office read speech',
        })
    return {
        'provenance': 'Original embedded THCHS-30 WAV bytes and release transcript. Detector-blind visual windows '
                      'cover the entire file. Mark the speech-only scoring bounds separately during human review.',
        'source': RELEASE, 'citation': CITATION, 'archive_revision': REVISION, 'archive_sha256': SHARDS,
        'selection': {
            'rule': 'Exact shared transcript at the same numeric D-prompt suffix, prefer internal punctuation, '
                    'then lowest numeric suffix, transcript order as a tie-break, and first three speaker codes.',
            'duration_bounds_s': DURATION_BOUNDS, 'han_count_bounds': CHARACTER_BOUNDS,
            'internal_punctuation': punctuated, 'han_count': len(HAN.findall(text)),
            'transcript': text, 'prompt_suffix': prompt,
        },
        'recordings': recordings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-dir', type=Path, required=True,
                        help='Gilbreth directory containing both named test shards from the pinned release')
    parser.add_argument('--output', type=Path, required=True,
                        help='Gilbreth directory for preserved WAVs and references.json for the blind renderer')
    args = parser.parse_args()
    from pyarrow.parquet import ParquetFile

    shards = {}
    for name, expected in SHARDS.items():
        path = args.archive_dir / name
        if sha256(path) != expected:
            raise ValueError(f'Pinned THCHS-30 shard hash mismatch: {path}')
        shards[name] = ParquetFile(path)
    (args.output / 'wav').mkdir(parents=True, exist_ok=True)
    result = prepare(shards, args.output)
    data = (json.dumps(result, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    write_immutable(data, args.output / 'references.json')
    print(json.dumps(result['selection'], ensure_ascii=False))
    print('Selected ' + ', '.join(row['id'] for row in result['recordings']))


if __name__ == '__main__':
    main()
