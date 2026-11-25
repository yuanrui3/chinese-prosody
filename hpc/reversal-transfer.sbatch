#!/bin/bash
#SBATCH --job-name=reversal-transfer
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=00:15:00
set -euo pipefail
umask 077
root=${1:?project}
run=${2:?study}
phase=${3:?phase}
py="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
export PYTHONPATH="$root/results/cadence-completion-20261123/code" HF_HOME="$root/cache/hf" HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
cd "$run"
sha256sum -c seals/design.sha256 seals/code.sha256
cd code
case "$phase" in
    develop) "$py" -B -m src.reversal_detector develop "$run" ;;
    apply)
        cd "$run"
        sha256sum -c seals/test.sha256
        cd code
        "$py" -B -m src.reversal_detector apply "$run"
        "$py" -B -m src.semantic_turn_relation classify "$run/previous"
        corpus_sha=$("$py" -c 'import json,sys;print(json.load(open(sys.argv[1]))["corpus.json"])' "$run/inputs/source-seal.json")
        "$py" -B -m src.yu_review_baseline "$root" "$run" "$root/results/ai-jiangnan-complete-20261123-N0QpQKI1" "$corpus_sha"
        ;;
    *) exit 2 ;;
esac
