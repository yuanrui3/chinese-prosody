"""Test measured Mandarin pauses and articulation against a frozen written editorial proxy."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import groupby
import json
import math
import os
from pathlib import Path
from random import Random
from statistics import fmean, median

import numpy as np

from audio.synthesize import write_rows
from data.phonology.annotate import syllable_slots


VOICES = ('zm_010', 'zf_001')
PENALTY = 10.0
SHUFFLES = 199
SEED = 20261122
MODEL_FEATURES = {'text_recalibrated': (), 'with_pause': ('pause',),
                  'with_pause_duration': ('pause', 'duration')}
PUNCTUATION = {'。': '。', '.': '。', '？': '？', '?': '？', '！': '！', '!': '！',
               '；': '；', ';': '；', '：': '：', ':': '：', '，': '，', ',': '，', '、': '、'}

# Experimental Standard Mandarin prescriptions in the context of these witnesses.
# Original characters and all lexical alternatives are retained in the manifests.
READING_ANCHORS = {
    'foyi': [('為僧琳', '為', 'wei4'), ('不傳之旨', '傳', 'chuan2'), ('佛言不行', '行', 'xing2'),
             ('尼父', '父', 'fu3'), ('達摩', '摩', 'mo2'), ('為醫王', '為', 'wei2'),
             ('行乎', '行', 'xing2'), ('為貴', '為', 'wei2'), ('為寶', '為', 'wei2'),
             ('既還', '還', 'huan2'), ('便門', '便', 'bian4'), ('傳衣', '傳', 'chuan2'),
             ('傳豈', '傳', 'chuan2')],
    'lizhi': [('華如橘', '華', 'hua1'), ('愨如紅', '愨', 'que4'), ('紅繒', '繒', 'zeng1'),
              ('南賓守', '守', 'shou3'), ('樂天', '樂', 'le4'), ('蓋為不識者', '為', 'wei4')],
}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.partial')
    pending.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    pending.replace(path)


def key(row):
    return row['work_id'], row['id']


def identity(work_id, line_id):
    return sha256(json.dumps([work_id, line_id], ensure_ascii=False).encode()).hexdigest()[:20]


def prepare(witness, output):
    from pypinyin import Style, lazy_pinyin, pinyin

    records, prescriptions, inputs = [], {}, {}
    for item in load(witness):
        wid, lid = key(item)
        pid = identity(wid, lid)
        if pid in inputs:
            raise ValueError(f'Duplicate work and line {wid}/{lid}')
        text = item['text']
        slots = syllable_slots(text)
        overrides = dict(item.get('audio_readings', {}))
        for anchor, char, reading in READING_ANCHORS.get(wid, []):
            if anchor in text:
                if text.count(anchor) != 1 or anchor.count(char) != 1:
                    raise ValueError(f'Ambiguous reading anchor {anchor!r}')
                offset = text.index(anchor) + anchor.index(char)
                index = next(s['slot_index'] for s in slots if s['offset'] == offset)
                overrides.setdefault(str(index), {'char': char, 'reading': reading, 'anchor': anchor})
        clauses, review = [], []
        clause = 0
        for slot in slots:
            slot['clause_index'] = clause
            marks = slot['marks_after']
            mark = next((PUNCTUATION[char] for char in marks if char in PUNCTUATION), '')
            if '\n' in marks and not mark:
                mark = '。'
            slot['marks_after'] = mark
            slot['boundary_after'] = int(bool(mark))
            clause += int(bool(mark))
        for _, clause_group in groupby(slots, key=lambda slot: slot['clause_index']):
            group = list(clause_group)
            han = ''.join(slot['char'] for slot in group)
            chosen = lazy_pinyin(han, style=Style.TONE3, neutral_tone_with_five=True,
                                 errors=lambda chars: list(chars))
            if len(chosen) != len(group):
                raise ValueError(f'{wid}/{lid}: pinyin count does not match characters')
            for i, slot in enumerate(group):
                char, ordinal = slot['char'], slot['slot_index']
                options = pinyin(char, style=Style.TONE3, heteronym=True, neutral_tone_with_five=True)[0]
                override = overrides.get(str(ordinal))
                if override:
                    if override['char'] != char:
                        raise ValueError(f'{wid}/{lid}: stale reading override at {ordinal}')
                    chosen[i] = override['reading']
                slot['readings'] = {'mandarin': {'selected': None,
                                                'candidates': [{'reading': value} for value in options]}}
                if len(options) > 1 or override:
                    review.append({'ordinal': ordinal, 'char': char, 'candidates': options,
                                   'synthesis_input': chosen[i], 'override': override})
            clauses.append(' '.join(chosen))
        hash_text = sha256(text.encode()).hexdigest()
        source_url = item['source_url']
        records.append({'passage_id': pid, 'text': text, 'text_sha256': hash_text,
                        'revision_id': item.get('revision_id', source_url), 'source_url': source_url,
                        'license': item['rights'], 'slots': slots, 'work_id': wid})
        prescriptions[pid] = {'text_sha256': hash_text, 'clauses': clauses}
        inputs[pid] = {'work_id': wid, 'id': lid, 'text': text, 'text_sha256': hash_text,
                       'candidate_junctions': [s['slot_index'] + 1 for s in slots[:-1] if s['boundary_after']],
                       'char_count': len(slots), 'genre': item['genre'], 'pronunciation_choices': review}
    if len({r['work_id'] for r in records}) < 2:
        raise ValueError('Work-held-out analysis requires at least two fresh works')
    write_rows(output / 'data/pilot/annotated.jsonl', records)
    dump(output / 'readings.json', prescriptions)
    dump(output / 'design.json', inputs)


def measure(project, output):
    from audio.align import MODEL_REVISION, VOCAB_REVISION, MandarinDecoder
    from src.quantitative_preboundary_features import extract

    design = load(output / 'design.json')
    manifest = output / 'audio/manifests/synthetic.jsonl'
    recordings = [json.loads(line) for line in manifest.read_text().splitlines() if line]
    index = {(rec['passage_id'], rec['speaker']): rec for rec in recordings}
    if (len(index) != len(recordings) or set(index) != {(pid, v) for pid in design for v in VOICES}):
        raise ValueError('Render every line in both synthetic voices exactly once')
    decoder = MandarinDecoder(project, offline=True)
    details = {}
    for pid, target in design.items():
        controls = sorted(set(range(1, target['char_count'])) - set(target['candidate_junctions']))
        takes = [index[pid, voice] for voice in VOICES]
        for field in ('speed', 'seed', 'text_sha256', 'text_revision', 'intended_pinyin', 'intended_model_phonemes'):
            if takes[0][field] != takes[1][field]:
                raise ValueError(f'Voice pair differs in {field}')
        if (takes[0]['text_sha256'] != target['text_sha256'] or takes[0]['audio_sha256'] == takes[1]['audio_sha256']):
            raise ValueError('Incorrect witness or duplicate waveform')
        info = {'work_id': target['work_id'], 'id': target['id'], 'candidate_junctions': target['candidate_junctions'],
                'text_sha256': target['text_sha256'], 'voices': {}}
        for take in takes:
            measure_info = {'wav_sha256': take['audio_sha256'], 'junctions': []}
            if target['candidate_junctions'] and controls:
                record = {'id': pid, 'path': take['audio_path'], 'wav_sha256': take['audio_sha256'],
                          'transcript': target['text'], 'recording_id': take['recording_id'],
                          'speaker': take['speaker'], 'work': target['work_id'], 'genre': target['genre'],
                          'boundaries': target['candidate_junctions'], 'controls': controls[:1]}
                sites, audit = extract(record, output, decoder, rescue_mode='baseline')
                measure_info.update(junctions=[s for s in sites if s['label']],
                                    detector_status=audit['detector_status'],
                                    aligned_characters=len(audit['aligned']), total_characters=target['char_count'])
            info['voices'][take['speaker']] = measure_info
        details[pid] = info
    report = {'charsiu_model_revision': MODEL_REVISION, 'charsiu_vocab_revision': VOCAB_REVISION,
              'synthetic_manifest_sha256': sha256(manifest.read_bytes()).hexdigest(), 'lines': details}
    dump(output / 'acoustics.json', report)


def common_sites(info):
    eligible = {}
    for voice, recording in info['voices'].items():
        eligible[voice] = {s['ordinal']: s for s in recording['junctions'] if s['exclusion'] is None
                           and s['pause_ms'] is not None and s['pre_duration_s'] and s['context_duration_s']}
    common = sorted(set.intersection(*(set(eligible[v]) for v in VOICES)))
    if not common:
        return common, {}
    feats = {}
    for voice in VOICES:
        sites = [eligible[voice][i] for i in common]
        feats[voice] = {'pause': median(math.log1p(s['pause_ms']) for s in sites),
                        'duration': median(math.log(s['pre_duration_s'] / s['context_duration_s']) for s in sites)}
    return common, feats


def fit_delta(train, features):
    residuals = [row['label'] - row['context_score'] for row in train]
    center = fmean(residuals)
    if not features:
        return lambda row: center
    x = np.array([[row[f] for f in features] for row in train])
    means, stds = x.mean(axis=0), x.std(axis=0)
    scales = np.where(stds > 1e-10, stds, 1.)
    z = (x - means) / scales
    weights = np.linalg.solve(z.T @ z + PENALTY * np.eye(len(features)), z.T @ (np.array(residuals) - center))
    return lambda row: center + float(((np.array([row[f] for f in features]) - means) / scales) @ weights)


def paired_rows(acoustics, context, exclude):
    context_index = {key(row): row for row in context['rows']}
    if len(context_index) != len(context['rows']) or set(context_index) != {key(r) for r in acoustics['lines'].values()}:
        raise ValueError('Mismatched text and acoustic line inventories')
    rows, coverage = [], {}
    for info in acoustics['lines'].values():
        work, line = key(info)
        if (work, line) in exclude:
            continue
        target = context_index[work, line]
        if sha256(target['text'].encode()).hexdigest() != info['text_sha256']:
            raise ValueError(f'Text differs for {work}/{line}')
        label = target.get('editorial_score')
        if label is not None and (type(label) is not int or not 1 <= label <= 7):
            raise ValueError(f'Invalid editorial score {label}')
        common, features = common_sites(info)
        counts = coverage.setdefault(work, Counter())
        counts['input_lines'] += 1
        counts['editorially_scored_lines'] += int(label is not None)
        counts['candidate_junctions'] += len(info['candidate_junctions'])
        counts['shared_usable_junctions'] += len(common)
        counts['shared_usable_lines'] += int(bool(common))
        for voice in VOICES:
            counts[voice + '_usable_junctions'] += sum(s['exclusion'] is None and s['context_duration_s'] is not None
                                                     for s in info['voices'][voice]['junctions'])
        if label is None or not features:
            continue
        for voice in VOICES:
            rows.append({'work_id': work, 'id': line, 'voice': voice, 'label': label,
                         'context_score': float(target['predictions']['context']['raw']),
                         'shared_ordinals': common, **features[voice]})
    return rows, coverage


def fit_folds(rows, works):
    folds, predictions = [], []
    for work in sorted(works):
        for voice in VOICES:
            train = [r for r in rows if r['work_id'] != work and r['voice'] != voice]
            test = [r for r in rows if r['work_id'] == work and r['voice'] == voice]
            fold = {'work_id': work, 'test_voice': voice, 'training_works': sorted({r['work_id'] for r in train}),
                    'train_lines': len(train), 'test_lines': len(test)}
            folds.append(fold)
            if len(train) < 3 or not test:
                fold['status'] = 'insufficient_shared_rows'
                continue
            fold['status'] = 'evaluated'
            corrections = {name: fit_delta(train, features) for name, features in MODEL_FEATURES.items()}
            for r in test:
                forecast = {'frozen_text': r['context_score'],
                            **{k: r['context_score'] + fn(r) for k, fn in corrections.items()}}
                predictions.append({**r, 'forecast': forecast})
            these = predictions[-len(test):]
            fold['mae'] = {model: fmean(abs(r['forecast'][model] - r['label']) for r in these)
                           for model in ('frozen_text', *MODEL_FEATURES)}
    evaluable = [fold for fold in folds if fold['status'] == 'evaluated']
    macro = {model: fmean(fold['mae'][model] for fold in evaluable) for model in ('frozen_text', *MODEL_FEATURES)
             } if evaluable else {}
    return folds, macro, predictions


def shuffle_acoustics(rows, rng):
    by_work = defaultdict(dict)
    for row in rows:
        by_work[row['work_id']].setdefault(row['id'], {})[row['voice']] = row
    shuffled = []
    for work in sorted(by_work):
        units = by_work[work]
        ids = sorted(units)
        donors = ids.copy()
        rng.shuffle(donors)
        for target, donor in zip(ids, donors):
            for voice in VOICES:
                vector = units[donor][voice]
                shuffled.append({**units[target][voice], 'pause': vector['pause'], 'duration': vector['duration']})
    return shuffled


def gains(mae):
    return {'pause_over_text': mae['text_recalibrated'] - mae['with_pause'],
            'duration_over_pause': mae['with_pause'] - mae['with_pause_duration'],
            'both_over_text': mae['text_recalibrated'] - mae['with_pause_duration']}


def shuffle_control(rows, works, macro, draws):
    if not macro or not draws:
        return None
    observed = gains(macro)
    rng = Random(SEED)
    null = {contrast: [] for contrast in observed}
    for _ in range(draws):
        _, estimates, _ = fit_folds(shuffle_acoustics(rows, rng), works)
        for contrast, gain in gains(estimates).items():
            null[contrast].append(gain)
    result = {}
    for contrast, actual in observed.items():
        sampled = null[contrast]
        result[contrast] = {'observed_gain_mae': actual, 'shuffled_gain_median': median(sampled),
                            'shuffled_gain_p025_p975': np.quantile(sampled, [.025, .975]).tolist(),
                            'upper_tail_fraction_plus_one': (1 + sum(x >= actual - 1e-12 for x in sampled)) /
                                                            (1 + draws)}
    return {'seed': SEED, 'draws': draws,
            'design': 'Within each work, jointly move both voices and both acoustic features between eligible '
                      'lines. Freeze labels, text scores, eligible rows and work/voice splits. Refit each fold '
                      'for each draw. Positive gain means smaller MAE.', 'contrasts': result}


def evaluate(acoustics, context, *, exclude=(), draws=SHUFFLES):
    rows, coverage = paired_rows(acoustics, context, exclude)
    folds, macro, predictions = fit_folds(rows, coverage)
    return {'outcome': 'Written GPT editorial proxy (1–7), same target in both voices.',
            '顺口': {'status': 'requires independent first-read production'}, 'coverage': coverage,
            'definition': 'Each line is a separate clip. The end of the clip and cross-line timing are excluded. '
                          'At internal punctuation only, take median log(1 + pause ms) and median log(final '
                          'syllable duration / local median). Both voices must support the identical junction(s).',
            'validation': 'Fixed unrounded context model plus residual ridge, penalty 10. Hold out entire work '
                          'and voice simultaneously. All recalibrated models use the same rows and intercept. '
                          'Macro MAE gives each evaluated work–voice fold equal weight.',
            'folds': folds, 'macro_mae': macro, 'predictions': predictions,
            'within_work_audio_shuffle': shuffle_control(rows, coverage, macro, draws)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=('prepare', 'measure', 'evaluate'))
    for arg in ('project', 'output'):
        parser.add_argument('--' + arg, type=Path, required=True)
    parser.add_argument('--witness', type=Path)
    parser.add_argument('--context', type=Path)
    args = parser.parse_args()
    project, output = args.project.resolve(strict=True), args.output.resolve(strict=True)
    if not output.is_relative_to(project) or output == project:
        parser.error('Keep the experiment inside the Gilbreth project')
    if args.step == 'prepare':
        prepare(args.witness, output)
    elif args.step == 'measure':
        if not os.environ.get('SLURM_JOB_ID'):
            parser.error('Use a Gilbreth Slurm GPU allocation for waveform analysis')
        measure(project, output)
    else:
        measured, context = load(output / 'acoustics.json'), load(args.context)
        results = evaluate(measured, context)
        uncertain = {key(r) for r in context['rows'] if '愨如紅' in r['text']}
        if uncertain:
            sensitivity = evaluate(measured, context, exclude=uncertain, draws=0)
            results['literal_愨_sensitivity'] = {'excluded': sorted(uncertain), 'macro_mae': sensitivity['macro_mae'],
                                               'folds': sensitivity['folds']}
        results['context_sha256'] = sha256(args.context.read_bytes()).hexdigest()
        dump(output / 'audio-increment.json', results)
        print(json.dumps({k: results[k] for k in ('coverage', 'macro_mae', 'folds', 'within_work_audio_shuffle')}))


if __name__ == '__main__':
    main()
