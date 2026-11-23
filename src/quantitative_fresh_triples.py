"""Apply archived written-prosody fits to a source-verified, work-held-out challenge."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
from random import Random
from statistics import fmean, median
from tempfile import TemporaryDirectory

from . import quantitative_editorial_grammar as grammar
from .quantitative_grammar_expansion import normalized_text


MODEL_SHA = '3457d6f5a87de5438f2ae5befe224b49eed057ce2336ac1780d412e89f5d683b'
TRAIN_SHA = '91b9bd7cee712eab0af519c8ed50497cca4bd298340bf1dc67bf1c649b365930'
MODES = ('always_six', 'context', 'context_grammar')


def key(row):
    return row['work_id'], row['id']


def confirmed_keys(triples, lines, edges):
    """Both edges of every reviewed window must join its actual consecutive units."""
    by_key = {line.key: i for i, line in enumerate(lines)}
    whole = {(e['work_id'], e['left_id'], e['right_id']) for e in edges if e['whole_frame']}
    selected = set()
    for t in triples:
        work, ids = t['work_id'], t['ids']
        if len(ids) != 3 or len(set(ids)) != 3 or not t['explanation'].strip():
            raise ValueError('Each reviewed window needs three distinct units and a grammatical explanation')
        keys = [(work, i) for i in ids]
        positions = [by_key[k] for k in keys]
        if positions != list(range(positions[0], positions[0] + 3)) or any(
                (work, left, right) not in whole for left, right in zip(ids, ids[1:])):
            raise ValueError(f'Window lacks two consecutive whole-frame edges: {keys}')
        selected.update(keys)
    return selected


def forecast(models, x):
    return {'always_six': [6.] * len(x),
            **{m: grammar.context.predict(models[m], x) for m in MODES[1:]}}


def measure(groups, predictions, target):
    by_work = {w: {m: fmean(abs(predictions[m][i] - target[i]) for i in indices) for m in MODES}
               for w, indices in groups.items()}
    indices = [i for indices in groups.values() for i in indices]
    if not indices:
        raise ValueError('No eligible units in endpoint')
    return {'n': len(indices), 'by_work': by_work, 'units_by_work': {w:len(v) for w,v in groups.items()},
            'scores': dict(sorted(Counter(target[i] for i in indices).items())),
            'equal_work': {m:fmean(r[m] for r in by_work.values()) for m in MODES},
            'pooled': {m:fmean(abs(predictions[m][i]-target[i]) for i in indices) for m in MODES}}


def shuffled(lines, original, models, groups, target, observed):
    draws = {}
    for mode in grammar.CONTROLS:
        rng = Random(grammar.SEED)
        sample = {k: [] for k in groups}
        for _ in range(199):
            if mode == 'section_order':
                order = grammar.section_shuffle(lines, rng)
                x, _ = grammar.matrix_rows(order, lines, grammar.context.in_context(order))
            else:
                x, _ = grammar.matrix_rows(lines, lines, original, positions_rng=rng)
            pred = forecast(models, x)
            for name, works in groups.items():
                score = measure(works, pred, target)['equal_work']
                sample[name].append((score['context_grammar'], score['context']-score['context_grammar']))
        draws[mode] = {}
        for name, values in sample.items():
            actual = observed[name]['equal_work']
            err = actual['context_grammar']
            gain = actual['context'] - err
            draws[mode][name] = {'draws':len(values), 'observed_mae':err, 'observed_gain':gain,
                                 'median_mae':median(e for e,g in values), 'median_gain':median(g for e,g in values),
                                 'mae_as_good':sum(e <= err+1e-12 for e,g in values),
                                 'gain_as_large':sum(g >= gain-1e-12 for e,g in values)}
    return draws


def run(root, inputs, output, screen=False):
    if output.exists():
        raise FileExistsError(output)
    signatures = {}

    def load(path, expected=None):
        path = path.resolve()
        raw = path.read_bytes()
        digest = sha256(raw).hexdigest()
        signatures[str(path.relative_to(root))] = digest
        if expected and digest != expected:
            raise ValueError(f'Archived checksum mismatch: {path.name}')
        return json.loads(raw)

    archive = root/'results/grammatical-training-expansion-20261122'
    pretrained = load(archive/'results/fresh-expanded-results.json', MODEL_SHA)['models']
    training = load(archive/'results/enriched-reference.json', TRAIN_SHA)
    lexicons, lex_hash = grammar.context.base.lexicon_data(root)
    if lex_hash != load(archive/'results/summary.json')['lexicon_sha256']:
        raise ValueError('Historical dictionary hashes differ from the expanded fit')
    for name in MODES[1:]:
        if list(grammar.MODEL_COLS[name]) != pretrained[name]['names']:
            raise ValueError('Frozen feature order differs from the archived model')
    prior = list(training)
    for path in (archive/'inputs/holdout.json', archive/'inputs/train-b.json',
                 root/'results/grammatical-patterns-20261122/inputs/fresh-witness.json',
                 root/'results/editorial-context-20261122/inputs/fresh-witness.json',
                 root/'results/dong-shaorong-holdout-20261122/witness.json'):
        prior.extend(load(path))
    witness = load(inputs/'witness.json')
    cards = load(inputs/'works.json')
    triples = load(inputs/'triples.json')
    if any('score' in r or 'editorial_score' in r for r in witness):
        raise ValueError('Use a label-free witness')
    works = {r['work_id']: r for r in cards}
    if (len(works) != len(cards) or set(works) != {r['work_id'] for r in witness}
            or len({r['author'] for r in cards}) != len(cards)):
        raise ValueError('A distinct author and a source card are required for every work')
    for field in ('work_id','author','title'):
        if {r[field] for r in cards} & {r.get(field) for r in prior}:
            raise ValueError(f'Prior material overlaps the new set by {field}')
    if any(any(r[k] != works[r['work_id']][k] for k in ('author','title')) for r in witness):
        raise ValueError('Incorrect source attribution')
    blocks = [k for k,_ in groupby(witness, key=lambda r:(r['work_id'],r['section']))]
    if len(set(blocks)) != len(blocks):
        raise ValueError('Broken contiguous source section')
    protected = {normalized_text(r) for r in prior}
    lines = grammar.context.describe(witness, lexicons)
    original = grammar.context.in_context(lines)
    edges = []
    x, frames = grammar.matrix_rows(lines, lines, original, edge_details=edges)
    named = confirmed_keys(triples, lines, edges)
    excluded = {}
    groups = {k:defaultdict(list) for k in ('confirmed_triples','strict_triples','strict_parallel','parallel','prose','all')}
    for i, ln in enumerate(lines):
        reason = ('historically reused exact line' if normalized_text(ln.row) in protected else
                  'incomplete unit' if not ln.complete else None)
        if reason:
            excluded[ln.key] = reason
            continue
        work = ln.key[0]
        role = works[work]['role']
        groups[role][work].append(i)
        groups['all'][work].append(i)
        if works[work]['form'] == 'parallel_prose':
            groups['strict_parallel'][work].append(i)
            if ln.key in named:
                groups['strict_triples'][work].append(i)
        if ln.key in named:
            if role != 'parallel':
                raise ValueError('Primary window must belong to a parallel work')
            groups['confirmed_triples'][work].append(i)
    if (len(groups['prose']) < 2 or len(groups['parallel']) < 2
            or set(groups['confirmed_triples']) != set(groups['parallel'])):
        raise ValueError('Need independent prose comparators and verified runs in each parallel work')
    for label in ('parallel', 'prose'):
        if set(groups[label]) != {w for w,c in works.items() if c['role']==label}:
            raise ValueError('Every reserved work must have scorable rows')
    eligibility = {'windows':triples, 'excluded':[{'work_id':w,'id':i,'reason':why} for (w,i),why in excluded.items()],
                   'groups':{name:{w:[lines[i].row['id'] for i in indices] for w,indices in works_by_group.items()}
                             for name,works_by_group in groups.items()},
                   'witness_sha256':signatures[str((inputs/'witness.json').relative_to(root))]}
    if screen:
        with output.open('x', encoding='utf-8') as f:
            json.dump(eligibility,f,ensure_ascii=False,indent=2)
            f.write('\n')
        return
    if eligibility != load(inputs/'eligibility.json'):
        raise ValueError('Test membership has changed since the outcome-blind screen')
    predictions = forecast(pretrained, x)
    packet = load(inputs/'reader-packet.json')
    mask_key = load(inputs/'reader-key.json')
    labels = load(inputs/'reader-verdict.json')
    by_mask = {r['id']:r for r in labels}
    if len(by_mask) != len(labels) or len(packet) != len(witness) or len(mask_key) != len(packet):
        raise ValueError('Incorrect rating or packet cardinality')
    masked = {r['id']:r for r in packet}
    decoded = {(k['work_id'],k['id']):k['masked_id'] for k in mask_key}
    if (len(decoded)!=len(mask_key) or set(decoded.values())!=set(masked) or set(masked)!=set(by_mask)
            or set(decoded)!={ln.key for ln in lines}):
        raise ValueError('Masked verdict and key differ from the source')
    target, rows = [], []
    for i, ln in enumerate(lines):
        mid = decoded[ln.key]
        label, item = by_mask[mid], masked[mid]
        if item['text']!=ln.row['text'] or label['work_id']!=item['work_id'] or not label['reason'].strip():
            raise ValueError(f'Correspondence lost at {ln.key}')
        score = label['score']
        if ln.complete and (not grammar.context.valid_score(score) or not label['quote'] or label['quote'] not in item['text']):
            raise ValueError(f'Invalid rating or quotation at {ln.key}')
        if not ln.complete and score is not None:
            raise ValueError('Material lacuna must remain unscored')
        target.append(score)
        rows.append({**ln.row,'role':works[ln.key[0]]['role'],'confirmed':ln.key in named,
                     'excluded':excluded.get(ln.key),'features':frames[ln.key][0],
                     'raw':{m:predictions[m][i] for m in MODES},'editorial':score,
                     'quote':label['quote'],'reason':label['reason']})
    summary = {k:measure(g,predictions,target) for k,g in groups.items()}
    controls = shuffled(lines, original, pretrained, groups, target, summary)
    result = {'endpoint':'written editorial 音律美','summary':summary,'controls':controls,'rows':rows,
              'sources':cards,'reviewed_windows':triples,'historical_sha256':lex_hash,'input_sha256':signatures,
              'shuffle_seed':grammar.SEED,'model_sha256':MODEL_SHA}
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)/'result'
        stage.mkdir()
        (stage/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        overview = ['Fresh challenge | written editorial 音律美 | unchanged expanded models',
                    'Raw mean absolute error, lower is better. Each work has equal weight.',
                    'Subset               Units  Works   Always 6   Without grammar   With grammar']
        for name,s in summary.items():
            v = s['equal_work']
            overview.append(f'{name:21s} {s["n"]:3d} {len(s["by_work"]):6d} {v["always_six"]:10.3f} {v["context"]:16.3f} {v["context_grammar"]:14.3f}')
        overview.extend(['', 'Excluded units: '+str(len(excluded)), 'Target: one frozen text-only editorial reading.'])
        (stage/'summary.txt').write_text('\n'.join(overview)+'\n')
        table = ['Original source order | written 音律美', 'Scores below are raw. Constant comparator = 6.']
        for r in rows:
            table.extend(['', f'{r["title"]} {r["id"]}  {r["text"]}',
                          f'Editorial {r["editorial"]} | Without grammar {r["raw"]["context"]:.2f} | With grammar {r["raw"]["context_grammar"]:.2f} | Confirmed run {r["confirmed"]} | {r["excluded"] or "scored"}',
                          r['reason']])
        (stage/'line-scores.txt').write_text('\n'.join(table)+'\n')
        stage.rename(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root','inputs','output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--screen', action='store_true', help='Freeze eligible IDs without loading ratings or predicting')
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if not all(p.resolve().is_relative_to(root) for p in (args.inputs,args.output)):
        parser.error('Keep challenge data on Gilbreth')
    run(root,args.inputs.resolve(),args.output.resolve(),args.screen)
