"""Compare frozen grammar models before and after expanding written 音律美 training."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unicodedata import normalize

from . import quantitative_editorial_grammar as grammar


PACKETS = (('a', 'train-a'), ('d', 'train-b'), ('k', 'holdout'))
FITS = ('original', 'expanded')
FEATURES = grammar.GRAMMAR
LAFAYETTE_AUTHOR = 'Author of the project’s 拉法叶赋'


def digest(data):
    return sha256(data).hexdigest()


def line_key(row):
    return row['work_id'], row['id']


def index_rows(rows, name, key=line_key):
    result = {key(row): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f'Duplicate ID in {name}')
    return result


def check_source_rows(rows, cards, role):
    by_work = defaultdict(list)
    for row in rows:
        by_work[row['work_id']].append(row)
    if set(by_work) != set(cards):
        raise ValueError(f'Source cards disagree with works in {role}')
    for work_id, items in by_work.items():
        card = cards[work_id]
        if 'split' in card and card['split'] != role:
            raise ValueError(f'Incorrect role for {work_id}')
        if any(not isinstance(card.get(key), str) or not card[key].strip()
               for key in ('author', 'title', 'source_url')):
            raise ValueError(f'Incomplete source details for {work_id}')
        if type(card['revision_id']) is not int or not card['source_url'].endswith(str(card['revision_id'])):
            raise ValueError(f'Invalid revision link for {work_id}')
        if any(row[key] != card[key] for row in items for key in ('author', 'title', 'source_url', 'revision_id')):
            raise ValueError(f'Witness disagrees with the source metadata for {work_id}')
        if any(row['order'] != i for i, row in enumerate(items, 1)):
            raise ValueError(f'Out-of-order witness for {work_id}')
        paragraphs = [''.join(r['text'] for r in group) for _, group in groupby(items, key=lambda r: r['section'])]
        if len(items) != card.get('unit_count', card.get('scoring_units')):
            raise ValueError(f'Wrong unit count for {work_id}')
        if len(paragraphs) != card.get('section_count', card.get('source_paragraphs')):
            raise ValueError(f'Wrong paragraph count for {work_id}')
        if 'text_sha256' in card and digest('\n\n'.join(paragraphs).encode()) != card['text_sha256']:
            raise ValueError(f'Text does not reconstruct the frozen edition for {work_id}')


def unmask(witness, blind, ratings, keys, role):
    actual = index_rows(witness, role)
    masked = index_rows(blind, f'blind {role}')
    labels = index_rows(ratings, f'labels {role}')
    if set(masked) != set(labels) or any(set(row) != {'work_id', 'id', 'section', 'text'} for row in blind):
        raise ValueError(f'Blinded inputs and labels disagree in {role}')
    used_keys = []
    recovered = []
    for row in blind:
        k = line_key(row)
        source_key = keys[k]
        orig = actual[source_key]
        if any(row[field] != orig[field] for field in ('text', 'section')):
            raise ValueError(f'Blinded text or section mismatch for {k}')
        if any(field in orig for field in ('score', 'editorial_score')):
            raise ValueError(f'Label visible in witness at {source_key}')
        label = labels[k]
        score = label['score']
        if ('□' in row['text'] and score is not None) or ('□' not in row['text'] and not grammar.context.valid_score(score)):
            raise ValueError(f'Invalid frozen score at {k}')
        if not label['quote'] or label['quote'] not in row['text'] or not label['reason'].strip():
            raise ValueError(f'Invalid evidence span at {k}')
        recovered.append({**label, 'work_id': source_key[0], 'id': source_key[1]})
        used_keys.append(source_key)
    if used_keys != list(actual):
        raise ValueError(f'Blind packet does not reconstruct the ordered witness for {role}')
    return recovered


def normalized_text(row):
    return ''.join(filter(grammar.context.base.han, normalize('NFKC', row['text'])))


def build_additions(inputs_by_role, labels_by_role, protected):
    """Remove reused lines from fitting while maintaining hard gaps in neighboring context."""
    reserved = defaultdict(list)
    for split, rows in protected.items():
        for row in rows:
            reserved[normalized_text(row)].append({'split': split, 'work_id': row['work_id'], 'id': row['id']})
    training, exclusions = [], []
    for role in ('train-a', 'train-b'):
        previous_section, retained_before, gap_number, gap_pending = None, False, 0, False
        for row, label in zip(inputs_by_role[role], labels_by_role[role]):
            section = (row['work_id'], row['section'])
            if section != previous_section:
                previous_section, retained_before, gap_number, gap_pending = section, False, 0, False
            duplicates = reserved.get(normalized_text(row), [])
            if duplicates or label['score'] is None:
                reason = 'Han-normalized exact duplicate' if duplicates else 'incomplete witness'
                exclusions.append({'work_id': row['work_id'], 'id': row['id'], 'section': row['section'],
                                   'text': row['text'], 'reason': reason, 'matches': duplicates})
                gap_pending = retained_before
                continue
            if gap_pending:
                gap_number += 1
                gap_pending = False
            output = {**row, 'score': label['score'], 'quote': label['quote'], 'reason': label['reason']}
            if gap_number:
                output['source_section'] = row['section']
                output['section'] = f'{row["section"]}#gap{gap_number}'
            training.append(output)
            retained_before = True
    return training, exclusions


def distinct_work_authors(batches):
    seen = {key: set() for key in ('work_id', 'title', 'author', 'text')}
    for role, rows in batches.items():
        here = defaultdict(set)
        for row in rows:
            original = row['work_id'] == 'lafayette'
            here['work_id'].add(row['work_id'])
            here['title'].add(row.get('title', '拉法叶赋' if original else ''))
            here['author'].add(row.get('author', LAFAYETTE_AUTHOR if original else ''))
            here['text'].add(normalized_text(row))
        if any('' in values for values in here.values()):
            raise ValueError(f'Empty author, title, work, or text in {role}')
        for key, values in here.items():
            if seen[key] & values:
                raise ValueError(f'{role} overlaps another split by {key}: {sorted(seen[key] & values)[:4]}')
            seen[key].update(values)


def support(rows, *, test_rows=False):
    if test_rows:
        described = [(r, r['frame_features']) for r in rows if r['editorial_score'] is not None]
    else:
        # These feature indicators use only punctuation, characters, and adjacent line order.
        lines = grammar.context.describe(rows, {})
        frames = grammar.frame_features(lines)
        described = [(line.row, frames[line.key][0]) for line in lines if line.complete]
    by_work = {}
    for row, frame in described:
        work = by_work.setdefault(row['work_id'], {
            'title': row.get('title', '拉法叶赋'), 'units': 0, 'score_counts': Counter(),
            'nonzero_lines': Counter({name: 0 for name in FEATURES}),
        })
        work['units'] += 1
        work['score_counts'][row['editorial_score' if test_rows else 'score']] += 1
        work['nonzero_lines'].update({name: int(bool(frame[name])) for name in FEATURES})
    return {
        'units': len(described), 'works': len(by_work), 'by_work': by_work,
        'score_counts': sum((w['score_counts'] for w in by_work.values()), Counter()),
        'nonzero_lines': {name: sum(w['nonzero_lines'][name] for w in by_work.values()) for name in FEATURES},
        'positive_works': {name: sum(w['nonzero_lines'][name] > 0 for w in by_work.values()) for name in FEATURES},
    }


def save_json(path, obj):
    with path.open('x', encoding='utf-8') as output:
        json.dump(obj, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write('\n')


def render_summary(summary):
    text = ['Written 音律美 training expansion', '', f'Frozen shuffles per control: {summary["shuffles"]}.',
            'Scores are GPT editorial judgments on visible text. Unit-level absolute errors use unrounded predictions.',
            'The primary statistic gives each work equal weight. Fresh Tang works are primary, and the four previously examined Song works are secondary.', '']
    for row in summary['training_exclusions']:
        text.append(f'Training exclusion {row["work_id"]}/{row["id"]} {row["text"]} — {row["reason"]}.')
    for fit, s in summary['training'].items():
        text.append(f'{fit} training | {s["units"]} units | {s["works"]} works | '
                    f'whole frames on {s["nonzero_lines"]["neighbor_whole_frame"]} units in '
                    f'{s["positive_works"]["neighbor_whole_frame"]} works | three-line frames on '
                    f'{s["nonzero_lines"]["three_line_frame"]} units in {s["positive_works"]["three_line_frame"]} works')
    for split,s in summary['tests'].items():
        text += ['', f'{split} | {s["support"]["units"]} units | {s["support"]["works"]} works',
                 'Fit / model                            equal-work MAE   pooled MAE']
        for fit, metric in s['fits'].items():
            for model in ('always_six', 'training_median', 'conditional_median', 'context', 'context_grammar'):
                m=metric['mae'][model]
                text.append(f'{fit + " / " + model:38s} {m["work_macro"]:10.4f}   {m["pooled"]:10.4f}')
        text.append('Work                              units   always 6   original grammar   expanded grammar')
        for work, item in s['support']['by_work'].items():
            old, new = (s['fits'][fit]['mae'] for fit in FITS)
            text.append(f'{work:31s} {item["units"]:4d} {new["always_six"][work]:10.4f} '
                        f'{old["context_grammar"][work]:18.4f} {new["context_grammar"][work]:18.4f}')
        text.append('Expanded grammar model, equal-work MAE under controls')
        for mode, vals in s['fits']['expanded']['controls'].items():
            stat = vals['mae']['work_macro']
            text.append(f'{mode}: observed {stat["observed"]:.4f}, median shuffled {stat["median_shuffled"]:.4f}, '
                        f'{stat["count_at_least_as_good"]}/{stat["draws"]} shuffled outcomes at least as good.')
    return '\n'.join(text)+'\n'


def run(root, reference_path, previous, inputs, output, shuffles):
    if shuffles < 1:
        raise ValueError('Specify at least one shuffle')
    root = root.resolve(strict=True)
    for path in (reference_path, previous, inputs, output):
        if not path.resolve().is_relative_to(root):
            raise ValueError('Keep data and outputs inside the Gilbreth project')
    if output.exists():
        raise FileExistsError(output)
    hashes = {}

    def load(path):
        if not path.resolve().is_relative_to(root):
            raise ValueError(f'Input resolves outside project: {path}')
        data = path.read_bytes()
        hashes[str(path.relative_to(root))] = digest(data)
        return json.loads(data)

    reference = load(reference_path)
    if len(reference) != 209 or {row['work_id'] for row in reference} != {'lafayette'}:
        raise ValueError('Expected the 209-unit original Lafayette reference')
    previous_rows = load(previous / 'fresh-witness.json')
    previous_labels = load(previous / 'fresh-labels.json')
    if (previous/'sources.json').is_file():
        cards = load(previous/'sources.json')['sources']
        check_source_rows(previous_rows, index_rows(cards, 'previous sources', key=lambda r:r['work_id']), 'previous')
    if len({r['work_id'] for r in previous_rows}) != 4:
        raise ValueError('Expected the previously tested four works')

    sources = load(inputs/'train-a-sources.json')['sources'] + load(inputs/'b-sources.json')['sources']
    cards = index_rows(sources, 'new sources', key=lambda r:r['work_id'])
    if {card['split'] for card in sources} != {role for _, role in PACKETS}:
        raise ValueError('Unexpected source-card role')
    key_rows = load(inputs/'a-mask-key.json') + load(inputs/'b-mask-key.json')
    keys = {(r['masked_work_id'], r['masked_id']): line_key(r) for r in key_rows}
    if len(keys) != len(key_rows) or len(set(keys.values())) != len(keys):
        raise ValueError('Mask key must be one-to-one')
    seen_masks = set()
    inputs_by_role, labels_by_role = {}, {}
    for suffix, role in PACKETS:
        witness = load(inputs/f'{role}.json')
        blind = load(inputs/f'blind-{suffix}.json')
        ratings = load(inputs/f'labels-{suffix}.json')
        check_source_rows(witness, {w:c for w,c in cards.items() if c['split'] == role}, role)
        labels_by_role[role] = unmask(witness, blind, ratings, keys, role)
        inputs_by_role[role] = witness
        seen_masks.update(map(line_key, blind))
    if seen_masks != set(keys):
        raise ValueError('Mask key contains rows outside the frozen packets')
    train_works = [c for c in sources if c['split'].startswith('train-')]
    if len(train_works) != 6 or len({c['author'] for c in train_works}) != 6:
        raise ValueError('Expected six independently authored training works')
    held = [c for c in sources if c['split'] == 'holdout']
    if len(held) != 2 or len({c['author'] for c in held}) != 2:
        raise ValueError('Expected two independently authored primary holdouts')
    protected = {'original': reference, 'fresh': inputs_by_role['holdout'], 'previous': previous_rows}
    additions, exclusions = build_additions(inputs_by_role, labels_by_role, protected)
    distinct_work_authors({**protected, 'additions': additions})
    # Dropping an entire work would silently change the declared training design.
    if {row['work_id'] for row in additions} != {card['work_id'] for card in train_works}:
        raise ValueError('No usable lines remain for one or more declared training works')
    expanded = reference + additions
    lexicons, lex_hashes = grammar.context.base.lexicon_data(root)
    summary = {'target': 'written editorial 音律美', 'primary': 'fresh equal-work raw MAE', 'shuffles':shuffles,
               'seed': grammar.SEED, 'ridge_penalty':grammar.context.base.RIDGE, 'input_sha256': hashes,
               'lexicon_sha256': lex_hashes, 'training_exclusions': exclusions, 'training':{}, 'tests':{}}
    if (inputs/'protocol.txt').is_file():
        hashes[str((inputs/'protocol.txt').relative_to(root))] = digest((inputs/'protocol.txt').read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.grammar-expansion-', dir=output.parent) as temp:
        stage = Path(temp)/'results'
        stage.mkdir()
        save_json(stage/'enriched-reference.json', expanded)
        summary['enriched_reference_sha256'] = digest((stage/'enriched-reference.json').read_bytes())
        fit_sets = {'original':reference, 'expanded':expanded}
        summary['training'] = {fit:support(rows) for fit,rows in fit_sets.items()}
        tests = {'fresh':(inputs_by_role['holdout'], [r for r in labels_by_role['holdout'] if r['score'] is not None]),
                 'previous':(previous_rows, previous_labels)}
        for split,(witness,labels) in tests.items():
            results = {}
            for fit, training in fit_sets.items():
                result = grammar.evaluate(training, witness, labels, lexicons, repeats=shuffles)
                results[fit] = {'mae':result['mae'], 'controls':result['controls']}
                save_json(stage/f'{split}-{fit}-results.json', result)
            changes = {model:{key:v - results['original']['mae'][model][key] for key,v in errors.items()}
                       for model,errors in results['expanded']['mae'].items()}
            summary['tests'][split] = {'support':support(result['rows'], test_rows=True),
                                       'fits':results, 'expanded_minus_original_mae':changes}
        save_json(stage/'summary.json', summary)
        (stage/'summary.txt').write_text(render_summary(summary), encoding='utf-8')
        stage.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root','reference','previous','inputs','output'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--shuffles', type=int, default=199)
    args = parser.parse_args()
    try:
        run(args.root.resolve(), args.reference.resolve(), args.previous.resolve(), args.inputs.resolve(),
            args.output.resolve(), args.shuffles)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(args.output/'summary.txt')


if __name__ == '__main__':
    main()
