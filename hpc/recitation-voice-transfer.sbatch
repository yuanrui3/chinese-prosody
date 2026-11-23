#!/bin/bash -l
#SBATCH --job-name=shunkou-phrasing-voice
#SBATCH --time=00:12:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G

set -euo pipefail
umask 077

project=$(realpath "${1:?Provide SHUNKOU_ROOT}")
code=$(realpath "${2:?Provide the uploaded code directory}")
environment=$(realpath "${3:?Provide the Stage 4 environment directory}")
mode=${4:-new}
[[ "$mode" == new || "$mode" == resume ]]
reference="$project/model-development/recitation-phrasing-alignment"
experiment="$project/model-development/recitation-voice-transfer"
results="results/recitation-phrasing"
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"
test -f "$environment/ready"
for item in stimuli pcm-alignment forced-alignment second-aligner-comparison; do
    test -s "$reference/$results/$item.json"
done

# Resolve the same overlay as recitation-funasr.sbatch without modifying it.
requirements="$code/hpc/requirements-funasr.txt"
env_hash=$(cat "$environment/installed.txt" "$requirements" | sha256sum | cut -c1-12)
overlay="$project/env/recitation-funasr-py312-$env_hash"
if [[ ! -f "$overlay/ready" ]]; then
    echo "Run the reference recitation-funasr.sbatch to prepare its pinned overlay first" >&2
    exit 1
fi
aligner_cache="$project/cache/aligners/funasr-fa-zh"
test -d "$aligner_cache"

mkdir -p "$experiment"
test "$(realpath "$experiment")" = "$experiment"
exec 9>"$experiment/.voice-transfer.lock"
flock -n 9
if [[ -e "$experiment/$results/voice-transfer.json" ]]; then
    echo "The second-voice benchmark has already completed at $experiment/$results/voice-transfer.json" >&2
    exit 1
fi
if [[ ! -e "$experiment/cache" && ! -L "$experiment/cache" ]]; then
    ln -sT "$project/cache" "$experiment/cache"
fi
test "$(realpath "$experiment/cache")" = "$(realpath "$project/cache")"

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_XET=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH
python="$environment/bin/python"
cd "$code"

transfer=(--project "$project" --reference "$reference" --root "$experiment")
if [[ "$mode" == new ]]; then
    echo "Preparing the pinned source passages and pronunciation prescriptions"
    "$python" -B -m src.recitation_voice_transfer "${transfer[@]}" --prepare
    echo "Rendering the second synthetic voice"
    "$python" -B audio/synthesize.py --root "$experiment" --offline --voice zf_001 --speed 0.9 \
        --readings "$experiment/data/pilot/voice-transfer-readings.json" \
        --duration-draft "$experiment/audio/derived/synthesis-durations.jsonl" --seed-reference-voice zm_010
    echo "Drafting the second voice's phone timings"
    "$python" -B audio/align.py --root "$experiment" --offline
    "$python" -B audio/features.py --root "$experiment" \
        --alignments "$experiment/audio/derived/alignment/alignments.jsonl" \
        --passages "$experiment/data/pilot/annotated.jsonl" --out-dir "$experiment/audio/derived/features"
fi
echo "Rendering controlled pairs and checking exact PCM reconstruction"
"$python" -B -m src.recitation_voice_transfer "${transfer[@]}" --render
"$python" -B -m src.recitation_pcm_alignment --root "$experiment"
echo "Timing the second voice with the pinned FunASR aligner"
PYTHONPATH="$overlay" "$python" -B -m src.recitation_second_aligner --project "$project" --root "$experiment" \
    --model-cache "$aligner_cache"
"$python" -B -m src.recitation_second_aligner_analysis --root "$experiment" \
    --alignment "$experiment/$results/forced-alignment.json"
echo "Evaluating the frozen threshold against exact PCM timing"
"$python" -B -m src.recitation_voice_transfer_report --reference "$reference" --root "$experiment"
