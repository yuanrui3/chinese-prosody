import importlib.util
import unittest

if importlib.util.find_spec('numpy') is not None:
    from src import quantitative_editorial_context as context


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'The pinned scoring environment supplies NumPy')
class EditorialContextTests(unittest.TestCase):
    @staticmethod
    def row(work, identifier, text, section='a', **fields):
        return {'id': identifier, 'work_id': work, 'section': section, 'text': text, **fields}

    def test_rhyme_requires_decidable_relation_and_respects_sections(self):
        readings = {char: [{'rhyme': name} for name in rhymes] for char, rhymes in
                    [('子', ['甲']), ('祉', ['甲', '乙']), ('美', ['甲']), ('山', ['丙'])]}
        lexicons = {'pingshui': readings}
        rows = [self.row('w', '1', '子'), self.row('w', '2', '祉'), self.row('w', '3', '美'),
                self.row('w', '4', '山', 'b'), self.row('v', '1', '子', 'b')]
        features = context.in_context(context.describe(rows, lexicons))
        values, neighbors, support = features[('w', '1')]
        self.assertEqual(neighbors, ['2', '3'])
        self.assertEqual(support['pingshui'], {'eligible': 2, 'resolved': 1})
        self.assertEqual(values['pingshui_cross_line_rhyme'], 1)
        self.assertIsNone(features[('w', '2')][0]['pingshui_cross_line_rhyme'])
        self.assertEqual(features[('w', '4')][1], [])
        self.assertEqual(features[('v', '1')][1], [])
        self.assertEqual(context.rhyme_agreement({'甲', '乙'}, {'丙'}), 0)

    def test_structural_features_keep_failed_echo_and_unmatched_groups(self):
        self.assertEqual(context.shape_and_echo(('山中', '天'), ('山外',)), (2 / 3, 1 / 3))
        self.assertEqual(context.arm_balance(('神有禍兮人無祉',)), 1)
        self.assertIsNone(context.arm_balance(('兮人',)))
        self.assertAlmostEqual(context.arm_balance(('山中', '天')), 0.5)

    def test_identical_baseline_and_held_out_labels_have_no_effect_on_fit(self):
        ref = [self.row('a', '1', '天寒。', score=4), self.row('a', '2', '水落，石出。', score=6),
               self.row('a', '3', '紅霞漸起。', score=7)]
        wit = [self.row('b', '1', '海風，江月。', editorial_score=5),
               self.row('b', '2', '春風徐來。', editorial_score=6),
               self.row('b', '3', '霜□寒。')]
        original = context.base.evaluate(ref, wit, {})['rows']
        first = context.evaluate(ref, wit, {}, repeats=3)
        for before, after in zip(original[:2], first['rows'][:2]):
            self.assertAlmostEqual(before['raw_prediction'], after['predictions']['baseline']['raw'])
        self.assertEqual(first['summary']['n_evaluated'], 2)
        self.assertIsNone(first['rows'][2]['predictions']['context']['raw'])
        self.assertNotIn('3', first['rows'][0]['neighbor_ids'])
        second = context.evaluate(ref, [{**w, 'editorial_score': 7} for w in wit], {}, repeats=3)
        self.assertEqual(first['fits'], second['fits'])
        self.assertEqual([x['predictions'] for x in first['rows']], [x['predictions'] for x in second['rows']])
        with self.assertRaisesRegex(ValueError, 'whole works'):
            context.evaluate(ref, [{**wit[0], 'work_id': 'a'}], {}, repeats=1)

    def test_constant_comparators_share_reference_only_values_across_works(self):
        ref = [self.row('a', '1', '山開', score=3), self.row('a', '2', '山遠', score=7),
               self.row('a', '3', '江長', score=7)]
        wit = [self.row('b', '1', '海風', editorial_score=7), self.row('c', '1', '明月', editorial_score=3)]
        result = context.evaluate(ref, wit, {}, repeats=1)
        self.assertEqual(result['training_constants'], {'constant_mean': 17 / 3, 'constant_median': 7})
        self.assertEqual(result['by_work']['b']['models']['constant_median']['mae_raw'], 0)
        self.assertEqual(result['by_work']['c']['models']['constant_median']['mae_raw'], 4)
        self.assertAlmostEqual(result['summary']['models']['constant_mean']['mae_raw'], 2)
        self.assertEqual(result['summary']['models']['constant_median']['mae_raw'], 2)
        self.assertNotIn('constant_mean', result['rows'][0]['predictions'])


if __name__ == '__main__':
    unittest.main()
