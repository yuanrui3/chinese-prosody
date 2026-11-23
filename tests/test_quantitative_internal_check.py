import unittest

from src.quantitative_internal_check import generator_windows, label_pauses, pause_edges


class GeneratorPauseLabelTests(unittest.TestCase):
    def test_generator_gap_must_be_the_pinned_punctuation_tokens(self):
        slots = [{'slot_index': 0, 'clause_index': 0, 'marks_after': '，', 'char': '甲'},
                 {'slot_index': 1, 'clause_index': 1, 'marks_after': '。', 'char': '乙'}]
        identity = {'recording_id': 'take', 'text_sha256': 'text', 'audio_sha256': 'audio', 'model_revision': 'model'}
        take = {**identity, 'intended_model_phonemes': 'a,b'}
        draft = {**identity, 'sample_count': 13_200, 'frame_samples': 600, 'token_frames': [2, 4, 10, 4, 2],
                 'slot_spans_samples': [[1_200, 3_600], [9_600, 12_000]]}
        self.assertEqual(generator_windows(draft, {'slots': slots}, take, 13_200), [
            {'after_slot': 0, 'start_sample': 3_600, 'end_sample': 9_600, 'marks': '，',
             'left_char': '甲', 'right_char': '乙'}])
        with self.assertRaises(ValueError):
            generator_windows(draft, {'slots': slots}, {**take, 'intended_model_phonemes': 'a;b'}, 13_200)

    def test_reference_run_must_have_the_same_unique_label_across_origins(self):
        window = {'after_slot': 1, 'start_sample': 3_600, 'end_sample': 9_600}
        reference = {'sample_rate': 24_000, 'internal_pause_count_matches': False, 'pauses': [
            {'start_ms': 180, 'end_ms': 320, 'start_range_ms': [175, 185], 'end_range_ms': [315, 325]},
            {'start_ms': 345, 'end_ms': 465, 'start_range_ms': [345, 345], 'end_range_ms': [465, 465]}]}
        first, second = label_pauses(reference, [window])
        self.assertEqual(first['after_slot'], 1)
        self.assertEqual(second['candidates_by_origin'], [[], [], [1]])
        self.assertIsNone(second['after_slot'])
        overlap = {**window, 'after_slot': 2}
        self.assertIsNone(label_pauses(reference, [window, overlap])[0]['after_slot'])

    def test_scoring_uses_the_pcm_edges_and_abstains_for_missing_phones(self):
        labels = [{'after_slot': 2, 'start_ms': 200, 'end_ms': 310,
                   'start_range_ms': [195, 205], 'end_range_ms': [305, 315]},
                  {'after_slot': None, 'start_ms': 400, 'end_ms': 550}]
        linked = {2: {'end_s': 0.190}}
        secondary = {2: {'end_s': 0.250}, 3: {'start_s': 0.320}}
        left, right = pause_edges({'recording_id': 'take'}, labels, linked, secondary)
        self.assertEqual((left['edge_ms'], left['charsiu_ms'], left['funasr_ms']), (200, 190, 250))
        self.assertEqual((right['edge_ms'], right['charsiu_ms'], right['funasr_ms']), (310, None, 320))
