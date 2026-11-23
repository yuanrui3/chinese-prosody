import unittest

from src.top_score_calibration_controls import permutation_control


class CalibrationControlTests(unittest.TestCase):
    def test_shuffle_preserves_each_works_sevens_and_cutoff(self):
        rows = [
            dict(work_id="a", id="1", score=7, current=6.2),
            dict(work_id="a", id="2", score=6, current=5.8),
            dict(work_id="b", id="1", score=7, current=5.4),
            dict(work_id="b", id="2", score=5, current=5.7),
        ]
        out = permutation_control(rows, 6.0)
        stat = out["calibrated_recall"]
        self.assertEqual(stat["observed"], 0.5)
        self.assertEqual(stat, out["recall_gain_vs_current"])
        self.assertTrue(399 < stat["at_least_observed"] < 600)
        self.assertEqual(stat["p_upper"], (stat["at_least_observed"] + 1) / 1000)
        self.assertEqual(out, permutation_control(rows, 6.0))
        sensitivity = out["leave_one_work_out"]
        self.assertEqual(sensitivity["ranges"]["macro_recall7"], {"min": 0, "max": 1, "defined_subsets": 2})
        self.assertEqual(sensitivity["ranges"]["pooled_precision7"]["defined_subsets"], 1)

    def test_no_recall_denominator_and_identical_forecasts(self):
        rows = [dict(work_id="a", id="1", score=6, current=6.6)]
        out = permutation_control(rows, 6.5)
        self.assertEqual(out["draws"], 0)
        self.assertIsNone(out["calibrated_recall"]["p_upper"])
        rows.append(dict(work_id="a", id="2", score=7, current=6.7))
        out = permutation_control(rows, 6.5)
        self.assertEqual(out["recall_gain_vs_current"],
                         {"observed": 0, "median_shuffled": 0, "at_least_observed": 999, "p_upper": 1})
