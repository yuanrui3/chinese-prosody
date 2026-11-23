#!/bin/bash -l
#SBATCH --job-name=prosody-second-aligner
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=00:08:00

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
experiment="$project/model-development/quantitative-report"
results="$experiment/results/quantitative-report"
secondary="$results/secondary-alignment.json"
report="$results/report-v3.json"

for directory in "$experiment" "$results"; do
    if [[ ! -d "$directory" || "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected a private, existing directory at %s\n' "$directory" >&2
        exit 1
    fi
done

exec 9>"$experiment/.quantitative-report.lock"
if ! flock -n 9; then
    printf 'Another quantitative report job holds the project lock\n' >&2
    exit 1
fi

if [[ -e "$report" || -L "$report" ]]; then
    printf 'The requested report already exists at %s\n' "$report" >&2
    exit 1
fi

requirements="$code/hpc/requirements-funasr.txt"
test -f "$environment/ready"
test -x "$environment/bin/python"
for input in "$environment/installed.txt" "$requirements" \
    "$experiment/data/pilot/annotated.jsonl" \
    "$experiment/audio/manifests/synthetic.jsonl" \
    "$experiment/audio/derived/features/syllables.jsonl" \
    "$experiment/audio/derived/features/recordings.jsonl"; do
    if [[ ! -s "$input" || ! -f "$input" ]]; then
        printf 'Missing or empty required input %s\n' "$input" >&2
        exit 1
    fi
done

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_XET=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH

cd "$code"
if [[ ! -e "$secondary" && ! -L "$secondary" ]]; then
    env_hash=$(cat "$environment/installed.txt" "$requirements" | sha256sum | cut -c1-12)
    overlay="$project/env/recitation-funasr-py312-$env_hash"
    model_cache="$project/cache/aligners/funasr-fa-zh"
    if [[ ! -f "$overlay/ready" || ! -d "$model_cache" ]]; then
        printf 'The existing FunASR environment and local model cache are required\n' >&2
        exit 1
    fi

    PYTHONPATH="$overlay" "$environment/bin/python" -B -m src.quantitative_second_alignment \
        --project "$project" --root "$experiment" --model-cache "$model_cache"
fi

if [[ ! -s "$secondary" || ! -f "$secondary" || -L "$secondary" ]]; then
    printf 'Expected a complete second alignment at %s\n' "$secondary" >&2
    exit 1
fi

"$environment/bin/python" -B -m src.quantitative_report --root "$experiment" \
    --secondary-alignment "$secondary" --output "$report"
