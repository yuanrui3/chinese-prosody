import unittest
from unittest.mock import patch

from src.pitch_control_extension import choose_target


class PitchControlExtensionTest(unittest.TestCase):
    def test_selects_longest_eligible_internal_ending_at_a_new_slot(self):
        passage = {'slots': [{'boundary_after': level} for level in (1, 1, 1, 1, 2)]}
        take = {'sample_rate': 24000, 'intended_pinyin': ['ba1'] * 5}
        rows = [
            {'slot_index': i, 'status': 'matched', 'duration_ms': 180,
             'observed_phone_draft': {'onset': 'b', 'final': 'o' if i == 3 else 'a'}}
            for i in range(5)
        ]
        with patch('src.pitch_control_extension.eligible_source',
                   side_effect=lambda _, row, __: (0, 200 if row['slot_index'] else 120)):
            target, count = choose_target(passage, take, rows, object(), excluded=2)
        self.assertEqual(count, 2)
        self.assertEqual(target['slot_index'], 1)
