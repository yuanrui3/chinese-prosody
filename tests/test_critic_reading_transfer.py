"""Check the representation of historical alternatives absent from the headword."""

from importlib.util import find_spec
import unittest

if find_spec('numpy'):
    from src.critic_reading_transfer import candidate_for


@unittest.skipUnless(find_spec('numpy'), 'The transfer scorer uses NumPy on Gilbreth')
class HistoricalAlternativeTest(unittest.TestCase):
    def test_lower_speller_needs_one_category_or_a_unanimous_complete_cut(self):
        def entry(tone, rhyme, cut):
            return {'tone': tone, 'rhyme': rhyme, 'entries': [{'fanqie': cut}]}

        lex = {'guangyun': {'角': [entry('入', '屋', '盧谷'), entry('入', '覺', '古岳')],
                            '㱿': [entry('入', '覺', '苦角')]}}
        selector = {'lower': '角', 'tone': '入', 'rhyme': '覺', 'cut': '苦角'}
        projection = candidate_for('殼', selector, lex, [])
        self.assertEqual(projection['pingze'], '仄')
        self.assertEqual(projection['rhyme'], '覺')
        self.assertNotIn('initial', projection)
        lex['guangyun']['另一條'] = [entry('入', '屋', '苦角')]
        with self.assertRaisesRegex(ValueError, 'underdetermined'):
            candidate_for('殼', selector, lex, [])

    def test_level_tone_alone_cannot_make_a_graph_native(self):
        yu = {'id': '汙虞', 'tone': '平', 'rhyme': '虞'}
        mo = {'id': '烏模', 'tone': '平', 'rhyme': '模'}
        lex = {'guangyun': {'汙': [yu], '烏': [mo]}}
        target = {'tone': '平', 'rhyme': '模'}
        with self.assertRaisesRegex(ValueError, 'matched 0'):
            candidate_for('汙', target, lex, [yu])
        self.assertEqual(candidate_for('汙', {**target, 'donor': '烏'}, lex, [yu]), mo)
