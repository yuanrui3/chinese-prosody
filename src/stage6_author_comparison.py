"""Compare an author's Stage 6 ratings with edition-linked pilot measures."""

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
from statistics import mean, median

from src.audio_validation import acoustic_observations, load_inputs, rank_association, read_jsonl
from src.stage6_listening import PRIVATE_DIR, STIMULUS_DIR, check_staged, digest, read_json, write_json
from src.stage6_production import VERSION, contained_file, restricted_path, stage6_path
from src.stage6_proxies import proxy_row
from src.text_metrics import text_metrics


RESPONSE_DIRECTORY = Path('results/stage6/responses')
TEXT_FIELDS = ('clause_mean_slots', 'clause_46_share', 'clause_end_pz_alternation', 'clause_end_rhyme_repeat')
PRODUCTION_FIELDS = ('written_slots', *TEXT_FIELDS, 'synthetic_ms_per_slot', 'synthetic_draft_edits_per_100_slots')


def checked_ratings(record, field, codes):
    ratings = record[field]
    if (record['scale'] != [1, 7] or set(ratings) != set(codes)
            or any(type(value) is not int or not 1 <= value <= 7 for value in ratings.values())):
        raise ValueError('Expected one 1–7 rating for each exact survey item')
    return ratings


def text_row(passage):
    if hashlib.sha256(passage['text'].encode('utf-8')).hexdigest() != passage['text_sha256']:
        raise ValueError('Passage differs from its pinned text hash')
    metrics = text_metrics(passage, tier='guangyun')
    return {'written_slots': len(passage['slots']), **{key: metrics[key] for key in TEXT_FIELDS}}


def listening_rows(root, response, passages, clips, takes, gaps, syllables):
    key = read_json(root / PRIVATE_DIR / 'unblinding.json')
    survey = check_staged(root / STIMULUS_DIR, key)
    if (response['survey_id'] != survey['survey_id'] or response['status'] != 'recorded_overall_pair_ratings'
            or response['reported_numbers'] != response['overall_pair_ratings']):
        raise ValueError('Listening response is linked to the wrong survey or response scale')
    ratings = checked_ratings(response, 'overall_pair_ratings', [row['trial_id'] for row in survey['trials']])
    audit = read_json(root / 'results/stage6/pause-audit.json')
    audits = {pair['pair_id']: pair for pair in audit['pairs']}
    rows = []
    for trial in key['trials']:
        sides = []
        for side in ('A', 'B'):
            member = trial[side]
            source = member['stage4_synthesis']
            identifier = source['recording_id']
            passage = passages[source['passage_id']]
            if clips[identifier] != source or member['text_provenance']['text_sha256'] != passage['text_sha256']:
                raise ValueError('Listening input has a stale edition or synthetic-source link')
            acoustic = acoustic_observations(passage, takes[identifier], syllables[identifier], gaps[identifier])
            _, pitch, pitch_positions = acoustic.get('clause_end_pz_alternation', (None, None, 0))
            sides.append({
                **text_row(passage), 'passage_id': passage['passage_id'], 'recording_id': identifier,
                'clip_duration_s': member['duration_s'], 'source_clause_end_pitch_difference_st': pitch,
                'source_pitch_positions': pitch_positions,
                'presented_ms_per_slot': 1000 * member['duration_s'] / len(passage['slots']),
            })
        pair_metrics = {}
        for field in (*TEXT_FIELDS, 'presented_ms_per_slot', 'source_clause_end_pitch_difference_st'):
            values = [side[field] for side in sides]
            pair_metrics[field] = mean(values) if all(value is not None for value in values) else None
        pair_metrics['absolute_clip_duration_difference_ms'] = 1000 * abs(
            sides[0]['clip_duration_s'] - sides[1]['clip_duration_s']
        )
        pause = None
        if trial['timing_edit']:
            item = audits[trial['comparison_id']]
            if item['status'] != 'measured' or item['passage_id'] != sides[0]['passage_id']:
                raise ValueError('Timing pair lacks its verified acoustic audit')
            pause = {field: item[field] for field in ('expected_extension_ms', 'draft_gap_extension_ms')}
        rows.append({'trial_id': trial['trial_id'], 'rating': ratings[trial['trial_id']],
                     'comparison': trial['comparison'], 'sides': sides, 'metrics': pair_metrics, 'pause': pause})
    return rows


