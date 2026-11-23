"""Prepare counterbalanced, owner-only follow-up forms from the expansion pilot."""

import argparse
from base64 import b64decode
from collections import Counter
import fcntl
from hashlib import sha256
from html import escape
from itertools import product
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from src.expansion_tasks import PILOT, matched_pairs, write_page
from src.stage6_listening import PRIVATE_DIR, STIMULUS_DIR, digest, read_json, write_json
from src.stage6_production import VERSION, private_directory, production_stimuli, read_aloud_page
from src.stage6_survey_page import clip_texts, listening_page


DESTINATION = 'followup-pilot'
WAV = re.compile(r'src="data:audio/wav;base64,([^"]+)"')
TRANSCRIPT = re.compile(r'<p class="transcript">(.*?)</p>', re.DOTALL)


def listening_forms(root, expected):
    staged = root / STIMULUS_DIR
    survey = read_json(staged / 'survey.json')
    texts = clip_texts(root, staged, survey)
    key = read_json(root / PRIVATE_DIR / 'unblinding.json')
    sources = {trial['trial_id']: trial for trial in key['trials']}
    assignments = {frozenset(row['passage_id'] for row in pair) for pair in expected}
    original = survey['trials']
    if len(original) != 2 or {
        frozenset(row[side]['text_provenance']['passage_id'] for side in 'AB')
        for row in sources.values()
    } != assignments:
        raise ValueError('Expected both matched listening pairs from the independent-work pilot')

    balance = Counter()
    for index, (visible, reversed_pairs, swapped_sides) in enumerate(product((False, True), repeat=3), 1):
        code = f'L{index:02d}'
        original_order = original[::-1] if reversed_pairs else original
        original_sides = 'BA' if swapped_sides else 'AB'
        transcripts, trials, mapping, hashes = {}, [], [], []
        expected_text = []
        for position, row in enumerate(original_order, 1):
            identifier = row['trial_id']
            files = {'trial_id': identifier}
            transcripts[identifier] = {}
            for side, previous in zip('AB', original_sides):
                files[side] = row[previous]
                transcripts[identifier][side] = texts[identifier][previous]
                expected_text.append(escape(transcripts[identifier][side]))
                hashes.append(sources[identifier][previous]['sha256'])
            trials.append(files)
            mapping.append({'trial_id': identifier, 'original_sides_in_play_order': original_sides})
            balance[identifier, visible, position, original_sides] += 1
        page = listening_page({**survey, 'trials': trials}, staged, overall=True,
                              transcripts=transcripts if visible else None, form_code=code)
        if ([sha256(b64decode(source)).hexdigest() for source in WAV.findall(page)] != hashes
                or TRANSCRIPT.findall(page) != (expected_text if visible else [])):
            raise ValueError('Listening form changed the clips or their assigned transcripts')
        yield code, page, {'presentation': 'text_supported' if visible else 'audio_only',
                           'trials': mapping, 'wav_sha256_in_play_order': hashes}
    if len(balance) != 16 or set(balance.values()) != {1}:
        raise ValueError('Listening presentation, trial position and clip order must balance')


def production_forms(root):
    path = root / 'audio/stage6/production/task.json'
    task = read_json(path)
    prompts = task['prompts']
    checked = production_stimuli(root)
    if (task['version'] != VERSION or len(prompts) != 4
            or {row['code']: row['text'] for row in prompts} !=
            {code: row['text'] for code, row in checked.items()}):
        raise ValueError('Expected the exact four independent read-aloud prompts')
    for offset in range(len(prompts)):
        code = f'P{offset + 1:02d}'
        ordered = prompts[offset:] + prompts[:offset]
        yield code, read_aloud_page(ordered, form_code=code), [row['code'] for row in ordered]


def render(root, staging):
    assigned = matched_pairs(root / PILOT)
    listening = {}
    production = {}
    listen_dir = private_directory(staging, 'participant', 'listening')
    read_dir = private_directory(staging, 'participant', 'read-aloud')
    for code, page, row in listening_forms(root, assigned['listening']):
        write_page(listen_dir / f'{code}.html', page)
        listening[code] = row
    for code, page, order in production_forms(root):
        write_page(read_dir / f'{code}.html', page)
        production[code] = order
    restricted = private_directory(staging, 'restricted')
    write_json(restricted / 'design.json', {
        'study': 'independent-work-followup-v1',
        'source_survey_id': read_json(root / STIMULUS_DIR / 'survey.json')['survey_id'],
        'source_production_task_sha256': digest(root / 'audio/stage6/production/task.json'),
        'listening_forms': listening, 'read_aloud_forms': production,
    })
    return {'listening_forms': len(listening), 'listening_conditions': 2,
            'unchanged_wavs_per_form': 4, 'read_aloud_forms': len(production),
            'read_aloud_prompts_per_form': 4}


def verify_existing(staging, destination):
    proposed = {path.relative_to(staging) for path in staging.rglob('*')}
    existing = {path.relative_to(destination) for path in destination.rglob('*')}
    if destination.is_symlink() or destination.stat().st_mode & 0o077 or proposed != existing:
        raise ValueError('Existing follow-up packet differs from the verified build')
    for relative in proposed:
        old, new = destination / relative, staging / relative
        if (old.is_symlink() or old.stat().st_mode & 0o077 or old.is_dir() != new.is_dir()
                or (new.is_file() and (not old.is_file() or digest(old) != digest(new)))):
            raise ValueError(f'Existing follow-up file differs from the verified build: {relative}')


def build(root):
    root = root.resolve(strict=True)
    destination = root / DESTINATION
    lock_dir = private_directory(root, 'results', 'stage6', 'expansion')
    with (lock_dir / '.followup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with TemporaryDirectory(dir=root, prefix='.followup-') as temporary:
            staging = private_directory(Path(temporary), DESTINATION)
            summary = render(root, staging)
            if destination.exists() or destination.is_symlink():
                verify_existing(staging, destination)
            else:
                staging.rename(destination)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(build(args.root)))


if __name__ == '__main__':
    main()
