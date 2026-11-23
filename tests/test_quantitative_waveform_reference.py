import unittest

from src.quantitative_waveform_reference import waveform_reference


class WaveformReferenceTests(unittest.TestCase):
    def test_stable_activity_and_quiet_edges_follow_exact_pcm_padding(self):
        samples = ([0] * 50 + [2000] * 100 + [0] * 120 + [-2000] * 100 + [0] * 50)
        base = waveform_reference(samples, 1000)
        shifted = waveform_reference([0] * 80 + samples + [0] * 80, 1000)
        self.assertEqual(base['status'], 'ok')
        self.assertEqual((base['speech_start_ms'], base['speech_end_ms']), (50, 370))
        self.assertEqual((shifted['speech_start_ms'], shifted['speech_end_ms']), (130, 450))
        self.assertEqual(len(base['pauses']), 1)
        self.assertEqual((base['pauses'][0]['start_ms'], base['pauses'][0]['end_ms']), (150, 270))
        self.assertEqual((shifted['pauses'][0]['start_ms'], shifted['pauses'][0]['end_ms']), (230, 350))
        self.assertEqual(base['speech_start_range_ms'], [50, 50])

    def test_reports_sensitivity_ranges_and_rejects_unstable_quiet_edges(self):
        def measure(shoulder):
            return waveform_reference([0] * 50 + [2000] * 100 + [75] * shoulder + [0] * 120
                                      + [75] * shoulder + [2000] * 100 + [0] * 50, 1000)
        stable = measure(10)
        self.assertEqual(len(stable['pauses']), 1)
        self.assertEqual(stable['pauses'][0]['start_range_ms'], [150, 160])
        self.assertEqual(stable['pauses'][0]['end_range_ms'], [280, 290])
        unstable = measure(25)
        self.assertEqual(unstable['quiet_candidates'], 1)
        self.assertEqual(unstable['quiet_candidate_rejections']['threshold_sensitive'], 1)
        self.assertEqual(unstable['pauses'], [])

    def test_quiet_without_nearby_strong_activity_is_unresolved(self):
        samples = [0] * 50 + [2000] * 80 + [200] * 100 + [0] * 120 + [2000] * 100 + [0] * 50
        result = waveform_reference(samples, 1000)
        self.assertEqual(result['quiet_candidates'], 1)
        self.assertEqual(result['quiet_candidate_rejections']['insufficient_adjacent_activity'], 1)
        self.assertEqual(result['pauses'], [])
        silent = waveform_reference([0] * 500, 1000)
        self.assertEqual(silent['status'], 'no_clear_activity')
        self.assertIsNone(silent['speech_start_ms'])
        self.assertIsNone(silent['speech_end_ms'])
