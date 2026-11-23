import unittest

from src.quantitative_onset_transfer import MODEL_PIN, WAVEFORM_SETTINGS, evaluate, freeze
from src.quantitative_report import VOICES


TRAINING_HASH = '1' * 64


def training_report():
    profiles, edges = [], []
    for number in range(8):
        witness = {'work_id': f'training-work-{number}', 'passage_id': f'training-passage-{number}',
                   'author': f'training-author-{number}'}
        voices = {}
        for voice_number, voice in enumerate(VOICES):
            identity = {'recording_id': f'{number}-{voice}',
                        'audio_sha256': f'{2 * number + voice_number:064x}'}
            voices[voice] = identity
            edges.append({**identity, 'work_id': witness['work_id'], 'passage_id': witness['passage_id'],
                          'voice': voice, 'kind': 'clip_start', 'edge_ms': 100,
                          'reference_range_ms': [95, 105], 'funasr_ms': 130 + voice_number * 10,
                          'clip_ms': 400})
        profiles.append({'witness': witness, '音律美': {'recorded_timing': voices}})
    return {'conditions': {'voice_ids': VOICES}, 'secondary_alignment': {'model': MODEL_PIN},
            'passages': profiles, 'waveform_offset': {'waveform_settings': WAVEFORM_SETTINGS, 'edges': edges}}


def collection():
    rows = []
    for number in (1, 2):
        for voice_number, voice in enumerate(VOICES):
            incomplete = number == 2 and voice_number == 1
            rows.append({'work_id': f'held-work-{number}', 'author': f'held-author-{number}',
                         'passage_id': f'held-passage-{number}', 'pair_id': 'held-pair-1', 'voice': voice,
                         'audio_sha256': f'{20 + 2 * number + voice_number:064x}', 'duration_ms': 300,
                         'reference_start_ms': None if incomplete else 100,
                         'reference_start_range_ms': None if incomplete else [95, 105],
                         'start_status': 'unresolved' if incomplete else 'ok', 'model_start_ms': 135,
                         'genre': 'parallel_prose' if number == 1 else 'comparison_prose'})
    return {'training_sha256': TRAINING_HASH, 'model': MODEL_PIN, 'waveform_settings': WAVEFORM_SETTINGS,
            'takes': rows}


class OnsetTransferTests(unittest.TestCase):
    def test_frozen_fit_and_identical_work_cohort(self):
        frozen = freeze(training_report())
        self.assertEqual(frozen['shift_ms'], -35)
        result = evaluate(collection(), frozen, TRAINING_HASH, '2' * 64)
        self.assertEqual(result['total_held_out_works'], 2)
        self.assertEqual(result['shared_held_out_works'], ['held-work-1'])
        self.assertEqual(result['by_voice'][VOICES[0]]['own_eligible_works'], 2)
        for voice in VOICES:
            summary = result['by_voice'][voice]
            self.assertEqual(summary['comparison_on_shared_works']['raw']['work_weighted_mae_ms'], 35)
            self.assertEqual(summary['comparison_on_shared_works']['frozen']['work_weighted_mae_ms'], 0)
            self.assertEqual(summary['comparison_on_shared_works']['fixed_minus_80']['work_weighted_mae_ms'], 45)
            self.assertEqual(summary['frozen_vs_raw']['improved'], 1)
        self.assertEqual(result['by_work'][0]['voices'][VOICES[0]]['genre'], 'parallel_prose')

    def test_rejects_overlap_and_stale_training_binding(self):
        frozen = freeze(training_report())
        source = collection()
        with self.assertRaisesRegex(ValueError, 'different training report'):
            evaluate(source, frozen, '9' * 64, '2' * 64)
        for field, value in (('work_id', 'training-work-0'), ('author', 'training-author-0'),
                             ('audio_sha256', '0' * 64)):
            with self.subTest(field=field):
                overlapped = collection()
                overlapped['takes'][0][field] = value
                with self.assertRaisesRegex(ValueError, 'reuses a training'):
                    evaluate(overlapped, frozen, TRAINING_HASH, '2' * 64)

    def test_negative_corrected_coordinates_keep_error(self):
        source = collection()
        source['takes'][0].update(reference_start_ms=0, reference_start_range_ms=[0, 0], model_start_ms=25)
        result = evaluate(source, freeze(training_report()), TRAINING_HASH, '2' * 64)
        shifted = result['by_voice'][VOICES[0]]['comparison_on_shared_works']['frozen']
        self.assertEqual(shifted['outside_clip'], 1)
        self.assertEqual(shifted['work_weighted_mae_ms'], 10)
