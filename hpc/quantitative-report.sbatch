#!/bin/bash -l
#SBATCH --job-name=shunkou-quantitative
#SBATCH --time=00:18:00
#SBATCH --gpus-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G

set -euo pipefail
umask 077

project=$(realpath "${1:?Provide SHUNKOU_ROOT}")
code=$(realpath "${2:?Provide the uploaded source directory}")
environment=$(realpath "${3:?Provide the Stage 4 environment directory}")
mode=${4:-new}
[[ "$mode" == new || "$mode" == resume ]]
test -n "${SLURM_JOB_ID:?Use a Gilbreth GPU allocation}"
test -f "$environment/ready"

experiment="$project/model-development/quantitative-report"
results="$experiment/results/quantitative-report"
pilot="$experiment/data/pilot"
derived="$experiment/audio/derived"
mkdir -p "$experiment"
test "$(realpath "$experiment")" = "$experiment"
test "$((8#$(stat -c %a "$experiment") & 077))" -eq 0
mkdir -p "$results" "$experiment/data/raw"
exec 9>"$experiment/.quantitative-report.lock"
flock -n 9
test ! -e "$results/report.json"

for shared in cache data/raw/phonology; do
    test -d "$project/$shared"
    if [[ ! -e "$experiment/$shared" && ! -L "$experiment/$shared" ]]; then
        ln -sT "$project/$shared" "$experiment/$shared"
    fi
    test "$(realpath "$experiment/$shared")" = "$(realpath "$project/$shared")"
done

module load anaconda/2024.10-py312
export HF_HOME="$project/cache/hf" MODELSCOPE_CACHE="$project/cache/modelscope"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_XET=1
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONNOUSERSITE=1
unset PYTHONPATH
python="$environment/bin/python"
cd "$code"

if [[ "$mode" == new ]]; then
    echo "Building the new period-matched passage inventory from pinned sources"
    witness=()
    if [[ -f "$pilot/reviewed-witnesses.json" ]]; then
        witness=(--snapshot "$pilot/reviewed-witnesses.json")
    fi
    "$python" -B data/pilot/build.py --root "$experiment" --manifest "$code/data/pilot/voice-report.json" \
        "${witness[@]}"
    "$python" -B data/phonology/annotate.py --root "$experiment" --offline
fi

echo "Checking the new works and credited authors against the archived cohorts"
"$python" -B - "$project" "$pilot/annotated.jsonl" "$results/freshness.json" <<'PY'
from html import unescape
from pathlib import Path
import json
import re
import sys

from src.expansion_design import authors
from src.pilot_validation import read_jsonl, write_json
from src.stage6_listening import digest


def author_keys(row):
    credit = unescape(row['author'])
    credit = re.sub(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]', r'\1', credit)
    credit = re.sub(r'<[^>]*>|(?:作者|Author)\s*[:：]', '', credit, flags=re.I)
    return {value.casefold() for value in authors({**row, 'author': credit})}


project, current, output = map(Path, sys.argv[1:])
archives = ('', 'listening-rounds/mandarin-male', 'pilot-expansions/independent-works',
            'model-development/historical-increment')
identities = ('work_id', 'passage_id', 'text_sha256')
seen = {field: set() for field in identities}
seen_authors = set()
inputs = {}
for cohort in archives:
    path = project / cohort / 'data/pilot/annotated.jsonl'
    rows = read_jsonl(path)
    if not rows:
        raise ValueError(f'Empty archived cohort: {cohort or "original"}')
    inputs[cohort or 'original'] = {'rows': len(rows), 'sha256': digest(path)}
    for field in identities:
        seen[field].update(row[field] for row in rows)
    seen_authors.update(name for row in rows for name in author_keys(row))

fresh = read_jsonl(current)
if not fresh:
    raise ValueError('No evaluation passages')
for row in fresh:
    names = author_keys(row)
    if (not names or names & seen_authors or any(row[field] in seen[field] for field in identities)):
        raise ValueError(f"Repeated or missing work, passage, text or credited author: {row['passage_id']}")
    for field in identities:
        seen[field].add(row[field])
    seen_authors.update(names)
summary = {'passages': len(fresh), 'archives': inputs, 'fresh_sha256': digest(current),
           'author_normalization': 'wikitext link targets, tags, credit prefixes, NFKC, separator and case normalization'}
write_json(output, summary)
print(json.dumps(summary, ensure_ascii=False))
PY

if [[ "$mode" == new ]]; then
    echo "Rendering both voices with the same pronunciation, seed and speed setting"
    "$python" -B audio/synthesize.py --root "$experiment" --readings "$code/audio/voice_report_readings.json" \
        --offline --voice zm_010 --voice zf_001 --speed 0.9 --seed-reference-voice zm_010

    echo "Aligning the exact waveforms and extracting Stage 4 acoustic features"
    "$python" -B audio/align.py --root "$experiment" --offline
    "$python" -B audio/features.py --root "$experiment" \
        --alignments "$derived/alignment/alignments.jsonl" --passages "$pilot/annotated.jsonl" \
        --out-dir "$derived/features"
fi

echo "Building and checking the quantitative report"
"$python" -B -m src.quantitative_report --root "$experiment" --output "$results/report.json"
