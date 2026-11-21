#!/bin/bash -l
#SBATCH --job-name=shunkou-stage5
#SBATCH --time=00:08:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G

set -euo pipefail
umask 077

root=$(realpath "${1:?Usage: stage5.sbatch SHUNKOU_ROOT SOURCE_ROOT STAGE4_ENV}")
code=$(realpath "${2:?Provide the uploaded source root}")
environment=$(realpath "${3:?Provide the completed Stage 4 environment directory}")
test -f "$environment/ready"

module load anaconda/2024.10-py312
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export SHUNKOU_ROOT="$root"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
cd "$code"
"$environment/bin/python" -m unittest discover -s tests -v
"$environment/bin/python" -m src.pilot_validation --root "$root" --draws 999 --seed 20261121 --device cuda
