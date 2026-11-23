"""Prepare the frozen MCGA excerpt set and combine independent pause references."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import wave


MCGA_REVISION = '75908a9464828207c37ce8bb5e2223b190134c7a'
MCGA_WORKS = {
    '1717-9': ('北山移文', '孔稚珪', 'parallel prose', 'https://zh.wikisource.org/wiki/北山移文'),
    '2695-1': ('与朱元思书', '吴均', 'parallel prose', 'https://zh.wikisource.org/w/index.php?oldid=2639101'),
    '1535-1': ('陈情表', '李密', 'memorial with parallel diction', 'https://zh.wikisource.org/wiki/陳情表_(李密)'),
    '3070-7': ('芜城赋', '鲍照', 'parallel rhapsody', 'https://zh.wikisource.org/wiki/蕪城賦'),
}


def write_json(path, payload):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def mcga_rows(archive):
    from pyarrow.parquet import ParquetFile

    columns = ['id', 'title', 'author', 'dynasty', 'gender', 'asr', 'audio']
    for path in sorted(archive.glob('test-*-of-00003.parquet')):
        shard = ParquetFile(path)
        for group in range(shard.num_row_groups):
            ids = shard.read_row_group(group, columns=['id']).column('id').to_pylist()
            wanted = [i for i, key in enumerate(ids) if key in MCGA_WORKS]
            if wanted:
                rows = shard.read_row_group(group, columns=columns).take(wanted).to_pylist()
                yield from ((path.name, row) for row in rows)


def extract_mcga(archive, output):
    rows = list(mcga_rows(archive))
    if sorted(row['id'] for _, row in rows) != sorted(MCGA_WORKS):
        raise ValueError('The four preselected excerpt IDs must occur exactly once')
    paths = output / 'mcga-wav'
    paths.mkdir(parents=True, exist_ok=True)
    result = []
    for shard, row in rows:
        key = row['id']
        title, author, genre, witness = MCGA_WORKS[key]
        if (''.join(row['title'].split()), ''.join(row['author'].split())) != (title, author):
            raise ValueError(f'Unexpected work metadata for {key}')
        original = row['audio']['bytes']
        with wave.open(BytesIO(original), 'rb') as handle:
            if (handle.getnchannels(), handle.getsampwidth()) != (1, 2):
                raise ValueError(f'Expected original mono PCM16 for {key}')
            duration = handle.getnframes() / handle.getframerate()
        file = paths / f'MCGA-{key}.wav'
        with file.open('xb') as handle:
            handle.write(original)
        result.append({'id': file.stem, 'speaker': file.stem, 'speaker_identity_known': False,
                       'gender': row['gender'].strip(), 'work': title, 'author': author,
                       'genre': genre, 'dynasty': row['dynasty'].strip(), 'variety': 'Standard Mandarin',
                       'style': 'prompted classical recitation', 'path': file.relative_to(output).as_posix(),
                       'wav_sha256': sha256(original).hexdigest(), 'source_shard': shard,
                       'source_id': key, 'text': row['asr'], 'edition': 'MCGA recorded clip and transcript',
                       'text_witness': witness, 'license': 'CC BY-NC-SA 4.0', 'duration_s': duration,
                       'visual_start_s': 0.2, 'visual_end_s': min(15.0, duration - 0.2)})
    result.sort(key=lambda row: row['id'])
    return {'corpus': 'MCGA', 'revision': MCGA_REVISION,
            'dataset': 'https://huggingface.co/datasets/yxdu/MCGA', 'recordings': result}


def reference(audio_root, inventories, annotations):
    rows = [row for inventory in inventories for row in inventory['recordings']]
    if len(rows) != len(annotations) or {row['id'] for row in rows} != set(annotations):
        raise ValueError('Each selected recording requires one independent annotation entry')
    clips = []
    for row in rows:
        key = row['id']
        mark = annotations[key]
        start, end = mark.get('score_window_s', [row['visual_start_s'], row['visual_end_s']])
        if not row['visual_start_s'] <= start < end <= row['visual_end_s']:
            raise ValueError(f'The scoring window for {key} is outside its waveform view')
        if sha256((audio_root / row['path']).read_bytes()).hexdigest() != row['wav_sha256']:
            raise ValueError(f'WAV checksum differs from the review inventory for {key}')
        pauses = [{'start_s': a, 'end_s': b} for a, b in mark['pauses']]
        masks = [{'start_s': a, 'end_s': b} for a, b in mark['uncertain']]
        if any(not start <= event['start_s'] < event['end_s'] <= end for event in pauses + masks):
            raise ValueError(f'An annotation for {key} is outside its visual review window')
        clips.append({**row, 'score_start_s': start, 'score_end_s': end, 'pauses': pauses,
                      'excluded_intervals': masks, 'clauses': [], 'visual_notes': mark['notes']})
    return {'provenance': 'Detector-blind AI review of waveforms and spectrograms, fixed source windows',
            'recordings': clips}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='command', required=True)
    prepare = actions.add_parser('mcga')
    prepare.add_argument('--archive', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--inventory', type=Path, required=True)
    score = actions.add_parser('references')
    score.add_argument('--audio-root', type=Path, required=True)
    score.add_argument('--inventory', type=Path, required=True, nargs='+')
    score.add_argument('--annotations', type=Path, required=True)
    score.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'mcga':
        data = extract_mcga(args.archive, args.output)
        write_json(args.inventory, data)
    else:
        inventories = [json.loads(path.read_text(encoding='utf-8')) for path in args.inventory]
        annotations = json.loads(args.annotations.read_text(encoding='utf-8'))
        data = reference(args.audio_root, inventories, annotations)
        write_json(args.output, data)
    print(', '.join(row['id'] for row in data['recordings']))


if __name__ == '__main__':
    main()
