"""Extract a metadata-selected, cross-reader subset of DEBATE segmentation audio."""

import argparse
from collections import defaultdict
from hashlib import md5, sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import unicodedata
import wave
from zipfile import ZipFile


SOURCE = 'https://zenodo.org/records/15609922'
PAPER = 'https://arxiv.org/html/2506.07502v1'
LICENSE = 'CC BY-NC 4.0'
SOURCE_MD5 = {'archive': 'ef369ccf3189aa9947f029fda90c6a1d',
              'annotations': '35a93979fa351657906560701a129287'}
WAVE_NAME = re.compile(r's(\d+)_seg_id_(\d+)\.wav', re.IGNORECASE)
ITEM_ID = re.compile(r'(?:sx[_ -])?(?:seg[_ -]?)?(?:id[_ -]?)?(\d+)(?:\.wav)?', re.IGNORECASE)
SPEAKER_ID = re.compile(r'(?:DEBATE-)?s?(\d+)', re.IGNORECASE)
SLASH = re.compile(r'[/／]')


def is_han(char):
    return unicodedata.name(char, '').startswith(('CJK UNIFIED IDEOGRAPH', 'CJK COMPATIBILITY IDEOGRAPH'))


def annotated_text(value):
    """Return the exact Han sequence and 1-based character joins marked in the prompt."""
    if not isinstance(value, str) or not SLASH.search(value):
        return None
    text, positive = [], set()
    for char in value:
        if SLASH.fullmatch(char):
            positive.add(len(text))
        elif is_han(char):
            text.append(char)
        elif not (char.isspace() or unicodedata.category(char).startswith('P')):
            return None
    positive = sorted(index for index in positive if 0 < index < len(text))
    return (''.join(text), tuple(positive)) if positive and len(text) >= 4 else None


def item_number(value):
    if isinstance(value, (int, float)) and value >= 0 and int(value) == value:
        return int(value)
    if isinstance(value, str):
        clean = PurePosixPath(value.strip()).name
        member = WAVE_NAME.fullmatch(clean)
        if member:
            return int(member[2])
        match = ITEM_ID.fullmatch(clean)
        if match:
            return int(match[1])
    return None


def annotation_groups(xls_path):
    import xlrd

    book = xlrd.open_workbook(str(xls_path))
    items = {}
    for sheet in book.sheets():
        for row_index in range(sheet.nrows):
            cells = sheet.row_values(row_index)
            if len(cells) < 2:
                continue
            transcript, raw_id = cells[:2]
            parsed = annotated_text(transcript)
            item = item_number(raw_id)
            if parsed is None or item is None:
                continue
            normalized, positive = parsed
            previous = items.get(item)
            if previous and (previous['text'], previous['positive']) != parsed:
                raise ValueError(f'Conflicting DEBATE prompt transcription for item {item}')
            items[item] = {'item': item, 'text': normalized, 'positive': positive,
                           'marked_prompt': transcript.strip(), 'annotation_row': row_index + 1,
                           'annotation_sheet': sheet.name}
    groups = defaultdict(list)
    for row in items.values():
        groups[row['text']].append(row)
    if not groups:
        raise ValueError('No DEBATE annotations with ID plus slash-marked Han transcription')
    return groups


def wav_members(archive):
    members = {}
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        match = WAVE_NAME.fullmatch(path.name)
        if entry.is_dir() or not match or path.parent.name.lower() != 'segment' or '__MACOSX' in path.parts:
            continue
        key = (int(match[1]), int(match[2]))
        if key in members:
            raise ValueError(f'Duplicate DEBATE recording {key}')
        members[key] = entry
    if not members:
        raise ValueError('No documented speaker-specific segmentation WAV paths in DEBATE archive')
    return members


def reader_number(value):
    if type(value) is int and value >= 0:
        return value
    match = SPEAKER_ID.fullmatch(value.strip()) if isinstance(value, str) else None
    return int(match[1]) if match else None


def recording_text(record):
    texts = set()
    for key in ('characters', 'transcript', 'text', 'marked_prompt'):
        if key not in record:
            continue
        value = record[key]
        if isinstance(value, list):
            if not all(isinstance(char, str) and len(char) == 1 for char in value):
                raise ValueError('Invalid character list in the DEBATE manifest')
            value = ''.join(value)
        if not isinstance(value, str) or any(not (is_han(char) or char.isspace()
                                                    or unicodedata.category(char).startswith('P')) for char in value):
            raise ValueError('Invalid Han transcript in the DEBATE manifest')
        texts.add(''.join(char for char in value if is_han(char)))
    if len(texts) != 1 or not next(iter(texts)):
        raise ValueError('The DEBATE manifest lacks one consistent Han transcript per recording')
    return texts.pop()


