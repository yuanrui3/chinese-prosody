from array import array
import unittest

from src.recitation_pause_estimator import choose_threshold, gap_features


class RecitationPauseEstimatorTests(unittest.TestCase):
    def test_thresholds_assign_adjacent_midpoint_corridors_without_overlap(self):
        samples = array('h', [1000] * 200)
        samples[45:55] = array('h', [0] * 10)
        samples[110:135] = array('h', [150] * 25)
        samples[145:165] = array('h', [250] * 20)
        spans = [{'start_s': point - .010, 'end_s': point + .010}
                 for point in (.025, .075, .125, .175)]

        # The same 25 ms low-energy run contributes 15 ms and 10 ms
        # to its two neighboring windows, with no duplicated samples.
        self.assertEqual(gap_features(samples, 1000, spans), {
            '-50': [10.0, 0.0, 0.0],
            '-45': [10.0, 15.0, 10.0],
            '-40': [10.0, 15.0, 20.0],
        })
        self.assertIsNone(gap_features(samples, 1000, spans[::-1]))
        spans[1] = None
        self.assertIsNone(gap_features(samples, 1000, spans))

    def test_threshold_selection_weights_whole_works_equally(self):
        def candidate(work, errors):
            reference = [40, -40, 0]
            return {'work_id': work, 'reference_ms': reference,
                    'quiet_ms_by_dbfs': {str(dbfs): [value + error for value in reference]
                                         for dbfs, error in zip((-50, -45, -40), errors)}}

        frequent = candidate('frequent', (60, 10, 0))
        single = candidate('single', (60, 0, 20))
        self.assertEqual(choose_threshold([frequent, dict(frequent), dict(frequent), single]), -45)
        self.assertEqual(choose_threshold([candidate('tie', (0, 0, 0))]), -45)
        self.assertEqual(choose_threshold([candidate('tie', (0, 10, 0))]), -50)


if __name__ == '__main__':
    unittest.main()
