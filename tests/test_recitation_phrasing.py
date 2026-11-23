from array import array
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest

from src.minimal_pitch_control import write_wav
from src.recitation_phrasing import AUDIO, render
from src.recitation_phrasing_analysis import measurement, shuffle_summary, verify_carrier
from src.stage6_listening import digest


class RecitationPhrasingTests(unittest.TestCase):
    def test_rendered_pair_recovers_pauses_from_waveform(self):
        rate = 1000
        rng = Random(44)
        samples = array('h', [100]) * rate
        starts = [100, 300, 500, 700]
        for start in starts:
            samples[start:start + 150] = array('h', (rng.randint(-14000, 14000) for _ in range(150)))
        with TemporaryDirectory() as temp:
            source_root = Path(temp).resolve() / 'source'
            experiment = Path(temp).resolve() / 'experiment'
            (experiment / AUDIO).mkdir(parents=True)
            filename = Path('audio/raw/fixture.wav')
            source_path = source_root / filename
            source_path.parent.mkdir(parents=True)
            write_wav(source_path, samples, rate)
            source = {'root': str(source_root), 'audio_path': str(filename), 'audio_sha256': digest(source_path),
                      'recording_id': 'fixture', 'sample_rate': rate}
            pair = {'source': source, 'passage_id': 'fixture', 'pair_id': 'fixture-0',
                    'clause_text': '人間何世', 'clause_index': 0, 'slot_indices': [0, 1, 2, 3],
                    'syllables': [{'slot_index': i, 'start_s': start / rate, 'end_s': (start + 150) / rate}
                                  for i, start in enumerate(starts)],
                    'cuts': [{'method': 'shared_taper', 'source_sample_index': sample} for sample in (275, 475)]}
            pair['sham'], pair['variants'] = render(experiment, source, samples, rate, pair)
            result = measurement(experiment, pair)
        self.assertTrue(result['waveform_anchors_support_placement'])
        self.assertEqual(result['waveform_anchor_delay_ms'], {'two_two': [0, 80, 0], 'one_one_two': [40, 40, 0]})
        self.assertEqual(result['common_carrier']['taper_window_total_ms'], 20)
        self.assertGreater(result['common_carrier']['removed_source_energy_pct'], 0)
        for level in result['quiet_runs_by_dbfs'].values():
            self.assertTrue(level['supports_redistribution'])
            self.assertEqual(level['third_gap_difference_ms'], 0)

    def test_sham_validation_rejects_changes_outside_windows(self):
        original = array('h', [10, 10, 10, 10])
        modified = array('h', [1, 10, 10, 10])
        with self.assertRaisesRegex(ValueError, 'outside'):
            verify_carrier(original, modified, [], 1000)

    def test_label_swap_blocks_multiple_clauses_from_the_same_work(self):
        summary = shuffle_summary({'A': [40, 80], 'B': [60]})
        self.assertEqual(summary['swaps'], 4)
        self.assertEqual(summary['observed_mean_contrast_ms'], 60)
        self.assertEqual(summary['upper_tail_fraction'], 0.25)


if __name__ == '__main__':
    unittest.main()
