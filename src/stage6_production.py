"""Prepare the blind Stage 6 reading task and score reviewed human recordings."""

import argparse
from collections import Counter, defaultdict
import hashlib
from html import escape
import json
from math import isfinite
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import wave

from src.pilot_validation import read_jsonl, write_json
from src.text_metrics import clauses


VERSION = 'stage6-read-aloud-v1'
PROMPTS = (('R01', 'SD06'), ('R02', 'ET03'), ('R03', 'SD05'), ('R04', 'ET04'))
PAUSE_THRESHOLD_S = 0.200
EVENTS = ('pause', 'hesitation', 'false_start', 'repair', 'reread')
READER_CODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{1,39}')
CONSENT_SCOPES = ('author_self_trial', 'approved_research_study')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def write_jsonl(path, rows):
    with TemporaryDirectory(dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        temporary.write_text(
            ''.join(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n' for row in rows),
            encoding='utf-8',
        )
        temporary.chmod(0o600)
        temporary.replace(path)


def private_directory(root, *parts):
    directory = root
    for part in parts:
        directory = directory / part
        if directory.is_symlink():
            raise ValueError(f'Private data directory is a symlink: {directory}')
        directory.mkdir(exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    return directory


def contained_file(path, directory):
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(directory.resolve(strict=True)):
        raise ValueError(f'Expected a file inside {directory}: {path}')
    return resolved


def stage6_path(root):
    return root / 'audio/stage6'


def restricted_path(root):
    return stage6_path(root) / 'restricted'


def production_stimuli(root):
    passages = {
        row['passage_id']: row
        for row in read_jsonl(root / 'data/pilot/annotated.jsonl')
    }
    stimuli = {}
    for code, passage_id in PROMPTS:
        row = passages[passage_id]
        if hashlib.sha256(row['text'].encode('utf-8')).hexdigest() != row['text_sha256']:
            raise ValueError(f'Passage text hash mismatch: {passage_id}')
        stimuli[code] = row
    return stimuli


def read_aloud_page(prompts):
    items = '\n'.join(
        '<details><summary>{}</summary><p class="passage">{}</p></details>'.format(
            escape(row['code']), escape(row['text']),
        )
        for row in prompts
    )
    return f'''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>順口試讀</title>
<style>
body {{ font: 1.05rem/1.7 system-ui, sans-serif; color: #162733; background: #f6f5f1; max-width: 44rem; margin: 3rem auto; padding: 0 1rem; }}
h1 {{ font-size: 1.8rem; line-height: 1.3; }}
h2 {{ font-size: 1.2rem; }}
details {{ background: white; border: 1px solid #c9cfce; border-radius: .5rem; margin: .7rem 0; padding: .55rem .9rem; }}
summary {{ cursor: pointer; }}
.passage {{ font-family: "Songti TC", "Noto Serif CJK TC", serif; font-size: 1.35rem; }}
code {{ overflow-wrap: anywhere; }}
</style>
</head>
<body>
<main>
<h1>順口試讀</h1>
<p>逐段打開。每次先準備好，再打開一段，用你平常讀文言的發音和速度直接出聲讀。卡住、改口或重讀時，自然繼續。每段保留第一次讀的版本。可以跳過任何一段。</p>
<p>若自願錄音，請每段分開，以段落代號命名。先開始錄音，再打開該段。</p>
{items}
<h2>讀完後回覆</h2>
<p>依實際開口的感覺給每段 1–7 分。1＝很拗口，4＝普通，7＝很順口。可加上以前讀過的段落代號。</p>
<p>回覆格式可直接用 <code>R01=＿ R02=＿ R03=＿ R04=＿　以前讀過=＿</code>。跳過可填「略」。</p>
</main>
</body>
</html>
'''


def prepare(root):
    stimuli = production_stimuli(root)
    prompts = [{'code': code, 'text': row['text']} for code, row in stimuli.items()]
    output = stage6_path(root) / 'production'
    write_json(output / 'task.json', {'version': VERSION, 'prompts': prompts})
    (output / 'read-aloud.html').write_text(read_aloud_page(prompts), encoding='utf-8')
    restricted = private_directory(stage6_path(root), 'restricted')
    key = restricted / 'production-key.json'
    write_json(key, {
        'version': VERSION,
        'prompts': {
            code: {
                field: row[field]
                for field in ('passage_id', 'work_id', 'pair_id', 'genre', 'source_url', 'revision_id', 'text_sha256')
                if field in row
            }
            for code, row in stimuli.items()
        },
    })
    key.chmod(0o600)
    print(json.dumps({'production_prompts': len(prompts), 'protocol': VERSION}))


def wav_metadata(path):
    if path.suffix.lower() != '.wav':
        raise ValueError('Expected a PCM WAV recording')
    try:
        with wave.open(str(path), 'rb') as audio:
            frames = audio.getnframes()
            rate = audio.getframerate()
            if frames <= 0 or rate <= 0 or audio.getcomptype() != 'NONE':
                raise ValueError(f'Expected nonempty PCM audio: {path}')
            width = audio.getnchannels() * audio.getsampwidth()
            audio.setpos(frames - 1)
            if len(audio.readframes(1)) != width:
                raise ValueError(f'Truncated WAV data: {path}')
    except (wave.Error, EOFError) as error:
        raise ValueError(f'Could not read PCM WAV recording: {path}') from error
    return {'audio_sha256': digest(path), 'sample_rate_hz': rate, 'duration_s': frames / rate}


def check_reader_code(value):
    if not isinstance(value, str) or not READER_CODE.fullmatch(value):
        raise ValueError('Reader code must contain 2–40 letters, digits, underscores or hyphens')
    return value


def raw_path(root, reader):
    return root / 'audio/raw/human/stage6' / reader


def reader_output(root, reader):
    return restricted_path(root) / 'production' / reader


def read_consent(root, consent_path):
    path = contained_file(consent_path, restricted_path(root))
    if path.stat().st_mode & 0o077:
        raise ValueError('The consent file must be private')
    consent = read_json(path)
    check_reader_code(consent.get('reader_code'))
    variety = consent.get('variety')
    consent_id = consent.get('consent_id')
    style = consent.get('style', 'usual cold read-aloud')
    if (
        consent.get('version') != VERSION or consent.get('affirmed') is not True
        or consent.get('scope') not in CONSENT_SCOPES
        or not isinstance(variety, str) or not variety.strip()
        or not isinstance(consent_id, str) or not READER_CODE.fullmatch(consent_id)
        or not isinstance(style, str) or not style.strip()
    ):
        raise ValueError('Recording intake requires the matching affirmative consent record and variety')
    return consent


def draft_manifest(root, consent_path):
    consent = read_consent(root, consent_path)
    reader = consent['reader_code']
    stimuli = production_stimuli(root)
    raw = raw_path(root, reader)
    if raw.is_symlink() or raw.resolve() != raw or raw.stat().st_mode & 0o077:
        raise ValueError(f'Recording folder must be private and inside the project: {raw}')
    rows, template = [], []
    for code, passage in stimuli.items():
        candidate = raw / f'{code}.wav'
        if not candidate.exists():
            continue
        path = contained_file(candidate, raw)
        if candidate.is_symlink() or path.stat().st_mode & 0o077:
            raise ValueError(f'Recording must be private and kept under its prompt filename: {candidate}')
        recording_id = f'{reader}-{code}'
        rows.append({
            'protocol_version': VERSION,
            'recording_id': recording_id,
            'kind': 'human',
            'reader_code': reader,
            'prompt_code': code,
            'passage_id': passage['passage_id'],
            'text_sha256': passage['text_sha256'],
            'audio_path': str(path.relative_to(root)),
            'consent_id': consent['consent_id'],
            'consent_path': str(consent_path.resolve().relative_to(root)),
            'recording_rights': consent['scope'],
            'variety': consent['variety'],
            'style': consent.get('style', 'usual cold read-aloud'),
            **wav_metadata(path),
        })
        for index, slots in enumerate(clauses(passage)):
            template.append({
                'recording_id': recording_id,
                'audio_sha256': rows[-1]['audio_sha256'],
                'clause_index': index,
                'reference_text': ''.join(
                    slot['char'] + slot.get('marks_after', '') for slot in slots
                ),
                'status': 'pending',
                'reviewer_code': None,
                'start_s': None,
                'end_s': None,
                'spoken_syllables': None,
                'events': [],
            })
    if not rows:
        raise ValueError('No Stage 6 reader WAVs are present')
    output = private_directory(restricted_path(root), 'production', reader)
    write_jsonl(output / 'recordings.jsonl', rows)
    write_jsonl(output / 'review-template.jsonl', template)
    print(json.dumps({'recordings': len(rows), 'clauses_for_review': len(template)}))


def number(value):
    return type(value) in (int, float) and isfinite(value)


def interval(start, end, lower, upper):
    return number(start) and number(end) and lower <= start < end <= upper


def summarize_clause(review, recording, slots):
    status = review.get('status')
    start, end = review.get('start_s'), review.get('end_s')
    spoken = review.get('spoken_syllables')
    events = review.get('events')
    result = {
        'recording_id': recording['recording_id'],
        'prompt_code': recording['prompt_code'],
        'clause_index': review['clause_index'],
        'reference_slots': len(slots),
        'reviewer_code': check_reader_code(review.get('reviewer_code')),
        'status': status,
    }
    if not isinstance(events, list):
        raise ValueError('Events must be a list')
    if status in ('omitted', 'unscorable'):
        if any(value is not None for value in (start, end, spoken)) or events:
            raise ValueError('Omitted or unscorable clauses must have null measures and no events')
        return {
            **result, 'start_s': None, 'end_s': None, 'spoken_syllables': None,
            'speech_syllables_per_s': None, 'pause_excluded_syllables_per_s': None,
            'within_clause_pause_s': None, 'events': [], 'event_counts': None,
        }
    if (
        status != 'verified' or not interval(start, end, 0, recording['duration_s'])
        or type(spoken) is not int or spoken <= 0
    ):
        raise ValueError('Verified clause requires reviewed bounds and a positive heard syllable count')
    pauses = []
    counts = Counter()
    for event in events:
        kind = event.get('type')
        onset, offset = event.get('start_s'), event.get('end_s')
        lower, upper = (0, recording['duration_s']) if kind == 'reread' else (start, end)
        if kind not in EVENTS or not interval(onset, offset, lower, upper):
            raise ValueError('Each audible event requires a valid type and a valid time interval')
        if kind == 'reread' and not start <= onset:
            raise ValueError('A re-read must follow the start of the clause first attempted')
        if kind == 'pause':
            if not start < onset < offset < end or offset - onset + 1e-9 < PAUSE_THRESHOLD_S:
                raise ValueError('Within-clause pauses must be at least 200 ms and internal to the clause')
            pauses.append((onset, offset))
        counts[kind] += 1
    if len({(event['type'], event['start_s'], event['end_s']) for event in events}) != len(events):
        raise ValueError('Review contains duplicate events')
    pauses.sort()
    if any(left[1] > right[0] for left, right in zip(pauses, pauses[1:])):
        raise ValueError('Silent pause events must not overlap')
    duration = end - start
    silent = sum(stop - begin for begin, stop in pauses)
    return {
        **result, 'start_s': start, 'end_s': end, 'spoken_syllables': spoken,
        'speech_syllables_per_s': spoken / duration,
        'pause_excluded_syllables_per_s': spoken / (duration - silent),
        'within_clause_pause_s': silent,
        'events': events, 'event_counts': {kind: counts[kind] for kind in EVENTS},
    }


def following_gaps(rows):
    for index, row in enumerate(rows):
        next_row = rows[index + 1] if index + 1 < len(rows) else {}
        next_start = next_row.get('start_s')
        end = row['end_s']
        gap = next_start - end if next_start is not None and end is not None else None
        row['following_boundary_gap_s'] = gap
        row['following_boundary_pause'] = (
            gap + 1e-9 >= PAUSE_THRESHOLD_S if gap is not None else None
        )


def validate_recordings(root, reader, stimuli, rows):
    seen = set()
    for row in rows:
        code = row['prompt_code']
        if code not in stimuli or code in seen:
            raise ValueError('Expected unique Stage 6 prompt codes per reader')
        seen.add(code)
        passage = stimuli[code]
        expected_path = raw_path(root, reader) / f'{code}.wav'
        path = contained_file(root / row['audio_path'], raw_path(root, reader))
        consent = read_consent(root, root / row['consent_path'])
        if (
            row['protocol_version'] != VERSION or row['reader_code'] != reader
            or row['recording_id'] != f'{reader}-{code}'
            or row['kind'] != 'human' or row['recording_rights'] not in CONSENT_SCOPES
            or any(row[field] != consent[field] for field in ('reader_code', 'consent_id', 'variety'))
            or row['recording_rights'] != consent['scope'] or path.stat().st_mode & 0o077
            or row['passage_id'] != passage['passage_id']
            or row['text_sha256'] != passage['text_sha256'] or path != expected_path
            or any(row.get(key) != value for key, value in wav_metadata(path).items())
        ):
            raise ValueError('Manifest must identify the consented human WAV and pinned passage')


def alignment_counts(root, path, recordings):
    if path is None:
        return {}
    rows = read_jsonl(contained_file(path, restricted_path(root)))
    by_id = {row['recording_id']: row for row in recordings}
    counts = defaultdict(Counter)
    seen = set()
    for row in rows:
        recording_id = row['recording_id']
        recording = by_id.get(recording_id)
        key = recording_id, row['event_index']
        if (
            recording is None or key in seen
            or row.get('alignment_source') != 'charsiu_waveform_only_then_lexical_link'
            or row['status'] not in ('matched', 'substitution', 'omission', 'insertion')
            or any(row.get(field) != recording[field] for field in (
                'passage_id', 'audio_path', 'audio_sha256', 'kind', 'variety',
            ))
        ):
            raise ValueError('Optional Stage 4 links must identify this human manifest and actual-waveform decoder')
        seen.add(key)
        counts[recording_id][row['status']] += 1
    if set(by_id) != set(counts):
        raise ValueError('Optional Stage 4 link file has missing recordings')
    return {key: dict(value) for key, value in counts.items()}


def analyze(root, reader, review_path, alignments_path):
    reader = check_reader_code(reader)
    stimuli = production_stimuli(root)
    output = reader_output(root, reader)
    recordings = read_jsonl(contained_file(output / 'recordings.jsonl', restricted_path(root)))
    if not recordings:
        raise ValueError('The human recording manifest is empty')
    validate_recordings(root, reader, stimuli, recordings)
    drafts = alignment_counts(root, alignments_path, recordings)

    reviews = {}
    for row in read_jsonl(contained_file(review_path, restricted_path(root))):
        key = row['recording_id'], row['clause_index']
        if type(row['clause_index']) is not int or key in reviews:
            raise ValueError('Each review row needs a unique recording ID and integer clause index')
        reviews[key] = row

    results = []
    summaries = []
    for recording in recordings:
        recording_id = recording['recording_id']
        rows = []
        previous_end = 0
        for index, slots in enumerate(clauses(stimuli[recording['prompt_code']])):
            review = reviews.pop((recording_id, index), None)
            if review is None or review.get('audio_sha256') != recording['audio_sha256']:
                raise ValueError(f'Missing or stale review for {recording_id} clause {index}')
            try:
                result = summarize_clause(review, recording, slots)
            except ValueError as error:
                raise ValueError(f'{recording_id} clause {index}: {error}') from error
            if result['start_s'] is not None:
                if result['start_s'] < previous_end:
                    raise ValueError(f'Clause intervals overlap or go backwards in {recording_id}')
                previous_end = result['end_s']
            rows.append(result)
        following_gaps(rows)
        results.extend(rows)
        coverage = Counter(row['status'] for row in rows)
        summaries.append({
            'prompt_code': recording['prompt_code'],
            'review_coverage': dict(coverage),
            'alignment_draft_event_counts': drafts.get(recording_id),
        })
    if reviews:
        raise ValueError('Review file contains unknown recordings or clauses')

    write_jsonl(output / 'clause-measures.jsonl', results)
    summary = output / 'summary.json'
    write_json(summary, {
        'protocol_version': VERSION,
        'reader_code': reader,
        'pause_threshold_s': PAUSE_THRESHOLD_S,
        'recordings': summaries,
    })
    summary.chmod(0o600)
    print(json.dumps({'recordings': len(recordings), 'reviewed_clauses': len(results)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'draft-manifest', 'analyze'):
        subcommands.add_parser(name).add_argument('--root', required=True, type=Path)
    subcommands.choices['draft-manifest'].add_argument('--consent', required=True, type=Path)
    analysis = subcommands.choices['analyze']
    analysis.add_argument('--reader-code', required=True)
    analysis.add_argument('--review', required=True, type=Path)
    analysis.add_argument('--alignments', type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if args.command == 'prepare':
        prepare(root)
    elif args.command == 'draft-manifest':
        draft_manifest(root, args.consent)
    else:
        analyze(root, args.reader_code, args.review, args.alignments)


if __name__ == '__main__':
    main()
