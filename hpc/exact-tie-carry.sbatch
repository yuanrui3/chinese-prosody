#!/bin/bash
#SBATCH --job-name=prosody-tie
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
phase=${4:?screen or test}
output=${5:?New output directory}
cd "$run/code"
exec "$python" -B -m src.exact_tie_transfer "$phase" --root "$root" --run "$run" --out "$output" "${@:6}"
