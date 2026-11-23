"""Evaluate a frozen recording-onset adjustment on a disjoint two-voice corpus."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from math import isclose, isfinite
import os
from pathlib import Path
import re

from src.expansion_design import authors
from src.quantitative_offset import FIXED_SHIFT_MS, errors, learn_shift
from src.quantitative_report import VOICES
from src.quantitative_waveform_reference import WAVEFORM_REFERENCE_SETTINGS
from src.recitation_second_aligner import MODEL, REVISION, WEIGHTS_SHA256
from src.stage6_listening import write_json
from src.stage7_cli import write_output


MODEL_PIN = {'name': MODEL, 'revision': REVISION, 'weights_sha256': WEIGHTS_SHA256}
WAVEFORM_SETTINGS = json.loads(json.dumps(WAVEFORM_REFERENCE_SETTINGS))
TRAINING_WORKS = 8
METHODS = ('raw', 'frozen', 'fixed_minus_80')


def required_text(row, key):
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Missing {key} in onset-validation inventory')
    return value


def audio_hash(row):
    checksum = required_text(row, 'audio_sha256')
    if not re.fullmatch('[0-9a-f]{64}', checksum):
        raise ValueError('Expected a lowercase SHA-256 for each recording')
    return checksum


def checked_model(model):
    if any(model.get(key) != value for key, value in MODEL_PIN.items()):
        raise ValueError('The alignment model differs from the pinned FunASR model')
    return model


def numeric(value):
    return type(value) in (int, float) and isfinite(value)


def check_landmark(reference, bounds, estimate, duration):
    if not numeric(duration) or duration <= 0:
        raise ValueError('The bound recording must have a positive duration')
    if reference is None:
        if bounds is not None:
            raise ValueError('A missing waveform onset cannot have a threshold range')
    elif (not numeric(reference) or not isinstance(bounds, (tuple, list)) or len(bounds) != 2
          or not all(numeric(edge) for edge in bounds)
          or not 0 <= bounds[0] <= reference <= bounds[1] <= duration
          or bounds[1] - bounds[0] > WAVEFORM_SETTINGS['maximum_sensitivity_width_ms']):
        raise ValueError('The waveform onset is outside its stable threshold range')
    if estimate is not None and (not numeric(estimate) or not 0 <= estimate < duration):
        raise ValueError('The uncorrected FunASR onset must lie within the bound recording')


def freeze(report):
    """Fit one common shift from the authenticated v4 training corpus only."""
    waveform = report['waveform_offset']
    if waveform['waveform_settings'] != WAVEFORM_SETTINGS or tuple(report['conditions']['voice_ids']) != VOICES:
        raise ValueError('Expected the v4 waveform settings and both benchmark voices')
    model = checked_model(report['secondary_alignment']['model'])
    works, credits, expected = set(), set(), {}
    for profile in report['passages']:
        witness = profile['witness']
        work, pid = (required_text(witness, field) for field in ('work_id', 'passage_id'))
        names = authors(witness)
        if work in works or not names or names & credits:
            raise ValueError('Training requires independent works and credited authors')
        works.add(work)
        credits.update(names)
        for voice in VOICES:
            timing = profile['音律美']['recorded_timing'][voice]
            key = work, voice
            expected[key] = (pid, timing['recording_id'], audio_hash(timing))
    if len(works) != TRAINING_WORKS:
        raise ValueError('Expected the eight-work v4 onset-calibration split')
    seen, eligible = set(), []
    for row in waveform['edges']:
        if row['kind'] != 'clip_start':
            continue
        key = row['work_id'], row['voice']
        identity = row['passage_id'], row['recording_id'], audio_hash(row)
        if key in seen or expected.get(key) != identity:
            raise ValueError('The v4 onset does not match exactly one training recording')
        seen.add(key)
        reference, estimate = row['edge_ms'], row['funasr_ms']
        check_landmark(reference, row['reference_range_ms'], estimate, row['clip_ms'])
        if reference is not None and estimate is not None:
            eligible.append(row)
    if seen != set(expected):
        raise ValueError('The v4 report must record a training onset or abstention for each take')
    shift = learn_shift(eligible, None, 'clip_start')
    if shift is None:
        raise ValueError('Insufficient stable training works to freeze an onset shift')
    return {'shift_ms': shift, 'training_works': works, 'training_authors': credits, 'model': model,
            'training_audio_sha256': {identity[2] for identity in expected.values()},
            'training_onsets': {voice: sum(row['voice'] == voice for row in eligible) for voice in VOICES},
            'fit_works': len({row['work_id'] for row in eligible})}


def paired_inputs(collection, frozen, training_sha256):
    if collection['training_sha256'] != training_sha256:
        raise ValueError('The collector used a different training report')
    model = checked_model(collection['model'])
    if model != frozen['model'] or collection['waveform_settings'] != WAVEFORM_SETTINGS:
        raise ValueError('The evaluation must use the training model and waveform settings')
    by_work, owners, seen_hashes = defaultdict(dict), {}, set()
    for row in collection['takes']:
        work, voice = (required_text(row, field) for field in ('work_id', 'voice'))
        for field in ('author', 'pair_id', 'passage_id', 'start_status'):
            required_text(row, field)
        names, checksum = authors(row), audio_hash(row)
        if (work in frozen['training_works'] or not names or names & frozen['training_authors']
                or checksum in frozen['training_audio_sha256']):
            raise ValueError('The held-out split reuses a training work, credited author, or recording')
        if voice not in VOICES or voice in by_work[work] or checksum in seen_hashes:
            raise ValueError('Expected one unique recording per work and benchmark voice')
        seen_hashes.add(checksum)
        pid = row['passage_id']
        if owners.setdefault(pid, work) != work:
            raise ValueError('A passage identifier cannot name multiple held-out works')
        check_landmark(row['reference_start_ms'], row['reference_start_range_ms'],
                       row['model_start_ms'], row['duration_ms'])
        by_work[work][voice] = row
    if not by_work or any(set(pair) != set(VOICES) for pair in by_work.values()):
        raise ValueError('Every held-out work must have both voices, including recorded abstentions')
    for pair in by_work.values():
        if any(pair[VOICES[0]].get(key) != pair[VOICES[1]].get(key)
               for key in ('passage_id', 'author', 'pair_id', 'period', 'genre')):
            raise ValueError('Voices must share the same held-out passage, source, and stratum')
    return by_work


def measure(row, shift):
    raw, reference = row['model_start_ms'], row['reference_start_ms']
    available = raw is not None and reference is not None
    predictions = dict(zip(METHODS, (raw, raw + shift, raw + FIXED_SHIFT_MS))) if available else dict.fromkeys(METHODS)
    signed = {name: value - reference if available else None for name, value in predictions.items()}
    return {**row, 'clip_ms': row['duration_ms'], 'edge_ms': reference,
            'reference_range_ms': row['reference_start_range_ms'], 'eligible': available,
            'predictions_ms': predictions, 'signed_error_ms': signed}


def was_improved(row):
    raw, candidate = (abs(row['signed_error_ms'][key]) for key in ('raw', 'frozen'))
    if isclose(raw, candidate, rel_tol=0, abs_tol=1e-9):
        return 'tied'
    return 'improved' if candidate < raw else 'worsened'


def evaluate(collection, frozen, training_sha256, collector_sha256):
    paired = paired_inputs(collection, frozen, training_sha256)
    items, shared = [], []
    for work, pair in sorted(paired.items()):
        measurements = [measure(pair[voice], frozen['shift_ms']) for voice in VOICES]
        comparable = all(row['eligible'] for row in measurements)
        if comparable:
            shared.append(work)
        items.append({'work_id': work, 'author': measurements[0]['author'], 'shared_onset': comparable,
                      'voices': {row['voice']: row for row in measurements}})
    summaries = {}
    for voice in VOICES:
        eligible = [item['voices'][voice] for item in items if item['shared_onset']]
        changes = [was_improved(row) for row in eligible]
        summaries[voice] = {
            'own_eligible_works': sum(item['voices'][voice]['eligible'] for item in items),
            'comparison_on_shared_works': {method: errors(
                [{**row, 'prediction': row['predictions_ms'][method]} for row in eligible], 'prediction')
                for method in METHODS},
            'frozen_vs_raw': {decision: changes.count(decision) for decision in ('improved', 'tied', 'worsened')},
        }
    return {'schema_version': 1, 'source_sha256': {'training_report': training_sha256,
                                                    'evaluation_collection': collector_sha256},
            'model': frozen['model'], 'waveform_settings': WAVEFORM_SETTINGS,
            'frozen_calibration': {'ms': frozen['shift_ms'], 'training_works': sorted(frozen['training_works']),
                                   'training_authors': sorted(frozen['training_authors']),
                                   'onsets_by_voice': frozen['training_onsets'], 'fit_works': frozen['fit_works']},
            'fixed_comparator_ms': FIXED_SHIFT_MS, 'total_held_out_works': len(items),
            'shared_held_out_works': shared, 'by_voice': summaries, 'by_work': items,
            '音律美': {'evidence': 'recording onset timing diagnostic'},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None}}


def render(report):
    shift = report['frozen_calibration']['ms']
    lines = ['# Held-out transfer of the recording-onset correction', '',
             f"The shift of {shift:+g} ms was fitted on eight v4 works before reading the evaluation landmarks. "
             'The evaluation works and credited authors are disjoint from that calibration set. Both voices use the '
             'same eligible held-out works. A recording onset is a stable waveform energy landmark.', '',
             f"Both voices had measurable onsets in {len(report['shared_held_out_works'])} of "
             f"{report['total_held_out_works']} held-out works.", '',
             '| Voice | Usable works before intersection | Raw error (ms) | Frozen error (ms) | −80 ms error (ms) | Improved / tied / worsened |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for voice, result in report['by_voice'].items():
        scores = [result['comparison_on_shared_works'][method]['work_weighted_mae_ms'] for method in METHODS]
        cells = ['Unavailable' if value is None else f'{value:.2f}' for value in scores]
        changes = ' / '.join(str(result['frozen_vs_raw'][label]) for label in ('improved', 'tied', 'worsened'))
        lines.append(f"| {voice} | {result['own_eligible_works']} | " + ' | '.join(cells) + f' | {changes} |')
    lines += ['', 'Errors are mean absolute errors weighted equally by work. Negative corrected '
              'coordinates keep their original error. The JSON records work-level measurements and abstentions.', '',
              'The waveform evidence concerns recording onset for 音律美. 顺口 still requires independent first-read evidence.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training', type=Path, required=True, help='Original v4 quantitative waveform report')
    parser.add_argument('--input', type=Path, required=True, help='Checksum-bound evaluation onset collection')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--markdown', type=Path)
    args = parser.parse_args()
    destinations = [args.output] + ([args.markdown] if args.markdown else [])
    paths = [args.training, args.input, *destinations]
    if len({path.resolve() for path in paths}) != len(paths):
        parser.error('Training, evaluation, and report files must use distinct paths')
    os.umask(0o077)
    training = args.training.read_bytes()
    frozen = freeze(json.loads(training))
    test = args.input.read_bytes()
    report = evaluate(json.loads(test), frozen, sha256(training).hexdigest(), sha256(test).hexdigest())
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    if args.markdown is not None:
        write_output(args.markdown, render(report))
    print(json.dumps({key: report[key] for key in ('total_held_out_works', 'shared_held_out_works',
                                                 'frozen_calibration', 'by_voice')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
