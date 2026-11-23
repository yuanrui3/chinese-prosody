"""Build fixed-text pause-distribution controls from existing Gilbreth WAVs."""

import argparse
from array import array
from collections import Counter, defaultdict
from hashlib import sha256
from math import cos, isclose, pi, sqrt
import os
from pathlib import Path
import re

from audio.align import lexical_key
from src.minimal_ending_analysis import usable_slots
from src.minimal_pitch_control import write_wav
from src.pilot_validation import read_jsonl, write_json
from src.stage6_listening import digest, read_clip
from src.text_metrics import clauses


CORPUS = Path('data/pilot/annotated.jsonl')
RECORDINGS = Path('audio/manifests/synthetic.jsonl')
SYLLABLES = Path('audio/derived/features/syllables.jsonl')
DESTINATION = Path('results/recitation-phrasing/stimuli.json')
AUDIO = Path('audio/raw/recitation-phrasing')
GUIDE_CLAUSES = {'日暮途遠': '2+2', '人間何世': '1+1+2'}
CONDITIONS = ('two_two', 'one_one_two')
TOTAL_PAUSE_MS = 80
BOUNDARY_ALLOWANCE_MS = 20
QUIET_HALF_WINDOW_MS = 2
MAX_EDGE_FRACTION = 0.005
MAX_WINDOW_RMS_FRACTION = 0.03
TAPER_HALF_MS = 5
MAX_TAPER_RMS_FRACTION = 0.25


def quiet_cut(pcm, rate, peak, left, right, *, taper=False,
              taper_rms_limit=MAX_TAPER_RMS_FRACTION):
    """Choose a quiet splice from baseline PCM, with an optional shared taper."""
    allowance = round(rate * BOUNDARY_ALLOWANCE_MS / 1000)
    radius = max(1, round(rate * (TAPER_HALF_MS if taper else QUIET_HALF_WINDOW_MS) / 1000))
    rms_limit = taper_rms_limit if taper else MAX_WINDOW_RMS_FRACTION
    edge = round(left['end_s'] * rate)
    onset = round(right['start_s'] * rate)
    first = max(radius, edge - allowance)
    last = min(len(pcm) - radius, onset + allowance)
    if peak == 0 or edge > onset or first > last:
        return None

    squares = [0]
    for sample in pcm[first - radius:last + radius]:
        squares.append(squares[-1] + sample * sample)
    choices = []
    for point in range(first, last + 1):
        if not taper and max(abs(pcm[point - 1]), abs(pcm[point])) > peak * MAX_EDGE_FRACTION:
            continue
        energy = squares[point - first + 2 * radius] - squares[point - first]
        rms_fraction = sqrt(energy / (2 * radius)) / peak
        if rms_fraction <= rms_limit:
            distance = abs(point - (edge + onset) / 2)
            choices.append((rms_fraction, distance, point))
    if not choices:
        return None
    rms_fraction, _, point = min(choices)
    return {'source_sample_index': point, 'baseline_window_rms_fraction': rms_fraction,
            'method': 'shared_taper' if taper else 'quiet_splice',
            'inside_draft_gap': edge <= point <= onset, 'draft_gap_start_s': edge / rate,
            'draft_gap_end_s': onset / rate}


