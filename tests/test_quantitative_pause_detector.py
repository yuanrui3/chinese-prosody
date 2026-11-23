import unittest

from src.quantitative_pause_detector import detect_relative


class RelativePauseDetectorTests(unittest.TestCase):
    def test_guard_edges_survive_unclipped_gain_change(self):
        samples = [0] * 40 + [2400] * 100 + [0] * 150 + [-2400] * 100 + [0] * 40
        original = detect_relative(samples, 1000)
        self.assertEqual(len(original['pauses']), 1)
        pause = original['pauses'][0]
        self.assertEqual((pause['start_sample'], pause['end_sample']), (140, 290))
        self.assertEqual(pause['end_range_ms'], [290, 290])
        self.assertTrue(pause['resumption_eligible'])
        for gain in (0.25, 2):
            scaled = detect_relative([int(value * gain) for value in samples], 1000)
            self.assertEqual(scaled['pauses'], original['pauses'])

    def test_counts_interruptible_activity_on_each_side(self):
        speech = ([2500] * 10 + [200] * 10) * 4
        result = detect_relative([0] * 50 + speech + [0] * 120 + speech + [0] * 50, 1000)
        self.assertEqual(len(result['pauses']), 1)
        self.assertEqual((result['pauses'][0]['start_ms'], result['pauses'][0]['end_ms']), (130, 250))

    def test_keeps_core_when_resumption_is_threshold_sensitive(self):
        samples = [0] * 40 + [2000] * 80 + [0] * 120 + [80] * 60 + [2000] * 80 + [0] * 40
        pause, = detect_relative(samples, 1000)['pauses']
        self.assertEqual((pause['start_ms'], pause['end_ms']), (120, 240))
        self.assertEqual(pause['end_range_ms'], [240, 300])
        self.assertFalse(pause['resumption_eligible'])

    def test_absent_adjusted_threshold_abstains_at_resumption(self):
        samples = [0] * 40 + [2000] * 80 + [40] * 120 + [2000] * 80 + [0] * 40
        pause, = detect_relative(samples, 1000)['pauses']
        self.assertEqual(pause['end_range_ms'], [240, 240])
        self.assertFalse(pause['resumption_eligible'])

    def test_insufficient_nearby_activity_and_zero_reference(self):
        samples = [2000] * 120 + [200] * 200 + [0] * 120 + [2000] * 100
        result = detect_relative(samples, 1000)
        self.assertEqual(result['quiet_candidates'], 1)
        self.assertEqual(result['quiet_candidate_rejections']['insufficient_adjacent_activity'], 1)
        self.assertEqual(result['pauses'], [])
        self.assertEqual(detect_relative([0] * 500, 1000)['status'], 'no_clear_activity')
