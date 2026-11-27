"""Keep the anonymous reading and model targets identical and their work contexts intact."""

import unittest

from src.written_rhyme_sources import blind_packet, period_evidence, work_rows
from src.yu_review_sources import norm


class WrittenRhymeSourcesTest(unittest.TestCase):
    def test_unique_spaced_targets_preserve_full_edition_and_section_context(self):
        sentences = [f'清風照古城{c}。' for c in '甲乙丙丁戊己庚辛壬癸']
        groups = [sentences[:5], sentences[5:]]
        rows = work_rows('W01', '某甲', 'fu', groups, norm)
        self.assertEqual([r['text'] for r in rows], sentences)
        self.assertEqual([r['order'] for r in rows if r['target']], [2, 4, 6, 8, 10])
        reading, blind = blind_packet(rows)
        self.assertEqual(set(blind.values()), {r['id'] for r in rows if r['target']})
        self.assertEqual(len(blind), len(reading))
        self.assertTrue(all(set(r) == {'blind_id', 'text', 'before', 'after'} for r in reading))
        edge = next(r for r in reading if blind[r['blind_id']] == 'W01-S006')
        self.assertEqual(edge['before'], [])
        self.assertEqual(edge['after'], sentences[6:8])
        self.assertEqual(blind_packet(rows), (reading, blind))

    def test_short_and_repeated_sentences_stay_as_context_but_never_targets(self):
        repeated = '文心可會悠悠。'
        eligible = [f'文心可會悠{c}。' for c in '甲乙丙丁戊']
        rows = work_rows('W02', '某乙', 'prose', [[repeated, *eligible, repeated, '臣某言。']], norm)
        self.assertEqual([r['text'] for r in rows if r['target']], eligible)
        with self.assertRaisesRegex(ValueError, 'fewer than five'):
            work_rows('W02', '某乙', 'prose', [[repeated, *eligible[:3], repeated, '臣某言。']], norm)

    def test_period_citation_belongs_to_credited_author_and_not_to_a_title(self):
        catalog = ('== 某甲 ==\n甲，貞元七年進士。\n===[[文甲]]===\n{{:文甲}}\n'
                   '=某乙=\n乙，尚書郎。\n==[[大曆賀表]]==\n{{:大曆賀表}}\n'
                   '=某丙=\n丙，開元中選吏。\n==[[文丙]]==\n{{:文丙}}')
        evidence = period_evidence(catalog, '某甲', '文甲', '文甲', 600)
        self.assertEqual(evidence['text'], '甲，貞元七年進士')
        for author, page, volume in [('某乙', '大曆賀表', 650), ('某甲', '文丙', 650), ('某甲', '文甲', 860)]:
            with self.assertRaises(ValueError):
                period_evidence(catalog, author, page, page, volume)