def inspect_clause(take, linked, slots, pcm, rate, peak, *, recovered_slot=None):
    rows = []
    for slot in slots:
        index = slot['slot_index']
        baseline = linked.get(index)
        phone = baseline.get('observed_phone_draft') if baseline else None
        segments, _ = lexical_key(take['intended_pinyin'][index])
        recovered = (index == recovered_slot and baseline is not None
                     and baseline['status'] == 'recovered_timing_draft'
                     and tuple(baseline['supported_segments']) == segments)
        if (baseline is None or baseline['char'] != slot['char']
                or (not recovered and (not phone or (phone['onset'], phone['final']) != segments))):
            return None, 'missing_exact_segment_link'
        if not 0 <= baseline['start_s'] < baseline['end_s'] <= len(pcm) / rate + 1e-6:
            raise ValueError(f"{take['recording_id']}: invalid baseline syllable bounds")
        rows.append(baseline)
    if any(a.get('last_event_index', a['event_index']) + 1 != b['event_index'] or a['end_s'] > b['start_s'] + 1e-6
           for a, b in zip(rows, rows[1:])):
        return None, 'nonadjacent_draft_syllables'
    boundaries = list(zip(rows[:2], rows[1:3]))
    cuts = [quiet_cut(pcm, rate, peak, left, right) for left, right in boundaries]
    if any(cut is None for cut in cuts):
        # If a taper is needed, select both 10 ms windows from the same baseline
        # RMS criterion so treatment allocation cannot influence the boundaries.
        cuts = [quiet_cut(pcm, rate, peak, left, right, taper=True) for left, right in boundaries]
    if any(cut is None for cut in cuts):
        return None, 'no_bounded_low_energy_cut'
    if cuts[0]['source_sample_index'] >= cuts[1]['source_sample_index']:
        return None, 'nonmonotonic_cuts'
    if cuts[0]['method'] == 'shared_taper':
        radius = max(1, round(rate * TAPER_HALF_MS / 1000))
        if cuts[0]['source_sample_index'] + 2 * radius > cuts[1]['source_sample_index']:
            return None, 'overlapping_taper_windows'
    syllables = [
        {field: row[field] for field in ('slot_index', 'start_s', 'end_s', 'observed_phone_draft')}
        for row in rows
    ]
    if recovered_slot is not None:
        for row, syllable in zip(rows, syllables):
            syllable['status'] = row['status']
    return {'syllables': syllables, 'cuts': cuts}, None


def insert_silence(source, edits):
    """Construct the variant without altering any original PCM sample."""
    result = array('h')
    start = 0
    for edit in edits:
        cut, count = edit['source_sample_index'], edit['inserted_samples']
        if not start < cut < len(source) or count <= 0:
            raise ValueError('Splice edits require increasing source offsets and positive silence')
        result.extend(source[start:cut])
        result.extend(array('h', [0]) * count)
        start = cut
    result.extend(source[start:])
    return result


def verify_variant(source, modified, edits):
    restored = array('h')
    previous = added = 0
    for edit in edits:
        start = edit['source_sample_index'] + added
        end = start + edit['inserted_samples']
        if any(modified[start:end]):
            raise ValueError('Edited interval contains nonzero samples')
        restored.extend(modified[previous:start])
        previous = end
        added += edit['inserted_samples']
    restored.extend(modified[previous:])
    if restored != source or len(modified) != len(source) + added:
        raise ValueError('Removing inserted silence did not reconstruct the original PCM')


def carrier_pcm(source, rate, cuts):
    """Taper both sites identically before assigning any added pause."""
    if all(cut['method'] == 'quiet_splice' for cut in cuts):
        return source, []
    radius = max(1, round(rate * TAPER_HALF_MS / 1000))
    result = array('h', source)
    tapers = []
    last_end = 0
    for boundary, cut in enumerate(cuts, start=1):
        point = cut['source_sample_index']
        start, end = point - radius, point + radius
        if not last_end <= start < end <= len(source):
            raise ValueError('Shared taper windows overlap or lie outside the source')
        for index in range(start, end):
            gain = (1 - cos(pi * abs(index - point) / radius)) / 2
            result[index] = round(source[index] * gain)
        tapers.append({'after_slot': boundary, 'source_start_sample': start, 'source_end_sample': end,
                       'source_sample_index': point})
        last_end = end
    return result, tapers


def verify_carrier(source, carrier, tapers):
    previous = 0
    for window in tapers:
        start, end = window['source_start_sample'], window['source_end_sample']
        if carrier[previous:start] != source[previous:start]:
            raise ValueError('Shared taper altered samples outside its windows')
        previous = end
    if len(carrier) != len(source) or carrier[previous:] != source[previous:]:
        raise ValueError('Shared taper altered length or samples outside its windows')


