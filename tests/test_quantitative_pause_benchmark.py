import unittest

from src.quantitative_pause_benchmark import anchored_edges, guard_pause, score_case


class PauseBenchmarkTests(unittest.TestCase):
    def test_known_guard_translates_the_independent_right_onset(self):
        reference = {'speech_start_range_ms': [15, 20]}
        self.assertEqual(anchored_edges(reference, 2400, 12000),
                         {'start_range_ms': [100, 100], 'end_range_ms': [515, 520]})
        self.assertIsNone(anchored_edges({'speech_start_range_ms': None}, 2400, 12000))

    def test_guard_selection_requires_covering_the_exact_zeros(self):
        other = {'start_sample': 140, 'end_sample': 1500}
        guard = {'start_sample': 4110, 'end_sample': 13500}
        reference = {'pauses': [other, guard]}
        self.assertIs(guard_pause(reference, 4000, 13600), guard)
        self.assertIsNone(guard_pause(reference, 3900, 13600))
        self.assertIsNone(guard_pause(reference, 4000, 13700))

    def test_mask_keeps_ordinal_search_and_wrong_clauses_are_counted(self):
        pause = {'start_range_ms': [110, 120], 'end_range_ms': [525, 535]}
        starts = {0: 0, 1: 80, 2: 530, 3: 690}
        match = score_case(pause, starts, {2, 3}, 2)
        self.assertEqual(match['outcome'], 'correct')
        self.assertEqual(match['masked']['status'], 'within_clause')
        self.assertEqual(match['masked']['right_slot'], 2)
        wrong = score_case(pause, starts, {2, 3}, 3)
        self.assertEqual(wrong['outcome'], 'wrong_clause')
        self.assertEqual(wrong['masked']['status'], 'clause_boundary')

    def test_detection_and_alignment_failures_stay_separate(self):
        pause = {'start_range_ms': [110, 120], 'end_range_ms': [525, 535]}
        self.assertEqual(score_case(None, {0: 0}, {2}, 2)['outcome'], 'undetected')
        self.assertEqual(score_case(pause, {}, {2}, 2)['outcome'], 'unaligned')
