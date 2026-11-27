#!/bin/bash
#SBATCH --job-name=within-work-rank
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:10:00
set -euo pipefail
umask 077
root=${1:?project directory}
run=${2:?study directory}
phase=${3:?sources, predict, evaluate or verify}
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$run/code"
if [[ "$phase" == sources ]]; then
    sha256sum --quiet -c "$run/seals/sources.sha256"
    exec "$python" -B -m src.within_work_sources "$root" "$run"
fi
sha256sum --quiet -c "$run/seals/analysis.sha256"
case "$phase" in
    predict)
        "$python" -B -c 'from pathlib import Path; import sys; from src.written_rhyme_readers import verify_inputs; verify_inputs(Path(sys.argv[1]))' "$run/inputs"
        "$python" -B -m src.within_work_rank predict "$root" "$run" --gpu
        ;;
    evaluate)
        "$python" -B -m src.written_rhyme_readers "$run"
        "$python" -B -m src.within_work_rank evaluate "$root" "$run" --gpu
        "$python" -B -m src.within_work_rank evaluate "$root" "$run" --gpu --ratings ratings-second.json --output evaluation-second.json
        ;;
    verify)
        "$python" -B "$run/audit/within-work-rank-summary.py" "$root" "$run" > "$run/results/summary.tmp"
        mv "$run/results/summary.tmp" "$run/results/summary.json"
        ;;
    *) exit 2 ;;
esac
