#!/bin/bash -l
#SBATCH --job-name=shunkou-stage4
#SBATCH --time=00:35:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=14G

set -euo pipefail
umask 077

root=${1:?Usage: stage4.sbatch SHUNKOU_ROOT SOURCE_ROOT [passage IDs...]}
code=${2:?Provide source snapshot path}
shift 2
root=$(realpath "$root")
code=$(realpath "$code")
test -s "$root/data/pilot/annotated.jsonl"

export HF_HOME="$root/cache/hf"
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_XET=1
export PIP_CACHE_DIR="$root/cache/pip" TMPDIR="$root/cache/tmp"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
mkdir -p "$HF_HOME" "$PIP_CACHE_DIR" "$TMPDIR" "$root/env" "$root/audio/manifests"

module load anaconda/2024.10-py312
python --version
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader

pin=2.7.1+cu126
dependencies="$code/audio/requirements-stage4.txt"
env_hash=$(sha256sum "$dependencies" | cut -c1-12)
environment="$root/env/stage4-py312-torch-$pin-$env_hash"
exec 9>"$environment.lock"
flock -w 300 9
if [[ ! -f "$environment/ready" ]]; then
    python -m venv "$environment"
    "$environment/bin/python" -m pip --disable-pip-version-check install \
        --retries 2 --timeout 45 --index-url https://download.pytorch.org/whl/cu126 "torch==$pin"
    "$environment/bin/python" -m pip --disable-pip-version-check install \
        --retries 2 --timeout 45 -r "$dependencies"
    "$environment/bin/python" -m pip check
    "$environment/bin/python" -m pip freeze --all > "$environment/installed.txt"
    touch "$environment/ready"
fi
flock -u 9
python="$environment/bin/python"

exec 8>"$root/audio/.stage4.lock"
flock -w 300 8

if ! "$python" "$code/audio/acquire_human.py" --root "$root"; then
    printf 'The independent licensed human reference could not be staged. See acquisition error above.\n' >&2
fi

passages=()
for identifier in "$@"; do passages+=(--passage-id "$identifier"); done
"$python" "$code/audio/synthesize.py" --root "$root" "${passages[@]}"
"$python" "$code/audio/align.py" --root "$root"
"$python" "$code/audio/features.py" --root "$root" \
    --alignments "$root/audio/derived/alignment/alignments.jsonl" \
    --passages "$root/data/pilot/annotated.jsonl" \
    --out-dir "$root/audio/derived/features"
"$python" "$code/audio/check_pilot.py" --root "$root"
"$python" "$code/audio/pause_probe.py" --root "$root"
