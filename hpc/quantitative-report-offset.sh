#!/bin/bash

set -euo pipefail
umask 077

if [[ $# -ne 3 ]]; then
    printf 'Usage: bash %s SHUNKOU_ROOT CODE_DIR STAGE4_ENV\n' "$0" >&2
    exit 2
fi
project=$(realpath -e "$1")
code=$(realpath -e "$2")
environment=$(realpath -e "$3")
experiment="$project/model-development/quantitative-report"
results="$experiment/results/quantitative-report"
secondary="$results/secondary-alignment.json"

for directory in "$experiment" "$results"; do
    if [[ ! -d "$directory" || "$(realpath -e "$directory")" != "$directory" ]] \
        || (( (8#$(stat -c %a "$directory") & 077) != 0 )); then
        printf 'Expected a private, existing directory at %s\n' "$directory" >&2
        exit 1
    fi
done

exec 9>>"$experiment/.quantitative-report.lock"
if ! flock -n 9; then
    printf 'Another quantitative report job holds the project lock\n' >&2
    exit 1
fi

for input in "$results/report-v3.json" "$secondary"; do
    if [[ ! -s "$input" || ! -f "$input" || -L "$input" ]] \
        || (( (8#$(stat -c %a "$input") & 077) != 0 )); then
        printf 'Expected a completed private input at %s\n' "$input" >&2
        exit 1
    fi
done
for name in report-v4.json report-v4.md; do
    if [[ -e "$results/$name" || -L "$results/$name" ]]; then
        printf 'The requested report already exists at %s\n' "$results/$name" >&2
        exit 1
    fi
done

test -f "$environment/ready"
test -x "$environment/bin/python"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH

staged=$(mktemp -d "$results/.offset-report.XXXXXXXX")
trap 'rm -f -- "$staged/report-v4.json" "$staged/report-v4.md" "$staged/input.sha256" && rmdir -- "$staged"' EXIT
sha256sum -- "$results/report-v3.json" "$secondary" >"$staged/input.sha256"
cd "$code"
timeout 90s "$environment/bin/python" -B -m src.quantitative_report --root "$experiment" \
    --secondary-alignment "$secondary" --check-waveform-offset --output "$staged/report-v4.json"
test -s "$staged/report-v4.json"
test -s "$staged/report-v4.md"
sha256sum -c -- "$staged/input.sha256"
mv -- "$staged/report-v4.md" "$results/report-v4.md"
mv -- "$staged/report-v4.json" "$results/report-v4.json"
