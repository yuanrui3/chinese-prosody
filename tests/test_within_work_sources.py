"""Coverage, period pairing, masked context, and previous-screen reservations for ranking."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src import within_work_sources as corpus
from src import work_weighted_sources as matched
from src.yu_review_sources import digest, norm, save


class WithinWorkSourcesTest(unittest.TestCase):
    def test_eight_unique_whole_sentences_keep_punctuation_and_context(self):
        lines = [f'江南細雨來{v}；樓外古木深。' for v in '甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳']
        rows = matched.build_rows('W01', '某甲', 'fu', [lines[:4], lines[4:]], norm, corpus.TARGETS)
        self.assertEqual([r['order'] for r in rows if r['target']], list(range(2,17,2)))
        readers, key = matched.blind_packet(rows)
        self.assertEqual(len(readers), 8)
        for item in readers:
            target = next(row for row in rows if row['id'] == key[item['blind_id']])
            self.assertEqual(item['text'], target['text'])
            self.assertIn('；', item['text'])
        with self.assertRaisesRegex(ValueError, 'fewer than 8'):
            matched.build_rows('W01', '某甲', 'fu', [lines[:7]], norm, corpus.TARGETS)

    def test_catalogue_screen_reserves_undownloaded_work_author_and_hash(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            catalog = folder / 'catalog' / '700-123.wiki'
            catalog.parent.mkdir()
            catalog.write_text('=某甲=\n==[[古城記]]==\n{{:古城記}}\n'
                               '=某乙=\n==[[遠遊賦]]==\n{{:遠遊賦}}\n')
            source = {'screened': [['古城記','no author-specific date'],['fu','遠遊賦','excluded']],
                      'catalogs': {catalog.name:digest(catalog.read_bytes())}}
            save(folder/'sources.json',source)
            authors, titles = set(), set()
            corpus.reserve_logged_candidates(folder, authors, titles, norm)
            self.assertEqual(authors, {'某甲','某乙'})
            self.assertEqual(titles, {'古城記','遠遊賦'})
            catalog.write_text('different')
            with self.assertRaisesRegex(ValueError, 'Changed previously screened'):
                corpus.reserve_logged_candidates(folder, authors, titles, norm)

    def test_full_offline_draw_groups_by_period_and_avoids_earlier_short_target(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            run = root / 'results' / 'new'
            inputs = run / 'inputs'
            catalog = inputs / 'catalog' / '610-802.wiki'
            editions = inputs / 'editions'
            catalog.parent.mkdir(parents=True)
            editions.mkdir()
            # A first eligible-looking prose work contains a six-character earlier sentence.
            chars = '甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午'
            toc, revisions = [], {}
            for i,ch in enumerate(chars):
                genre = 'prose' if i == 0 or i % 2 == 0 else 'fu'
                title = ch + ('山記' if genre == 'prose' else '山賦（以「山川日月」為韻）')
                author = '某' + ch
                marker = '貞元' if i < 9 else '大中' + '初'
                header = f'={author}=\n{author}，{marker}進士。\n==[[{title}]]==\n{{{{:{title}}}}}\n'
                toc.append(header)
                text = ''.join(f'{ch}山春光映古{j}。' for j in '甲乙丙丁戊己庚辛')
                if i == 0:
                    text += '江南細雨入城。'
                witness = ('{{Header|title=' + title + '|author=' + author +
                           '|times=唐|from=全唐文/卷0610|}}<onlyinclude>' + text + '</onlyinclude>')
                revisions[title] = 500 + i
                (editions / f'{500+i}.wiki').write_text(witness)
            catalog.write_text(''.join(toc))
            save(inputs/'fetched-revisions.json',revisions)
            reservation = (set(), set(), {'江南細雨入城'}, {}, norm, set(), [])
            with patch.object(corpus, 'previous', return_value=reservation), \
                 patch.object(matched, 'catalogue', return_value={610:catalog}):
                corpus.acquire(root, run)
            sources = json.loads((inputs / 'sources.json').read_bytes())
            self.assertIn(['甲山記','identical earlier sentence'], sources['screened'])
            self.assertEqual(len({w['author'] for w in sources['works']}), 16)
            self.assertEqual({w['targets'] for w in sources['works']},{8})
            for i in range(8):
                pair = sources['works'][2*i:2*i+2]
                self.assertEqual({w['genre'] for w in pair}, {'prose','fu'})
                self.assertEqual(len({w['period_evidence']['stratum'] for w in pair}),1)
            blind = json.loads((inputs/'reading.json').read_bytes())
            self.assertEqual([r['blind_id'] for r in blind], [f'B{i:03}' for i in range(1,129)])
            seal = json.loads((inputs/'source-seal.json').read_bytes())
            for name, verified in seal.items():
                self.assertEqual(digest((inputs/name).read_bytes()), verified)
