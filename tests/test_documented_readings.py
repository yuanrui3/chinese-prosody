"""Occurrence-specific reading, scoring and citation regressions."""

from contextlib import redirect_stderr
from copy import deepcopy
import importlib.util
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.historical_readings import reading_catalog
from src.stage7_cli import main
from src.stage7_prototype import sentence_rows
from src.stage7_render import render_html, render_markdown
from src.stage7_text import annotate_text, score_passage


def candidate(tone, rhyme):
    return {'id': f'{tone}-{rhyme}', 'tone': tone, 'pingze': '平' if tone == '平' else '仄', 'rhyme': rhyme}


NI = [candidate('平', '齊'), candidate('去', '霽'), candidate('入', '屑')]
SHEN = '駕雌霓之連蜷'
LEX = {**{c: [candidate('平', '仙')] for c in '雌之連蜷踡'}, '駕': [candidate('去', '禡')], '霓': NI}


class DocumentedReadingsTest(unittest.TestCase):
    def test_quotation_selects_one_occurrence_and_keeps_other_evidence(self):
        text = '𠮷霓。' + SHEN + '。'
        passage = annotate_text(text, guangyun=LEX, pingshui={'霓': NI},
                                mandarin={'霓': [{'id': 'ni2', 'reading': 'ní'}]})
        other, attested = [s for s in passage['slots'] if s['char'] == '霓']
        self.assertIsNone(other['readings']['guangyun']['selected'])
        self.assertIsNone(attested['readings']['mandarin']['selected'])
        self.assertIsNone(attested['readings']['pingshui']['selected'])
        chosen = attested['readings']['guangyun']
        self.assertEqual((attested['offset'], chosen['selected'], chosen['candidates']), (5, NI[2], NI))
        self.assertIn('oldid=639591', chosen['evidence']['source'])
        report = score_passage(passage)
        clause = report['paragraphs'][0]['clauses'][1]
        self.assertEqual(clause['historical_tones']['guangyun'],
                         {'pattern': '仄平仄平平平', 'longest_level_run': [3, 3]})
        for render in (render_markdown, render_html):
            view = render({'text': report, 'audio': None})
            for token in ('仄平仄平平平', '霓 @ 5', '入聲 · 屑', '平聲 · 齊', '雌霓讀作雌鶂', 'oldid=639591'):
                self.assertIn(token, view)
        open_report = score_passage(annotate_text(SHEN, guangyun=LEX, historical_readings=[]))
        self.assertEqual(open_report['paragraphs'][0]['clauses'][0]['historical_tones']['guangyun'],
                         {'pattern': '仄平?平平平', 'longest_level_run': [3, 5]})

    def test_explicit_reviews_fail_closed_and_preserve_pinned_copy(self):
        review = next(r for r in reading_catalog() if r['anchor'] == SHEN)
        base = annotate_text(SHEN, guangyun=LEX, historical_readings=[])
        saved = deepcopy(base)
        pinned = annotate_text(SHEN, pinned_passage=base, historical_readings=[review])
        self.assertEqual(base, saved)
        self.assertEqual(pinned['slots'][2]['readings']['guangyun']['selected'], NI[2])
        second = {**review, 'source': 'independent test citation'}
        corroborated = annotate_text(SHEN, pinned_passage=pinned, historical_readings=[second])
        linked = corroborated['slots'][2]['readings']['guangyun']
        self.assertEqual(linked['evidence']['source'], review['source'])
        self.assertEqual(linked['additional_evidence'][0]['source'], second['source'])
        for delta in ({'offset': False}, {'offset': 1}, {'char': '蜺'}, {'tier': 'mandarin'}, {'source': ' '},
                      {'witness': []}, {'reason': ''}, {'text_sha256': 'stale'},
                      {'match': {'tone': '上'}}, {'match': {'pingze': '仄'}}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                annotate_text(SHEN, pinned_passage=base, historical_readings=[{**review, **delta}])
        with self.assertRaisesRegex(ValueError, 'Conflicts'):
            annotate_text(SHEN, pinned_passage=pinned, historical_readings=[{**review, 'match': {'tone': '平'}}])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            annotate_text(SHEN, pinned_passage=base, historical_readings=[review, review])
        absent = score_passage(annotate_text(SHEN))
        self.assertTrue(absent['historical_reading_notes'])
        self.assertIsNone(absent['paragraphs'][0]['clauses'][0]['historical_tones']['guangyun']['longest_level_run'])
        repeated = annotate_text(SHEN + '，' + SHEN, guangyun=LEX)
        self.assertTrue(repeated['historical_reading_notes'])
        self.assertTrue(all(not s['readings']['guangyun']['selected'] for s in repeated['slots']))
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            annotate_text(SHEN + SHEN, guangyun=LEX, historical_readings=[review])

    def test_sentence_model_receives_document_reviews_at_rebased_offsets(self):
        text = '卷首。𠮷與，' + SHEN + '！\n\n雌霓連踡。彩霓。'
        rows = sentence_rows(score_passage(annotate_text(text, guangyun=LEX)))
        self.assertEqual([row['section'] for row in rows], ['1', '1', '2', '2'])
        self.assertEqual([len(r['historical_readings']) for r in rows], [0, 1, 1, 0])
        for r in rows:
            self.assertEqual(text[r['start']:r['end']], r['text'])
            again = annotate_text(r['text'], guangyun=LEX, historical_readings=r['historical_readings'])
            for decision in r['historical_readings']:
                slot = next(s for s in again['slots'] if s['offset'] == decision['offset'])
                self.assertEqual(slot['readings']['guangyun']['selected'], NI[2])

    def test_independent_pingshui_review_preserves_the_mandarin_alignment_inputs(self):
        from src.stage7_audio import alignment_cache

        text = '彩霓。'
        lex = dict(guangyun=LEX, pingshui={'霓': NI}, mandarin={'霓': [{'id': 'ni2', 'reading': 'ní'}]})
        base = annotate_text(text, **lex)
        review = dict(anchor='彩霓', offset=1, tier='pingshui', match={'id': NI[0]['id']},
                      source='unit-test witness', reason='Independent reading in this test reference.')
        reviewed = annotate_text(text, **lex, historical_readings=[review])
        self.assertEqual(reviewed['slots'][1]['readings']['pingshui']['selected'], NI[0])
        self.assertIsNone(reviewed['slots'][1]['readings']['guangyun']['selected'])
        self.assertEqual(alignment_cache(Path('.'), base, 'sample.wav', 'test-hash'),
                         alignment_cache(Path('.'), reviewed, 'sample.wav', 'test-hash'))

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'The numerical scorer uses NumPy')
    def test_model_uses_resolved_internal_feet_and_cross_line_rhyme(self):
        from src import quantitative_editorial_context as context

        text = '雌霓連踡'
        lex = {'guangyun': {**LEX, '與': [candidate('平', '魚'), candidate('上', '語'), candidate('去', '御')],
                            '豫': [candidate('去', '御')]}}
        reviewed = context.base.measure(text, lex)
        unresolved = context.base.measure(text, lex, historical_readings=[])
        self.assertEqual(reviewed['guangyun_foot_pz_alternation'], 1)
        self.assertIsNone(unresolved['guangyun_foot_pz_alternation'])
        a = dict(id='a', work_id='w', section='p', text='靈輿安步，周流容與。')
        b = dict(id='b', work_id='w', section='p', text='豫。')
        for reviews, value in ((None, 1), ([], None)):
            rows = [dict(a, historical_readings=reviews), b]
            result = context.in_context(context.describe(rows, lex))
            for key in (('w', 'a'), ('w', 'b')):
                self.assertEqual(result[key][0]['guangyun_cross_line_rhyme'], value)

    def test_cli_custom_review_source_and_output_protection(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            input_file, choices, output = (folder / name for name in ('text.txt', 'reviews.json', 'result.json'))
            input_file.write_text('彩霓。' + SHEN + '。', encoding='utf-8')
            decision = dict(anchor='彩霓', offset=1, char='霓', tier='guangyun', match={'id': NI[0]['id']},
                            source='unit-test witness', reason='Test distinct occurrence.')
            choices.write_text(json.dumps([decision]), encoding='utf-8')
            argv = ['score', str(input_file), '--root', tmp, '--historical-readings', str(choices)]
            with patch('src.stage7_cli.available_lexicons', return_value={'guangyun': LEX}):
                main(argv + ['-o', str(output)])
                self.assertIn('unit-test witness', output.read_text())
                self.assertIn('oldid=639591', output.read_text())
                main(argv + ['--no-reading-catalog', '-o', str(output)])
                self.assertIn('unit-test witness', output.read_text())
                self.assertNotIn('oldid=639591', output.read_text())
            preserved = choices.read_bytes()
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(argv + ['-o', str(choices)])
            self.assertEqual(choices.read_bytes(), preserved)
            choices.write_text('null')
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(argv + ['-o', str(output)])
