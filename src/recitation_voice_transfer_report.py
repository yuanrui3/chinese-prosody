"""Evaluate the frozen pause estimator on the original and a second delivery."""

import argparse
from collections import Counter, defaultdict
import json
from math import isclose
from pathlib import Path
from statistics import mean, median

from src.recitation_pause_estimator import absolute_errors, agreement, measure
from src.recitation_pcm_alignment import OUTPUT as PCM_ALIGNMENT
from src.recitation_phrasing import TOTAL_PAUSE_MS
from src.recitation_phrasing_analysis import MANIFEST, ROLES, shuffle_summary
from src.recitation_second_aligner_analysis import (FORCED_ALIGNMENT, OUTPUT as ALIGNER_COMPARISON,
                                                   index_rows)
from src.stage6_listening import digest, read_json, write_json


OUTPUT = MANIFEST.with_name('voice-transfer.json')
FROZEN_DBFS = -50
EXPECTED_PAIRS = 13
EXPECTED_SPLICES = dict(zip(ROLES, ((0, 80, 0), (40, 40, 0))))
EXPECTED_CHANGE = [40, -40, 0]
PAIR_FIELDS = ('passage_id', 'work_id', 'clause_index', 'clause_text', 'slot_indices',
               'characters_in_passage')
SOURCE_FIELDS = ('text_sha256', 'text_revision', 'intended_pinyin', 'intended_model_phonemes',
                 'kind', 'variety', 'style', 'model_revision', 'speed', 'sample_rate', 'seed')


def load_inputs(root):
    paths = {name: root / file for name, file in (
        ('manifest', MANIFEST), ('pcm', PCM_ALIGNMENT), ('forced', FORCED_ALIGNMENT),
        ('comparison', ALIGNER_COMPARISON),
    )}
    hashes = {name: digest(path) for name, path in paths.items()}
    inputs = {name: read_json(path) for name, path in paths.items()}
    comparison = inputs['comparison']
    if (any(inputs[name]['stimuli_sha256'] != hashes['manifest'] for name in ('pcm', 'forced', 'comparison'))
            or comparison['pcm_alignment_sha256'] != hashes['pcm']
            or comparison['forced_alignment_sha256'] != hashes['forced']
            or comparison['model'] != inputs['forced']['model']):
        raise ValueError('The comparison and alignments must describe the same recordings and model')
    inventories = {name: index_rows(item['pairs'], 'pair_id') for name, item in inputs.items()}
    if any(inventory.keys() != inventories['manifest'].keys() for inventory in inventories.values()):
        raise ValueError('All alignment reports must cover the stimulus inventory')
    return hashes, inventories, inputs['forced']['model']


def design(pair):
    """Check and return the common duration of the two treated recordings."""
    source = pair['source']
    sham = pair['sham']
    if source['kind'] != 'synthetic' or source['variety'] != 'cmn' or set(pair['variants']) != set(ROLES):
        raise ValueError('Expected two controlled synthetic Mandarin variants per phrase')
    takes = [pair['variants'][role] for role in ROLES]
    rate = source['sample_rate']
    source_samples = source['sample_count']
    if (any(member[field] != source[field] for member in [sham, *takes]
            for field in (*SOURCE_FIELDS, 'passage_id', 'speaker'))
            or sham['sample_count'] != source_samples
            or takes[0]['sample_count'] != takes[1]['sample_count']
            or not isclose(1000 * (takes[0]['sample_count'] - source_samples) / rate,
                           TOTAL_PAUSE_MS, abs_tol=1000 / rate, rel_tol=0)):
        raise ValueError('Recorded pair differs in text, speaker, delivery condition, or duration')
    return 1000 * takes[0]['sample_count'] / rate


def checked_reference(pair, pcm):
    if any(pair[key] != pcm[key] for key in ('pair_id', 'passage_id', 'work_id', 'clause_text')):
        raise ValueError('Exact PCM reference names a different work or clause')
    if pcm['status'] != 'aligned' or not pcm['supports_pause_distribution']:
        return None
    for role, schedule in EXPECTED_SPLICES.items():
        variant = pcm['variants'][role]
        if (variant['status'] != 'aligned' or not variant['full_carrier_pcm_reconstructed']
                or variant['sample_count'] != pair['variants'][role]['sample_count']
                or tuple(gap['added_ms'] for gap in variant['gaps']) != schedule):
            raise ValueError('Exact PCM check did not verify the declared pause placement')
    values = pcm['split_minus_concentrated_ms']
    if values != EXPECTED_CHANGE:
        raise ValueError('Exact PCM check found a different pause contrast')
    return values


