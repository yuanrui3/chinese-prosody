from itertools import combinations
from random import Random
from statistics import mean
import unittest

from src.quantitative_clause_structure import expected_share, label_swap, randomized_share, recover_witness


class ClauseStructureTests(unittest.TestCase):
    def test_analytic_expectation_matches_all_cut_positions(self):
        for total, clauses in ((4, 1), (10, 3), (10, 5), (3, 3)):
            shares = []
            for internal in combinations(range(1, total), clauses - 1):
                cuts = (0, *internal, total)
                shares.append(sum(right - left in (4, 6) for left, right in zip(cuts, cuts[1:])) / clauses)
            self.assertAlmostEqual(expected_share(total, clauses), mean(shares))
        self.assertEqual(randomized_share(6, 1, Random(31)), 1)
        self.assertEqual(randomized_share(6, 6, Random(31)), 0)

    def test_exact_one_sided_comparison_keeps_tied_pairs(self):
        out = label_swap([0.75, 0.30, 0, 0.17])
        self.assertEqual(out, {'assignments': 16, 'one_sided_p': 0.125, 'smallest_attainable_p': 0.125})

    def test_remove_only_declared_punctuation_including_terminal_marks(self):
        passage = {'text': '甲，乙；丙丁。', 'start_anchor': '甲乙', 'end_anchor': '丙丁', 'witness_codepoints': 5,
                   'insert_punctuation_after': {'1': '，', '5': '。'}}
        self.assertEqual(recover_witness(passage), '甲乙；丙丁')
        passage['insert_punctuation_after']['1'] = '、'
        with self.assertRaisesRegex(ValueError, 'Declared punctuation'):
            recover_witness(passage)


if __name__ == '__main__':
    unittest.main()