def write_member(root, take, pcm, rate, recording_id, **details):
    path = root / AUDIO / f'{recording_id}.wav'
    write_wav(path, pcm, rate)
    member = {**take, 'recording_id': recording_id, 'audio_path': str(path.relative_to(root)),
              'audio_sha256': digest(path), 'duration_s': len(pcm) / rate, 'sample_count': len(pcm), **details}
    _, written = read_clip(root, member, rate)
    if written != pcm or path.stat().st_mode & 0o077:
        raise ValueError('Written PCM or permissions differ from the verified manifest')
    return member, written


def render(root, take, pcm, rate, pair):
    carrier, tapers = carrier_pcm(pcm, rate, pair['cuts'])
    sham, written = write_member(root, take, carrier, rate, f"{pair['pair_id']}-sham", tapers=tapers)
    verify_carrier(pcm, written, tapers)
    half = round(rate * TOTAL_PAUSE_MS / 2000)
    variants = {}
    for role, planned in zip(CONDITIONS, (((2, 2 * half),), ((1, half), (2, half)))):
        edits = [{'after_slot': boundary, 'source_sample_index': pair['cuts'][boundary - 1]['source_sample_index'],
                  'inserted_samples': count} for boundary, count in planned]
        recording_id = f"{pair['pair_id']}-{role}"
        member, edited = write_member(root, take, insert_silence(carrier, edits), rate, recording_id,
                                      insertions=edits)
        verify_variant(carrier, edited, edits)
        if len(edited) != len(carrier) + 2 * half:
            raise ValueError('Variant duration differs from the shared pause budget')
        variants[role] = member
    return sham, variants


def clean_label(value):
    if not re.fullmatch('[A-Za-z0-9_-]+', value):
        raise ValueError('Expected a simple passage identifier')
    return value


def build_source(root, source, label):
    passages = {row['passage_id']: row for row in read_jsonl(source / CORPUS)}
    takes = read_jsonl(source / RECORDINGS)
    take_by_id = {row['recording_id']: row for row in takes}
    if not takes or len(take_by_id) != len(takes) or len({take['passage_id'] for take in takes}) != len(takes):
        raise ValueError('Expected one canonical baseline per passage')
    syllables = defaultdict(list)
    for row in read_jsonl(source / SYLLABLES):
        parent = take_by_id[row['recording_id']]
        if any(row.get(field) != parent[field] for field in ('audio_path', 'audio_sha256', 'passage_id')):
            raise ValueError('Cached syllables disagree with the canonical waveform')
        syllables[row['recording_id']].append(row)

    screens = []
    pairs = []
    seen_guides = set()
    for take in takes:
        pid = clean_label(take['passage_id'])
        if label == 'guide' and pid != 'SD01':
            continue
        passage = passages[pid]
        work_id = passage['work_id']
        if (take['kind'] != 'synthetic' or take['variety'] != 'cmn' or take['speaker'] != 'zm_010'
                or take['speed'] != 0.9 or take['text_revision'] != passage['revision_id']
                or take['text_sha256'] != passage['text_sha256']
                or sha256(passage['text'].encode('utf-8')).hexdigest() != take['text_sha256']
                or len(take['intended_pinyin']) != len(passage['slots'])):
            raise ValueError(f'{pid}: source did not match the pinned text and male voice condition')
        rate, pcm = read_clip(source, take, take['sample_rate'])
        if not isclose(len(pcm) / rate, take['duration_s'], abs_tol=1e-6, rel_tol=0):
            raise ValueError(f'{pid}: WAV duration differs from the manifest')
        peak = max(map(abs, pcm), default=0)
        linked = usable_slots(syllables[take['recording_id']])
        eligible = []
        for slots in clauses(passage):
            text = ''.join(slot['char'] for slot in slots)
            if len(slots) != 4 or (label == 'guide' and text not in GUIDE_CLAUSES):
                continue
            if label == 'guide':
                seen_guides.add(text)
            index = slots[0]['clause_index']
            screen = {'pair_id': f'{pid}-clause-{index:02d}', 'passage_id': pid, 'work_id': work_id,
                      'clause_index': index, 'clause_text': text, 'source_set': label,
                      'period': passage['period'], 'genre': passage['genre'],
                      'guide_grouping': GUIDE_CLAUSES.get(text) if label == 'guide' else None,
                      'slot_indices': [slot['slot_index'] for slot in slots]}
            candidate, reason = inspect_clause(take, linked, slots, pcm, rate, peak)
            screen.update(status='ineligible' if reason else 'eligible_unselected', reason=reason)
            screens.append(screen)
            if candidate is not None:
                eligible.append((screen, candidate))
        if label == 'fresh' and eligible:
            # Favor the quietest worse cut, with a fixed clause-order tie break.
            eligible = [min(eligible, key=lambda item: (
                item[1]['cuts'][0]['method'] != 'quiet_splice',
                max(cut['baseline_window_rms_fraction'] for cut in item[1]['cuts']), item[0]['clause_index'],
            ))]
        for screen, candidate in eligible:
            screen['status'] = 'selected'
            pair = {**screen, **candidate, 'source': {'root': str(source), **take,
                    'sample_count': len(pcm)}, 'characters_in_test_clause': 4,
                    'characters_in_passage': len(passage['slots'])}
            pair['sham'], pair['variants'] = render(root, take, pcm, rate, pair)
            pairs.append(pair)
    if label == 'guide' and seen_guides != GUIDE_CLAUSES.keys():
        raise ValueError('The pinned SD01 excerpt lacks the two expected guide clauses')
    return screens, pairs


