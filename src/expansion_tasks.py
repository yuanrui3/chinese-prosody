"""Stage the listening and first-read materials for the independent-work pilot."""

import argparse
from collections import Counter, defaultdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import secrets
from tempfile import NamedTemporaryFile, TemporaryDirectory

from src.stage6_listening import (
    PRIVATE_DIR, STIMULUS_DIR, check_staged, make_trial, read_json, read_rows, write_json,
)
from src.stage6_production import VERSION, private_directory, read_aloud_page
from src.stage6_survey_page import listening_page


PILOT = Path('data/pilot/annotated.jsonl')
SYNTHETIC = Path('audio/manifests/synthetic.jsonl')
TASKS = ('listening', 'read_aloud')
GENRES = {'parallel_prose', 'comparison_prose'}
SEED = 20261121


def matched_pairs(path):
    rows = read_rows(path)
    if len(rows) != 8 or {row.get('task') for row in rows} != set(TASKS):
        raise ValueError('Expected eight passages assigned to the two expansion tasks')
    for field in ('passage_id', 'work_id', 'author', 'text_sha256'):
        values = {row[field] for row in rows}
        if len(values) != len(rows) or any(not value for value in values):
            raise ValueError(f'Expansion excerpts must have distinct nonempty {field} values')

    groups = defaultdict(list)
    for row in rows:
        checksum = hashlib.sha256(row['text'].encode('utf-8')).hexdigest()
        if checksum != row['text_sha256']:
            raise ValueError(f"{row['passage_id']}: pinned text differs from its checksum")
        if not row['pair_id'] or not row['period']:
            raise ValueError(f"{row['passage_id']}: pair and period are required")
        groups[row['pair_id']].append(row)

    tasks = {task: [] for task in TASKS}
    for pair_id, group in sorted(groups.items()):
        if (len(group) != 2 or {row['genre'] for row in group} != GENRES
                or len({row['period'] for row in group}) != 1
                or len({row['task'] for row in group}) != 1):
            raise ValueError(f'{pair_id}: expected one period-matched pair in a single task')
        tasks[group[0]['task']].append(sorted(group, key=lambda row: row['passage_id']))

    if any(len(pairs) != 2 for pairs in tasks.values()):
        raise ValueError('Expected two matched pairs per task')
    periods = [Counter(pair[0]['period'] for pair in tasks[task]) for task in TASKS]
    if periods[0] != periods[1]:
        raise ValueError('The two tasks must have the same period balance')
    return tasks


def write_page(path, html):
    with NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as stream:
        staged = Path(stream.name)
        try:
            stream.write(html)
            stream.close()
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)


def prepare_read_aloud(root, pairs, seed):
    rows = [row for pair in pairs for row in pair]
    random.Random(seed).shuffle(rows)
    metadata_fields = ('passage_id', 'work_id', 'title', 'author', 'pair_id', 'genre',
                       'period', 'match_topic', 'source_url', 'revision_id', 'text_sha256',
                       'work_rights', 'license', 'attribution')
    prompts = [{'code': f'R{number:02d}', 'text': row['text']} for number, row in enumerate(rows, 1)]
    key = {'version': VERSION, 'prompts': {
        prompt['code']: {field: row[field] for field in metadata_fields if field in row}
        for prompt, row in zip(prompts, rows)
    }}
    restricted = private_directory(root, 'audio', 'stage6', 'restricted')
    key_path = restricted / 'production-key.json'
    if key_path.exists() and read_json(key_path) != key:
        raise ValueError('The saved read-aloud prompts use a different assignment or order')
    write_json(key_path, key)
    output = private_directory(root, 'audio', 'stage6', 'production')
    write_json(output / 'task.json', {'version': VERSION, 'prompts': prompts})
    write_page(output / 'read-aloud.html', read_aloud_page(prompts))
    return len(prompts)


