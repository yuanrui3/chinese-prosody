#!/usr/bin/env bash

set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

root=${1:?Usage: stage3-pilot.sh PROJECT_ROOT [--snapshot WITNESS_JSON]}
shift
code=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python=${SHUNKOU_PYTHON:-python3}

mkdir -p "$root/data" "$root/audio/raw" "$root/audio/derived" "$root/audio/manifests"
"$python" --version
"$python" "$code/data/pilot/build.py" --root "$root" "$@"
"$python" "$code/data/phonology/annotate.py" --root "$root" \
    --overrides "$code/data/pilot/context-reviews.json"
