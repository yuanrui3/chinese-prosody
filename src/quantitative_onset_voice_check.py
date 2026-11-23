"""Test the frozen recording-onset correction in an additional synthetic voice."""

import argparse
from hashlib import sha256
from importlib.metadata import version
import json
from math import isclose
import os
from pathlib import Path

from audio.synthesize import ASSET_SHA256, REPO, REVISION as KOKORO_REVISION, SAMPLE_RATE
from src.quantitative_offset import FIXED_SHIFT_MS, errors
from src.quantitative_onset_collect import CODE, HISTORICAL, TRAINING, verify_inventory, verify_takes
from src.quantitative_onset_transfer import (
    METHODS, WAVEFORM_SETTINGS, audio_hash, check_landmark, freeze, measure, paired_inputs, was_improved,
)
from src.quantitative_report import FILES, VOICES, index
from src.quantitative_second_alignment import predict_take
from src.quantitative_waveform_reference import waveform_reference
from src.recitation_second_aligner import FRAME_MS, MandarinTimestampPredictor
from src.stage6_listening import digest, read_clip, read_json, read_rows, write_json
from src.stage7_cli import write_output


TRANSFER = Path('model-development/quantitative-onset-transfer')
EXPERIMENT = Path('model-development/quantitative-onset-third-voice')
OBSERVATIONS = Path('results/onset-transfer/onset-observations.json')
THIRD_VOICE = 'zf_002'
ALL_VOICES = (*VOICES, THIRD_VOICE)
SOURCE_FIELDS = ('work_id', 'author', 'pair_id', 'passage_id', 'genre', 'period', 'source_url', 'text_sha256')
RENDER_FIELDS = ('text_sha256', 'text_revision', 'text_source_url', 'text_license', 'intended_pinyin',
                 'intended_model_phonemes', 'kind', 'variety', 'style', 'speed', 'sample_rate', 'seed',
                 'source_url', 'model_revision', 'model_license', 'pronunciation_status')


def verify_third_takes(root, passages, known_takes, training_audio):
    takes = index(read_rows(root / FILES['takes']), lambda row: row['passage_id'])
    if takes.keys() != passages.keys():
        raise ValueError('Expected a third-voice take for every archived evaluation work')
    hashes = set(training_audio) | {audio_hash(take) for take in known_takes.values()}
    for pid, passage in passages.items():
        take = takes[pid]
        recording = f'kokoro-{pid}-{THIRD_VOICE}-0p9'
        path = Path('audio/raw/synthetic') / f'{recording}.wav'
        audio = root / path
        seed = int(sha256(f'kokoro-{pid}-{VOICES[0]}-0p9'.encode()).hexdigest()[:8], 16)
        checksum = audio_hash(take)
        if (take['speaker'] != THIRD_VOICE or take['recording_id'] != recording or Path(take['audio_path']) != path
                or (take['kind'], take['variety'], take['style'], take['speed'], take['sample_rate'])
                != ('synthetic', 'cmn', 'controlled_read_speech', 0.9, SAMPLE_RATE)
                or take['text_sha256'] != passage['text_sha256'] or take['text_revision'] != passage['revision_id']
                or take['text_source_url'] != passage['source_url'] or take['text_license'] != passage['license']
                or take['source_url'] != f'https://huggingface.co/{REPO}/tree/{KOKORO_REVISION}'
                or take['model_revision'] != KOKORO_REVISION or take['model_license'] != 'Apache-2.0'
                or take['pronunciation_status'] != 'input_only' or take['seed'] != seed
                or any(take[key] != known_takes[pid, voice][key]
                       for voice in VOICES for key in RENDER_FIELDS)
                or checksum in hashes or audio.is_symlink() or audio.stat().st_mode & 0o077):
            raise ValueError(f'{recording}: third-voice synthesis conditions or waveform provenance differ')
        hashes.add(checksum)
    return takes


