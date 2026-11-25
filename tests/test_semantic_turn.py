from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.semantic_turn_pairs import prepare, select_pair
from src.semantic_turn_quotation_audit import quoted_sentences
from src.semantic_turn_test import audit_packet, lexical
from src.yu_review_transfer import read, write


class SemanticTurnTests(unittest.TestCase):
    def test_embedded_quotation_extends_over_sentence_boundary(self):
        rows = [dict(work_id="W", id=str(i), text=t) for i, t in enumerate(
            ["臣聞。", "書曰：「若是。", "既至。」", "臣請行。"])]
        self.assertEqual(quoted_sentences(rows), {"1", "2"})

    def test_motivating_correspondence_has_priority(self):
        chosen = select_pair("斬將搴旗，出於料外；堅城便地，盡落彀中。")
        self.assertEqual((chosen["i"], chosen["j"]), (1, 3))
        self.assertEqual(chosen["first"], "出於料外")
        self.assertTrue(lexical(chosen["first"], chosen["second"]))

    def test_last_adjacent_eligible_pair_and_equal_repeats(self):
        self.assertIsNone(select_pair("山高，水長。"))
        self.assertIsNone(select_pair("雨初晴，雨初晴。"))
        found = select_pair("渡江來，行數里，望山前，荒村落葉。")
        self.assertEqual((found["first"], found["second"]), ("行數里", "望山前"))
        self.assertFalse(lexical(found["first"], found["second"]))

    def test_private_key_and_same_work_width_control(self):
        with TemporaryDirectory() as temp:
            run = Path(temp)
            (run / "inputs").mkdir()
            (run / "private").mkdir()
            rows = [dict(id="T", work_id="W", paragraph="P", target=True, text="雨初晴，客方歸。"),
                    dict(id="D", work_id="W", paragraph="P", target=False, text="潮已落。")]
            write(run / "inputs/corpus.json", rows)
            prepare(run)
            p = read(run / "inputs/pair-packet.json")
            self.assertEqual(p["foils"][0]["marked"], "【甲：雨初晴】，【乙：潮已落】。")
            audit_packet(run)
            public = read(run / "inputs/audit-packet.json")
            self.assertEqual({frozenset(r) for r in public}, {frozenset(("id", "marked"))})
            self.assertEqual(len(read(run / "private/audit-key.json")), 2)
