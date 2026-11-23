import unittest

from src.quantitative_historical_transfer import GENRES, PERIODS, SERIES, TIERS, VOICES, run_comparisons


def cohort(prefix):
    return {
        voice: [{
            'work_id': f'{prefix}-work-{i}', 'passage_id': f'{prefix}-passage-{i}',
            'authors': [f'{prefix}-author-{i}'], 'text_sha256': f'{prefix}-text-{i}',
            'audio_sha256': f'{prefix}-{voice}-audio-{i}', 'condition': (voice, 0.9),
            'period': PERIODS[i // 4], 'genre': GENRES[i // 2 % 2],
            'slots': 20, 'duration_ms': 4000 + 500 * i,
            'descriptors': {tier: {feature: {'value': i / 10} for feature_tier, feature in SERIES
                                   if feature_tier == tier} for tier in TIERS},
        } for i in range(8)]
        for voice in VOICES
    }


class HistoricalTransferTests(unittest.TestCase):
    def test_voice_runs_share_permutations_and_primary_holm_family(self):
        results = run_comparisons(cohort('cal'), cohort('test'), draws=29, seed=13)
        primary = [row for row in results[VOICES[0]] if row['tier'] == TIERS[0]]
        smallest = min(primary, key=lambda row: row['p_value'])
        self.assertAlmostEqual(smallest['p_holm'], min(1, 4 * smallest['p_value']))
        for left, right in zip(*(results[voice] for voice in VOICES)):
            self.assertEqual(left, right)
            self.assertAlmostEqual(left['augmented_mae_ms'], 0)
            self.assertLess(left['augmented_mae_ms'], left['baseline_mae_ms'])
            self.assertGreater(left['distinct_assignments_drawn'], 1)
            if left['tier'] == TIERS[0]:
                self.assertGreaterEqual(left['p_holm'], left['p_value'])
            else:
                self.assertIsNone(left['p_holm'])

    def test_rejects_an_author_shared_by_training_and_holdout(self):
        calibration, holdout = cohort('cal'), cohort('test')
        holdout[VOICES[1]][0]['authors'] = calibration[VOICES[1]][0]['authors']
        with self.assertRaisesRegex(ValueError, 'share an author'):
            run_comparisons(calibration, holdout, draws=5)


if __name__ == '__main__':
    unittest.main()
