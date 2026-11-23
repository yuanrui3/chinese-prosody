import unittest

from src.timing_benchmark import check_split, evaluate, fit


class TimingBenchmarkTest(unittest.TestCase):
    def test_equal_work_weight_and_fixed_holdout_predictions(self):
        a = {'work_id': 'a', 'slots': 10, 'clause_breaks': 2, 'duration_ms': 2600}
        b = {'work_id': 'b', 'slots': 8, 'clause_breaks': 1, 'duration_ms': 1900}
        fitted = fit([a, a, b])
        self.assertAlmostEqual(fitted['slot_count']['ms_per_slot'], 248.75)
        candidate = fitted['slot_count_and_clause_breaks']
        self.assertAlmostEqual(candidate['ms_per_slot'], 200)
        self.assertAlmostEqual(candidate['ms_per_clause_break'], 300)
        holdout = [{'work_id': 'c', 'slots': 16, 'clause_breaks': 4, 'duration_ms': 4400}]
        _, _, summary = evaluate(holdout, fitted)
        self.assertAlmostEqual(summary['work_mean_absolute_error_ms']['slot_count_and_clause_breaks'], 0)
        self.assertEqual(summary['works_with_lower_error_from_clause_breaks'], 1)

    def test_shared_authorship_rejects_otherwise_distinct_inputs(self):
        def sample(identifier, author):
            return {**dict.fromkeys(('work_id', 'passage_id', 'text_sha256', 'audio_sha256'), identifier),
                    'authors': [author], 'condition': ('same-model', 'same-voice')}

        calibration = [sample('a', 'first')]
        check_split(calibration, [sample('b', 'second')])
        with self.assertRaisesRegex(ValueError, 'share an author'):
            check_split(calibration, [sample('b', 'first')])
