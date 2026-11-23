import unittest

from src.quantitative_pattern_endings import arm, forecasts, metrics, screen, signals


class EndingChallengeTests(unittest.TestCase):
    def test_background_variation_and_new_wording_are_separate(self):
        f = signals(list(map(arm, ["其聲清", "其葉青", "其花晚黃"])))
        self.assertTrue(f["rhythm"])
        self.assertFalse(f["wording"])
        g = signals(list(map(arm, ["其花美", "其枝青", "獨根深"])))
        self.assertFalse(g["rhythm"])
        self.assertTrue(g["wording"])
        self.assertEqual(g["new_cue"], "獨")
        self.assertFalse(signals(list(map(arm, ["山青", "水明朗", "風清"])))["rhythm"])

    def test_nonconsecutive_arms_cannot_create_a_terminal_change(self):
        row = {"id": "1", "work_id": "w", "section": "s", "text": "其心，其志，歎曰，其言。"}
        run = {
            "work_id": "w",
            "section": "s",
            "target_id": "1",
            "explanation": "同構",
            "boundary": "句終",
            "members": [{"id": "1", "quote": q} for q in ("其心", "其志", "其言")],
        }
        with self.assertRaisesRegex(ValueError, "intervening"):
            screen([row], [run], [])

    def test_no_seven_six_contrast_is_undefined_and_constant_receives_half(self):
        def sample(w, s, v):
            return {
                "work_id": w,
                "score": s,
                "rhythm": False,
                "wording": False,
                "predictions": forecasts(v, False, False),
            }

        rows = [sample("a", 7, 6.6), sample("a", 6, 6.3), sample("b", 5, 6.9)]
        result = metrics(rows)
        self.assertEqual(result["mixed_works"], ["a"])
        self.assertEqual(result["methods"]["current"]["within_work_auc"], 1.0)
        self.assertEqual(result["methods"]["always6"]["within_work_auc"], 0.5)
        self.assertIsNone(metrics(rows[::2])["methods"]["always6"]["within_work_auc"])
