import unittest

from src.quantitative_noise_aware_detector import detect_noise_aware
from src.quantitative_pause_detector import detect_relative


class NoiseAwarePauseDetectorTests(unittest.TestCase):
    def test_silent_background_preserves_relative_detector_edges(self):
        samples = [0] * 40 + [2400] * 100 + [0] * 150 + [-2400] * 100 + [0] * 40
        baseline = detect_relative(samples, 1000)
        adaptive = detect_noise_aware(samples, 1000)
        self.assertEqual(adaptive['mode'], 'relative_fallback')
        self.assertEqual(adaptive['pauses'], baseline['pauses'])

    def test_recovers_the_edges_of_a_noisy_pause(self):
        rate = 24_000
        frame = rate // 200
        leading = [2400] * (20 * frame)
        noise = [value for value in [120, 145, 110, 140, 130] * 6 for _ in range(frame)]
        noise[12 * frame:13 * frame] = [500] * frame
        samples = leading + noise + leading
        self.assertEqual(detect_relative(samples, rate)['pauses'], [])
        detected = detect_noise_aware(samples, rate)
        self.assertEqual(detected['mode'], 'noise_aware')
        pause, = detected['pauses']
        self.assertEqual((pause['start_sample'], pause['end_sample']), (20 * frame, 50 * frame))
        self.assertEqual(pause['end_range_ms'], [250, 250])
        self.assertTrue(pause['resumption_eligible'])
        self.assertEqual(detect_noise_aware([value // 2 for value in samples], rate)['pauses'], [pause])

    def test_unstable_resumption_retains_core_but_withholds_timing(self):
        detected = detect_noise_aware([2400] * 100 + [120] * 150 + [220] * 65 + [2400] * 100, 1000)
        pause, = detected['pauses']
        self.assertEqual(pause['end_range_ms'], [250, 315])
        self.assertFalse(pause['resumption_eligible'])

    def test_short_pause_and_weak_energy_contrast_abstain(self):
        short = [2400] * 160 + [120] * 60 + [2400] * 160
        self.assertEqual(detect_noise_aware(short, 1000)['pauses'], [])
        low_contrast = [200] * 160 + [120] * 150 + [200] * 160
        rejected = detect_noise_aware(low_contrast, 1000)
        self.assertEqual(rejected['status'], 'insufficient_level_above_background')
        self.assertEqual(rejected['pauses'], [])
