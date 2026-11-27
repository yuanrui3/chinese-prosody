#!/bin/bash
#SBATCH --job-name=work-weighted
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:12:00
set -euo pipefail
umask 077
root=${1:?project directory}
run=${2:?study directory}
phase=${3:?sources-predict, predict, evaluate or retrospective}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$run/code"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
sha256sum --quiet -c "$run/seals/analysis.sha256"
if [[ "$phase" == sources-predict ]]; then
    "$python" -B -m src.work_weighted_sources "$root" "$run"
    phase=predict
fi
case "$phase" in
    predict)
        "$python" -B -c 'from pathlib import Path; import sys; from src.written_rhyme_readers import verify_inputs; verify_inputs(Path(sys.argv[1]))' "$run/inputs"
        "$python" -B -m src.work_weighted_scores predict "$root" "$run" --gpu
        ;;
    evaluate)
        "$python" -B -m src.written_rhyme_readers "$run"
        "$python" -B -m src.work_weighted_scores evaluate "$root" "$run" --gpu
        "$python" -B -m src.work_weighted_scores evaluate "$root" "$run" --ratings ratings-second.json --output evaluation-second.json --gpu
        ;;
    retrospective)
        prior="$root/results/written-rhyme-DvfWnBBA"
        replay="$run/retrospective"
        mkdir -p "$replay/results"
        [[ -d "$replay/inputs" ]] || ln -s "$prior/inputs" "$replay/inputs"
        "$python" -B -m src.work_weighted_scores predict "$root" "$replay" --gpu
        "$python" -B -m src.work_weighted_scores evaluate "$root" "$replay" --gpu
        "$python" -B -m src.work_weighted_scores evaluate "$root" "$replay" --ratings ratings-second.json --output evaluation-second.json --gpu
        ;;
    *) exit 2 ;;
esac
