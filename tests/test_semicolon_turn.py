import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from src.semicolon_turn_sources import closing_pair, eligible_sentences, variant_families
from src.semicolon_turn_sensitivity import strict_shape
from src.semicolon_turn_ratings import keys
from src.semicolon_turn_test import ordering_changes
from src.yu_review_transfer import write


class SemicolonTurnTests(unittest.TestCase):
    def test_only_corresponding_final_phrases_with_lead_ins(self):
        example = "斬將搴旗，出於料外；堅城便地，盡落彀中。"
        self.assertEqual(closing_pair(example)["second"], "盡落彀中")
        for sentence in ("斬將搴旗，出於料外，堅城便地，盡落彀中。",
                         "斬將搴旗，出於料外；盡落彀中。",
                         "出於料外；堅城便地，盡落彀中。",
                         "斬將搴旗，出於料外；堅城便地，落彀中。",
                         "斬將搴旗，料外；堅城便地，彀中。",
                         "斬將搴旗，出於料外；堅城便地；盡落彀中。"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(closing_pair(sentence))

    def test_skip_quoted_repeated_and_previously_used_text(self):
        sentence = "斬將搴旗，出於料外；堅城便地，盡落彀中。"
        self.assertEqual(eligible_sentences([[sentence]], set()), [0])
        self.assertEqual(eligible_sentences([[sentence, sentence]], set()), [])
        self.assertEqual(eligible_sentences([["人云：「山高。", sentence + "」"]], set()), [])
        self.assertEqual(eligible_sentences([[sentence]], {"斬將搴旗出於料外堅城便地盡落彀中"}), [])

    def test_transitions_respect_the_work_and_reference_grade(self):
        rows = [dict(work_id=w, grade=g, current=b, qwen_turn=c)
                for w, g, b, c in (("A", 7, 6, 6.75), ("A", 6, 6, 6),
                                    ("B", 7, 5, 5), ("C", 5, 6, 6.75))]
        self.assertEqual(ordering_changes(rows), {"tie_to_win": 1})

    def test_do_not_mistake_an_enumeration_suffix_for_a_whole_closing(self):
        self.assertEqual(strict_shape(dict(text="故黃鳥白麟，載稱姬、漢之日；玄圭黑玉，式昭禹、湯之代。",
                                           first="漢之日", second="湯之代")), (False, False))
        self.assertEqual(strict_shape(dict(text="斬將搴旗，出於料外；堅城便地，盡落彀中。",
                                           first="出於料外", second="盡落彀中")), (True, True))

    def test_previous_authors_match_across_character_forms(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "variants.zip"
            with ZipFile(path, "w") as z:
                z.writestr("Unihan_Variants.txt", "# Unicode 17.0.0\nU+97E9\tkTraditionalVariant\tU+97D3\n"
                                                 "U+97D3\tkSimplifiedVariant\tU+97E9\n")
            table = variant_families(path)
            self.assertEqual("韩愈".translate(table), "韓愈".translate(table))

    def test_grade_transfer_depends_on_edition_and_neighbor_text(self):
        with TemporaryDirectory() as folder:
            run = Path(folder)
            (run / "inputs").mkdir()
            source = run / "inputs/sources.json"
            corpus = run / "inputs/corpus.json"
            work = {"work_id": "A", "revision": 100}
            rows = [dict(id="untested", work_id="A", paragraph="P", target=False, text="昨雨。"),
                    dict(id="rated", work_id="A", paragraph="P", target=True, text="今晴。")]
            write(source, {"works": [work]})
            write(corpus, rows)
            old = keys(run)["rated"]
            write(source, {"works": [dict(work, revision=101)]})
            self.assertNotEqual(old, keys(run)["rated"])
            write(source, {"works": [work]})
            write(corpus, [dict(rows[0], text="昨雪。"), rows[1]])
            self.assertNotEqual(old, keys(run)["rated"])
