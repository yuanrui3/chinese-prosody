"""Run the FunASR Mandarin timestamp predictor on the verified phrasing WAVs."""

import argparse
from importlib.metadata import version
import json
from math import gcd
import os
from pathlib import Path

from src.pilot_validation import write_json
from src.recitation_phrasing import CORPUS, DESTINATION
from src.recitation_phrasing_decode import ROLES
from src.stage6_listening import digest, read_clip, read_json, read_rows


MODEL = 'funasr/fa-zh'
REVISION = 'd7701644d6e336f093501241beca010519c0986f'
WEIGHTS_SHA256 = 'f34ede558af831fb504206b25f1c2f27ca2f77753c26c4dd38d03323153b6f73'
MODEL_FILES = ['model.pt', 'config.yaml', 'configuration.json', 'tokens.json', 'am.mvn', 'seg_dict']
MODEL_RATE = 16000
FRAME_MS = 20
OUTPUT = DESTINATION.with_name('forced-alignment.json')


class MandarinTimestampPredictor:
    def __init__(self, cache):
        import torch
        from funasr import AutoModel
        from huggingface_hub import snapshot_download

        if not torch.cuda.is_available():
            raise RuntimeError('Use an allocated Gilbreth GPU for FunASR')
        checkpoint = Path(snapshot_download(MODEL, revision=REVISION, cache_dir=cache,
                                            allow_patterns=MODEL_FILES, max_workers=2))
        if digest(checkpoint / 'model.pt') != WEIGHTS_SHA256:
            raise ValueError('FunASR weights differ from their published checksum')
        pipeline = AutoModel(model=str(checkpoint), device='cuda:0', disable_update=True, ncpu=2)
        self.frontend = pipeline.kwargs['frontend']
        self.model = pipeline.model.eval()
        if (type(self.model).__name__ != 'MonotonicAligner' or self.frontend.fs != MODEL_RATE
                or self.frontend.frame_shift * self.frontend.lfr_n != FRAME_MS * 3):
            raise ValueError('Unexpected model or frame rate for the pinned timestamp backend')
        self.torch = torch

    def timestamps(self, pcm, rate, characters):
        import numpy as np
        from funasr.utils.load_utils import extract_fbank
        from funasr.utils.timestamp_tools import ts_prediction_lfr6_standard
        from scipy.signal import resample_poly

        waveform = np.asarray(pcm, dtype=np.float32) / 32768
        if rate != MODEL_RATE:
            divisor = gcd(rate, MODEL_RATE)
            waveform = resample_poly(waveform, MODEL_RATE // divisor, rate // divisor)
        torch = self.torch
        with torch.inference_mode():
            features, lengths = extract_fbank([torch.from_numpy(waveform)], data_type='sound', frontend=self.frontend)
            encoded, encoded_lengths = self.model.encode(features.to('cuda:0'), lengths.to('cuda:0'))
            # The official model conditions its timestamp predictor on the
            # supplied count. Apply the original Han labels after inference.
            count = torch.tensor([len(characters) + 1], device='cuda:0')
            _, _, weights, peaks = self.model.calc_predictor_timestamp(encoded, encoded_lengths, token_num=count)
            frames = int(encoded_lengths[0]) * 3
            _, intervals = ts_prediction_lfr6_standard(weights[0, :frames], peaks[0, :frames], list(characters))
        return intervals


def map_intervals(intervals, characters, duration_ms):
    if len(intervals) != len(characters):
        return [], 'timestamp_count_differs_from_han_count'
    rows = []
    previous = 0
    for index, (char, raw) in enumerate(zip(characters, intervals)):
        start, end = raw
        if (start < -2 * FRAME_MS or end > duration_ms + 2 * FRAME_MS
                or max(0, start) < previous or min(duration_ms, end) <= max(0, start)):
            return [], 'invalid_timestamp_order_or_bounds'
        previous = min(duration_ms, end)
        rows.append({'slot_index': index, 'char': char, 'start_s': max(0, start) / 1000,
                     'end_s': previous / 1000, 'model_timestamp_ms': list(raw)})
    return rows, 'aligned'


def align(project, root, cache):
    if not root.is_relative_to(project) or not cache.is_relative_to(project):
        raise ValueError('Keep the inputs, model and alignments on the Gilbreth project filesystem')
    manifest = root / DESTINATION
    pairs = read_json(manifest)['pairs']
    if not pairs or len({pair['pair_id'] for pair in pairs}) != len(pairs):
        raise ValueError('Expected unique verified phrasing pairs')
    model = MandarinTimestampPredictor(cache)
    witnesses, output = {}, []
    for pair in pairs:
        source = pair['source']
        origin = Path(source['root']).resolve(strict=True)
        if not origin.is_relative_to(project):
            raise ValueError('Pinned text witness must live in the Gilbreth project')
        if origin not in witnesses:
            witnesses[origin] = {row['passage_id']: row for row in read_rows(origin / CORPUS)}
        passage = witnesses[origin][pair['passage_id']]
        slots = passage['slots']
        characters = ''.join(slot['char'] for slot in slots)
        if (passage['text_sha256'] != source['text_sha256'] or passage['revision_id'] != source['text_revision']
                or [slot['slot_index'] for slot in slots] != list(range(len(characters)))
                or ''.join(characters[i] for i in pair['slot_indices']) != pair['clause_text']):
            raise ValueError('The model input is disconnected from the pinned four-character clause')
        takes = [pair['sham'], *(pair['variants'][role] for role in ROLES[1:])]
        if takes[1]['sample_count'] != takes[2]['sample_count']:
            raise ValueError('Both phrasing alternatives must have the same duration')
        records = {}
        for role, take in zip(ROLES, takes):
            fixed = ('sample_rate', 'text_sha256', 'text_revision', 'intended_pinyin', 'speaker', 'speed')
            if any(take[key] != source[key] for key in fixed):
                raise ValueError('One take changed the reference text or voice')
            rate, pcm = read_clip(root, take, source['sample_rate'])
            if len(pcm) != take['sample_count']:
                raise ValueError('One take changed its recorded duration')
            intervals = model.timestamps(pcm, rate, characters)
            rows, status = map_intervals(intervals, characters, 1000 * len(pcm) / rate)
            records[role] = {'status': status, 'audio_sha256': take['audio_sha256'],
                             'sample_count': len(pcm), 'slots': rows,
                             **({'raw_timestamps_ms': intervals} if status != 'aligned' else {})}
        output.append({'pair_id': pair['pair_id'], 'takes': records, 'supplied_han_count': len(characters)})
    write_json(root / OUTPUT, {'stimuli_sha256': digest(manifest), 'frame_ms': FRAME_MS,
               'model': {'name': MODEL, 'revision': REVISION, 'weights_sha256': WEIGHTS_SHA256,
                         'funasr_version': version('funasr'), 'conditioning': 'ordered Han count'}, 'pairs': output})
    return {'pairs': len(output), 'aligned_takes': sum(take['status'] == 'aligned' for row in output
                                                       for take in row['takes'].values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(align(args.project.resolve(strict=True), args.root.resolve(strict=True),
                           args.model_cache.resolve()), allow_nan=False))


if __name__ == '__main__':
    main()
