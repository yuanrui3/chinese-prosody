import hashlib
import json
from pathlib import Path
from struct import pack
from tempfile import TemporaryDirectory
import unittest
import wave

from src.expansion_tasks import PILOT, SYNTHETIC, matched_pairs, prepare
from src.followup_pilot import DESTINATION, build
from src.stage6_listening import PRIVATE_DIR, STIMULUS_DIR, read_json
from src.stage6_production import production_stimuli


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


def passage_fixture():
    rows = []
    for number, first in enumerate('子丑寅卯辰巳午未'):
        passage = f'{first}有千言，四方所聞。'
        rows.append({
            'passage_id': f'fixture-passage-{number}',
            'work_id': f'fixture-work-{number}',
            'author': f'fixture-author-{number}',
            'title': f'fixture-title-{number}',
            'pair_id': f'fixture-pair-{number // 2}',
            'period': 'sixth-century' if number % 4 < 2 else 'early-tang',
            'genre': 'parallel_prose' if number % 2 == 0 else 'comparison_prose',
            'match_topic': 'fixture-matching-topic',
            'task': 'listening' if number < 4 else 'read_aloud',
            'source_url': f'https://example.test/work/{number}',
            'revision_id': str(number),
            'text': passage,
            'text_sha256': hashlib.sha256(passage.encode()).hexdigest(),
            'license': 'CC-BY-SA-4.0',
            'work_rights': 'Public domain',
            'attribution': f'fixture-source-{number}',
        })
    return rows


def recording_fixture(root, passages):
    recordings = []
    for number, row in enumerate(passages):
        relative = f'audio/synthetic/clip-{number}.wav'
        clip = root / relative
        clip.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(clip), 'wb') as stream:
            stream.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            stream.writeframes(pack('<hh', 600 + number, -600) * 480)
        recordings.append({
            'recording_id': f'fixture-voice-{number}',
            'passage_id': row['passage_id'],
            'audio_path': relative,
            'audio_sha256': hashlib.sha256(clip.read_bytes()).hexdigest(),
            'sample_rate': 24000,
            'kind': 'synthetic',
            'variety': 'cmn',
            'speaker': 'zm_010',
            'speed': 0.9,
            'model_license': 'Apache-2.0',
            'text_license': row['license'],
            'text_sha256': row['text_sha256'],
            'text_revision': row['revision_id'],
            'text_source_url': row['source_url'],
        })
    return recordings


class ExpansionTasksTest(unittest.TestCase):
    def test_followup_forms_balance_positions_and_preserve_source_audio(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = passage_fixture()
            write_rows(root / PILOT, rows)
            write_rows(root / SYNTHETIC, recording_fixture(root, rows[:4]))
            prepare(root)
            old_page = root / 'audio/stage6/listening-web/with-text.html'
            original = old_page.read_bytes()
            counts = build(root)
            self.assertEqual(counts['listening_forms'], 8)
            self.assertEqual(counts['read_aloud_forms'], 4)
            self.assertEqual(counts, build(root))
            self.assertEqual(old_page.read_bytes(), original)

            packet = root / DESTINATION
            design = read_json(packet / 'restricted/design.json')
            forms = design['listening_forms']
            hashes = {tuple(sorted(form['wav_sha256_in_play_order'])) for form in forms.values()}
            self.assertEqual(len(hashes), 1)
            self.assertEqual(len(hashes.pop()), 4)
            for code, form in forms.items():
                html = (packet / f'participant/listening/{code}.html').read_text(encoding='utf-8')
                self.assertIn(f'<code>{code}</code>', html)
                self.assertEqual(html.count('class="transcript"'),
                                 4 if form['presentation'] == 'text_supported' else 0)
                for row in rows[4:]:
                    self.assertNotIn(row['text'], html)
            orders = list(design['read_aloud_forms'].values())
            for column in zip(*orders):
                self.assertEqual(set(column), {'R01', 'R02', 'R03', 'R04'})
            for code in design['read_aloud_forms']:
                page = (packet / f'participant/read-aloud/{code}.html').read_text(encoding='utf-8')
                self.assertNotIn('<audio ', page)
                for row in rows[:4]:
                    self.assertNotIn(row['text'], page)

    def test_preparation_preserves_independent_stimuli_and_saved_assignments(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = passage_fixture()
            write_rows(root / PILOT, rows)
            self.assertEqual(prepare(root, production_only=True), {'read_aloud_prompts': 4})
            self.assertFalse((root / STIMULUS_DIR).exists())
            write_rows(root / SYNTHETIC, recording_fixture(root, rows[:4]))
            result = prepare(root)
            self.assertEqual(result['listening_pairs'], 2)
            self.assertEqual(result, prepare(root))

            stage = root / 'audio/stage6'
            key = read_json(stage / 'restricted/production-key.json')
            self.assertEqual(set(key['prompts']), {'R01', 'R02', 'R03', 'R04'})
            self.assertEqual({prompt['text_sha256'] for prompt in key['prompts'].values()},
                             {row['text_sha256'] for row in rows[4:]})
            self.assertEqual({code: row['passage_id'] for code, row in production_stimuli(root).items()},
                             {code: row['passage_id'] for code, row in key['prompts'].items()})
            listening_key = read_json(root / PRIVATE_DIR / 'unblinding.json')
            listening_ids = {trial[side]['text_provenance']['passage_id']
                             for trial in listening_key['trials'] for side in 'AB'}
            self.assertEqual(listening_ids, {row['passage_id'] for row in rows[:4]})

            blind = (stage / 'listening-web/index.html').read_text(encoding='utf-8')
            transcript = (stage / 'listening-web/with-text.html').read_text(encoding='utf-8')
            production = (stage / 'production/read-aloud.html').read_text(encoding='utf-8')
            self.assertEqual(blind.count('data:audio/wav;base64,'), 4)
            self.assertIn('E01=＿ E02=＿', blind)
            self.assertEqual(blind.count('type="radio"'), 16)
            self.assertNotIn('data:audio', production)
            for row in rows:
                self.assertNotIn(row['text'], blind)
                self.assertEqual(row['text'] in transcript, row['task'] == 'listening')
                self.assertEqual(row['text'] in production, row['task'] == 'read_aloud')
                for page in (blind, transcript, production):
                    self.assertNotIn(row['title'], page)
                    self.assertNotIn(row['match_topic'], page)

    def test_rejects_reused_authorship_and_period_imbalance(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'annotated.jsonl'
            rows = passage_fixture()
            rows[4]['author'] = rows[0]['author']
            write_rows(path, rows)
            with self.assertRaisesRegex(ValueError, 'distinct nonempty author'):
                matched_pairs(path)

            rows = passage_fixture()
            for row in rows[6:]:
                row['period'] = 'sixth-century'
            write_rows(path, rows)
            with self.assertRaisesRegex(ValueError, 'same period balance'):
                matched_pairs(path)
