import importlib.util
from random import Random
import unittest

if importlib.util.find_spec('numpy') is not None:
    from src import quantitative_editorial_grammar as grammar


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'The pinned scoring environment supplies NumPy')
class EditorialGrammarTests(unittest.TestCase):
    @staticmethod
    def row(work, i, text, section='a', **fields):
        return dict(work_id=work, id=str(i), text=text, section=section, **fields)

    def test_varied_slots_in_comparison_and_season_frames(self):
        samples = ['葉如桂，冬青。', '華如橘，春榮。', '實如丹，夏熟。', '實如丹，夏熟。']
        rows = [self.row('a', i, s) for i, s in enumerate(samples)]
        lines = grammar.context.describe(rows, {})
        fm = grammar.frame_features(lines)
        for i in range(3):
            values, neighbors, slots = fm[('a', str(i))]
            self.assertEqual(values, dict(neighbor_whole_frame=1, neighbor_member_frame_coverage=1,
                                          three_line_frame=1))
            self.assertEqual(slots, (('', 'likening', ''), ('season', '')))
        self.assertEqual(fm[('a', '1')][1], ['0', '2'])
        self.assertEqual(fm[('a', '3')][0]['neighbor_whole_frame'], 0)
        self.assertEqual(fm[('a', '3')][0]['three_line_frame'], 0)

    def test_work_section_missing_neighbor_and_open_slots(self):
        rows = [self.row('b', 1, '雲如海。'), self.row('b', 2, '風如□。'), self.row('b', 3, '山如屏。'),
                self.row('b', 4, '松如雪。', 'b'), self.row('c', 5, '雲如雪。', 'b'),
                self.row('c', 6, '山中夜。', 'b'), self.row('c', 7, '水外春。', 'b')]
        frames = grammar.frame_features(grammar.context.describe(rows, {}))
        for values, neighbors, _ in frames.values():
            self.assertFalse(neighbors)
            self.assertFalse(any(values.values()))

    def test_slot_permutation_preserves_the_context_scores_and_group_lengths(self):
        rows = [self.row('a', i, s) for i, s in enumerate(['葉如桂，冬青。', '華如橘，春榮。', '實如丹，夏熟。'])]
        lines = grammar.context.describe(rows, {})
        ctx = grammar.context.in_context(lines)
        before, frames = grammar.matrix_rows(lines, lines, ctx)
        after, shuffled = grammar.matrix_rows(lines, lines, ctx, positions_rng=Random(13))
        for i, line in enumerate(lines):
            self.assertEqual([before[i][k] for k in grammar.MODEL_COLS['context']],
                             [after[i][k] for k in grammar.MODEL_COLS['context']])
            self.assertEqual(list(map(len, frames[line.key][2])), list(map(len, shuffled[line.key][2])))
        self.assertNotEqual([r['neighbor_whole_frame'] for r in before], [r['neighbor_whole_frame'] for r in after])

    def test_previous_model_reproduced_and_labels_do_not_enter_new_predictions(self):
        ref = [self.row('a', i, s, score=y) for i, (s, y) in enumerate(
            [('氣如玉。', 7), ('水如江。', 7), ('月落天寒。', 4), ('燕歸。', 5)])]
        test = [self.row('b', 1, '草如青絲。'), self.row('b', 2, '煙如白絹。'), self.row('c', 1, '其知也。')]
        labels = [{**{k: r[k] for k in ('work_id', 'id')}, 'score': s} for r, s in zip(test, [5, 7, 3])]
        run = grammar.evaluate(ref, test, labels, {}, 3)
        changed = grammar.evaluate(ref, test, [dict(label, score=4) for label in labels], {}, 3)
        legacy = grammar.context.evaluate(ref, test, {}, repeats=2)
        self.assertEqual([r['raw'] for r in run['rows']], [r['raw'] for r in changed['rows']])
        self.assertEqual(run['conditional_median_training']['frame']['median'], 7)
        self.assertEqual(run['conditional_median_training']['no_frame']['median'], 4.5)
        self.assertEqual([r['raw']['context'] for r in run['rows']],
                         [r['predictions']['context']['raw'] for r in legacy['rows']])
        self.assertEqual(run['mae']['always_six']['work_macro'], 2)
        self.assertAlmostEqual(run['mae']['always_six']['pooled'], 5 / 3)
        self.assertEqual(run['by_work']['b']['always_six']['concordance']['proportion'], 0.5)
        self.assertIsNone(run['by_work']['c']['always_six']['concordance']['proportion'])
        for mode, control in run['controls'].items():
            gains = control['gain_over_matched_context']['work_macro']
            self.assertAlmostEqual(gains['observed'], run['mae']['context']['work_macro']
                                   - run['mae']['context_grammar']['work_macro'])
            self.assertEqual(gains['draws'], 3)
            self.assertLessEqual(gains['count_at_least_as_large'], 3)
        self.assertEqual([(e['work_id'], e['left_id'], e['right_id']) for e in run['edges']], [('b', '1', '2')])
        self.assertTrue(run['edges'][0]['whole_frame'])
        with self.assertRaisesRegex(ValueError, 'label-free'):
            grammar.evaluate(ref, [dict(test[0], score=5)], [], {}, 1)
        with self.assertRaisesRegex(ValueError, 'whole works'):
            grammar.evaluate(ref, [dict(test[0], work_id='a')], [], {}, 1)

    def test_partial_alignment_and_empty_training_subgroup(self):
        rows = [self.row('a', 1, '葉如桂，冬青。'), self.row('a', 2, '華如橘，不久。')]
        lines = grammar.context.describe(rows, {})
        edges = []
        frame, _, _ = grammar.frame_features(lines, edge_details=edges)[lines[0].key]
        self.assertEqual(frame['neighbor_whole_frame'], 0)
        self.assertEqual(frame['neighbor_member_frame_coverage'], 3 / 5)
        self.assertTrue(edges[0]['any_aligned_frame'])
        self.assertFalse(edges[0]['whole_frame'])
        groups = grammar.fit_group_medians([frame], [5])
        self.assertEqual(groups['no_frame'], {'n': 0, 'median': 5, 'uses_global_fallback': True})
