#!/bin/bash -l
#SBATCH --job-name=shunkou-expansion
#SBATCH --time=00:15:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G

set -euo pipefail
umask 077

root=$(realpath "${1:?Usage: expand-pilot.sbatch SHUNKOU_ROOT SOURCE_ROOT STAGE4_ENV}")
code=$(realpath "${2:?Provide source snapshot path}")
environment=$(realpath "${3:?Provide completed Stage 4 environment directory}")
test -n "${SLURM_JOB_ID:?Run in a Gilbreth Slurm GPU allocation}"
test -f "$environment/ready"

round="$root/pilot-expansions/independent-works"
mkdir -p "$round/data/raw"
exec 9>"$round/.build.lock"
flock -n 9
test ! -e "$round/audio/stage6/listening/survey.json"
for shared in cache data/raw/phonology; do
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

witness="$round/data/pilot/reviewed-witnesses.json"
input=()
if [[ -f "$witness" ]]; then
    input=(--snapshot "$witness")
fi
"$python" data/pilot/build.py --root "$round" --manifest "$code/data/pilot/expansion-passages.json" "${input[@]}"
"$python" data/phonology/annotate.py --root "$round" --offline
"$python" -m src.expansion_design --root "$round" --reference "$root/data/pilot/annotated.jsonl"
"$python" -m src.expansion_tasks --root "$round" --production-only

"$python" - "$round" "$code/audio/expansion_readings.json" <<'PY'
import json
from pathlib import Path
import sys

from src.pilot_validation import read_jsonl

passages = read_jsonl(Path(sys.argv[1]) / 'data/pilot/annotated.jsonl')
readings = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
if readings.keys() != {row['passage_id'] for row in passages if row['task'] == 'listening'}:
    raise ValueError('Audio recipes must cover precisely the excerpts assigned to listening')
PY
"$python" audio/synthesize.py --root "$round" --readings "$code/audio/expansion_readings.json" \
    --offline --voice zm_010 --speed 0.9
"$python" audio/align.py --root "$round" --offline
"$python" audio/features.py --root "$round" \
    --alignments "$round/audio/derived/alignment/alignments.jsonl" \
    --passages "$round/data/pilot/annotated.jsonl" --out-dir "$round/audio/derived/features"
"$python" audio/check_pilot.py --root "$round"
"$python" -m src.expansion_tasks --root "$round" --voice zm_010 --speed 0.9
