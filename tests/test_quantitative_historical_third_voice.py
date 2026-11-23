from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from src.quantitative_historical_third_voice import THIRD_VOICE, TIERS, compare_third, measure
from src.quantitative_historical_transfer import VOICES, run_comparisons
from src.stage6_listening import digest
from tests.test_quantitative_historical_transfer import cohort


class HistoricalThirdVoiceTests(unittest.TestCase):
    def test_third_voice_reuses_the_original_controls_and_its_own_holm_family(self):
        fit, test = cohort('fit'), cohort('test')
        previous = run_comparisons(fit, test, draws=29)[VOICES[0]]
        third = compare_third(fit[VOICES[0]], test[VOICES[0]], draws=29)
        for before, after in zip(previous, third):
            self.assertEqual(before['shuffle_seed'], after['shuffle_seed'])
            self.assertEqual(before['null_gains_ms'], after['null_gains_ms'])
        primary = [row for row in third if row['tier'] == TIERS[0]]
        first = min(primary, key=lambda row: row['p_value'])
        self.assertAlmostEqual(first['p_holm'], min(1, 2 * first['p_value']))
        self.assertTrue(all(row['p_holm'] is None for row in third if row['tier'] != TIERS[0]))

    def test_entire_checksum_bound_pcm_supplies_the_duration(self):
        passage = {'passage_id': 'work', 'work_id': 'id', 'author': '張三', 'period': 'sixth-century',
                   'genre': 'parallel_prose', 'pair_id': 'pair', 'text_sha256': 'content',
                   'source_url': 'https://example.org', 'slots': [{'char': '甲'}]}
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / 'audio/example.wav'
            path.parent.mkdir()
            with wave.open(str(path), 'wb') as clip:
                clip.setparams((1, 2, 24000, 0, 'NONE', 'uncompressed'))
                clip.writeframes(bytes(96))
            take = {'audio_path': 'audio/example.wav', 'audio_sha256': digest(path),
                    'duration_s': 0.002, 'speed': 0.9, 'model_revision': 'voice-pin',
                    'recording_id': 'recording'}
            evidence = measure(root, {'work': passage}, {'work': take})[0]
            self.assertEqual(evidence['duration_ms'], 2)
            self.assertEqual(evidence['sample_count'], 48)
            self.assertEqual(evidence['condition'][1], THIRD_VOICE)
            take['audio_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'checksum'):
                measure(root, {'work': passage}, {'work': take})


if __name__ == '__main__':
    unittest.main()
