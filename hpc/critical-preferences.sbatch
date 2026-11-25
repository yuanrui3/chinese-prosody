#!/bin/bash
#SBATCH --job-name=critic-variants
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:12:00
set -euo pipefail
umask 077
root=${1:?Gilbreth project root}
run=${2:?sealed study directory}
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$run/code"
"$python" -m src.critical_preferences seal "$root" "$run"
"$python" -m src.critical_preferences score "$root" "$run"
"$python" -m src.critical_reading_probe "$root" "$run"
