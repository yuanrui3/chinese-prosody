"""Ablation, held-out scoring and work-level resampling regression checks."""
from importlib.util import find_spec
import unittest

if find_spec('numpy'):
    from src import written_rhyme_ablation as study


@unittest.skipUnless(find_spec('numpy'), 'The Gilbreth written model requires NumPy')
class WrittenRhymeAblationTest(unittest.TestCase):
    def target(self, ident, work, genre, value):
        return {'id': ident, 'work_id': work, 'genre': genre, 'author': work, 'text': ident,
                'section': '正文', 'target': True,
                'predictions': {'with_rhyme': value, 'without_cross_line': 6.,
                                'without_any_rhyme': 5., 'always_6': 6.}}

    def test_separate_cross_and_internal_rhyme_ablations(self):
        full = set(study.COLUMNS['with_rhyme'])
        self.assertEqual(full - set(study.COLUMNS['without_cross_line']), set(study.CROSS))
        self.assertEqual(full - set(study.COLUMNS['without_any_rhyme']), set(study.CROSS + study.INTERNAL))
        self.assertTrue(set(study.INTERNAL).issubset(study.COLUMNS['without_cross_line']))
        for names in study.COLUMNS.values():
            self.assertIn('guangyun_group_end_pz_alternation', names)
            self.assertIn('three_line_frame', names)

    def test_sealed_ratings_require_one_integer_per_target(self):
        rows = [self.target('a', 'work', 'fu', 6)]
        for labels in ([], [{'id': 'a', 'score': 4.5}], [{'id': 'b', 'score': 6}],
                       [{'id': 'a', 'score': 5}, {'id': 'a', 'score': 5}]):
            with self.assertRaises(ValueError):
                study.compare(rows, labels)

    def test_primary_weights_works_and_uses_paired_differences(self):
        pred = [self.target(i, 'short', 'fu', 7.) for i in ('a',)]
        pred.extend(self.target(i, 'long', 'prose', 5.) for i in ('b', 'c', 'd'))
        labels = [{'id': x['id'], 'score': 6} for x in pred]
        labels[0]['score'] = 7
        out = study.compare(pred, labels)
        all_ = out['groups']['all']
        self.assertEqual(all_['work_equal_mae']['with_rhyme'], .5)
        self.assertEqual(all_['work_equal_mae']['always_6'], .5)
        self.assertEqual(all_['full_minus']['always_6']['paired_95'], [0., 0.])
        self.assertFalse(out['decision']['passes'])
        self.assertEqual(out['groups']['fu']['full_minus']['always_6']['paired_95'], [-1., -1.])

    def test_exposure_and_stale_target_checks(self):
        rows = [self.target('甲', 'A', 'fu', 6.)]
        study.validate_corpus(rows, [])
        for prior in ([{'work_id': 'A', 'text': '乙'}], [{'author': 'A', 'text': '乙'}],
                      [{'work_id': 'old', 'text': '甲。'}]):
            with self.assertRaises(ValueError):
                study.validate_corpus(rows, prior)
        with self.assertRaises(ValueError):
            study.validate_corpus([dict(rows[0], target=False)], [])