def listening_sources(root, pairs, voice, speed):
    wanted = {row['passage_id'] for pair in pairs for row in pair}
    recordings = {}
    for row in read_rows(root / SYNTHETIC):
        passage_id = row['passage_id']
        if passage_id in wanted and row['speaker'] == voice and row['speed'] == speed:
            if passage_id in recordings:
                raise ValueError(f'{passage_id}: multiple recordings for the selected condition')
            recordings[passage_id] = row
    if recordings.keys() != wanted or len({row['recording_id'] for row in recordings.values()}) != len(wanted):
        raise ValueError('Expected one independent source recording per listening excerpt')
    return recordings


def prepare_listening(root, pairs, seed, voice, speed):
    sources = listening_sources(root, pairs, voice, speed)
    recordings = {row['recording_id']: row for row in sources.values()}
    passages = {row['passage_id']: row for pair in pairs for row in pair}
    rng = random.Random(seed)
    order = list(pairs)
    rng.shuffle(order)
    private = private_directory(root, *PRIVATE_DIR.parts)
    key_path = private / 'unblinding.json'
    prior = read_json(key_path) if key_path.exists() else None
    survey = {'schema_version': 1, 'survey_id': prior['survey']['survey_id'] if prior else secrets.token_hex(8),
              'trials': []}
    key = {'schema_version': 1, 'study': 'independent-prose-expansion', 'seed': seed,
           'survey': survey, 'trials': []}
    destination = root / STIMULUS_DIR
    with TemporaryDirectory(dir=destination.parent, prefix='.expansion-listening-') as temporary:
        staged = Path(temporary) / 'clips'
        staged.mkdir(mode=0o700)
        for number, pair in enumerate(order, 1):
            members = [{field: sources[row['passage_id']][field]
                        for field in ('recording_id', 'passage_id', 'audio_path', 'audio_sha256')} for row in pair]
            comparison = {'comparison_id': pair[0]['pair_id'], 'comparison': 'period_matched_prose',
                          'speaker_preset': voice, 'speed': speed, 'members': members}
            blind, details = make_trial(root, staged, comparison, f'E{number:02d}', recordings, passages, rng)
            if pair[0].get('match_topic'):
                details['match_topic'] = pair[0]['match_topic']
            survey['trials'].append(blind)
            key['trials'].append(details)
        write_json(staged / 'survey.json', survey)
        check_staged(staged, key)
        if prior is not None and prior != key:
            raise ValueError('The new listening stimuli differ from the saved survey')
        if destination.exists():
            if prior is None or destination.is_symlink():
                raise ValueError('A listening folder already exists without its verified expansion key')
            check_staged(destination, prior)
        else:
            write_json(key_path, key)
            staged.replace(destination)

    transcripts = {
        trial['trial_id']: {side: passages[trial[side]['text_provenance']['passage_id']]['text'] for side in 'AB'}
        for trial in key['trials']
    }
    web = private_directory(root, 'audio', 'stage6', 'listening-web')
    write_page(web / 'index.html', listening_page(survey, destination, overall=True))
    write_page(web / 'with-text.html', listening_page(survey, destination, overall=True, transcripts=transcripts))
    return len(survey['trials']), survey['survey_id']


def prepare(root, *, voice='zm_010', speed=0.9, seed=SEED, production_only=False):
    root = root.resolve(strict=True)
    tasks = matched_pairs(root / PILOT)
    private = private_directory(root, 'results', 'stage6', 'expansion')
    with (private / '.prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = {'read_aloud_prompts': prepare_read_aloud(root, tasks['read_aloud'], seed)}
        if not production_only:
            count, survey_id = prepare_listening(root, tasks['listening'], seed, voice, speed)
            result.update(listening_pairs=count, listening_survey_id=survey_id)
    return result


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--voice', default='zm_010')
    parser.add_argument('--speed', type=float, default=0.9)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--production-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, voice=args.voice, speed=args.speed, seed=args.seed,
                             production_only=args.production_only)))


if __name__ == '__main__':
    main()
