"""Mandarin pinyin and Cantonese Jyutping lookup candidates from Unihan."""

from collections import defaultdict
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata
from urllib.request import Request, urlopen
from zipfile import ZipFile


VERSION = '17.0.0'
ARCHIVE = f'Unihan-{VERSION}.zip'
URL = f'https://www.unicode.org/Public/{VERSION}/ucd/Unihan.zip'
MEMBERS = ('Unihan_Readings.txt', 'Unihan_DictionaryLikeData.txt', 'Unihan_Variants.txt')


def fetch_modern(raw_dir):
    """Stream the official versioned archive into a private cache."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / ARCHIVE
    if target.is_file():
        return target
    request = Request(URL, headers={'User-Agent': 'shunkou-research/0.1 (Unicode data download)'})
    with tempfile.TemporaryDirectory(dir=raw_dir) as working:
        temporary = Path(working) / ARCHIVE
        with urlopen(request, timeout=60) as source, temporary.open('wb') as destination:
            shutil.copyfileobj(source, destination)
        with ZipFile(temporary) as archive:
            for member in MEMBERS:
                archive.getinfo(member)
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f'Corrupt Unihan member: {bad_member}')
        temporary.replace(target)
    return target


def reading_rows(archive, member, fields):
    with archive.open(member) as stream:
        header = stream.read(4096).decode('utf-8', errors='ignore').splitlines()
        if not any(VERSION in line and line.startswith('#') for line in header):
            raise ValueError(f'{member} has no Unicode {VERSION} header')
        stream.seek(0)
        for line in stream:
            if line.startswith(b'U+'):
                codepoint, field, content = line.decode('utf-8').rstrip('\n\r').split('\t', 2)
                if field in fields:
                    yield chr(int(codepoint[2:], 16)), field, content


def load_modern(raw_dir):
    """Return modern lookup candidates and explicit simplified-to-traditional alternatives."""
    mandarin = defaultdict(lambda: defaultdict(set))
    cantonese = defaultdict(lambda: defaultdict(set))
    variants = {}
    with ZipFile(Path(raw_dir) / ARCHIVE) as archive:
        for char, field, content in reading_rows(archive, MEMBERS[0], {'kMandarin', 'kHanyuPinyin', 'kCantonese'}):
            if field == 'kHanyuPinyin':
                readings = (reading for group in content.split() for reading in group.split(':', 1)[1].split(','))
            else:
                readings = content.split()
            index = cantonese if field == 'kCantonese' else mandarin
            for reading in readings:
                index[char][unicodedata.normalize('NFC', reading)].add(field)
        for char, field, content in reading_rows(archive, MEMBERS[1], {'kCheungBauer'}):
            # The final subfield contains comma-separated Jyutping for each source entry.
            for entry in content.split():
                value = entry.rsplit(';', 1)[-1]
                for reading in re.findall(r'[a-z]+[1-6]', value):
                    cantonese[char][reading].add(field)
        for char, _, content in reading_rows(archive, MEMBERS[2], {'kTraditionalVariant'}):
            variants[char] = sorted({chr(int(value[2:], 16)) for value in content.split()})

    def export(index):
        return {
            char: [{'id': reading, 'reading': reading, 'properties': sorted(properties)}
                   for reading, properties in sorted(readings.items())]
            for char, readings in index.items()
        }

    return {'mandarin': export(mandarin), 'cantonese': export(cantonese)}, variants
