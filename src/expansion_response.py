"""Compare the independent-work author ratings with text and waveform measures."""

import argparse
from collections import defaultdict
import json
from math import isclose
import os
from pathlib import Path
from statistics import mean
import wave

from src.audio_validation import acoustic_observations, load_inputs, read_jsonl
from src.expansion_tasks import PILOT, matched_pairs
from src.stage6_author_comparison import RESPONSE_DIRECTORY, TEXT_FIELDS, checked_ratings
from src.stage6_listening import PRIVATE_DIR, STIMULUS_DIR, digest, read_clip, read_json, write_json
from src.stage6_production import VERSION, contained_file, production_stimuli
from src.stage6_round_comparison import round_rows
from src.stage6_survey_page import clip_texts, listening_page
from src.text_metrics import text_metric_support


SOURCE_AUDIO = {
    'clause_mean_slots': 'source_clause_articulation_ms',
    'clause_end_pz_alternation': 'source_clause_end_pitch_difference_st',
    'clause_end_rhyme_repeat': 'source_clause_end_final_repeat',
}


def text_measures(passage):
    estimates = text_metric_support(passage, 'guangyun')
    return {field: estimates[field] for field in TEXT_FIELDS}


def mean_if_complete(values):
    values = list(values)
    return mean(values) if values and all(value is not None for value in values) else None


def listening_side(root, folder, filename, member, passage, take, syllables, gaps):
    source = member['stage4_synthesis']
    source_rate, samples = read_clip(root, source, source['sample_rate'])
    with wave.open(str(folder / filename), 'rb') as clip:
        presented_duration = clip.getnframes() / clip.getframerate()
    if any(not isclose(duration, presented_duration, abs_tol=1e-6) for duration in
           (member['duration_s'], take['waveform_duration_s'], len(samples) / source_rate)):
        raise ValueError('Presented and source waveform timing disagree')
    slots = len(passage['slots'])
    if take['slots_expected'] != slots:
        raise ValueError('Acoustic slot inventory differs from the text')
    observed = acoustic_observations(passage, take, syllables, gaps)
    audio = {}
    for field, name in SOURCE_AUDIO.items():
        same_positions, value, usable = observed.get(field, (None, None, 0))
        audio[name] = {'value': value, 'matched_text_value': same_positions, 'usable': usable}
    return {'passage_id': passage['passage_id'], 'recording_id': source['recording_id'],
            'written_slots': slots, 'aligned_slots': take['slots_measured'],
            'text': text_measures(passage), 'source_audio': audio,
            'presented_duration_s': presented_duration, 'presented_ms_per_slot': 1000 * presented_duration / slots}


def listening_trials(root, path, record, expected, inputs):
    _, condition = round_rows(root, path)
    passages, clips, takes, gaps, syllables = inputs
    indexed = {row['recording_id']: row for row in takes}
    folder = root / STIMULUS_DIR
    survey = read_json(folder / 'survey.json')
    key = read_json(root / PRIVATE_DIR / 'unblinding.json')
    page = root / 'audio/stage6/listening-web/with-text.html'
    if (record['presentation'] != 'text_supported' or digest(page) != record['page_sha256']
            or listening_page(survey, folder, overall=True, transcripts=clip_texts(root, folder, survey))
            != page.read_text(encoding='utf-8')):
        raise ValueError('The presented transcript and waveform page differ from the recorded condition')
    expected_pairs = {frozenset(row['passage_id'] for row in pair) for pair in expected}
    seen = set()
    rows = []
    for blind, trial in zip(survey['trials'], key['trials']):
        if trial['comparison'] != 'period_matched_prose' or trial['timing_edit'] or trial['wording_edit']:
            raise ValueError('Expected an unedited period-matched comparison')
        sides = []
        for side in 'AB':
            member = trial[side]
            recording_id = member['stage4_synthesis']['recording_id']
            passage = passages[clips[recording_id]['passage_id']]
            sides.append(listening_side(root, folder, blind[side], member, passage,
                                        indexed[recording_id], syllables[recording_id], gaps[recording_id]))
        pair = frozenset(side['passage_id'] for side in sides)
        if pair not in expected_pairs or pair in seen:
            raise ValueError('Listening members disagree with the assigned matched pairs')
        seen.add(pair)
        metrics = {field: mean_if_complete(side['text'][field]['value'] for side in sides)
                   for field in TEXT_FIELDS}
        metrics.update({field: mean_if_complete(side['source_audio'][field]['value'] for side in sides)
                        for field in SOURCE_AUDIO.values()})
        metrics.update(presented_ms_per_slot=mean(side['presented_ms_per_slot'] for side in sides),
                       absolute_clip_duration_difference_ms=1000 * abs(
                           sides[0]['presented_duration_s'] - sides[1]['presented_duration_s']),
                       pooled_slots_per_clause=sum(side['written_slots'] for side in sides) /
                       sum(side['text']['clause_mean_slots']['usable'] for side in sides),
                       pooled_46_share=sum(side['text']['clause_46_share']['value'] *
                                           side['text']['clause_46_share']['usable'] for side in sides) /
                       sum(side['text']['clause_46_share']['usable'] for side in sides))
        support = {field: sum(side['text'][field]['usable'] for side in sides) for field in TEXT_FIELDS}
        support.update({field: sum(side['source_audio'][field]['usable'] for side in sides)
                        for field in SOURCE_AUDIO.values()})
        rows.append({'trial_id': trial['trial_id'], 'rating': record['overall_pair_ratings'][trial['trial_id']],
                     'sides': sides, 'metrics': metrics, 'usable': support})
    if seen != expected_pairs or len(rows) != len(expected_pairs):
        raise ValueError('Expected every assigned listening pair exactly once')
    return rows, condition


