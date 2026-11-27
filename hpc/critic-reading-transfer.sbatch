#!/bin/bash
#SBATCH --job-name=critic-readings
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:12:00
set -euo pipefail
umask 077
root=${1:?project root}
run=${2:?run folder}
seal=${3:?input checksum}
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$run/code"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
"$python" hpc/critic-reading-exposure.py "$root" "$run"
"$python" -m src.critic_reading_transfer "$root" "$run" "$seal"
