"""Use archived ManDi lexical alignment and a separate text-only clause tier."""

import argparse
from collections import Counter
from itertools import accumulate
import json
from pathlib import Path
import re


# Zhao's thesis, Appendix d, p. 170. Ordinals count Han characters only.
PROMPT_ROW_ENDS = (3, 18, 22, 29, 38, 46, 47, 64, 71, 79, 83, 85,
                   91, 104, 108, 113, 118, 121, 127, 140, 149, 159)
# Conservative text-only review. Temporal frames and ambiguous analyses are tracked separately.
CLAUSE_ENDS = (18, 29, 38, 64, 71, 83, 91, 104, 113, 118, 127, 140)
TEMPORAL_FRAME_ENDS = (22, 108)
AMBIGUOUS_ENDS = (46, 47, 79, 149)
HAN = re.compile(r'[\u3400-\u9fff]')
INTERVAL = re.compile(r'intervals \[\d+\]:\s+xmin = (\S+)\s+xmax = (\S+)\s+text = "((?:[^"]|"")*)"')


def tiers(path):
    raw = path.read_bytes()
    text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    result = {}
    for tier in re.split(r'\n\s*item \[\d+\]:', text)[1:]:
        name = re.search(r'\bname = "([^"]+)"', tier)
        if not name:
            raise ValueError(f'Missing tier name in {path}')
        result[name[1]] = [(float(left), float(right), label.replace('""', '"'))
                           for left, right, label in INTERVAL.findall(tier)]
    return result


def build(root, manifest):
    recordings = []
    excluded = []
    for entry in manifest['recordings']:
        key = entry['recording_id']
        if not entry.get('output_textgrid'):
            excluded.append({'id': key, 'reason': 'no_published_mfa_grid'})
            continue
        archive = tiers(root / entry['output_textgrid'])
        words = [row for row in archive['words'] if HAN.search(row[2])]
        lengths = [len(HAN.findall(row[2])) for row in words]
        # MFA sometimes merges adjacent prompt rows and can include a title before the passage.
        layouts = [(index, list(accumulate(lengths[index:]))) for index in range(len(lengths))
                   if sum(lengths[:index]) <= 8 and sum(lengths[index:]) == PROMPT_ROW_ENDS[-1]]
        if (len(layouts) != 1 or not set(layouts[0][1]).issubset(PROMPT_ROW_ENDS)
                or not {38, 46}.issubset(layouts[0][1])):
            excluded.append({'id': key, 'reason': 'prompt_rows_do_not_match', 'row_lengths': lengths})
            continue
        offset, aligned_ends = layouts[0]
        words = words[offset:]
        gaps = [{'after_char': after, 'start_s': left[1], 'end_s': right[0]}
                for after, left, right in zip(aligned_ends, words, words[1:])]
        by_ordinal = {gap['after_char']: gap for gap in gaps}
        utterances = tiers(root / entry['input_textgrid'])['utterance']
        recordings.append({'id': key, 'speaker': key.removesuffix('_CMN_NWS'), 'work': 'ManDi-NWS',
                           'path': entry['wav'], 'score_start_s': words[0][0], 'score_end_s': words[-1][1],
                           'pauses': [gap for gap in gaps if gap['end_s'] - gap['start_s'] >= 0.1 - 1e-8],
                           'clauses': [by_ordinal.get(end, {'after_char': end, 'start_s': None, 'end_s': None})
                                       for end in CLAUSE_ENDS],
                           'prompt_row_gaps': gaps, 'checked_utterance_label_counts': dict(Counter(
                               'speech' if HAN.search(label) else label for _, _, label in utterances)),
                           'visual_start_s': words[0][0], 'visual_end_s': words[aligned_ends.index(46)][1]})
    return {'provenance': 'Published ManDi MFA word tier, paired with separate text-only clause annotation',
            'minimum_pause_s': 0.1, 'text_source': 'Zhao dissertation appendix d, p. 170',
            'clear_clause_ends': CLAUSE_ENDS, 'temporal_frame_ends': TEMPORAL_FRAME_ENDS,
            'ambiguous_ends': AMBIGUOUS_ENDS, 'recordings': recordings, 'excluded': excluded}


def apply_visual(references, annotations):
    reviewed = []
    for row in references['recordings']:
        key = row['id']
        annotation = annotations[key]
        start, end = row['visual_start_s'], row['visual_end_s']
        pauses = [{'start_s': a, 'end_s': b} for a, b in annotation['pauses']]
        masks = [{'start_s': a, 'end_s': b} for a, b in annotation['uncertain']]
        if any(not start < event['start_s'] < event['end_s'] < end for event in pauses + masks):
            raise ValueError(f'Visual labels fall outside the plotted interior window for {key}')
        reviewed.append({**row, 'score_start_s': start, 'score_end_s': end, 'pauses': pauses,
                         'excluded_intervals': masks, 'clauses': [], 'visual_notes': annotation['notes']})
    if set(annotations) != {row['id'] for row in reviewed}:
        raise ValueError('Every plotted recording must have exactly one visual review')
    return {**references, 'provenance': 'Detector-blind visual pause annotation from original PCM. '
            'Scored only in the first six prompt rows. Separate clause estimates use the full MFA reference.',
            'recordings': reviewed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--visual-annotations', type=Path)
    args = parser.parse_args()
    root = args.corpus
    result = build(root, json.loads((root / 'mandi_manifest.json').read_text(encoding='utf-8')))
    if args.visual_annotations:
        result = apply_visual(result, json.loads(args.visual_annotations.read_text(encoding='utf-8')))
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({row['id']: (len(row['pauses']), row['checked_utterance_label_counts'])
                      for row in result['recordings']}))
    print(json.dumps(result['excluded']))


if __name__ == '__main__':
    main()
