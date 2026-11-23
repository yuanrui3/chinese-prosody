#!/bin/bash
#SBATCH --job-name=prosody-function
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:04:00
set -eu
umask 077
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
root=${1:?Gilbreth project}
run=${2:?Frozen challenge directory}
python=${3:?Pinned Python}
output=${4:?New output directory}
cd "$run/code"
exec "$python" -B -m src.quantitative_ending_functions --root "$root" --inputs "$run/inputs" --output "$output"
