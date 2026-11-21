import hashlib
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import wave

from src import stage7_audio as audio


RATE = 8000
INTERVALS = ((0.00, 0.10), (0.31, 0.41), (0.46, 0.50), (0.51, 0.56),
             (0.60, 0.64), (0.65, 0.71), (0.77, 0.82), (None, None))


class FixtureWaveform:
    def __init__(self, path):
        with wave.open(str(path), 'rb') as stream:
            data = stream.readframes(stream.getnframes())
            self.samples = [value for value, in struct.iter_unpack('<h', data)]
        self.duration_s = len(self.samples) / RATE
        self.octave_jump_count = 0

    def samples_in(self, bounds):
        start, end = (round(point * RATE) for point in bounds)
        return self.samples[start:end]

    def pitch_in(self, bounds):
        return []


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


class AudioScoreTests(TestCase):
    def setUp(self):
        workspace = TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name).resolve()
        self.wav = self.root / 'audio/raw/fixture.wav'
        self.wav.parent.mkdir(parents=True)
        with wave.open(str(self.wav), 'wb') as stream:
            stream.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            samples = [0] * RATE
            for start, end in INTERVALS[:-1]:
                left, right = round(start * RATE), round(end * RATE)
                samples[left:right] = [900] * (right - left)
            stream.writeframes(struct.pack(f'<{len(samples)}h', *samples))

        text = '甲乙，丙丁，戊己，庚辛。'
        checksum = hashlib.sha256(text.encode('utf-8')).hexdigest()
        slots = [{'slot_index': i, 'clause_index': i // 2, 'boundary_after': i % 2, 'char': char,
                  'marks_after': '。' if i == 7 else '，' if i % 2 else '',
                  'readings': {'mandarin': {'candidates': [{'reading': 'jia3'}]}}}
                 for i, char in enumerate('甲乙丙丁戊己庚辛')]
        self.passage = {'passage_id': 'fixture', 'text': text, 'text_sha256': checksum, 'slots': slots}
        self.recording = {'recording_id': 'fixture-wav', 'kind': 'synthetic', 'speaker': 'fixture voice',
                          'variety': 'cmn', 'style': 'fixture', 'recording_rights': 'fixture',
                          'passage_id': 'fixture', 'text_sha256': checksum,
                          'audio_path': str(self.wav.relative_to(self.root)), **audio.wav_metadata(self.wav)}
        self.events = [{**self.recording, 'event_index': i, 'slot_index': i,
                        'start_s': start, 'end_s': end, 'status': 'matched' if start is not None else 'omission',
                        'realized_reading': None}
                       for i, (start, end) in enumerate(INTERVALS)]
        write_rows(self.root / audio.SYNTHETIC_MANIFEST, [self.recording])

    def test_verified_stage6_cache_reports_timing_and_conservative_cues(self):
        legacy_edition_fields = [{key: value for key, value in row.items() if key != 'text_sha256'}
                                 for row in self.events]
        write_rows(self.root / audio.PILOT_DRAFTS[0], legacy_edition_fields)
        with patch.object(audio.features, 'Waveform', FixtureWaveform):
            result = audio.score_audio(self.root, self.wav, self.passage)
        self.assertEqual(result['duration_s'], 1)
        self.assertEqual(result['summary']['slots_measured'], 7)
        self.assertEqual(result['summary']['pronunciations_recorded'], 0)
        self.assertEqual(result['clauses'][-1]['draft_span_start_s'], 0.77)
        self.assertIsNone(result['clauses'][-1]['start_s'])
        self.assertEqual([row['category'] for row in result['observations']],
                         ['internal_quiet_gap', 'relatively_slow_clause', 'incomplete_acoustic_link'])
        self.assertAlmostEqual(result['observations'][0]['evidence']['gap_ms'], 210)

    def test_rejects_untied_legacy_alignment_and_stale_checksum(self):
        write_rows(self.root / audio.PILOT_DRAFTS[1],
                   [{key: value for key, value in row.items() if key != 'audio_sha256'} for row in self.events])
        with self.assertRaisesRegex(ValueError, 'No checksum-bound alignment'):
            audio.score_audio(self.root, self.wav, self.passage)
        stale = [{**row, 'audio_sha256': 'bad'} for row in self.events]
        write_rows(self.root / audio.PILOT_DRAFTS[0], stale)
        with self.assertRaisesRegex(ValueError, 'exact waveform and annotated edition'):
            audio.score_audio(self.root, self.wav, self.passage)

    def test_fresh_decode_cache_is_reusable_and_requires_slurm(self):
        with patch.dict(audio.os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Slurm GPU allocation'):
                audio.score_audio(self.root, self.wav, self.passage, decode=True)
        with patch.object(audio.features, 'Waveform', FixtureWaveform):
            with patch.object(audio, 'decode_waveform', return_value=self.events) as decode:
                first = audio.score_audio(self.root, self.wav, self.passage, decode=True)
                second = audio.score_audio(self.root, self.wav, self.passage)
        self.assertEqual(first, second)
        decode.assert_called_once()
        self.assertEqual(len(list((self.root / audio.CACHE).glob('*.json'))), 1)

    def test_explicit_alignment_requires_checksum_and_reviewed_human_readings(self):
        path = self.root / 'audio/derived/external.jsonl'
        reading = [{**row, 'realized_reading': 'jia3'} if row['status'] == 'matched' else row for row in self.events]
        write_rows(path, reading)
        with self.assertRaisesRegex(ValueError, 'verified performed reading'):
            audio.score_audio(self.root, self.wav, self.passage, alignment=path)
        write_rows(path, [{**row, 'text_sha256': 'stale'} for row in self.events])
        with self.assertRaisesRegex(ValueError, 'exact waveform and annotated edition'):
            audio.score_audio(self.root, self.wav, self.passage, alignment=path)

    def test_explicit_human_review_counts_only_documented_pronunciation(self):
        manifest = self.root / 'audio/manifests/reviewed.jsonl'
        write_rows(manifest, [{**self.recording, 'kind': 'human', 'consent_id': 'fixture consent'}])
        path = self.root / 'audio/derived/reviewed.jsonl'
        rows = [{**row, 'kind': 'human', 'alignment_source': 'fixture_review'} for row in self.events]
        rows[0].update(status='reviewed', realized_reading='jia3')
        write_rows(path, rows)
        with patch.object(audio.features, 'Waveform', FixtureWaveform):
            result = audio.score_audio(self.root, self.wav, self.passage, manifest=manifest, alignment=path)
        self.assertEqual(result['summary']['pronunciations_recorded'], 1)
        self.assertEqual(result['reviewed_events'], 1)
        self.assertEqual(result['recording']['consent_id'], 'fixture consent')
