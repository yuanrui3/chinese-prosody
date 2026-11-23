#!/bin/bash -l
#SBATCH --job-name=prosody-internal-check
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
original="$project/model-development/quantitative-report"
experiment="$project/model-development/quantitative-internal-check"
annotations="$original/data/pilot/annotated.jsonl"
results="$original/results/quantitative-report"
output="$results/internal-pause-check.json"
draft="$experiment/audio/derived/synthesis-durations.jsonl"

test -d "$results"
mkdir -p "$experiment/data/pilot"
for directory in "$experiment" "$results" "$experiment/data/pilot"; do
    if [[ "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected private directories for the timing check\n' >&2
        exit 1
    fi
done
exec 9>"$experiment/.internal-check.lock"
flock -n 9
test ! -e "$output" && test ! -L "$output"
test -s "$annotations"
test -f "$environment/ready"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1
export HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_XET=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH
python="$environment/bin/python"
cd "$code"

if [[ ! -s "$draft" ]]; then
    test ! -e "$experiment/audio" && test ! -L "$experiment/audio"
    stage=$(mktemp -d "$experiment/.internal-check.XXXXXXXX")
    trap 'rm -rf -- "$stage"' EXIT
    mkdir -p "$stage/data/pilot"
    install -m 600 "$annotations" "$stage/data/pilot/annotated.jsonl"
    ln -sT "$project/cache" "$stage/cache"
    "$python" -B audio/synthesize.py --root "$stage" --readings "$code/audio/voice_report_readings.json" \
        --offline --voice zm_010 --voice zf_001 --speed 0.9 --seed-reference-voice zm_010 \
        --duration-draft "$stage/audio/derived/synthesis-durations.jsonl"
    cmp -s "$annotations" "$stage/data/pilot/annotated.jsonl"
    install -m 600 "$stage/data/pilot/annotated.jsonl" "$experiment/data/pilot/annotated.jsonl"
    mv -T -- "$stage/audio" "$experiment/audio"
fi

cmp -s "$annotations" "$experiment/data/pilot/annotated.jsonl"
"$python" -B -m src.quantitative_internal_check --root "$original" --regenerated "$experiment" --output "$output"
