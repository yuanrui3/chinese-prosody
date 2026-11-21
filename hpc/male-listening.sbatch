#!/bin/bash -l
#SBATCH --job-name=shunkou-male-listening
#SBATCH --time=00:14:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G

set -euo pipefail
umask 077

root=$(realpath "${1:?Usage: male-listening.sbatch SHUNKOU_ROOT SOURCE_ROOT STAGE4_ENV}")
code=$(realpath "${2:?Provide source snapshot path}")
environment=$(realpath "${3:?Provide completed Stage 4 environment directory}")
test -n "${SLURM_JOB_ID:?Run in a Gilbreth Slurm GPU allocation}"
test -f "$environment/ready"
round="$root/listening-rounds/mandarin-male"
mkdir -p "$round"
exec 9>"$round/.build.lock"
flock -n 9
test ! -e "$round/audio/stage6/listening/survey.json"
for shared in data cache; do
    if [[ ! -L "$round/$shared" ]]; then
        ln -sT "$root/$shared" "$round/$shared"
    fi
    test "$(realpath "$round/$shared")" = "$(realpath "$root/$shared")"
done

module load anaconda/2024.10-py312
export HF_HOME="$root/cache/hf" HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1
export HF_HUB_DISABLE_TELEMETRY=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
python="$environment/bin/python"
cd "$code"
"$python" - "$root/cache/hf/hub" <<'PY'
from pathlib import Path
import sys

from huggingface_hub import hf_hub_download
from audio.synthesize import ASSET_SHA256, MALE_VOICE, REPO, REVISION, sha256

name = f'voices/{MALE_VOICE}.pt'
asset = hf_hub_download(REPO, name, revision=REVISION, cache_dir=sys.argv[1])
if sha256(Path(asset)) != ASSET_SHA256[name]:
    raise ValueError('Male voice embedding differs from the publisher checksum')
PY
"$python" audio/synthesize.py --root "$round" --offline --voice zm_010 --speed 0.9 \
    --passage-id SD01 --passage-id SD03 --passage-id SD04 --passage-id ET05 \
    --passage-id ET06 --passage-id NS01 --passage-id NS02
"$python" audio/align.py --root "$round" --offline
"$python" audio/features.py --root "$round" \
    --alignments "$round/audio/derived/alignment/alignments.jsonl" \
    --passages "$round/data/pilot/annotated.jsonl" --out-dir "$round/audio/derived/features"
"$python" audio/check_pilot.py --root "$round"
"$python" audio/pause_probe.py --root "$round"
"$python" -m src.stage6_listening prepare --root "$round" --voice zm_010 --speed 0.9 --prefix M
"$python" -m src.stage6_survey_page --root "$round" --overall
