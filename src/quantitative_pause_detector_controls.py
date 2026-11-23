"""Check waveform pause detection on exact insertions in held-out synthetic speech."""

import argparse
from array import array
from hashlib import sha256
import json
from math import isclose
import os
from pathlib import Path
import sys

from audio.synthesize import REPO, REVISION, SAMPLE_RATE, encode_syllable, prepare_passage
from src.expansion_design import authors
from src.quantitative_onset_collect import TRAINING
from src.quantitative_onset_voice_check import ALL_VOICES, OBSERVATIONS, TRANSFER
from src.quantitative_report import FILES, VOICES, check_inventory, index
from src.quantitative_waveform_reference import WAVEFORM_REFERENCE_SETTINGS, waveform_reference
from src.recitation_phrasing import insert_silence, verify_variant
from src.stage6_listening import digest, read_clip, read_json, read_rows, write_json
from src.stage7_cli import write_output


CODE = Path(__file__).resolve().parents[1]
EXPERIMENT = Path('model-development/quantitative-pause-detector')
REPLICATION = Path('model-development/quantitative-pause-replication')
ARCHIVE = Path('pilot-expansions/independent-works')
HOLDOUT_PASSAGES = {'XSD03', 'XSD04', 'XET01', 'XET02'}
REPLICATION_PASSAGES = {'PSD1P', 'PSD1C', 'PET1P', 'PET1C'}
DEVELOPMENT = ('quantitative-report', 'historical-increment')
GAINS_DB = (0, -12)
GUARDS_MS = (0, 60, 120, 240, 400)
POSITIVE_MIN_MS = 100
FRAME_MS = 5
FLANK_MS = 30
MIN_FLANK_DBFS = -34
EDGE_TOLERANCE_MS = 20
METHODS = ('strict', 'relative')


def files_to_check(project, root):
    sources = {
        'archived_annotations': project / ARCHIVE / FILES['passages'],
        'evaluation_annotations': root / FILES['passages'],
        'evaluation_recordings': root / FILES['takes'],
        'development_v4_report': project / TRAINING,
        'development_historical_observations': project / TRANSFER / OBSERVATIONS,
        **{name: project / 'model-development' / name / FILES['passages'] for name in DEVELOPMENT},
    }
    if root == project / REPLICATION:
        sources.update({'replication_pins': CODE / 'data/pilot/pause-replication.json',
                        'reading_pins': CODE / 'audio/pause_replication_readings.json',
                        'original_annotations': project / FILES['passages']})
    else:
        sources.update({'expansion_pins': CODE / 'data/pilot/expansion-passages.json',
                        'reading_pins': CODE / 'audio/expansion_readings.json'})
    return sources


def checked_passages(sources):
    archive = index(read_rows(sources['archived_annotations']), lambda row: row['passage_id'])
    rendered = index(read_rows(sources['evaluation_annotations']), lambda row: row['passage_id'])
    replication = 'replication_pins' in sources
    expected = REPLICATION_PASSAGES if replication else HOLDOUT_PASSAGES
    if replication and set(rendered) != expected:
        raise ValueError('The replication requires exactly four fresh annotated works')
    if not replication and (set(rendered) not in (expected, set(archive)) or not expected <= set(archive)
                            or any(row != archive[pid] for pid, row in rendered.items())):
        raise ValueError('The evaluation inventory must copy the archived expansion annotations exactly')
    inventory = read_json(sources['replication_pins' if replication else 'expansion_pins'])
    pins = index(inventory['passages'], lambda row: row['passage_id'])
    witnesses = index(inventory['sources'], lambda row: row['source_id'])
    if replication and set(pins) != expected:
        raise ValueError('The replication inventory must pin all four fresh passages')
    passages = {pid: rendered[pid] for pid in sorted(expected)}
    v4_pin = read_json(sources['development_v4_report'])['source_sha256']['passages']
    historical_pin = read_json(sources['development_historical_observations'])['source_sha256']['annotated']
    if (digest(sources['quantitative-report']) != v4_pin
            or digest(sources['historical-increment']) != historical_pin):
        raise ValueError('Development inventories differ from the previously audited sources')
    archive_development = [row for name in DEVELOPMENT for row in read_rows(sources[name])]
    if replication:
        archive_development += list(archive.values()) + read_rows(sources['original_annotations'])
    old_works = {row['work_id'] for row in archive_development}
    old_authors = {author for row in archive_development for author in authors(row)}
    old_texts = {row['text_sha256'] for row in archive_development}
    for pid, passage in passages.items():
        pin = pins[pid]
        source = witnesses[pin['source_id']]
        if ((replication and ('task' in passage or 'task' in pin))
                or (not replication and (passage['task'], pin['task']) != ('listening', 'listening'))
                or any(passage[key] != pin[key] for key in (
                    'source_id', 'period', 'genre', 'pair_id', 'han_count', 'text_sha256'))
                or any(passage[key] != source[key] for key in (
                    'work_id', 'author', 'source_url', 'revision_id', 'license', 'attribution'))
                or passage['work_id'] in old_works or authors(passage) & old_authors
                or passage['text_sha256'] in old_texts):
            raise ValueError(f'{pid}: expected an independent pinned edition, work and author')
    check_inventory(passages)
    return passages


