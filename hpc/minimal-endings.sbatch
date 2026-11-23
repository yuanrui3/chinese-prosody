#!/bin/bash -l
#SBATCH --job-name=shunkou-minimal
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

experiment="$root/model-development/minimal-endings"
mkdir -p "$experiment/data/pilot"
exec 9>"$experiment/.build.lock"
flock -n 9
test ! -e "$experiment/results/minimal-endings/analysis.json"

source="$root/model-development/historical-increment/data/pilot/annotated.jsonl"
annotation="$experiment/data/pilot/annotated.jsonl"
for link in "$annotation" "$experiment/cache"; do
    if [[ "$link" == "$annotation" ]]; then
        target="$source"
    else
        target="$root/cache"
    fi
    if [[ ! -L "$link" ]]; then
        ln -sT "$target" "$link"
    fi
    test "$(realpath "$link")" = "$(realpath "$target")"
done
test -s "$annotation"

module load anaconda/2024.10-py312
export HF_HOME="$root/cache/hf" HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1
export HF_HUB_DISABLE_TELEMETRY=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
python="$environment/bin/python"
cd "$code"
"$python" audio/synthesize.py --root "$experiment" --readings "$code/audio/historical_increment_readings.json" \
    --ending-plan "$code/audio/minimal_ending_sites.json" --voice zm_010 --speed 0.9 --offline
"$python" audio/align.py --root "$experiment" --experimental-endings --offline
"$python" audio/features.py --root "$experiment" \
    --alignments "$experiment/audio/derived/alignment/alignments.jsonl" \
    --passages "$annotation" --out-dir "$experiment/audio/derived/features"
"$python" -m src.minimal_ending_analysis --root "$experiment"
