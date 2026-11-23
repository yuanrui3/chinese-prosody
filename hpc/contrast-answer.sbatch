#!/bin/bash
#SBATCH --job-name=contrast-answer
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=00:12:00
set -euo pipefail
umask 077
root=${1:?project}
run=${2:?run directory}
py=${3:?pinned Python}
phase=${4:?screen, relation, or evaluate}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 HF_HOME="$root/cache/hf" HF_HUB_OFFLINE=1
cd "$run/code"
if [[ "$phase" == relation ]]; then
    exec "$py" -B -m src.contrast_answer_relation "$run"
fi
exec "$py" -B -m src.contrast_answer_test "$phase" "$root" "$run"