def linked_observation(observation, passage, take):
    if (any(observation[key] != passage[key] for key in SOURCE_FIELDS)
            or any(observation[key] != take[key] for key in ('recording_id', 'audio_sha256'))
            or not isclose(observation['duration_ms'], 1000 * take['duration_s'], rel_tol=0, abs_tol=1e-6)):
        raise ValueError('The earlier onset observation no longer matches its source and recording manifest')


def third_observation(root, model, passage, take):
    rate, pcm = read_clip(root, take, SAMPLE_RATE)
    reference = waveform_reference(pcm, rate)
    alignment = predict_take(model, root, take, passage)
    estimate = round(1000 * alignment['slots'][0]['start_s'], 9) if alignment['slots'] else None
    duration = 1000 * len(pcm) / rate
    check_landmark(reference['speech_start_ms'], reference['speech_start_range_ms'], estimate, duration)
    return {**{key: passage[key] for key in SOURCE_FIELDS},
            'voice': THIRD_VOICE, 'recording_id': take['recording_id'], 'audio_sha256': take['audio_sha256'],
            'reference_start_ms': reference['speech_start_ms'],
            'reference_start_range_ms': reference['speech_start_range_ms'],
            'model_start_ms': estimate, 'start_status': reference['status'],
            'model_status': alignment['status'], 'duration_ms': duration}


def summarize(works):
    """Report each voice's available cohort and the exact common three-voice subset."""
    if not works or any(set(voices) != set(ALL_VOICES) for voices in works.values()):
        raise ValueError('Expected the full archived set for all three voices')
    shared = sorted(work for work, voices in works.items() if all(row['eligible'] for row in voices.values()))

    def table(rows):
        outcomes = [was_improved(row) for row in rows]
        return {'works': len(rows),
                'by_method': {method: errors([{**row, 'estimate': row['predictions_ms'][method]} for row in rows],
                                             'estimate') for method in METHODS},
                'frozen_vs_raw': {status: outcomes.count(status) for status in ('improved', 'tied', 'worsened')}}

    by_voice = {voice: {
        'own_onset_metrics': table([rows[voice] for rows in works.values() if rows[voice]['eligible']]),
        'all_three_onset_metrics': table([works[work][voice] for work in shared]),
    } for voice in ALL_VOICES}
    return {'total_works': len(works), 'shared_works_all_three': shared, 'by_voice': by_voice}