def prescription_inputs(passage, prescription):
    from misaki.zh_frontend import ZH_MAP
    from pypinyin.contrib.tone_convert import to_finals_tone3, to_initials, to_tone3

    def encode(pinyin):
        return encode_syllable(pinyin, ZH_MAP, to_initials, to_finals_tone3)

    pinyin, phonemes, _ = prepare_passage(passage, prescription, encode, to_tone3)
    return pinyin, phonemes


def load_cohort(project, root):
    """Verify the four untouched works and the matched synthesis conditions."""
    if root not in (project / EXPERIMENT, project / REPLICATION) or not root.is_dir():
        raise ValueError('Use the isolated Gilbreth pause-detector experiment')
    sources = files_to_check(project, root)
    passages = checked_passages(sources)
    takes = index(read_rows(sources['evaluation_recordings']), lambda row: (row['passage_id'], row['speaker']))
    if (takes.keys() != {(pid, voice) for pid in passages for voice in ALL_VOICES}
            or len({row['audio_sha256'] for row in takes.values()}) != len(takes)):
        raise ValueError('Expected one distinct recording per work and synthetic voice')
    prescriptions = read_json(sources['reading_pins'])
    if prescriptions.keys() != passages.keys():
        raise ValueError('Expected exactly the four pinned pronunciation prescriptions')
    for pid, passage in passages.items():
        pinyin, phonemes = prescription_inputs(passage, prescriptions[pid])
        seed = int(sha256(f'kokoro-{pid}-{VOICES[0]}-0p9'.encode()).hexdigest()[:8], 16)
        for voice in ALL_VOICES:
            take = takes[pid, voice]
            recording = f'kokoro-{pid}-{voice}-0p9'
            audio_path = Path('audio/raw/synthetic') / f'{recording}.wav'
            wave_path = root / audio_path
            if (take['recording_id'] != recording or Path(take['audio_path']) != audio_path
                    or wave_path.is_symlink() or wave_path.stat().st_mode & 0o077
                    or (take['kind'], take['variety'], take['style'], take['speed'], take['sample_rate'])
                    != ('synthetic', 'cmn', 'controlled_read_speech', 0.9, SAMPLE_RATE)
                    or take['seed'] != seed or take['text_sha256'] != passage['text_sha256']
                    or take['text_revision'] != passage['revision_id']
                    or take['text_source_url'] != passage['source_url'] or take['text_license'] != passage['license']
                    or take['source_url'] != f'https://huggingface.co/{REPO}/tree/{REVISION}'
                    or take['model_revision'] != REVISION or take['model_license'] != 'Apache-2.0'
                    or take['pronunciation_status'] != 'input_only'
                    or (take['intended_pinyin'], take['intended_model_phonemes']) != (pinyin, phonemes)):
                raise ValueError(f'{recording}: expected the pinned text, input, voice and common seed')
    return passages, takes, sources


def sample_count(rate, ms):
    return round(rate * ms / 1000)


