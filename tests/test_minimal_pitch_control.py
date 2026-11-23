from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from src.minimal_pitch_control import pitch_readout, splice, voiced_core, write_wav


class MinimalPitchControlTest(unittest.TestCase):
    def test_faded_splice_preserves_duration_and_non_target_samples_on_disk(self):
        source = array('h', range(10))
        edited = splice(source, [0.5] * len(source), 2, 8, 2)
        self.assertEqual(edited[:3], source[:3])
        self.assertEqual(edited[7:], source[7:])
        self.assertNotEqual(edited[3:7], source[3:7])
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'test.wav'
            write_wav(path, edited, 24000)
            with wave.open(str(path), 'rb') as wav:
                self.assertEqual(wav.getnframes(), len(source))
                self.assertEqual(wav.getframerate(), 24000)

    def test_pitch_readout_needs_one_supported_estimate_in_each_band(self):
        points = [(0.2, 0.02, 120), (0.3, 0.03, 120), (0.5, 0.05, 108),
                  (0.6, 0.06, 90), (0.7, 0.07, 90)]
        self.assertLess(pitch_readout(points)['late_minus_early_st'], -4)
        self.assertIsNone(pitch_readout(points[:-1])['late_minus_early_st'])

    def test_voiced_core_selects_contiguous_frames_inside_the_target(self):
        points = [(i / 100, i / 100, 120) for i in (*range(10, 20), *range(23, 29))]
        self.assertEqual(voiced_core(points, 24000, 2304, 10000), (2304, 4680))
        self.assertIsNone(voiced_core(points[-6:], 24000, 0, 10000))
