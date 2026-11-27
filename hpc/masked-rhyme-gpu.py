"""Independently replay the held-out 賦 work bootstrap on an allocated CUDA GPU."""

import argparse
from hashlib import sha256
import json
from math import isclose
from pathlib import Path
import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.masked_rhyme_recovery import seeded
from src.yu_review_baseline import save_sealed


TOLERANCE = 1e-12
HALF_POINTS = {'win': 2, 'loss': 0, 'tie': 1, 'abstain': 1}


def require_close(observed, expected):
    if not isclose(observed, expected, rel_tol=0, abs_tol=TOLERANCE):
        raise ValueError(f'Bootstrap replay differs from primary value: {observed!r} vs {expected!r}')


def verify(folder):
    if not torch.cuda.is_available():
        raise RuntimeError('This verification requires allocated CUDA hardware.')
    files = {name: (folder / f'{name}.json').read_bytes() for name in ('seal', 'items', 'work_results', 'summary')}
    data = {name: json.loads(content) for name, content in files.items()}
    held = data['summary']['test']['fu']
    work_deltas = {}
    for work in data['work_results']:
        if (work['split'], work['genre']) != ('test', 'fu') or not work['trials']:
            continue
        key = work['work_id']
        items = data['items'][key]
        sealed_ids = data['seal']['trials'][key]
        if len(items) != work['trials'] or len(items) != len(sealed_ids) or {r['id'] for r in items} != set(sealed_ids):
            raise ValueError(f'{key}: item outcomes disagree with the sealed trial roster.')
        half = {m: sum(HALF_POINTS[r['outcomes'][m]] for r in items) for m in ('local', 'run')}
        for method, earned in half.items():
            require_close(earned / (2 * len(items)), work['intact'][method]['accuracy'])
        work_deltas[key] = (half['run'] - half['local']) / (2 * len(items))
    n = len(work_deltas)
    if not n or n != held['eligible_works']:
        raise ValueError('Invalid eligible work count for CUDA replay.')
    draws = data['seal']['protocol']['work_bootstraps']
    rng = seeded('bootstrap', 'test', 'fu')
    indices = torch.tensor([rng.choices(range(n), k=n) for _ in range(draws)], dtype=torch.int64, device='cuda')
    deltas = torch.tensor(list(work_deltas.values()), dtype=torch.float64, device='cuda')
    simulations = deltas[indices].mean(dim=1)
    probabilities = torch.tensor([.025, .975], dtype=torch.float64, device='cuda')
    interval = torch.quantile(simulations, probabilities, interpolation='linear').tolist()
    difference = deltas.mean().item()
    require_close(difference, held['run_minus_local'])
    for measured, published in zip(interval, held['bootstrap_95']):
        require_close(measured, published)
    report = {'verified': True, 'gpu': torch.cuda.get_device_name(), 'torch': str(torch.__version__),
              'cuda': torch.version.cuda, 'precision': 'float64', 'draws': draws, 'works': n,
              'run_minus_local': difference, 'bootstrap_95': interval, 'absolute_tolerance': TOLERANCE,
              'input_sha256': {name: sha256(raw).hexdigest() for name, raw in files.items()}}
    save_sealed(folder / 'cuda-verification.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    print(json.dumps(verify(parser.parse_args().results)))
