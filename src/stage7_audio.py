"""Build clause timing and review cues from edition-linked recordings on Gilbreth."""

from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
from statistics import mean, median
from tempfile import NamedTemporaryFile

from audio import align, features
from audio.synthesize import sha256
from src.stage6_production import wav_metadata


SYNTHETIC_MANIFEST = Path('audio/manifests/synthetic.jsonl')
PILOT_DRAFTS = (
    Path('audio/derived/stage6/pause-audit/alignments.jsonl'),
    Path('audio/derived/alignment/alignments.jsonl'),
)
CACHE = Path('audio/derived/stage7-alignments')
MANDARIN = {'cmn', 'cmn-Hans', 'cmn-Hant'}
QUIET_GAP_MS = 150
SLOW_FACTOR = 1.5


def project_file(root, path, directory):
    path = Path(path)
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(root / directory):
        raise ValueError(f'Expected a file inside the Gilbreth project {directory} directory')
    return resolved


def stable_hash(value):
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def alignment_cache(root, passage, relative_path, checksum):
    # Token strings and lexical choices can change independently of the edition text.
    anchors = []
    for slot in passage['slots']:
        mandarin = slot['readings'].get('mandarin', {})
        candidates = [mandarin['selected']] if mandarin.get('selected') else mandarin.get('candidates', [])
        anchors.append([slot['slot_index'], slot['char'], sorted({x['reading'] for x in candidates})])
    token = stable_hash([relative_path, checksum, passage['passage_id'], passage['text_sha256'],
                         anchors, align.MODEL_REVISION, align.VOCAB_REVISION])
    return root / CACHE / f'{token}.json'


def find_recording(root, manifest, relative_path):
    source = project_file(root, manifest, 'audio') if manifest else root / SYNTHETIC_MANIFEST
    if not source.exists():
        return None
    matches = [row for row in features.read_jsonl(source) if row.get('audio_path') == relative_path]
    if len(matches) > 1 or (manifest and not matches):
        raise ValueError('Expected exactly one recording manifest row for this waveform')
    return matches[0] if matches else None


def provenance(record, passage, relative_path, metadata, variety, rights, speaker, style):
    if record is None:
        record = {'recording_id': f"reading-{metadata['audio_sha256'][:16]}", 'kind': 'human',
                  'audio_path': relative_path, 'audio_sha256': metadata['audio_sha256'],
                  'passage_id': passage['passage_id'], 'text_sha256': passage['text_sha256']}
    if (record.get('audio_path') != relative_path
            or record.get('audio_sha256') != metadata['audio_sha256']
            or record.get('passage_id') != passage['passage_id']
            or record.get('text_sha256') != passage['text_sha256']):
        raise ValueError('Recording provenance must match the exact waveform and annotated edition')
    for key, nominal in [('duration_s', metadata['duration_s']),
                         ('sample_rate_hz', metadata['sample_rate_hz']),
                         ('sample_rate', metadata['sample_rate_hz'])]:
        if key in record and abs(record[key] - nominal) > 1e-6:
            raise ValueError(f'Recording manifest {key} differs from the WAV metadata')
    source = {
        'variety': record.get('variety'), 'style': record.get('style'),
        'speaker': record.get('speaker') or record.get('speaker_id') or record.get('reader_code'),
        'recording_rights': record.get('recording_rights'),
    }
    for key, provided in [('variety', variety), ('style', style), ('speaker', speaker), ('recording_rights', rights)]:
        if provided is not None:
            if source[key] is not None and source[key] != provided:
                raise ValueError(f'Recording manifest and command line disagree on {key}')
            source[key] = provided
    if source['recording_rights'] is None and record.get('kind') == 'synthetic' and record.get('model_license'):
        source['recording_rights'] = 'Synthetic research stimulus. Model and text licensing are recorded separately.'
    if (record.get('kind') not in {'human', 'synthetic'}
            or any(not isinstance(value, str) or not value.strip()
                   for value in (record.get('recording_id'), *source.values()))):
        raise ValueError('Supply a recording manifest or specify the recording variety, speaker code, '
                         'style, and documented rights or consent')
    edition = {key: passage.get(field) for key, field in [('text_revision', 'revision_id'),
               ('text_source_url', 'source_url'), ('text_license', 'license')]}
    if any(record.get(key) is not None and value is not None and record[key] != value
           for key, value in edition.items()):
        raise ValueError('Recording manifest and text annotation disagree on edition or license')
    preserved = ('recording_id', 'kind', 'audio_path', 'passage_id', 'text_sha256', 'source_url',
                 'model_revision', 'model_license', 'speed', 'consent_id')
    return {**{key: record[key] for key in preserved if key in record}, **metadata, **source,
            **{key: record.get(key, value) for key, value in edition.items()}}


