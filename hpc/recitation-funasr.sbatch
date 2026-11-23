#!/bin/bash -l
#SBATCH --job-name=shunkou-phrasing-funasr
#SBATCH --time=00:15:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G

set -euo pipefail
umask 077

project=$(realpath "${1:?Provide SHUNKOU_ROOT}")
code=$(realpath "${2:?Provide the uploaded code directory}")
environment=$(realpath "${3:?Provide the Stage 4 environment directory}")
experiment="$project/model-development/recitation-phrasing-alignment"
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"
test -f "$environment/ready"
test -s "$experiment/results/recitation-phrasing/stimuli.json"
test -s "$experiment/results/recitation-phrasing/pcm-alignment.json"
exec 8>"$experiment/.second-aligner.lock"
flock -n 8

module load anaconda/2024.10-py312
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_XET=1
export PIP_CACHE_DIR="$project/cache/pip" TMPDIR="$project/cache/tmp"
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
unset PYTHONPATH
mkdir -p "$HF_HOME" "$MODELSCOPE_CACHE" "$PIP_CACHE_DIR" "$TMPDIR" "$project/env"

python="$environment/bin/python"
pin=2.7.1+cu126
requirements="$code/hpc/requirements-funasr.txt"
env_hash=$(cat "$environment/installed.txt" "$requirements" | sha256sum | cut -c1-12)
overlay="$project/env/recitation-funasr-py312-$env_hash"
exec 9>"$overlay.lock"
flock -w 300 9

check_environment() {
    PYTHONPATH="$1" "$python" -m pip --disable-pip-version-check check
    PYTHONPATH="$1" "$python" - "$pin" <<'PY'
from importlib.metadata import version
import sys

import torch
import torchaudio
from funasr import AutoModel
from funasr.register import tables

pin = sys.argv[1]
assert torch.__version__ == torchaudio.__version__ == pin
assert torch.cuda.is_available(), "The Stage 4 interpreter cannot see its allocated GPU"
assert version("funasr") == "1.2.7"
assert AutoModel and "MonotonicAligner" in tables.model_classes
print(f"FunASR {version('funasr')} with PyTorch {pin} on {torch.cuda.get_device_name()}")
PY
}

if [[ ! -f "$overlay/ready" ]]; then
    staging=$(mktemp -d "$project/env/.recitation-funasr.XXXXXXXX")
    trap 'rm -rf -- "$staging"' EXIT
    pip=("$python" -m pip --disable-pip-version-check install --retries 2 --timeout 45)
    "${pip[@]}" --index-url https://download.pytorch.org/whl/cu126 \
        --no-deps --only-binary=:all: --target "$staging" "torchaudio==$pin"

    # Resolve against Stage 4 first. A direct installation with --target would
    # otherwise resolve from scratch and shadow its PyTorch and numerical stack.
    PYTHONPATH="$staging" "${pip[@]}" --index-url https://pypi.org/simple \
        --dry-run --report "$staging/install-plan.json" \
        -c "$environment/installed.txt" -r "$requirements"
    PYTHONPATH="$staging" "$python" - "$staging" <<'PY'
import json
from importlib.metadata import distributions
from pathlib import Path
import sys

from pip._vendor.packaging.utils import canonicalize_name

target = Path(sys.argv[1])
plan = json.loads((target / "install-plan.json").read_text())
installed = {canonicalize_name(item.metadata["Name"]) for item in distributions()}
resolved = []
for item in plan["install"]:
    meta = item["metadata"]
    name = canonicalize_name(meta["name"])
    if name in installed:
        raise SystemExit(f"The FunASR overlay would shadow an existing dependency: {name}")
    resolved.append(f"{name}=={meta['version']}")
(target / "resolved.txt").write_text("\n".join(sorted(resolved)) + "\n")
PY
    "${pip[@]}" --index-url https://pypi.org/simple --no-deps \
        --target "$staging" -r "$staging/resolved.txt"
    check_environment "$staging"
    touch "$staging/ready"
    mv -T -- "$staging" "$overlay"
    trap - EXIT
fi
flock -u 9

export PYTHONPATH="$overlay"
check_environment "$overlay"
cd "$code"
"$python" -B -m src.recitation_second_aligner --project "$project" --root "$experiment" \
    --model-cache "$project/cache/aligners/funasr-fa-zh"
"$python" -B -m src.recitation_second_aligner_analysis --root "$experiment" \
    --alignment "$experiment/results/recitation-phrasing/forced-alignment.json"
