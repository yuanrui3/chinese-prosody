"""Build same-witness prescriptions for isolated Mandarin ending changes."""

import re

if __package__:
    from .align import lexical_key
else:
    from align import lexical_key


PINYIN = re.compile(r'[a-z]+[1-5]')


def tokens(prescription):
    return [token for clause in prescription['clauses'] for token in PINYIN.findall(clause)]


def change_token(prescription, target, replacement):
    clauses = list(prescription['clauses'])
    if not PINYIN.fullmatch(replacement) or target < 0:
        raise ValueError('Expected a numbered pinyin syllable and valid target slot')
    for index, clause in enumerate(clauses):
        matches = list(PINYIN.finditer(clause))
        if target < len(matches):
            match = matches[target]
            clauses[index] = clause[:match.start()] + replacement + clause[match.end():]
            return {**prescription, 'clauses': clauses}
        target -= len(matches)
    raise ValueError('Target is outside the pinyin prescription')


def candidate_key(pinyin):
    segments, tone = lexical_key(pinyin)
    return (*segments, tone)


def variants(passage, prescription, plan):
    slots = passage['slots']
    readings = tokens(prescription)
    target, anchor = plan['target_slot_index'], plan['anchor_slot_index']
    if not 0 <= target < len(slots) - 1 or not 0 <= anchor < len(slots):
        raise ValueError('Expected an internal test ending and an anchor in the passage')
    a, b = slots[target], slots[anchor]
    if (not a['boundary_after'] or not b['boundary_after']
            or abs(a['clause_index'] - b['clause_index']) != 1
            or a['char'] != plan['target_character'] or b['char'] != plan['anchor_character']
            or readings[target] != plan['base'] or readings[anchor] != plan['anchor']):
        raise ValueError(f"{plan['passage_id']}: ending or rhyme anchor differs from its pinned recipe")

    base_key = candidate_key(readings[target])
    tone_key, rhyme_key = (candidate_key(plan[role]) for role in ('tone', 'rhyme'))
    for role, key, expected in (('tone', tone_key, [2]), ('rhyme', rhyme_key, [1])):
        changed = [i for i, (old, new) in enumerate(zip(base_key, key)) if old != new]
        if changed != expected:
            raise ValueError(f"{plan['passage_id']}: {role} must change only its designated feature")
    anchor_final = candidate_key(readings[anchor])[1]
    recurrence_before = base_key[1] == anchor_final
    if recurrence_before == (rhyme_key[1] == anchor_final):
        raise ValueError(f"{plan['passage_id']}: rhyme edit must reverse recurrence with its anchor")
    common = {'target_slot_index': target, 'anchor_slot_index': anchor, 'anchor_pinyin': readings[anchor]}
    return [
        ({**prescription} if role in ('base', 'sham') else change_token(prescription, target, plan[role]),
         {**common, 'role': role, 'candidate_key': key})
        for role, key in [('base', base_key), ('sham', base_key), ('tone', tone_key), ('rhyme', rhyme_key)]
    ]
