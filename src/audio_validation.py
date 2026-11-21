"""Compare Stage 5 text measures with Stage 4 synthetic waveform diagnostics."""

import argparse
from collections import Counter, defaultdict
from itertools import product
import json
import math
from pathlib import Path
from statistics import mean, median, stdev

from src.text_metrics import clauses, reading_values, text_metrics


TIER = 'guangyun'
QUIET_THRESHOLDS = (100, 150, 200)
COMPARISONS = {
    'clause_mean_slots': 'Mean clause articulation in milliseconds over the same complete clauses.',
    'clause_sd_slots': 'Sample standard deviation of clause articulation milliseconds over the same complete clauses.',
    'clause_npvi': 'Clause articulation nPVI over the same adjacent complete clause pairs.',
    'parallel_length_similarity': 'Mean minimum/maximum articulation-time ratio between annotated sides with complete timings.',
    'internal_boundary_rate': 'Fraction of the same waveform-eligible adjacent slots with a 150 ms quiet-gap candidate.',
    'ping_share': 'Share of measured articulation time at matched, determinate historical 平 slots. Both shares reuse the text labels.',
    'syllable_pz_alternation': 'Mean absolute next-early minus previous-late F0 in semitones at the same within-clause transitions.',
    'foot_pz_alternation': 'Mean absolute late-F0 difference between fixed disyllabic foot-head positions in the same clause.',
    'clause_end_pz_alternation': 'Mean absolute late-F0 difference across the same neighboring clause endings.',
    'parallel_end_pz_opposition': 'Mean absolute late-F0 difference across the same annotated paired-side endings.',
    'adjacent_han_repeat': 'Exact draft onset, final, and tone recurrence at the same acoustically adjacent within-clause positions.',
    'adjacent_initial_repeat': 'Exact draft onset recurrence at the same acoustically adjacent within-clause positions.',
    'adjacent_final_repeat': 'Exact draft final recurrence at the same acoustically adjacent within-clause positions.',
    'clause_end_rhyme_repeat': 'Exact draft final recurrence across the same neighboring clause endings, without equating modern finals with historical rhyme groups.',
}


