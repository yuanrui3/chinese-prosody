#!/bin/bash
#SBATCH --job-name=cadence-completion
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=00:09:00
set -euo pipefail
umask 077
root=${1:?Gilbreth project}
run=${2:?Study directory}
python=${3:?Pinned Python}
shift 3
export HF_HOME="$root/cache/hf" HF_HUB_OFFLINE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
cd "$run/code"
for phase in "$@"; do
    "$python" -B -m src.cadence_completion "$phase" "$root" "$run"
done
