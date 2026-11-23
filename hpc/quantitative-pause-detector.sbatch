#!/bin/bash -l
#SBATCH --job-name=prosody-pause-detector
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=10G
#SBATCH --time=00:16:00

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
experiment="$project/model-development/quantitative-pause-detector"
results="$experiment/results"
annotations="$experiment/data/pilot/annotated.jsonl"
archive="$project/pilot-expansions/independent-works/data/pilot/annotated.jsonl"
manifest="$experiment/audio/manifests/synthetic.jsonl"
requirements="$code/hpc/requirements-funasr.txt"
model_cache="$project/cache/aligners/funasr-fa-zh"

mkdir -p "$results" "$experiment/data/pilot"
for directory in "$experiment" "$results" "$experiment/data/pilot"; do
    if [[ "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected private pause-detector directories\n' >&2
        exit 1
    fi
done
exec 9>"$experiment/.detector.lock"
flock -n 9
test -s "$archive"
test -f "$environment/ready"
if [[ ! -e "$annotations" && ! -L "$annotations" ]]; then
    install -m 600 "$archive" "$annotations"
fi
test ! -L "$annotations"
cmp -s "$archive" "$annotations"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1 HF_HUB_DISABLE_TELEMETRY=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH
python="$environment/bin/python"
cd "$code"
stage=$(mktemp -d "$experiment/.pause-detector.XXXXXXXX")
trap 'rm -rf -- "$stage"' EXIT

if [[ ! -s "$manifest" ]]; then
    test ! -e "$experiment/audio" && test ! -L "$experiment/audio"
    mkdir -p "$stage/data/pilot"
    install -m 600 "$annotations" "$stage/data/pilot/annotated.jsonl"
    ln -sT "$project/cache" "$stage/cache"
    "$python" -B audio/synthesize.py --root "$stage" --readings "$code/audio/expansion_readings.json" \
        --offline --voice zm_010 --voice zf_001 --voice zf_002 --speed 0.9 --seed-reference-voice zm_010
    test -s "$stage/audio/manifests/synthetic.jsonl"
    cmp -s "$annotations" "$stage/data/pilot/annotated.jsonl"
    mv -T -- "$stage/audio" "$experiment/audio"
fi

if [[ ! -s "$results/interior-controls.json" ]]; then
    "$python" -B -m src.quantitative_pause_detector_controls --project "$project" --root "$experiment" \
        --output "$results/interior-controls.json" --markdown "$results/interior-controls.md"
fi

if [[ ! -s "$results/joins.json" ]]; then
    env_hash=$(cat "$environment/installed.txt" "$requirements" | sha256sum | cut -c1-12)
    overlay="$project/env/recitation-funasr-py312-$env_hash"
    test -f "$overlay/ready"
    test -d "$model_cache"
    PYTHONPATH="$overlay" "$python" -B -m src.quantitative_pause_detector_joins \
        --project "$project" --root "$experiment" --model-cache "$model_cache" \
        --output "$results/joins.json" --markdown "$results/joins.md"
fi
