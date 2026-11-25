import unittest

from src.yu_review_transfer import compare, prediction, signals, summarize


class YuReviewTransferTests(unittest.TestCase):
    def test_real_pace_change_and_equal_length_controls(self):
        four = signals("朝發，行過蒼茫古道；暮歸，重看隱約青山。")
        self.assertTrue(four["repeated_pace"])
        self.assertEqual(four["lengths"], [2, 6, 2, 6])
        self.assertEqual(four["route"], "four_phrases")
        same = signals("清風，明月；青山，白石。")
        self.assertTrue(same["balanced"])
        self.assertFalse(same["repeated_pace"])
        self.assertFalse(signals("朝發；行過蒼茫古道，暮歸，重看隱約青山。")["balanced"])

    def test_hinge_position_and_subminimum_coda(self):
        example = signals("登臺而遠望，對月而長吟。")
        self.assertEqual(example["route"], "shared_hinge")
        self.assertFalse(signals("登臺而遠望，對月以長吟。")["repeated_pace"])
        self.assertFalse(signals("登臺而望，對月而吟。")["repeated_pace"])
        self.assertEqual(prediction(6.52, True), 7)

    def test_pair_denominator_and_absent_grade(self):
        rows = [dict(work_id="a", grade=g, score=p) for g, p in [(7, 6), (6, 6), (6, 5)]]
        self.assertEqual(compare(rows, "score")["ordering"], 0.75)
        extra = dict(work_id="b", grade=4, score=6.5)
        result = summarize(rows + [extra], "score")
        self.assertEqual(result["ordering"], 0.75)
        self.assertIsNone(result["leave_one_out"]["a"])
        self.assertEqual((result["caught"], result["false_on_sixes"], result["false_on_lower"]),
                         (0, 0, 1))
