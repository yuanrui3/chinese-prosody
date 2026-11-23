#!/bin/bash -l
#SBATCH --job-name=shunkou-historical
#SBATCH --time=00:20:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G

set -euo pipefail
umask 077

root=$(realpath "${1:?Provide SHUNKOU_ROOT}")
code=$(realpath "${2:?Provide the uploaded code directory}")
environment=$(realpath "${3:?Provide the Stage 4 environment directory}")
test -n "${SLURM_JOB_ID:?Use a Gilbreth Slurm GPU allocation}"
test -f "$environment/ready"

fresh="$root/model-development/historical-increment"
mkdir -p "$fresh/data/raw" "$fresh/results/historical-increment"
exec 9>"$fresh/.build.lock"
flock -n 9
test ! -e "$fresh/results/historical-increment/stage5.json"
for shared in cache data/raw/phonology; do
    if [[ ! -L "$fresh/$shared" ]]; then
        ln -sT "$root/$shared" "$fresh/$shared"
    fi
    test "$(realpath "$fresh/$shared")" = "$(realpath "$root/$shared")"
done

module load anaconda/2024.10-py312
export HF_HOME="$root/cache/hf" HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1
export HF_HUB_DISABLE_TELEMETRY=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
python="$environment/bin/python"
cd "$code"

input=()
witness="$fresh/data/pilot/reviewed-witnesses.json"
if [[ -f "$witness" ]]; then
    input=(--snapshot "$witness")
fi
"$python" data/pilot/build.py --root "$fresh" --manifest "$code/data/pilot/historical-increment.json" "${input[@]}"
"$python" data/phonology/annotate.py --root "$fresh" --offline
"$python" -m src.historical_increment --root "$root" --fresh "$fresh" --check-corpus
"$python" audio/synthesize.py --root "$fresh" --readings "$code/audio/historical_increment_readings.json" \
    --offline --voice zm_010 --speed 0.9
"$python" -m src.historical_increment --root "$root" --fresh "$fresh"
"$python" audio/align.py --root "$fresh" --offline
"$python" audio/features.py --root "$fresh" \
    --alignments "$fresh/audio/derived/alignment/alignments.jsonl" \
    --passages "$fresh/data/pilot/annotated.jsonl" --out-dir "$fresh/audio/derived/features"
"$python" audio/check_pilot.py --root "$fresh"
"$python" -m src.pilot_validation --root "$fresh" --output "$fresh/results/historical-increment/stage5.json" --device cuda
