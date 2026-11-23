#!/bin/bash
#SBATCH --job-name=grammar-expansion
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
set -eu
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
umask 077

root=${1:?Gilbreth project directory}
run=${2:?Expansion archive with code and inputs}
python=${3:?Pinned Python executable}
output=${4:?New results directory inside the project}
cd "$run/code"
exec "$python" -B -m src.quantitative_grammar_expansion \
  --root "$root" --inputs "$run/inputs" --output "$output" \
  --reference "$root/results/editorial-context-20261122/inputs/reference-context.json" \
  --previous "$root/results/grammatical-patterns-20261122/inputs" --shuffles 199
