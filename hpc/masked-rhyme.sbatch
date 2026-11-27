#!/bin/bash
#SBATCH --job-name=masked-rhyme
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:35:00
set -euo pipefail
umask 077
root=${1:?project directory}
run=${2:?study directory}
phase=${3:?prepare, score or all}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$run/code"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
case "$phase" in prepare|score|all) ;; *) exit 2 ;; esac
if [[ "$phase" == prepare || "$phase" == all ]]; then
    "$python" -m src.masked_rhyme_sources "$root" "$run"
fi
if [[ "$phase" == score || "$phase" == all ]]; then
    sha256sum --quiet -c "$run/release.sha256"
    "$python" - "$run/inputs" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

folder = Path(sys.argv[1])
for name, expected in json.loads((folder / 'source-seal.json').read_bytes()).items():
    if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
        raise ValueError(f'Changed source packet file: {name}')
PY
    "$python" -m src.masked_rhyme_recovery "$root" "$run/inputs/rows.json" "$run/results"
    "$python" -m src.masked_rhyme_shuffle_check "$root" "$run/inputs/rows.json" "$run/results"
    "$python" hpc/masked-rhyme-gpu.py "$run/results"
fi