def find_cut(pcm, rate):
    """Pick a deterministic energetic cut without any detector or text labels."""
    frame = sample_count(rate, FRAME_MS)
    flank_frames = FLANK_MS // FRAME_MS
    floor = 32768 ** 2 * 10 ** (MIN_FLANK_DBFS / 10)
    powers = [sum(value * value for value in pcm[offset:offset + frame]) / frame
              for offset in range(0, len(pcm) - frame + 1, frame)]
    eligible = ((min(powers[i - flank_frames:i + flank_frames]), i)
                for i in range(max(flank_frames, (len(powers) + 4) // 5),
                               min(len(powers) - flank_frames, 4 * len(powers) // 5) + 1))
    best = max(eligible, key=lambda row: (row[0], -abs(2 * row[1] - len(powers)), -row[1]), default=None)
    return best[1] * frame if best is not None and best[0] >= floor else None


def apply_gain(pcm, db):
    if db == 0:
        return pcm
    if db > 0:
        raise ValueError('Controls allow only attenuation')
    # Round the same samplewise transform once, before splitting into treatments.
    amplitude = 10 ** (db / 20)
    return array('h', (round(sample * amplitude) for sample in pcm))


def pcm_checksum(pcm):
    if sys.byteorder != 'little':
        pcm = array('h', pcm)
        pcm.byteswap()
    return sha256(pcm.tobytes()).hexdigest()


def score_site(pauses, cut, guard, rate):
    """Score only the manufactured target, separately from off-site quiet runs."""
    positive = guard >= sample_count(rate, POSITIVE_MIN_MS)
    tolerance = sample_count(rate, FRAME_MS)
    center = cut + guard // 2

    def matches(row):
        start, end = row['start_sample'], row['end_sample']
        if not start <= center < end:
            return False
        if positive:
            return start <= cut + tolerance and end >= cut + guard - tolerance
        return end - start >= sample_count(rate, POSITIVE_MIN_MS)

    candidates = [row for row in pauses if matches(row)]
    if len(candidates) > 1:
        raise ValueError('A detector produced overlapping candidates at the control site')
    found = candidates[0] if candidates else None
    result = {'total_pauses': len(pauses), 'target_pause': found,
              'outcome': ('hit' if found else 'miss') if positive else ('false_pause' if found else 'no_pause'),
              'usable_resume': bool(found and found.get('resumption_eligible', True)),
              'absolute_edge_error_ms': None, 'both_edges_within_tolerance': None}
    if found is not None and positive:
        errors = [1000 * abs(found[key] - expected) / rate
                  for key, expected in (('start_sample', cut), ('end_sample', cut + guard))]
        result['absolute_edge_error_ms'] = errors
        result['both_edges_within_tolerance'] = all(error <= EDGE_TOLERANCE_MS for error in errors)
    return result


def evaluate_recording(samples, rate, relative_detector):
    cut = find_cut(samples, rate)
    if cut is None:
        return {'status': 'no_energetic_interior_cut', 'cut_sample': None, 'variants': []}
    variants = []
    for db in GAINS_DB:
        carrier = apply_gain(samples, db)
        for ms in GUARDS_MS:
            guard = sample_count(rate, ms)
            edits = [{'source_sample_index': cut, 'inserted_samples': guard}] if guard else []
            variant = insert_silence(carrier, edits)
            verify_variant(carrier, variant, edits)
            outputs = {'strict': waveform_reference(variant, rate), 'relative': relative_detector(variant, rate)}
            variants.append({'gain_db': db, 'guard_ms': ms, 'guard_samples': [cut, cut + guard],
                             'pcm16le_sha256': pcm_checksum(variant),
                             'samples_preserved_after_removing_guard': True,
                             'results': {method: score_site(output['pauses'], cut, guard, rate)
                                         for method, output in outputs.items()}})
    return {'status': 'scored', 'cut_sample': cut, 'variants': variants}


def summarize_cases(cases):
    scored = [row for row in cases if row['status'] == 'scored']
    by_gain = {}
    for gain in GAINS_DB:
        by_gain[str(gain)] = {}
        for method in METHODS:
            by_guard = {}
            for ms in GUARDS_MS:
                rows = [trial['results'][method] for case in scored for trial in case['variants']
                        if trial['gain_db'] == gain and trial['guard_ms'] == ms]
                errors = [row['absolute_edge_error_ms'] for row in rows if row['absolute_edge_error_ms'] is not None]
                by_guard[str(ms)] = {'trials': len(rows), 'hits': sum(row['outcome'] == 'hit' for row in rows),
                                     'false_pauses': sum(row['outcome'] == 'false_pause' for row in rows),
                                     'usable_resume_hits': sum(row['outcome'] == 'hit' and row['usable_resume']
                                                               for row in rows),
                                     'tight_edges': sum(row['both_edges_within_tolerance'] is True for row in rows),
                                     'mean_absolute_edge_error_ms': ([sum(values) / len(values)
                                                                     for values in zip(*errors)] if errors else None)}
            by_gain[str(gain)][method] = by_guard
    return {'recordings': len(cases), 'scored_recordings': len(scored), 'by_gain': by_gain}


def run(project, root):
    from src import quantitative_pause_detector

    before = files_to_check(project, root)
    before['strict_detector'] = Path(sys.modules[waveform_reference.__module__].__file__)
    before['relative_detector'] = Path(quantitative_pause_detector.__file__)
    checksums = {label: digest(path) for label, path in before.items()}
    passages, takes, _ = load_cohort(project, root)
    cases = []
    for (pid, voice), take in sorted(takes.items()):
        rate, pcm = read_clip(root, take, SAMPLE_RATE)
        if not isclose(take['duration_s'], len(pcm) / rate, rel_tol=0, abs_tol=1e-6):
            raise ValueError(f"{take['recording_id']}: duration disagrees with the checked WAV")
        cases.append({
            **{key: passages[pid][key] for key in ('work_id', 'author', 'pair_id', 'passage_id', 'period', 'genre')},
            'voice': voice, 'recording_id': take['recording_id'], 'source_audio_sha256': take['audio_sha256'],
            'source_samples': len(pcm), 'sample_rate': rate,
            **evaluate_recording(pcm, rate, quantitative_pause_detector.detect_relative),
        })
    if checksums != {label: digest(path) for label, path in before.items()}:
        raise ValueError('A pinned input or detector changed during the benchmark')
    return {
        'schema_version': 1, 'cohort': root.name, 'source_sha256': checksums,
        'strict_waveform_settings': WAVEFORM_REFERENCE_SETTINGS,
        'relative_pause_settings': quantitative_pause_detector.RELATIVE_PAUSE_SETTINGS,
        'design': {'gain_db': GAINS_DB, 'guard_ms': GUARDS_MS, 'positive_minimum_ms': POSITIVE_MIN_MS,
                   'grid_ms': FRAME_MS, 'flank_ms': FLANK_MS, 'minimum_flank_dbfs': MIN_FLANK_DBFS,
                   'exact_edge_tolerance_ms': EDGE_TOLERANCE_MS},
        'by_voice': {voice: summarize_cases([row for row in cases if row['voice'] == voice]) for voice in ALL_VOICES},
        'by_work': {row['work_id']: summarize_cases([case for case in cases if case['work_id'] == row['work_id']])
                    for row in passages.values()},
        'cases': cases, '音律美': {'evidence': 'held-out controlled waveform pause detection'},
        '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None},
    }


def render(report):
    lines = ['# Held-out waveform pause controls', '',
             'The four exact works and credited authors are disjoint from the earlier detector cohorts. '
             'The same text, seed and synthesis conditions were used in three voices. For each recording, '
             'the benchmark inserts exact digital silence into a fixed, independently chosen energetic site. '
             'Removing the added samples recovers the entire same-gain source. The controls retain the unchanged '
             'recording and a 60 ms guard, below the 100 ms target duration.', '',
             '| Voice | Gain (dB) | Detector | Eligible takes | Hits / positives | Usable resume hits / positives | '
             'Hits with both edges within 20 ms | False pauses / negative sites |',
             '| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |']
    for voice, summary in report['by_voice'].items():
        for gain, methods in summary['by_gain'].items():
            for method, guards in methods.items():
                positive = [row for ms, row in guards.items() if int(ms) >= POSITIVE_MIN_MS]
                negative = [row for ms, row in guards.items() if int(ms) < POSITIVE_MIN_MS]
                total = sum(row['trials'] for row in positive)
                hits = sum(row['hits'] for row in positive)
                resume = sum(row['usable_resume_hits'] for row in positive)
                tight = sum(row['tight_edges'] for row in positive)
                false = sum(row['false_pauses'] for row in negative)
                negatives = sum(row['trials'] for row in negative)
                lines.append(f"| {voice} | {gain} | {method} | {summary['scored_recordings']}/"
                             f"{summary['recordings']} | {hits}/{total} | {resume}/{total} | {tight}/{hits} | "
                             f"{false}/{negatives} |")
    return '\n'.join(lines + ['', 'Counts and edge errors by guard length and work are in the JSON report. '
                                'These controlled acoustic results inform pause timing for 音律美. '
                                'A manufactured gap inside energetic speech carries no clause identity. '
                                '顺口 awaits independent first-read evidence.', ''])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('project', 'root', 'output', 'markdown'):
        parser.add_argument(f'--{key}', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    project, root = args.project.resolve(strict=True), args.root.resolve(strict=True)
    output, markdown = args.output.resolve(), args.markdown.resolve()
    if (output == markdown or output.suffix != '.json' or markdown.suffix != '.md'
            or any(path.exists() or not path.is_relative_to(root / 'results') for path in (output, markdown))):
        parser.error('Choose new JSON and Markdown files inside the isolated experiment results')
    report = run(project, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_output(markdown, render(report))
    write_json(output, report)
    print(json.dumps({voice: summary['scored_recordings'] for voice, summary in report['by_voice'].items()}))


if __name__ == '__main__':
    main()
