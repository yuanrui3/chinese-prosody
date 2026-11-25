"""Compare timing in voiced witnesses of variant prose without assigning a listening score."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
import re
from statistics import median

from audio.align import MODEL_REVISION, VOCAB_REVISION, read_rows
from audio.synthesize import ASSET_SHA256, REVISION, SAMPLE_RATE, write_rows
from data.phonology.annotate import syllable_slots
from src.pilot_validation import write_json
from src.quantitative_native_pause_eval import read_wav
from src.quantitative_preboundary_features import observed_pauses


VOICES = ('zm_010', 'zf_001', 'zf_002')


def prepare(config, root):
    records, readings, families, repeats = [], {}, {}, {}
    seen = set()
    for item in config['versions']:
        vid, family, text = item['id'], item['family'], item['text']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', vid) or vid.endswith('-repeat') or vid in seen:
            raise ValueError(f'Unsafe or duplicate version ID {vid}')
        seen.add(vid)
        slots = syllable_slots(text)
        words = item['pinyin'].split()
        if not slots or len(words) != len(slots) or any(not re.fullmatch(r'[a-z]+[1-5]', w) for w in words):
            raise ValueError(f'{vid}: each Han character needs one numbered Mandarin syllable')
        for slot, word in zip(slots, words):
            if slot['marks_after'] not in ('', '，', '；', '。', '、', '？', '！'):
                raise ValueError(f"{vid}: unsupported punctuation {slot['marks_after']!r}")
            slot['readings'] = {'mandarin': {'selected': None, 'candidates': [{'reading': word}]}}
        records_for_version = [vid]
        if family not in repeats:
            repeats[family] = vid
            records_for_version.append(vid + '-repeat')
        for identifier in records_for_version:
            digest = sha256(text.encode()).hexdigest()
            records.append(dict(passage_id=identifier, text=text, slots=slots, text_sha256=digest,
                                revision_id=item['source'], source_url=item['source'],
                                license='Historical work in the public domain. See cited transcription.'))
            readings[identifier] = {'text_sha256': digest, 'clauses': [
                ' '.join(words[s['slot_index']] for s in group)
                for _, group in groupby(slots, key=lambda s: s['clause_index'])]}
            families[identifier] = family
    write_rows(root / 'data/pilot/annotated.jsonl', records)
    write_json(root / 'readings.json', readings)
    write_json(root / 'families.json', families)
    write_json(root / 'repeat-bases.json', repeats)


def phrase_timings(slots, events, detector_status, pauses):
    linked = {e['slot_index']: e for e in events if e['status'] == 'matched'}
    rows = []
    for index, group in groupby(slots, key=lambda s: s['clause_index']):
        phrase = list(group)
        first, last = phrase[0]['slot_index'], phrase[-1]['slot_index']
        left, end, following = linked.get(first), linked.get(last), linked.get(last + 1)
        consecutive = bool(end and following and following['event_index'] == end['event_index'] + 1)
        pause_reason = None
        if last + 1 == len(slots):
            pause_reason = 'recording_end'
        elif not consecutive:
            pause_reason = 'junction_unlinked_or_nonconsecutive'
        elif detector_status != 'ok':
            pause_reason = detector_status
        pause_detected = None if pause_reason else last + 1 in pauses
        if pause_detected is False:
            pause_reason = 'no_assigned_event'
        rows.append({
            'ordinal': index + 1, 'text': ''.join(s['char'] for s in phrase), 'chars': len(phrase),
            'linked_first': bool(left), 'linked_last': bool(end),
            'linked_count': sum(s['slot_index'] in linked for s in phrase),
            'elapsed_ms': round(1000 * (end['end_s'] - left['start_s'])) if left and end else None,
            'final_syllable_ms': round(1000 * (end['end_s'] - end['start_s'])) if end else None,
            'pause_detected': pause_detected,
            'pause_ms': pauses[last + 1] if pause_detected else None,
            'pause_unavailable': pause_reason})
    return rows


def compare(pair, versions):
    rows = []
    for voice in VOICES:
        a, b = (versions[vid, voice] for vid in (pair['a'], pair['b']))
        if len(a['phrases']) != len(b['phrases']):
            raise ValueError(f"{pair['id']}: need a reviewed alignment of phrase ordinals")
        fields = ('elapsed_ms', 'final_syllable_ms', 'pause_ms')
        deltas = {field: [] for field in fields}
        changed, incidence = [], []
        for left, right in zip(a['phrases'], b['phrases']):
            if left['intended_pinyin'] != right['intended_pinyin']:
                changed.append(left['ordinal'])
            incidence.append([left['pause_detected'], right['pause_detected']])
            for field in fields:
                delta = None if left[field] is None or right[field] is None else right[field] - left[field]
                deltas[field].append(delta)
        rows.append({'pair': pair['id'], 'a': pair['a'], 'b': pair['b'], 'voice': voice,
                     'clip_delta_ms': round(1000 * (b['samples'] - a['samples']) / SAMPLE_RATE),
                     'changed_phrase_ordinals': changed, 'pause_incidence_a_b': incidence,
                     'b_minus_a_by_phrase': deltas})
    return rows


def measure(config, root):
    takes = read_rows(root / 'audio/manifests/synthetic.jsonl')
    passages = {r['passage_id']: r for r in read_rows(root / 'data/pilot/annotated.jsonl')}
    expected = {(vid, voice) for vid in passages for voice in VOICES}
    index = {(r['passage_id'], r['speaker']): r for r in takes}
    if len(index) != len(takes) or set(index) != expected:
        raise ValueError('Expected one recording per voice, including the same-input repeats')
    events = defaultdict(list)
    for event in read_rows(root / 'audio/derived/alignment/alignments.jsonl'):
        events[event['recording_id']].append(event)
    repeat_bases = json.loads((root / 'repeat-bases.json').read_text())
    family_controls = defaultdict(set)
    measured, repeats = {}, []
    for (vid, voice), take in index.items():
        path = root / take['audio_path']
        rate, samples, checksum = read_wav(path)
        if rate != SAMPLE_RATE or checksum != take['audio_sha256'] or not len(samples):
            raise ValueError(f'{vid}/{voice}: invalid sample rate, length or original WAV hash')
        if take['text_sha256'] != passages[vid]['text_sha256'] or take['speed'] != .9:
            raise ValueError(f'{vid}/{voice}: text or speed mismatch')
        family_controls[take['control_family']].add((take['seed'], take['voice_embedding_index']))
        if vid.endswith('-repeat'):
            base = repeat_bases[take['control_family']]
            identical = checksum == index[base, voice]['audio_sha256']
            repeats.append({'version': base, 'voice': voice, 'sha256': checksum, 'identical': identical})
            if not identical:
                raise ValueError(f'{vid}/{voice}: same-input repeat differs')
            continue
        links = events[take['recording_id']]
        if not links or any(e['audio_sha256'] != checksum for e in links):
            raise ValueError(f'{vid}/{voice}: missing or stale waveform decode')
        aligned = {e['slot_index']: {'start_s': e['start_s'], 'event': e['event_index']}
                   for e in links if e['status'] == 'matched'}
        detector, pauses = observed_pauses(samples, rate, aligned)
        slots = passages[vid]['slots']
        phrases = phrase_timings(slots, links, detector['status'], pauses)
        for phrase, (_, group) in zip(phrases, groupby(slots, key=lambda s: s['clause_index'])):
            phrase['intended_pinyin'] = [take['intended_pinyin'][s['slot_index']] for s in group]
        measured[vid, voice] = {'version': vid, 'voice': voice, 'family': take['control_family'],
                                'samples': len(samples), 'hash': checksum,
                                'alignment_counts': dict(Counter(e['status'] for e in links)),
                                'detector': detector, 'assigned_pauses_ms': pauses,
                                'phrases': phrases}
    if any(len(settings) != 1 for settings in family_controls.values()):
        raise ValueError('Unmatched seed or voice embedding index within a family')
    for version in config['versions']:
        if len({measured[version['id'], v]['hash'] for v in VOICES}) != len(VOICES):
            raise ValueError(f"{version['id']}: duplicate voice waveform")
    pairs = [row for pair in config['pairs'] for row in compare(pair, measured)]
    result = {'kokoro_revision': REVISION, 'assets': ASSET_SHA256, 'charsiu_revision': MODEL_REVISION,
              'charsiu_vocab_revision': VOCAB_REVISION, 'voices': VOICES, 'rate_hz': SAMPLE_RATE,
              'speed': .9, 'family_seed_embedding': {k: list(next(iter(v))) for k, v in family_controls.items()},
              'repeats': repeats, 'recordings': list(measured.values()), 'comparisons': pairs}
    write_json(root / 'measured.json', result)
    summary = {'versions': len(config['versions']), 'same_input_repeats': len(repeats), 'voice_coverage': {}}
    for voice in VOICES:
        phrases = [p for r in measured.values() if r['voice'] == voice for p in r['phrases']]
        summary['voice_coverage'][voice] = {k: sum(p[k] is not None for p in phrases)
                                           for k in ('elapsed_ms', 'final_syllable_ms', 'pause_ms')}
        summary['voice_coverage'][voice].update(phrases=len(phrases), internal=len(phrases) - len(config['versions']),
                                               pause_incidence_observed=sum(p['pause_detected'] is not None for p in phrases),
                                               no_assigned_event=sum(p['pause_detected'] is False for p in phrases))
    summary['pairs'] = []
    for pair in config['pairs']:
        triple = [r for r in pairs if r['pair'] == pair['id']]
        changed = triple[0]['changed_phrase_ordinals']
        item = {'pair': pair['id'], 'b_minus_a_clip_ms': [r['clip_delta_ms'] for r in triple],
                'changed_phrase_ordinals': changed}
        for field in ('elapsed_ms', 'final_syllable_ms', 'pause_ms'):
            positions = list(zip(*(r['b_minus_a_by_phrase'][field] for r in triple)))
            shared = [(i + 1, v) for i, v in enumerate(positions) if all(x is not None for x in v)]
            item[field] = {'common_ordinals': [i for i, v in shared],
                           'median_delta_by_voice': [median(v[j] for i, v in shared) for j in range(len(VOICES))]
                           if shared else None,
                           'delta_by_common_ordinal': {i: v for i, v in shared},
                           'changed_common': [{
                               'ordinal': i, 'median_ms': median(v), 'delta_ms': v,
                               'all_voices_10ms_direction': 1 if min(v) >= 10 else -1 if max(v) <= -10 else 0}
                               for i, v in shared if i in changed]}
        summary['pairs'].append(item)
    write_json(root / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=('prepare', 'measure'))
    parser.add_argument('config', type=Path)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.step == 'prepare':
        prepare(config, args.root)
    else:
        measure(config, args.root)


if __name__ == '__main__':
    main()
