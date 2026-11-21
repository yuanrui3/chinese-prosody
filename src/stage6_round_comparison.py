"""Compare overall listening ratings across two shuffled Stage 6 rounds."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from statistics import mean, median

from src.stage6_author_comparison import RESPONSE_DIRECTORY, checked_ratings
from src.stage6_listening import PRIVATE_DIR, STIMULUS_DIR, check_staged, digest, read_json, read_rows, write_json
from src.stage6_production import contained_file


def round_rows(root, response_path):
    path = contained_file(response_path, root / RESPONSE_DIRECTORY)
    if path.stat().st_mode & 0o077 or path.parent.stat().st_mode & 0o077:
        raise ValueError('Listening comparisons require owner-only response access')
    response = read_json(path)
    listening = response['listening']
    key = read_json(root / PRIVATE_DIR / 'unblinding.json')
    survey = check_staged(root / STIMULUS_DIR, key)
    if (listening['survey_id'] != survey['survey_id'] or listening['status'] != 'recorded_overall_pair_ratings'
            or listening.get('pairwise_choices') is not None):
        raise ValueError('Expected overall listening ratings for this exact survey')
    ratings = checked_ratings(listening, 'overall_pair_ratings', [row['trial_id'] for row in survey['trials']])
    annotations = {row['passage_id']: row for row in read_rows(root / 'data/pilot/annotated.jsonl')}
    manifest = {row['recording_id']: row for row in read_rows(root / 'audio/manifests/synthetic.jsonl')}
    rows = {}
    conditions = set()
    for trial in key['trials']:
        texts = []
        ms_per_slot = []
        for side in 'AB':
            member = trial[side]
            source = member['stage4_synthesis']
            if manifest[source['recording_id']] != source:
                raise ValueError('The survey source differs from its synthesis manifest')
            conditions.add((source['speaker'], source['speed']))
            edition = member['text_provenance']
            passage = annotations[edition['passage_id']]
            checksum = hashlib.sha256(passage['text'].encode('utf-8')).hexdigest()
            if (checksum != passage['text_sha256'] or checksum != edition['text_sha256']
                    or checksum != source['text_sha256'] or passage['passage_id'] != source['passage_id']):
                raise ValueError('A clip is disconnected from its exact text witness')
            texts.append((passage['passage_id'], checksum))
            ms_per_slot.append(1000 * member['duration_s'] / len(passage['slots']))
        edit = trial['timing_edit']
        # The voiced samples and absolute boundary time differ with the speaker and speed.
        pause = tuple(edit[field] for field in ('after_slot_index', 'source_anchor', 'method', 'added_ms')) if edit else ()
        design = (trial['comparison'], tuple(sorted(texts)), pause)
        if design in rows:
            raise ValueError('More than one pair represents the same comparison design')
        rows[design] = {'trial_id': trial['trial_id'], 'rating': ratings[trial['trial_id']],
                        'presented_ms_per_slot': mean(ms_per_slot)}
    if len(conditions) != 1 or len(rows) != len(ratings):
        raise ValueError('Each round must use one voice and speed and rate every keyed pair')
    voice, speed = conditions.pop()
    return rows, {'participant_id': response['participant_id'], 'survey_id': survey['survey_id'],
                  'voice': voice, 'nominal_speed': speed, 'presentation': listening.get('presentation'),
                  'response_sha256': digest(path)}


def compare(first, second):
    if not first or set(first) != set(second):
        raise ValueError('The two rounds must contain the same unique pair designs')
    joined = []
    for design, original in first.items():
        followup = second[design]
        joined.append({'comparison': design[0], 'text_witnesses': design[1], 'pause_specification': design[2],
                       'first': original, 'followup': followup,
                       'rating_change': followup['rating'] - original['rating']})
    changes = [row['rating_change'] for row in joined]
    pause_changes = [row['rating_change'] for row in joined if row['pause_specification']]
    summary = {'pairs': len(joined), 'higher': sum(change > 0 for change in changes),
               'lower': sum(change < 0 for change in changes), 'unchanged': changes.count(0),
               'mean_absolute_change': mean(map(abs, changes)),
               'pause_pairs_unchanged': pause_changes.count(0), 'pause_pairs': len(pause_changes)}
    for label, rows in (('first', first), ('followup', second)):
        scores = [row['rating'] for row in rows.values()]
        summary[label] = {'mean': mean(scores), 'median': median(scores), 'range': [min(scores), max(scores)],
                          'mean_presented_ms_per_slot': round(mean(row['presented_ms_per_slot'] for row in rows.values()), 2)}
    return joined, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--first-response', required=True, type=Path)
    parser.add_argument('--followup-root', required=True, type=Path)
    parser.add_argument('--followup-response', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    root, followup_root = args.root.resolve(strict=True), args.followup_root.resolve(strict=True)
    first, first_context = round_rows(root, args.first_response)
    followup, followup_context = round_rows(followup_root, args.followup_response)
    if (first_context['participant_id'] != followup_context['participant_id']
            or first_context['survey_id'] == followup_context['survey_id']):
        raise ValueError('Compare different survey rounds from the same participant')
    joined, summary = compare(first, followup)
    path = args.followup_response.resolve(strict=True)
    write_json(path.with_name(path.stem + '-round-comparison.json'), {
        'first_round': first_context, 'followup_round': followup_context,
        'paired_ratings': joined, 'summary': summary,
    })
    print(json.dumps(summary, allow_nan=False))


if __name__ == '__main__':
    main()
