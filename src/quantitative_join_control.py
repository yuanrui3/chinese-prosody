"""Check absolute internal onset timing at known PCM joins in two synthetic voices."""

import argparse
from array import array
from collections import defaultdict
from hashlib import sha256
from importlib.metadata import version
import json
from math import isclose, isfinite
import os
from pathlib import Path
from statistics import median
import sys

from audio.synthesize import SAMPLE_RATE
from src.quantitative_offset import errors
from src.quantitative_onset_collect import HISTORICAL, TRAINING, verify_inventory, verify_takes
from src.quantitative_onset_transfer import METHODS, WAVEFORM_SETTINGS, freeze, measure, paired_inputs, was_improved
from src.quantitative_report import FILES, VOICES, check_inventory
from src.quantitative_waveform_reference import waveform_reference
from src.recitation_second_aligner import FRAME_MS, MandarinTimestampPredictor, map_intervals
from src.stage6_listening import digest, read_clip, read_json, write_json
from src.stage7_cli import write_output


TRANSFER = Path('model-development/quantitative-onset-transfer')
EXPERIMENT = Path('model-development/quantitative-join-control')
OBSERVATIONS = Path('results/onset-transfer/onset-observations.json')
GAP_MS = 400


def compose_pcm(left, right, rate, gap_ms=GAP_MS):
    if (left.typecode != 'h' or right.typecode != 'h' or not left or not right or rate != SAMPLE_RATE
            or type(gap_ms) is not int or gap_ms < 1):
        raise ValueError('Expected complete nonempty recordings in the same PCM16 format')
    gap = array('h', [0]) * (gap_ms * rate // 1000)
    right_start = len(left) + len(gap)
    joined = left + gap + right
    if joined[:len(left)] != left or joined[len(left):right_start] != gap or joined[right_start:] != right:
        raise ValueError('Concatenation did not preserve both original waveform regions and the exact zero guard')
    canonical = joined
    if sys.byteorder != 'little':
        canonical = array('h', joined)
        canonical.byteswap()
    return joined, right_start, sha256(canonical.tobytes()).hexdigest()


def checked_donor(root, passage, take, observed):
    if (observed['recording_id'] != take['recording_id'] or observed['audio_sha256'] != take['audio_sha256']
            or observed['text_sha256'] != passage['text_sha256']
            or any(observed[key] != passage[key] for key in ('work_id', 'author', 'pair_id', 'passage_id'))):
        raise ValueError('Standalone onset row is disconnected from its source or audio')
    rate, pcm = read_clip(root, take, SAMPLE_RATE)
    reference = waveform_reference(pcm, rate)
    duration_ms = 1000 * len(pcm) / rate
    if (not isclose(observed['duration_ms'], duration_ms, abs_tol=1e-6, rel_tol=0)
            or not isclose(take['duration_s'], len(pcm) / rate, abs_tol=1e-6, rel_tol=0)
            or observed['reference_start_ms'] != reference['speech_start_ms']
            or observed['reference_start_range_ms'] != reference['speech_start_range_ms']
            or observed['start_status'] != reference['status']):
        raise ValueError('Standalone recording duration or waveform landmarks cannot be reproduced')
    return {'pcm': pcm, 'reference': reference, 'observed': observed,
            'characters': ''.join(slot['char'] for slot in passage['slots'])}


def join_case(model, left, right, shift):
    pcm, right_start, checksum = compose_pcm(left['pcm'], right['pcm'], SAMPLE_RATE)
    right_slot = len(left['characters'])
    characters = left['characters'] + right['characters']
    duration_ms = len(pcm) * 1000 / SAMPLE_RATE
    try:
        times = model.timestamps(pcm, SAMPLE_RATE, characters)
    except AssertionError:
        intervals, status = [], 'timestamp_prediction_rejected'
    else:
        if all(isfinite(value) for interval in times for value in interval):
            intervals, status = map_intervals(times, characters, duration_ms)
        else:
            intervals, status = [], 'nonfinite_timestamp'
    model_ms = round(intervals[right_slot]['start_s'] * 1000, 9) if intervals else None
    source = right['observed']
    right_offset_ms = right_start * 1000 / SAMPLE_RATE
    donor_onset_sample = right['reference']['speech_start_sample']
    onset_sample = right_start + donor_onset_sample if donor_onset_sample is not None else None
    reference_ms = 1000 * onset_sample / SAMPLE_RATE if onset_sample is not None else None
    range_ms = source['reference_start_range_ms']
    standalone_model_ms = source['model_start_ms']
    return measure({
        **{key: source[key] for key in ('pair_id', 'work_id', 'passage_id', 'voice', 'period', 'genre')},
        'left_recording_id': left['observed']['recording_id'],
        'left_audio_sha256': left['observed']['audio_sha256'],
        'right_recording_id': source['recording_id'],
        'right_audio_sha256': source['audio_sha256'],
        'sample_rate_hz': SAMPLE_RATE,
        'composite_pcm16le_sha256': checksum,
        'left_sample_count': len(left['pcm']),
        'right_sample_count': len(right['pcm']),
        'right_start_sample': right_start,
        'reference_onset_sample': onset_sample,
        'right_slot_index': right_slot,
        'status': status,
        'reference_status': source['start_status'],
        'reference_start_ms': reference_ms,
        'reference_start_range_ms': [right_offset_ms + value for value in range_ms] if range_ms is not None else None,
        'model_start_ms': model_ms,
        'duration_ms': duration_ms,
        'standalone_model_start_ms': standalone_model_ms,
        'context_movement_ms': (model_ms - right_offset_ms - standalone_model_ms
                                if model_ms is not None and standalone_model_ms is not None else None),
    }, shift)


def summarize(rows):
    by_work = defaultdict(dict)
    for row in rows:
        work, voice = row['work_id'], row['voice']
        if voice in by_work[work]:
            raise ValueError('A target work must occur only once per voice')
        by_work[work][voice] = row
    if any(set(voices) != set(VOICES) for voices in by_work.values()):
        raise ValueError('Both voices must have the same target works')
    shared = sorted(work for work, voices in by_work.items() if all(row['eligible'] for row in voices.values()))
    shared_context = [work for work in shared if all(row['context_movement_ms'] is not None
                                                    for row in by_work[work].values())]
    by_voice = {}
    for voice in VOICES:
        eligible = [by_work[work][voice] for work in shared]
        movement = [by_work[work][voice]['context_movement_ms'] for work in shared_context]
        stats = {}
        for method in METHODS:
            metrics = errors([{**row, 'work_id': row['pair_id'], 'estimate': row['predictions_ms'][method]}
                              for row in eligible], 'estimate')
            stats[method] = {'landmarks': metrics['edges'], 'pairs': metrics['works'],
                             'pair_weighted_mae_ms': metrics['work_weighted_mae_ms'],
                             'median_signed_error_ms': metrics['median_signed_error_ms'],
                             'pair_weighted_distance_outside_reference_range_ms':
                             metrics['work_weighted_distance_outside_reference_range_ms'],
                             'outside_clip': metrics['outside_clip']}
        changes = [was_improved(row) for row in eligible]
        by_voice[voice] = {'eligible_targets': sum(item[voice]['eligible'] for item in by_work.values()),
                           'by_method_on_shared_targets': stats,
                           'frozen_vs_raw': {key: changes.count(key) for key in ('improved', 'tied', 'worsened')},
                           'context_median_movement_ms': median(movement) if movement else None,
                           'context_median_absolute_movement_ms': median(map(abs, movement)) if movement else None}
    return {'shared_target_works': shared, 'shared_standalone_comparison_works': shared_context, 'by_voice': by_voice}


def run(project, root, cache):
    if root != project / EXPERIMENT or not cache.is_relative_to(project):
        raise ValueError('Keep the join control and the timestamp model on the Gilbreth project filesystem')
    corpus = project / TRANSFER
    inputs = {'training': project / TRAINING, 'observations': corpus / OBSERVATIONS,
              'annotations': corpus / FILES['passages'], 'manifest': corpus / FILES['takes'],
              'historical_manifest': project / HISTORICAL / FILES['takes']}
    hashes = {name: digest(path) for name, path in inputs.items()}
    frozen = freeze(read_json(inputs['training']))
    collection = read_json(inputs['observations'])
    if collection.get('source_sha256') != {
            'training': hashes['training'], 'annotated': hashes['annotations'], 'takes': hashes['manifest'],
            'archived_takes': hashes['historical_manifest']}:
        raise ValueError('Standalone onset observations do not match the frozen source manifests')
    observed = paired_inputs(collection, frozen, hashes['training'])
    passages = verify_inventory(project, corpus)
    takes, _ = verify_takes(project, corpus, passages)
    if set(observed) != {row['work_id'] for row in passages.values()}:
        raise ValueError('Expected standalone onset rows for the full set of target works')
    if version('funasr') != frozen['model']['funasr_version']:
        raise ValueError('Expected the same FunASR package as the standalone run')
    pairs = check_inventory(passages)
    model = MandarinTimestampPredictor(cache)
    results = []
    for _, pair in sorted(pairs.items()):
        for voice in VOICES:
            first, second = (checked_donor(corpus, row, takes[row['passage_id'], voice],
                                           observed[row['work_id']][voice]) for row in pair)
            results.append(join_case(model, first, second, frozen['shift_ms']))
            results.append(join_case(model, second, first, frozen['shift_ms']))
    if hashes != {name: digest(path) for name, path in inputs.items()}:
        raise ValueError('A pinned input changed during the join experiment')
    return {'schema_version': 1, 'source_sha256': hashes, 'inserted_silence_ms': GAP_MS, 'model': frozen['model'],
            'model_frame_ms': FRAME_MS, 'waveform_settings': WAVEFORM_SETTINGS,
            'frozen_calibration_ms': frozen['shift_ms'], 'matched_pairs': len(pairs), 'composites': len(results),
            **summarize(results), 'rows': results}


def render(report):
    lines = ['# Absolute onset timing at controlled PCM joins', '',
             f"Both directions of {report['matched_pairs']} matched historical prose pairs were assembled in both voices. "
             f"Each in-memory composite preserves the complete source WAV sample arrays around a {report['inserted_silence_ms']} ms "
             'zero interval. The waveform reference is the onset measured on the untouched second donor and translated by '
             'the known placement. FunASR targets the first Han position of that donor in the combined input.', '',
             f"Both voices were measurable for {len(report['shared_target_works'])} of {report['composites'] // len(VOICES)} "
             'target works. Errors weight literary pairs equally when both directions are measurable. The onset correction '
             f"of {report['frozen_calibration_ms']:+g} ms was frozen on v4 recording onsets before the separate transfer run.", '',
             '| Voice | Own eligible targets | Raw MAE (ms) | Frozen correction MAE (ms) | −80 ms MAE (ms) | Median absolute context movement (ms) |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for voice, result in report['by_voice'].items():
        scores = [result['by_method_on_shared_targets'][method]['pair_weighted_mae_ms'] for method in METHODS]
        scores.append(result['context_median_absolute_movement_ms'])
        formatted = ['Unavailable' if value is None else f'{value:.2f}' for value in scores]
        lines.append(f"| {voice} | {result['eligible_targets']} | " + ' | '.join(formatted) + ' |')
    lines += ['', 'Context movement compares the embedded onset with the standalone model onset, after subtracting '
              'the exact placement of the second donor. Both predictions refer to identical source speech. '
              'The comparison measures relocation by context. The known audio join supplies a synthetic internal landmark. '
              'Native clause timing and phonetic identity require separate evidence.', '']
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
            or any(path.exists() or not path.is_relative_to(root) for path in destinations)):
        parser.error('Expected new, distinct report files within the private experiment')
    report = run(project, root, cache)
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
    if markdown:
        write_output(markdown, render(report))
    write_json(output, report)
    print(json.dumps({key: report[key] for key in ('composites', 'shared_target_works', 'by_voice')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
