"""Generate project-local Qwen character identity drafts for released recordings."""

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path

from src.quantitative_native_pause_eval import read_wav
from src.quantitative_preboundary_features import HAN


MODEL_REVISION = 'c7cbfc2048c462b0d63a45797104fc9db3ad62b7'


def intervals(text, items, max_time):
    if ''.join(item.text for item in items) != text or len(items) != len(text):
        return [None] * len(text), 'transcript_mismatch'
    result = []
    previous_end = 0.0
    for item in items:
        start, end = item.start_time, item.end_time
        if not (math.isfinite(start) and math.isfinite(end)
                and previous_end <= start <= end <= max_time + 0.08):
            return [None] * len(text), 'nonmonotone_or_out_of_bounds'
        result.append([start, end] if start < end <= max_time else None)
        previous_end = end
    return result, 'ok'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project', 'manifest', 'model', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):
        parser.error('Run Qwen in a Gilbreth Slurm GPU allocation')
    project = args.project.resolve(strict=True)
    manifest = args.manifest.resolve(strict=True)
    model = args.model.resolve(strict=True)
    if (not all(path.is_relative_to(project) for path in (manifest, model, args.output.resolve()))
            or model.name != MODEL_REVISION):
        parser.error('Use the pinned project-local model and project-local corpus and output')

    import numpy as np
    import torch
    from qwen_asr import Qwen3ForcedAligner
    from scipy.signal import resample_poly

    if not torch.cuda.is_available():
        raise RuntimeError('An allocated GPU is required')
    aligner = Qwen3ForcedAligner.from_pretrained(
        str(model), dtype=torch.bfloat16, device_map='cuda:0',
        attn_implementation='sdpa', local_files_only=True,
    )
    raw = manifest.read_bytes()
    recordings = {}
    for record in json.loads(raw)['recordings']:
        rid = record['recording_id']
        path = (manifest.parent / record['path']).resolve(strict=True)
        text = ''.join(HAN.findall(record['transcript']))
        if not path.is_relative_to(manifest.parent) or rid in recordings or not text:
            raise ValueError(f'{rid}: corpus or transcript integrity check failed')
        rate, samples, digest = read_wav(path, downmix=True)
        if (digest != record['wav_sha256'] or len(samples) != record.get('sample_count', len(samples))
                or rate != record['sample_rate'] or abs(record.get('duration_s', len(samples) / rate)
                                                         - len(samples) / rate) > 0.5 / rate):
            raise ValueError(f'{rid}: WAV differs from its pinned manifest')
        audio = np.asarray(samples, dtype=np.float32) / 32768
        if rate != 16000:
            divisor = math.gcd(rate, 16000)
            audio = resample_poly(audio, 16000 // divisor, rate // divisor)
        result, = aligner.align(audio=(audio, 16000), text=text, language='Chinese')
        times, status = intervals(text, result.items, len(samples) / rate)
        recordings[rid] = {'characters': text, 'status': status, 'intervals_s': times}
        print(rid, status, sum(interval is not None for interval in times), '/', len(text), flush=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump({'manifest_sha256': sha256(raw).hexdigest(), 'qwen_model_revision': MODEL_REVISION,
                   'timestamp_grid_ms': 80, 'recordings': recordings}, handle, ensure_ascii=False, allow_nan=False)
        handle.write('\n')


if __name__ == '__main__':
    main()
