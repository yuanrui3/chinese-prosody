import copy
import random
import unittest

from src.historical_increment import compare, descriptors, permute


TIER = 'guangyun'
RHYME = 'rhyme_group_concentration'


def slot(*groups, selected=None):
    return {
        'readings': {
            TIER: {
                'candidates': [{'rhyme': group, 'pingze': '平'} for group in groups],
                'selected': {'rhyme': selected, 'pingze': '平'} if selected is not None else None,
            },
        },
    }


class HistoricalIncrementTest(unittest.TestCase):
    def test_rhyme_concentration_uses_resolved_groups_without_choosing_a_reading(self):
        passage = {
            'slots': [
                slot('東'), slot('東', '東'), slot('東', '冬', selected='東'),
                slot('冬'), slot('東', '冬'), slot(),
            ],
        }
        before = copy.deepcopy(passage)
        estimate = descriptors(passage, TIER)[RHYME]

        self.assertEqual(estimate, {'value': 0.5, 'usable': 6, 'eligible': 15, 'resolved_slots': 4})
        self.assertEqual(passage, before)

    def test_fewer_than_two_resolved_slots_has_no_estimate(self):
        passage = {'slots': [slot('東'), slot('東', '冬'), slot()]}
        estimate = descriptors(passage, TIER)[RHYME]

        self.assertEqual(estimate, {'value': None, 'usable': 0, 'eligible': 3, 'resolved_slots': 1})

    def test_permutations_keep_the_inventory_in_each_period_and_genre(self):
        strata = [
            ('early-tang', 'parallel_prose'), ('sixth-century', 'parallel_prose'),
            ('early-tang', 'comparison_prose'), ('early-tang', 'parallel_prose'),
            ('early-tang', 'comparison_prose'), ('sixth-century', 'comparison_prose'),
            ('sixth-century', 'parallel_prose'),
        ]
        rows = [{'period': period, 'genre': genre, 'work_id': index}
                for index, (period, genre) in enumerate(strata)]
        values = [0.2, 0.3, 0.4, 0.2, 0.5, 0.6, 0.7]
        before = copy.deepcopy(rows)
        samples = [permute(rows, values, random.Random(seed)) for seed in range(16)]

        self.assertEqual(rows, before)
        self.assertEqual(values, [0.2, 0.3, 0.4, 0.2, 0.5, 0.6, 0.7])
        self.assertGreater(len({tuple(sample) for sample in samples}), 1)
        for sample in samples:
            self.assertEqual(len(sample), len(values))
            for stratum in set(strata):
                indices = [index for index, label in enumerate(strata) if label == stratum]
                self.assertCountEqual([sample[index] for index in indices],
                                      [values[index] for index in indices])

    def test_repeated_works_move_as_vectors_within_their_ordered_strata(self):
        parallel = 'parallel_prose'
        comparison = 'comparison_prose'
        placements = [
            ('a', parallel), ('d', parallel), ('b', parallel), ('c', parallel),
            ('e', comparison), ('a', parallel), ('d', comparison), ('b', parallel),
            ('e', parallel),
        ]
        rows = [{'work_id': work, 'period': 'early-tang', 'genre': genre}
                for work, genre in placements]
        values = list(range(len(rows)))
        samples = [permute(rows, values, random.Random(seed)) for seed in range(16)]
        pairs = [[index for index, (work, _) in enumerate(placements) if work == name]
                 for name in ('a', 'b')]
        expected = [tuple(values[index] for index in pair) for pair in pairs]

        self.assertGreater(len({tuple(sample) for sample in samples}), 1)
        for sample in samples:
            self.assertCountEqual([tuple(sample[index] for index in pair) for pair in pairs], expected)
            # The singleton and the mixed, differently ordered signatures stay fixed.
            self.assertEqual([sample[index] for index in (1, 3, 4, 6, 8)], [1, 3, 4, 6, 8])

    def test_shuffled_comparison_uses_the_same_complete_support_as_the_baseline(self):
        def row(work, value, duration):
            return {
                'work_id': work, 'period': 'early-tang', 'genre': 'parallel_prose',
                'slots': 20, 'duration_ms': duration,
                'descriptors': {TIER: {RHYME: {'value': value}}},
            }

        development = [row('d1', 0.2, 2200), row('d2', 0.8, 2800), row('d3', None, 10000)]
        holdout = [row('h1', 0.1, 2100), row('h2', 0.9, 2900), row('h3', None, 10000)]
        result = compare(development, holdout, TIER, RHYME, draws=32, seed=7)

        self.assertEqual(result['status'], 'measured')
        self.assertEqual(result['calibration_passages'], 2)
        self.assertEqual(result['holdout_passages'], 2)
        self.assertAlmostEqual(result['baseline_mae_ms'], 400)
        self.assertAlmostEqual(result['augmented_mae_ms'], 0)
        self.assertEqual(result['draws_used'], 32)
        self.assertGreater(result['distinct_assignments_drawn'], 1)
        self.assertEqual(set(result['gain_ms_by_work']), {'h1', 'h2'})
