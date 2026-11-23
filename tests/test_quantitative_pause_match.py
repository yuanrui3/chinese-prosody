import unittest

from src.quantitative_pause_match import match_pause


class PauseMatchTests(unittest.TestCase):
    pause = {'start_range_ms': [100, 105], 'end_range_ms': [245, 255]}

    def test_checks_every_position_before_using_the_clause_boundary_label(self):
        starts = {0: 40, 1: 240, 2: 401}
        chosen = match_pause(self.pause, starts, {2})
        self.assertEqual((chosen['status'], chosen['right_slot']), ('within_clause', 1))
        self.assertEqual(match_pause(self.pause, starts, {1})['status'], 'clause_boundary')

    def test_requires_prior_position_before_the_entire_quiet_region(self):
        starts = {0: 40, 1: 150, 2: 250}
        chosen = match_pause(self.pause, starts, {2})
        self.assertEqual((chosen['status'], chosen['right_slot']), ('unmatched', None))

    def test_uses_worst_threshold_edge_and_abstains_on_near_tie(self):
        self.assertEqual(match_pause(self.pause, {0: 30, 1: 310}, {1})['status'], 'unmatched')
        short = {'start_range_ms': [230, 235], 'end_range_ms': [245, 255]}
        chosen = match_pause(short, {0: 30, 1: 225, 2: 245}, {2})
        self.assertEqual((chosen['status'], chosen['right_slot']), ('ambiguous', None))
