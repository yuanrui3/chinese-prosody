import json
from pathlib import Path
import unittest

from src.critical_preferences import METHODS, compare, fit_length, index_packet, summarize


class CriticalPreferencesTest(unittest.TestCase):
    def test_manifest_and_no_reference_in_unranked_pair(self):
        path = Path(__file__).resolve().parents[1] / "research/critic-variants.json"
        packet = json.loads(path.read_text())
        versions = index_packet(packet)
        predictions = {k: dict.fromkeys(METHODS, 6) for k in versions}
        paired = compare(packet, predictions)
        for item in paired:
            expected = {} if item["preferred"] is None else dict.fromkeys(METHODS, 0.5)
            self.assertEqual(item["pair_credit"], expected)
        self.assertIsNone(summarize([])["current"]["credit"])

    def test_family_weighting_and_blind_label_reversals(self):
        cases = [dict(family=k, pair_credit=dict.fromkeys(METHODS, x))
                 for k, x in [("first", 1), ("first", 1), ("second", 0)]]
        result = summarize(cases)["current"]
        self.assertEqual(result["families"], 2)
        self.assertEqual(result["credit"], 0.5)
        self.assertEqual(result["label_flip_upper_tail"], 0.75)

    def test_length_uses_only_han_characters(self):
        rows = [dict(text="甲。", score=3), dict(text="「乙丙？」", score=5)]
        self.assertEqual(fit_length(rows), (1, 2))
