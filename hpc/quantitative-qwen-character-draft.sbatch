#!/bin/bash -l
#SBATCH --job-name=qwen-char-draft
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:10:00

set -euo pipefail
umask 077
if (( $# != 7 )); then
    printf 'Usage: sbatch %s PROJECT CODE STAGE4_ENV QWEN_PACKAGES MODEL MANIFEST DRAFT_JSON\n' "$0" >&2
    exit 2
fi

project=$(realpath -e "$1")
code=$(realpath -e "$2")
env=$(realpath -e "$3")
packages=$(realpath -e "$4")
test -n "${SLURM_JOB_ID:?Use a Gilbreth Slurm allocation}"
test -x "$env/bin/python"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
export PYTHONPATH="$packages"

cd "$code"
"$env/bin/python" -B -m src.quantitative_qwen_character_draft --project "$project" \
    --manifest "$6" --model "$5" --output "$7"
