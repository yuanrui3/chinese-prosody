"""Regression tests for exact prose segmentation and uncertain readings."""

import unittest

from src.stage7_text import annotate_text, score_passage, score_text


def candidate(tone, rhyme):
    return {'id': f'{tone}-{rhyme}', 'tone': tone, 'pingze': '平' if tone == '平' else '仄', 'rhyme': rhyme}


class Stage7TextTest(unittest.TestCase):
    def test_paragraphs_keep_unicode_offsets_and_global_clause_ids(self):
        text = '「𠮷甲，乙。」\r\n \r\nProse note\n\n丙。\n丁戊。'
        report = score_text(text)
        paragraphs = report['paragraphs']
        self.assertEqual([paragraph['text'] for paragraph in paragraphs],
                         ['「𠮷甲，乙。」', 'Prose note', '丙。\n丁戊。'])
        clauses = [clause for paragraph in paragraphs for clause in paragraph['clauses']]
        self.assertEqual([clause['clause_index'] for clause in clauses], [0, 1, 2, 3])
        self.assertEqual([clause['text'] for clause in clauses], ['「𠮷甲，', '乙。」', '丙。\n', '丁戊。'])
        self.assertTrue(all(text[clause['start']:clause['end']] == clause['text'] for clause in clauses))
        self.assertEqual([slot['slot_index'] for clause in clauses for slot in clause['slots']], list(range(6)))
        self.assertEqual(paragraphs[1]['metrics']['guangyun']['clause_mean_slots']['eligible'], 0)
        self.assertFalse(report['reference']['historical']['guangyun']['available'])
        self.assertEqual(report['observations'], [])

    def test_ambiguous_ending_is_bounded_without_selecting_a_reading(self):
        lexicon = {'甲': [candidate('平', '麻'), candidate('上', '馬')]}
        report = score_text('甲，甲。', guangyun=lexicon)
        estimate = report['metrics']['guangyun']['clause_end_pz_alternation']
        self.assertEqual(estimate, {'value': None, 'eligible': 1, 'usable': 0,
                                    'lower': 0.0, 'upper': 1.0, 'bounded': 1})
        readings = report['paragraphs'][0]['clauses'][0]['slots'][0]['readings']['guangyun']
        self.assertEqual(readings['status'], 'ambiguous')
        self.assertEqual(readings['candidates'], lexicon['甲'])
        self.assertIsNone(readings['selected'])

    def test_local_patterns_need_an_established_run(self):
        text = '甲甲，乙乙，丙丙，丁丁丁丁，戊戊戊戊。'
        lexicon = {'甲': [candidate('平', '歌')], '乙': [candidate('去', '歌')],
                   '丙': [candidate('平', '歌')], '丁': [candidate('平', '麻')],
                   '戊': [candidate('入', '葉')]}
        report = score_text(text, guangyun=lexicon)
        observations = {row['metric']: row for row in report['observations']}
        self.assertEqual(observations['clause_end_pz_alternation']['clause_indices'], [0, 1, 2, 3])
        self.assertEqual(observations['clause_end_rhyme_repeat']['clause_indices'], [0, 1, 2, 3])
        self.assertIn('2 consecutive 4-slot clauses', observations['clause_npvi']['reason'])
        self.assertTrue(all(row['evidence'] == 'local_pattern' for row in observations.values()))
        clipped = score_text('甲甲，乙乙。\n\n丙丙，丁丁丁丁，戊戊戊戊。', guangyun=lexicon)
        self.assertEqual(clipped['observations'], [])

    def test_pinned_readings_and_provenance_require_exact_input(self):
        text = '甲，乙乙。'
        lexicon = {'甲': [candidate('平', '歌'), candidate('去', '箇')], '乙': [candidate('平', '麻')]}
        cached = annotate_text(text, guangyun=lexicon, passage_id='fixture')
        reading = cached['slots'][0]['readings']['guangyun']
        reading.update(selected=reading['candidates'][0], status='context_reviewed',
                       evidence={'source': 'fixture', 'reason': 'Known reviewed variant.'})
        cached.update(revision_id=123, license='CC-BY-SA-4.0', start_anchor='甲，',
                      parallel_clause_groups=[[[0], [1]]])

        record = annotate_text(text, pinned_passage=cached)
        report = score_passage(record)
        self.assertEqual(record['slots'][0]['readings']['guangyun']['selected'], lexicon['甲'][0])
        self.assertEqual(report['reference']['witness'],
                         {'revision_id': 123, 'license': 'CC-BY-SA-4.0', 'start_anchor': '甲，'})
        self.assertEqual([row['metric'] for row in report['observations']],
                         ['parallel_end_pz_opposition', 'parallel_length_similarity'])
        self.assertEqual([row['rank'] for row in report['observations']], [1, 2])
        with self.assertRaisesRegex(ValueError, 'differs from the pinned edition'):
            annotate_text(text + '\n', pinned_passage=cached)
        with self.assertRaisesRegex(ValueError, 'offsets or boundaries are stale'):
            annotate_text(text, pinned_passage={**cached, 'slots': cached['slots'][1:]})
