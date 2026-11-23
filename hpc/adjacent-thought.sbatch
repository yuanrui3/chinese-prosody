#!/bin/bash
#SBATCH --job-name=prosody-thought
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:03:00
set -eu
umask 077
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
root=${1:?Gilbreth project}
run=${2:?Experiment directory}
python=${3:?Pinned Python}
phase=${4:?audit or test}
out=${5:?New output}
cd "$run/code"
case "$phase" in
    audit) exec "$python" -B -m src.written_tie_audit --root "$root" --out "$out" ;;
    test) exec "$python" -B -m src.adjacent_thought_transfer --root "$root" --run "$run" --out "$out" ;;
    *) exit 2 ;;
esac
