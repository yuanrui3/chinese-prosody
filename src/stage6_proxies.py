"""Compare ancillary machine proxies using existing Gilbreth tables."""

import argparse
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import median

from src.audio_validation import load_inputs, rank_association, read_jsonl
from src.pilot_validation import write_json
from src.text_metrics import text_metrics


THRESHOLDS_MS = (100, 150, 200)
DISCREPANCIES = ('omission', 'substitution', 'insertion')
PROXIES = {
    'draft_discrepancy': 'Omissions, substitutions, and insertions per written slot. Insertions can raise the rate above one.',
    'linked_phone_confidence': 'Median Charsiu confidence across uniquely timed matched syllables, conditional on linking. Each syllable value averages the frame-max posterior within each decoded phone and then across its phones.',
}
COMPARATORS = (
    'waveform_seconds_per_written_slot',
    'syllable_duration_npvi',
    'quiet_gap_150_ms',
    'written_clause_length_npvi',
)
TEXT_PAIR_PROMPT = {
    'prompt_id': 'stage6-text-pair-v1',
    'text': ('Read A and B silently. Based on the written phrasing, which passage would be easier '
             'for a fluent reader of your usual Mandarin to produce aloud on a first pass? '
             'Answer A, B, tie, or skip.'),
    'presentation': 'Show exact passage text and punctuation only, randomize A/B, and withhold the genre, source, audio, and scores.',
    'response_fields': ['prompt_id', 'model', 'pair_id', 'a_passage_id', 'a_text_sha256',
                        'b_passage_id', 'b_text_sha256', 'choice'],
}


def proxy_row(take, syllables, gaps, passage):
    counts = take['events_by_status']
    expected = take['slots_expected']
    if (Counter(row['status'] for row in syllables) != Counter(counts)
            or len(gaps) != take['eligible_gaps'] or expected != len(passage['slots']) or not expected):
        raise ValueError(f"{take['recording_id']}: Stage 4 feature counts disagree with their input tables.")
    confidence = [row['confidence'] for row in syllables
                  if row['status'] == 'matched' and row['duration_ms'] is not None and row['confidence'] is not None]
    off_punctuation = [row for row in gaps if row['boundary_after'] == 0]
    quiet_counts = {threshold: sum(threshold in row['quiet_candidate_ms_thresholds'] for row in off_punctuation)
                    for threshold in THRESHOLDS_MS}
    speaker, speed = take['condition']
    return {
        'recording_id': take['recording_id'], 'passage_id': take['passage_id'], 'speaker': speaker, 'speed': speed,
        'written_slots': expected, 'draft_matched_slots': counts.get('matched', 0),
        'draft_edits': {key: counts.get(key, 0) for key in DISCREPANCIES},
        'draft_discrepancy': sum(counts.get(key, 0) for key in DISCREPANCIES) / expected,
        'linked_phone_confidence': median(confidence) if confidence else None,
        'linked_phone_confidence_slots': len(confidence),
        'waveform_seconds_per_written_slot': take['waveform_duration_s'] / expected,
        'syllable_duration_npvi': take['syllable_duration_npvi']['value'],
        'syllable_duration_npvi_pairs': take['syllable_duration_npvi']['pairs'],
        'off_punctuation_gaps': len(off_punctuation),
        'off_punctuation_quiet_counts': {str(threshold): count for threshold, count in quiet_counts.items()},
        'quiet_gap_150_ms': quiet_counts[150] / len(off_punctuation) if off_punctuation else None,
    }


def aggregate(rows, keys, metrics):
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[key] for key in keys)].append(row)
    summaries = []
    for identifiers, group in sorted(grouped.items()):
        summary = dict(zip(keys, identifiers))
        for metric in metrics:
            values = [row[metric] for row in group if row[metric] is not None]
            summary[metric] = median(values) if values else None
        summaries.append(summary)
    return summaries


def comparisons(rows):
    pairs = [tuple(PROXIES), *[(proxy, other) for proxy in PROXIES for other in COMPARATORS]]
    return [{'left': left, 'right': right, **rank_association(
        [row for row in rows if row[left] is not None and row[right] is not None], left, right
    )} for left, right in pairs]


