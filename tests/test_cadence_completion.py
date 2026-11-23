import unittest

from src.cadence_completion import PROBES, paragraphs, profile, signals


class CadenceCompletionTests(unittest.TestCase):
    def test_motivating_line_has_two_separate_anchors(self):
        case = PROBES[0]
        result = signals(case["prior"], case["target"])
        self.assertTrue(result["anchored"])
        self.assertIn(("無", "有"), result["earlier"])
        self.assertIn(("之", "之"), result["closing"])

    def test_controls_do_not_reward_count_or_copy(self):
        results = [signals(case["prior"], case["target"]) for case in PROBES[1:]]
        self.assertEqual([r["shape"] for r in results], [True, True, True])
        self.assertEqual([r["anchored"] for r in results], [True, False, False])

    def test_single_correspondence_cannot_fill_both_slots(self):
        result = signals("山川相接，聞江上之風。", "物色尤奇，照陌畔之花。")
        self.assertTrue(result["shape"])
        self.assertFalse(result["anchored"])
        self.assertNotEqual(profile("春風吹柳，初見溪邊之綠。"), profile("春風吹，柳影遍溪邊之岸。"))

    def test_verse_coda_exclusion_preserves_preceding_prose(self):
        a = "春風入戶，秋雨敲桐。清波映月，落葉隨風。今夜如何？"
        self.assertEqual(paragraphs("{{Header|author=甲}}\n"+a+"\n銘曰：\n"+a), [a])