def score(root, pair, forced, pcm, comparison):
    duration = design(pair)
    observations = measure(root, pair, forced)['quiet_ms_by_dbfs']
    reference_ms = checked_reference(pair, pcm)
    baselines = comparison.get('split_minus_concentrated', {})
    if reference_ms is not None and baselines['pcm_pause_changes_ms'] != reference_ms:
        raise ValueError('The secondary aligner report and PCM reference disagree')
    pcm_status = ('unexpected_pause_placement' if pcm['status'] == 'aligned' and reference_ms is None
                  else pcm['status'])
    return {'placement_method': pair.get('placement_method', 'prior_source_draft'),
            'speaker': pair['source']['speaker'], 'treatment_duration_ms': duration,
            'reference_ms': reference_ms, 'pcm_status': pcm_status,
            'frozen_rms_ms': observations[str(FROZEN_DBFS)] if observations is not None else None,
            'funasr_midpoint_ms': baselines.get('model_landmark_spacing_changes_ms'),
            'funasr_span_gap_ms': baselines.get('model_span_gap_changes_ms'),
            'funasr_treatment_status': {role: forced['takes'][role]['status'] for role in ROLES},
            **({'guide_tu_alignment': comparison['guide_tu']} if 'guide_tu' in comparison else {})}


def summarize_voice(rows, condition):
    scores = [{'work_id': row['work_id'], **row[condition]} for row in rows]
    verified = [row for row in scores if row['reference_ms'] is not None]
    by_work = defaultdict(list)
    for row in verified:
        values = row['frozen_rms_ms']
        if values is not None:
            by_work[row['work_id']].append(values[0] - values[1])
    return {'speaker': scores[0]['speaker'], 'pairs_attempted': len(scores),
            'exact_pcm_pairs': len(verified), 'pcm_statuses': dict(Counter(row['pcm_status'] for row in scores)),
            'placement_methods': dict(Counter(row['placement_method'] for row in scores)),
            'aligned_treatment_wavs': sum(status == 'aligned' for row in scores
                                          for status in row['funasr_treatment_status'].values()),
            'frozen_rms_estimated_pairs': sum(row['frozen_rms_ms'] is not None for row in scores),
            'methods_against_pcm': {field: agreement(verified, field) for field in (
                'frozen_rms_ms', 'funasr_midpoint_ms', 'funasr_span_gap_ms',
            )}, 'fixed_threshold_label_swap': shuffle_summary(by_work)}


def paired_summary(rows):
    by_work = defaultdict(list)
    directional = Counter()
    durations = []
    for row in rows:
        old, new = (row[condition] for condition in ('original', 'second'))
        durations.append(new['treatment_duration_ms'] - old['treatment_duration_ms'])
        if any(item['reference_ms'] is None or item['frozen_rms_ms'] is None for item in (old, new)):
            continue
        first, second = (item['frozen_rms_ms'] for item in (old, new))
        old_ok, new_ok = (value[0] > 0 > value[1] for value in (first, second))
        directional[('neither', 'second_only', 'original_only', 'both')[2 * old_ok + new_ok]] += 1
        change = mean(absolute_errors(second, new['reference_ms'])) - mean(absolute_errors(first, old['reference_ms']))
        by_work[row['work_id']].append(change)
    return {'common_measured_pairs': sum(directional.values()), 'common_measured_works': len(by_work),
            'both_edited_directions': {group: directional[group] for group in (
                'both', 'original_only', 'second_only', 'neither',
            )}, 'work_mean_absolute_error_change_second_minus_original_ms': (
                mean(map(mean, by_work.values())) if by_work else None),
            'paired_duration_change_second_minus_original_ms': {'median': median(durations),
                                                                  'range': [min(durations), max(durations)]}}


def analyze(reference, root):
    if reference == root:
        raise ValueError('Choose separate reference and second-voice experiment roots')
    old_hashes, original, old_model = load_inputs(reference)
    new_hashes, second, new_model = load_inputs(root)
    pairs = original['manifest']
    if len(pairs) != EXPECTED_PAIRS or pairs.keys() != second['manifest'].keys():
        raise ValueError(f'Both experiments must include the same {EXPECTED_PAIRS} phrasing pairs')
    if old_model != new_model:
        raise ValueError('Use the same FunASR model and version for both voices')
    voices = [{pair['source']['speaker'] for pair in data['manifest'].values()} for data in (original, second)]
    if any(len(voice) != 1 for voice in voices) or voices[0] == voices[1]:
        raise ValueError('Use one distinct voice in each experiment')

    rows = []
    for key, pair in pairs.items():
        replication = second['manifest'][key]
        if (any(pair[field] != replication[field] for field in PAIR_FIELDS)
                or any(pair['source'][field] != replication['source'][field] for field in SOURCE_FIELDS)):
            raise ValueError(f'{key}: the second voice must use the same written and intended reading condition')
        rows.append({'pair_id': key, 'work_id': pair['work_id'], 'clause_text': pair['clause_text'],
                     **{name: score(base, data['manifest'][key], data['forced'][key], data['pcm'][key],
                                    data['comparison'][key]) for name, base, data in (
                                        ('original', reference, original), ('second', root, second),
                                    )}})
    summary = {'pairs': len(rows), 'works': len({row['work_id'] for row in rows}),
               'threshold_dbfs': FROZEN_DBFS,
               'voices': {name: summarize_voice(rows, name) for name in ('original', 'second')},
               'paired_comparison': paired_summary(rows),
               'guide_tu': next((row for row in rows if row['clause_text'] == '日暮途遠'), None)}
    write_json(root / OUTPUT, {'summary': summary, 'model': new_model, 'input_hashes': {
        'original': old_hashes, 'second': new_hashes}, 'pairs': rows})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    summary = analyze(args.reference.resolve(strict=True), args.root.resolve(strict=True))
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
