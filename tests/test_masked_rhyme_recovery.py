"""Masked exact-group comparisons and the safeguards on their denominators."""

from importlib.util import find_spec
import unittest

if find_spec('numpy'):
    from src import masked_rhyme_recovery as study


@unittest.skipUnless(find_spec('numpy'), 'The existing context scorer uses NumPy on Gilbreth')
class MaskedRhymeTest(unittest.TestCase):
    def row(self, id_, groups, section='s', tone='平'):
        return study.Ending(str(id_), section, str(id_), frozenset(groups), tone, True)

    def test_run_infers_alternating_groups_without_choice_or_answer(self):
        near = {-2: self.row('a', ['東']), 2: self.row('b', ['東']),
                -1: self.row('c', ['冬']), 1: self.row('d', ['文'])}
        self.assertEqual(study.run_group(near), '東')
        scores, inferred = study.predict(near, ['冬', '文'], {})
        self.assertEqual(inferred, '東')
        self.assertEqual(scores['run'], {})
        near[-1] = self.row('c', ['文'])
        self.assertIsNone(study.run_group(near))

    def test_local_rule_agrees_with_existing_uncertain_group_treatment(self):
        near = {-1: self.row('a', ['東', '冬']), 1: self.row('b', ['東']), 3: self.row('c', ['文'])}
        self.assertEqual(study.local_agreement(near, '東'), 1.)
        self.assertEqual(study.local_agreement(near, '冬'), 0.)
        self.assertEqual(study.local_agreement(near, '文'), 0.)
        self.assertIsNone(study.local_agreement({-1: near[-1]}, '冬'))

    def test_target_is_excluded_from_frequency_and_never_crosses_sections(self):
        rows = [self.row(0, ['東']), self.row(1, ['冬'], section='t'), self.row(2, ['東'], section='t')]
        work = study.Work('w', 'X', 'test', 'fu', rows)
        trials = {'0': {'tone': '平', 'group': '東', 'foil': '冬'}}
        counts, supported, detail = study.evaluate_work(work, trials, details=True)
        self.assertEqual(counts['frequency'], {'tie': 1})
        self.assertEqual(counts['local'], {'abstain': 1})
        self.assertEqual(counts['tone'], {'tie': 1})
        self.assertEqual(supported, 0)
        self.assertEqual(detail[0]['neighbors'], {})
        shuffled = study.evaluate_work(work, trials, shuffle=4, details=True)[2][0]
        self.assertEqual((detail[0]['id'], detail[0]['foil']), (shuffled['id'], shuffled['foil']))

    def test_foil_never_uses_held_out_only_category_or_another_tone(self):
        dev = study.Work('d', 'X', 'development', 'fu', [self.row(0, ['東']), self.row(1, ['冬']),
                                                        self.row(2, ['屋'], tone='入')])
        rows = [self.row(0, ['東']), self.row(1, ['江']), self.row(2, ['江', '文']), self.row(3, ['屋'], tone='入')]
        test = study.Work('t', 'Y', 'test', 'fu', rows)
        trials = study.make_trials({'d': dev, 't': test})['t']
        self.assertEqual(trials['0']['foil'], '冬')
        self.assertIn(trials['1']['foil'], ['東', '冬'])
        self.assertNotIn('2', trials)
        self.assertNotIn('3', trials)

    def test_abstentions_and_works_have_declared_weights(self):
        from collections import Counter
        large = study.rates(Counter(win=100))
        small = study.rates(Counter(abstain=4, loss=1, tie=1))
        self.assertEqual(small['accuracy'], 2.5 / 6)
        self.assertEqual(small['attempted_accuracy'], .25)
        self.assertEqual(small['coverage'], 2 / 6)
        aggregate = study.distribution_summary([{'intact': dict.fromkeys(study.METHODS, value)}
                                                for value in (large, small)])
        self.assertAlmostEqual(aggregate['run']['accuracy'], (1 + 2.5 / 6) / 2)

    def test_reject_author_leakage_across_splits(self):
        row = dict(id='1', section='s', text='□', genre='fu', author='X')
        with self.assertRaisesRegex(ValueError, 'crosses split'):
            study.load_works([{**row, 'work_id': 'd', 'split': 'development'},
                              {**row, 'work_id': 't', 'split': 'test'}], {})
