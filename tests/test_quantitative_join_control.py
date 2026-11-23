from array import array
from unittest import TestCase
from unittest.mock import Mock

from audio.synthesize import SAMPLE_RATE
from src.quantitative_join_control import compose_pcm, join_case, summarize
from src.quantitative_onset_transfer import measure
from src.quantitative_report import VOICES


class QuantitativeJoinControlTests(TestCase):
    def test_join_translates_the_second_donor_by_exact_sample_count(self):
        left = array('h', [200] * 2400)
        right = array('h', [0] * 120 + [400] * 2400)
        pcm, right_start, digest = compose_pcm(left, right, SAMPLE_RATE)
        self.assertEqual(right_start, 12000)
        self.assertEqual(pcm[:2400], left)
        self.assertEqual(pcm[2400:right_start], array('h', [0]) * 9600)
        self.assertEqual(pcm[right_start:], right)
        observation = {'pair_id': 'pair', 'work_id': 'right', 'passage_id': 'right', 'voice': VOICES[0],
                       'period': 'sixth-century', 'genre': 'parallel_prose',
                       'recording_id': 'right-1', 'audio_sha256': '1' * 64, 'start_status': 'ok',
                       'reference_start_range_ms': [5, 10], 'model_start_ms': 25}
        model = Mock()
        model.timestamps.return_value = [[0, 80], [540, 580]]
        result = join_case(model, {'pcm': left, 'characters': '故', 'observed': {
            'recording_id': 'left-1', 'audio_sha256': '2' * 64}},
            {'pcm': right, 'characters': '昔', 'observed': observation, 'reference': {'speech_start_sample': 120}},
            -35)
        model.timestamps.assert_called_once_with(pcm, SAMPLE_RATE, '故昔')
        self.assertEqual(result['right_slot_index'], 1)
        self.assertEqual(result['reference_onset_sample'], 12120)
        self.assertEqual(result['reference_start_ms'], 505)
        self.assertEqual(result['reference_start_range_ms'], [505, 510])
        self.assertEqual(result['predictions_ms']['frozen'], 505)
        self.assertEqual(result['context_movement_ms'], 15)
        self.assertEqual(result['composite_pcm16le_sha256'], digest)

    def test_coupled_voice_mask_and_equal_pair_weights(self):
        rows = []
        for work, pair, offsets in (('a', 'P1', (0, 10)), ('b', 'P1', (80, 50)),
                                    ('c', 'P2', (100, 15)), ('d', 'P2', (300, None))):
            for voice, offset in zip(VOICES, offsets):
                row = {'work_id': work, 'pair_id': pair, 'voice': voice, 'duration_ms': 1000,
                       'reference_start_ms': 500, 'reference_start_range_ms': [495, 505],
                       'context_movement_ms': offset, 'model_start_ms': 500 + offset if offset is not None else None}
                rows.append(measure(row, -35))
        stats = summarize(rows)
        self.assertEqual(stats['shared_target_works'], ['a', 'b', 'c'])
        self.assertEqual(stats['shared_standalone_comparison_works'], ['a', 'b', 'c'])
        self.assertEqual(stats['by_voice'][VOICES[0]]['eligible_targets'], 4)
        self.assertEqual(stats['by_voice'][VOICES[0]]['by_method_on_shared_targets']['raw']['pair_weighted_mae_ms'], 70)
        self.assertEqual(stats['by_voice'][VOICES[1]]['by_method_on_shared_targets']['raw']['pair_weighted_mae_ms'], 22.5)
