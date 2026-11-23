#!/bin/bash -l
#SBATCH --job-name=prosody-pause-replication
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=10G
#SBATCH --time=00:12:00

set -euo pipefail
umask 077
if [[ $# -lt 3 || $# -gt 4 ]]; then
    printf 'Usage: sbatch %s SHUNKOU_ROOT CODE_DIR STAGE4_ENV [REVIEWED_WITNESS_SNAPSHOT]\n' "$0" >&2
    exit 2
fi
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"
project=$(realpath -e "$1")
code=$(realpath -e "$2")
environment=$(realpath -e "$3")
experiment="$project/model-development/quantitative-pause-replication"
results="$experiment/results"
pilot="$experiment/data/pilot"
manifest="$experiment/audio/manifests/synthetic.jsonl"
source_pins="$code/data/pilot/pause-replication.json"
reading_pins="$code/audio/pause_replication_readings.json"
requirements="$code/hpc/requirements-funasr.txt"
model_cache="$project/cache/aligners/funasr-fa-zh"
witness=()
if [[ $# -eq 4 ]]; then
    snapshot=$(realpath -e "$4")
    if [[ "$snapshot" != "$project/sources/"* || ! -f "$snapshot" ]]; then
        printf 'Expected a reviewed witness snapshot under the Gilbreth project sources\n' >&2
        exit 1
    fi
    witness=(--snapshot "$snapshot")
fi

mkdir -p "$results" "$pilot" "$experiment/data/raw"
for directory in "$experiment" "$results" "$pilot" "$experiment/data/raw"; do
    if [[ "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected private pause-replication directories\n' >&2
        exit 1
    fi
done
exec 9>"$experiment/.replication.lock"
flock -n 9
test -s "$source_pins"
test -s "$reading_pins"
test -f "$environment/ready"
if [[ ! -e "$experiment/data/raw/phonology" && ! -L "$experiment/data/raw/phonology" ]]; then
    ln -sT "$project/data/raw/phonology" "$experiment/data/raw/phonology"
fi
test "$(realpath -e "$experiment/data/raw/phonology")" = "$(realpath -e "$project/data/raw/phonology")"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1 HF_HUB_DISABLE_TELEMETRY=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH
python="$environment/bin/python"
cd "$code"
stage=$(mktemp -d "$experiment/.pause-replication.XXXXXXXX")
output_stage=$(mktemp -d "$results/.pause-replication.XXXXXXXX")
trap 'rm -rf -- "$stage" "$output_stage"' EXIT

mkdir -p "$stage/data/pilot" "$stage/data/raw"
ln -sT "$experiment/data/raw/phonology" "$stage/data/raw/phonology"
ln -sT "$project/cache" "$stage/cache"
"$python" -B data/pilot/build.py --root "$stage" --manifest "$source_pins" "${witness[@]}"
"$python" -B data/phonology/annotate.py --root "$stage" --offline
for artifact in passages.jsonl annotated.jsonl annotation-summary.json; do
    if [[ ! -e "$pilot/$artifact" && ! -L "$pilot/$artifact" ]]; then
        install -m 600 "$stage/data/pilot/$artifact" "$pilot/$artifact"
    fi
    test ! -L "$pilot/$artifact"
    cmp -s "$stage/data/pilot/$artifact" "$pilot/$artifact"
done

if [[ ! -s "$manifest" ]]; then
    test ! -e "$experiment/audio" && test ! -L "$experiment/audio"
    "$python" -B audio/synthesize.py --root "$stage" --readings "$reading_pins" \
        --offline --voice zm_010 --voice zf_001 --voice zf_002 --speed 0.9 --seed-reference-voice zm_010
    test -s "$stage/audio/manifests/synthetic.jsonl"
    mv -T -- "$stage/audio" "$experiment/audio"
fi

if [[ ! -s "$results/interior-controls.json" || ! -s "$results/interior-controls.md" ]]; then
    "$python" -B -m src.quantitative_pause_detector_controls --project "$project" --root "$experiment" \
        --output "$output_stage/interior-controls.json" --markdown "$output_stage/interior-controls.md"
    mv -T -- "$output_stage/interior-controls.md" "$results/interior-controls.md"
    mv -T -- "$output_stage/interior-controls.json" "$results/interior-controls.json"
fi

if [[ ! -s "$results/joins.json" || ! -s "$results/joins.md" ]]; then
    env_hash=$(cat "$environment/installed.txt" "$requirements" | sha256sum | cut -c1-12)
    overlay="$project/env/recitation-funasr-py312-$env_hash"
    test -f "$overlay/ready"
    test -d "$model_cache"
    PYTHONPATH="$overlay" "$python" -B -m src.quantitative_pause_detector_joins \
        --project "$project" --root "$experiment" --model-cache "$model_cache" \
        --output "$output_stage/joins.json" --markdown "$output_stage/joins.md"
    mv -T -- "$output_stage/joins.md" "$results/joins.md"
    mv -T -- "$output_stage/joins.json" "$results/joins.json"
fi
