"""Render the fixed inventory of phrasing pairs with a second Kokoro voice."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median

from audio.align import lexical_key
from audio.synthesize import MALE_VOICE, READINGS, SAMPLE_RATE, SAMPLES_PER_DURATION_FRAME, write_rows
from src.minimal_ending_analysis import usable_slots
from src.pilot_validation import read_jsonl, write_json
from src.recitation_phrasing import (AUDIO, CORPUS, DESTINATION, RECORDINGS, SYLLABLES, TAPER_HALF_MS,
                                     inspect_clause, quiet_cut, render)
from src.recitation_second_aligner_analysis import index_rows
from src.stage6_listening import digest, read_clip, read_json
from src.text_metrics import clauses


SECOND_VOICE = 'zf_001'
FRESH_READINGS = READINGS.with_name('historical_increment_readings.json')
TRANSFER_READINGS = CORPUS.with_name('voice-transfer-readings.json')
DURATION_DRAFTS = Path('audio/derived/synthesis-durations.jsonl')
RENDER_SCREEN = DESTINATION.with_name('render-screen.json')
MAX_GENERATOR_OFFSET_MS = 75
GENERATOR_TIMESTAMP_LEAD_FRAMES = 3
FALLBACK_TAPER_RMS_FRACTION = 0.50
FIXED_SOURCE = ('text_sha256', 'text_revision', 'intended_pinyin', 'intended_model_phonemes', 'seed',
                'speed', 'variety', 'kind', 'style', 'model_revision', 'model_license', 'sample_rate')
SITE_FIELDS = ('pair_id', 'passage_id', 'clause_index', 'clause_text', 'work_id', 'slot_indices',
               'source_set', 'period', 'genre', 'guide_grouping', 'characters_in_test_clause', 'characters_in_passage')


def inventory(reference):
    pairs = read_json(reference / DESTINATION)['pairs']
    if (len(pairs) != 13 or len(index_rows(pairs, 'pair_id')) != 13
            or len({pair['work_id'] for pair in pairs}) != 12
            or any(pair['source']['speaker'] != MALE_VOICE or pair['source']['speed'] != 0.9 for pair in pairs)):
        raise ValueError('Expected the verified 13-site original male-voice benchmark')
    return pairs


def check_clause(pair, passage):
    slots, = [group for group in clauses(passage) if group[0]['clause_index'] == pair['clause_index']]
    if (len(slots) != 4 or [slot['slot_index'] for slot in slots] != pair['slot_indices']
            or ''.join(slot['char'] for slot in slots) != pair['clause_text']
            or len(passage['slots']) != pair['characters_in_passage']):
        raise ValueError('The pinned target clause or the full character count differs')
    return slots


def prepare(project, reference, root):
    passages, prescriptions, witnesses = {}, {}, {}
    recipes = {'guide': read_json(READINGS), 'fresh': read_json(FRESH_READINGS)}
    for pair in inventory(reference):
        source = pair['source']
        origin = Path(source['root']).resolve(strict=True)
        if not origin.is_relative_to(project) or origin == root:
            raise ValueError('The original witnesses must reside in the Gilbreth project')
        if origin not in witnesses:
            witnesses[origin] = index_rows(read_jsonl(origin / CORPUS), 'passage_id')
        pid = pair['passage_id']
        passage = witnesses[origin][pid]
        prescription = recipes[pair['source_set']][pid]
        if (sha256(passage['text'].encode('utf-8')).hexdigest() != source['text_sha256']
                or source['text_sha256'] != passage['text_sha256']
                or source['text_sha256'] != prescription['text_sha256']
                or source['text_revision'] != passage['revision_id'] or passage['work_id'] != pair['work_id']
                or [token for clause in prescription['clauses'] for token in clause.replace('/', ' ').split()]
                != source['intended_pinyin'] or (pid in passages and passages[pid] != passage)):
            raise ValueError('Witness, synthesis prescription, or reading changed from the verified pair')
        check_clause(pair, passage)
        passages[pid], prescriptions[pid] = passage, prescription
    write_rows(root / CORPUS, passages.values())
    write_json(root / TRANSFER_READINGS, prescriptions)
    return {'passages': len(passages), 'pairs': 13, 'speaker': SECOND_VOICE}


def generator_candidate(take, pcm, rate, peak, slots, linked, draft):
    if (any(draft[key] != take[key] for key in ('recording_id', 'audio_sha256', 'text_sha256', 'model_revision'))
            or draft['sample_count'] != len(pcm) or draft['frame_samples'] != SAMPLES_PER_DURATION_FRAME
            or len(draft['slot_spans_samples']) != len(take['intended_pinyin'])):
        raise ValueError('Generator timings must describe the exact second-voice recording and text')
    spans = draft['slot_spans_samples']
    # Anchor the generator coordinates to the median midpoint of actual phone drafts
    # whose segment labels agree with the supplied reading for this recording.
    offsets = []
    for index, match in linked.items():
        phone = match.get('observed_phone_draft') or {}
        if (phone.get('onset'), phone.get('final')) == lexical_key(take['intended_pinyin'][index])[0]:
            offsets.append(rate * (match['start_s'] + match['end_s']) / 2 - sum(spans[index]) / 2)
    if not offsets:
        return None, 'no_independent_phone_anchor_for_generator'
    max_offset = round(rate * MAX_GENERATOR_OFFSET_MS / 1000)
    offset = round(median(offsets))
    # Kokoro's timestamp routine subtracts up to three leading frames. Keep
    # the measured offset and bound its departure from that documented origin.
    nominal = -min(draft['token_frames'][0], GENERATOR_TIMESTAMP_LEAD_FRAMES) * draft['frame_samples']
    if abs(offset - nominal) > max_offset:
        return None, 'generator_offset_outside_limit'
    bounds = []
    for slot in slots:
        index = slot['slot_index']
        start, end = spans[index]
        if not 0 <= start + offset < end + offset <= len(pcm):
            return None, 'generator_span_outside_recording'
        bounds.append({'slot_index': index, 'start_s': (start + offset) / rate, 'end_s': (end + offset) / rate,
                       'observed_phone_draft': (linked.get(index) or {}).get('observed_phone_draft'),
                       'status': 'generator_timing_draft', 'generator_span_samples': [start, end]})
    windows = list(zip(bounds[:2], bounds[1:3]))
    cuts = [quiet_cut(pcm, rate, peak, left, right) for left, right in windows]
    if any(cut is None for cut in cuts):
        cuts = [quiet_cut(pcm, rate, peak, left, right, taper=True, taper_rms_limit=FALLBACK_TAPER_RMS_FRACTION)
                for left, right in windows]
    if any(cut is None for cut in cuts):
        return None, 'generator_has_no_bounded_low_energy_cut'
    minimum = round(rate * 2 * TAPER_HALF_MS / 1000)
    if cuts[1]['source_sample_index'] - cuts[0]['source_sample_index'] < minimum:
        return None, 'generator_taper_windows_overlap'
    return {'syllables': bounds, 'cuts': cuts, 'generator_offset_samples': offset,
            'generator_nominal_offset_samples': nominal,
            'generator_phone_anchor_count': len(offsets)}, None


def build(reference, root):
    targets = inventory(reference)
    passages = index_rows(read_jsonl(root / CORPUS), 'passage_id')
    takes = index_rows(read_jsonl(root / RECORDINGS), 'passage_id')
    durations = index_rows(read_jsonl(root / DURATION_DRAFTS), 'recording_id')
    if not passages.keys() == takes.keys() == {row['passage_id'] for row in targets}:
        raise ValueError('Second-voice synthesis must cover the unchanged source inventory')
    draft_rows = defaultdict(list)
    for row in read_jsonl(root / SYLLABLES):
        source = takes[row['passage_id']]
        if any(row[key] != source[key] for key in ('recording_id', 'audio_path', 'audio_sha256')):
            raise ValueError('Phone draft changed recording identity')
        draft_rows[row['recording_id']].append(row)
    (root / AUDIO).mkdir(parents=True, exist_ok=True)
    pairs, screens = [], []
    for target in targets:
        pid = target['passage_id']
        take = takes[pid]
        if (take['speaker'] != SECOND_VOICE or take['sample_rate'] != SAMPLE_RATE
                or any(take[key] != target['source'][key] for key in FIXED_SOURCE)
                or take['audio_sha256'] == target['source']['audio_sha256']):
            raise ValueError('Second-voice synthesis changed a controlled setting or reused the old waveform')
        slots = check_clause(target, passages[pid])
        rate, pcm = read_clip(root, take, SAMPLE_RATE)
        peak = max(map(abs, pcm))
        linked = usable_slots(draft_rows[take['recording_id']])
        fields = {key: target[key] for key in SITE_FIELDS}
        candidate, draft_failure = inspect_clause(take, linked, slots, pcm, rate, peak)
        method, failure = 'charsiu_exact', None
        if candidate is None:
            method = 'kokoro_generator_duration'
            candidate, failure = generator_candidate(take, pcm, rate, peak, slots, linked,
                                                      durations[take['recording_id']])
        screen = {**fields, 'status': 'selected' if candidate else 'unresolved', 'reason': failure,
                  'placement_method': method, 'phone_draft_rejection': draft_failure}
        screens.append(screen)
        if candidate is not None:
            pair = {**screen, **candidate, 'source': {**take, 'root': str(root), 'sample_count': len(pcm)}}
            pair['sham'], pair['variants'] = render(root, take, pcm, rate, pair)
            pairs.append(pair)
    summary = {'requested_pairs': len(targets), 'rendered_pairs': len(pairs),
               'placement_methods': dict(Counter(pair['placement_method'] for pair in pairs)),
               'unresolved': {row['pair_id']: row['reason'] for row in screens if row['status'] == 'unresolved'}}
    write_json(root / RENDER_SCREEN, {'summary': summary, 'screens': screens})
    if len(pairs) != len(targets):
        raise ValueError(f'The pilot requires the same sites in both voices: {summary}')
    write_json(root / DESTINATION, {'reference_stimuli_sha256': digest(reference / DESTINATION),
                                    'summary': summary, 'pairs': pairs, 'screens': screens})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--render', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    project, reference, root = (path.resolve(strict=True) for path in (args.project, args.reference, args.root))
    if len({project, reference, root}) != 3 or not (root.is_relative_to(project) and reference.is_relative_to(project)):
        raise ValueError('Use separate private experiment roots within the Gilbreth project')
    print(json.dumps(prepare(project, reference, root) if args.prepare else build(reference, root), allow_nan=False))


if __name__ == '__main__':
    main()
