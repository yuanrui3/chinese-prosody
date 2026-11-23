import unittest
from array import array

from audio.align import MODEL_REVISION
from audio.synthesize import duration_draft
from src.recitation_context_decode import consensus
from src.recitation_guide_recovery import recover_fragmented_clause
from src.recitation_pcm_alignment import locate_silence, project_edge
from src.recitation_second_aligner import map_intervals
from src.recitation_second_aligner_analysis import summarize
from src.recitation_voice_transfer import generator_candidate


class RecitationAlignmentTests(unittest.TestCase):
    def test_generator_timing_draft_respects_sentinels_and_separator(self):
        take = dict(recording_id='fixture', audio_sha256='audio', text_sha256='text',
                    model_revision='mock', intended_model_phonemes='ab/c')
        frames = [2, 3, 1, 2, 4, 1]
        draft = duration_draft(take, [(0, 2), (3, 4)], frames, 7800)
        self.assertEqual(draft['slot_spans_samples'], [[1200, 3600], [4800, 7200]])
        self.assertEqual(draft['audio_sha256'], take['audio_sha256'])
        with self.assertRaisesRegex(ValueError, 'waveform length'):
            duration_draft(take, [(0, 2), (3, 4)], frames, 7000)

    def test_generator_alignment_bounds_departure_from_kokoro_timestamp_origin(self):
        lineage = dict(recording_id='fixture', audio_sha256='audio', text_sha256='text', model_revision='mock')
        take = {**lineage, 'intended_pinyin': ['ri4', 'mu4', 'tu2', 'yuan3']}
        draft = {**lineage, 'sample_count': 20000, 'frame_samples': 600, 'token_frames': [12],
                 'slot_spans_samples': [[start, start + 2400] for start in range(7200, 16800, 2400)]}
        slots = [{'slot_index': index} for index in range(4)]
        pcm = array('h', [0]) * draft['sample_count']
        pcm[1000] = 3000
        evidence = {1: {'start_s': .30, 'end_s': .40, 'observed_phone_draft': {'onset': 'm', 'final': 'u'}}}
        candidate, failure = generator_candidate(take, pcm, 24000, 3000, slots, evidence, draft)
        self.assertIsNone(failure)
        self.assertEqual(candidate['generator_offset_samples'], -2400)
        self.assertEqual(candidate['generator_nominal_offset_samples'], -1800)
        evidence[1].update(start_s=.15, end_s=.25)
        self.assertEqual(generator_candidate(take, pcm, 24000, 3000, slots, evidence, draft),
                         (None, 'generator_offset_outside_limit'))

    def test_fragmented_final_preserves_conflicting_phone_and_original_link(self):
        take = {'recording_id': 'fixture', 'passage_id': 'fixture', 'audio_path': 'fixture.wav',
                'audio_sha256': 'fixture-hash', 'intended_pinyin': ['ri4', 'mu4', 'tu2', 'yuan3']}
        lineage = {key: value for key, value in take.items() if key != 'intended_pinyin'}
        slots = [{'slot_index': index, 'char': char} for index, char in enumerate('日暮途遠')]
        events = []
        for event, (slot, status, onset, final, tone, start, end) in enumerate([
            (0, 'matched', 'r', 'iii', '4', .25, .40),
            (1, 'matched', 'm', 'u', '4', .40, .57),
            (None, 'insertion', '', 'ong', '2', .72, .75),
            (2, 'substitution', '', 'u', '2', .75, .78),
            (3, 'matched', '', 'van', '3', .78, 1.02),
        ]):
            events.append({**lineage, 'event_index': event, 'slot_index': slot, 'status': status,
                           'start_s': start, 'end_s': end,
                           'observed_phone_draft': {'onset': onset, 'final': final, 'tone': tone}})
        linked = {event['slot_index']: event for event in events if event['status'] == 'matched'}
        draft = {**lineage, 'frame_s': .01, 'model_revision': MODEL_REVISION, 'phones': [
            {'label': label, 'start_s': start, 'end_s': end, 'confidence': .7}
            for label, start, end in [('t', .57, .71), ('u2', .71, .72), ('ong2', .72, .75), ('u2', .75, .78)]
        ]}
        rows, evidence = recover_fragmented_clause(take, slots, linked, draft, events)
        self.assertEqual((rows[2]['start_s'], rows[2]['end_s']), (.57, .78))
        self.assertEqual(rows[2]['observed_phone_draft'], events[3]['observed_phone_draft'])
        self.assertEqual(evidence['raw_phones'][2]['label'], 'ong2')
        self.assertEqual(events[3]['status'], 'substitution')
        draft['phones'][2]['label'] = 'ong3'
        self.assertIsNone(recover_fragmented_clause(take, slots, linked, draft, events))

    def test_silence_reconstruction_keeps_all_equivalent_locations(self):
        self.assertEqual(locate_silence([1, 0, 0, 2], [1, 0, 0, 0, 0, 2], 2), [1, 3])
        self.assertIsNone(locate_silence([1, 0, 0, 2], [1, 0, 7, 0, 0, 2], 2))
        self.assertEqual(project_edge(2, [(1, 3, 2)], start=True), [2, 4])

    def test_context_agreement_abstains_on_shifted_edges(self):
        first = {'status': 'measured', 'left_end_s': .5, 'right_start_s': .54, 'gap_ms': 40}
        self.assertEqual(consensus([first, {**first, 'right_start_s': .55}]), (40, 'two_view_agreement'))
        self.assertEqual(consensus([first, {**first, 'right_start_s': .60}]), (None, 'conflicting_edges'))

    def test_second_aligner_preserves_supplied_characters_and_raw_edges(self):
        timestamps = [[-20, 180], [180, 360], [380, 610], [610, 820]]
        spans, status = map_intervals(timestamps, '日暮途遠', 800)
        self.assertEqual(status, 'aligned')
        self.assertEqual(''.join(span['char'] for span in spans), '日暮途遠')
        self.assertEqual((spans[0]['start_s'], spans[-1]['end_s']), (0, .8))
        self.assertEqual(spans[-1]['model_timestamp_ms'], [610, 820])
        self.assertEqual(map_intervals(timestamps[:-1], '日暮途遠', 800),
                         ([], 'timestamp_count_differs_from_han_count'))
        timestamps[2][0] = 350
        self.assertEqual(map_intervals(timestamps, '日暮途遠', 800),
                         ([], 'invalid_timestamp_order_or_bounds'))

    def test_second_aligner_summary_distinguishes_spacing_from_span_gaps(self):
        core_shifts = {'two_two': [0, 0, 80, 80], 'one_one_two': [0, 40, 80, 80]}
        report = summarize([{
            'status': 'measured',
            'take_status': dict.fromkeys(('carrier', *core_shifts), 'aligned'),
            'split_minus_concentrated': {
                'model_landmark_spacing_changes_ms': [30, -30, 0],
                'model_span_gap_changes_ms': [0, 0, 0],
                'pcm_pause_changes_ms': [40, -40, 0],
            },
            'carrier_relative': {
                'model_midpoint_shifts_ms': core_shifts,
                'pcm_core_shifts_ms': core_shifts,
                'first_and_last_anchor_residuals_ms': dict.fromkeys(core_shifts, [0, 0]),
            },
        }], 20)
        self.assertEqual(report['all_three_takes_aligned'], 1)
        spacing = report['approaches']['model_landmark_spacing_changes_ms']
        self.assertEqual(spacing['both_pcm_directions'], 1)
        self.assertEqual(spacing['boundaries'][0]['median_absolute_error_ms'], 10)
        self.assertEqual(report['approaches']['model_span_gap_changes_ms']['both_pcm_directions'], 0)


if __name__ == '__main__':
    unittest.main()
