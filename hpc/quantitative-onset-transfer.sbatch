#!/bin/bash -l
#SBATCH --job-name=prosody-onset-transfer
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=00:12:00

set -euo pipefail
umask 077

if [[ $# -lt 3 || $# -gt 4 ]]; then
    printf 'Usage: sbatch %s SHUNKOU_ROOT CODE_DIR STAGE4_ENV [resume]\n' "$0" >&2
    exit 2
fi
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"

project=$(realpath -e "$1")
code=$(realpath -e "$2")
environment=$(realpath -e "$3")
mode=${4:-new}
if [[ "$mode" != new && "$mode" != resume ]]; then
    printf 'Expected new or resume mode\n' >&2
    exit 2
fi

experiment="$project/model-development/quantitative-onset-transfer"
pilot="$experiment/data/pilot"
results="$experiment/results/onset-transfer"
archive="$project/model-development/historical-increment/data/pilot/annotated.jsonl"
annotations="$pilot/annotated.jsonl"
training="$project/model-development/quantitative-report/results/quantitative-report/report-v4.json"
observations="$results/onset-observations.json"
manifest="$experiment/audio/manifests/synthetic.jsonl"
readings="$code/audio/historical_increment_readings.json"
requirements="$code/hpc/requirements-funasr.txt"
model_cache="$project/cache/aligners/funasr-fa-zh"

mkdir -p "$pilot" "$results"
for directory in "$experiment" "$pilot" "$results"; do
    if [[ "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected a private experiment directory at %s\n' "$directory" >&2
        exit 1
    fi
done
exec 9>"$experiment/.onset-transfer.lock"
if ! flock -n 9; then
    printf 'Another onset transfer job holds the project lock\n' >&2
    exit 1
fi
for artifact in "$results/report.json" "$results/report.md"; do
    if [[ -L "$artifact" || ( -e "$artifact" && ( "$artifact" == "$results/report.json" || "$mode" != resume ) ) ]]; then
        printf 'Onset transfer report already exists at %s\n' "$artifact" >&2
        exit 1
    fi
done

test -f "$environment/ready"
test -x "$environment/bin/python"
for input in "$archive" "$training" "$readings" "$requirements" "$environment/installed.txt"; do
    if [[ ! -f "$input" || ! -s "$input" ]]; then
        printf 'Missing required input at %s\n' "$input" >&2
        exit 1
    fi
done

if [[ ! -e "$annotations" && ! -L "$annotations" ]]; then
    install -m 600 "$archive" "$annotations"
fi
test ! -L "$annotations"
cmp -s "$archive" "$annotations"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_XET=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH
python="$environment/bin/python"
cd "$code"

staging=$(mktemp -d "$experiment/.onset-transfer.XXXXXXXX")
trap 'rm -rf -- "$staging"' EXIT
sha256sum -- "$archive" "$annotations" "$training" "$readings" >"$staging/inputs.sha256"

if [[ "$mode" == new ]]; then
    if [[ -e "$experiment/audio" || -L "$experiment/audio" || -e "$observations" || -L "$observations" ]]; then
        printf 'Existing onset transfer data found. Use resume for a finished synthesis.\n' >&2
        exit 1
    fi
    test -d "$project/cache"
    mkdir -p "$staging/data/pilot"
    install -m 600 "$annotations" "$staging/data/pilot/annotated.jsonl"
    ln -sT "$project/cache" "$staging/cache"
    printf 'Rendering both voices in the eight archived matched pairs\n'
    "$python" -B audio/synthesize.py --root "$staging" --readings "$readings" --offline \
        --voice zm_010 --voice zf_001 --speed 0.9 --seed-reference-voice zm_010
    test -s "$staging/audio/manifests/synthetic.jsonl"
    sha256sum -c -- "$staging/inputs.sha256"
    mv -T -- "$staging/audio" "$experiment/audio"
fi
test -s "$manifest"

if [[ ! -e "$observations" && ! -L "$observations" ]]; then
    env_hash=$(cat "$environment/installed.txt" "$requirements" | sha256sum | cut -c1-12)
    overlay="$project/env/recitation-funasr-py312-$env_hash"
    if [[ ! -f "$overlay/ready" || ! -d "$model_cache" ]]; then
        printf 'The cached FunASR environment and model are required\n' >&2
        exit 1
    fi
    printf 'Measuring waveform onsets and FunASR timestamps in both voices\n'
    PYTHONPATH="$overlay" "$python" -B -m src.quantitative_onset_collect \
        --project "$project" --root "$experiment" --training "$training" \
        --model-cache "$model_cache" --output "$observations"
fi
test -f "$observations"
test ! -L "$observations"
test -s "$observations"

"$python" -B -m src.quantitative_onset_transfer --training "$training" --input "$observations" \
    --output "$staging/report.json" --markdown "$staging/report.md"
test -s "$staging/report.json"
test -s "$staging/report.md"
sha256sum -c -- "$staging/inputs.sha256"
# JSON publication marks completion. A stopped publish may already have placed Markdown.
if [[ -e "$results/report.md" ]]; then
    if ! cmp -s "$staging/report.md" "$results/report.md"; then
        printf 'Existing Markdown differs from the resumed report at %s\n' "$results/report.md" >&2
        exit 1
    fi
else
    mv -T -- "$staging/report.md" "$results/report.md"
fi
mv -T -- "$staging/report.json" "$results/report.json"
