#!/bin/bash -l
#SBATCH --job-name=editorial-audio
#SBATCH --partition=a10
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=00:20:00

set -euo pipefail
umask 077
if (( $# != 5 && $# != 6 )); then
    echo "Usage: sbatch $0 PROJECT CODE STAGE4_ENV WITNESS OUTPUT_DIR [CONTEXT_RESULTS]" >&2
    exit 2
fi
project=$(realpath -e "$1")
code=$(realpath -e "$2")
environment=$(realpath -e "$3")
witness=$(realpath -e "$4")
mkdir -p "$5"
output=$(realpath -e "$5")
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"
[[ "$output" == "$project/"* ]]
test -x "$environment/bin/python"
exec 9>"$output/.audio.lock"
flock -n 9
if [[ ! -e "$output/cache" && ! -L "$output/cache" ]]; then
    ln -s "$project/cache" "$output/cache"
fi
test "$(realpath "$output/cache")" = "$(realpath "$project/cache")"
module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
python="$environment/bin/python"
cd "$code"
if [[ -f "$output/witness.sha256" ]]; then
    sha256sum -c "$output/witness.sha256"
    test "$(cut -d' ' -f1 "$output/witness.sha256")" = "$(sha256sum "$witness" | cut -d' ' -f1)"
else
    sha256sum "$witness" > "$output/witness.sha256"
fi
shared=(--project "$project" --output "$output")
"$python" -B -m src.quantitative_editorial_audio prepare "${shared[@]}" --witness "$witness"
if [[ ! -s "$output/audio/manifests/synthetic.jsonl" ]]; then
    "$python" -B -m audio.synthesize --root "$output" --offline --voice zm_010 --voice zf_001 \
        --speed 0.9 --seed-reference-voice zm_010 --readings "$output/readings.json"
fi
if [[ ! -s "$output/acoustics.json" ]]; then
    "$python" -B -m src.quantitative_editorial_audio measure "${shared[@]}"
fi
if (( $# == 6 )); then
    "$python" -B -m src.quantitative_editorial_audio evaluate "${shared[@]}" --context "$6"
fi