def read_aloud_rows(root, record):
    task_path = root / 'audio/stage6/production/task.json'
    task = read_json(task_path)
    prompts = production_stimuli(root)
    if (record['protocol'] != VERSION or task['version'] != VERSION or record['recording_supplied'] is not False
            or digest(task_path) != record['task_sha256']
            or {row['code']: row['text'] for row in task['prompts']} !=
            {code: row['text'] for code, row in prompts.items()}):
        raise ValueError('Expected the exact first-read task with ratings only')
    ratings = checked_ratings(record, 'ratings', prompts)
    return [{'code': code, 'passage_id': row['passage_id'], 'pair_id': row['pair_id'], 'period': row['period'],
             'rating': ratings[code], 'written_slots': len(row['slots']), 'text': text_measures(row)}
            for code, row in prompts.items()]


def summarize(listening, production):
    bands, matches = defaultdict(list), defaultdict(list)
    for row in listening:
        bands[row['rating']].append(row)
    for row in production:
        matches[row['pair_id']].append(row)
    acoustic_text = []
    for group in bands.values():
        acoustic_text.append({'pairs': len(group),
                              'metrics': {field: mean_if_complete(row['metrics'][field] for row in group)
                                          for field in group[0]['metrics']},
                              'usable': {field: sum(row['usable'][field] for row in group)
                                         for field in group[0]['usable']},
                              'alignment': [sum(side[field] for row in group for side in row['sides'])
                                            for field in ('aligned_slots', 'written_slots')]})
    contrasts = []
    for group in matches.values():
        lower, higher = sorted(group, key=lambda row: row['rating'])
        contrasts.append({'period': lower['period'], 'tie': lower['rating'] == higher['rating'],
                          'values_lower_then_higher': {
                              'written_slots': [lower['written_slots'], higher['written_slots']],
                              **{field: [lower['text'][field], higher['text'][field]] for field in TEXT_FIELDS}}})
    return {'listening': {'rating_bands_low_to_high': acoustic_text, 'presentation': 'text_supported'},
            'read_aloud': {'ratings': len(production), 'recordings': 0, 'matched': contrasts}}


def run(root, response_path):
    path = contained_file(response_path, root / RESPONSE_DIRECTORY)
    if path.stat().st_mode & 0o077 or path.parent.stat().st_mode & 0o077:
        raise ValueError('Expanded pilot responses require owner-only access')
    response = read_json(path)
    if response['study'] != 'independent-prose-expansion':
        raise ValueError('Expected the independent prose expansion response')
    assigned = matched_pairs(root / PILOT)
    inputs = load_inputs(root, read_jsonl(root / PILOT))
    listening, condition = listening_trials(root, path, response['listening'], assigned['listening'], inputs)
    production = read_aloud_rows(root, response['read_aloud'])
    listening.sort(key=lambda row: row['rating'])
    summary = summarize(listening, production)
    output = path.with_name(path.stem + '-comparison.json')
    write_json(output, {'response_sha256': condition['response_sha256'], 'listening': listening,
                        'read_aloud': production, 'summary': summary})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--response', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(run(args.root.resolve(strict=True), args.response), ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
