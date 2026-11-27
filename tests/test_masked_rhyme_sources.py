import unittest

from src.masked_rhyme_sources import parse


class TestMaskedRhymeSources(unittest.TestCase):
    title = '觀風賦（以「春風入戶」為韻）'
    page = '觀風賦 (某甲)'
    sentences = ('東山出日，西谷聞風。', '川上有舟，山中有人！', '城南誰往，市北誰歸？', '來者未至；候者無言。')

    def witness(self, title=None, body=None):
        return '\n'.join((
            '{{header', '| title = ' + (title or self.title), '| author = 某甲',
            '| times = 唐', '| from = 全唐文/卷0001', '}}',
            '外題不入正文。', '<onlyinclude>',
            body if body is not None else '\n'.join([''.join(self.sentences)] * 2),
            '</onlyinclude>', '篇後附識。',
        ))

    def test_disambiguated_page_retains_rubric_only_in_metadata(self):
        author, _, edition, groups, assigned = parse(self.witness(), self.page, 'fu')
        self.assertEqual((author, edition, assigned), ('某甲', '全唐文/卷0001', '春風入戶'))
        self.assertEqual(groups, [list(self.sentences), list(self.sentences)])

    def test_unassigned_damage_and_trailing_text_are_ineligible(self):
        body = ''.join(self.sentences * 2)
        for raw in (
            self.witness(title='觀風賦（以題為韻）'),
            self.witness(body=body + '編者識'),
            self.witness(body=body.replace('舟', '<ref>古本</ref>舟')),
            self.witness(body=body.replace('舟', '□')),
            self.witness(body='序曰：' + body),
        ):
            with self.subTest(witness=raw):
                with self.assertRaises(ValueError):
                    parse(raw, self.page, 'fu')

    def test_unrubricated_prose_uses_same_endings(self):
        _, _, _, groups, assigned = parse(self.witness(title='謝恩表'), '謝恩表', 'prose')
        self.assertEqual(groups, [list(self.sentences), list(self.sentences)])
        self.assertEqual(assigned, '')
        with self.assertRaisesRegex(ValueError, 'rhymed title'):
            parse(self.witness(), self.page, 'prose')
