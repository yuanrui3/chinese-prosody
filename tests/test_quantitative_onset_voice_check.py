import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from audio.synthesize import REPO, REVISION
from src.quantitative_onset_transfer import measure
from src.quantitative_onset_voice_check import ALL_VOICES, THIRD_VOICE, summarize, verify_third_takes
from src.quantitative_report import FILES, VOICES


class OnsetVoiceCheckTests(unittest.TestCase):
    def test_views_use_the_same_three_voice_work_intersection(self):
        works = {}
        for work, errors in (('shared', (40, 45, 50)), ('missing-third', (100, 110, None)),
                             ('missing-first', (None, 25, 30))):
            works[work] = {}
            for voice, error in zip(ALL_VOICES, errors):
                works[work][voice] = measure({
                    'work_id': work, 'duration_ms': 1000, 'reference_start_ms': 100,
                    'reference_start_range_ms': [95, 105],
                    'model_start_ms': 100 + error if error is not None else None,
                }, -35)
        result = summarize(works)
        self.assertEqual(result['shared_works_all_three'], ['shared'])
        earlier, third = (result['by_voice'][voice] for voice in (VOICES[0], THIRD_VOICE))
        self.assertEqual(earlier['own_onset_metrics']['by_method']['raw']['work_weighted_mae_ms'], 70)
        self.assertEqual(earlier['all_three_onset_metrics']['by_method']['raw']['work_weighted_mae_ms'], 40)
        self.assertEqual(third['own_onset_metrics']['by_method']['frozen']['work_weighted_mae_ms'], 10)
        self.assertEqual(third['all_three_onset_metrics']['by_method']['frozen']['work_weighted_mae_ms'], 15)

    def test_third_voice_conditions_reject_prior_waveforms_and_unsupported_rights(self):
        pid = 'H03'
        passage = {'text_sha256': '1' * 64, 'revision_id': 14, 'source_url': 'source',
                   'license': 'CC-BY-SA-4.0'}
        rid = f'kokoro-{pid}-{THIRD_VOICE}-0p9'
        audio_path = f'audio/raw/synthetic/{rid}.wav'
        candidate = {'passage_id': pid, 'speaker': THIRD_VOICE, 'recording_id': rid, 'audio_path': audio_path,
                     'audio_sha256': '2' * 64, 'kind': 'synthetic', 'variety': 'cmn',
                     'style': 'controlled_read_speech', 'speed': 0.9, 'sample_rate': 24000,
                     'text_sha256': passage['text_sha256'], 'text_revision': passage['revision_id'],
                     'text_source_url': passage['source_url'], 'text_license': passage['license'],
                     'source_url': f'https://huggingface.co/{REPO}/tree/{REVISION}',
                     'model_revision': REVISION, 'model_license': 'Apache-2.0', 'pronunciation_status': 'input_only',
                     'intended_pinyin': ['zhong1'], 'intended_model_phonemes': 'z',
                     'seed': int(sha256(f'kokoro-{pid}-{VOICES[0]}-0p9'.encode()).hexdigest()[:8], 16)}
        others = {(pid, voice): {**candidate, 'audio_sha256': str(voice_number + 3) * 64}
                  for voice_number, voice in enumerate(VOICES)}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / FILES['takes']
            audio = root / audio_path
            manifest.parent.mkdir(parents=True)
            audio.parent.mkdir(parents=True)
            audio.touch(mode=0o600)
            manifest.write_text(json.dumps(candidate) + '\n', encoding='utf-8')
            self.assertEqual(verify_third_takes(root, {pid: passage}, others, set())[pid], candidate)
            for change in ({'audio_sha256': '3' * 64}, {'text_license': 'unresolved'}, {'seed': 0}):
                manifest.write_text(json.dumps({**candidate, **change}) + '\n', encoding='utf-8')
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'conditions or waveform'):
                    verify_third_takes(root, {pid: passage}, others, set())
