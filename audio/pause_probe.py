"""Place a controlled pause extension at an acoustically quiet pilot boundary."""

import argparse
from array import array
import hashlib
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import wave

from align import read_rows, write_rows


TARGETS = {'NS03': '皆足以垂于不朽', 'SD01': '人間何世', 'SD04': '遂矯詔斬之',
           'ET01': '潦水盡而寒潭清'}
INSERT_MS = 120
MIN_GAP_MS = 100
EDGE_GUARD_MS = 15


def target_slots(passages):
    for passage in passages:
        identifier = passage['passage_id']
        if identifier not in TARGETS:
            continue
        anchor = TARGETS[identifier]
        if passage['text'].count(anchor) != 1:
            raise ValueError(f'{identifier}: pause anchor must occur exactly once')
        offset = passage['text'].index(anchor) + len(anchor) - 1
        slot = next(slot for slot in passage['slots'] if slot['offset'] == offset)
        if not slot['boundary_after']:
            raise ValueError(f'{identifier}: pause anchor is not at a documented boundary')
        yield identifier, slot['slot_index']


def extend_gap(root, recording, gap):
    source = root / recording['audio_path']
    with wave.open(str(source), 'rb') as stream:
        params = stream.getparams()
        if params.nchannels != 1 or params.sampwidth != 2 or params.comptype != 'NONE':
            raise ValueError(f'{source}: expected mono PCM-16')
        pcm = stream.readframes(params.nframes)
    samples = array('h')
    samples.frombytes(pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    guard = params.framerate * EDGE_GUARD_MS / 1000
    first = max(1, math.ceil(gap['start_s'] * params.framerate + guard))
    stop = min(len(samples), math.floor(gap['end_s'] * params.framerate - guard))
    if first >= stop:
        return None
    midpoint = (first + stop) / 2

    def edge(frame):
        return max(abs(samples[frame - 1]), abs(samples[frame]))

    frame = min(range(first, stop), key=lambda index: (edge(index), abs(index - midpoint)))
    if edge(frame) > 0.002 * max(map(abs, samples)):
        return None
    frames = round(params.framerate * INSERT_MS / 1000)
    splice = frame * params.sampwidth
    added = b'\0' * (frames * params.sampwidth)
    folder = root / 'audio/derived/listening/pause'
    folder.mkdir(parents=True, exist_ok=True)
    variant_id = f"{recording['recording_id']}-pause{INSERT_MS}ms"
    path = folder / f'{variant_id}.wav'
    with TemporaryDirectory(dir=folder) as temporary:
        staged = Path(temporary) / path.name
        with wave.open(str(staged), 'wb') as stream:
            stream.setparams(params)
            stream.writeframes(pcm[:splice] + added + pcm[splice:])
        with wave.open(str(staged), 'rb') as stream:
            variant_pcm = stream.readframes(stream.getnframes())
        if variant_pcm[:splice] + variant_pcm[splice + len(added):] != pcm:
            raise ValueError(f'{variant_id}: sample-preservation check failed')
        digest = hashlib.sha256(staged.read_bytes()).hexdigest()
        staged.replace(path)
    return {'comparison_id': variant_id, 'comparison': 'synthetic_pause_extension',
            'passage_id': recording['passage_id'], 'speaker_preset': recording['speaker'],
            'speed': recording['speed'], 'listening_review': 'pending',
            'members': [{key: recording[key] for key in ('recording_id', 'audio_path', 'audio_sha256')},
                        {'recording_id': variant_id, 'audio_path': str(path.relative_to(root)),
                         'audio_sha256': digest}],
            'edit': {'after_slot_index': gap['after_slot_index'], 'source_anchor': TARGETS[recording['passage_id']],
                     'source_gap_ms': gap['gap_ms'], 'added_ms': 1000 * frames / params.framerate,
                     'sample_offset': frame, 'inserted_samples': frames, 'method': 'insert_zero_samples'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    root = parser.parse_args().root.resolve(strict=True)
    targets = dict(target_slots(read_rows(root / 'data/pilot/annotated.jsonl')))
    recordings = {row['recording_id']: row for row in read_rows(root / 'audio/manifests/synthetic.jsonl')}
    probes = []
    for gap in read_rows(root / 'audio/derived/features/gaps.jsonl'):
        identifier = gap['passage_id']
        if identifier not in targets or gap['after_slot_index'] != targets[identifier]:
            continue
        if MIN_GAP_MS not in gap['quiet_candidate_ms_thresholds']:
            continue
        probe = extend_gap(root, recordings[gap['recording_id']], gap)
        if probe:
            probes.append(probe)
    write_rows(root / 'audio/manifests/pause-probes.jsonl', probes)
    print(f'{len(probes)} verified pause edits at: {sorted({row["passage_id"] for row in probes})}')


if __name__ == '__main__':
    main()
