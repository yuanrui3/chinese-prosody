"""Supplementary work-held-out diagnostic inside the deliberately frame-enriched training corpus."""

import argparse
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
from statistics import fmean

from . import quantitative_editorial_grammar as grammar
from .quantitative_grammar_expansion import normalized_text


WORKS = {'xie-huilian-xue', 'sun-chuo-tiantai', 'tao-yuanming-xianqing',
         'wei-zheng-ten-thoughts', 'ouyang-xiu-autumn', 'su-shi-chengtian'}
SUBSETS = {'all': None, 'whole_frame': 'neighbor_whole_frame', 'three_line_frame': 'three_line_frame'}
MODELS = ('always_six', 'context', 'context_grammar')


def describe_subset(indices, scores, predictions):
    if not indices:
        return {'units': 0, 'editorial_mean': None, 'prediction_mean': None, 'mae': None}
    return {
        'units': len(indices),
        'editorial_mean': fmean(scores[i] for i in indices),
        'prediction_mean': {name: fmean(predictions[name][i] for i in indices) for name in MODELS},
        'mae': {name: fmean(abs(predictions[name][i] - scores[i]) for i in indices) for name in MODELS},
    }


def evaluate(rows, lexicons):
    groups = {row['work_id'] for row in rows}
    if groups != WORKS | {'lafayette'} or len(rows) != 337:
        raise ValueError('Expected the frozen 337-unit enriched reference with six historical works and Lafayette.')
    authors = {row['work_id']: row['author'] for row in rows if row['work_id'] in WORKS}
    if len(set(authors.values())) != len(WORKS) or any(
            row['author'] != authors[row['work_id']] for row in rows if row['work_id'] in WORKS):
        raise ValueError('Historical-work authors must be distinct and consistent.')
    # Reuse the verified archive itself. Detect accidental regrouping, repeated rows, and invalid labels.
    section_runs = [key for key, _ in groupby(rows, lambda row: (row['work_id'], row['section']))]
    if len(set(section_runs)) != len(section_runs):
        raise ValueError('Noncontiguous work/section in enriched reference.')
    scores = [row['score'] for row in rows]
    if any(not grammar.context.valid_score(score) for score in scores):
        raise ValueError('Every training unit must have a complete integer 1–7 label.')
    normalized = [normalized_text(row) for row in rows]
    lines = grammar.context.describe(rows, lexicons)
    if not all(line.complete for line in lines):
        raise ValueError('Incomplete witness in the enriched reference.')
    # Both descriptor routines group by work and section. Precomputing cannot cross a held-out work.
    features, _ = grammar.matrix_rows(lines, lines, grammar.context.in_context(lines))
    by_work = {}
    for work_id in sorted(WORKS):
        train = [i for i, row in enumerate(rows) if row['work_id'] != work_id]
        test = [i for i, row in enumerate(rows) if row['work_id'] == work_id]
        if set(normalized[i] for i in train) & {normalized[i] for i in test}:
            raise ValueError(f'A held-out line occurs in training for {work_id}.')
        training_features = [features[i] for i in train]
        training_scores = [scores[i] for i in train]
        heldout_features = [features[i] for i in test]
        heldout_scores = [scores[i] for i in test]
        predictions = {'always_six': [6.0] * len(test)}
        for name in ('context', 'context_grammar'):
            fit = grammar.context.fit_model(training_features, training_scores, grammar.MODEL_COLS[name])
            predictions[name] = grammar.context.predict(fit, heldout_features)
        subsets = {}
        for name, field in SUBSETS.items():
            eligible = [i for i, frame in enumerate(heldout_features) if field is None or frame[field]]
            subsets[name] = describe_subset(eligible, heldout_scores, predictions)
        by_work[work_id] = {'title': rows[test[0]]['title'], 'training_units': len(train),
                            'scored_units': len(test), 'subsets': subsets}
    overall = {}
    for name in SUBSETS:
        included = {w: record['subsets'][name] for w, record in by_work.items() if record['subsets'][name]['units']}
        units = sum(s['units'] for s in included.values())
        overall[name] = {
            'eligible_works': list(included), 'works': len(included), 'units': units,
            'work_macro_mae': {m: fmean(s['mae'][m] for s in included.values()) for m in MODELS} if units else None,
            'pooled_mae': {m: sum(s['units'] * s['mae'][m] for s in included.values()) / units
                           for m in MODELS} if units else None,
            'work_macro_prediction_mean': {m: fmean(s['prediction_mean'][m] for s in included.values())
                                           for m in MODELS} if units else None,
            'work_macro_editorial_mean': fmean(s['editorial_mean'] for s in included.values()) if units else None,
        }
    return {
        'method': 'Supplementary post-hoc diagnostic within the deliberately grammar-enriched corpus. '
                  'Hold out each entire historical work and fit on the other five historical works plus Lafayette. '
                  'Use the same held-out rows for each model and compute each subset mean over eligible works. '
                  'All scores are written GPT editorial 音律美 judgments; subgroups can overlap. '
                  'There is no retuning or inference of generalization to the broader genre.',
        'ridge_penalty': grammar.context.base.RIDGE, 'subsets': overall, 'by_work': by_work,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'reference', 'output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        if not all(path.resolve().is_relative_to(root) for path in (args.reference, args.output)):
            raise ValueError('Keep the reference and result on Gilbreth.')
        raw = args.reference.read_bytes()
        lexicons, lexicon_hashes = grammar.context.base.lexicon_data(root)
        result = evaluate(json.loads(raw), lexicons)
        result.update(reference_sha256=sha256(raw).hexdigest(), lexicon_sha256=lexicon_hashes)
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write('\n')
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(args.output)


if __name__ == '__main__':
    main()
