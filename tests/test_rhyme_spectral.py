from array import array
from importlib.util import find_spec
import math
from pathlib import Path
import unittest

from src.rhyme_spectral import BANDS, analyze_pair, distance, final_shape, mel_weights, summarize


class RhymeSpectralTest(unittest.TestCase):
    def test_provenance_mismatch_rejected_before_loading_audio(self):
        comparison = {'passage_id': 'test', 'takes': {'base': {
            'recording_id': 'example', 'audio_path': 'audio/raw/base.wav',
            'audio_sha256': 'verified',
        }}}
        manifests = {'example': {'passage_id': 'different', 'experimental_ending': {'role': 'base'}}}
        with self.assertRaisesRegex(ValueError, 'manifest disagree'):
            analyze_pair(Path('/unneeded-on-mismatch'), comparison, manifests, {})

    def test_summary_keeps_missing_cases_and_fixed_anchor_separate(self):
        row = {'distance_change': -2, 'anchor_drift': 4, 'supports_intended_direction': True,
               'distance_change_holding_base_anchor_fixed': 1}
        missing = dict.fromkeys(row)
        pairs = [{'intended_change': 'gained', 'bands': dict.fromkeys(BANDS, band_row)}
                 for band_row in (row, missing)]
        summary = summarize(pairs)
        for report in summary.values():
            self.assertEqual(report['supported_pairs'], 1)
            self.assertEqual(report['missing_pairs'], 1)
            self.assertEqual(report['intended_direction_supported'], 1)
            self.assertEqual(report['fixed_anchor_intended_direction_supported'], 0)

    @unittest.skipUnless(find_spec('numpy') and find_spec('scipy'), 'requires pinned Stage 4 array packages')
    def test_spectral_change_separates_signal_shape_from_level_and_missing_support(self):
        rate = 24000
        weights = mel_weights(rate, 1024)
        observation = {'final_start_s': 0, 'final_end_s': 0.25}

        def profile(frequency, amplitude):
            signal = array('h', (round(amplitude * math.sin(2 * math.pi * frequency * i / rate))
                                 for i in range(rate // 4)))
            return final_shape(signal, rate, observation, weights)

        full, quiet, shifted = profile(400, 15000), profile(400, 7000), profile(1000, 7000)
        for band in BANDS:
            self.assertGreaterEqual(full[band][1], 2)
            self.assertLess(distance(full[band][0], quiet[band][0]), 0.1)
            self.assertGreater(distance(full[band][0], shifted[band][0]), 1)
        self.assertEqual(profile(400, 0), dict.fromkeys(BANDS, (None, 0)))