def recording_reader(record):
    label = reader_number(record.get('speaker'))
    source = record.get('source_member')
    match = WAVE_NAME.fullmatch(PurePosixPath(source).name) if isinstance(source, str) else None
    member = int(match[1]) if match else None
    if label is not None and member is not None and label != member:
        raise ValueError('DEBATE speaker label disagrees with its archive member')
    identity = member if member is not None else label
    if identity is None:
        raise ValueError('Missing numeric source reader ID in a DEBATE recording')
    return identity


def exclusions(manifest):
    if 'source_md5' in manifest and manifest['source_md5'] != SOURCE_MD5:
        raise ValueError('The cited DEBATE exclusion manifest is from a different release')
    records = manifest.get('recordings')
    if not records:
        raise ValueError('The DEBATE exclusion manifest must contain its selected recordings')
    texts = {recording_text(record) for record in records}
    speakers = {recording_reader(record) for record in records}
    for value in manifest.get('speaker_ids', []):
        identity = reader_number(value)
        if identity is None:
            raise ValueError(f'Invalid archive speaker ID {value!r} in DEBATE exclusion manifest')
        speakers.add(identity)
    return texts, speakers


def select(groups, members, group_count, speaker_count, *, excluded_texts=frozenset(), excluded_speakers=frozenset()):
    release_speakers = {speaker for speaker, _ in members}
    if excluded_speakers - release_speakers or excluded_texts - groups.keys():
        raise ValueError('The DEBATE exclusion identities differ from the pinned release inventory')
    speakers = sorted(release_speakers - excluded_speakers)
    if speaker_count is not None:
        if not 2 <= speaker_count <= len(speakers):
            raise ValueError('The DEBATE archive has fewer than the requested number of available speakers')
        # Preserve the even spread across the available reader IDs for specified cohort sizes.
        speakers = [speakers[i * (len(speakers) - 1) // (speaker_count - 1)] for i in range(speaker_count)]
    if len(speakers) < 2:
        raise ValueError('At least two available DEBATE speakers are required')
    subjects = []
    for text, items in groups.items():
        if text in excluded_texts:
            continue
        variants = {}
        for item in sorted(items, key=lambda row: row['item']):
            if all((speaker, item['item']) in members for speaker in speakers):
                variants.setdefault(item['positive'], item)
        # Require a differing join in both directions. This yields matched internal controls.
        ordered = list(variants.values())
        pairs = [(first, second) for i, first in enumerate(ordered)
                 for second in ordered[i + 1:]
                 if set(first['positive']) - set(second['positive'])
                 and set(second['positive']) - set(first['positive'])]
        if not pairs:
            continue
        first, second = min(pairs, key=lambda pair: (pair[0]['item'], pair[1]['item']))
        digest = sha256(text.encode('utf-8')).hexdigest()
        subjects.append((digest, first, second))
    if len(subjects) < group_count:
        raise ValueError(f'Only {len(subjects)} groups satisfy fixed metadata criteria; need {group_count}')
    return speakers, sorted(subjects)[:group_count]


def extract(args, speakers, groups, archive, members):
    recordings = []
    for digest, first, second in groups:
        for variant, opposite in ((first, second), (second, first)):
            a, b = map(set, (variant['positive'], opposite['positive']))
            positive = sorted(a - b)
            negative = sorted(b - a)
            for speaker in speakers:
                member = members[speaker, variant['item']]
                identity = f"DEBATE-s{speaker}-seg-{variant['item']:03d}"
                path = Path('wav') / f'{identity}.wav'
                data = archive.read(member)
                with wave.open(BytesIO(data), 'rb') as handle:
                    channels = handle.getnchannels()
                    if channels not in (1, 2) or (handle.getsampwidth(), handle.getframerate()) != (2, 16000):
                        raise ValueError(f'{member.filename}: expected released mono or stereo 16 kHz PCM16')
                    duration = handle.getnframes() / handle.getframerate()
                with (args.output / path).open('xb') as target:
                    target.write(data)
                recordings.append({
                    'id': identity, 'recording_id': identity, 'speaker': f'DEBATE-{speaker}',
                    'work': f'DEBATE-{digest[:16]}', 'transcript': variant['text'],
                    'characters': list(variant['text']), 'text': variant['text'],
                    'marked_prompt': variant['marked_prompt'], 'positive_ordinals': positive,
                    'negative_ordinals': negative, 'eligible_controls': negative,
                    'candidate_ordinals': sorted(set(positive) | set(negative)),
                    'source_positive_ordinals': list(variant['positive']),
                    'annotation_namespace': 'prompted structural boundary',
                    'annotation_sheet': variant['annotation_sheet'], 'annotation_row': variant['annotation_row'],
                    'path': path.as_posix(), 'wav_path': path.as_posix(), 'wav_sha256': sha256(data).hexdigest(),
                    'duration_s': duration, 'sample_rate': 16000, 'channels': channels, 'source_member': member.filename,
                    'license': LICENSE, 'source': SOURCE, 'performed_variety': 'Mandarin',
                    'recording_style': 'Prompted structural-disambiguation reading over personal devices',
                })
    return recordings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--groups', type=int, default=24)
    parser.add_argument('--speaker-count', type=int,
                        help='Use this many readers (default is six, or every remaining reader with exclusion)')
    parser.add_argument('--exclude-manifest', type=Path,
                        help='Exclude all exact Han texts and archived reader IDs in a prior DEBATE manifest')
    args = parser.parse_args()
    if args.groups < 1 or (args.speaker_count is not None and args.speaker_count < 2):
        parser.error('At least one text group and two speakers are required')
    external = args.exclude_manifest is not None
    speaker_count = args.speaker_count if external or args.speaker_count is not None else 6
    excluded_texts, excluded_speakers = set(), set()
    if external:
        prior = args.exclude_manifest.read_bytes()
        excluded_texts, excluded_speakers = exclusions(json.loads(prior))
    for key, path in (('annotations', args.annotations), ('archive', args.archive)):
        with path.open('rb') as handle:
            checksum = md5()
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
                checksum.update(block)
            if checksum.hexdigest() != SOURCE_MD5[key]:
                raise ValueError(f'{path}: differs from the versioned Zenodo release hash')
    metadata = annotation_groups(args.annotations)
    with ZipFile(args.archive) as archive:
        members = wav_members(archive)
        speakers, groups = select(metadata, members, args.groups, speaker_count,
                                  excluded_texts=excluded_texts, excluded_speakers=excluded_speakers)
        if (set(speakers) & excluded_speakers
                or any(row['text'] in excluded_texts for _, first, second in groups for row in (first, second))):
            raise ValueError('DEBATE holdout selection overlaps the exclusion manifest')
        (args.output / 'wav').mkdir(parents=True, exist_ok=False)
        records = extract(args, speakers, groups, archive, members)
    manifest = {'source': SOURCE, 'paper': PAPER, 'license': LICENSE, 'source_md5': SOURCE_MD5,
                'selection': 'Exact shared Han transcript with two prospectively annotated mutually different '
                             'placements. Fixed speaker IDs sampled evenly by archive ID. Select first two '
                             'eligible variants by item ID and first text groups by SHA-256.',
                'annotation': 'Archive slash marks specify the intended joins. Score only positions contrasted '
                              'between both variants. No reference audio timestamps are in this release.',
                'metadata_groups': len(metadata), 'selected_groups': len(groups), 'speaker_ids': speakers,
                'recordings': records}
    if external:
        if ({recording_text(record) for record in records} & excluded_texts
                or {recording_reader(record) for record in records} & excluded_speakers):
            raise ValueError('DEBATE holdout recordings overlap the exclusion manifest')
        reader_rule = ('All remaining source readers.' if speaker_count is None
                       else 'Specified number of readers evenly spaced among the remaining source IDs.')
        manifest['selection'] = ('Exact shared Han transcript with two differing join variants. Exclude prior '
                                 f'transcripts and source readers. {reader_rule} Select first eligible text '
                                 'groups by SHA-256 and first eligible pair by item IDs.')
        manifest['external_holdout'] = {'release': SOURCE, 'excluded_manifest_sha256': sha256(prior).hexdigest(),
                                        'excluded_text_groups': len(excluded_texts),
                                        'excluded_speaker_ids': sorted(excluded_speakers),
                                        'text_identity': 'Unpunctuated exact Han sequence',
                                        'speaker_identity': 'Numeric DEBATE release reader ID',
                                        'overlapping_text_groups': 0, 'overlapping_speaker_ids': []}
    with (args.output / 'manifest.json').open('x', encoding='utf-8') as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(f"DEBATE: {len(records)} original recordings, {len(groups)} distinct strings, {len(speakers)} speakers")


if __name__ == '__main__':
    main()
