#!/bin/bash -l
#SBATCH --job-name=prosody-third-voice
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=10G
#SBATCH --time=00:10:00

set -euo pipefail
umask 077
if [[ $# -lt 3 || $# -gt 4 ]]; then
    printf 'Usage: sbatch %s SHUNKOU_ROOT CODE_DIR STAGE4_ENV [onset|duration]\n' "$0" >&2
    exit 2
fi
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"
project=$(realpath -e "$1")
code=$(realpath -e "$2")
environment=$(realpath -e "$3")
mode=${4:-onset}
case "$mode" in
    onset)
        experiment="$project/model-development/quantitative-onset-third-voice"
        results="$experiment/results/third-voice"
        original="$project/model-development/quantitative-onset-transfer/data/pilot/annotated.jsonl"
        readings="$code/audio/historical_increment_readings.json"
        test -s "$project/model-development/quantitative-onset-transfer/results/onset-transfer/onset-observations.json"
        ;;
    duration)
        experiment="$project/model-development/quantitative-historical-third-voice"
        results="$experiment/results/historical-third-voice"
        original="$project/model-development/quantitative-report/data/pilot/annotated.jsonl"
        readings="$code/audio/voice_report_readings.json"
        test -s "$project/model-development/quantitative-onset-transfer/results/onset-transfer/historical-duration-transfer.json"
        ;;
    *)
        printf 'Expected onset or duration mode\n' >&2
        exit 2
        ;;
esac
annotations="$experiment/data/pilot/annotated.jsonl"
manifest="$experiment/audio/manifests/synthetic.jsonl"
requirements="$code/hpc/requirements-funasr.txt"
model_cache="$project/cache/aligners/funasr-fa-zh"

mkdir -p "$results" "$experiment/data/pilot"
for directory in "$experiment" "$results" "$experiment/data/pilot"; do
    if [[ "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected private directories for the third-voice check\n' >&2
        exit 1
    fi
done
exec 9>"$experiment/.third-voice.lock"
flock -n 9
for artifact in "$results/report.json" "$results/report.md"; do
    test ! -e "$artifact" && test ! -L "$artifact"
done
test -f "$environment/ready"
test -s "$original"
test -s "$readings"
if [[ ! -e "$annotations" && ! -L "$annotations" ]]; then
    install -m 600 "$original" "$annotations"
fi
test ! -L "$annotations"
cmp -s "$original" "$annotations"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1
export HF_HUB_DISABLE_TELEMETRY=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
unset PYTHONPATH
python="$environment/bin/python"
cd "$code"
stage=$(mktemp -d "$experiment/.third-voice.XXXXXXXX")
trap 'rm -rf -- "$stage"' EXIT

if [[ ! -s "$manifest" ]]; then
    test ! -e "$experiment/audio" && test ! -L "$experiment/audio"
    mkdir -p "$stage/data/pilot"
    install -m 600 "$annotations" "$stage/data/pilot/annotated.jsonl"
    ln -sT "$project/cache" "$stage/cache"
    "$python" -B audio/synthesize.py --root "$stage" --readings "$readings" \
        --offline --voice zf_002 --speed 0.9 --seed-reference-voice zm_010
    test -s "$stage/audio/manifests/synthetic.jsonl"
    cmp -s "$annotations" "$stage/data/pilot/annotated.jsonl"
    mv -T -- "$stage/audio" "$experiment/audio"
fi

if [[ "$mode" == onset ]]; then
    env_hash=$(cat "$environment/installed.txt" "$requirements" | sha256sum | cut -c1-12)
    overlay="$project/env/recitation-funasr-py312-$env_hash"
    test -f "$overlay/ready"
    test -d "$model_cache"
    PYTHONPATH="$overlay" "$python" -B -m src.quantitative_onset_voice_check \
        --project "$project" --root "$experiment" --model-cache "$model_cache" \
        --output "$results/report.json" --markdown "$results/report.md"
else
    "$python" -B -m src.quantitative_historical_third_voice \
        --project "$project" --root "$experiment" --output "$results/report.json"
fi