def decode_waveform(root, waveform, passage, recording):
    if recording['variety'] not in MANDARIN:
        raise ValueError('Automatic acoustic decoding requires a confirmed Mandarin recording')
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('Run fresh acoustic decoding in a Gilbreth Slurm GPU allocation')
    if not 0.1 <= recording['duration_s'] <= 60:
        raise ValueError('Use a WAV excerpt between 0.1 and 60 seconds for acoustic decoding')
    if not any(slot['readings'].get('mandarin', {}).get('candidates') for slot in passage['slots']):
        raise ValueError('Supply the cached Unihan Mandarin lexicon for acoustic linking')
    decoder = align.MandarinDecoder(root, offline=True)
    heard = align.heard_syllables(decoder.decode(waveform))
    base = {key: recording[key] for key in ('recording_id', 'passage_id', 'audio_path', 'variety',
                                           'kind', 'audio_sha256', 'text_sha256')}
    events = []
    for index, (slot, syllable, status, basis) in enumerate(align.link_slots(passage['slots'], heard)):
        events.append({**base, 'event_index': index, 'status': status, 'match_basis': basis,
                       'slot_index': slot['slot_index'] if slot else None,
                       'start_s': syllable.phones[0].start_s if syllable else None,
                       'end_s': syllable.phones[-1].end_s if syllable else None,
                       'confidence': mean(phone.confidence for phone in syllable.phones) if syllable else None,
                       'observed_phone_draft': {'onset': syllable.key[0], 'final': syllable.key[1],
                                                'tone': syllable.tone} if syllable else None,
                       'realized_reading': None, 'reading_status': 'acoustic_draft' if syllable else 'unobserved',
                       'alignment_source': 'charsiu_waveform_only_then_lexical_link',
                       'model_revision': align.MODEL_REVISION, 'frame_s': decoder.step_s})
    return events


