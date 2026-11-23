"""Check whether a fresh phone draft resolves the pause placement in each pair."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
from statistics import median

from audio.align import MODEL_REVISION, MandarinDecoder, heard_syllables, link_slots, read_rows
from src.pilot_validation import write_json
from src.stage6_listening import digest, read_json


RESULTS = Path('results/recitation-phrasing')
ROLES = ('carrier', 'two_two', 'one_one_two')


def decode(decoder, root, recording, slots):
    path = (root / recording['audio_path']).resolve(strict=True)
    if not path.is_relative_to(root / 'audio') or digest(path) != recording['audio_sha256']:
        raise ValueError('Decoder input is outside the audio directory or differs from its manifest')
    links = link_slots(slots, heard_syllables(decoder.decode(path)))
    return {slot['slot_index']: (index, sound) for index, (slot, sound, status, _) in enumerate(links)
            if slot is not None and status == 'matched'}


def gaps(takes, indices):
    """Match both neighboring sounds across takes before measuring each gap."""
    result = []
    for left, right in zip(indices, indices[1:]):
        triplet = [(take.get(left), take.get(right)) for take in takes]
        if any(a is None or b is None or b[0] != a[0] + 1 for a, b in triplet):
            result.append(None)
            continue
        if len({(a[1].key, b[1].key) for a, b in triplet}) != 1:
            result.append(None)
            continue
        result.append({role: round(1000 * (b[1].phones[0].start_s - a[1].phones[-1].end_s), 6)
                       for role, (a, b) in zip(ROLES, triplet)})
    return result


def analyze(project, root):
    manifest = root / RESULTS / 'stimuli.json'
    pairs = read_json(manifest)['pairs']
    if not pairs or len({pair['pair_id'] for pair in pairs}) != len(pairs):
        raise ValueError('Expected a nonempty set of unique verified pairs')
    decoder = MandarinDecoder(project, offline=True)
    passages = {}
    rows = []
    for pair in pairs:
        source = pair['source']
        source_root = Path(source['root']).resolve(strict=True)
        if not source_root.is_relative_to(project):
            raise ValueError('Source lies outside the Gilbreth project')
        if source_root not in passages:
            passages[source_root] = {row['passage_id']: row for row in
                                     read_rows(source_root / 'data/pilot/annotated.jsonl')}
        passage = passages[source_root][pair['passage_id']]
        slots = passage['slots']
        indices = pair['slot_indices']
        if (len(indices) != 4 or indices != list(range(indices[0], indices[0] + 4))
                or ''.join(slots[i]['char'] for i in indices) != pair['clause_text']):
            raise ValueError('Expected four consecutive written slots in the exact witness')
        takes = [decode(decoder, root, pair['sham'], slots)]
        takes.extend(decode(decoder, root, pair['variants'][role], slots) for role in ROLES[1:])
        measured = gaps(takes, indices)
        changes = [None if gap is None else round(gap['one_one_two'] - gap['two_two'], 6)
                   for gap in measured]
        rows.append({'pair_id': pair['pair_id'], 'passage_id': pair['passage_id'],
                     'clause_text': pair['clause_text'], 'gaps_ms': measured, 'split_minus_concentrated_ms': changes})
    complete = [row for row in rows if None not in row['split_minus_concentrated_ms'][:2]]
    boundary_summaries = []
    for index in range(3):
        values = [row['split_minus_concentrated_ms'][index] for row in rows
                  if row['split_minus_concentrated_ms'][index] is not None]
        boundary_summaries.append({'boundary': index + 1, 'measured': len(values),
                                   'median_split_minus_concentrated_ms': median(values) if values else None})
    summary = {'pairs': len(rows), 'two_boundary_coverage': len(complete),
               'both_directions_recovered': sum(row['split_minus_concentrated_ms'][0] > 0
                                                and row['split_minus_concentrated_ms'][1] < 0 for row in complete),
               'fully_measured_by_passage': dict(Counter(row['passage_id'] for row in complete)),
               'boundaries': boundary_summaries}
    write_json(root / RESULTS / 'decoder.json', {'model_revision': MODEL_REVISION,
               'frame_ms': 1000 * decoder.step_s, 'manifest_sha256': digest(manifest),
               'summary': summary, 'pairs': rows})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(analyze(args.project.resolve(strict=True), args.root.resolve(strict=True)), allow_nan=False))


if __name__ == '__main__':
    main()
