"""Test source-identified readings with fixed text and frozen written scoring weights."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from src import quantitative_ending_functions as frozen
from src import quantitative_editorial_grammar as grammar
from src.stage7_text import annotate_text
from src.yu_review_baseline import save_sealed


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def candidate_for(char, selector, lex, native):
    if 'lower' in selector:
        # A fanqie lower speller supplies the rime and tone, never the onset.
        entries = lex['guangyun'][selector['lower']]
        expected = {(selector['tone'], selector['rhyme'])}
        if {(e['tone'], e['rhyme']) for e in entries} != expected:
            # 角 has two readings. The exact complete cut 苦角 is attested.
            exact = {(c['tone'], c['rhyme']) for row in lex['guangyun'].values() for c in row
                     if any(e.get('fanqie') == selector['cut'] for e in c['entries'])}
            if exact != expected:
                raise ValueError(f"Both the lower speller and the complete cut are underdetermined: {selector}")
        return {'id': f"fanqie-projection:{char}:{selector['cut']}", 'rhyme': selector['rhyme'],
                'tone': selector['tone'], 'pingze': '平' if selector['tone'] == '平' else '仄'}
    candidates = lex['guangyun'][selector['donor']] if 'donor' in selector else native
    chosen = [c for c in candidates if c['tone'] == selector['tone'] and c['rhyme'] == selector['rhyme']]
    if len(chosen) != 1:
        raise ValueError(f"{char}: {selector} matched {len(chosen)} candidates")
    return chosen[0]


def condition(case, arm, lex, rows, target, key):
    """Change a single slot, even when a sound gloss requires another headword."""
    text = rows[target]
    char = case['char']
    assert text.count(char) == 1
    offset = text.index(char)
    # Retain all candidates, including any selected through character-variant lookup.
    original = annotate_text(text, **lex, historical_readings=[])['slots']
    at = next(s for s in original if s['offset'] == offset)['readings']['guangyun']
    choices = [candidate_for(char, sel, lex, at['candidates']) for sel in case['readings']]
    pick = choices[arm]
    extra = [c for c in choices if c not in at['candidates']]
    row_lex = {**lex, 'guangyun': {**lex['guangyun'], char: [*at['candidates'], *extra]}} if extra else lex
    decision = dict(anchor=text, offset=offset, char=char, match={'id': pick['id']}, tier='guangyun',
                    source=case['critic_source'], reason=case['evidence'])
    lines, native_rows = [], []
    for i, sentence in enumerate(rows):
        is_target = i == target
        row = dict(id=f'L{i}', work_id=key, section='1', text=sentence,
                   historical_readings=[decision] if is_target else [])
        lines.extend(grammar.context.describe([row], row_lex if is_target else lex))
        native_rows.append(row)
    features, _ = grammar.matrix_rows(lines, lines, grammar.context.in_context(lines))
    return features[target], pick['id'], native_rows


def run(root, folder, seal):
    packet = folder / 'inputs/packet.json'
    if sha(packet) != seal:
        raise ValueError('Input packet differs from its seal')
    cases = json.loads(packet.read_text())
    archive = root / 'results/grammatical-training-expansion-20261122'
    path = archive / 'results/fresh-expanded-results.json'
    assert sha(path) == frozen.prev.MODEL_SHA
    model = json.loads(path.read_text())['models']['context_grammar']
    lex, hashes = grammar.context.base.lexicon_data(root)
    assert hashes == json.loads((archive / 'results/summary.json').read_text())['lexicon_sha256']
    all_native, expected, results = [], {}, {}
    for case in cases:
        conditions = {'isolated': ([case['text']], 0)}
        if 'context' in case:
            conditions['neighbors'] = case['context'], case['target_index']
        results[case['id']] = {}
        for mode, (rows, target) in conditions.items():
            arms = []
            for arm, selector in enumerate(case['readings']):
                key = f"{case['id']}-{mode}-{arm}"
                values, chosen, native = condition(case, arm, lex, rows, target, key)
                score = frozen.prev.bounded(grammar.context.predict(model, [values])[0])
                arms.append(dict(score=score, selected=chosen, features=values))
                if 'donor' not in selector and 'lower' not in selector:
                    all_native.extend(native)
                    expected[key, native[target]['id']] = score
            changed = {k: [v['features'][k] for v in arms] for k in model['names']
                       if arms[0]['features'][k] != arms[1]['features'][k]}
            delta = arms[0]['score'] - arms[1]['score']
            direction = 0 if abs(delta) <= 1e-10 else (1 if delta > 0 else -1)
            # Repeat numerical inference on the reversed inputs and an identical duplicate.
            backwards = grammar.context.predict(model, [arms[1]['features'], arms[0]['features'], arms[0]['features']])
            assert all(abs(frozen.prev.bounded(s) - arms[a]['score']) <= 1e-12 for s,a in zip(backwards,(1,0,0)))
            results[case['id']][mode] = dict(rows=rows,target_index=target,arms=arms,
                                             delta_first_minus_second=delta,changed_features=changed,
                                             votes={name: direction * sign for name, sign in case['directions'].items()})
    check, _ = frozen.model(root, archive, all_native)
    assert all(abs(check[k]-v) <= 1e-12 for k,v in expected.items())
    save_sealed(folder/'results/scores.json', dict(packet_sha256=seal, model_sha256=sha(path),
                dictionaries=hashes, native_target_predictions_checked=len(expected), results=results))
    for key, modes in results.items():
        for mode, result in modes.items():
            print(key, mode, [round(a['score'], 6) for a in result['arms']], list(result['changed_features']), result['votes'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('folder', type=Path)
    parser.add_argument('packet_sha256')
    a = parser.parse_args()
    run(a.root, a.folder, a.packet_sha256)