def run(project, root, cache):
    if root != project / EXPERIMENT or not cache.is_relative_to(project):
        raise ValueError('Keep the third-voice validation and its model inside the Gilbreth project')
    transfer = project / TRANSFER
    sources = {'training': project / TRAINING, 'earlier_observations': transfer / OBSERVATIONS,
               'earlier_annotations': transfer / FILES['passages'], 'earlier_takes': transfer / FILES['takes'],
               'annotated': root / FILES['passages'], 'takes': root / FILES['takes'],
               'archived_annotations': project / HISTORICAL / FILES['passages'],
               'archived_takes': project / HISTORICAL / FILES['takes'],
               'historical_inventory': CODE / 'data/pilot/historical-increment.json',
               'reading_inventory': CODE / 'audio/historical_increment_readings.json'}
    hashes = {name: digest(path) for name, path in sources.items()}
    frozen = freeze(read_json(sources['training']))
    collection = read_json(sources['earlier_observations'])
    if (collection.get('source_sha256') != {'training': hashes['training'],
            'annotated': hashes['earlier_annotations'], 'takes': hashes['earlier_takes'],
            'archived_takes': hashes['archived_takes']}
            or hashes['earlier_annotations'] != hashes['archived_annotations']):
        raise ValueError('Earlier onset observations differ from the audited archive and manifests')
    earlier = paired_inputs(collection, frozen, hashes['training'])
    passages = verify_inventory(project, root)
    known_takes, _ = verify_takes(project, transfer, passages)
    if earlier.keys() != {passage['work_id'] for passage in passages.values()}:
        raise ValueError('Earlier observations and the third response must use the full archival work set')
    third_takes = verify_third_takes(root, passages, known_takes, frozen['training_audio_sha256'])
    for pid, passage in passages.items():
        for voice in VOICES:
            linked_observation(earlier[passage['work_id']][voice], passage, known_takes[pid, voice])
    if version('funasr') != frozen['model']['funasr_version'] or THIRD_VOICE in VOICES:
        raise ValueError('Expected the frozen model and a voice absent from calibration')

    model = MandarinTimestampPredictor(cache)
    by_work = {}
    for pid, passage in sorted(passages.items()):
        work = passage['work_id']
        third = third_observation(root, model, passage, third_takes[pid])
        observations = {**earlier[work], THIRD_VOICE: third}
        by_work[work] = {voice: measure(row, frozen['shift_ms']) for voice, row in observations.items()}
    if hashes != {name: digest(path) for name, path in sources.items()}:
        raise ValueError('A pinned input changed during third-voice validation')
    return {'schema_version': 1, 'source_sha256': hashes, 'model': frozen['model'], 'model_frame_ms': FRAME_MS,
            'new_voice': THIRD_VOICE, 'new_voice_asset_sha256': ASSET_SHA256[f'voices/{THIRD_VOICE}.pt'],
            'waveform_settings': WAVEFORM_SETTINGS, 'frozen_calibration_ms': frozen['shift_ms'],
            'fixed_comparator_ms': FIXED_SHIFT_MS, **summarize(by_work), 'by_work': by_work,
            '音律美': {'evidence': 'recording onset timing diagnostic'},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None}}


def render(report):
    lines = ['# Held-out voice check for the recording-onset correction', '',
             f"`{report['new_voice']}` was absent from calibration and the earlier two-voice check. "
             f"The frozen {report['frozen_calibration_ms']:+g} ms correction came from the eight v4 training works. "
             'The previously archived evaluation texts and authors are disjoint from those training works.', '',
             f"All three voices had measurable onsets in {len(report['shared_works_all_three'])} of "
             f"{report['total_works']} evaluation works. Waveform landmarks are stable energy transitions near "
             'the start of the unedited recordings. Errors are means weighted equally by work.', '',
             '| Voice | Work cohort | Count | Raw MAE (ms) | Frozen MAE (ms) | −80 ms MAE (ms) | Improved / tied / worsened |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for voice, cohorts in report['by_voice'].items():
        for key, label in (('own_onset_metrics', 'Available in this voice'),
                           ('all_three_onset_metrics', 'Available in all three voices')):
            result = cohorts[key]
            scores = [result['by_method'][method]['work_weighted_mae_ms'] for method in METHODS]
            cells = ['Unavailable' if value is None else f'{value:.2f}' for value in scores]
            changes = ' / '.join(str(result['frozen_vs_raw'][key]) for key in ('improved', 'tied', 'worsened'))
            lines.append(f"| {voice} | {label} | {result['works']} | " + ' | '.join(cells) + f' | {changes} |')
    lines.extend(['', 'The JSON includes each work and abstention. These measurements concern recording-onset timing '
                  'for 音律美 research. 顺口 awaits independent first-read evidence.', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--markdown', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    project, root, cache = (path.resolve(strict=True) for path in (args.project, args.root, args.model_cache))
    output, markdown = args.output.resolve(), args.markdown.resolve() if args.markdown else None
    destinations = [output] + ([markdown] if markdown else [])
    if (len(set(destinations)) != len(destinations)
            or any(path.exists() or not path.is_relative_to(root / 'results') for path in destinations)):
        parser.error('Expected new, distinct report files inside the experiment results')
    report = run(project, root, cache)
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
    if markdown:
        write_output(markdown, render(report))
    write_json(output, report)
    print(json.dumps({key: report[key] for key in ('total_works', 'shared_works_all_three', 'by_voice')},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
