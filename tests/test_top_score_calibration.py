"""Regression tests for strict work holdout and inclusive, false-six-limited top calls."""

import json
import unittest

from src.quantitative_top_score_calibration import benchmark, call_seven, fit


def work(name, entries):
    return [dict(work_id=name, id=str(i), score=label, current=value)
            for i, (label, value) in enumerate(entries)]


class TopScoreCalibrationTests(unittest.TestCase):
    def test_tied_predictions_call_every_unit_and_accept_exact_twenty_percent(self):
        rows = work("a", [(7, 6.2), (6, 6.2)] + [(6, 5)] * 4 + [(4, 6.2)])
        result = fit(rows)
        self.assertEqual(result["threshold"], 6.2)
        summary = result["training"]["pooled"]
        self.assertEqual((summary["true7"], summary["false7_from6"], summary["false7_from_lower"]), (1, 1, 1))
        self.assertAlmostEqual(summary["precision7"], 1 / 3)
        self.assertEqual(fit(rows[:5])["threshold"], 6.5)

    def test_both_false_six_guards_are_enforced(self):
        big_violates = work("large", [(7, 6.2)] + [(6, 6.2)] * 3 + [(6, 5)] * 7)
        small_safe = work("small", [(6, 5)])
        self.assertEqual(fit(big_violates + small_safe)["threshold"], 6.5)
        big_safe = work("large", [(6, 5)] * 10 + [(7, 6.2)])
        small_violates = work("small", [(6, 6.2)])
        self.assertEqual(fit(big_safe + small_violates)["threshold"], 6.5)

    def test_keep_current_on_ties_and_never_call_if_tied_maximum_exceeds_budget(self):
        self.assertEqual(fit(work("w", [(7, 6.9), (6, 5.9)]))["threshold"], 6.5)
        self.assertIsNone(fit(work("w", [(7, 7.0), (6, 7.0)]))["threshold"])
        self.assertFalse(call_seven(7.0, None))
        self.assertEqual(fit(work("w", [(7, 5.0)]))["status"], "missing calibration class")
        self.assertIsNone(fit(work("w", [(6, 6.9)]))["threshold"])
        self.assertEqual(fit([])["threshold"], 6.5)

    def test_each_earlier_work_is_held_out_and_fresh_labels_cannot_change_cutoff(self):
        earlier = work("a", [(7, 6.4), (6, 5.0)]) + work("b", [(7, 6.1), (6, 5.0)])
        fresh = work("c", [(7, 6.3), (6, 5.9), (3, 6.2), (None, None)])
        result = benchmark(earlier, fresh)
        oof = result["earlier_oof"]
        self.assertEqual(oof["folds"]["a"]["training_works"], ["b"])
        self.assertEqual(oof["folds"]["b"]["training_works"], ["a"])
        self.assertEqual([r["calibrated_threshold"] for r in oof["rows"]], [6.1, 6.1, 6.4, 6.4])
        self.assertEqual(oof["methods"]["calibrated"]["pooled"]["true7"], 1)
        self.assertEqual(result["fresh"]["decision"]["status"], "passed")
        for r in result["fresh"]["rows"]:
            self.assertEqual(r["calibrated_threshold"], 6.1)
        self.assertEqual(result["fresh"]["excluded"], [{"work_id": "c", "id": "3"}])
        self.assertEqual(result["fit"], benchmark(earlier, work("d", [(2, 2.0)]))["fit"])
        self.assertIsNone(result["fresh"]["methods"]["always6"]["pooled"]["precision7"])
        self.assertEqual(benchmark(earlier, [])["fresh"]["decision"]["status"], "undefined")
        json.dumps(result, allow_nan=False)

    def test_no_shared_work_and_no_repeated_unit_keys(self):
        with self.assertRaisesRegex(ValueError, "both calibration and fresh"):
            benchmark(work("a", [(7, 6.2)]), work("a", [(6, 5.0)]))
        unit = work("w", [(6, 5.0)])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            fit(unit + unit)