def text_pairwise(path, passages, measurements):
    result = {'protocol': TEXT_PAIR_PROMPT, 'submitted_rows': 0, 'models': {}, 'status': 'awaiting_independent_responses'}
    if path is None:
        return result
    by_id = {row['passage_id']: row for row in measurements}
    counts = defaultdict(lambda: defaultdict(Counter))
    tested = set()
    for row in read_jsonl(path):
        model, pair, choice = row['model'], row['pair_id'], row['choice']
        a, b = (passages.get(row[f'{side}_passage_id']) for side in ('a', 'b'))
        if (row['prompt_id'] != TEXT_PAIR_PROMPT['prompt_id'] or not isinstance(model, str) or not model.strip()
                or choice not in ('A', 'B', 'tie', 'skip') or (model, pair) in tested
                or a is None or b is None or a['genre'] == b['genre'] or a['pair_id'] != pair or b['pair_id'] != pair
                or a['text_sha256'] != row['a_text_sha256'] or b['text_sha256'] != row['b_text_sha256']):
            raise ValueError(f'Invalid or duplicate text-pair response for {pair!r}.')
        tested.add((model, pair))
        for proxy, easier_when_high in (('draft_discrepancy', False), ('linked_phone_confidence', True)):
            x, y = (by_id.get(p['passage_id'], {}).get(proxy) for p in (a, b))
            if choice in ('tie', 'skip'):
                status = f'model_{choice}'
            elif x is None or y is None:
                status = 'proxy_missing'
            elif x == y:
                status = 'proxy_tie'
            else:
                expected_choice = 'A' if (x > y) == easier_when_high else 'B'
                status = 'concordant' if expected_choice == choice else 'opposed'
            counts[model][proxy][status] += 1
    if tested:
        result.update({'status': 'descriptive', 'submitted_rows': len(tested), 'models': counts})
    return result


def evaluate(root, text_judgments=None):
    annotations = read_jsonl(root / 'data/pilot/annotated.jsonl')
    if len({row['passage_id'] for row in annotations}) != len(annotations):
        raise ValueError('Passage IDs must be unique.')
    passages = {row['passage_id']: row for row in annotations if row['subset'] == 'matched'}
    _, _, takes, gaps, syllables = load_inputs(root, annotations)
    rows = [proxy_row(take, syllables[take['recording_id']], gaps[take['recording_id']], passages[take['passage_id']])
            for take in takes if take['passage_id'] in passages]
    metrics = (*PROXIES, *COMPARATORS[:-1])
    cells = aggregate(rows, ('passage_id', 'speaker', 'speed'), metrics)
    pooled = aggregate(cells, ('passage_id',), metrics)
    written = {identifier: text_metrics(row)['clause_npvi'] for identifier, row in passages.items()}
    for row in [*cells, *pooled]:
        row['written_clause_length_npvi'] = written[row['passage_id']]
    conditions = sorted({(row['speaker'], row['speed']) for row in cells})
    support = {key: sum(row[key] for row in rows) for key in (
        'written_slots', 'draft_matched_slots', 'linked_phone_confidence_slots',
        'syllable_duration_npvi_pairs', 'off_punctuation_gaps',
    )}
    support['off_punctuation_quiet_counts'] = {
        str(threshold): sum(row['off_punctuation_quiet_counts'][str(threshold)] for row in rows)
        for threshold in THRESHOLDS_MS
    }
    return {
        'population': 'Stage 4 controlled synthetic Mandarin drafts for Stage 3 matched prose',
        'aggregation': 'Median across takes per passage × voice × speed, then equal-weight median across available conditions.',
        'interpretation': ('Spearman correlations describe machine outputs for this pilot. Draft discrepancy and linked confidence '
                           'share a decoder, and syllable duration and quiet gaps also rely on its links. Waveform length and '
                           'written clause lengths use separate measurements. Confidence is conditional and uncalibrated.'),
        'proxy_definitions': PROXIES,
        'matched_passages': len(passages), 'matched_pairs': len({row['pair_id'] for row in passages.values()}),
        'matched_recordings': len(rows), 'other_recordings': len(takes) - len(rows),
        'matched_conditions': len(conditions), 'support': support,
        'recording_rows': rows, 'passage_medians': pooled, 'passage_spearman': comparisons(pooled),
        'per_condition_spearman': [{'speaker': speaker, 'speed': speed, 'comparisons': comparisons(
            [row for row in cells if (row['speaker'], row['speed']) == (speaker, speed)]
        )} for speaker, speed in conditions],
        'text_pairwise': text_pairwise(text_judgments, passages, pooled),
        'audio_model_human_stumbling': {'status': 'unavailable', 'reason': 'No reviewed, consented human read-aloud trial data.'},
        'author_self_rating': {'status': 'unavailable', 'reason': 'No edition-linked and condition-matched author responses.'},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--text-judgments', type=Path, help='Optional independent, blinded text responses as JSONL.')
    args = parser.parse_args()
    output = args.root / 'results/stage6/proxies.json'
    write_json(output, evaluate(args.root, args.text_judgments))
    print(output)


if __name__ == '__main__':
    main()
