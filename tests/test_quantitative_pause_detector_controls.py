from array import array
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.phonology.annotate import syllable_slots
from src.quantitative_pause_detector_controls import (
    GUARDS_MS, SAMPLE_RATE, apply_gain, checked_passages, evaluate_recording, find_cut, sample_count, score_site,
    summarize_cases,
)
from src.quantitative_pause_detector import detect_relative
from src.stage6_listening import digest


class IndependentPauseControlsTests(unittest.TestCase):
    def test_cut_is_internal_deterministic_and_rejects_silence(self):
        samples = array('h', [3000, -3000] * 12000)
        self.assertEqual(find_cut(samples, SAMPLE_RATE), 12000)
        self.assertIsNone(find_cut(array('h', [0]) * len(samples), SAMPLE_RATE))

    def test_attenuated_carrier_is_rounded_before_inserting_samples(self):
        samples = array('h', [32767, -32768, 1, 0])
        self.assertEqual(apply_gain(samples, -12), array('h', [8231, -8231, 0, 0]))
        self.assertIs(apply_gain(samples, 0), samples)

    def test_site_scoring_counts_false_targets_and_ignores_offsite_pauses(self):
        rate = SAMPLE_RATE
        cut = 24000
        guard = sample_count(rate, 120)
        offsite = {'start_sample': 0, 'end_sample': 4000, 'resumption_eligible': True}
        correct = {'start_sample': cut - 30, 'end_sample': cut + guard + 90, 'resumption_eligible': False}
        hit = score_site([offsite, correct], cut, guard, rate)
        self.assertEqual(hit['outcome'], 'hit')
        self.assertFalse(hit['usable_resume'])
        self.assertEqual(hit['absolute_edge_error_ms'], [1.25, 3.75])
        self.assertTrue(hit['both_edges_within_tolerance'])
        self.assertEqual(score_site([correct], cut, 0, rate)['outcome'], 'false_pause')
        self.assertEqual(score_site([offsite], cut, 0, rate)['outcome'], 'no_pause')

    def test_active_carrier_produces_paired_control_results(self):
        samples = array('h', [3000, -3000] * 12000)
        case = evaluate_recording(samples, SAMPLE_RATE, detect_relative)
        self.assertEqual(case['status'], 'scored')
        self.assertEqual(len(case['variants']), 2 * len(GUARDS_MS))
        self.assertTrue(all(row['samples_preserved_after_removing_guard'] for row in case['variants']))
        summary = summarize_cases([case])
        for gain in ('0', '-12'):
            relative = summary['by_gain'][gain]['relative']
            for ms in ('0', '60'):
                self.assertEqual(relative[ms]['false_pauses'], 0)
            for ms in ('120', '240', '400'):
                self.assertEqual(relative[ms]['hits'], 1)
                self.assertEqual(relative[ms]['usable_resume_hits'], 1)

    def test_fresh_replication_rejects_an_author_from_the_original_archive(self):
        with TemporaryDirectory() as temp:
            location = Path(temp)

            def save(name, value, *, rows=False):
                path = location / name
                payload = '\n'.join(json.dumps(row) for row in value) if rows else json.dumps(value)
                path.write_text(payload, encoding='utf-8')
                return path

            pins, witnesses, rendered = [], [], []
            for i, (pid, period, genre, text) in enumerate((
                ('PSD1P', 'sixth-century', 'parallel_prose', '彼'),
                ('PSD1C', 'sixth-century', 'comparison_prose', '此'),
                ('PET1P', 'early-tang', 'parallel_prose', '古'),
                ('PET1C', 'early-tang', 'comparison_prose', '今'),
            )):
                pin = {'passage_id': pid, 'source_id': str(i), 'genre': genre, 'period': period,
                       'pair_id': period, 'han_count': 1, 'text_sha256': sha256(text.encode()).hexdigest()}
                source = {'source_id': str(i), 'work_id': f'work-{i}', 'author': f'author-{i}', 'source_url': str(i),
                          'revision_id': i, 'license': 'CC-BY-SA-4.0', 'attribution': str(i)}
                pins.append(pin)
                witnesses.append(source)
                rendered.append({**source, **pin, 'text': text, 'slots': syllable_slots(text)})
            paths = {
                'replication_pins': save('pins', {'passages': pins, 'sources': witnesses}),
                'evaluation_annotations': save('rendered', rendered, rows=True),
                'archived_annotations': save('expansion', [], rows=True),
                'original_annotations': save('original', [], rows=True),
                'quantitative-report': save('v4-inventory', [], rows=True),
                'historical-increment': save('historical-inventory', [], rows=True),
            }
            paths['development_v4_report'] = save(
                'v4', {'source_sha256': {'passages': digest(paths['quantitative-report'])}})
            paths['development_historical_observations'] = save(
                'historical', {'source_sha256': {'annotated': digest(paths['historical-increment'])}})
            self.assertEqual(set(checked_passages(paths)), {row['passage_id'] for row in pins})
            paths['original_annotations'] = save('original', [{
                'work_id': 'earlier', 'author': rendered[0]['author'], 'text_sha256': 'prior',
            }], rows=True)
            with self.assertRaisesRegex(ValueError, 'independent pinned'):
                checked_passages(paths)


if __name__ == '__main__':
    unittest.main()
