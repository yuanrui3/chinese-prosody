import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import wave

from src.minimal_ending_analysis import measure_pairs, sound_key, summarize, verify_bundle


def example_bundle(root):
    bundle = {}
    audio = root / 'audio'
    audio.mkdir()
    for role, target, frames in (('base', 'ba1', 24000), ('sham', 'ba1', 24000),
                                 ('tone', 'ba4', 24360), ('rhyme', 'bang1', 24240)):
        path = audio / f'{role}.wav'
        with wave.open(str(path), 'wb') as stream:
            stream.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            stream.writeframes(b'\0\0' * frames)
        bundle[role] = {
            'recording_id': role, 'passage_id': 'fixture', 'text_sha256': 'text-digest', 'text_revision': 1,
            'text_source_url': 'https://example.org/fixture', 'speaker': 'fixture', 'speed': 0.9, 'seed': 1,
            'model_revision': 'fixture', 'sample_rate': 24000, 'kind': 'synthetic', 'style': 'synthetic',
            'variety': 'cmn', 'duration_s': frames / 24000, 'audio_path': str(path.relative_to(root)),
            'audio_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'intended_pinyin': ['bang1', target, 'mi3'],
            'experimental_ending': {'target_slot_index': 1, 'anchor_slot_index': 0, 'voice_embedding_index': 8,
                                    'role': role, 'candidate_key': sound_key(target)},
        }
    return bundle


def event(slot, pinyin, early, late):
    onset, final, tone = sound_key(pinyin)
    return {'slot_index': slot, 'status': 'matched', 'duration_ms': 200, 'f0_early_st': early,
            'f0_late_st': late, 'voiced_frames': 15, 'start_s': 0.2 * slot, 'end_s': 0.2 * (slot + 1),
            'observed_phone_draft': {'onset': onset, 'final': final, 'tone': tone}}


class MinimalEndingAnalysisTest(unittest.TestCase):
    def test_decoder_recurrence_and_target_pitch_change_have_separate_support(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            bundle = example_bundle(root)
            rows = {role: [event(0, 'bang1', 2.0, 2.0), event(1, pinyin, 2.0, late), event(2, 'mi3', 1.0, 2.0)]
                    for role, pinyin, late in (('base', 'ba1', 3.0), ('tone', 'ba4', -2.0), ('rhyme', 'bang1', None))}
            gaps = {role: {1: {'gap_ms': gap}} for role, gap in (('base', 22), ('tone', 31), ('rhyme', 26))}
            with patch('src.minimal_ending_analysis.central_formants', return_value=(380, 1510, 5)):
                pairs = list(measure_pairs(root, bundle, rows, gaps))
            self.assertAlmostEqual(pairs[0]['deltas_edited_minus_base']['clip_duration_ms'], 15)
            self.assertEqual(pairs[0]['deltas_edited_minus_base']['f0_slope_st'], -5.0)
            self.assertEqual(pairs[0]['deltas_edited_minus_base']['gap_after_ms'], 9)
            self.assertEqual(pairs[1]['decoded_final_recurrence_with_anchor']['transition'], 'gained')
            summary = summarize(pairs)
            self.assertEqual(summary['rhyme']['measures']['f0_slope_st']['pairs'], 0)
            self.assertEqual(summary['rhyme']['intended_recurrence_recovered'], 1)
            self.assertEqual(summary['tone']['falling_tone_check']['median_falling_minus_other_st'], -5)

    def test_bundle_rejects_seed_or_extra_input_changes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            bundle = example_bundle(root)
            self.assertEqual(verify_bundle(root, bundle)[:2], (1, 0))
            bundle['tone']['seed'] = 2
            with self.assertRaisesRegex(ValueError, 'experiment condition'):
                verify_bundle(root, bundle)
            bundle['tone']['seed'] = 1
            bundle['tone']['intended_pinyin'][2] = 'mi4'
            with self.assertRaisesRegex(ValueError, 'change only the intended slot'):
                verify_bundle(root, bundle)
