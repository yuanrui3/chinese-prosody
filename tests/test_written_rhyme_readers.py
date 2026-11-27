from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

if find_spec('numpy'):
    from src.written_rhyme_readers import read_judgments


@unittest.skipUnless(find_spec('numpy'), 'The archived written scorer uses NumPy')
class WrittenRhymeReaderTest(unittest.TestCase):
    def test_quote_must_come_from_the_target_and_each_id_must_occur_once(self):
        packet = {'B001': {'text': '野曠天低樹。', 'before': ['明月照高樓。']}}
        key = {'B001': 'W99-S001'}
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'reading.tsv'
            valid = 'B001\t6\t天低樹\tThe three final syllables form a cadence.\n'
            path.write_text(valid)
            self.assertEqual(read_judgments(path, packet, key)['B001']['id'], key['B001'])
            for bad in (valid + valid, valid.replace('天低樹', '明月'), valid.replace('\t6\t', '\t8\t'), ''):
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    read_judgments(path, packet, key)
