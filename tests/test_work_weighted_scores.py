from importlib.util import find_spec
from unittest.mock import patch
import unittest

if find_spec('numpy'):
    import numpy as np
    from src import work_weighted_scores as study


@unittest.skipUnless(find_spec('numpy'), 'The archived written scorer uses NumPy')
class WorkWeightedTests(unittest.TestCase):
    def test_equal_work_moments_with_missing_and_sparse_features(self):
        rows = [{'a': 0, 'b': None}, {'a': 2, 'b': 1.}, {'a': 10, 'b': None}]
        fit = study.equal_work_fit(rows, [1, 3, 7], ['long', 'long', 'short'], ('a', 'b'))
        self.assertEqual(fit['intercept'], 4.5)
        self.assertEqual(fit['means'], [5.5, 1.])
        self.assertEqual(fit['observed_weight'], [3., .75])
        self.assertEqual(fit['scales'][1], 1.)
        np.testing.assert_allclose(fit['scales'][0], np.sqrt(.25 * 5.5 ** 2 + .25 * 3.5 ** 2 + .5 * 4.5 ** 2))
        self.assertEqual(fit['weights'][1], 0.)

    def test_balanced_sample_reproduces_unweighted_ridge(self):
        rows = [{'a': v, 'b': b} for v, b in [(1, 2), (4, 6), (5, None), (3, 1)]]
        scores = [6, 4, 7, 7]
        fit = study.equal_work_fit(rows, scores, ['x','x','y','y'], ('a','b'))
        other = study.context.fit_model(rows, scores, ('a', 'b'))
        for key in ('intercept', 'means', 'scales', 'weights'):
            np.testing.assert_allclose(fit[key], other[key], rtol=0, atol=1e-14)

    @staticmethod
    def row(ident, work, balanced, current, genre='fu'):
        return {'id':ident,'work_id':work,'genre':genre,
                'predictions':{'equal_work':balanced,'current':current,'always_6':6.}}

    def test_cutoff_negative_classes_and_paired_metrics(self):
        rows = [self.row(0,'A',6.5,6), self.row(1,'A',5.,6.6), self.row(2,'B',6.501,6),
                self.row(3,'B',6.499,5), self.row(4,'C',6.8,6,'prose'), self.row(5,'C',6.2,6,'prose')]
        grades = [7, 5, 7, 7, 6, 3]
        with patch.object(study, 'DRAWS', 200):
            r = study.compare(rows, [{'id':i,'score':g} for i,g in enumerate(grades)])
        a = r['groups']['all']
        self.assertEqual((a['methods']['equal_work']['hits'], a['methods']['equal_work']['misses']), (2,1))
        self.assertEqual(a['methods']['equal_work']['false_positives_among_sixes'], 1)
        self.assertEqual(a['methods']['current']['false_positives_among_sixes'], 0)
        self.assertEqual(a['methods']['current']['false_positives'], 1)
        self.assertEqual(a['methods']['equal_work']['recall'], 2/3)
        self.assertIsNone(a['methods']['always_6']['precision'])
        self.assertEqual(a['changed_sevens']['current']['gained_works'], 2)
        self.assertAlmostEqual(a['methods']['equal_work']['sd'],
                               np.std([r['predictions']['equal_work'] for r in rows]))
        self.assertEqual(r['groups']['prose']['equal_work_minus']['current']['recall'],
                         {'difference':None,'paired_95':None,'valid_draws':0})
        self.assertEqual(a['within_work_shuffle']['methods']['always_6']['one_sided_plus_one'], 1.)

    def test_each_work_has_equal_mass_on_unequal_holdout_counts(self):
        rows = [self.row('a','A',7,6)] + [self.row(i,'B',5,6) for i in range(4)]
        labels = [{'id':r['id'], 'score':5} for r in rows]
        with patch.object(study, 'DRAWS', 100):
            result = study.compare(rows, labels)['groups']['all']['methods']['equal_work']
        self.assertEqual(result['sd'], 1.)
        self.assertEqual(result['mean_within_work_sd'], 0.)
        self.assertEqual(result['mae'], 1.)
        self.assertIsNone(result['recall'])