def production_rows(root, response, passages, takes, gaps, syllables):
    task = read_json(stage6_path(root) / 'production/task.json')
    key = read_json(restricted_path(root) / 'production-key.json')
    prompts = {row['code']: row['text'] for row in task['prompts']}
    if (response['protocol'] != VERSION or task['version'] != VERSION or key['version'] != VERSION
            or set(prompts) != set(key['prompts']) or response['recording_supplied'] is not False):
        raise ValueError('Expected the exact Stage 6 rating-only read-aloud task')
    ratings = checked_ratings(response, 'ratings', prompts)
    takes_by_passage = defaultdict(list)
    for take in takes.values():
        takes_by_passage[take['passage_id']].append(take)
    rows = []
    for code, text in prompts.items():
        source = key['prompts'][code]
        identifier = source['passage_id']
        passage = passages[identifier]
        if text != passage['text'] or any(passage[field] != value for field, value in source.items()):
            raise ValueError('Read-aloud input has a stale edition link')
        conditions = takes_by_passage[identifier]
        if len(conditions) != 6 or len({take['condition'] for take in conditions}) != 6:
            raise ValueError('Expected all six synthetic controls for each read-aloud text')
        proxy_rows = [proxy_row(take, syllables[take['recording_id']], gaps[take['recording_id']], passage)
                      for take in conditions]
        metrics = {**text_row(passage),
                   'synthetic_ms_per_slot': 1000 * median(row['waveform_seconds_per_written_slot'] for row in proxy_rows),
                   'synthetic_draft_edits_per_100_slots': 100 * median(row['draft_discrepancy'] for row in proxy_rows)}
        rows.append({'prompt_code': code, 'passage_id': identifier, 'period': passage['period'],
                     'pair_id': passage['pair_id'], 'rating': ratings[code], 'metrics': metrics})
    return rows


def means(rows):
    metrics = {}
    for field in rows[0]['metrics']:
        values = [row['metrics'][field] for row in rows if row['metrics'][field] is not None]
        metrics[field] = [round(mean(values), 4) if values else None, len(values)]
    return metrics


def matched_contrasts(rows):
    strata = defaultdict(list)
    for row in rows:
        strata[row['pair_id']].append(row)
    result = []
    for group in strata.values():
        if len(group) != 2 or group[0]['period'] != group[1]['period']:
            raise ValueError('Expected a period-matched read-aloud comparison')
        low, high = sorted(group, key=lambda row: row['rating'])
        result.append({'period': low['period'], 'ease_difference': high['rating'] - low['rating'],
                       'measures': {field: [round(row['metrics'][field], 4) if row['metrics'][field] is not None
                                            else None for row in (low, high)] for field in PRODUCTION_FIELDS}})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--response', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve(strict=True)
    path = contained_file(args.response, root / RESPONSE_DIRECTORY)
    if path.stat().st_mode & 0o077 or path.parent.stat().st_mode & 0o077:
        raise ValueError('The response and analysis require owner-only access')
    response = read_json(path)
    passages, clips, takes, gaps, syllables = load_inputs(root, read_jsonl(root / 'data/pilot/annotated.jsonl'))
    take_index = {row['recording_id']: row for row in takes}
    listening = listening_rows(root, response['listening'], passages, clips, take_index, gaps, syllables)
    production = production_rows(root, response['read_aloud'], passages, take_index, gaps, syllables)
    levels = sorted({row['rating'] for row in listening})
    labels = (['lower', *(f'band_{index + 1}' for index in range(1, len(levels) - 1)), 'higher']
              if len(levels) > 1 else ['all'])
    groups = {label: [row for row in listening if row['rating'] == rating]
              for label, rating in zip(labels, levels)}
    listening_summary = {label: {'pairs': len(rows), 'means_and_support': means(rows),
                                 'conditions': [row['comparison'] for row in rows]}
                         for label, rows in groups.items()}
    listening_summary['pause_audit_ms'] = next(row['pause'] for row in listening if row['pause'] is not None)
    associations = {}
    for field in PRODUCTION_FIELDS:
        points = [{'rating': row['rating'], 'metric': row['metrics'][field]} for row in production
                  if row['metrics'][field] is not None]
        result = rank_association(points, 'rating', 'metric')
        associations[field] = {**result, 'rho': round(result['rho'], 4) if result['rho'] is not None else None}
    summary = {'listening': listening_summary, 'read_aloud': {'matched': matched_contrasts(production),
                                                           'descriptive_spearman': associations}}
    output = path.with_name(path.stem + '-comparison.json')
    write_json(output, {'response_sha256': digest(path), 'listening_pairs': listening,
                        'read_aloud_passages': production, 'summary': summary})
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
