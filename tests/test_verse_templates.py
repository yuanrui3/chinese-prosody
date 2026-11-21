"""Examples independently anchored in primary verse witnesses and tonal profiles."""

import unittest

from src.verse_templates import (
    ParallelToken, align_parallel_tokens, bamboo_window, match_regulated_poem, weighted_tone_edit,
)


class VerseTemplateTest(unittest.TestCase):
    def test_verse_windows_follow_qigong_exact_sequence(self):
        # 启功's oral account, https://xcb.bnu.edu.cn/xywh/jsff/14401.html
        self.assertEqual([bamboo_window(5, phase) for phase in range(4)],
                         ['PPZZP', 'PZZPP', 'ZZPPZ', 'ZPPZZ'])
        self.assertEqual([bamboo_window(7, phase) for phase in range(4)],
                         ['PPZZPPZ', 'PZZPPZZ', 'ZZPPZZP', 'ZPPZZPP'])

    def test_five_character_known_poem_distinguishes_the_profiles(self):
        # 《登鸛雀樓》, Wikisource revision 12807586, reading 更 as the adverb.
        # https://zh.wikisource.org/w/index.php?oldid=12807586
        # The fixture uses the standard reading of 白日依山盡 / 黃河入海流 /
        # 欲窮千里目 / 更上一層樓. 流 and 樓 share 平水韻 下平聲十一尤.
        witness = ('ZZPPZ', 'PPZZP', 'ZPPZZ', 'ZZZPP')
        strict, = match_regulated_poem(witness, first_line_rhymes=False)
        relaxed, = match_regulated_poem(witness, profile='literal_odd', first_line_rhymes=False)
        self.assertEqual(strict.line_types, 'ABCD')
        self.assertEqual(strict.mismatches, ((), (), (0,), ()))
        self.assertEqual(relaxed.cost, 0)
        self.assertEqual(match_regulated_poem(witness, first_line_rhymes=True)[0].cost, 3)

    def test_seven_character_known_poem_allows_a_first_line_rhyme(self):
        # 李商隱 《夜雨寄北》, Wikisource revision 1566402.
        # https://zh.wikisource.org/w/index.php?oldid=1566402
        # Pingshui rhyme check for 期、池、時 uses 上平聲四支.
        witness = ('PZPPZZP', 'PPZZZPP', 'PPZZPPZ', 'ZZPPZZP')
        strict, = match_regulated_poem(witness)
        relaxed, = match_regulated_poem(witness, profile='literal_odd')
        self.assertEqual(strict.line_types, 'BDAB')
        self.assertTrue(strict.first_line_rhymes)
        self.assertEqual(strict.mismatches, ((0,), (), (), ()))
        self.assertEqual(relaxed.cost, 0)

    def test_seven_character_even_position_and_link_are_required(self):
        # Duanmu and Stiennon, (1), (3)–(5). https://websites.umich.edu/~duanmu/PingZe05.pdf
        witness = ('PPZZZPP', 'ZZPPZZP', 'ZZPPPZZ', 'PPZZZPP',
                   'PPZZPPZ', 'ZZPPZZP', 'ZZPPPZZ', 'PPZZZPP')
        fit, = match_regulated_poem(witness)
        self.assertEqual(fit.line_types, 'DBCDABCD')
        self.assertTrue(fit.first_line_rhymes)
        self.assertEqual(fit.cost, 0)
        shifted = witness[:2] + (witness[2][0] + 'P' + witness[2][2:],) + witness[3:]
        self.assertEqual(match_regulated_poem(shifted, profile='literal_odd')[0].mismatches[2], (1,))
        with self.assertRaisesRegex(ValueError, 'resolved historical'):
            match_regulated_poem(witness[:2] + ('?ZPPPZZ',) + witness[3:])

    def test_weighted_edit_penalizes_a_missing_syllable_and_preserves_rhyme_position(self):
        mismatch = weighted_tone_edit('PZZZP', 'PPZZP', mismatch_weights=(1, 2, 1, 1, 1), gap_cost=3)
        self.assertEqual(mismatch.cost, 2)
        self.assertEqual(mismatch.path, tuple((i, i) for i in range(5)))
        self.assertEqual(mismatch.optimal_paths, 1)
        self.assertEqual(weighted_tone_edit('PPZP', 'PPZZP', gap_cost=3).cost, 3)
        self.assertEqual(weighted_tone_edit('PZZZZ', 'XPXPP', gap_cost=3).cost, 3)


class ParallelAlignmentTest(unittest.TestCase):
    def test_du_fu_parallel_couplet(self):
        # 杜甫 《登高》 lines 3–4, Wikisource revision 12915048.
        # https://zh.wikisource.org/w/index.php?oldid=12915048
        # Phrase, role and fine semantic labels are declared analysis fixtures.
        left = (  # 無邊 / 落木 / 蕭蕭 / 下
            ParallelToken(2, 'adjective', 'modifier', 'extent', ('P', 'P')),
            ParallelToken(2, 'noun', 'subject', 'vegetation', ('Z', 'Z')),
            ParallelToken(2, 'adverb', 'manner', 'auditory_manner', ('P', 'P')),
            ParallelToken(1, 'verb', 'predicate', 'directional_motion', ('Z',)),
        )
        right = (  # 不盡 / 長江 / 滚滚 / 來
            ParallelToken(2, 'adjective', 'modifier', 'extent', ('Z', 'Z')),
            ParallelToken(2, 'noun', 'subject', 'watercourse', ('P', 'P')),
            ParallelToken(2, 'adverb', 'manner', 'movement_manner', ('Z', 'Z')),
            ParallelToken(1, 'verb', 'predicate', 'directional_motion', ('P',)),
        )
        fit = align_parallel_tokens(left, right)
        self.assertEqual(fit.alignment.path, ((0, 0), (1, 1), (2, 2), (3, 3)))
        self.assertEqual(fit.gaps, 0)
        self.assertEqual(fit.length_similarity, 1)
        self.assertEqual(fit.agreement_counts, {'pos': (4, 4), 'role': (4, 4), 'semantic': (2, 4),
                                                'tone_opposition': (7, 7)})
        lexical_fit = align_parallel_tokens(left, right, weights={'pos': 0.30, 'role': 0.30, 'semantic': 0.25})
        self.assertEqual(lexical_fit.alignment.path, fit.alignment.path)
        self.assertAlmostEqual(lexical_fit.alignment.cost, 0.5)
        self.assertAlmostEqual(lexical_fit.normalized_cost, 0.5 / 4.8)

    def test_alignment_preserves_a_gap_and_withholds_missing_tones(self):
        left = (ParallelToken(2, 'noun', 'subject', tones=('Z', 'Z')),
                ParallelToken(1, 'verb', 'predicate', tones=('P',)))
        right = (ParallelToken(2, 'noun', 'subject', tones=(None, 'P')),
                 ParallelToken(1, 'adverb', 'manner'), ParallelToken(1, 'verb', 'predicate', tones=('Z',)))
        fit = align_parallel_tokens(left, right)
        self.assertEqual(fit.alignment.path, ((0, 0), (None, 1), (1, 2)))
        self.assertEqual(fit.gaps, 1)
        self.assertEqual(fit.length_similarity, 0.75)
        self.assertEqual(fit.agreement_counts['tone_opposition'], (2, 2))
        with self.assertRaisesRegex(ValueError, 'incomparable active annotation'):
            align_parallel_tokens(left, right, weights={'tone_opposition': 1})
