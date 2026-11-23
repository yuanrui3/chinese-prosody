import unittest

from src.quantitative_offset import compare, observe


class WaveformOffsetTests(unittest.TestCase):
    def test_fits_exclude_both_voices_of_the_test_work(self):
        landmarks = [
            {'work_id': work, 'voice': voice, 'edge_ms': 100, 'clip_ms': 1000,
             'reference_range_ms': [97, 103], 'kind': 'clip_start',
             'funasr_ms': 100 + error, 'charsiu_ms': None}
            for work, errors in (('held', (90, 130)), ('train-a', (10, 30)), ('train-b', (20, 40)))
            for voice, error in zip(('male', 'female'), errors)
        ]
        scores, folds = compare(landmarks, ('male', 'female'))
        held = {row['voice']: row for row in folds if row['work_id'] == 'held' and row['landmark'] == 'clip'}
        self.assertEqual(held['male']['pooled_ms'], -25)
        self.assertEqual(held['female']['pooled_ms'], -25)
        self.assertEqual(held['male']['other_voice_ms'], -35)
        self.assertEqual(held['female']['other_voice_ms'], -15)
        self.assertEqual(scores['male']['internal']['held_out_pooled_ms']['estimate']['edges'], 0)

    def test_internal_matching_requires_an_unambiguous_count(self):
        passage = {'slots': [{'slot_index': 0, 'char': '山', 'clause_index': 0},
                             {'slot_index': 1, 'char': '河', 'clause_index': 1}]}
        pause = {'start_ms': 100, 'end_ms': 200, 'start_range_ms': [100, 105],
                 'end_range_ms': [195, 200]}
        reference = {'speech_start_ms': 0, 'speech_end_ms': 300, 'speech_start_range_ms': [0, 0],
                     'speech_end_range_ms': [295, 300], 'pauses': [pause],
                     'quiet_candidate_rejections': {'threshold_sensitive': 0}}
        rows, breaks, matched = observe(passage, reference, {}, {})
        self.assertEqual(breaks, 1)
        self.assertTrue(matched)
        self.assertEqual([(item['kind'], item['char']) for item in rows[-2:]], [
            ('pause_start', '山'), ('pause_end', '河')])
        reference['quiet_candidate_rejections']['threshold_sensitive'] = 1
        rows, _, matched = observe(passage, reference, {}, {})
        self.assertFalse(matched)
        self.assertEqual(len(rows), 2)
