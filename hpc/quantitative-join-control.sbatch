#!/bin/bash -l
#SBATCH --job-name=prosody-join-control
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:10:00

set -euo pipefail
umask 077
if [[ $# -ne 3 ]]; then
    printf 'Usage: sbatch %s SHUNKOU_ROOT CODE_DIR STAGE4_ENV\n' "$0" >&2
    exit 2
fi
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"
project=$(realpath -e "$1")
code=$(realpath -e "$2")
environment=$(realpath -e "$3")
experiment="$project/model-development/quantitative-join-control"
results="$experiment/results/join-control"
source_results="$project/model-development/quantitative-onset-transfer/results/onset-transfer"
requirements="$code/hpc/requirements-funasr.txt"
model_cache="$project/cache/aligners/funasr-fa-zh"

mkdir -p "$results"
for directory in "$experiment" "$results"; do
    if [[ "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected private directories for the join control\n' >&2
        exit 1
    fi
done
exec 9>"$experiment/.join-control.lock"
flock -n 9
test ! -e "$results/report.json" && test ! -L "$results/report.json"
test -s "$source_results/report.json"
test -s "$source_results/onset-observations.json"
test -f "$environment/ready"
env_hash=$(cat "$environment/installed.txt" "$requirements" | sha256sum | cut -c1-12)
overlay="$project/env/recitation-funasr-py312-$env_hash"
test -f "$overlay/ready"
test -d "$model_cache"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_XET=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
cd "$code"
PYTHONPATH="$overlay" "$environment/bin/python" -B -m src.quantitative_join_control \
    --project "$project" --root "$experiment" --model-cache "$model_cache" \
    --output "$results/report.json" --markdown "$results/report.md"
