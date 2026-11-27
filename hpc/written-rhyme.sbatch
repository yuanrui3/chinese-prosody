#!/bin/bash
#SBATCH --job-name=written-rhyme
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:12:00
set -euo pipefail
umask 077
root=${1:?project directory}
run=${2:?study directory}
phase=${3:?sources, predict or evaluate}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$run/code"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
if [[ "$phase" == sources-and-predict ]]; then
    sha256sum --quiet -c "$run/seals/analysis.sha256"
    "$python" -B -m src.written_rhyme_sources "$root" "$run"
    phase=predict
fi
case "$phase" in
    sources)
        "$python" -B -m src.written_rhyme_sources "$root" "$run"
        ;;
    predict)
        sha256sum --quiet -c "$run/seals/analysis.sha256"
        "$python" -B -c 'from pathlib import Path; import sys; from src.written_rhyme_readers import verify_inputs; verify_inputs(Path(sys.argv[1]))' "$run/inputs"
        "$python" -B -m src.written_rhyme_ablation predict "$root" "$run" --gpu
        ;;
    evaluate)
        sha256sum --quiet -c "$run/seals/analysis.sha256"
        "$python" -B -m src.written_rhyme_readers "$run"
        "$python" -B -m src.written_rhyme_ablation evaluate "$root" "$run" --gpu
        "$python" -B -m src.written_rhyme_ablation evaluate "$root" "$run" --ratings ratings-second.json --output evaluation-second.json --gpu
        ;;
    retrospective)
        sha256sum --quiet -c "$run/seals/analysis.sha256"
        archive="$run/retrospective"
        "$python" -B -m src.written_rhyme_archive prepare "$root" "$archive"
        "$python" -B -m src.written_rhyme_ablation predict "$root" "$archive" --gpu
        "$python" -B -m src.written_rhyme_ablation evaluate "$root" "$archive" --gpu
        "$python" -B -m src.written_rhyme_archive verify "$root" "$archive"
        ;;
    *) exit 2 ;;
esac
