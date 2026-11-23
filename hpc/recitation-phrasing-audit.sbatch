#!/bin/bash -l
#SBATCH --job-name=shunkou-phrasing
#SBATCH --time=00:06:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G

set -euo pipefail
umask 077

project=$(realpath "${1:?Provide SHUNKOU_ROOT}")
code=$(realpath "${2:?Provide the uploaded code directory}")
environment=$(realpath "${3:?Provide the Stage 4 environment directory}")
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"
test -f "$environment/ready"

experiment="$project/model-development/recitation-phrasing"
test -s "$experiment/results/recitation-phrasing/stimuli.json"
test -s "$experiment/results/recitation-phrasing/audio-check.json"
exec 9>"$experiment/.analysis.lock"
flock -n 9
module load anaconda/2024.10-py312
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
python="$environment/bin/python"
cd "$code"

"$python" -m src.recitation_phrasing_decode --project "$project" --root "$experiment"
