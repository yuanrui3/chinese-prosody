"""Estimate full-passage Mandarin timestamps for the fixed two-voice corpus."""

import argparse
from hashlib import sha256
from importlib.metadata import version
import json
from math import isclose, isfinite
import os
from pathlib import Path

from audio.synthesize import REVISION as SYNTHESIS_REVISION, SAMPLE_RATE
from src.pilot_validation import write_json
from src.quantitative_report import FILES, VOICES, check_inventory, index
from src.recitation_second_aligner import (
    FRAME_MS, MODEL, REVISION, WEIGHTS_SHA256, MandarinTimestampPredictor, map_intervals,
)
from src.stage6_listening import digest, read_clip, read_json, read_rows


CODE = Path(__file__).resolve().parents[1]
RESULTS = Path('results/quantitative-report')
OUTPUT = RESULTS / 'secondary-alignment.json'


def pinned_passages(root, paths):
    hashes = {name: digest(path) for name, path in paths.items()}
    original = read_json(root / RESULTS / 'report.json')['source_sha256']
    if any(original[name] != checksum for name, checksum in hashes.items()):
        raise ValueError('The annotated passages or synthesis manifest changed since the original report')
    pins = read_json(CODE / 'data/pilot/voice-report.json')
    sources = index(pins['sources'], lambda row: row['source_id'])
    specifications = index(pins['passages'], lambda row: row['passage_id'])
    readings = read_json(CODE / 'audio/voice_report_readings.json')
    passages = index(read_rows(paths['passages']), lambda row: row['passage_id'])
    if len(passages) != 8 or passages.keys() != specifications.keys() or passages.keys() != readings.keys():
        raise ValueError('Expected the eight pinned quantitative-report passages and readings')
    check_inventory(passages)
    for pid, passage in passages.items():
        specification = specifications[pid]
        source = sources[specification['source_id']]
        provenance = ('source_id', 'pair_id', 'period', 'genre', 'text_sha256', 'han_count')
        witness = ('work_id', 'revision_id', 'source_url', 'license')
        if (any(passage[key] != specification[key] for key in provenance)
                or any(passage[key] != source[key] for key in witness)
                or readings[pid]['text_sha256'] != passage['text_sha256']):
            raise ValueError(f'{pid}: the text or reading differs from its pinned witness')
    return passages, readings, hashes


def verify_takes(root, path, passages, readings):
    takes = index(read_rows(path), lambda row: (row['passage_id'], row['speaker']))
    if (takes.keys() != {(pid, voice) for pid in passages for voice in VOICES}
            or len({take['audio_sha256'] for take in takes.values()}) != len(takes)):
        raise ValueError('Expected a distinct, checksum-bound recording per passage and voice')
    for pid, passage in passages.items():
        reference, alternate = (takes[pid, voice] for voice in VOICES)
        recipe = [clause.replace('/', ' ').split() for clause in readings[pid]['clauses']]
        pinyin = [syllable for clause in recipe for syllable in clause]
        clausal_slots = [number for number, clause in enumerate(recipe) for _ in clause]
        if (clausal_slots != [slot['clause_index'] for slot in passage['slots']]
                or reference['intended_model_phonemes'] != alternate['intended_model_phonemes']
                or not reference['intended_model_phonemes']):
            raise ValueError(f'{pid}: the voice comparison changed the intended phoneme input')
        seed_id = f'kokoro-{pid}-{VOICES[0]}-0p9'
        seed = int(sha256(seed_id.encode()).hexdigest()[:8], 16)
        for voice, take in zip(VOICES, (reference, alternate)):
            recording_id = f'kokoro-{pid}-{voice}-0p9'
            expected_audio = Path('audio/raw/synthetic') / f'{recording_id}.wav'
            if (take['recording_id'] != recording_id or Path(take['audio_path']) != expected_audio
                    or take['text_sha256'] != passage['text_sha256']
                    or take['text_revision'] != passage['revision_id']
                    or take['text_source_url'] != passage['source_url']
                    or take['text_license'] != passage['license']
                    or take['model_revision'] != SYNTHESIS_REVISION or take['model_license'] != 'Apache-2.0'
                    or take['intended_pinyin'] != pinyin or take['pronunciation_status'] != 'input_only'
                    or take['seed'] != seed
                    or (take['kind'], take['variety'], take['style'], take['speed'], take['sample_rate'])
                    != ('synthetic', 'cmn', 'controlled_read_speech', 0.9, SAMPLE_RATE)
                    or (root / expected_audio).stat().st_mode & 0o077):
                raise ValueError(f'{recording_id}: unexpected recording lineage or permissions')
    return takes


def predict_take(model, root, take, passage):
    rate, pcm = read_clip(root, take, SAMPLE_RATE)
    if not pcm or not isclose(take['duration_s'], len(pcm) / rate, abs_tol=1e-6, rel_tol=0):
        raise ValueError(f"{take['recording_id']}: unexpected PCM duration")
    characters = ''.join(slot['char'] for slot in passage['slots'])
    try:
        intervals = model.timestamps(pcm, rate, characters)
    except AssertionError:
        # Timestamp decoding can reject a take if the estimated peaks do not match its count.
        rows, status = [], 'timestamp_prediction_rejected'
    else:
        if all(isfinite(point) for interval in intervals for point in interval):
            rows, status = map_intervals(intervals, characters, 1000 * len(pcm) / rate)
        else:
            rows, status = [], 'nonfinite_timestamp'
    return {**{key: take[key] for key in ('recording_id', 'passage_id', 'audio_sha256', 'text_sha256')},
            'sample_count': len(pcm), 'status': status, 'slots': rows}


def align(project, root, cache):
    if not root.is_relative_to(project) or not cache.is_relative_to(project):
        raise ValueError('Keep the recordings, model cache and alignments in the Gilbreth project')
    paths = {name: (root / FILES[name]).resolve(strict=True) for name in ('passages', 'takes')}
    destination = root / OUTPUT
    if (any(not path.is_relative_to(root) for path in paths.values())
            or not (root / RESULTS / 'report.json').resolve(strict=True).is_relative_to(root)
            or not destination.parent.resolve().is_relative_to(root)):
        raise ValueError('The original report inputs and new alignment must stay within the experiment')
    passages, readings, hashes = pinned_passages(root, paths)
    takes = verify_takes(root, paths['takes'], passages, readings)
    model = MandarinTimestampPredictor(cache)
    results = [predict_take(model, root, take, passages[pid]) for (pid, _), take in takes.items()]
    if hashes != {name: digest(path) for name, path in paths.items()}:
        raise ValueError('The input manifests changed during alignment')
    write_json(destination, {'manifest_sha256': hashes['takes'], 'passages_sha256': hashes['passages'],
               'model': {'name': MODEL, 'revision': REVISION, 'weights_sha256': WEIGHTS_SHA256,
                         'funasr_version': version('funasr'), 'conditioning': 'ordered Han count'},
               'frame_ms': FRAME_MS, 'takes': results})
    return {'takes': len(results), 'aligned_takes': sum(take['status'] == 'aligned' for take in results)}


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