def save_cache(root, path, recording, events):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.resolve(strict=True) != root / CACHE or path.parent.stat().st_mode & 0o077:
        raise ValueError('The Stage 7 alignment cache must be private to the project owner')
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump({'recording': recording, 'events': events}, stream, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def load_events(root, path, recording):
    if path is not None:
        path = project_file(root, path, 'audio')
        candidates = [(path, True)]
    else:
        candidates = [(root / item, False) for item in PILOT_DRAFTS if (root / item).is_file()]
    for candidate, check_edition in candidates:
        events = [row for row in features.read_jsonl(candidate) if row.get('recording_id') == recording['recording_id']]
        if events and (check_edition or all(row.get('audio_sha256') for row in events)):
            return events, check_edition
    raise ValueError('No checksum-bound alignment is available for this WAV. Run --decode in a Gilbreth Slurm GPU allocation.')


def checked_events(events, recording, slots, check_edition):
    if not events:
        raise ValueError('This recording has no alignment events')
    required = {'recording_id', 'passage_id', 'audio_path', 'audio_sha256'}
    if check_edition:
        required.add('text_sha256')
    statuses = features.SPEECH | {'omission'}
    previous_slot = -1
    for row in events:
        if (any(row.get(key) != recording[key] for key in required)
                or any(key in row and row[key] != recording[key] for key in ('text_sha256', 'kind', 'variety'))):
            raise ValueError('Alignment does not match the exact waveform and annotated edition')
        status, slot = row.get('status'), row.get('slot_index')
        if (status not in statuses or (slot is not None and (type(slot) is not int or slot not in slots))
                or (slot is None and status not in {'insertion', 'repetition'})
                or (slot is not None and status == 'insertion')):
            raise ValueError('Alignment contains an invalid status or written slot')
        if row.get('realized_reading') is not None and (status != 'reviewed' or recording['kind'] != 'human'):
            raise ValueError('A verified performed reading requires a reviewed human event')
        if (status == 'omission') != (row.get('start_s') is None and row.get('end_s') is None):
            raise ValueError('An acoustic event must have times unless it is an omission')
        if slot is not None and status != 'repetition':
            if slot < previous_slot:
                raise ValueError('Primary alignment slots must follow the written text order')
            previous_slot = slot
    return [{**row, 'kind': recording['kind'], 'speaker_id': recording['speaker'],
             'variety': recording['variety'], 'style': recording['style']} for row in events]


def clause_timeline(syllables, summary):
    linked = defaultdict(list)
    discrepant = defaultdict(Counter)
    for row in syllables:
        index = row['clause_index']
        if row['duration_ms'] is not None:
            linked[index].append(row)
        elif index is not None:
            discrepant[index][row['status']] += 1
    clauses = []
    for clause in summary['clauses']:
        index = clause['clause_index']
        measured = linked[index]
        start = measured[0]['start_s'] if measured else None
        end = measured[-1]['end_s'] if measured else None
        elapsed = clause['elapsed_ms']
        clauses.append({**clause, 'start_s': start if elapsed is not None else None,
                        'end_s': end if elapsed is not None else None, 'draft_span_start_s': start,
                        'draft_span_end_s': end, 'unlinked_events': dict(discrepant[index]),
                        'matched_slots_per_s': 1000 * clause['slots_measured'] / elapsed if elapsed else None})
    return clauses


def review_cues(clauses, gaps, slots):
    cues = []
    rates = [clause['matched_slots_per_s'] for clause in clauses if clause['matched_slots_per_s'] is not None]
    typical = median(rates) if len(rates) >= 3 else None
    for clause in clauses:
        index = clause['clause_index']
        rate = clause['matched_slots_per_s']
        if rate and typical and typical / rate >= SLOW_FACTOR:
            cues.append({'category': 'relatively_slow_clause', 'clause_indices': [index], 'priority': 2,
                         'strength': typical / rate,
                         'reason': f'This clause has {rate:.2f} linked slots per second versus a take median of {typical:.2f}.',
                         'start_s': clause['start_s'], 'end_s': clause['end_s'], 'slot_indices': [],
                         'evidence': {'matched_slots_per_s': rate, 'take_median_slots_per_s': typical}})
        missing = clause['slots_expected'] - clause['slots_measured']
        if missing:
            cues.append({'category': 'incomplete_acoustic_link', 'clause_indices': [index], 'priority': 1,
                         'strength': missing / clause['slots_expected'],
                         'reason': f'{missing} written slot(s) lack a unique matched audio interval. Check the waveform and reading.',
                         'start_s': None, 'end_s': None, 'slot_indices': [],
                         'evidence': {'missing_slots': missing, 'observations': clause['unlinked_events']}})
    for gap in gaps:
        if gap['boundary_after'] or QUIET_GAP_MS not in gap['quiet_candidate_ms_thresholds']:
            continue
        left = gap['after_slot_index']
        cues.append({'category': 'internal_quiet_gap', 'clause_indices': [slots[left]['clause_index']], 'priority': 3,
                     'strength': gap['gap_ms'],
                     'reason': f'A {gap["gap_ms"]:.0f} ms low-energy gap occurs within the clause. Listen to check how the phrase breaks.',
                     'start_s': gap['start_s'], 'end_s': gap['end_s'], 'slot_indices': [left, left + 1],
                     'evidence': {'gap_ms': gap['gap_ms'], 'boundary_after': gap['boundary_after']}})
    return sorted(cues, key=lambda row: (-row['priority'], -row['strength'], row['clause_indices']))


def score_audio(root, wav, passage, *, manifest=None, alignment=None, decode=False, variety=None,
                rights=None, speaker=None, style=None):
    """Measure checked waveform intervals and highlight cues that merit human review."""
    if decode and alignment is not None:
        raise ValueError('Choose fresh decoding or an existing alignment')
    root = Path(root).resolve(strict=True)
    waveform_path = project_file(root, wav, 'audio/raw')
    if not passage['slots'] or hashlib.sha256(passage['text'].encode('utf-8')).hexdigest() != passage['text_sha256']:
        raise ValueError('The annotated passage needs Han slots and an exact text checksum')
    slots = {slot['slot_index']: slot for slot in passage['slots']}
    if list(slots) != list(range(len(passage['slots']))):
        raise ValueError('The annotated passage needs consecutive written slot indices')
    relative_path = str(waveform_path.relative_to(root))
    metadata = wav_metadata(waveform_path)
    path = alignment_cache(root, passage, relative_path, metadata['audio_sha256'])
    cached = None
    if path.is_file() and not decode:
        if path.is_symlink() or path.resolve(strict=True) != path or path.stat().st_mode & 0o077:
            raise ValueError('The Stage 7 alignment cache file must be private to the project owner')
        cached = json.loads(path.read_text(encoding='utf-8'))
    record = find_recording(root, manifest, relative_path)
    if record is None and cached is not None:
        record = cached['recording']
    recording = provenance(record, passage, relative_path, metadata, variety, rights, speaker, style)
    if decode:
        events, check_edition = decode_waveform(root, waveform_path, passage, recording), True
    elif cached is not None and alignment is None:
        events, check_edition = cached['events'], True
    else:
        events, check_edition = load_events(root, alignment, recording)
    events = checked_events(events, recording, slots, check_edition)
    waveform = features.Waveform(waveform_path)
    syllables, gaps, summary = features.extract_recording(events, passage, waveform, [])
    if abs(waveform.duration_s - metadata['duration_s']) > 1e-6 or sha256(waveform_path) != recording['audio_sha256']:
        raise ValueError('The waveform changed while its audio was being scored')
    if decode:
        save_cache(root, path, recording, events)
    clauses = clause_timeline(syllables, summary)
    reviewed = sum(row['status'] == 'reviewed' for row in events)
    sources = sorted({row['alignment_source'] for row in events if row.get('alignment_source')})
    if reviewed:
        method = 'Human-reviewed event intervals are marked separately.'
    elif sources == ['charsiu_waveform_only_then_lexical_link']:
        method = 'Charsiu decoded the waveform before matching text slots. Review draft timing and pronunciation by ear.'
    else:
        method = 'Imported draft interval links need independent timing and pronunciation review.'
    return {'recording': recording, 'duration_s': waveform.duration_s, 'summary': summary,
            'method': method, 'alignment_sources': sources, 'reviewed_events': reviewed,
            'clauses': clauses, 'gaps': gaps, 'syllables': syllables,
            'observations': review_cues(clauses, gaps, slots)}
