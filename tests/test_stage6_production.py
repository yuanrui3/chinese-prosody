"""Fixture checks for Stage 6 intake, blind prompts and reviewed measurements."""

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import wave

from src.stage6_production import (
    PROMPTS, VERSION, analyze, draft_manifest, prepare, read_json, read_jsonl, write_jsonl,
)


class Stage6ProductionTests(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()
        output = self.root / 'data/pilot'
        output.mkdir(parents=True)
        text = '甲乙，丙丁。'
        records = [{
            'passage_id': passage_id,
            'text': text,
            'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'slots': [
                {'char': char, 'clause_index': index // 2}
                for index, char in enumerate('甲乙丙丁')
            ],
        } for _, passage_id in PROMPTS]
        write_jsonl(output / 'annotated.jsonl', records)
        with redirect_stdout(io.StringIO()):
            prepare(self.root)
        self.stage = self.root / 'audio/stage6'

    def intake_fixture(self):
        restricted = self.stage / 'restricted'
        consent = restricted / 'fixture.json'
        consent.write_text(json.dumps({
            'version': VERSION, 'reader_code': 'fixture-01', 'consent_id': 'fixture-consent',
            'scope': 'author_self_trial', 'affirmed': True, 'variety': 'cmn',
        }))
        consent.chmod(0o600)
        # Generated silence tests file handling and calculations only.
        wav = self.root / 'audio/raw/human/stage6/fixture-01/R01.wav'
        wav.parent.mkdir(parents=True, mode=0o700)
        with wave.open(str(wav), 'wb') as stream:
            stream.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            stream.writeframes(bytes(8000 * 2 * 5))
        wav.chmod(0o600)
        with redirect_stdout(io.StringIO()):
            draft_manifest(self.root, consent)
        return restricted / 'production/fixture-01'

    def test_reader_material_has_opaque_ids(self):
        task = read_json(self.stage / 'production/task.json')
        self.assertEqual([prompt['code'] for prompt in task['prompts']], [code for code, _ in PROMPTS])
        for prompt in task['prompts']:
            self.assertEqual(set(prompt), {'code', 'text'})

    def test_review_measures_timed_events_and_rejects_stale_alignment(self):
        output = self.intake_fixture()
        rows = read_jsonl(output / 'review-template.jsonl')
        rows[0].update(
            status='verified', reviewer_code='coder-01', start_s=0.1, end_s=1.1,
            spoken_syllables=3,
            events=[
                {'type': 'pause', 'start_s': 0.3, 'end_s': 0.5},
                {'type': 'false_start', 'start_s': 0.2, 'end_s': 0.3},
                {'type': 'reread', 'start_s': 3.2, 'end_s': 4},
            ],
        )
        rows[1].update(
            status='verified', reviewer_code='coder-01', start_s=1.5, end_s=2.5,
            spoken_syllables=2,
        )
        path = output / 'reviewed.jsonl'
        write_jsonl(path, rows)
        with redirect_stdout(io.StringIO()):
            analyze(self.root, 'fixture-01', path, None)
        measures = read_jsonl(output / 'clause-measures.jsonl')
        first = measures[0]
        self.assertAlmostEqual(first['speech_syllables_per_s'], 3.0)
        self.assertAlmostEqual(first['pause_excluded_syllables_per_s'], 3.75)
        self.assertAlmostEqual(first['following_boundary_gap_s'], 0.4)
        self.assertTrue(first['following_boundary_pause'])
        self.assertEqual(first['event_counts']['reread'], 1)
        self.assertEqual(first['event_counts']['false_start'], 1)
        self.assertIsNone(measures[1]['following_boundary_gap_s'])

        manifest = read_jsonl(output / 'recordings.jsonl')[0]
        draft = output / 'alignment.jsonl'
        link = {key: manifest[key] for key in ('recording_id', 'passage_id', 'audio_path', 'kind', 'variety')}
        link.update(
            audio_sha256='stale', status='matched', event_index=0,
            alignment_source='charsiu_waveform_only_then_lexical_link',
        )
        write_jsonl(draft, [link])
        with self.assertRaisesRegex(ValueError, 'actual-waveform'):
            analyze(self.root, 'fixture-01', path, draft)
        write_jsonl(draft, [{**link, 'audio_sha256': manifest['audio_sha256']}])
        with redirect_stdout(io.StringIO()):
            analyze(self.root, 'fixture-01', path, draft)
        self.assertEqual(
            read_json(output / 'summary.json')['recordings'][0]['alignment_draft_event_counts'],
            {'matched': 1},
        )

    def test_pending_review_is_not_interpreted_as_zero(self):
        output = self.intake_fixture()
        path = output / 'reviewed.jsonl'
        row, other = read_jsonl(output / 'review-template.jsonl')
        row.update(reviewer_code='coder-01')
        write_jsonl(path, [row, other])
        with self.assertRaisesRegex(ValueError, 'Verified clause'):
            analyze(self.root, 'fixture-01', path, None)
