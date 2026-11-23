#!/bin/bash -l
#SBATCH --job-name=prosody-noise-aware
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=10G
#SBATCH --time=00:14:00

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
experiment="$project/model-development/quantitative-pause-replication"
results="$experiment/results"
requirements="$code/hpc/requirements-funasr.txt"
model_cache="$project/cache/aligners/funasr-fa-zh"

for directory in "$experiment" "$results"; do
    if [[ "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected owner-only replication directories\n' >&2
        exit 1
    fi
done
exec 9>"$experiment/.noise-aware.lock"
flock -n 9
test -f "$environment/ready"
test -s "$results/joins.json"
test -s "$experiment/audio/manifests/synthetic.jsonl"
env_hash=$(cat "$environment/installed.txt" "$requirements" | sha256sum | cut -c1-12)
overlay="$project/env/recitation-funasr-py312-$env_hash"
test -f "$overlay/ready"
test -d "$model_cache"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1 HF_HUB_DISABLE_TELEMETRY=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH
python="$environment/bin/python"
cd "$code"
stage=$(mktemp -d "$results/.noise-aware.XXXXXXXX")
trap 'rm -rf -- "$stage"' EXIT

if [[ ! -s "$results/noise-aware-inserts.json" || ! -s "$results/noise-aware-inserts.md" ]]; then
    "$python" -B -m src.quantitative_noise_detector_eval --project "$project" --root "$experiment" \
        --output "$stage/noise-aware-inserts.json" --markdown "$stage/noise-aware-inserts.md"
    mv -T -- "$stage/noise-aware-inserts.md" "$results/noise-aware-inserts.md"
    mv -T -- "$stage/noise-aware-inserts.json" "$results/noise-aware-inserts.json"
fi
if [[ ! -s "$results/noise-aware-joins.json" || ! -s "$results/noise-aware-joins.md" ]]; then
    PYTHONPATH="$overlay" "$python" -B -m src.quantitative_noise_detector_joins \
        --project "$project" --root "$experiment" --model-cache "$model_cache" \
        --output "$stage/noise-aware-joins.json" --markdown "$stage/noise-aware-joins.md"
    mv -T -- "$stage/noise-aware-joins.md" "$results/noise-aware-joins.md"
    mv -T -- "$stage/noise-aware-joins.json" "$results/noise-aware-joins.json"
fi
