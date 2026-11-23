#!/bin/bash -l
#SBATCH --job-name=shunkou-rhyme-check
#SBATCH --time=00:12:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G

set -euo pipefail
umask 077

root=$(realpath "${1:?Provide SHUNKOU_ROOT}")
code=$(realpath "${2:?Provide the uploaded code directory}")
environment=$(realpath "${3:?Provide the Stage 4 environment directory}")
test -n "${SLURM_JOB_ID:?Use the Gilbreth GPU allocation}"
test -f "$environment/ready"
experiment="$root/model-development/minimal-endings"
results="$root/model-development/ending-control-extension/results/minimal-endings"
test -s "$results/rhyme-alignment.json"
exec 9>"$results/.window-redecode.lock"
flock -n 9

module load anaconda/2024.10-py312
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
python="$environment/bin/python"
cd "$code"
"$python" -m src.rhyme_window_redecode --root "$experiment" \
    --recovery "$results/rhyme-alignment.json" --output "$results/rhyme-window-alignment.json"
"$python" -m src.rhyme_spectral --root "$experiment" \
    --recovery "$results/rhyme-window-alignment.json" --output "$results/rhyme-window-spectral.json"
