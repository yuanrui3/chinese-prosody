#!/bin/bash -l
#SBATCH --job-name=critic-variant-audio
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=00:15:00

set -euo pipefail
umask 077
project=$(realpath -e "${1:?Project directory}")
code=$(realpath -e "${2:?Code directory}")
environment=$(realpath -e "${3:?Stage 4 environment}")
config=$(realpath -e "${4:?Witness configuration}")
mkdir -p "${5:?Audio results directory}"
out=$(realpath -e "$5")
[[ "$out" == "$project/"* ]]
test -n "${SLURM_JOB_ID:?Submit through Slurm}"
exec 9>"$out/.lock"
flock -n 9
if [[ ! -e "$out/cache" ]]; then ln -s "$project/cache" "$out/cache"; fi
test "$(realpath "$out/cache")" = "$(realpath "$project/cache")"
module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH
python="$environment/bin/python"
cd "$code"
if [[ -f "$out/config.sha256" ]]; then
    sha256sum -c "$out/config.sha256"
    test "$(cut -d' ' -f1 "$out/config.sha256")" = "$(sha256sum "$config" | cut -d' ' -f1)"
else
    sha256sum "$config" > "$out/config.sha256"
fi
"$python" -B -m src.critical_variant_audio prepare "$config" "$out"
if [[ ! -s "$out/audio/manifests/synthetic.jsonl" ]]; then
    "$python" -B -m audio.synthesize --root "$out" --readings "$out/readings.json" \
        --family-controls "$out/families.json" --offline --speed 0.9 --seed-reference-voice zm_010 \
        --voice zm_010 --voice zf_001 --voice zf_002
fi
if [[ ! -s "$out/audio/derived/alignment/alignments.jsonl" ]]; then
    "$python" -B -m audio.align --root "$out" --offline
fi
"$python" -B -m src.critical_variant_audio measure "$config" "$out"
sha256sum "$out/summary.json" "$out/measured.json" "$out/audio/manifests/synthetic.jsonl"
