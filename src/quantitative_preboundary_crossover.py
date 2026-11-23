"""Check whether the DEBATE duration contrast survives normalization and eligibility controls."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import expm1, isclose, isfinite, log
from pathlib import Path
from random import Random
from statistics import fmean, quantiles


def index_by(rows, keys):
    indexed = {}
    for row in rows:
        key = tuple(row[field] for field in keys)
        if key in indexed:
            raise ValueError(f'Duplicate {keys}: {key!r}')
        indexed[key] = row
    return indexed


def log_difference(a, b):
    if a is None or b is None:
        return None
    if not (isfinite(a) and isfinite(b) and a > 0 and b > 0):
        raise ValueError('Expected positive finite durations')
    return log(a) - log(b)


def articulation(aligned, ordinal):
    return aligned.get(str(ordinal - 1), {}).get('duration_s')


def placebo_ordinals(length, annotated, a_only, b_only):
    # Text-only choices. Distinct controls avoid a mechanically zero crossover.
    possible = [j for j in range(1, length) if all(abs(j - k) >= 2 for k in annotated)]
    if len(possible) < 2:
        return None
    distances = [{j: fmean(abs(j - k) for k in target) for j in possible} for target in (a_only, b_only)]
    return min(((a, b) for a in possible for b in possible if a != b),
               key=lambda pair: (distances[0][pair[0]] + distances[1][pair[1]], *pair))


def paired_cells(candidates, manifest):
    inventory = index_by(manifest['recordings'], ('recording_id',))
    waveforms = index_by(candidates['recordings'], ('recording_id',))
    labels = index_by(candidates['rows'], ('recording_id', 'ordinal'))
    if not inventory or inventory.keys() != waveforms.keys():
        raise ValueError('The DEBATE manifest and waveform results must contain the same recordings')
    groups = defaultdict(list)
    for key, record in inventory.items():
        if not record['work'].startswith('DEBATE-'):
            raise ValueError('Crossover requires a DEBATE-only manifest')
        waveform = waveforms[key]
        if (record['wav_sha256'] != waveform['wav_sha256']
                or ''.join(record['characters']) != waveform['characters']):
            raise ValueError(f'{key[0]}: decoded material differs from the source manifest')
        groups[record['work'], record['speaker']].append(record)

    seen = set()
    cells = []
    for (work, speaker), variants in sorted(groups.items()):
        variants.sort(key=lambda record: record['recording_id'])
        if len(variants) != 2 or variants[0]['characters'] != variants[1]['characters']:
            raise ValueError(f'{work}/{speaker}: expected two readings of one exact Han sequence')
        a, b = variants
        a_id, b_id = (record['recording_id'] for record in variants)
        a_marked, b_marked = (set(record['source_positive_ordinals']) for record in variants)
        a_only, b_only = a_marked - b_marked, b_marked - a_marked
        if not a_only or not b_only:
            raise ValueError(f'{work}/{speaker}: expected both crossover directions')
        length = len(a['characters'])
        if not all(type(j) is int and 0 < j < length for j in a_marked | b_marked):
            raise ValueError(f'{work}/{speaker}: a prompt join is outside the unpunctuated text')
        for record, positive, negative in ((a, a_only, b_only), (b, b_only, a_only)):
            if set(record['positive_ordinals']) != positive or set(record['negative_ordinals']) != negative:
                raise ValueError(f'{work}/{speaker}: contrasted labels differ from source prompts')

        a_aligned, b_aligned = (waveforms[(record_id,)]['aligned'] for record_id in (a_id, b_id))
        joins = []
        for ordinal in sorted(a_only | b_only):
            keys = [(a_id, ordinal), (b_id, ordinal)]
            row_a, row_b = (labels[key] for key in keys)
            seen.update(keys)
            a_positive = ordinal in a_only
            for row, expected in ((row_a, a_positive), (row_b, not a_positive)):
                if row['work'] != work or row['speaker'] != speaker or row['label'] != expected:
                    raise ValueError(f'{work}/{speaker}/{ordinal}: acoustic row differs from source label')
            raw = log_difference(articulation(a_aligned, ordinal), articulation(b_aligned, ordinal))
            denominator = log_difference(row_a['context_duration_s'], row_b['context_duration_s'])
            pause = row_a['pause_ms'], row_b['pause_ms']
            strict = all(row[field] is not None for row in (row_a, row_b)
                         for field in ('pre_duration_s', 'context_duration_s', 'pause_ms'))
            if strict:
                measured = log_difference(row_a['pre_duration_s'], row_b['pre_duration_s'])
                if raw is None or not isclose(raw, measured, abs_tol=1e-12):
                    raise ValueError(f'{work}/{speaker}/{ordinal}: target duration differs from logged alignment')
            joins.append({'ordinal': ordinal, 'a_positive': a_positive, 'raw': raw, 'denominator': denominator,
                          'strict': strict, 'no_pause': pause == (0, 0),
                          'left_a_linked': articulation(a_aligned, ordinal) is not None,
                          'left_b_linked': articulation(b_aligned, ordinal) is not None})
        text_placebos = placebo_ordinals(length, a_marked | b_marked, a_only, b_only)
        placebo = None
        if text_placebos is not None:
            first, second = (log_difference(articulation(a_aligned, j), articulation(b_aligned, j))
                             for j in text_placebos)
            if first is not None and second is not None:
                placebo = (first - second) / 2
        cells.append({'work': work, 'speaker': speaker, 'joins': joins,
                      'placebo_ordinals': text_placebos, 'placebo': placebo})
    if seen != set(labels):
        raise ValueError('An acoustic candidate is outside the reviewed DEBATE contrasts')
    return cells


def estimate(rows, *, draws, seed):
    if not rows:
        return {'complete_cells': 0, 'works': 0, 'speakers': 0, 'mean_log_duration_crossover': None,
                'duration_percent': None, 'permutation': None, 'crossed_bootstrap_interval_95': None}
    works = defaultdict(list)
    for work, speaker, value in rows:
        works[work].append((speaker, value))
    work_keys = sorted(works)
    speakers = sorted({speaker for _, speaker, _ in rows})
    means = [fmean(value for _, value in works[work]) for work in work_keys]
    observed = fmean(means)
    rng = Random(seed)
    greater = two_sided = 0
    for _ in range(draws):
        reversed_signs = rng.getrandbits(len(means))
        estimate_under_null = fmean(-value if reversed_signs & (1 << i) else value
                                    for i, value in enumerate(means))
        greater += estimate_under_null >= observed - 1e-12
        two_sided += abs(estimate_under_null) >= abs(observed) - 1e-12

    bootstrap = []
    if len(work_keys) >= 2 and len(speakers) >= 2:
        for _ in range(min(draws, 2000)):
            sampled = Counter(rng.choices(work_keys, k=len(work_keys)))
            speaker_weights = Counter(rng.choices(speakers, k=len(speakers)))
            total = count = 0
            for work, weight in sampled.items():
                denominator = sum(speaker_weights[s] for s, _ in works[work])
                if denominator:
                    total += weight * sum(speaker_weights[s] * value for s, value in works[work]) / denominator
                    count += weight
            if count:
                bootstrap.append(total / count)
    interval = None
    if len(bootstrap) >= 2:
        cuts = quantiles(bootstrap, n=40, method='inclusive')
        interval = [cuts[0], cuts[-1]]
    return {'complete_cells': len(rows), 'works': len(work_keys), 'speakers': len(speakers),
            'positive_cells': sum(value > 0 for _, _, value in rows),
            'mean_log_duration_crossover': observed, 'duration_percent': 100 * expm1(observed),
            'permutation': {'draws': draws, 'p_greater': (greater + 1) / (draws + 1),
                            'p_two_sided': (two_sided + 1) / (draws + 1)},
            'crossed_bootstrap_draws': len(bootstrap), 'crossed_bootstrap_interval_95': interval}


def measure(cells, eligible, *, normalized, draws, seed):
    # Each direction first averages its own annotated joins in the same work and speaker.
    effects = defaultdict(list)
    coverage = Counter()
    for cell in cells:
        groups = {direction: [j for j in cell['joins'] if j['a_positive'] == direction and eligible(j)]
                  for direction in (True, False)}
        coverage['eligible_a_only_joins'] += len(groups[True])
        coverage['eligible_b_only_joins'] += len(groups[False])
        if not groups[True] or not groups[False]:
            continue
        work, speaker = cell['work'], cell['speaker']
        fields = ('raw', 'denominator') if normalized else ('raw',)
        for field in fields:
            crossover = (fmean(j[field] for j in groups[True]) - fmean(j[field] for j in groups[False])) / 2
            effects[field].append((work, speaker, crossover))
        if normalized:
            effects['local_ratio'].append((work, speaker, effects['raw'][-1][2] - effects['denominator'][-1][2]))
    return {**dict(coverage), 'raw': estimate(effects['raw'], draws=draws, seed=seed),
            **({key: estimate(effects[key], draws=draws, seed=seed) for key in ('denominator', 'local_ratio')}
               if normalized else {})}, effects['raw']


def evaluate(candidates, manifest, *, draws=10000, seed=20261122):
    if draws < 1:
        raise ValueError('Expected at least one permutation draw')
    cells = paired_cells(candidates, manifest)
    subsets = {
        'strict_model_sites': (lambda join: join['strict'], True),
        'all_matched_left_sites': (lambda join: join['raw'] is not None, False),
        'newly_usable_left_sites': (lambda join: join['raw'] is not None and not join['strict'], False),
        'neither_pause_detected': (lambda join: join['strict'] and join['no_pause'], True),
    }
    result = {'design': 'Equal-direction crossover within each work and speaker, then equal weight per work. '
                        'A whole-work sign swap preserves all speakers and both directions together. '
                        'Bootstrap intervals are descriptive with crossed work and speaker resampling.',
              'candidate_cells': len(cells), 'candidate_joins': sum(len(c['joins']) for c in cells),
              'eligible_subsets': {}}
    for key, (filter_join, normalized) in subsets.items():
        summary, values = measure(cells, filter_join, normalized=normalized, draws=draws, seed=seed)
        if key == 'all_matched_left_sites':
            target = {(work, speaker): delta for work, speaker, delta in values}
        result['eligible_subsets'][key] = summary
    paired = {(c['work'], c['speaker']): c['placebo'] for c in cells
              if c['placebo'] is not None and (c['work'], c['speaker']) in target}
    result['nonboundary_placebo'] = {
        'selection': 'Two distinct text positions with no marked join within one ordinal in either variant. '
                     'Minimize total mean ordinal distance from the respective A and B target sets.',
        'text_eligible_cells': sum(c['placebo_ordinals'] is not None for c in cells),
        'matched_target': estimate([(w, s, target[w, s]) for w, s in paired], draws=draws, seed=seed),
        'matched_placebo': estimate([(w, s, delta) for (w, s), delta in paired.items()], draws=draws, seed=seed),
        'target_minus_placebo': estimate([(w, s, target[w, s] - delta) for (w, s), delta in paired.items()],
                                        draws=draws, seed=seed),
    }
    lead_counts = Counter()
    for cell in cells:
        for join in cell['joins']:
            positive, negative = (('left_a_linked', 'left_b_linked') if join['a_positive']
                                  else ('left_b_linked', 'left_a_linked'))
            lead_counts['positive_left_matched'] += join[positive]
            lead_counts['negative_left_matched'] += join[negative]
            lead_counts['both_left_matched'] += join[positive] and join[negative]
    result['left_link_coverage'] = dict(lead_counts)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--draws', type=int, default=10000)
    args = parser.parse_args()
    candidates = json.loads(args.candidates.read_text(encoding='utf-8'))
    source = args.manifest.read_bytes()
    if candidates['manifest_sha256'] != sha256(source).hexdigest():
        raise ValueError('Candidates were not generated from this exact DEBATE manifest')
    report = evaluate(candidates, json.loads(source), draws=args.draws)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(report, out, ensure_ascii=False, allow_nan=False, indent=2)
        out.write('\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
