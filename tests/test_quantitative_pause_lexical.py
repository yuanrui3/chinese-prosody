from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from data.phonology.modern import MEMBERS, VERSION
from src.quantitative_pause_lexical import audit_pause, conservative_variants, lexical_match, main


class PauseLexicalTests(unittest.TestCase):
    def test_command_defaults_to_base_and_forwards_explicit_small(self):
        with TemporaryDirectory() as folder, patch('src.quantitative_pause_lexical.analyze') as run, \
                patch('src.quantitative_pause_lexical.os.umask'), patch('builtins.print'):
            root = Path(folder).resolve()
            run.return_value = {'cohorts': {}, 'controlled_joins': None}
            for variant in ('base', 'small'):
                args = ['audit', '--project', str(root), '--model-cache', str(root),
                        '--output', str(root / f'{variant}.json')]
                if variant == 'small':
                    args += ['--variant', 'small']
                with patch('sys.argv', args):
                    main()
                run.assert_called_with(root, root, None, variant=variant)

    def test_literal_unique_position_and_short_or_mixed_flanks(self):
        source = '君子文學其所習'
        row = lexical_match(source, '君子文，', '學其所習。', {})
        self.assertEqual((row['status'], row['right_slot']), ('unique_exact', 3))
        self.assertEqual(lexical_match(source, '子文', '學其所', {})['status'], 'missing_han_flank')
        self.assertEqual(lexical_match(source, '君子文1', '學其所', {})['status'], 'missing_han_flank')
        self.assertEqual(lexical_match(source, '君子聞', '學其所', {})['status'], 'no_gap_match')

    def test_variant_ambiguity_stays_unresolved_even_with_one_literal_hit(self):
        variants = {'传': '傳', '统': '統'}
        row = lexical_match('傳統文體用字', '传统文', '體用字', variants)
        self.assertEqual((row['status'], row['right_slot']), ('unique_variant', 3))
        row = lexical_match('傳統文體用字传统文體用字', '传统文', '體用字', variants)
        self.assertEqual((row['status'], row['right_slot']), ('ambiguous_gap', None))
        self.assertEqual(row['exact_candidates'], [9])
        self.assertEqual(row['variant_candidates'], [3, 9])

    def test_unihan_mapping_requires_reciprocal_singleton(self):
        rows = [
            ('传', 'kTraditionalVariant', '傳'), ('傳', 'kSimplifiedVariant', '传'),
            ('后', 'kTraditionalVariant', '後'), ('後', 'kSimplifiedVariant', '后後'),
            ('云', 'kTraditionalVariant', '雲云'), ('雲', 'kSimplifiedVariant', '云'),
        ]
        header = f'# Unicode {VERSION}\n'
        text = header + ''.join(
            f'U+{ord(source):X}\t{field}\t' + ' '.join(f'U+{ord(target):X}' for target in targets) + '\n'
            for source, field, targets in rows
        )
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.zip'
            with ZipFile(path, 'w') as archive:
                archive.writestr(MEMBERS[2], text)
            self.assertEqual(conservative_variants(path), {'传': '傳'})

    def test_recognizer_receives_exact_disjoint_waveform_flanks(self):
        pcm = array('h', [100, 200, 0, 0, 0, 300, 400])
        heard = []

        def recognize(samples, rate):
            heard.append((list(samples), rate))
            return ('傳統文' if samples[0] else '體用字')

        passage = {'slots': [{'char': char, 'clause_index': i // 3} for i, char in enumerate('傳統文體用字')]}
        row = audit_pause(recognize, passage, pcm, 24000, {'start_sample': 2, 'end_sample': 5},
                          {'funasr': {'right_slot': 3}}, {})
        self.assertEqual(heard, [(list(pcm[:3]), 24000), (list(pcm[3:]), 24000)])
        self.assertEqual(row['split_sample'], 3)
        self.assertTrue(row['asr']['is_written_clause_break'])
        self.assertEqual(row['comparison_with_funasr'], 'agrees')
