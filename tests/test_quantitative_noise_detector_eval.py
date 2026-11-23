from array import array
from unittest import TestCase
from unittest.mock import patch

from src import quantitative_noise_detector_eval as benchmark
from src import quantitative_pause_noise as controls


def result(outcome, usable=False, error=None):
    return {
        'outcome': outcome, 'usable_resume': usable, 'absolute_edge_error_ms': error,
        'both_edges_within_tolerance': all(item <= 20 for item in error) if error else None,
    }


class NoiseDetectorEvaluationTests(TestCase):
    def test_detector_callback_receives_exact_baseline_pcm(self):
        observed = {method: [] for method in benchmark.METHODS}

        def record(method):
            def detect(samples, rate):
                observed[method].append(controls.pcm_checksum(samples))
                return {'pauses': [], 'reference_frame_power': 1}
            return detect

        source = array('h', [5000] * 9600)
        with (patch.object(controls.quantitative_waveform_reference, 'waveform_reference', record('strict')),
              patch.object(controls.quantitative_pause_detector, 'detect_relative', record('relative'))):
            default = controls.evaluate(source, 24000, '0' * 64)
            augmented = controls.evaluate(source, 24000, '0' * 64,
                                          extra_detectors=(('noise_aware', record('noise_aware')),))

        checksums = [row['pcm16le_sha256'] for row in augmented['trials']]
        self.assertEqual(observed['strict'], checksums * 2)
        self.assertEqual(observed['relative'], checksums * 2)
        self.assertEqual(observed['noise_aware'], checksums)
        for row in augmented['trials']:
            self.assertIn('noise_aware', row['results'])
            del row['results']['noise_aware']
        self.assertEqual(default, augmented)

    def test_timing_denominators_distinguish_detections_and_usable_edges(self):
        scored = benchmark.summarize_trials(
            [result('hit', True, [40, 20]), result('hit', False, [0, 0]), result('miss')],
            [result('false_pause'), result('no_pause')],
        )
        self.assertEqual(scored['detections'], 2)
        self.assertEqual(scored['usable_resumptions'], 1)
        self.assertEqual(scored['usable_resumptions_within_20ms'], 1)
        self.assertEqual(scored['positive_trial_fraction_with_usable_resumption_within_20ms'], 1 / 3)
        self.assertEqual(scored['detected_with_both_edges_within_20ms'], 1)
        self.assertEqual(scored['mean_absolute_start_end_error_ms_on_usable_resumptions'], [40, 20])
        self.assertEqual(scored['false_matches_at_negative_sites'], 1)

    def test_joint_masks_require_the_same_work_in_all_voices(self):
        indexed = {}
        for voice in benchmark.ALL_VOICES:
            outcomes = {method: result('hit', True, [0, 0]) for method in benchmark.METHODS}
            if voice == benchmark.ALL_VOICES[0]:
                outcomes['noise_aware'] = result('hit', True, [5, 21])
            indexed[-24, 120, 'work-a', voice] = outcomes
            indexed[-24, 60, 'work-a', voice] = {method: result('no_pause') for method in benchmark.METHODS}
        indexed[-24, 120, 'work-b', benchmark.ALL_VOICES[0]] = outcomes
        indexed[-24, 60, 'work-a', benchmark.ALL_VOICES[1]]['noise_aware'] = result('false_pause')

        masks = benchmark.joint_work_masks(indexed, ['work-a', 'work-b'], -24, 120)
        negative = benchmark.joint_work_masks(indexed, ['work-a', 'work-b'], -24, 60)
        self.assertEqual(masks['works_available_in_all_three_voices'], ['work-a'])
        self.assertEqual(masks['by_method']['noise_aware']['usable_resumption_in_all_three_voices'], ['work-a'])
        self.assertEqual(masks['by_method']['noise_aware']['usable_resumption_within_20ms_in_all_three_voices'], [])
        self.assertEqual(masks['mean_absolute_start_end_error_ms_on_common_works']['noise_aware'], [5 / 3, 7])
        self.assertEqual(negative['by_method']['noise_aware']['false_match_in_any_voice'], ['work-a'])
