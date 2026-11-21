"""Run prespecified text controls and draft-audio checks for the prose pilot."""

import argparse
from collections import defaultdict
import hashlib
from itertools import product
import json
from math import fsum
from pathlib import Path
import random
from statistics import mean
from tempfile import TemporaryDirectory

from src.audio_validation import compare_audio
from src.text_metrics import METRIC_LABELS, METRIC_NULLS, clauses, metric_results, slot_label


NULLS = ('within_clause', 'clause_order', 'tone_stratified')
TIERS = ('guangyun', 'pingshui')
INPUTS = (
    'data/pilot/annotated.jsonl',
    'audio/manifests/synthetic.jsonl',
    'audio/derived/features/recordings.jsonl',
    'audio/derived/features/syllables.jsonl',
    'audio/derived/features/gaps.jsonl',
)


def read_jsonl(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as directory:
        draft = Path(directory) / path.name
        draft.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
        draft.replace(path)


def shuffle_syllables(passage, rng):
    positions = []
    for group in clauses(passage):
        shuffled = list(group)
        rng.shuffle(shuffled)
        for destination, source in zip(group, shuffled):
            positions.append({**destination, 'char': source['char'], 'readings': source['readings']})
    return {**passage, 'slots': positions}


def shuffle_clauses(passage, rng):
    groups = clauses(passage)
    shuffled = list(groups)
    rng.shuffle(shuffled)
    positions = []
    for destination, source in zip(groups, shuffled):
        for slot in source:
            positions.append({**slot, 'slot_index': len(positions), 'clause_index': destination[0]['clause_index']})
        boundary = destination[-1]
        positions[-1].update(boundary_after=boundary['boundary_after'], marks_after=boundary.get('marks_after', ''))
    return {**passage, 'slots': positions}


def resample_tones(passages, tier, rng):
    strata = defaultdict(list)
    for passage_index, passage in enumerate(passages):
        stratum = passage['period'], passage['genre']
        for slot_index, slot in enumerate(passage['slots']):
            label = slot_label(slot, tier, 'pingze')
            if label in ('平', '仄'):
                strata[stratum].append((passage_index, slot_index, label))
    resampled = [{**passage, 'slots': list(passage['slots'])} for passage in passages]
    for pool in strata.values():
        labels = [label for _, _, label in pool]
        rng.shuffle(labels)
        for (passage_index, slot_index, _), label in zip(pool, labels):
            slots = resampled[passage_index]['slots']
            slots[slot_index] = {**slots[slot_index], 'null_pingze': {tier: label}}
    return resampled


def weights_by_work(passages):
    counts = defaultdict(int)
    for passage in passages:
        counts[passage['work_id']] += 1
    return [1 / (len(counts) * counts[passage['work_id']]) for passage in passages]


def bootstrap_interval(effects, rng, draws=1999):
    if len(effects) < 2:
        return None
    results = sorted(mean(rng.choices(effects, k=len(effects))) for _ in range(draws))
    return [results[int(0.025 * draws)], results[int(0.975 * draws)]]


def reduce_permutations(values, weights, device):
    """Batch work-weighted means and two-sided randomization tails on CUDA if requested."""
    if device == 'cuda':
        import torch

        draws = torch.tensor(values, dtype=torch.float64, device='cuda')
        weight = torch.tensor(weights, dtype=torch.float64, device='cuda')
        statistics = draws.mv(weight)
        center = statistics.mean()
        distances = (statistics - center).abs()
        p = (distances >= distances[0] - 1e-12).double().mean().item()
        return statistics[0].item(), statistics[1:].mean().item(), p, draws[1:].mean(dim=0).tolist()

    statistics = [fsum(value * weight for value, weight in zip(row, weights)) for row in values]
    center = mean(statistics)
    threshold = abs(statistics[0] - center) - 1e-12
    p = sum(abs(statistic - center) >= threshold for statistic in statistics) / len(statistics)
    return statistics[0], mean(statistics[1:]), p, [mean(column[1:]) for column in zip(*values)]


def holm_adjust(rows):
    tested = sorted((row for row in rows if row.get('p_value') is not None), key=lambda row: row['p_value'])
    maximum = 0.0
    for index, row in enumerate(tested):
        maximum = max(maximum, row['p_value'] * (len(tested) - index))
        row['p_holm'] = min(1.0, maximum)


def control_tests(passages, tier, observed, draws, seed, device):
    results = []
    support = {metric: [index for index, row in enumerate(observed) if row[metric].value is not None]
               for metric in METRIC_LABELS}
    for null_index, null in enumerate(NULLS):
        rng = random.Random(seed + 1009 * null_index)
        accepted = {metric: [] for metric, indices in support.items() if indices and null in METRIC_NULLS[metric]}
        invariant = [metric for metric in METRIC_LABELS if null not in METRIC_NULLS[metric]]
        for _ in range(draws):
            if null == 'tone_stratified':
                controls = resample_tones(passages, tier, rng)
            else:
                shuffle = shuffle_syllables if null == 'within_clause' else shuffle_clauses
                controls = [shuffle(passage, rng) for passage in passages]
            estimates = [metric_results(passage, tier) for passage in controls]
            for actual, replicate in zip(observed, estimates):
                for metric in invariant:
                    if actual[metric] != replicate[metric]:
                        raise ValueError(f'{tier}: {metric} unexpectedly changed under {null}')
            for metric, values in accepted.items():
                replicate = [estimates[index][metric].value for index in support[metric]]
                if all(value is not None for value in replicate):
                    values.append(replicate)

        for metric, indices in support.items():
            row = {'null': null, 'metric': metric, 'passages': len(indices),
                   'work_count': len({passages[index]['work_id'] for index in indices}),
                   'draws_requested': draws, 'p_value': None, 'p_holm': None}
            results.append(row)
            if null not in METRIC_NULLS[metric]:
                row['status'] = 'invariant_by_design'
                continue
            if not accepted.get(metric):
                row.update(status='unavailable', draws_used=0)
                continue
            cohort = [passages[index] for index in indices]
            actual = [observed[index][metric].value for index in indices]
            resamples = accepted[metric]
            real, reference, p, per_passage = reduce_permutations([actual, *resamples], weights_by_work(cohort), device)
            per_work = defaultdict(list)
            for passage, value, expected in zip(cohort, actual, per_passage):
                per_work[passage['work_id']].append(value - expected)
            interval = bootstrap_interval([mean(values) for values in per_work.values()],
                                          random.Random(seed + 1291 + null_index))
            row.update(status='tested', draws_used=len(resamples), observed=real, control_mean=reference,
                       real_minus_control=real - reference, p_value=p, work_bootstrap_95=interval)
    holm_adjust(results)
    return results


def matched_pairs(passages):
    grouped = defaultdict(dict)
    for index, passage in enumerate(passages):
        identifier, genre = passage['pair_id'], passage['genre']
        if genre in grouped[identifier]:
            raise ValueError(f'{identifier}: duplicated matched genre')
        grouped[identifier][genre] = index
    if any(set(pair) != {'parallel_prose', 'comparison_prose'} for pair in grouped.values()):
        raise ValueError('Every matched set must contain one passage of each prose genre')
    return [(identifier, pair['parallel_prose'], pair['comparison_prose'])
            for identifier, pair in sorted(grouped.items())]


def work_blocks(pairs, passages):
    blocks = []
    for identifier, left, right in pairs:
        works = {passages[left]['work_id'], passages[right]['work_id']}
        hits = [block for block in blocks if works & block[1]]
        ids = {identifier}
        for block in hits:
            ids.update(block[0])
            works.update(block[1])
            blocks.remove(block)
        blocks.append((ids, works))
    return [sorted(ids) for ids, _ in blocks]


def genre_checks(passages, observed):
    pairs = matched_pairs(passages)
    membership = work_blocks(pairs, passages)
    results = {}
    for metric in METRIC_LABELS:
        differences = {}
        for identifier, left, right in pairs:
            a, b = observed[left][metric].value, observed[right][metric].value
            if a is not None and b is not None:
                differences[identifier] = a - b
        block_sums = [sum(differences[key] for key in block if key in differences)
                      for block in membership if any(key in differences for key in block)]
        total = sum(block_sums)
        assignments = list(product((-1, 1), repeat=len(block_sums))) if block_sums else []
        p = (sum(abs(sum(sign * delta for sign, delta in zip(signs, block_sums))) >= abs(total) - 1e-12
                 for signs in assignments) / len(assignments) if assignments else None)
        results[metric] = {'paired_differences': differences,
                           'mean_parallel_minus_comparison': mean(differences.values()) if differences else None,
                           'parallel_higher': sum(value > 1e-12 for value in differences.values()),
                           'comparison_higher': sum(value < -1e-12 for value in differences.values()),
                           'ties': sum(abs(value) <= 1e-12 for value in differences.values()),
                           'block_sign_swap_p': p, 'assignments': len(assignments)}
    return {'work_connected_pair_blocks': membership, 'metrics': results}


def validate(root, destination, draws, seed, device):
    if device == 'cuda':
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError('CUDA validation requires an allocated Gilbreth GPU')
        print(f'Batched permutation reduction on {torch.cuda.get_device_name()}', flush=True)
    passages = read_jsonl(root / INPUTS[0])
    matched = [passage for passage in passages if passage['subset'] == 'matched']
    if not matched or len({row['passage_id'] for row in passages}) != len(passages):
        raise ValueError('Expected unique IDs and a nonempty matched pilot')
    result = {'seed': seed, 'draws_per_control': draws, 'device': device, 'matched_passages': len(matched),
              'source_sha256': {}, 'metrics': METRIC_LABELS, 'tiers': {}}
    for relative in INPUTS:
        with (root / relative).open('rb') as stream:
            result['source_sha256'][relative] = hashlib.sha256(stream.read()).hexdigest()
    for tier in TIERS:
        scores = {row['passage_id']: metric_results(row, tier) for row in passages}
        original = [scores[row['passage_id']] for row in matched]
        nulls = control_tests(matched, tier, original, draws, seed, device)
        retained = sorted({row['metric'] for row in nulls if row.get('p_holm') is not None and row['p_holm'] <= 0.05})
        result['tiers'][tier] = {'shuffled_controls': nulls, 'genre_checks': genre_checks(matched, original),
                                 'control_sensitive_metrics': retained,
                                 'descriptive_only_metrics': sorted(set(METRIC_LABELS) - set(retained)),
                                 'observed': {identifier: {name: vars(estimate) for name, estimate in row.items()}
                                              for identifier, row in scores.items()}}
        print(f'{tier}: {sum(row["status"] == "tested" for row in nulls)} tests, {len(retained)} retained control signals',
              flush=True)
    primary = result['tiers']['guangyun']['observed']
    text_values = {identifier: {name: estimate['value'] for name, estimate in row.items()}
                   for identifier, row in primary.items()}
    result['audio'] = compare_audio(root, passages, text_values)
    write_json(destination, result)
    print(f'Validation written to {destination}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--draws', type=int, default=999)
    parser.add_argument('--seed', type=int, default=20261121)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    args = parser.parse_args()
    if args.draws < 1:
        parser.error('--draws must be positive')
    root = args.root.resolve(strict=True)
    validate(root, args.output or root / 'results/stage5/validation.json', args.draws, args.seed, args.device)


if __name__ == '__main__':
    main()
