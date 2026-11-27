"""Verify work-level isolation, independent genre selection, and the masked reader packet."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.work_weighted_sources import build_rows, indexed_titles, read_work, stratum
from src.written_rhyme_sources import blind_packet, period_evidence
from src.yu_review_sources import balanced, norm


class WorkWeightedSourcesTest(unittest.TestCase):
    def test_six_spaced_targets_with_context_limited_to_its_own_paragraph(self):
        sentences = [f'江南細雨入城{c}。' for c in '甲乙丙丁戊己庚辛壬癸子丑']
        rows = build_rows('W01', '某甲', 'fu', [sentences[:7], sentences[7:]], norm)
        self.assertEqual([r['text'] for r in rows], sentences)
        targets = [r for r in rows if r['target']]
        self.assertEqual([r['order'] for r in targets], [2, 4, 6, 8, 10, 12])
        reading, key = blind_packet(rows)
        self.assertEqual(set(key.values()), {r['id'] for r in targets})
        self.assertTrue(all(set(r) == {'blind_id', 'before', 'text', 'after'} for r in reading))
        first = next(r for r in reading if key[r['blind_id']] == 'W01-S008')
        self.assertEqual(first['before'], [])
        self.assertEqual(first['after'], sentences[8:10])
        repeated = sentences[0]
        with self.assertRaisesRegex(ValueError, 'fewer than six unique'):
            build_rows('W02', '某乙', 'prose', [[*sentences[:6], repeated, '臣言。']], norm)

    def test_discursive_work_with_no_paired_clauses_qualifies(self):
        plain = ''.join(f'論其治國之要{c}。' for c in '甲乙丙丁戊己庚辛')
        witness = ('{{Header|title=議政論|author=某甲|times=唐|from=全唐文/卷0612|}}'
                   '<onlyinclude>' + plain + '</onlyinclude>')
        author, _, edition, sections = read_work(witness, '議政論', 'prose')
        self.assertEqual((author, edition), ('某甲', '全唐文/卷0612'))
        self.assertFalse(any(balanced(t) for t in sections[0]))
        with self.assertRaises(ValueError):
            read_work(witness.replace(plain, '其詩曰：' + plain), '議政論', 'prose')
        with self.assertRaises(ValueError):
            read_work(witness, '賀平亂表', 'prose')
        with self.assertRaisesRegex(ValueError, 'assigned rhyming'):
            read_work(witness.replace('議政論', '秋風賦'), '秋風賦', 'fu')

    def test_author_period_comes_from_credited_notice_and_maps_to_matching_stratum(self):
        raw = ('=[[Author:某甲|某甲]]=\n甲，元和七年舉進士。\n==[[文甲記]]==\n{{:文甲記}}\n'
               '=某乙=\n乙，太宗朝為令。\n==[[文乙賦]]==\n{{:文乙賦}}\n'
               '=某丙=\n丙，官尚書郎。\n==[[大中時論]]==\n{{:大中時論}}')
        with TemporaryDirectory() as folder:
            path = Path(folder) / '615-999.wiki'
            path.write_text(raw)
            self.assertEqual(indexed_titles(path, 615), [
                ('文甲記', '某甲', 615, 'prose'), ('文乙賦', '某乙', 615, 'fu'),
                ('大中時論', '某丙', 615, 'prose')])
        one = period_evidence(raw, '某甲', '文甲記', '文甲記', 615)
        two = period_evidence(raw, '某乙', '文乙賦', '文乙賦', 615)
        self.assertEqual(one['text'], '甲，元和七年舉進士')
        self.assertEqual(stratum(one['marker']), stratum('貞元'))
        self.assertNotEqual(stratum(one['marker']), stratum(two['marker']))
        self.assertNotEqual(stratum('大中時'), stratum(two['marker']))
        with self.assertRaisesRegex(ValueError, 'author-specific'):
            period_evidence(raw, '某丙', '大中時論', '大中時論', 615)

    def test_reject_marked_lacunae_even_in_context_for_both_genres(self):
        text = '登樓闕觀城邑。' + ''.join(f'春山遠近凝翠{c}。' for c in '甲乙丙丁戊己庚')
        for genre, page in [('prose', '城邑記'), ('fu', '城邑賦（以「天地日月」為韻）')]:
            witness = ('{{Header|title=' + page + '|author=某甲|times=唐|from=全唐文/卷0612|}}'
                       '<onlyinclude>' + text + '</onlyinclude>')
            self.assertEqual(read_work(witness, page, genre)[3][0][0], '登樓闕觀城邑。')
            for mark in ('（闕三字）', '（闕二字）', '(原缺)', '〔缺字〕', '脫數字', '▢', '□'):
                with self.subTest(genre=genre, mark=mark), self.assertRaises(ValueError):
                    read_work(witness.replace('觀城邑', '觀' + mark + '城邑'), page, genre)
