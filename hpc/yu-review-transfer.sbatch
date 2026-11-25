#!/bin/bash
#SBATCH --job-name=yu-review-transfer
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:05:00
set -euo pipefail
umask 077
run=${1:?Gilbreth study directory}
phase=${2:?prepare or evaluate}
cd "$run"
sha256sum -c seals/hypothesis.sha256 seals/rule.sha256
python3 - "$run" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
folder = Path(sys.argv[1]) / 'inputs'
seal = json.loads((folder / 'source-seal.json').read_text())
for name in ('corpus.json', 'reading.json', 'sources.json'):
    if hashlib.sha256((folder / name).read_bytes()).hexdigest() != seal[name]:
        raise SystemExit(f'Source seal differs for {name}')
PY
case "$phase" in
    prepare)
        cd "$run/code"
        python3 -B -m src.yu_review_transfer prepare "$run"
        cd "$run"
        sha256sum private/signals.json > seals/signals.sha256
        ;;
    evaluate)
        sha256sum -c seals/signals.sha256 seals/editorial.sha256 seals/baseline.sha256
        cd "$run/code"
        python3 -B -m src.yu_review_transfer evaluate "$run"
        ;;
    *)
        echo "Expected prepare or evaluate" >&2
        exit 2
        ;;
esac
