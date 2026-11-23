#!/bin/bash -l
#SBATCH --job-name=prosody-pause-lexical
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=10G
#SBATCH --time=00:18:00

set -euo pipefail
umask 077
if [[ $# -lt 3 || $# -gt 4 ]]; then
    printf 'Usage: sbatch %s SHUNKOU_ROOT CODE_DIR STAGE4_ENV [base|small]\n' "$0" >&2
    exit 2
fi
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"
project=$(realpath -e "$1")
code=$(realpath -e "$2")
environment=$(realpath -e "$3")
variant=${4:-base}
[[ "$variant" == base || "$variant" == small ]]
experiment="$project/model-development/quantitative-pause-lexical"
results="$experiment/results"
if [[ "$variant" == small ]]; then
    results="$experiment/results-small"
fi
cache="$project/cache/recognizers/whisper-$variant"
holdout="$project/model-development/quantitative-pause-benchmark/results-v2/report.json"
mkdir -p "$results"
for directory in "$experiment" "$results"; do
    if [[ "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected private lexical-audit directories\n' >&2
        exit 1
    fi
done
exec 9>"$experiment/.lexical.lock"
flock -n 9
for output in "$results/report.json" "$results/report.md"; do
    test ! -e "$output" && test ! -L "$output"
done
test -f "$environment/ready"
test -d "$cache"
test -s "$holdout"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1
export HF_HUB_DISABLE_XET=1 HF_HUB_DISABLE_TELEMETRY=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH
cd "$code"
"$environment/bin/python" -B -m src.quantitative_pause_lexical \
    --project "$project" --model-cache "$cache" --heldout-report "$holdout" --variant "$variant" \
    --output "$results/report.json" --markdown "$results/report.md"
