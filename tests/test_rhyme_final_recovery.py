import unittest

from src.rhyme_final_recovery import observations, recover, recurrence, take_endpoints
from src.rhyme_window_redecode import consensus


def phone_fixture(keys):
    phones = []
    for index, (onset, final) in enumerate(keys):
        start = index / 4
        phones.extend([
            {'label': onset, 'start_s': start, 'end_s': start + 0.04, 'confidence': 0.8},
            {'label': final, 'start_s': start + 0.04, 'end_s': start + 0.18, 'confidence': 0.9},
        ])
    return observations(phones, len(keys) / 4)


def event(slot, observed, status):
    return {
        'slot_index': slot,
        'status': status,
        'start_s': observed['start_s'],
        'end_s': observed['end_s'],
        'duration_ms': observed['duration_ms'] if status == 'matched' else None,
        'observed_phone_draft': observed['decoder'],
    }


class RhymeFinalRecoveryTest(unittest.TestCase):
    def test_recovered_final_keeps_its_noncanonical_onset_and_tone(self):
        decoded = phone_fixture([('m', 'a1'), ('r', 'uo3'), ('m', 'a2'), ('z', 'uo4'), ('m', 'i2')])
        member = {'recording_id': 'take', 'audio_path': 'take.wav', 'audio_sha256': 'fixture',
                  'intended_pinyin': ['ma1', 'liu2', 'ma2', 'zuo4', 'mi2']}
        events = [event(index, observed, 'substitution' if index == 1 else 'matched')
                  for index, observed in enumerate(decoded)]
        take = take_endpoints(member, decoded, events, events, target=1, anchor=3)
        self.assertIsNone(take['target']['before'])
        self.assertEqual(take['target']['method'], 'strict_neighbor_bracket')
        self.assertEqual(take['target']['flank_slots'], [0, 2])
        self.assertEqual(take['target']['after']['decoder'], {'onset': 'r', 'final': 'uo', 'tone': '3'})
        self.assertAlmostEqual(take['target']['after']['final_start_s'], 0.29)
        self.assertEqual(take['anchor']['method'], 'original_link')
        self.assertIsNone(recurrence(take, 'before'))
        self.assertTrue(recurrence(take, 'after'))
        self.assertEqual(take['masked_known_link_check'],
                         {'tested': 3, 'recovered': 1, 'agrees': 1, 'abstains': 2, 'disagrees': 0})

    def test_extra_candidate_between_flanks_is_unresolved(self):
        observed = phone_fixture([('m', 'a1'), ('l', 'uo2'), ('l', 'iou2'), ('m', 'a2')])
        expected = [('m', 'a'), ('l', 'iou'), ('m', 'a')]
        self.assertEqual(recover(1, {0: 0, 2: 3}, observed, expected, {1}),
                         (None, 'ambiguous_interior_count'))

    def test_non_endpoint_sound_disagreement_is_not_skipped(self):
        observed = phone_fixture([('m', 'a1'), ('l', 'uo2'), ('z', 'a2'), ('m', 'i2')])
        expected = [('m', 'a'), ('l', 'iou'), ('m', 'a'), ('m', 'i')]
        self.assertEqual(recover(1, {0: 0, 3: 3}, observed, expected, {1}),
                         (None, 'intervening_context_disagrees'))

    def test_terminal_context_requires_two_consecutive_matches(self):
        observed = phone_fixture([('m', 'a1'), ('m', 'i2'), ('l', 'uo2')])
        expected = [('m', 'a'), ('m', 'i'), ('l', 'iou')]
        self.assertEqual(recover(2, {0: 0, 1: 1}, observed, expected, {2}),
                         ((2, 1, 3), 'terminal_context'))
        self.assertEqual(recover(2, {1: 1}, observed, expected, {2}), (None, 'missing_strict_flanks'))

    def test_recovery_cannot_reuse_a_raw_final_from_an_existing_other_link(self):
        observed = phone_fixture([('m', 'a1'), ('l', 'uo2'), ('m', 'a2')])
        expected = [('m', 'a'), ('l', 'iou'), ('m', 'a')]
        self.assertEqual(recover(1, {0: 0, 2: 2}, observed, expected, {1}, occupied={1}),
                         (None, 'competing_original_slot'))

    def test_window_consensus_keeps_raw_label_and_abstains_on_conflict(self):
        first = phone_fixture([('r', 'uo3')])[0]
        second = {**first, 'final_confidence': 0.75, 'final_start_s': first['final_start_s'] + 0.01}
        views = [{'observation': first}, {'observation': second}]
        self.assertEqual(consensus(views), (first, 'redecode_consensus'))
        self.assertEqual(consensus(views[:1]), (None, 'insufficient_anchored_views'))
        other = {**second, 'decoder': {**second['decoder'], 'final': 'o'}}
        self.assertEqual(consensus(views + [{'observation': other}]), (None, 'conflicting_final_labels'))

    def test_window_consensus_rejects_shifted_boundaries(self):
        first = phone_fixture([('r', 'uo3')])[0]
        second = {**first, 'final_end_s': first['final_end_s'] + 0.05}
        self.assertEqual(consensus([{'observation': first}, {'observation': second}]),
                         (None, 'conflicting_final_intervals'))


if __name__ == '__main__':
    unittest.main()