def read_jsonl(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def same_reading(left, right, field):
    a, b = (reading_values(slot, TIER, field) for slot in (left, right))
    if not a or not b:
        return None
    if a.isdisjoint(b):
        return False
    if len(a) == len(b) == 1:
        return True
    return None


def draft_reading(row, fields):
    draft = row.get('observed_phone_draft') or {}
    values = tuple(draft.get(field) for field in fields)
    return values if all(value is not None for value in values) else None


def same_phone(left, right, fields):
    a, b = (draft_reading(row, fields) for row in (left, right))
    return a == b if a is not None and b is not None else None


def add_observation(result, metric, pairs):
    eligible = [(x, y) for x, y in pairs if x is not None and y is not None]
    if eligible:
        text, acoustic = zip(*eligible)
        result[metric] = (mean(text), mean(acoustic), len(eligible))


def length_observations(result, recording, side_groups):
    rows = recording['clauses']
    complete = {row['clause_index']: row for row in rows if row['articulation_ms'] is not None}
    add_observation(result, 'clause_mean_slots', [(row['slots_expected'], row['articulation_ms'])
                                                  for row in complete.values()])
    if len(complete) >= 2:
        result['clause_sd_slots'] = (stdev(row['slots_expected'] for row in complete.values()),
                                     stdev(row['articulation_ms'] for row in complete.values()), len(complete))

    def npvi_pair(a, b):
        return 200 * abs(a - b) / (a + b)

    add_observation(result, 'clause_npvi', [
        (npvi_pair(a['slots_expected'], b['slots_expected']), npvi_pair(a['articulation_ms'], b['articulation_ms']))
        for a, b in zip(rows, rows[1:])
        if a['clause_index'] + 1 == b['clause_index'] and a['articulation_ms'] is not None and b['articulation_ms'] is not None
    ])
    pair_lengths = []
    for left, right in side_groups:
        if all(index in complete for index in (*left, *right)):
            counts = [sum(complete[index]['slots_expected'] for index in side) for side in (left, right)]
            times = [sum(complete[index]['articulation_ms'] for index in side) for side in (left, right)]
            pair_lengths.append((min(counts) / max(counts), min(times) / max(times)))
    add_observation(result, 'parallel_length_similarity', pair_lengths)


def acoustic_observations(passage, recording, syllables, gaps):
    grouped = clauses(passage)
    by_slot = {slot['slot_index']: slot for slot in passage['slots']}
    reads = {row['slot_index']: row for row in syllables if row['duration_ms'] is not None}
    by_gap = {row['after_slot_index']: row for row in gaps}
    ends = {clause[-1]['clause_index']: clause[-1]['slot_index'] for clause in grouped}
    side_groups = passage.get('parallel_clause_groups', [])
    result = {}
    length_observations(result, recording, side_groups)
    add_observation(result, 'internal_boundary_rate', [(row['boundary_after'] > 0,
                                                       150 in row['quiet_candidate_ms_thresholds']) for row in gaps])

    pz = {index: reading_values(slot, TIER, 'pingze') for index, slot in by_slot.items()}
    timed_tones = [(next(iter(pz[index])) == '平', row['duration_ms'])
                   for index, row in reads.items() if len(pz[index]) == 1]
    if timed_tones:
        total_ms = sum(duration for _, duration in timed_tones)
        result['ping_share'] = (mean(is_ping for is_ping, _ in timed_tones),
                                 sum(duration for is_ping, duration in timed_tones if is_ping) / total_ms, len(timed_tones))

    in_clause = [(left, left + 1) for left, gap in by_gap.items() if gap['boundary_after'] == 0]
    add_observation(result, 'syllable_pz_alternation', [
        (different(left, right, by_slot), abs(by_gap[left]['adjacent_pitch_reset_st'])
         if by_gap[left]['adjacent_pitch_reset_st'] is not None else None) for left, right in in_clause
    ])
    foot_pairs = []
    for clause in grouped:
        heads = [slot['slot_index'] for slot in clause[1::2]]
        foot_pairs.extend((a, b) for a, b in zip(heads, heads[1:]) if all(i in by_gap for i in range(a, b)))
    clause_ends = list(ends.values())
    end_pairs = list(zip(clause_ends, clause_ends[1:]))
    parallel_end_pairs = [(ends[left[-1]], ends[right[-1]]) for left, right in side_groups]
    for metric, pairs in (('foot_pz_alternation', foot_pairs), ('clause_end_pz_alternation', end_pairs),
                          ('parallel_end_pz_opposition', parallel_end_pairs)):
        add_observation(result, metric, [(different(left, right, by_slot), pitch_distance(reads[left], reads[right]))
                                          for left, right in pairs if left in reads and right in reads])

    add_observation(result, 'adjacent_han_repeat', [
        (by_slot[a]['char'] == by_slot[b]['char'], same_phone(reads[a], reads[b], ('onset', 'final', 'tone')))
        for a, b in in_clause if a in reads and b in reads
    ])
    for metric, pairs, field, phone in (('adjacent_initial_repeat', in_clause, 'initial', 'onset'),
                                       ('adjacent_final_repeat', in_clause, 'final', 'final'),
                                       ('clause_end_rhyme_repeat', end_pairs, 'rhyme', 'final')):
        add_observation(result, metric, [(same_reading(by_slot[a], by_slot[b], field),
                                          same_phone(reads[a], reads[b], (phone,)))
                                         for a, b in pairs if a in reads and b in reads])
    return result


def different(left, right, slots):
    same = same_reading(slots[left], slots[right], 'pingze')
    return None if same is None else not same


def pitch_distance(a, b):
    x, y = a.get('f0_late_st'), b.get('f0_late_st')
    return abs(y - x) if x is not None and y is not None else None


def ranks(values):
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and indexed[end][1] == indexed[start][1]:
            end += 1
        middle = (start + end - 1) / 2
        for index, _ in indexed[start:end]:
            result[index] = middle
        start = end
    return result


def rank_association(rows, x='text', y='acoustic', unit='passages'):
    n = len(rows)
    summary = {unit: n, 'rho': None}
    if n < 3:
        return {**summary, 'status': 'fewer_than_three_units'}
    tx = ranks([row[x] for row in rows])
    ay = ranks([row[y] for row in rows])
    center = (n - 1) / 2
    a, b = [v - center for v in tx], [v - center for v in ay]
    norm = math.sqrt(sum(v * v for v in a) * sum(v * v for v in b))
    if norm == 0:
        return {**summary, 'status': 'constant_text_or_acoustic_values'}
    coefficient = sum(left * right for left, right in zip(a, b)) / norm
    return {**summary, 'rho': max(-1.0, min(1.0, coefficient)), 'status': 'descriptive'}


def rank_gaps(rows):
    if len(rows) < 3 or len({row['text'] for row in rows}) < 2 or len({row['acoustic'] for row in rows}) < 2:
        return []
    tx = ranks([row['text'] for row in rows])
    ay = ranks([row['acoustic'] for row in rows])
    ranked = [{**row, 'acoustic_minus_text_rank': (acoustic - text) / (len(rows) - 1)}
              for row, text, acoustic in zip(rows, tx, ay) if text != acoustic]
    return sorted(ranked, key=lambda row: (-abs(row['acoustic_minus_text_rank']), row['passage_id']))[:3]


def collapse(observations):
    cells = defaultdict(list)
    for row in observations:
        cells[row['passage_id'], row['speaker'], row['speed']].append(row)
    return {(identifier, speaker, speed): {
        'passage_id': identifier, 'speaker': speaker, 'speed': speed,
        'text': median(row['text'] for row in group),
        'acoustic': median(row['acoustic'] for row in group),
        'opportunities': sum(row['opportunities'] for row in group), 'takes': len(group),
    } for (identifier, speaker, speed), group in cells.items()}


def passage_rows(passages, cells, whole_text, metric):
    indexed = defaultdict(list)
    for row in cells.values():
        indexed[row['passage_id']].append(row)
    result = []
    for passage in passages:
        identifier = passage['passage_id']
        conditions = indexed[identifier]
        if conditions:
            result.append({'passage_id': identifier, 'genre': passage['genre'], 'period': passage['period'],
                           'text': median(row['text'] for row in conditions),
                           'text_all_positions': whole_text.get(identifier, {}).get(metric),
                           'acoustic': median(row['acoustic'] for row in conditions),
                           'conditions': len(conditions), 'takes': sum(row['takes'] for row in conditions),
                           'opportunities': sum(row['opportunities'] for row in conditions)})
    return result


def paired_rows(passages, cells, conditions):
    groups = defaultdict(list)
    for passage in passages:
        if passage['pair_id']:
            groups[passage['pair_id']].append(passage)
    result = []
    for identifier, members in sorted(groups.items()):
        if len(members) != 2:
            continue
        left, right = sorted(members, key=lambda row: (row['genre'] != 'parallel_prose', row['passage_id']))
        source_ids = left['passage_id'], right['passage_id']
        common = [(cells[(source_ids[0], *condition)], cells[(source_ids[1], *condition)])
                  for condition in conditions if all((source_id, *condition) in cells for source_id in source_ids)]
        if common:
            result.append({'pair_id': identifier, 'members': list(source_ids), 'period': left['period'],
                           'works': sorted({left['work_id'], right['work_id']}), 'conditions': len(common),
                           'text_delta': median(a['text'] - b['text'] for a, b in common),
                           'acoustic_delta': median(a['acoustic'] - b['acoustic'] for a, b in common)})
    return result


def design_blocks(pairs):
    blocks = []
    for row in pairs:
        works = set(row['works'])
        cluster = [row['pair_id']]
        retained = []
        for old_works, old_ids in blocks:
            if works & old_works:
                works.update(old_works)
                cluster.extend(old_ids)
            else:
                retained.append((old_works, old_ids))
        blocks = retained + [(works, cluster)]
    return sorted(sorted(ids) for _, ids in blocks)


def sign_flip(rows, blocks):
    spread = {row['pair_id']: row['acoustic_delta'] for row in rows}
    if not spread:
        return {'paired_mean_difference': None, 'p_two_sided_work_block': None, 'assignments': 0, 'blocks': []}
    used = [[pair for pair in block if pair in spread] for block in blocks]
    used = [block for block in used if block]
    totals = [sum(spread[pair] for pair in block) for block in used]
    observed = abs(sum(totals))
    null = [abs(sum(sign * total for sign, total in zip(assignment, totals)))
            for assignment in product((-1, 1), repeat=len(used))]
    return {'paired_mean_difference': mean(spread.values()),
            'p_two_sided_work_block': sum(draw >= observed - 1e-12 for draw in null) / len(null),
            'assignments': len(null), 'blocks': used}


def contrast_summaries(matched_passages, gaps_by_recording, takes):
    matched = [row for row in takes if row['passage_id'] in matched_passages]
    diagnostics = {}
    for tier in ('guangyun', 'pingshui'):
        by_identifier = defaultdict(lambda: defaultdict(list))
        token_counts = Counter()
        for row in matched:
            timing = row['ping_ze_duration'][tier]
            groups = timing['groups']
            if (timing['geomean_ping_ze_ratio'] is not None
                    and all(groups[tone]['tokens'] >= 2 for tone in ('平', '仄'))):
                by_identifier[row['passage_id']][row['condition']].append(timing['geomean_ping_ze_ratio'])
                token_counts.update({tone: groups[tone]['tokens'] for tone in ('平', '仄')})
        values = [{'passage_id': identifier, 'takes': sum(map(len, cells.values())),
                   'geomean_ratio': median(median(values) for values in cells.values())}
                  for identifier, cells in sorted(by_identifier.items())]
        diagnostics[tier] = {'passages': len(values), 'takes': sum(row['takes'] for row in values),
                             'total_observations_by_historical_class': dict(token_counts),
                             'median_passage_ratio': median(row['geomean_ratio'] for row in values) if values else None,
                             'by_passage': values}

    def boundary_role(kind, gap, passage):
        if kind == 'any_punctuation':
            return gap['boundary_after'] > 0
        if kind == 'major_punctuation':
            return gap['boundary_after'] >= 2
        if passage.get('parallel_clause_groups') and gap['boundary_after'] > 0:
            return gap['pair_side_end']
        return None

    boundary = {}
    for kind in ('any_punctuation', 'major_punctuation', 'annotated_side_end_among_punctuation'):
        selected = [(take, roles) for take in matched if (roles := [
            (flag, gap['quiet_candidate_ms_thresholds']) for gap in gaps_by_recording[take['recording_id']]
            if (flag := boundary_role(kind, gap, matched_passages[take['passage_id']])) is not None
        ])]
        thresholds = {}
        for threshold in QUIET_THRESHOLDS:
            counts = Counter()
            by_identifier = defaultdict(lambda: defaultdict(list))
            for take, roles in selected:
                cell = Counter((boundary, threshold in flags) for boundary, flags in roles)
                counts.update(cell)
                high = cell[True, True] + cell[True, False]
                low = cell[False, True] + cell[False, False]
                if high and low:
                    by_identifier[take['passage_id']][take['condition']].append(
                        cell[True, True] / high - cell[False, True] / low)
            tp, fp, fn, tn = (counts[flag, detected] for flag, detected in ((True, True), (False, True), (True, False), (False, False)))
            deltas = [median(median(values) for values in cells.values()) for cells in by_identifier.values()]
            thresholds[str(threshold)] = {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn, 'eligible': tp + fp + fn + tn,
                                         'precision_pooled_takes': tp / (tp + fp) if tp + fp else None,
                                         'recall_pooled_takes': tp / (tp + fn) if tp + fn else None,
                                         'passages_with_both_categories': len(deltas),
                                         'median_passage_candidate_rate_difference': median(deltas) if deltas else None}
        boundary[kind] = thresholds
    return {'historical_tone_duration': diagnostics, 'boundary_quiet_gap_candidates': boundary}


def load_inputs(root, passages):
    by_id = {passage['passage_id']: passage for passage in passages}
    clips = read_jsonl(root / 'audio/manifests/synthetic.jsonl')
    takes = read_jsonl(root / 'audio/derived/features/recordings.jsonl')
    clip_index = {clip['recording_id']: clip for clip in clips}
    take_index = {take['recording_id']: take for take in takes}
    if not clips or len(clip_index) != len(clips) or len(take_index) != len(takes) or clip_index.keys() != take_index.keys():
        raise ValueError('Synthetic and Stage 4 recording manifests must have the same nonempty, unique recording IDs.')
    gaps_by_recording, syllables_by_recording = defaultdict(list), defaultdict(list)
    for identifier, clip in clip_index.items():
        take = take_index[identifier]
        passage = by_id.get(clip['passage_id'])
        if (clip['kind'] != 'synthetic' or take['passage_id'] != clip['passage_id'] or take['audio_path'] != clip['audio_path']
                or passage is None or clip['text_sha256'] != passage['text_sha256']):
            raise ValueError(f'{identifier}: recording, acoustic summary, and edition disagree.')
        take['condition'] = (clip['speaker'], clip['speed'])
    for path, groups in (('syllables', syllables_by_recording), ('gaps', gaps_by_recording)):
        for row in read_jsonl(root / f'audio/derived/features/{path}.jsonl'):
            identifier = row['recording_id']
            if identifier not in clip_index or row['passage_id'] != clip_index[identifier]['passage_id']:
                raise ValueError(f'{identifier}: acoustic {path} row is disconnected from its source edition.')
            groups[identifier].append(row)
    return by_id, clip_index, takes, gaps_by_recording, syllables_by_recording


def metric_comparison(metric, matched, probes, cells, conditions, blocks, whole_text):
    primary = passage_rows(matched, cells, whole_text, metric)
    complete = [row for row in primary if row['conditions'] == len(conditions)]
    paired = paired_rows(matched, cells, conditions)
    per_condition = []
    for condition in conditions:
        rows = [cells[(passage['passage_id'], *condition)]
                for passage in matched if (passage['passage_id'], *condition) in cells]
        per_condition.append({'speaker': condition[0], 'speed': condition[1], **rank_association(rows)})
    return {'acoustic_definition': COMPARISONS[metric],
            'matched': {**rank_association(primary), 'rows': primary, 'largest_rank_disagreements': rank_gaps(primary),
                        'condition_count': len(conditions), 'complete_condition_only': rank_association(complete),
                        'per_condition': per_condition, 'matched_pair_deltas': paired,
                        'paired_delta_association': rank_association(paired, 'text_delta', 'acoustic_delta', unit='pairs'),
                        'paired_acoustic_sign_flip': sign_flip(paired, blocks)},
            'critic_probes': passage_rows(probes, cells, whole_text, metric),
            'critic_pair_differences': paired_rows([row for row in probes if row['pair_id'] == 'P01'], cells, conditions)}


def compare_audio(root, passages, passage_text_metrics=None):
    """Build synthetic draft diagnostics from external Stage 3 and Stage 4 JSONL."""
    passages = list(passages)
    if len({passage['passage_id'] for passage in passages}) != len(passages):
        raise ValueError('Passage IDs must be unique.')
    by_id, clips, takes, gaps, syllables = load_inputs(Path(root), passages)
    whole_text = passage_text_metrics if passage_text_metrics is not None else {
        identifier: text_metrics(passage, tier=TIER) for identifier, passage in by_id.items()
    }
    conditions = sorted({(clip['speaker'], clip['speed']) for clip in clips.values()})
    matched = [passage for passage in passages if passage['subset'] == 'matched']
    probes = [passage for passage in passages if passage['subset'] == 'critic_probe']
    blocks = design_blocks([
        {'pair_id': identifier, 'works': sorted({p['work_id'] for p in matched if p['pair_id'] == identifier})}
        for identifier in sorted({p['pair_id'] for p in matched})
    ])
    collected = defaultdict(list)
    for recording in takes:
        identifier, passage_id = recording['recording_id'], recording['passage_id']
        clip = clips[identifier]
        for metric, (text, acoustic, opportunities) in acoustic_observations(
                by_id[passage_id], recording, syllables[identifier], gaps[identifier]).items():
            collected[metric].append({'passage_id': passage_id, 'speaker': clip['speaker'], 'speed': clip['speed'],
                                      'text': text, 'acoustic': acoustic, 'opportunities': opportunities})
    return {'analysis_unit': 'passage medians of available speaker-preset × speed cell medians',
            'population': 'controlled synthetic Mandarin waveform drafts',
            'tone_and_rhyme_reference': TIER,
            'matched_source_passages': len(matched), 'critic_source_passages': len(probes), 'recordings': len(takes),
            'matched_design_work_blocks': blocks,
            'inference': 'Passage rank correlations are descriptive. Paired exact sign swaps assume block-level sign symmetry.',
            'comparisons': {metric: metric_comparison(metric, matched, probes, collapse(collected[metric]),
                                                       conditions, blocks, whole_text) for metric in COMPARISONS},
            'direct_checks': contrast_summaries({p['passage_id']: p for p in matched}, gaps, takes),
            'unavailable': {
                'clause_variance_slots': 'The same spread is represented by sample SD on the shared clause mask.',
                'clause_46_share': 'There is no calibrated acoustic threshold corresponding to four or six written slots.',
                'parallel_end_zp_share': 'No fixed pitch direction corresponds to historical 仄–平 in modern Mandarin.',
                'percent_v_delta_c_breath_groups': 'The matched corpus has no independently reviewed segment or breath intervals.',
                'human_performed_sound_and_preferences': 'The matched corpus has no audio-review or preference judgments.',
            }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare_audio(args.root, read_jsonl(args.root / 'data/pilot/annotated.jsonl'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
