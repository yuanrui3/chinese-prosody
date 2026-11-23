"""Collect waveform and FunASR onsets for the previously archived matched prose."""

import argparse
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path

from audio.synthesize import REVISION as KOKORO_REVISION, SAMPLE_RATE
from src.quantitative_report import FILES, VOICES, check_inventory, index
from src.quantitative_second_alignment import predict_take
from src.quantitative_waveform_reference import WAVEFORM_REFERENCE_SETTINGS, waveform_reference
from src.recitation_second_aligner import MODEL, REVISION, WEIGHTS_SHA256, MandarinTimestampPredictor
from src.stage6_listening import digest, read_clip, read_json, read_rows, write_json


CODE = Path(__file__).resolve().parents[1]
HISTORICAL = Path('model-development/historical-increment')
TRAINING = Path('model-development/quantitative-report/results/quantitative-report/report-v4.json')
EXPECTED_WORKS = 16


def verify_inventory(project, root):
    corpus_path = root / FILES['passages']
    source_path = project / HISTORICAL / FILES['passages']
    if digest(corpus_path) != digest(source_path):
        raise ValueError('Evaluation requires an exact copy of the previously annotated historical-increment cohort')
    passages = index(read_rows(corpus_path), lambda row: row['passage_id'])
    pins = index(read_json(CODE / 'data/pilot/historical-increment.json')['passages'], lambda row: row['passage_id'])
    if len(passages) != EXPECTED_WORKS or passages.keys() != pins.keys():
        raise ValueError('Expected the complete pinned evaluation inventory')
    for pid, expected in pins.items():
        fields = ('genre', 'period', 'pair_id', 'source_id', 'han_count', 'text_sha256')
        if any(passages[pid][field] != expected[field] for field in fields):
            raise ValueError(f'{pid}: archived text or condition is inconsistent with the pinned witness')
    check_inventory(passages)
    return passages


def verify_takes(project, root, passages):
    takes = index(read_rows(root / FILES['takes']), lambda row: (row['passage_id'], row['speaker']))
    archived_manif = project / HISTORICAL / FILES['takes']
    archived = index(read_rows(archived_manif), lambda row: row['passage_id'])
    if (takes.keys() != {(pid, voice) for pid in passages for voice in VOICES}
            or passages.keys() != archived.keys()
            or len({take['audio_sha256'] for take in takes.values()}) != len(takes)):
        raise ValueError('Expected a distinct take of each pinned work per voice')
    readings = read_json(CODE / 'audio/historical_increment_readings.json')
    for pid, passage in passages.items():
        recipe = [clause.replace('/', ' ').split() for clause in readings[pid]['clauses']]
        pinyin = [syllable for clause in recipe for syllable in clause]
        slots = [number for number, clause in enumerate(recipe) for _ in clause]
        if readings[pid]['text_sha256'] != passage['text_sha256'] or slots != [
                item['clause_index'] for item in passage['slots']]:
            raise ValueError(f'{pid}: reading prescription has changed')
        seed_id = f'kokoro-{pid}-{VOICES[0]}-0p9'
        seed = int(sha256(seed_id.encode()).hexdigest()[:8], 16)
        for voice in VOICES:
            take = takes[pid, voice]
            recording_id = f'kokoro-{pid}-{voice}-0p9'
            audio_path = Path('audio/raw/synthetic') / f'{recording_id}.wav'
            if (take['recording_id'] != recording_id or Path(take['audio_path']) != audio_path
                    or take['text_sha256'] != passage['text_sha256'] or take['text_revision'] != passage['revision_id']
                    or take['intended_pinyin'] != pinyin or take['seed'] != seed
                    or not take['intended_model_phonemes'] or take['model_revision'] != KOKORO_REVISION
                    or take['intended_model_phonemes'] != archived[pid]['intended_model_phonemes']
                    or (take['kind'], take['variety'], take['style'], take['speed'], take['sample_rate'])
                    != ('synthetic', 'cmn', 'controlled_read_speech', 0.9, SAMPLE_RATE)
                    or (root / audio_path).stat().st_mode & 0o077):
                raise ValueError(f'{recording_id}: synthesis inputs or permissions differ from the declared conditions')
    return takes, archived


def collect(project, root, cache, training, output):
    if (not root.is_relative_to(project) or not cache.is_relative_to(project)
            or training != project / TRAINING or not output.is_relative_to(root / 'results')):
        raise ValueError('Keep the held-out check and its model in the Gilbreth project')
    sources = {'training': training, 'annotated': root / FILES['passages'], 'takes': root / FILES['takes'],
               'archived_takes': project / HISTORICAL / FILES['takes']}
    hashes = {name: digest(path) for name, path in sources.items()}
    passages = verify_inventory(project, root)
    takes, archived = verify_takes(project, root, passages)
    model = MandarinTimestampPredictor(cache)
    rows = []
    for (pid, voice), take in takes.items():
        passage = passages[pid]
        rate, pcm = read_clip(root, take, SAMPLE_RATE)
        reference = waveform_reference(pcm, rate)
        alignment = predict_take(model, root, take, passage)
        start = alignment['slots'][0]['start_s'] if alignment['slots'] else None
        rows.append({**{key: passage[key] for key in ('work_id', 'author', 'pair_id', 'passage_id', 'genre', 'period',
                                                      'source_url', 'text_sha256')},
                     'voice': voice, 'recording_id': take['recording_id'], 'audio_sha256': take['audio_sha256'],
                     'reference_start_ms': reference['speech_start_ms'],
                     'reference_start_range_ms': reference['speech_start_range_ms'],
                     'model_start_ms': round(start * 1000, 9) if start is not None else None,
                     'start_status': reference['status'],
                     'model_status': alignment['status'], 'duration_ms': 1000 * len(pcm) / rate,
                     'archival_wav_repeat': take['audio_sha256'] == archived[pid]['audio_sha256']
                                            if voice == VOICES[0] else None})
    if hashes != {name: digest(path) for name, path in sources.items()}:
        raise ValueError('An input manifest or the training report changed during the check')
    write_json(output, {'training_sha256': hashes['training'], 'source_sha256': hashes,
                        'model': {'name': MODEL, 'revision': REVISION, 'weights_sha256': WEIGHTS_SHA256,
                                  'funasr_version': version('funasr'), 'conditioning': 'ordered Han count'},
                        'waveform_settings': WAVEFORM_REFERENCE_SETTINGS, 'takes': rows})
    return {'works': len(passages), 'takes': len(rows), 'waveform_onsets': sum(
        row['reference_start_ms'] is not None for row in rows), 'aligned_takes': sum(
        row['model_start_ms'] is not None for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--training', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.project.resolve(strict=True), args.root.resolve(strict=True),
                             args.model_cache.resolve(strict=True), args.training.resolve(strict=True),
                             args.output.resolve()), allow_nan=False))


if __name__ == '__main__':
    main()
