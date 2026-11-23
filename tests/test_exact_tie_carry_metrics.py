import math
import unittest

from src.exact_tie_carry_metrics import benchmark


def row(work, unit, group, score, current, one, two=None):
    return dict(work_id=work, id=unit, group=group, score=score, current=current,
                coder1=one, coder2=two or one)


class ExactTieMetricsTests(unittest.TestCase):
    def test_work_balance_abstention_and_mixed_group_members(self):
        rows = [row("w", "a", "1", 7, 6.0, "advance"),
                row("w", "b", "1", 6, 6.0, "parallel"),
                row("w", "c", "1", 6, 6.0, "advance"),
                row("w", "d", "1", 5, 6.0, "restate"),
                row("w", "e", "2", 6, 5.5, "advance"),
                row("w", "f", "2", 7, 5.5, "advance", "parallel"),
                row("x", "a", "1", 7, 6.0, "advance"),
                row("x", "b", "1", 6, 6.0, "parallel")]
        report = benchmark(rows)
        main = report["primary"]
        self.assertEqual((main["n_pairs"], main["n_units"], main["informative_groups"]), (4, 7, 3))
        self.assertEqual((main["correct"], main["wrong"], main["tied"]), (2, 1, 1))
        self.assertEqual(main["methods"]["augmented"]["macro"], .75)
        self.assertEqual(main["methods"]["augmented"]["pooled"], .625)
        self.assertEqual(report["opposite"]["n_pairs"], 2)
        self.assertEqual(report["consensus_only"]["n_pairs"], 3)
        self.assertEqual(report["sensitivity"]["coder1"]["tied"], 2)
        self.assertEqual(report["permutation"]["draws"], 999)

    def test_binary_scores_and_clipping(self):
        rows = [row("w", "a", "G", 7, 7.0, "advance"), row("w", "b", "G", 6, 7.0, "parallel")]
        report = benchmark(rows)
        self.assertEqual(report["primary"]["fraction_resolved"], 0)
        self.assertEqual(report["permutation"]["p_upper"], 1)
        self.assertIsNone(report["primary"]["accuracy_among_resolved"])
        with self.assertRaisesRegex(ValueError, "full-precision"):
            benchmark([rows[0], dict(rows[1], current=math.nextafter(7., 0.))])
        with self.assertRaisesRegex(ValueError, "full-precision"):
            benchmark([rows[0], dict(rows[1], group="H")])

    def test_no_cross_work_or_cross_score_pairs(self):
        rows = [row("w", "a", "1", 7, 6., "advance"), row("w", "b", "2", 6, 5., "parallel"),
                row("x", "a", "1", 6, 6., "parallel")]
        out = benchmark(rows)
        self.assertFalse(out["primary"]["informative_works"])
        self.assertIsNone(out["primary"]["methods"]["always6"]["macro"])
        self.assertEqual(out["permutation"]["draws"], 0)
        self.assertIsNone(out["permutation"]["p_upper"])
        self.assertEqual(out["n_targets"], 3)
