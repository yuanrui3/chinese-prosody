#!/bin/bash -l
#SBATCH --job-name=preboundary-duration
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=00:10:00

set -euo pipefail
umask 077
if (( $# != 5 && $# != 7 )); then
    printf 'Usage: sbatch %s PROJECT CODE STAGE4_ENV RECORDINGS_MANIFEST OUTPUT_DIR [QWEN_DRAFT MODE]\n' "$0" >&2
    exit 2
fi

project=$(realpath -e "$1")
code=$(realpath -e "$2")
env=$(realpath -e "$3")
manifest=$(realpath -e "$4")
mkdir -p "$5"
destination=$(realpath -e "$5")
test -n "${SLURM_JOB_ID:?Use a Gilbreth Slurm allocation}"
test -x "$env/bin/python"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH

cd "$code"
rescue_args=()
if (( $# == 7 )); then
    rescue_args=(--qwen-draft "$6" --rescue-mode "$7")
fi
"$env/bin/python" -B -m src.quantitative_preboundary_features --project "$project" \
    --manifest "$manifest" --output "$destination/candidates.json" "${rescue_args[@]}"
"$env/bin/python" -B -m src.quantitative_preboundary_duration --input "$destination/candidates.json" \
    --output "$destination/evaluation.json"
