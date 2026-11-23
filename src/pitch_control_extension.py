"""Extend direct pitch controls using eligibility in the original voicing only."""

import argparse
from collections import Counter, defaultdict
import json
from math import isclose
import os
from pathlib import Path
from statistics import median

from audio.align import lexical_key
from audio.features import Waveform
from src.minimal_ending_analysis import usable_slots
from src.minimal_pitch_control import (
    MIN_SECONDS, MIN_VOICED, control, pitch_in_band, pitch_readout, target_positions, voiced_core,
)
from src.pilot_validation import read_jsonl, write_json
from src.stage6_listening import digest, read_clip


CORPUS = Path('data/pilot/annotated.jsonl')
RECORDINGS = Path('audio/manifests/synthetic.jsonl')
SYLLABLES = Path('audio/derived/features/syllables.jsonl')
DESTINATION = Path('results/minimal-endings/pitch-extension.json')


def eligible_source(waveform, row, rate):
    left, right = (round(row[key] * rate) for key in ('start_s', 'end_s'))
    if not 0 <= left < right <= len(waveform.samples) or (right - left) / rate < MIN_SECONDS - 1e-9:
        return None
    points = target_positions(waveform, left / rate, right / rate)
    span = voiced_core(points, rate, left, right)
    if span is None:
        return None
    start, end = (sample / rate for sample in span)
    core = target_positions(waveform, start, end)
    if (len(core) < MIN_VOICED or pitch_readout(core)['late_minus_early_st'] is None
            or not pitch_in_band(median(frequency for _, _, frequency in core))):
        return None
    return span


def choose_target(passage, take, observations, waveform, excluded):
    eligible = []
    for index, measured in usable_slots(observations).items():
        slot = passage['slots'][index]
        if index == excluded or index == len(passage['slots']) - 1 or not slot['boundary_after']:
            continue
        phone = measured.get('observed_phone_draft') or {}
        segments, _ = lexical_key(take['intended_pinyin'][index])
        if (phone.get('onset'), phone.get('final')) != segments:
            continue
        span = eligible_source(waveform, measured, take['sample_rate'])
        if span is not None:
            eligible.append((span[1] - span[0], index, measured))
    if not eligible:
        return None, 0
    _, _, target = max(eligible, key=lambda item: (item[0], -item[1]))
    return target, len(eligible)


def run(source, experiment, previous):
    passages = {row['passage_id']: row for row in read_jsonl(source / CORPUS)}
    selected = read_jsonl(source / RECORDINGS)
    takes = {row['recording_id']: row for row in selected}
    if (not takes or len(takes) != len(selected)
            or {row['passage_id'] for row in selected} != passages.keys()
            or len({row['work_id'] for row in passages.values()}) != len(takes)):
        raise ValueError('Expected one canonical WAV per independent work')
    excluded = {row['passage_id']: row['target_slot_index']
                for row in json.loads(previous.read_text(encoding='utf-8'))}
    if not excluded or excluded.keys() - passages.keys():
        raise ValueError('The earlier test sites must belong to the same pinned corpus')
    syllables = defaultdict(list)
    for row in read_jsonl(source / SYLLABLES):
        parent = takes[row['recording_id']]
        if (row['audio_path'] != parent['audio_path'] or row['passage_id'] != parent['passage_id']
                or row.get('audio_sha256') != parent['audio_sha256']):
            raise ValueError('Cached alignment differs from its canonical WAV')
        syllables[row['recording_id']].append(row)
    results = []
    for take in takes.values():
        identifier = take['passage_id']
        passage = passages[identifier]
        if (take['kind'] != 'synthetic' or take['variety'] != 'cmn'
                or take['text_sha256'] != passage['text_sha256']
                or take['text_revision'] != passage['revision_id']
                or len(passage['slots']) != len(take['intended_pinyin'])):
            raise ValueError('Canonical source disagrees with its pinned witness')
        rate, samples = read_clip(source, take, take['sample_rate'])
        if not isclose(len(samples) / rate, take['duration_s'], abs_tol=1e-6, rel_tol=0):
            raise ValueError('Canonical WAV duration differs from its manifest')
        target, count = choose_target(passage, take, syllables[take['recording_id']],
                                      Waveform(source / take['audio_path']), excluded.get(identifier))
        context = {'passage_id': identifier, 'work_id': passage['work_id'], 'genre': passage['genre'],
                   'period': passage['period'], 'han_slots': len(passage['slots']),
                   'text_sha256': passage['text_sha256'], 'previously_tested_work': identifier in excluded,
                   'eligible_baseline_sites': count}
        if target is None:
            results.append({**context, 'status': 'no_eligible_site'})
            continue
        index = target['slot_index']
        result = control(experiment, take, target, target=index, use_voiced_core=True, source_root=source)
        results.append({**context, **result, 'target_character': passage['slots'][index]['char'],
                        'target_pinyin': take['intended_pinyin'][index]})
    verified = [row for row in results if row['status'] == 'verified']
    summary = {'passages_screened': len(results), 'new_sites_rendered': sum('takes' in row for row in results),
               'statuses': dict(Counter(row['status'] for row in results)),
               'verified_previously_untested_works': sum(not row['previously_tested_work'] for row in verified),
               'verified_by_period': dict(Counter(row['period'] for row in verified)),
               'verified_by_genre': dict(Counter(row['genre'] for row in verified)),
               'median_verified_falling_minus_flat_st': median(row['falling_minus_flat_slope_st']
                                                               for row in verified) if verified else None}
    write_json(experiment / DESTINATION,
               {'inputs_sha256': {str(file): digest(source / file) for file in (CORPUS, RECORDINGS, SYLLABLES)},
                'excluded_prior_sites_sha256': digest(previous), 'summary': summary, 'sites': results})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--previous-sites', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(run(args.source.resolve(strict=True), args.root.resolve(), args.previous_sites), allow_nan=False))


if __name__ == '__main__':
    main()
