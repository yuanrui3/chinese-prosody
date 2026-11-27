"""The whole-work null preserves exposure and trials while relaxing section membership."""

from collections import Counter
from importlib.util import find_spec
import unittest

if find_spec('numpy'):
    from src import masked_rhyme_recovery as m
    from src import masked_rhyme_shuffle_check as diag


@unittest.skipUnless(find_spec('numpy'), 'The existing context scorer uses NumPy on Gilbreth')
class WholeWorkShuffleTest(unittest.TestCase):
    def test_short_sections_are_exactly_invariant_to_the_primary_shuffle(self):
        rows = [m.Ending(str(i), section, str(i), frozenset([group]), '平', True)
                for i, (section, group) in enumerate(zip('abbccc', '東冬東文文冬'))]
        work = m.Work('w', 'X', 'test', 'fu', rows)
        trials = {r.id: {'group': r.group, 'foil': '冬' if r.group == '文' else '文', 'tone': '平'} for r in rows}
        def scores(draw):
            _, _, details = m.evaluate_work(work, trials, shuffle=draw, details=True)
            return {r['id']: r['outcomes'] for r in details}
        for draw in range(12):
            self.assertEqual(scores(None), scores(draw))
        randomized = diag.permute_work(work, 0)
        self.assertEqual([r.section for r in rows], [r.section for r in randomized.rows])
        self.assertEqual(Counter((r.id,r.group) for r in rows), Counter((r.id,r.group) for r in randomized.rows))
        self.assertNotEqual([r.id for r in rows], [r.id for r in randomized.rows])
        self.assertEqual(diag.short_sections(work, trials)['3'], {'sections': 1, 'rows': 3, 'trials': 3})
