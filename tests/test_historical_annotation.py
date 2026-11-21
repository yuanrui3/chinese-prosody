"""Regression checks for the Stage 3 historical reading interface."""

import json
import os
from pathlib import Path
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'data' / 'phonology'))
from annotate import TIERS, annotate_passage


REVIEWS = json.loads((PROJECT / 'data' / 'pilot' / 'context-reviews.json').read_text(encoding='utf-8'))


def annotate(text, lexicons, *, passage_id='fixture', variants=None, reviews=()):
    return annotate_passage({'text': text, 'passage_id': passage_id},
                            {tier: lexicons.get(tier, {}) for tier in TIERS}, variants or {}, reviews)


class HistoricalAnnotationTest(unittest.TestCase):
    def test_guangyun_lexical_choice_preserves_the_alternate(self):
        # 廣韻 四庫全書 witness, vols. 3–4, 晧 and 號 sections.
        # https://zh.wikisource.org/zh-hant/廣韻_(四庫全書本)/卷3
        # https://zh.wikisource.org/zh-hant/廣韻_(四庫全書本)/卷4
        rainwater = {'id': 'rainwater', 'position': '來開一豪上', 'rhyme': '晧', 'tone': '上', 'pingze': '仄'}
        flood = {'id': 'flood', 'position': '來開一豪去', 'rhyme': '號', 'tone': '去', 'pingze': '仄'}
        readings = {'guangyun': {'潦': [rainwater, flood]}}
        snippet = '潦水盡而寒潭清'
        review = [decision for decision in REVIEWS if decision['passage_id'] == 'ET01']
        unresolved = annotate(snippet, readings)['slots'][0]['readings']['guangyun']
        resolved = annotate(snippet, readings, passage_id='ET01', reviews=review)['slots'][0]['readings']['guangyun']
        self.assertEqual(unresolved['status'], 'ambiguous')
        self.assertIsNone(unresolved['selected'])
        self.assertEqual(resolved['status'], 'context_reviewed')
        self.assertEqual(resolved['selected']['tone'], '上')
        self.assertEqual(resolved['selected']['rhyme'], '晧')
        self.assertEqual(resolved['candidates'], [rainwater, flood])

    def test_reviewed_mandarin_and_historical_readings_are_separate(self):
        # Ministry of Education entry 還, meaning return.
        # https://dict.revised.moe.edu.tw/dictView.jsp?ID=5181&q=1&word=%E9%82%84
        review = [decision for decision in REVIEWS if decision['passage_id'] == 'SD01']
        source = {'mandarin': {'還': [{'id': 'huan', 'reading': 'huán'}, {'id': 'hai', 'reading': 'hái'}]}}
        slots = annotate('將軍一去；壯士不還。', source, passage_id='SD01', reviews=review)['slots']
        self.assertEqual([slot['clause_index'] for slot in slots], [0] * 4 + [1] * 4)
        self.assertEqual(slots[3]['marks_after'], '；')
        self.assertEqual(slots[-1]['offset'], 8)
        tiers = slots[-1]['readings']
        self.assertEqual(tiers['mandarin']['selected']['reading'], 'huán')
        self.assertEqual(tiers['guangyun']['status'], 'missing')
        self.assertIsNone(tiers['guangyun']['selected'])

    def test_pingshui_variant_lookup_preserves_witness_and_provenance(self):
        # 平水韻 下平聲十一尤 contains 樓.
        # https://zh.wikisource.org/wiki/平水韻#下平聲十一尤
        candidate = {'id': 'you', 'tone': '平', 'pingze': '平', 'rhyme': '下平聲十一尤'}
        slot = annotate('楼。', {'pingshui': {'樓': [candidate]}}, variants={'楼': ['樓']})['slots'][0]
        self.assertEqual(slot['char'], '楼')
        self.assertEqual(slot['readings']['pingshui']['lookup'], 'traditional_variant')
        self.assertEqual(slot['readings']['pingshui']['candidates'], [{**candidate, 'lookup_char': '樓'}])
        self.assertIsNone(slot['readings']['pingshui']['selected'])

    def test_review_fails_when_the_context_is_stale(self):
        review = [decision for decision in REVIEWS if decision['passage_id'] == 'ET01']
        with self.assertRaisesRegex(ValueError, 'must appear exactly once'):
            annotate('潦水。', {}, passage_id='ET01', reviews=review)

    @unittest.skipUnless(os.environ.get('SHUNKOU_ROOT'), 'Set SHUNKOU_ROOT for the materialized pilot smoke check')
    def test_gilbreth_pilot_preserves_two_tone_systems_and_the_prose_pair(self):
        path = Path(os.environ['SHUNKOU_ROOT']) / 'data' / 'pilot' / 'annotated.jsonl'
        with path.open(encoding='utf-8') as stream:
            passages = {row['passage_id']: row for row in map(json.loads, stream)}
        guangyun = passages['ET01']['slots'][0]['readings']['guangyun']
        self.assertEqual(guangyun['selected']['rhyme'], '晧')
        self.assertTrue({'上', '去'} <= {row['tone'] for row in guangyun['candidates']})
        # 《默記》 records both versions of clauses 1–2 in the research edition.
        # https://www.shidianguji.com/zh/book/CZBZZ051/chapter/1kxs7vmwg6230
        for identifier, endings, tones in [('NS01', ('山', '水'), ('平', '仄')),
                                            ('NS02', ('上', '淵'), ('仄', '平'))]:
            slots = passages[identifier]['slots']
            observed = tuple(next(slot for slot in reversed(slots) if slot['clause_index'] == index)
                             for index in (1, 2))
            self.assertEqual(tuple(slot['char'] for slot in observed), endings)
            self.assertEqual(tuple({r['pingze'] for r in slot['readings']['guangyun']['candidates']}
                                   for slot in observed), tuple({tone} for tone in tones))
