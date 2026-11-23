import unittest

from src import quantitative_grammar_expansion as expansion


class ExpansionTests(unittest.TestCase):
    def test_repeated_test_text_cannot_join_training_neighbors(self):
        rows = [
            {'work_id': 'a', 'section': 'p', 'id': str(i), 'text': text}
            for i, text in enumerate(('其聲清。', '嗟乎！', '其氣明。', '其色清。'))
        ]
        labels = [{'score': 6, 'quote': row['text'], 'reason': 'fixture'} for row in rows]
        protected = {'test': [{'work_id': 'b', 'id': 'only', 'text': '嗟乎。'}]}
        used, excluded = expansion.build_additions(
            {'train-a': rows, 'train-b': []}, {'train-a': labels, 'train-b': []}, protected)
        self.assertEqual([r['id'] for r in used], ['0', '2', '3'])
        self.assertEqual(excluded[0]['matches'], [{'split': 'test', 'work_id': 'b', 'id': 'only'}])
        self.assertNotEqual(used[0]['section'], used[1]['section'])
        self.assertEqual(used[1]['section'], used[2]['section'])
        self.assertEqual(used[1]['source_section'], 'p')

    def test_swapped_text_fails_to_unmask_with_matching_ids(self):
        blind = [{'work_id': 'masked', 'id': 'm1', 'text': '其色清。', 'section': '1'}]
        witness = [{'work_id': 'work', 'id': 'w1', 'text': '其聲清。', 'section': '1'}]
        labels = [{'work_id': 'masked', 'id': 'm1', 'score': 6, 'quote': '清', 'reason': 'fixture'}]
        with self.assertRaisesRegex(ValueError, 'Blinded text or section mismatch'):
            expansion.unmask(witness, blind, labels, {('masked', 'm1'): ('work', 'w1')}, 'test')
