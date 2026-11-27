"""Mask one independent ending and predict its exact 廣韻 rhyme group in two-alternative trials."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
from random import Random
from statistics import fmean

from data.phonology.annotate import han
from src.quantitative_editorial_context import rhyme_agreement
from src.quantitative_editorial_transfer import lexicon_data
from src.stage7_text import annotate_text
from src.text_metrics import reading_values
from src.yu_review_baseline import save_sealed


SEED = 20261126
SHUFFLES = 200
BOOTSTRAPS = 10000
MIN_TEST_WORKS = 8
METHODS = ('local', 'run', 'frequency', 'tone')
CREDIT = {'win': 1., 'loss': 0., 'tie': .5, 'abstain': .5}
PROTOCOL = {
    'version': 1, 'seed': SEED, 'shuffles': SHUFFLES, 'work_bootstraps': BOOTSTRAPS,
    'minimum_independent_test_fu': MIN_TEST_WORKS,
    'local': 'Existing mean resolved exact-group agreement at offsets -2,-1,+1,+2 within section.',
    'run': 'For strides 1 and 2, check offset pairs (-2,-1), (-1,+1), (+1,+2) times stride. '
           'Each pair of identical unambiguous groups votes once. Use only a unique plurality; '
           'abstain on insufficient support, conflicting plurality or a group outside both choices.',
    'foil': 'Draw one different group of the same tone, weighted by frequencies at eligible '
            'unambiguous development endings. Sort groups and seed separately for each position.',
    'frequency': 'Choose the more frequent candidate among unambiguous unmasked rhyme groups in the work.',
    'shuffle': 'Shuffle whole rows within contiguous sections, preserving trials, labels and decoys.',
    'tolerance': '95th percentile of absolute differences between paired independent shuffled '
                 'development-fu advantages of run over work frequency.',
    'decision': 'At least eight eligible test fu works and eight distinct test fu authors, lower '
                'paired work-bootstrap 95% bound for run minus local above zero, positive intact '
                'run advantage over frequency and its drop on shuffling greater than development tolerance.',
}


@dataclass(frozen=True)
class Ending:
    id: str
    section: str
    character: str
    groups: frozenset
    tone: str | None
    target: bool
    rubric_literal_final: bool = False

    @property
    def group(self):
        return next(iter(self.groups)) if len(self.groups) == 1 else None


@dataclass
class Work:
    id: str
    author: str
    split: str
    genre: str
    rows: list


def seeded(*parts):
    key = json.dumps([SEED, *parts], ensure_ascii=False, separators=(',', ':')).encode()
    return Random(int.from_bytes(sha256(key).digest(), 'big'))


def load_works(rows, lex):
    works, authors, lookups = {}, {}, {}
    for work_id, group in groupby(rows, key=lambda x: x['work_id']):
        group = list(group)
        if not work_id or work_id in works or len({r['id'] for r in group}) != len(group):
            raise ValueError(f'{work_id}: work rows must be contiguous with unique IDs')
        identity = {(r['author'], r['split'], r['genre']) for r in group}
        if len(identity) != 1:
            raise ValueError(f'{work_id}: changing author, split or genre')
        author, split, genre = identity.pop()
        if not author or split not in {'development', 'test'} or genre not in {'fu', 'prose'}:
            raise ValueError(f'{work_id}: unknown author, split or genre')
        if authors.setdefault(author, split) != split:
            raise ValueError(f'{author} crosses split')
        sections = [s for s, _ in groupby(group, key=lambda r: r['section'])]
        if len(set(sections)) != len(sections) or not all(sections):
            raise ValueError(f'{work_id}: require named contiguous sections')
        ends = []
        for row in group:
            text = row['text']
            char = next((c for c in reversed(text) if han(c)), '')
            groups, tone = frozenset(), None
            if char and not any(marker in text for marker in ('□', '�')):
                if char not in lookups:
                    slot = annotate_text(char, **lex)['slots'][0]
                    tones = reading_values(slot, 'guangyun', 'tone')
                    lookups[char] = (reading_values(slot, 'guangyun', 'rhyme'),
                                     next(iter(tones)) if len(tones) == 1 else None)
                groups, tone = lookups[char]
            ends.append(Ending(row['id'], row['section'], char, groups, tone, row.get('target', True),
                               row.get('rubric_literal_final', False)))
        works[work_id] = Work(work_id, author, split, genre, ends)
    return works


def make_trials(works):
    pool = defaultdict(Counter)
    for work in works.values():
        if work.split == 'development':
            for row in work.rows:
                if row.target and row.tone and row.group:
                    pool[row.tone][row.group] += 1
    trials = {}
    for work in works.values():
        by_id = {}
        for row in work.rows:
            if not (row.target and row.tone and row.group):
                continue
            alternatives = sorted(set(pool[row.tone]) - {row.group})
            if alternatives:
                weights = [pool[row.tone][g] for g in alternatives]
                foil = seeded('foil', work.id, row.id).choices(alternatives, weights=weights)[0]
                by_id[row.id] = {'group': row.group, 'foil': foil, 'tone': row.tone}
        trials[work.id] = by_id
    return trials


def outcome(values, choices, answer):
    left, right = (values.get(group) for group in choices)
    if left is None or right is None:
        return 'abstain'
    if left == right:
        return 'tie'
    return 'win' if choices[int(right > left)] == answer else 'loss'


def run_group(near):
    votes = Counter()
    for stride in (1, 2):
        for a, b in ((-2, -1), (-1, 1), (1, 2)):
            left, right = near.get(a * stride), near.get(b * stride)
            if left and right and left.group is not None and left.group == right.group:
                votes[left.group] += 1
    ranked = votes.most_common(2)
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        return ranked[0][0]
    return None


def local_agreement(near, candidate):
    values = [rhyme_agreement({candidate}, row.groups) for d, row in near.items() if abs(d) <= 2]
    usable = [value for value in values if value is not None]
    return fmean(usable) if usable else None


def predict(near, choices, frequencies):
    # Inputs deliberately contain neither the hidden character nor its correct candidate index.
    local = {c: local_agreement(near, c) for c in choices}
    pattern = run_group(near)
    return {'local': local, 'run': {c: int(c == pattern) for c in choices} if pattern in choices else {},
            'frequency': {c: frequencies.get(c, 0) for c in choices},
            'tone': dict.fromkeys(choices, 0)}, pattern


def evaluate_work(work, trials, shuffle=None, details=False):
    counts = {method: Counter() for method in METHODS}
    freq = Counter(row.group for row in work.rows if row.group)
    items, supported = [], 0
    for section, grouped in groupby(work.rows, key=lambda row: row.section):
        section_rows = list(grouped)
        if shuffle is not None:
            seeded('shuffle', shuffle, work.id, section).shuffle(section_rows)
        for i, row in enumerate(section_rows):
            if row.id not in trials:
                continue
            trial = trials[row.id]
            choices = sorted((trial['group'], trial['foil']))
            near = {j - i: section_rows[j] for j in range(max(0, i - 4), min(len(section_rows), i + 5)) if j != i}
            # Remove the held-out occurrence even if it is the only instance in the work.
            masked_freq = {c: freq[c] - int(c == row.group) for c in choices}
            scores, pattern = predict(near, choices, masked_freq)
            results = {m: outcome(scores[m], choices, trial['group']) for m in METHODS}
            for method, status in results.items():
                counts[method][status] += 1
            supported += int(pattern is not None)
            if details:
                items.append({'id': row.id, 'section': section, 'char': row.character, **trial,
                              'run_group': pattern, 'scores': scores, 'outcomes': results,
                              'rubric_literal_final': row.rubric_literal_final,
                              'repeated_end_char_in_window': any(row.character == other.character for other in near.values()),
                              'neighbors': {str(d): r.id for d, r in near.items()}})
    return counts, supported, items


def rates(counts):
    n = sum(counts.values())
    attempted = n - counts['abstain']
    credit = sum(CREDIT[key] * value for key, value in counts.items())
    return {'counts': dict(counts), 'accuracy': credit / n if n else None,
            'coverage': attempted / n if n else None,
            'attempted_accuracy': (credit - .5 * counts['abstain']) / attempted if attempted else None,
            'decisive_share': (counts['win'] + counts['loss']) / n if n else None}


def percentile(values, probability):
    vals = sorted(values)
    at = (len(vals) - 1) * probability
    left = int(at)
    return vals[left] + (vals[min(left + 1, len(vals) - 1)] - vals[left]) * (at - left)


def mean_or_none(values):
    vals = [v for v in values if v is not None]
    return fmean(vals) if vals else None


def distribution_summary(results):
    out = {}
    for method in METHODS:
        values = [r['intact'][method] for r in results]
        out[method] = {key: mean_or_none(v[key] for v in values)
                       for key in ('accuracy', 'coverage', 'attempted_accuracy', 'decisive_share')}
        counts = Counter()
        for row in values:
            counts.update(row['counts'])
        out[method]['counts'] = dict(counts)
        out[method]['works_with_attempts'] = sum(v['attempted_accuracy'] is not None for v in values)
    return out


def analyze_subset(works, trials):
    records, items = [], {}
    for work in works:
        trials_here = trials[work.id]
        counts, supported, detail = evaluate_work(work, trials_here, details=True)
        items[work.id] = detail
        acc, shuffled_coverage = defaultdict(list), defaultdict(list)
        for rep in range(SHUFFLES):
            draw, _, _ = evaluate_work(work, trials_here, shuffle=rep)
            for method in METHODS:
                stats = rates(draw[method])
                acc[method].append(stats['accuracy'])
                shuffled_coverage[method].append(stats['coverage'])
        records.append({'work_id': work.id, 'author': work.author, 'split': work.split, 'genre': work.genre,
                        'rows': len(work.rows), 'available_targets': sum(r.target for r in work.rows),
                        'unambiguous_targets': sum(1 for r in work.rows if r.target and r.group and r.tone),
                        'trials': len(trials_here), 'run_supported': supported,
                        'intact': {m: rates(counts[m]) for m in METHODS},
                        'shuffled_accuracy': dict(acc), 'shuffled_coverage': {m: mean_or_none(v) for m, v in shuffled_coverage.items()}})
    eligible = [r for r in records if r['trials']]
    result = {'works': len(records), 'eligible_works': len(eligible), 'authors': len({r['author'] for r in eligible}),
              'rows': sum(r['rows'] for r in records), 'trials': sum(r['trials'] for r in records),
              'intact': distribution_summary(eligible)}
    if not eligible:
        return result, records, items, []
    delta = [r['intact']['run']['accuracy'] - r['intact']['local']['accuracy'] for r in eligible]
    rng = seeded('bootstrap', eligible[0]['split'], eligible[0]['genre'])
    boot = [fmean(rng.choices(delta, k=len(delta))) for _ in range(BOOTSTRAPS)]
    permuted = {m: [fmean(r['shuffled_accuracy'][m][rep] for r in eligible) for rep in range(SHUFFLES)] for m in METHODS}
    null = [a - b for a, b in zip(permuted['run'], permuted['frequency'])]
    result.update({'run_minus_local': fmean(delta), 'bootstrap_95': [percentile(boot, q) for q in (.025, .975)],
                   'run_minus_frequency': result['intact']['run']['accuracy'] - result['intact']['frequency']['accuracy'],
                   'shuffled': {m: {'accuracy': fmean(permuted[m]), 'coverage': fmean(r['shuffled_coverage'][m] for r in eligible)} for m in METHODS},
                   'run_supported_share': fmean(r['run_supported'] / r['trials'] for r in eligible),
                   'shuffled_run_minus_frequency': fmean(null)})
    for label, keep in (('rubric_literal', lambda item: item['rubric_literal_final']),
                        ('no_local_glyph_repeat', lambda item: not item['repeated_end_char_in_window'])):
        selected = []
        for work_items in items.values():
            subset = [item for item in work_items if keep(item)]
            if subset:
                selected.append({'intact': {
                    m: rates(Counter(item['outcomes'][m] for item in subset)) for m in METHODS}})
        result[label] = {'works': len(selected), 'metrics': distribution_summary(selected)}
    return result, records, items, null


def run(root, input_file, output):
    output.mkdir(parents=True, exist_ok=True)
    raw = input_file.read_bytes()
    lex, hashes = lexicon_data(root)
    works = load_works(json.loads(raw), lex)
    trials = make_trials(works)
    save_sealed(output / 'seal.json', {'protocol': PROTOCOL, 'input_sha256': sha256(raw).hexdigest(),
                'lexicon_sha256': hashes, 'analysis_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'trials': trials})
    summary, work_results, all_items = {}, [], {}
    for split in ('development', 'test'):
        summary[split] = {}
        for genre in ('fu', 'prose'):
            subset = [w for w in works.values() if w.split == split and w.genre == genre]
            result, work_rows, items, null = analyze_subset(subset, trials)
            summary[split][genre] = result
            work_results.extend(work_rows)
            all_items.update(items)
            if (split, genre) == ('development', 'fu'):
                changes = [abs(a - b) for a, b in zip(null[::2], null[1::2])]
                tolerance = percentile(changes, .95) if changes else None
                save_sealed(output / 'development_gate.json', {'shuffle_tolerance': tolerance,
                            'eligible_development_fu': result['eligible_works'], 'development_null': null})
    held = summary['test']['fu']
    gate = {'minimum_works_and_authors': min(held['eligible_works'], held['authors']) >= MIN_TEST_WORKS,
            'positive_lower_bound': bool(held.get('bootstrap_95') and held['bootstrap_95'][0] > 0),
            'positive_advantage_over_frequency': held.get('run_minus_frequency', 0.) > 0,
            'shuffle_drop_exceeds_development_tolerance': bool(tolerance is not None and held['trials'] and
                held['run_minus_frequency'] - held['shuffled_run_minus_frequency'] > tolerance)}
    summary['decision'] = {'promote': all(gate.values()), 'gates': gate, 'development_shuffle_tolerance': tolerance}
    save_sealed(output / 'work_results.json', work_results)
    save_sealed(output / 'items.json', all_items)
    save_sealed(output / 'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('rows', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.rows, args.output_dir)['decision'], ensure_ascii=False))
