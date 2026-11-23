import unittest
from types import SimpleNamespace

from src import quantitative_fresh_triples as challenge


class TripleEndpointTests(unittest.TestCase):
    def test_verified_overlapping_windows_count_each_unit_once(self):
        ids = list('abcd')
        lines = [SimpleNamespace(key=('w', i)) for i in ids]
        edges = [{'work_id':'w', 'left_id':a, 'right_id':b, 'whole_frame':True}
                 for a,b in zip(ids, ids[1:])]
        windows = [{'work_id':'w','ids':ids[i:i+3],'explanation':'same syntactic positions'} for i in (0,1)]
        self.assertEqual(challenge.confirmed_keys(windows, lines, edges), {line.key for line in lines})
        edges[1]['whole_frame'] = False
        with self.assertRaisesRegex(ValueError, 'consecutive'):
            challenge.confirmed_keys(windows, lines, edges)

    def test_each_work_receives_equal_weight(self):
        forecasts = {m:[6,6,6] for m in challenge.MODES}
        observed = challenge.measure({'a':[0], 'b':[1,2]}, forecasts, [4,6,6])
        self.assertEqual(observed['equal_work']['always_six'], 1.0)
        self.assertAlmostEqual(observed['pooled']['always_six'], 2/3)
