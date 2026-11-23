"""Report written prosody and complete-clause timing on paired synthetic deliveries."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from math import isclose
import os
from pathlib import Path
from random import Random
from statistics import mean, median

from data.phonology.annotate import syllable_slots
from src.audio_validation import rank_association
from src.expansion_design import authors
from src.pilot_validation import read_jsonl
from src.quantitative_alignment_audit import audit
from src.stage6_listening import digest, read_clip, read_json, write_json
from src.stage7_cli import write_output
from src.text_metrics import clauses, text_metric_support


VOICES = ('zm_010', 'zf_001')
GENRES = ('parallel_prose', 'comparison_prose')
PERIODS = ('sixth-century', 'early-tang')
TEXT_METRICS = ('clause_mean_slots', 'clause_npvi', 'clause_46_share')
HISTORICAL_METRICS = ('clause_end_pz_alternation', 'clause_end_rhyme_repeat')
TIERS = ('guangyun', 'pingshui')
FILES = {
    'passages': Path('data/pilot/annotated.jsonl'),
    'takes': Path('audio/manifests/synthetic.jsonl'),
    'syllables': Path('audio/derived/features/syllables.jsonl'),
    'recordings': Path('audio/derived/features/recordings.jsonl'),
}
DRAW_COUNT = 999
SEED = 20261122


def index(rows, key):
    result = {key(row): row for row in rows}
    if len(result) != len(rows):
        raise ValueError('Duplicate passage, take, or clause identifier')
    return result


def check_inventory(passages):
    pairs, claims = defaultdict(list), set()
    seen_works, seen_authors = set(), set()
    for row in passages.values():
        credits = authors(row)
        if row['work_id'] in seen_works or not credits or credits & seen_authors:
            raise ValueError('Expected unique works and credited authors')
        seen_works.add(row['work_id'])
        seen_authors.update(credits)
        pairs[row['pair_id']].append(row)
        if row['period'] not in PERIODS or row['genre'] not in GENRES:
            raise ValueError('Expected sixth-century or Early Tang historical prose')
        claims.add(row['period'])
        literal = syllable_slots(row['text'])
        if (not literal or len(literal) != row['han_count'] or len(literal) != len(row['slots'])
                or any(any(slot[key] != value for key, value in expected.items())
                       for slot, expected in zip(row['slots'], literal))
                or sha256(row['text'].encode()).hexdigest() != row['text_sha256']):
            raise ValueError('Annotated slots do not match the pinned text')
    if claims != set(PERIODS):
        raise ValueError('Expected coverage of both periods')
    for pair in pairs.values():
        if (len(pair) != 2 or {row['genre'] for row in pair} != set(GENRES)
                or pair[0]['period'] != pair[1]['period']):
            raise ValueError('Each pair needs one parallel and one period-matched comparison passage')
    return pairs


def linked_timing(root, passage, take, recording, events):
    immutable = ('recording_id', 'passage_id', 'audio_path')
    if (any(recording[field] != take[field] for field in immutable)
            or any(any(event[field] != take[field] for field in (*immutable, 'audio_sha256')) for event in events)
            or take['text_sha256'] != passage['text_sha256'] or take['text_revision'] != passage['revision_id']
            or (take['kind'], take['variety'], take['style'], take['speed'], take['sample_rate'])
            != ('synthetic', 'cmn', 'controlled_read_speech', 0.9, 24000)):
        raise ValueError('A waveform or phone draft is not linked to the exact synthesis input')
    path = root / take['audio_path']
    rate, pcm = read_clip(root, take, take['sample_rate'])
    duration = len(pcm) / rate
    if (not pcm or path.stat().st_mode & 0o077 or not all(isclose(item, duration, abs_tol=1e-6, rel_tol=0)
            for item in (take['duration_s'], recording['waveform_duration_s']))):
        raise ValueError('Unexpected WAV duration or permissions')
    slots = index(passage['slots'], lambda row: row['slot_index'])
    measured = index([row for row in events if row['duration_ms'] is not None], lambda row: row['slot_index'])
    for number, event in measured.items():
        slot = slots[number]
        if (event['char'] != slot['char'] or event['clause_index'] != slot['clause_index']
                or event['status'] != 'matched' or event.get('realized_reading') is not None
                or not 0 <= event['start_s'] < event['end_s'] <= duration + 1e-6
                or not isclose(event['duration_ms'], 1000 * (event['end_s'] - event['start_s']), abs_tol=1e-6)):
            raise ValueError('A complete timing measurement contains an invalid draft link')
    recorded_clauses = index(recording['clauses'], lambda row: row['clause_index'])
    lines = clauses(passage)
    if (set(recorded_clauses) != {line[0]['clause_index'] for line in lines}
            or (recording['slots_expected'], recording['slots_measured']) != (len(slots), len(measured))):
        raise ValueError('Recorded coverage differs from the actual phone drafts')
    amounts, bracketed = {}, {}
    for line in lines:
        ident = line[0]['clause_index']
        widths = [measured[slot['slot_index']]['duration_ms'] for slot in line if slot['slot_index'] in measured]
        result = sum(widths) if len(widths) == len(line) else None
        published = recorded_clauses[ident]
        stored_ms = published['articulation_ms']
        same_timing = (stored_ms is None if result is None else stored_ms is not None
                       and isclose(stored_ms, result, abs_tol=1e-6, rel_tol=0))
        if ((len(line), len(widths)) != (published['slots_expected'], published['slots_measured'])
                or not same_timing):
            raise ValueError('Clause summary differs from the waveform-linked measurements')
        amounts[ident] = result
        first, last = (measured.get(line[i]['slot_index']) for i in (0, -1))
        bracketed[ident] = 1000 * (last['end_s'] - first['start_s']) if first and last else None
    return {'recording_id': take['recording_id'], 'audio_sha256': take['audio_sha256'],
            'audio_path': take['audio_path'], 'duration_ms': 1000 * duration,
            'written_slots_per_second': len(slots) / duration, 'slots_linked': len(measured),
            'complete_clauses': sum(value is not None for value in amounts.values()),
            'bracketed_clauses': sum(value is not None for value in bracketed.values()),
            'articulation_ms': amounts, 'bracketed_elapsed_ms': bracketed}


def passage_profile(root, passage, takes, recordings, events):
    pid = passage['passage_id']
    pair = [takes[pid, voice] for voice in VOICES]
    for field in ('intended_pinyin', 'intended_model_phonemes', 'seed', 'model_revision', 'model_license'):
        if pair[0][field] != pair[1][field]:
            raise ValueError(f'{pid}: voice comparison changed {field}')
    if pair[0]['audio_sha256'] == pair[1]['audio_sha256']:
        raise ValueError('The same WAV cannot represent two voices')
    summaries = {voice: linked_timing(root, passage, take, recordings[take['recording_id']],
                                     events[take['recording_id']]) for voice, take in zip(VOICES, pair)}
    support = {tier: text_metric_support(passage, tier) for tier in TIERS}
    rows = []
    for line in clauses(passage):
        ident = line[0]['clause_index']
        start, end = line[0]['offset'], line[-1]['offset'] + 1 + len(line[-1]['marks_after'])
        rows.append({'clause_index': ident, 'text': passage['text'][start:end], 'slots': len(line),
                     **{key: {voice: item[key][ident] for voice, item in summaries.items()}
                        for key in ('articulation_ms', 'bracketed_elapsed_ms')}})
    return {'witness': {field: passage[field] for field in ('passage_id', 'pair_id', 'work_id', 'title', 'author',
                'period', 'genre', 'text_sha256', 'revision_id', 'source_url', 'license', 'attribution', 'date',
                'selection_note', 'insert_punctuation_after') if field in passage},
            'text': passage['text'], 'slots': len(passage['slots']), 'clauses': rows,
            '音律美': {'written_rhythm': {name: support[TIERS[0]][name] for name in TEXT_METRICS},
                       'historical_endings': {tier: {name: values[name] for name in HISTORICAL_METRICS}
                                              for tier, values in support.items()},
                       'recorded_timing': {voice: {key: value for key, value in item.items()
                                                   if key not in ('articulation_ms', 'bracketed_elapsed_ms')}
                                           for voice, item in summaries.items()}},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None}}


def held_out(work_rows, lengths, metric='articulation_ms'):
    """A count-only baseline and a constant baseline, fit without the evaluated work."""
    results = {}
    for voice in VOICES:
        levels = {work: (mean(row[metric][voice] for row in rows),
                         mean(row[metric][voice] / count for row, count in zip(rows, lengths[work])))
                  for work, rows in work_rows.items()}
        errors = {}
        for work, rows in work_rows.items():
            rest = [pair for key, pair in levels.items() if key != work]
            center, per_char = map(mean, zip(*rest))
            observed = [row[metric][voice] for row in rows]
            errors[work] = {'constant_ms': mean(abs(center - value) for value in observed),
                            'count_ms': mean(abs(per_char * count - value) for count, value in
                                             zip(lengths[work], observed))}
        results[voice] = {name: mean(row[name] for row in errors.values()) for name in ('constant_ms', 'count_ms')}
        results[voice]['errors_by_work'] = errors
    return results


def validation(profiles, metric='articulation_ms'):
    matched = {profile['witness']['work_id']: [row for row in profile['clauses']
               if None not in row[metric].values()] for profile in profiles}
    work_rows = {work: rows for work, rows in matched.items() if rows}
    paired = [row for rows in work_rows.values() for row in rows]
    summary = {'total_clauses': sum(len(item['clauses']) for item in profiles), 'shared_clauses': len(paired),
               'works_with_shared_clauses': len(work_rows),
               'shared_clauses_by_work': {work: len(rows) for work, rows in matched.items()},
               'cross_voice_articulation_ranks': rank_association([{
                   'text': row[metric][VOICES[0]], 'acoustic': row[metric][VOICES[1]],
               } for row in paired], unit='common clauses'),
               'cross_voice_median_absolute_difference_ms': median(abs(row[metric][VOICES[0]]
                   - row[metric][VOICES[1]]) for row in paired) if paired else None}
    if len(work_rows) < 2:
        return {**summary, 'held_out_timing': None, 'length_shuffle_control': None}
    lengths = {work: [row['slots'] for row in rows] for work, rows in work_rows.items()}
    observed = held_out(work_rows, lengths, metric)
    varying = sum(len(set(values)) > 1 for values in lengths.values())
    control = None
    if varying:
        rng = Random(SEED)
        null = defaultdict(list)
        for _ in range(DRAW_COUNT):
            shuffled = {work: rng.sample(values, len(values)) for work, values in lengths.items()}
            for voice, result in held_out(work_rows, shuffled, metric).items():
                null[voice].append(result['count_ms'])
        control = {'seed': SEED, 'draws': DRAW_COUNT, 'works_with_variable_length': varying, 'voices': {
            voice: {'null_median_count_mae_ms': median(values), 'lower_tail_fraction':
                    (1 + sum(value <= observed[voice]['count_ms'] + 1e-9 for value in values)) / (1 + DRAW_COUNT)}
            for voice, values in null.items()}}
    return {**summary, 'held_out_timing': observed, 'length_shuffle_control': control}


def show(value, digits=2):
    return f'{value:.{digits}f}' if value is not None else 'Unavailable'


def matched_contrasts(pairs, profiles):
    by_passage = index(profiles, lambda row: row['witness']['passage_id'])
    contrasts = []
    for pair_id, pair in pairs.items():
        genres = index(pair, lambda row: row['genre'])
        parallel, prose = [by_passage[genres[genre]['passage_id']] for genre in GENRES]
        parallel_rhythm, prose_rhythm = (row['音律美']['written_rhythm'] for row in (parallel, prose))
        values = {}
        for metric in TEXT_METRICS:
            a, b = parallel_rhythm[metric]['value'], prose_rhythm[metric]['value']
            values[metric] = a - b if a is not None and b is not None else None
        voice_ms = {voice: (parallel['音律美']['recorded_timing'][voice]['duration_ms'] / parallel['slots']
                            - prose['音律美']['recorded_timing'][voice]['duration_ms'] / prose['slots'])
                    for voice in VOICES}
        contrasts.append({'pair_id': pair_id, 'period': pair[0]['period'],
                          'parallel_id': parallel['witness']['passage_id'], 'prose_id': prose['witness']['passage_id'],
                          'written_rhythm_difference': values, 'clip_ms_per_han_difference_by_voice': voice_ms})
    return contrasts


def render_timing_check(title, result):
    lines = ['', f'### {title}', '', f"Both voices have timings for {result['shared_clauses']} of "
             f"{result['total_clauses']} clauses. Median absolute difference "
             f"{show(result['cross_voice_median_absolute_difference_ms'])} ms. "
             f"Descriptive Spearman ρ {show(result['cross_voice_articulation_ranks']['rho'], 3)}.", '']
    if result['held_out_timing']:
        lines.extend(['| Voice | Constant baseline MAE (ms) | Character-count MAE (ms) | Shuffled count median MAE (ms) |',
                      '| --- | ---: | ---: | ---: |'])
        for voice, fit in result['held_out_timing'].items():
            shuffled = (result['length_shuffle_control'] or {}).get('voices', {}).get(voice, {})
            lines.append(f"| {voice} | {show(fit['constant_ms'])} | {show(fit['count_ms'])} | "
                         f"{show(shuffled.get('null_median_count_mae_ms'))} |")
    if not result['length_shuffle_control']:
        lines.extend(['', 'A within-work length shuffle needs different lengths among comparable clauses in a work.'])
    return lines


def render_secondary(data):
    coverage = data['coverage']
    lines = ['', '### Second aligner on the same recordings', '',
             'FunASR estimates intervals from the waveform and expected Han count. The pipeline attaches the text labels afterward. '
             'The resulting spans can include pauses. Confirming which syllables were spoken requires separate phonetic evidence.', '',
             f"A direct endpoint needs agreement between midpoint estimates within {data['anchor_tolerance_ms']} ms. "
             f"An endpoint without a phone link needs a nearby agreeing midpoint on each side, at most "
             f"{data['max_slot_distance_per_side']} Han positions away per side. The estimated endpoint midpoint must fall between the anchor midpoints.", '',
             f"| Clause coverage (of {coverage['total_clauses']}) | {VOICES[0]} | {VOICES[1]} | Both voices |",
             '| --- | ---: | ---: | ---: |']
    for label, key in (
        ('Complete original articulation', 'articulation_ms'),
        ('Original endpoint spans', 'bracketed_elapsed_ms'),
        ('Raw FunASR spans', 'secondary_elapsed_ms'),
        ('Anchor-supported FunASR spans', 'secondary_anchored_elapsed_ms'),
        ('Anchor-supported FunASR among incomplete original articulation', 'anchor_supported_among_incomplete'),
        ('Elapsed spans available by either method', 'either_elapsed_support'),
        ('Additional coverage beyond original endpoint spans', 'new_over_original_brackets'),
    ):
        lines.append(f"| {label} | " + ' | '.join(str(coverage[key][item]) for item in (*VOICES, 'both')) + ' |')
    lines.extend(['', '| Passage | Clauses | Original endpoint spans in both voices | Anchor-supported FunASR spans in both | Additional spans in both via either method |',
                  '| --- | ---: | ---: | ---: | ---: |'])
    for pid, item in data['coverage_by_passage'].items():
        lines.append(f"| {pid} | {item['total_clauses']} | {item['bracketed_elapsed_ms']['both']} | "
                     f"{item['secondary_anchored_elapsed_ms']['both']} | {item['new_over_original_brackets']['both']} |")
    lines.extend(['', 'Coverage from either method can use Charsiu for one voice and anchor-supported FunASR for the other. '
                  'The held-out comparison below uses FunASR in both voices.', '',
                  '| Voice | Raw timestamped Han | Agreeing linked Han midpoints | Median midpoint difference (ms) | Original common clause spans compared | Median span difference (ms) |',
                  '| --- | ---: | ---: | ---: | ---: | ---: |'])
    for voice, item in data['comparison_by_voice'].items():
        timestamped = sum(take['timestamped_han'] for take in item['takes'])
        expected = sum(take['expected_han'] for take in item['takes'])
        lines.append(f"| {voice} | {timestamped}/{expected} | {item['han_midpoints_within_tolerance']}/"
                     f"{item['shared_han_midpoints']} | {show(item['median_absolute_midpoint_error_ms'])} | "
                     f"{item['original_shared_elapsed_compared']} | "
                     f"{show(item['median_absolute_original_shared_elapsed_difference_ms'])} |")
    lines.extend(render_timing_check('Anchor-supported FunASR elapsed timing', data['anchored_elapsed_evaluation']))
    lines.extend(['', 'FunASR receives character count as input, so this count benchmark is conditional on that alignment. '
                  'Model agreement checks the timing estimates on these synthetic voices. '
                  'Listener judgments of sound-pattern beauty await validation.'])
    return lines


def render_waveform_offset(data):
    settings = data['waveform_settings']
    lines = ['', '### Absolute waveform timing and the 80 ms hypothesis', '',
             f"PCM activity uses {settings['frame_ms']} ms RMS windows and a primary threshold of "
             f"{settings['primary_quiet_dbfs']} dBFS. Eligible edges remain within "
             f"{settings['maximum_sensitivity_width_ms']} ms across −55, −50 and −45 dBFS. "
             'The internal check matches quiet intervals to written clause breaks in order only when the counts agree '
             'and there are no rejected quiet candidates. The resulting audio landmarks measure energy transitions. '
             'Internal pause labels inferred by rank remain provisional.', '',
             'The −80 ms candidate comes from the prior inter-aligner comparison on these works. '
             'Each fitted shift excludes the evaluated work in both voices. The pooled fit weights works equally and '
             'balances their voices. Transfer fits on the other voice of other works. An exploratory check fits '
             'separate shifts by landmark type after inspecting the uneven coverage. Predictions outside the clip '
             'retain their measured error. Each fit requires at least two other works.', '',
             '| Voice | Waveform landmark | FunASR edges | Raw signed median (ms) | Raw MAE (ms) | −80 ms MAE | Held-out pooled MAE | Other-voice held-out MAE | Held-out landmark-specific MAE | Charsiu MAE (edges) |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for voice, groups in data['metrics_by_voice'].items():
        for label, key in (('Clip onset', 'clip_start'), ('Clip offset', 'clip_end'), ('Clip edges combined', 'clip'),
                           ('Quiet onset', 'pause_start'), ('Quiet offset', 'pause_end'), ('Internal edges combined', 'internal')):
            group = groups[key]
            raw = group['raw']
            cells = []
            for name in ('fixed_minus_80_ms', 'held_out_pooled_ms', 'held_out_other_voice_ms',
                         'held_out_same_landmark_ms', 'charsiu_ms'):
                estimate = group[name]['estimate']
                cell = show(estimate['work_weighted_mae_ms'])
                if estimate['edges'] and (estimate['edges'] != raw['edges'] or name == 'charsiu_ms'):
                    cell += f" ({estimate['edges']})"
                cells.append(cell)
            lines.append(f"| {voice} | {label} | {raw['edges']} | {show(raw['median_signed_error_ms'])} | "
                         f"{show(raw['work_weighted_mae_ms'])} | " + ' | '.join(cells) + ' |')
    lines.extend(['', 'Errors are mean absolute error with equal weight per work. Numbers in parentheses give the '
                  'denominator when an estimate uses a different set of waveform edges. The JSON includes the raw '
                  'comparison on each exact matched subset, threshold sensitivity ranges and the shift in each fold.', '',
                  '| Voice | Median FunASR minus Charsiu midpoint (ms) | Absolute difference before/after −80 ms (ms) |',
                  '| --- | ---: | ---: |'])
    for voice, values in data['model_midpoint_difference'].items():
        lines.append(f"| {voice} | {show(values['median_funasr_minus_charsiu_ms'])} | "
                     f"{show(values['raw_median_absolute_ms'])} / {show(values['fixed_shift_median_absolute_ms'])} |")
    lines.extend(['', 'A uniform shift translates both endpoints equally, so it cannot change a clause’s duration. '
                  'Agreement between aligners and agreement with waveform edges are separate diagnostics. '
                  'The clause table uses the original timestamps.'])
    return lines


def render(report):
    conditions = report['conditions']
    lines = ['# Quantitative prosody report', '',
             f"{conditions['independent_works']} independent works in {conditions['pairs']} period-matched pairs. "
             'Two synthetic Mandarin voices with the same intended phonemes and nominal speed.', '',
             '## Sound-pattern beauty (音律美) diagnostics', '',
             'The following features describe written rhythm, historical endings and the recorded deliveries.', '',
             '| Witness | Genre | Han | Clauses | 4 or 6 share | Length nPVI | Clip ms (original / second) | Complete clauses (original / second) |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in report['passages']:
        src = row['witness']
        data = row['音律美']
        text = data['written_rhythm']
        times = [data['recorded_timing'][voice] for voice in VOICES]
        lines.append(f"| [{src['title']}]({src['source_url']}) | {src['genre']} | {row['slots']} | {len(row['clauses'])} | "
                     f"{show(text['clause_46_share']['value'])} | {show(text['clause_npvi']['value'])} | "
                     f"{' / '.join(show(item['duration_ms'], 0) for item in times)} | "
                     f"{' / '.join(str(item['complete_clauses']) for item in times)} |")
    lines.extend(['', '### Historical clause endings', '',
                  'Point estimate and resolved transitions over eligible transitions. The JSON also gives bounds from the full reading candidates.', '',
                  '| Passage | 廣韻 平仄 contrast | 廣韻 rhyme recurrence | 平水韻 平仄 contrast | 平水韻 rhyme recurrence |',
                  '| --- | --- | --- | --- | --- |'])
    for row in report['passages']:
        history = row['音律美']['historical_endings']
        values = [history[tier][metric] for tier in TIERS for metric in HISTORICAL_METRICS]
        cells = [f"{show(item['value'])} ({item['usable']}/{item['eligible']})" for item in values]
        lines.append('| ' + ' | '.join([row['witness']['passage_id'], *cells]) + ' |')
    lines.extend(['', '### Period-matched contrasts', '',
                  'Differences are the parallel prose value minus its paired comparison. Clip milliseconds per Han include pauses.', '',
                  '| Pair | Period | Four or six share difference | nPVI difference | Clip ms per Han difference (original / second) |',
                  '| --- | --- | ---: | ---: | ---: |'])
    for row in report['matched_contrasts']:
        text = row['written_rhythm_difference']
        timing = ' / '.join(show(row['clip_ms_per_han_difference_by_voice'][voice]) for voice in VOICES)
        lines.append(f"| {row['pair_id']} | {row['period']} | {show(text['clause_46_share'])} | "
                     f"{show(text['clause_npvi'])} | {timing} |")
    lines.extend(render_timing_check('Complete articulation', report['evaluation']))
    lines.extend(render_timing_check('Exploratory elapsed timing between matched endpoints',
                                    report['exploratory_bracketed_elapsed_evaluation']))
    lines.extend(['', 'Elapsed spans include any gaps or other speech between the endpoints. '
                       'This separate coverage check was added after inspecting complete alignment.'])
    if 'secondary_alignment' in report:
        lines.extend(render_secondary(report['secondary_alignment']))
    if 'waveform_offset' in report:
        lines.extend(render_waveform_offset(report['waveform_offset']))
    columns = [('articulation_ms', 'Articulation ms'), ('bracketed_elapsed_ms', 'Bracketed elapsed ms')]
    if 'secondary_alignment' in report:
        columns.append(('secondary_anchored_elapsed_ms', 'Anchor-supported FunASR elapsed ms'))
    lines.extend(['', '### Clause timings to inspect', '',
                  'Articulation excludes inter-syllable gaps. One missing or disputed phone link makes that voice’s clause timing unavailable.', '',
                  '| Passage | Clause | Han | ' + ' | '.join(f'{label} (original / second)' for _, label in columns) + ' |',
                  '| --- | --- | ---: |' + ' ---: |' * len(columns)])
    for row in report['passages']:
        pid = row['witness']['passage_id']
        for clause in row['clauses']:
            text = ' '.join(clause['text'].split()).replace('|', '\\|')
            timing = [' / '.join(show(clause[key][voice], 0) for voice in VOICES) for key, _ in columns]
            lines.append(f"| {pid} | {text} | {clause['slots']} | " + ' | '.join(timing) + ' |')
    lines.extend(['', '## Ease of reading aloud (顺口)', '',
                  'First-read timing, repairs and ease ratings await separate participant validation.', ''])
    return '\n'.join(lines)


def build(root, secondary_path=None, check_waveform_offset=False):
    sources = {name: root / file for name, file in FILES.items()}
    inputs = {name: read_jsonl(path) for name, path in sources.items()}
    passages = index(inputs['passages'], lambda row: row['passage_id'])
    pairs = check_inventory(passages)
    takes = index(inputs['takes'], lambda row: (row['passage_id'], row['speaker']))
    recordings = index(inputs['recordings'], lambda row: row['recording_id'])
    events = defaultdict(list)
    for row in inputs['syllables']:
        events[row['recording_id']].append(row)
    if (takes.keys() != {(key, voice) for key in passages for voice in VOICES}
            or not {take['recording_id'] for take in takes.values()} == recordings.keys() == events.keys()):
        raise ValueError('Each pinned passage requires one checksum-bound recording per voice')
    profiles = [passage_profile(root, passage, takes, recordings, events) for passage in passages.values()]
    evaluation = validation(profiles)
    report = {'source_sha256': {name: digest(path) for name, path in sources.items()},
            'conditions': {'voice_ids': VOICES, 'kind': 'synthetic', 'nominal_speed': 0.9,
                           'pairs': len(pairs), 'independent_works': len(passages)},
            'passages': profiles, 'matched_contrasts': matched_contrasts(pairs, profiles), 'evaluation': evaluation,
            'exploratory_bracketed_elapsed_evaluation': validation(profiles, 'bracketed_elapsed_ms')}
    if secondary_path is not None:
        alignment = read_json(secondary_path)
        secondary = audit(alignment, report['source_sha256'], profiles, passages, takes, events, VOICES)
        secondary['alignment_sha256'] = digest(secondary_path)
        secondary['anchored_elapsed_evaluation'] = validation(profiles, 'secondary_anchored_elapsed_ms')
        report['secondary_alignment'] = secondary
        if check_waveform_offset:
            from src.quantitative_offset import analyze

            report['waveform_offset'] = analyze(root, alignment, profiles, passages, takes, events, VOICES)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--secondary-alignment', type=Path)
    parser.add_argument('--check-waveform-offset', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve(strict=True)
    output = args.output.resolve()
    if not output.is_relative_to(root / 'results') or output.suffix != '.json':
        raise ValueError('Write the quantitative report to a JSON file in the Gilbreth experiment results')
    output.parent.mkdir(parents=True, exist_ok=True)
    secondary = args.secondary_alignment.resolve(strict=True) if args.secondary_alignment else None
    if secondary is not None and (not secondary.is_relative_to(root / 'results') or secondary == output):
        raise ValueError('Use a separate second-aligner file in the Gilbreth experiment results')
    if args.check_waveform_offset and secondary is None:
        parser.error('--check-waveform-offset requires --secondary-alignment')
    report = build(root, secondary, check_waveform_offset=args.check_waveform_offset)
    write_output(output.with_suffix('.md'), render(report))
    write_json(output, report)
    result = report['secondary_alignment']['coverage'] if secondary is not None else report['evaluation']
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
