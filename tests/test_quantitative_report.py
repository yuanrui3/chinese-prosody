import unittest
from unittest.mock import patch

from src.quantitative_alignment_audit import coverage, endpoint_support, validated_slots
from src.quantitative_report import VOICES, held_out, validation
from src.recitation_second_aligner import map_intervals


def clause(slots, first, second):
    return {'slots': slots, 'articulation_ms': dict(zip(VOICES, (first, second)))}


def profile(work, clauses):
    return {'witness': {'work_id': work}, 'clauses': clauses}


class QuantitativeReportTests(unittest.TestCase):
    def test_missing_endpoint_requires_agreeing_observed_anchors_on_both_sides(self):
        secondary = {number: {'start_s': number / 10, 'end_s': (number + 1) / 10}
                     for number in range(5)}
        linked = {number: secondary[number] for number in (0, 3)}
        self.assertEqual(endpoint_support(1, secondary, linked, {0: 60, 3: 0}), 'bracketed')
        self.assertEqual(endpoint_support(0, secondary, linked, {0: 60, 3: 0}), 'direct')
        self.assertEqual(endpoint_support(1, secondary, linked, {0: 61, 3: 0}), 'unsupported')
        self.assertEqual(endpoint_support(4, secondary, linked, {0: 0, 3: 0}), 'unsupported')
        # A discrepant closest anchor cannot be replaced with an agreeable farther one.
        linked[2] = secondary[2]
        self.assertEqual(endpoint_support(1, secondary, linked, {0: 0, 2: 61, 3: 0}), 'unsupported')

    def test_timestamped_text_cannot_be_substituted_for_the_verified_slots(self):
        slots, status = map_intervals([[0, 200], [200, 410]], '四海', 400)
        passage = {'slots': [{'char': char} for char in '四海']}
        ident = {'recording_id': 'a', 'passage_id': 'b', 'audio_sha256': 'c', 'text_sha256': 'd'}
        take = {**ident, 'sample_rate': 24000}
        row = {**ident, 'sample_count': 9600, 'status': status, 'slots': slots}
        self.assertEqual(len(validated_slots(row, passage, take, 400)), 2)
        with self.assertRaises(ValueError):
            validated_slots({**row, 'audio_sha256': 'stale'}, passage, take, 400)
        with self.assertRaises(ValueError):
            validated_slots({**row, 'slots': [{**slots[0], 'char': '五'}, slots[1]]}, passage, take, 400)

    def test_new_joint_coverage_excludes_raw_timestamps_without_anchor_support(self):
        rows = [
            {'articulation_ms': dict(zip(VOICES, (None, None))),
             'bracketed_elapsed_ms': dict(zip(VOICES, (50, None))),
             'secondary_elapsed_ms': dict(zip(VOICES, (53, 55))),
             'secondary_anchored_elapsed_ms': dict(zip(VOICES, (None, 55)))},
            {'articulation_ms': dict(zip(VOICES, (None, None))),
             'bracketed_elapsed_ms': dict(zip(VOICES, (None, None))),
             'secondary_elapsed_ms': dict(zip(VOICES, (53, 55))),
             'secondary_anchored_elapsed_ms': dict(zip(VOICES, (None, None)))},
        ]
        result = coverage(rows, VOICES)
        self.assertEqual(result['secondary_elapsed_ms']['both'], 2)
        self.assertEqual(result['secondary_anchored_elapsed_ms']['both'], 0)
        self.assertEqual(result['new_over_original_brackets']['both'], 1)

    def test_bracketed_elapsed_keeps_its_own_coverage(self):
        complete = {**clause(4, 60, 65), 'bracketed_elapsed_ms': dict(zip(VOICES, (80, 90)))}
        partial = {**clause(4, 70, None), 'bracketed_elapsed_ms': dict(zip(VOICES, (95, 105)))}
        profiles = [profile('a', [complete, partial])]
        self.assertEqual(validation(profiles)['shared_clauses'], 1)
        self.assertEqual(validation(profiles, 'bracketed_elapsed_ms')['shared_clauses'], 2)

    def test_cross_voice_mask_excludes_a_clause_missing_in_either_voice(self):
        profiles = [
            profile('a', [clause(2, 20, 40), clause(4, 40, 80), clause(50, 5000, None)]),
            profile('b', [clause(3, 30, 60), clause(5, 50, 100), clause(50, None, 5000)]),
            profile('excluded', [clause(2, None, 40)]),
        ]
        result = validation(profiles)
        self.assertEqual(result['total_clauses'], 7)
        self.assertEqual(result['shared_clauses'], 4)
        self.assertEqual(result['works_with_shared_clauses'], 2)
        self.assertEqual(result['shared_clauses_by_work'], {'a': 2, 'b': 2, 'excluded': 0})
        self.assertEqual(result['cross_voice_articulation_ranks']['rho'], 1.0)
        self.assertEqual(result['cross_voice_median_absolute_difference_ms'], 35)
        for voice in VOICES:
            fit = result['held_out_timing'][voice]
            self.assertEqual(set(fit['errors_by_work']), {'a', 'b'})
            self.assertEqual(fit['count_ms'], 0)

    def test_count_baseline_fits_equal_weighted_training_works(self):
        lengths = {'a': [2, 4, 8], 'b': [3], 'c': [4]}
        rows = {'a': [clause(2, 20, 40), clause(4, 40, 80), clause(8, 80, 160)],
                'b': [clause(3, 60, 120)], 'c': [clause(4, 120, 240)]}
        result = held_out(rows, lengths)
        for voice, scale in zip(VOICES, (1, 2)):
            fit = result[voice]
            self.assertEqual({work: row['count_ms'] for work, row in fit['errors_by_work'].items()},
                             {'a': 70 * scale, 'b': 0, 'c': 60 * scale})
            self.assertAlmostEqual(fit['count_ms'], 130 * scale / 3)
            self.assertAlmostEqual(fit['constant_ms'], 400 * scale / 9)

    def test_seeded_control_shuffles_lengths_independently_within_each_work(self):
        lengths = (2, 4, 6, 8)
        profiles = [profile(work, [clause(count, count * 10, count * 20) for count in lengths])
                    for work in ('a', 'b', 'c')]
        with patch('src.quantitative_report.DRAW_COUNT', 9), \
                patch('src.quantitative_report.held_out', wraps=held_out) as fitted:
            first = validation(profiles)
            shuffled = [call.args[1] for call in fitted.call_args_list[1:]]
            second = validation(profiles)

        self.assertEqual(first, second)
        self.assertEqual(len(shuffled), 9)
        for draw in shuffled:
            for work_lengths in draw.values():
                self.assertCountEqual(work_lengths, lengths)
        self.assertTrue(any(len({tuple(counts) for counts in draw.values()}) > 1 for draw in shuffled))
        control = first['length_shuffle_control']
        self.assertEqual(control['works_with_variable_length'], 3)
        self.assertEqual(control['draws'], 9)
        for voice in VOICES:
            self.assertEqual(first['held_out_timing'][voice]['count_ms'], 0)
            self.assertGreater(control['voices'][voice]['null_median_count_mae_ms'], 0)


if __name__ == '__main__':
    unittest.main()
