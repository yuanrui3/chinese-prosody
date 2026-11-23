"""Try a coarse second alignment only at junctions the primary path could not score."""

import argparse
import json
from pathlib import Path

from src.quantitative_preboundary_rescue_eval import eligible


def merge(primary, secondary):
    if (primary['manifest_sha256'] != secondary['manifest_sha256']
            or len(primary['rows']) != len(secondary['rows'])
            or secondary.get('rescue_mode') != 'qwen_coarse'):
        raise ValueError('Expected primary and coarse drafts of the same candidate set')
    fields = ('recording_id', 'ordinal', 'label', 'speaker', 'work', 'genre', 'left_char', 'right_char')
    rows = []
    for before, after in zip(primary['rows'], secondary['rows'], strict=True):
        if any(before[key] != after[key] for key in fields):
            raise ValueError('Candidate set or ordering differs across alignments')
        use_fallback = not eligible(before) and eligible(after)
        row = after if use_fallback else before
        rows.append({**row, 'qwen_identity_at_junction': use_fallback,
                     'feature_source': 'qwen_coarse' if use_fallback else 'charsiu'})
    return {'manifest_sha256': primary['manifest_sha256'], 'rescue_mode': 'qwen_coarse_fallback',
            'qwen_model_revision': secondary['qwen_model_revision'],
            'charsiu_model_revision': primary['charsiu_model_revision'],
            'feature_sources': {'charsiu': primary['frame_s'], 'qwen_coarse': secondary['frame_s']},
            'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('primary', 'secondary', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    primary = json.loads(args.primary.read_text(encoding='utf-8'))
    secondary = json.loads(args.secondary.read_text(encoding='utf-8'))
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(merge(primary, secondary), handle, ensure_ascii=False, allow_nan=False)
        handle.write('\n')


if __name__ == '__main__':
    main()
