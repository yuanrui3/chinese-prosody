"""Test repeated, marker-anchored grammatical frames against frozen written 音律美 ratings."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import combinations, groupby
import json
from pathlib import Path
from random import Random
from statistics import fmean, median

from . import quantitative_editorial_context as context


# Morphosyntactic cues in these positions are hypotheses. A character can serve other roles.
MARKERS = {
    'likening': '如若似猶犹',
    'negation': '不弗未非無无莫勿',
    'reference': '其此彼斯是',
    'linker': '之',
    'nominalizer': '者',
    'locative': '於于',
    'instrumental': '以',
    'coordinator': '而與与',
    'consequent': '則则乃遂',
    'nominal_aux': '所',
    'modal': '可宜能',
    'copular': '為为',
    'question': '何孰安焉',
    'final_particle': '也矣乎哉耳',
    'caesura': '兮',
}
TOKEN = {char: kind for kind, chars in MARKERS.items() for char in chars}
SEASONS = '春夏秋冬'
GRAMMAR = ('neighbor_whole_frame', 'neighbor_member_frame_coverage', 'three_line_frame')
MODEL_COLS = {'context': context.MODELS['context'], 'frame_only': GRAMMAR,
              'context_grammar': context.MODELS['context'] + GRAMMAR}
CONTROLS = ('section_order', 'within_member_positions')
SEED = 20261123


def signature(groups):
    return tuple(tuple('season' if i == 0 and len(group) > 1 and ch in SEASONS else TOKEN.get(ch, '')
                       for i, ch in enumerate(group)) for group in groups)


def matches(a_groups, b_groups, a_pattern, b_pattern):
    if a_pattern != b_pattern or not any(any(group) for group in a_pattern):
        return False
    return any(not slot and a != b
               for left, right, pattern in zip(a_groups, b_groups, a_pattern)
               for a, b, slot in zip(left, right, pattern))


def frame_features(lines, *, shuffled_positions=None, edge_details=None):
    """Order in the supplied line list defines adjacency. All counts remain tied to the original IDs."""
    result = {}
    for _, chunk in groupby(lines, key=lambda ln: (ln.row['work_id'], ln.row['section'])):
        section = list(chunk)
        groups = []
        for line in section:
            row = line.groups
            if shuffled_positions is not None:
                row = tuple(''.join(shuffled_positions.sample(group, len(group))) for group in row)
            groups.append(row)
        patterns = [signature(g) for g in groups]
        full_edges = []
        coverages = []
        for i in range(len(section) - 1):
            a, b = groups[i:i + 2]
            sa, sb = patterns[i:i + 2]
            usable = section[i].complete and section[i + 1].complete
            full_edges.append(usable and matches(a, b, sa, sb))
            count = sum(len(x) for x, y, sx, sy in zip(a, b, sa, sb)
                        if usable and matches((x,), (y,), (sx,), (sy,)))
            coverages.append(count / max(sum(map(len, a)), sum(map(len, b))))
            if edge_details is not None:
                left, right = section[i:i + 2]
                edge_details.append({'work_id': left.key[0], 'section': left.row['section'],
                                     'left_id': left.key[1], 'right_id': right.key[1], 'eligible': usable,
                                     'whole_frame': full_edges[-1], 'member_coverage': coverages[-1],
                                     'any_aligned_frame': bool(full_edges[-1] or count)})
        for i, line in enumerate(section):
            incident = [edge for edge in (i - 1, i) if 0 <= edge < len(full_edges)]
            in_three = any(full_edges[j] and full_edges[j + 1]
                           for j in range(max(0, i - 2), min(i + 1, len(full_edges) - 1)))
            whole_neighbors = [section[j + 1 if j == i else j].row['id'] for j in incident if full_edges[j]]
            result[line.key] = ({
                'neighbor_whole_frame': int(bool(whole_neighbors)),
                'neighbor_member_frame_coverage': max((coverages[j] for j in incident), default=0.0),
                'three_line_frame': int(in_three),
            }, whole_neighbors, patterns[i])
    return result


def section_shuffle(lines, rng):
    reordered = []
    for _, group in groupby(lines, key=lambda ln: (ln.row['work_id'], ln.row['section'])):
        window = list(group)
        rng.shuffle(window)
        reordered.extend(window)
    return reordered


def matrix_rows(sequence, line_order, context_map, *, positions_rng=None, edge_details=None):
    frame_map = frame_features(sequence, shuffled_positions=positions_rng, edge_details=edge_details)
    rows = [{**context_map[line.key][0], **frame_map[line.key][0]} for line in line_order]
    return rows, frame_map


def scoring_inputs(reference, witness, lexicons):
    if any('editorial_score' in r or 'score' in r for r in witness):
        raise ValueError('Supply a label-free witness and separate frozen labels.')
    train = context.describe(reference, lexicons)
    test = context.describe(witness, lexicons)
    ids = {line.row['work_id'] for line in train}
    if any(line.row['work_id'] in ids for line in test):
        raise ValueError('Hold out whole works.')
    train_text = {''.join(line.groups) for line in train}
    if any(''.join(line.groups) in train_text for line in test):
        raise ValueError('Held-out line also occurs in the reference.')
    scores = [r.get('score') for r in reference]
    if any(not ln.complete or not context.valid_score(y) for ln, y in zip(train, scores)) or len(set(scores)) < 2:
        raise ValueError('Expected complete reference lines with variable 1–7 scores.')
    for batch in (train, test):
        checked = set()
        for key, _ in groupby(batch, key=lambda ln: (ln.row['work_id'], ln.row['section'])):
            if key in checked:
                raise ValueError(f'Noncontiguous section: {key}')
            checked.add(key)
    return train, test, scores


def concordance(observed, predicted):
    """Compare every pair of distinct target scores, assigning half-credit to prediction ties."""
    credit = 0.0
    count = 0
    for i, j in combinations(range(len(observed)), 2):
        if observed[i] != observed[j]:
            delta = (observed[i] - observed[j]) * (predicted[i] - predicted[j])
            credit += 0.5 if abs(predicted[i] - predicted[j]) < 1e-10 else float(delta > 0)
            count += 1
    return {'pairs': count, 'proportion': credit / count if count else None}


def calculate_metrics(predictions, observed, indices):
    y = [observed[i] for i in indices]
    result = {}
    for name, forecast in predictions.items():
        p = [forecast[i] for i in indices]
        result[name] = {'mae': fmean(abs(x - v) for x, v in zip(y, p)),
                        'concordance': concordance(y, p)}
    return result


def mae_groups(raw, y, batches):
    per_work = {work: fmean(abs(raw[i] - y[i]) for i in indices) for work, indices in batches.items()}
    pooled = fmean(abs(raw[i] - y[i]) for indices in batches.values() for i in indices)
    return {**per_work, 'pooled': pooled, 'work_macro': fmean(per_work.values())}


def summarize_shuffles(samples, observed):
    return {work: {'observed': observed[work], 'median_shuffled': median(values),
                   'count_at_least_as_good': sum(v <= observed[work] + 1e-12 for v in values),
                   'draws': len(values)} for work, values in samples.items()}


def group_name(row):
    return 'frame' if row['neighbor_whole_frame'] or row['neighbor_member_frame_coverage'] > 0 else 'no_frame'


def fit_group_medians(train_x, scores):
    fallback = median(scores)
    groups = {}
    for name in ('frame', 'no_frame'):
        selected = [s for features, s in zip(train_x, scores) if group_name(features) == name]
        groups[name] = {'n': len(selected), 'median': median(selected) if selected else fallback,
                        'uses_global_fallback': not selected}
    return groups


def run_controls(test, models, group_medians, context_map, labels, batches, observed, repeats):
    summaries = {}
    for mode in CONTROLS:
        rng = Random(SEED)
        errors = {name: defaultdict(list) for name in ('context_grammar', 'conditional_median')}
        gains = defaultdict(list)
        activated = []
        for _ in range(repeats):
            if mode == 'section_order':
                order = section_shuffle(test, rng)
                input_rows, _ = matrix_rows(order, test, context.in_context(order))
            else:
                input_rows, _ = matrix_rows(test, test, context_map, positions_rng=rng)
            forecasts = {'context_grammar': context.predict(models['context_grammar'], input_rows),
                         'conditional_median': [group_medians[group_name(row)]['median'] for row in input_rows]}
            plain = mae_groups(context.predict(models['context'], input_rows), labels, batches)
            for name, forecast in forecasts.items():
                for key, value in mae_groups(forecast, labels, batches).items():
                    errors[name][key].append(value)
                    if name == 'context_grammar':
                        gains[key].append(plain[key] - value)
            activated.append(sum(row['neighbor_whole_frame'] for ln, row in zip(test, input_rows) if ln.complete))
        summaries[mode] = {'mae': summarize_shuffles(errors['context_grammar'], observed['context_grammar']),
                           'conditional_median_mae': summarize_shuffles(errors['conditional_median'],
                                                                       observed['conditional_median']),
                           'median_lines_whole_frame': median(activated)}
        gain_summary = {}
        for key, draws in gains.items():
            actual = observed['context'][key] - observed['context_grammar'][key]
            gain_summary[key] = {'observed': actual, 'median_shuffled': median(draws), 'draws': len(draws),
                                 'count_at_least_as_large': sum(g >= actual - 1e-12 for g in draws)}
        summaries[mode]['gain_over_matched_context'] = gain_summary
    return summaries


def summarize_support(frame_map, lines):
    features = [frame_map[ln.key][0] for ln in lines if ln.complete]
    return {'complete': len(features), 'nonzero_lines': {
        name: sum(bool(row[name]) for row in features) for name in GRAMMAR}}


def evaluate(reference, witness, labels, lexicons, repeats=199):
    if repeats < 1:
        raise ValueError('Specify at least one shuffle.')
    train, test, scores = scoring_inputs(reference, witness, lexicons)
    train_x, train_frames = matrix_rows(train, train, context.in_context(train))
    original_context = context.in_context(test)
    edges = []
    test_x, test_frames = matrix_rows(test, test, original_context, edge_details=edges)
    models = {name: context.fit_model(train_x, scores, cols) for name, cols in MODEL_COLS.items()}
    forecast = {name: context.predict(model, test_x) for name, model in models.items()}
    group_medians = fit_group_medians(train_x, scores)
    forecast['conditional_median'] = [group_medians[group_name(row)]['median'] for row in test_x]
    forecast['always_six'] = [6.0] * len(test)
    forecast['training_median'] = [float(median(scores))] * len(test)

    # Join labels after feature extraction, fitting and prediction. No test scores supply fitted parameters.
    index = {(r['work_id'], r['id']): r['score'] for r in labels}
    if len(index) != len(labels) or set(index) != {line.key for line in test if line.complete}:
        raise ValueError('Frozen labels must exactly cover each complete witness line once.')
    if any(not context.valid_score(y) for y in index.values()):
        raise ValueError('Frozen labels must be integer editorial scores 1–7.')
    y = [index.get(line.key) for line in test]
    batches = defaultdict(list)
    rows = []
    for i, line in enumerate(test):
        frame, neighbors, pattern = test_frames[line.key]
        raw = {name: forecasts[i] if line.complete else None for name, forecasts in forecast.items()}
        rows.append({**line.row, 'editorial_score': y[i], 'raw': raw, 'frame_features': frame,
                     'recognized_slots': [[slot or '*' for slot in g] for g in pattern],
                     'whole_frame_neighbors': neighbors})
        if line.complete:
            batches[line.row['work_id']].append(i)
    if not batches or set(batches) & {'pooled', 'work_macro'}:
        raise ValueError('Expected scored works and nonreserved work IDs.')
    by_work = {w: calculate_metrics(forecast, y, ii) for w, ii in batches.items()}
    pooled = {name: mae_groups(p, y, batches) for name, p in forecast.items()}
    return {'rows': rows, 'edges': edges, 'models': models, 'conditional_median_training': group_medians,
            'mae': pooled, 'by_work': by_work,
            'target_counts': dict(sorted(Counter(index.values()).items())),
            'frame_support': {'training': summarize_support(train_frames, train),
                              'test': summarize_support(test_frames, test),
                              'by_work': {w: summarize_support(test_frames, [test[i] for i in ii])
                                          for w, ii in batches.items()}},
            'controls': run_controls(test, models, group_medians, original_context, y,
                                     batches, pooled, repeats),
            'method': {'target': 'written editorial 音律美', 'primary': 'work-macro raw MAE versus always_six',
                       'penalty': context.base.RIDGE, 'training_median': median(scores),
                       'markers': MARKERS, 'multi_character_member_initial_seasons': SEASONS,
                       'seed': SEED, 'draws_per_control': repeats,
                       'frame': 'Exact classified slot sequence and at least one differing open slot. Whole frames preserve every punctuation-member length.',
                       'section_order': 'Shuffle intact lines within their contiguous sections and recompute both context and grammatical frames.',
                       'within_member_positions': 'Shuffle characters within each punctuation member only for grammatical features. Text baseline and original line order remain fixed.'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'reference', 'witness', 'labels', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--shuffles', type=int, default=199)
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        if any(not p.resolve().is_relative_to(root) for p in (args.reference, args.witness, args.labels, args.output)):
            raise ValueError('Keep files in the Gilbreth project.')
        reference, ref_hash = context.base.load_rows(args.reference)
        witness, witness_hash = context.base.load_rows(args.witness)
        label_data = args.labels.read_bytes()
        lexicons, lexicon_hashes = context.base.lexicon_data(root)
        result = evaluate(reference, witness, json.loads(label_data), lexicons, args.shuffles)
        result.update(input_sha256={'reference': ref_hash, 'witness': witness_hash,
                                    'labels': sha256(label_data).hexdigest()}, lexicon_sha256=lexicon_hashes)
        with args.output.open('x', encoding='utf-8') as target:
            json.dump(result, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.write('\n')
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps({'mae': result['mae'], 'support': result['frame_support']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
