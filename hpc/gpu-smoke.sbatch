#!/bin/bash
#SBATCH --job-name=shunkou-gpu-smoke
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --gpus-per-node=1
#SBATCH --mem=2G
#SBATCH --time=00:02:00

set -euo pipefail

printf 'Job: %s\nNode: %s\nCUDA_VISIBLE_DEVICES: %s\n' \
  "${SLURM_JOB_ID:?Run this script through sbatch}" "$(hostname)" \
  "${CUDA_VISIBLE_DEVICES:?Slurm did not expose a GPU}"
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
