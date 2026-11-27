"""Transfer one work's editorial 音律美 scores to an untouched historical witness."""

import argparse
from collections import Counter
from hashlib import sha256
from itertools import groupby
import json
import math
from operator import ne
from pathlib import Path
from statistics import fmean

import numpy as np

from data.phonology.annotate import han
from data.phonology.historical import load_historical
from data.phonology.modern import ARCHIVE, load_modern
from src.stage7_text import HISTORICAL_REFERENCES, annotate_text
from src.text_metrics import metric_results, reading_values, relation_rate


RIDGE = 10.0
GROUP_BREAKS = frozenset('，,；;：:。.!！?？「」『』“”"‘’\n')
FEATURES = (
    'log_han_count',
    'four_six_group_share',
    'adjacent_length_balance',
    'guangyun_foot_pz_alternation',
    'guangyun_group_end_pz_alternation',
    'guangyun_equal_length_group_end_opposition',
    'guangyun_group_end_rhyme_repeat',
    'pingshui_group_end_rhyme_repeat',
)


def load_rows(path):
    payload = path.read_bytes()
    rows = json.loads(payload)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f'{path}: expected a nonempty JSON array')
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('text'), str) or not any(map(han, row['text'])):
            raise ValueError(f'{path}: each row needs nonempty Han text')
    return rows, sha256(payload).hexdigest()


def lexicon_data(root):
    raw = root / 'data' / 'raw' / 'phonology'
    files = [raw / 'guangyun.csv', raw / 'pingshui.html']
    if not all(path.is_file() for path in files):
        raise ValueError('Expected the existing 廣韻 and 平水韻 caches in data/raw/phonology')
    options = load_historical(raw)
    if (raw / ARCHIVE).is_file():
        _, options['variants'] = load_modern(raw)
        files.append(raw / ARCHIVE)
    return options, {path.name: sha256(path.read_bytes()).hexdigest() for path in files}


def annotate_groups(text, lexicons, *, historical_readings=None):
    """Preserve reading candidates and regroup punctuation as in the original scoring sheet."""
    original = annotate_text(text, historical_readings=historical_readings, **lexicons)
    group_index = 0
    slots = []
    for slot in original['slots']:
        boundary = int(any(mark in GROUP_BREAKS for mark in slot['marks_after']))
        slots.append({**slot, 'clause_index': group_index, 'boundary_after': boundary})
        group_index += boundary
    groups = [list(values) for _, values in groupby(slots, key=lambda slot: slot['clause_index'])]
    return {'slots': slots}, groups


def group_endings(text, groups):
    endings = []
    for group in groups:
        first, final = group[0], group[-1]
        offset = final['offset']
        readings = {}
        for tier in HISTORICAL_REFERENCES:
            entry = final['readings'][tier]
            fields = ('id', 'tone', 'pingze', 'rhyme', 'lookup_char')
            readings[tier] = {
                'status': entry['status'], 'lookup': entry['lookup'],
                'candidates': [{key: candidate[key] for key in fields if key in candidate}
                               for candidate in entry['candidates']],
            }
            if entry.get('selected') is not None:
                readings[tier]['selected'] = {k: entry['selected'][k] for k in fields if k in entry['selected']}
                readings[tier]['evidence'] = entry['evidence']
                if 'additional_evidence' in entry:
                    readings[tier]['additional_evidence'] = entry['additional_evidence']
        endings.append({'char': final['char'], 'offset': offset, 'group_start_offset': first['offset'],
                        'group_text': text[first['offset']:offset + 1], 'readings': readings})
    return endings


def measure(text, lexicons, *, detail=False, historical_readings=None):
    passage, groups = annotate_groups(text, lexicons, historical_readings=historical_readings)
    lengths = [len(group) for group in groups]
    guangyun = metric_results(passage, 'guangyun')
    pingshui = metric_results(passage, 'pingshui')
    adjacent = list(zip(groups, groups[1:]))
    equal_pairs = [[left[-1], right[-1]] for left, right in adjacent if len(left) == len(right)]
    opposition = relation_rate(equal_pairs, lambda slot: reading_values(slot, 'guangyun', 'pingze'), ne)
    estimates = {
        'guangyun_foot_pz_alternation': guangyun['foot_pz_alternation'],
        'guangyun_group_end_pz_alternation': guangyun['clause_end_pz_alternation'],
        'guangyun_equal_length_group_end_opposition': opposition,
        'guangyun_group_end_rhyme_repeat': guangyun['clause_end_rhyme_repeat'],
        'pingshui_group_end_rhyme_repeat': pingshui['clause_end_rhyme_repeat'],
    }
    features = {
        'log_han_count': math.log(sum(lengths)),
        'four_six_group_share': guangyun['clause_46_share'].value,
        'adjacent_length_balance': fmean(min(a, b) / max(a, b) for a, b in zip(lengths, lengths[1:]))
        if adjacent else None,
        **{name: estimate.value for name, estimate in estimates.items()},
    }
    if not detail:
        return features
    return {
        'features': features,
        'group_lengths': lengths,
        'group_endings': [group[-1]['char'] for group in groups],
        'historical_endings': group_endings(text, groups),
        'historical_support': {
            name: {'eligible': estimate.eligible, 'usable': estimate.usable,
                   'bounded': estimate.bounded, 'lower': estimate.lower, 'upper': estimate.upper}
            for name, estimate in estimates.items()
        },
        'missing_features': [name for name in FEATURES if features[name] is None],
    }


