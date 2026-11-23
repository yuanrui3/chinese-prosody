import json
import unittest

from src.written_carry_metrics import benchmark


def row(work, ident, score, current, first, second=None):
    return dict(work_id=work, id=ident, score=score, current=current, coder1=first, coder2=second or first)


class WrittenCarryMetricsTests(unittest.TestCase):
    def test_consensus_nonadvance_does_not_require_same_subcategory(self):
        result = benchmark(
            [
                row("a", "1", 7, 6.3, "advance"),
                row("a", "2", 6, 6.3, "parallel", "restate"),
                row("a", "3", 7, 6.6, "advance", "uncertain"),
                row("a", "4", 6, 6.7, "restate"),
                row("a", "5", 5, 6.1, "uncertain"),
            ]
        )
        self.assertEqual(result["agreement"]["exact"], 3)
        self.assertEqual(result["agreement"]["eligible"], 3)
        self.assertEqual(
            [r["role"] for r in result["rows"]], ["advance", "nonadvance", None, "nonadvance", None]
        )
        self.assertEqual(result["rows"][2]["augmented"], 6.6)
        z = result["consensus"]
        self.assertEqual((z["primary"]["within_pairs"], z["all"]["within_pairs"]), (2, 4))
        self.assertIsNone(z["all"]["methods"]["role_only"]["macro"])
        self.assertEqual(z["tied_opposite"]["transitions"]["tied"]["correct"], 1)
        self.assertEqual(z["error"]["all"]["methods"]["augmented"]["threshold"], dict(tp=2, fp=1, tn=2, fn=0))
        self.assertEqual(result["sensitivity"]["coder1"]["eligible_count"], 4)

    def test_macro_and_pair_weighting_exact_ties_and_disagreements(self):
        rows = [
            row("a", "1", 7, 6.0, "advance"),
            row("a", "2", 6, 6.0, "restate"),
            row("a", "3", 6, 6.0, "parallel"),
            row("b", "1", 7, 6.0, "parallel"),
            row("b", "2", 6, 6.0, "advance"),
            row("b", "3", 6, 6.0, "restate"),
            row("c", "1", 6, 6.0 + 1e-12, "parallel"),
            row("c", "2", 7, 6.0, "advance"),
        ]
        result = benchmark(rows)["consensus"]
        tied = result["tied_opposite"]
        self.assertEqual((tied["within_pairs"], tied["informative_works"]), (3, ["a", "b"]))
        self.assertEqual(tied["methods"]["augmented"]["macro"], 0.5)
        self.assertEqual(tied["methods"]["augmented"]["within_pooled"], 2 / 3)
        self.assertEqual(tied["transitions"]["tied"], {"correct": 2, "tied": 0, "wrong": 1})
        self.assertEqual(result["tied_eligible"]["within_pairs"], 4)
        self.assertEqual(
            (result["primary"]["advance_7_pairs"], result["primary"]["nonadvance_7_pairs"]), (3, 1)
        )
        self.assertEqual(result["primary"]["methods"]["always6"]["macro"], 0.5)
        self.assertEqual(result["permutation"]["draws"], 999)
        self.assertEqual(
            result["permutation"]["p_upper"], (result["permutation"]["at_least_observed"] + 1) / 1000
        )

    def test_shuffling_ignores_lower_and_disputed_roles_and_keeps_pairs_fixed(self):
        two = [row("w", "1", 7, 6, "advance"), row("w", "2", 6, 6, "restate")]
        extra = [row("w", "3", 5, 6, "advance"), row("w", "4", 7, 6, "advance", "parallel")]
        original = benchmark(two)["consensus"]["permutation"]
        self.assertEqual(original, benchmark(two + extra)["consensus"]["permutation"])
        self.assertEqual(original["observed_gain"], 0.5)
        self.assertGreater(original["at_least_observed"], 410)
        self.assertLess(original["at_least_observed"], 590)

    def test_missing_comparisons_coverage_and_validation(self):
        z = benchmark([row("a", "1", 7, 7, "advance"), row("b", "1", 6, 6, "restate")])["consensus"]
        self.assertIsNone(z["primary"]["methods"]["current"]["macro"])
        self.assertEqual(z["primary"]["pooled_pairs"], 1)
        self.assertEqual(z["permutation"]["draws"], 0)
        r = row("x", "1", 7, 6, "advance")
        for invalid in ([r, r], [{**r, "coder1": "other"}], [{**r, "score": None}]):
            with self.assertRaises(ValueError):
                benchmark(invalid)
        json.dumps(benchmark([]), allow_nan=False)
