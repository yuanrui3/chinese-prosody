"""Add a contextually recovered guide clause without rerendering the verified pairs."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path

from src.minimal_ending_analysis import usable_slots
from src.pilot_validation import read_jsonl, write_json
from src.recitation_guide_recovery import recover_fragmented_clause
from src.recitation_phrasing import AUDIO, CORPUS, DESTINATION, RECORDINGS, SYLLABLES, inspect_clause, render
from src.stage6_listening import digest, read_clip, read_json
from src.text_metrics import clauses


ALIGNMENTS = Path('audio/derived/alignment/alignments.jsonl')
PHONE_DRAFTS = Path('audio/derived/alignment/phone-drafts.jsonl')
GUIDE = '日暮途遠'


def retain_waveforms(prior, root, pairs):
    for pair in pairs:
        for member in (pair['sham'], *pair['variants'].values()):
            relative = Path(member['audio_path'])
            previous = (prior / relative).resolve(strict=True)
            target = root / relative
            if (not previous.is_relative_to(prior / AUDIO) or target.parent != root / AUDIO
                    or previous.stat().st_mode & 0o077 or digest(previous) != member['audio_sha256']):
                raise ValueError('Original phrasing WAV is outside the expected private directory or has changed')
            if not target.exists():
                os.link(previous, target)
            if target.is_symlink() or digest(target) != member['audio_sha256'] or target.stat().st_mode & 0o077:
                raise ValueError('The retained phrasing WAV differs from the original')


def try_guide(root, guide, screen, inputs):
    if any(digest(guide / path) != inputs[str(path)] for path in (CORPUS, RECORDINGS, SYLLABLES)):
        raise ValueError('The guide source changed since the initial screen')
    identifier = screen['passage_id']
    passage, = [row for row in read_jsonl(guide / CORPUS) if row['passage_id'] == identifier]
    take, = [row for row in read_jsonl(guide / RECORDINGS) if row['passage_id'] == identifier]
    slots, = [row for row in clauses(passage) if [slot['slot_index'] for slot in row] == screen['slot_indices']]
    if (len(slots) != 4 or ''.join(slot['char'] for slot in slots) != GUIDE
            or sha256(passage['text'].encode('utf-8')).hexdigest() != take['text_sha256']
            or passage['revision_id'] != take['text_revision']):
        raise ValueError('Recovery requires the original four-character witness and recording')
    recording_id = take['recording_id']
    linked = usable_slots([row for row in read_jsonl(guide / SYLLABLES) if row['recording_id'] == recording_id])
    draft, = [row for row in read_jsonl(guide / PHONE_DRAFTS) if row['recording_id'] == recording_id]
    events = [row for row in read_jsonl(guide / ALIGNMENTS) if row['recording_id'] == recording_id]
    for row in (draft, *events):
        if any(row[field] != take[field] for field in ('passage_id', 'audio_path', 'audio_sha256')):
            raise ValueError('Cached phone evidence belongs to a different recording')
    recovered = recover_fragmented_clause(take, slots, linked, draft, events)
    if recovered is None:
        return None, 'no_unique_contextual_link'
    effective, evidence = recovered
    rate, pcm = read_clip(guide, take, take['sample_rate'])
    candidate, reason = inspect_clause(take, effective, slots, pcm, rate, max(map(abs, pcm)),
                                       recovered_slot=evidence['slot_index'])
    if reason is not None:
        return None, reason
    pair = {**screen, **candidate, 'status': 'selected', 'reason': None, 'baseline_recovery': evidence,
            'source': {'root': str(guide), **take, 'sample_count': len(pcm)},
            'characters_in_test_clause': 4, 'characters_in_passage': len(passage['slots'])}
    pair['sham'], pair['variants'] = render(root, take, pcm, rate, pair)
    return pair, 'contextually_linked'


def extend(root, prior, guide):
    if len({root, prior, guide}) != 3:
        raise ValueError('The original experiment, new experiment, and guide source must be distinct')
    for path in (root / AUDIO, (root / DESTINATION).parent):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise ValueError('Experiment directories must be private')
    manifest = prior / DESTINATION
    original = read_json(manifest)
    pairs = original['pairs'].copy()
    screens = [row.copy() for row in original['screens']]
    screen, = [row for row in screens if row['source_set'] == 'guide' and row['clause_text'] == GUIDE]
    if screen['status'] != 'ineligible' or screen['reason'] != 'missing_exact_segment_link':
        raise ValueError('Expected the original unresolved guide slot')
    retain_waveforms(prior, root, pairs)
    recovered, status = try_guide(root, guide, screen, original['inputs_sha256']['guide'])
    if recovered is not None:
        screen.update(status='selected', reason=None)
        pairs.append(recovered)
    summary = {'screened': len(screens), 'prior_pairs_retained': len(original['pairs']),
               'rendered_pairs': len(pairs), 'independent_works': len({pair['work_id'] for pair in pairs}),
               'output_wavs': 3 * len(pairs), 'by_genre': dict(Counter(pair['genre'] for pair in pairs)),
               'by_period': dict(Counter(pair['period'] for pair in pairs)), 'guide_recovery': status}
    write_json(root / DESTINATION, {**original, 'summary': summary, 'pairs': pairs, 'screens': screens,
               'prior_stimuli_sha256': digest(manifest), 'guide_recovery_source_sha256': {
                   str(path): digest(guide / path) for path in (ALIGNMENTS, PHONE_DRAFTS)}})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--prior', type=Path, required=True)
    parser.add_argument('--guide', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(extend(args.root.resolve(), args.prior.resolve(strict=True), args.guide.resolve(strict=True)),
                     ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
