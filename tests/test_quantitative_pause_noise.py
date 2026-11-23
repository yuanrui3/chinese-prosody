from array import array
from statistics import mean
import unittest

from src.quantitative_pause_noise import (
    SAMPLE_RATE, add_bounded_noise, compound, evaluate, noise_profile, noise_seed, summarize,
)


class PauseNoiseTests(unittest.TestCase):
    def test_noise_stream_is_centered_and_deterministic(self):
        seed = noise_seed('0' * 64)
        first = noise_profile(64, seed)
        self.assertEqual(first, noise_profile(64, seed))
        self.assertNotEqual(first, noise_profile(64, noise_seed('1' * 64)))
        self.assertAlmostEqual(mean(first), 0)

    def test_only_noise_is_limited_and_subtracting_it_restores_pcm(self):
        original = array('h', [-32768, 32767, 100, -100])
        mixed, applied, limited = add_bounded_noise(original, [-10, 10, -30, 40])
        self.assertEqual(limited, 2)
        self.assertEqual(mixed.tolist(), [-32768, 32767, 70, -60])
        self.assertEqual([value - noise for value, noise in zip(mixed, applied)], original.tolist())
        self.assertEqual(compound(mixed, 2, array('h', [5, 10])).tolist(),
                         [-32768, 32767, 5, 10, 70, -60])

    def test_treatments_recover_one_paired_carrier_and_report_guard_power(self):
        signal = array('h', [3000, -3000] * (SAMPLE_RATE // 2))
        case = evaluate(signal, SAMPLE_RATE, '0' * 64)
        self.assertEqual(case['status'], 'scored')
        self.assertEqual(len(case['trials']), 15)
        for level in (None, -36, -24):
            rows = [row for row in case['trials'] if row['noise_target_db_relative_to_clean_p90'] == level]
            self.assertEqual(len({row['noisy_carrier_pcm16le_sha256'] for row in rows}), 1)
            self.assertTrue(all(row['exact_noisy_carrier_recovery'] for row in rows))
            long = next(row for row in rows if row['guard_ms'] == 400)
            fractions = long['guard_threshold_check']['quiet_fraction_of_guard_frames']
            self.assertEqual(long['guard_threshold_check']['complete_guard_frames'], 80)
            if level is None:
                self.assertEqual(fractions, {'strict': 1.0, 'relative': 1.0})
                self.assertIsNone(long['realized_guard_noise_db_relative_to_clean_p90'])
            else:
                self.assertAlmostEqual(long['realized_guard_noise_db_relative_to_clean_p90'], level, delta=1)
                self.assertAlmostEqual(long['realized_carrier_noise_db_relative_to_clean_p90'], level, delta=1)
                self.assertGreater(long['realized_guard_noise_pcm16_power'], 0)
        levels = summarize([case])['by_level']
        self.assertEqual(levels['clean']['by_guard']['120']['relative']['hits'], 1)
        self.assertEqual(levels['clean']['by_guard']['60']['relative']['false_pauses'], 0)


if __name__ == '__main__':
    unittest.main()
