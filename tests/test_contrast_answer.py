import unittest

from src.contrast_answer_sources import PUNCT, anthology, prose_lines
from src.contrast_answer_test import choose


class ContrastAnswerTests(unittest.TestCase):
    def test_index_keeps_prose_volumes_and_resolves_display_titles(self):
        body = "==卷一 賦==\n#[[賦]]\n==卷二　詔 敕==\n#[[舉賢詔 (元宏)|舉賢詔]]\n==卷十 銘==\n#[[銘]]"
        self.assertEqual(anthology(body), {"舉賢詔 (元宏)": "詔 敕"})

    def test_clean_paragraphs_stay_separate_and_verse_coda_stops(self):
        raw = "{{header\n|notes={{nested}}\n}}\n天地有時。\n字{{variant}}未詳。\n今昔異勢；誰知其故？」\n亂曰：非本文。\n其後不收。"
        paras = prose_lines(raw)
        self.assertEqual(paras, ["天地有時。", "今昔異勢；誰知其故？」"])
        self.assertEqual(PUNCT.findall(paras[-1]), ["今昔異勢；", "誰知其故？」"])

    def test_group_sampling_never_creates_singletons(self):
        groups = {("a", "1"): list(range(20)), ("b", "2"): [20, 21], ("c", "2"): [22, 23, 24]}
        selected = set(choose(groups, 10))
        self.assertEqual(selected, set(choose(dict(reversed(list(groups.items()))), 10)))
        self.assertLessEqual(len(selected), 10)
        for ids in groups.values():
            self.assertIn(len(selected.intersection(ids)), {0, min(8, len(ids))})
