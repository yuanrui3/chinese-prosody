import copy
import unittest

from audio.align import HeardSyllable, Phone, experimental_ending_hint, link_slots
from audio.ending_variants import variants


class EndingVariantsTest(unittest.TestCase):
    def setUp(self):
        self.slots = [
            {'slot_index': 0, 'char': '流', 'clause_index': 0, 'boundary_after': 1,
             'readings': {'mandarin': {'selected': None, 'candidates': [{'reading': 'liu2'}]}}},
            {'slot_index': 1, 'char': '作', 'clause_index': 1, 'boundary_after': 2,
             'readings': {'mandarin': {'selected': None, 'candidates': [{'reading': 'zuo4'}]}}},
        ]
        self.passage = {'slots': self.slots}
        self.prescription = {'clauses': ['liu2', 'zuo4'], 'text_sha256': 'fixture'}
        self.plan = {'passage_id': 'fixture', 'target_slot_index': 0, 'anchor_slot_index': 1,
                     'target_character': '流', 'anchor_character': '作', 'base': 'liu2', 'anchor': 'zuo4',
                     'tone': 'liu4', 'rhyme': 'luo2'}

    def test_one_pinyin_token_and_expected_coordinate_change(self):
        result = variants(self.passage, self.prescription, self.plan)
        self.assertEqual([metadata['role'] for _, metadata in result], ['base', 'sham', 'tone', 'rhyme'])
        self.assertEqual([recipe['clauses'] for recipe, _ in result],
                         [['liu2', 'zuo4'], ['liu2', 'zuo4'], ['liu4', 'zuo4'], ['luo2', 'zuo4']])
        self.assertTrue(all(recipe['text_sha256'] == 'fixture' for recipe, _ in result))
        with self.assertRaisesRegex(ValueError, 'designated feature'):
            variants(self.passage, self.prescription, {**self.plan, 'tone': 'luo4'})
        with self.assertRaisesRegex(ValueError, 'reverse recurrence'):
            variants(self.passage, self.prescription, {**self.plan, 'rhyme': 'liang2'})

    def test_experimental_link_does_not_change_observed_or_annotated_readings(self):
        annotation = copy.deepcopy(self.slots)
        _, edit = variants(self.passage, self.prescription, self.plan)[-1]
        recording = {'kind': 'synthetic', 'intended_pinyin': ['luo2', 'zuo4'], 'experimental_ending': edit}
        heard = [HeardSyllable([Phone('uo2', 0, 0.2, 0.9)], ('l', 'uo'), '2'),
                 HeardSyllable([Phone('uo4', 0.3, 0.5, 0.9)], ('z', 'uo'), '4')]
        self.assertEqual(link_slots(self.slots, heard)[0][2], 'substitution')
        hint = experimental_ending_hint(recording, self.passage)
        linked = link_slots(self.slots, heard, ending_pinyin=hint)
        self.assertEqual(linked[0][2:], ('matched', 'segment_and_tone'))
        self.assertIs(linked[0][1], heard[0])
        self.assertEqual(self.slots, annotation)
