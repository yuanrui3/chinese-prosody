#!/bin/bash
#SBATCH --job-name=semicolon-turn
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=00:15:00
set -euo pipefail
umask 077
root=${1:?project root}
run=${2:?study directory}
phase=${3:?forecast or evaluate}
py="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export PYTHONPATH="$root/results/cadence-completion-20261123/code"
export HF_HOME="$root/cache/hf" HF_HUB_OFFLINE=1
cd "$run"
sha256sum -c seals/protocol.sha256 seals/analysis.sha256 seals/pair-packet.sha256
case "$phase" in
    forecast)
        cd code
        corpus_sha=$("$py" -c 'import json,sys; print(json.load(open(sys.argv[1]))["corpus.json"])' "$run/inputs/source-seal.json")
        "$py" -B -m src.yu_review_baseline "$root" "$run" "$root/results/ai-jiangnan-complete-20261123-N0QpQKI1" "$corpus_sha"
        "$py" -B -m src.semantic_turn_relation classify "$run"
        cd "$run"
        sha256sum results/baseline.json results/baseline-provenance.json > seals/baseline.sha256
        ;;
    evaluate)
        sha256sum -c seals/editorial.sha256 seals/baseline.sha256 seals/relation.sha256
        cd code
        "$py" -B -m src.semicolon_turn_test "$run"
        cd "$run"
        sha256sum results/comparison.json private/joined.json > seals/results.sha256
        ;;
    *) echo "Expected forecast or evaluate" >&2; exit 2 ;;
esac
