#!/bin/bash
#SBATCH --job-name=phrase-meaning
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=3G
#SBATCH --time=00:05:00
set -euo pipefail
umask 077
root=${1:?project root}
run=${2:?study directory}
phase=${3:?baseline or evaluate}
cd "$run"
sha256sum -c seals/protocol.sha256 seals/analysis.sha256
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export PYTHONPATH="$root/results/cadence-completion-20261123/code"
py="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
case "$phase" in
    baseline)
        cd code
        input_sha=$("$py" -c 'import json,sys; print(json.load(open(sys.argv[1]))["corpus.json"])' "$run/inputs/source-seal.json")
        "$py" -B -m src.yu_review_baseline "$root" "$run" "$root/results/ai-jiangnan-complete-20261123-N0QpQKI1" "$input_sha"
        cd "$run"
        sha256sum results/baseline.json > seals/baseline.sha256
        ;;
    evaluate)
        sha256sum -c seals/editorial.sha256 seals/audit-grades.sha256 seals/baseline.sha256 seals/pair-packet.sha256 seals/relation.sha256 seals/audit-packet.sha256
        cd code
        "$py" -B -m src.semantic_turn_test evaluate "$run"
        ;;
    *)
        echo "Expected baseline or evaluate" >&2
        exit 2
        ;;
esac