def run(root, guide, fresh):
    if len({root, guide, fresh}) != 3:
        raise ValueError('Use separate input and experiment roots')
    output = root / DESTINATION
    for directory in (root / AUDIO, output.parent):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or directory.stat().st_mode & 0o077:
            raise ValueError(f'Experiment paths must be private directories: {directory}')
    os.umask(0o077)
    sources = {'guide': guide, 'fresh': fresh}
    screens, pairs = [], []
    for label, source in sources.items():
        screened, rendered = build_source(root, source, label)
        screens.extend(screened)
        pairs.extend(rendered)
    if len({item['pair_id'] for item in pairs}) != len(pairs):
        raise ValueError('Expected unique clause identifiers')
    summary = {'screened': len(screens), 'rendered_pairs': len(pairs), 'output_wavs': 3 * len(pairs),
               'status_counts': dict(Counter(row['status'] for row in screens)),
               'ineligibility_counts': dict(Counter(row['reason'] for row in screens if row['reason'])),
               'by_genre': dict(Counter(row['genre'] for row in pairs)),
               'by_period': dict(Counter(row['period'] for row in pairs)),
               'by_source_set': dict(Counter(row['source_set'] for row in pairs)),
               'by_splice_method': dict(Counter(row['cuts'][0]['method'] for row in pairs)),
               'guide_sites': {row['clause_text']: row['reason'] or row['status'] for row in screens
                               if row['source_set'] == 'guide'}}
    write_json(output, {'summary': summary, 'pairs': pairs, 'screens': screens,
                        'inputs_sha256': {label: {str(path): digest(source / path)
                                                  for path in (CORPUS, RECORDINGS, SYLLABLES)}
                                          for label, source in sources.items()},
                        'conditions': list(CONDITIONS), 'planned_added_pause_ms': TOTAL_PAUSE_MS,
                        'baseline_boundary_allowance_ms': BOUNDARY_ALLOWANCE_MS,
                        'shared_taper_half_window_ms': TAPER_HALF_MS,
                        'shared_taper_max_window_rms_fraction_of_source_peak': MAX_TAPER_RMS_FRACTION,
                        'scope': 'fixed-text pause placement in synthetic Mandarin at pre-selected draft boundaries'})
    if not pairs:
        raise ValueError('No source clause passed the boundary screen; see the saved screening results')
    return summary


def main():
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--guide', required=True, type=Path)
    parser.add_argument('--fresh', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(run(args.root.resolve(), args.guide.resolve(strict=True), args.fresh.resolve(strict=True)),
                     ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