def matrix(rows):
    return np.array([[row[name] if row[name] is not None else np.nan for name in FEATURES] for row in rows],
                    dtype=float)


def fit(reference, lexicons):
    labels = []
    values = []
    for index, row in enumerate(reference, start=1):
        score = row.get('score')
        if type(score) is not int or not 1 <= score <= 7 or '□' in row['text']:
            raise ValueError(f'Reference row {index}: expected a complete line and integer editorial score 1–7')
        labels.append(score)
        values.append(measure(row['text'], lexicons, historical_readings=row.get('historical_readings')))
    if len(set(labels)) < 2:
        raise ValueError('Reference needs at least two distinct editorial scores')
    raw = matrix(values)
    observed = np.isfinite(raw)
    count = observed.sum(axis=0)
    means = np.divide(np.nansum(raw, axis=0), count, out=np.zeros(len(FEATURES)), where=count > 0)
    centered = np.where(observed, raw - means, 0.0)
    deviations = np.sqrt(np.divide((centered**2).sum(axis=0), count,
                                   out=np.zeros(len(FEATURES)), where=count > 0))
    scales = np.where(deviations > 0, deviations, 1.0)
    design = centered / scales
    intercept = float(np.mean(labels))
    weights = np.linalg.solve(design.T @ design + RIDGE * np.eye(len(FEATURES)),
                              design.T @ (np.asarray(labels, dtype=float) - intercept))
    details = {
        'method': 'ridge regression with unpenalized intercept, standardized nonempty reference features',
        'target': 'written sound-pattern beauty editorial scores from one previous work',
        'penalty': RIDGE,
        'n_reference_rows': len(labels),
        'intercept': intercept,
        'features': [
            {'name': name, 'mean': float(means[index]), 'scale': float(scales[index]),
             'observed': int(count[index]), 'weight': float(weights[index])}
            for index, name in enumerate(FEATURES)
        ],
        'missing_value_rule': 'Use the reference feature mean, which gives zero after centering.',
        'output_rule': 'Round the unscaled prediction to the nearest integer (half up) and bound to [1, 7].',
    }
    return (means, scales, intercept, weights), details, labels


def distribution(values):
    counts = Counter(values)
    occupied = sorted(set(counts) - {None})
    return {
        'counts': {str(score): counts[score] for score in range(1, 8)},
        'scored': len(values) - counts[None],
        'unscored': counts[None],
        'minimum': min(occupied) if occupied else None,
        'maximum': max(occupied) if occupied else None,
        'occupied': occupied,
        'all_1_to_7_occupied': occupied == list(range(1, 8)),
    }


def evaluate(reference, witness, lexicons):
    ids = set()
    reference_texts = {''.join(filter(han, row['text'])) for row in reference}
    for row in witness:
        rid = row.get('id')
        if not isinstance(rid, str) or not rid.strip() or rid in ids:
            raise ValueError('Witness rows need unique nonempty string IDs')
        ids.add(rid)
        if ''.join(filter(han, row['text'])) in reference_texts:
            raise ValueError(f'{rid}: exact Han string also occurs in the reference')

    (means, scales, intercept, weights), fit_details, labels = fit(reference, lexicons)
    rows = []
    for row in witness:
        detail = measure(row['text'], lexicons, detail=True, historical_readings=row.get('historical_readings'))
        # Preserve the exact source row and its candidate diagnostics even when no score is assigned.
        if '□' in row['text']:
            raw = score = None
            status = 'lacuna_unscored'
        else:
            observed = matrix([detail['features']])[0]
            standardized = np.where(np.isfinite(observed), observed - means, 0.0) / scales
            raw = float(intercept + standardized @ weights)
            score = min(7, max(1, math.floor(raw + 0.5)))
            status = 'scored'
        rows.append({
            **row, **detail, 'text_sha256': sha256(row['text'].encode('utf-8')).hexdigest(),
            'status': status, 'raw_prediction': raw, 'score': score,
        })
    return {
        'rows': rows,
        'fit': fit_details,
        'distributions': {'reference': distribution(labels), 'witness': distribution([row['score'] for row in rows])},
        'scope': 'Cross-work transfer of editorial written-cadence scores. Listening and first-read outcomes are separate.',
        'grouping': 'Commas, semicolons, colons, quotes, sentence stops and newlines delimit groups. The list mark 、 stays within a group.',
        'reading_rule': 'Point estimates use resolved historical readings. Equal-length neighbors supply a structural contrast only.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--witness', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    paths = (args.reference, args.witness, args.output)
    if any(not path.resolve().is_relative_to(root) for path in paths):
        parser.error('Keep the reference, witness and output inside the Gilbreth project')
    try:
        reference, ref_hash = load_rows(args.reference)
        witness, witness_hash = load_rows(args.witness)
        lexicons, lexicon_hashes = lexicon_data(root)
        result = evaluate(reference, witness, lexicons)
        result['input_sha256'] = {'reference': ref_hash, 'witness': witness_hash}
        result['lexicons'] = {'historical': HISTORICAL_REFERENCES, 'source_sha256': lexicon_hashes}
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write('\n')
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result['distributions'], ensure_ascii=False))


if __name__ == '__main__':
    main()
