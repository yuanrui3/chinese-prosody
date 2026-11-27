from importlib.util import find_spec
import unittest

if find_spec('numpy'):
    import numpy as np
    from src import within_work_rank as study


@unittest.skipUnless(find_spec('numpy'), 'The pinned release scoring environment uses NumPy')
class WithinWorkRankingTests(unittest.TestCase):
    def test_pair_orientation_work_mass_and_stationarity(self):
        # C has no 7. A's many cross-products must have the same total mass as B's one.
        x = np.array([[2,1], [1,2], [0,3], [-1,0], [5,4], [0,4], [9,8]], dtype=float)
        y = [7,7,6,5,7,6,5]
        works = ['A','A','A','A','B','B','C']
        d, mass, counts = study.training_pairs(x,y,works)
        self.assertEqual([r['pairs'] for r in counts.values()], [4,1,0])
        np.testing.assert_allclose(mass, [.125,.125,.125,.125,.5])
        beta, convergence = study.fit_ranker(d,mass)
        self.assertLessEqual(convergence['max_abs_gradient'], 1e-9)
        self.assertGreater((d @ beta).min(), 0.)
        idx = np.array([5,6,2,1,3,4,0])
        reorder = study.training_pairs(x[idx], np.array(y)[idx], np.array(works)[idx])
        np.testing.assert_allclose(study.fit_ranker(*reorder[:2])[0], beta, atol=1e-10)
        # Translating all lines of one work cannot change its pair differences.
        x[:4] += [5,-6]
        np.testing.assert_array_equal(study.training_pairs(x,y,works)[0], d)

    def test_exact_ties_macro_pair_counts_and_missing_endpoints(self):
        p, gold = [], []
        def add(work,genre,ratings,candidate,current):
            for i,(rating,u,v) in enumerate(zip(ratings,candidate,current)):
                ident = f'{work}{i}'
                p.append({'id':ident,'work_id':work,'genre':genre,
                          'predictions':{'pairwise':u,'current':v,'always_6':6}})
                gold.append({'id':ident,'score':rating})
        add('A','fu',[7,5,6,2],[2,2,1,300],[4,6,6,4])
        add('B','prose',[7,6],[1,2],[6,5])
        add('C','prose',[7],[2],[5])
        data = study.compare(p,gold,draws=60,shuffles=59)['groups']
        main = data['all']['seven_vs_five_six']
        self.assertEqual((main['works'],main['eligible_works'],main['pairs'],main['sevens'],main['eligible_sevens']),
                         (3,2,3,3,2))
        self.assertEqual(main['methods']['pairwise'], {
            'wins':1,'ties':1,'losses':1,'pair_pooled_concordance':.5,'work_equal_concordance':.375})
        self.assertEqual(main['methods']['current']['work_equal_concordance'], .5)
        self.assertEqual(main['methods']['always_6']['work_equal_concordance'], .5)
        self.assertEqual(main['shuffle']['always_6'], {'mean':.5,'one_sided_plus_one':1.,'informative':False})
        absent = data['prose']['seven_vs_five']
        self.assertEqual(absent['eligible_works'], 0)
        self.assertIsNone(absent['methods']['pairwise']['work_equal_concordance'])
        self.assertEqual(absent['paired']['current'], {'difference':None,'paired_95':None,'valid_draws':0})
        self.assertEqual(data['fu']['seven_vs_six']['methods']['pairwise']['wins'], 1)
        self.assertEqual(data['fu']['seven_vs_five']['methods']['pairwise']['ties'], 1)

    def test_released_standardization_preserves_missing_feature_and_rank_scale(self):
        model = {'names':['a','b'], 'means':[4.,30.], 'scales':[2.,10.]}
        x = study.standardized(model, [{'a':None,'b':40},{'a':-12,'b':30}])
        np.testing.assert_array_equal(x,[[0.,1.],[-8.,0.]])
        with self.assertRaisesRegex(ValueError, 'No training work'):
            study.training_pairs(x,[7,4],['A','A'])
