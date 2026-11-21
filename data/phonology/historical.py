"""Load revision-pinned historical rhyme books as character reading candidates."""

from collections import Counter, defaultdict
import csv
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import unicodedata
from urllib.request import Request, urlopen


GUANGYUN_REVISION = '21585e22c8a730ca2fd175112f4d18e16d5ce578'
GUANGYUN_BLOB = '1b3c5c7f36504a5f187f00f8c2f8e8ee2e3b515e'
GUANGYUN_URL = (
    'https://raw.githubusercontent.com/nk2028/tshet-uinh-data/'
    f'{GUANGYUN_REVISION}/%E9%9F%BB%E6%9B%B8/%E5%BB%A3%E9%9F%BB.csv'
)
PINGSHUI_REVISION = '8264804'
PINGSHUI_URL = f'https://zh.wikisource.org/w/index.php?title=%E5%B9%B3%E6%B0%B4%E9%9F%BB&oldid={PINGSHUI_REVISION}'

POSITION = re.compile(r'(?P<initial>.)(?P<mouth>[開合]?)(?P<grade>[一二三四])(?P<class>[ABC]?)(?P<family>.)(?P<tone>[平上去入])')
PINGSHUI_GROUP = re.compile(r'(上平|下平|上|去|入)聲([一二三四五六七八九十]+)(.)')
PINGSHUI_COUNTS = {'上平': 15, '下平': 15, '上': 29, '去': 30, '入': 17}

# Baxter & Sagart (2014) Middle Chinese transcription. Adapted from the MIT-
# licensed TshetUinh examples, with the onset and final returned separately.
# See HISTORICAL.md and LICENSE.baxter-port.txt for sources and notice.
BAXTER_INITIALS = {
    '幫': 'p', '滂': 'ph', '並': 'b', '明': 'm',
    '端': 't', '透': 'th', '定': 'd', '泥': 'n', '來': 'l',
    '知': 'tr', '徹': 'trh', '澄': 'dr', '孃': 'nr',
    '精': 'ts', '清': 'tsh', '從': 'dz', '心': 's', '邪': 'z',
    '莊': 'tsr', '初': 'tsrh', '崇': 'dzr', '生': 'sr', '俟': 'zr',
    '章': 'tsy', '昌': 'tsyh', '常': 'dzy', '日': 'ny', '書': 'sy', '船': 'zy', '以': 'y',
    '見': 'k', '溪': 'kh', '羣': 'g', '疑': 'ng',
    '影': "'", '曉': 'x', '匣': 'h', '云': 'h',
}
BAXTER_FINALS = {
    '東': 'uwng', '冬': 'owng', '模': 'u', '泰': 'aj', '灰': 'oj', '咍': 'oj',
    '魂': 'on', '痕': 'on', '寒': 'an', '豪': 'aw', '歌': 'a', '唐': 'ang',
    '登': 'ong', '侯': 'uw', '覃': 'om', '談': 'am',
    '江': 'aewng', '佳': 'ea', '皆': 'eaj', '夬': 'aej', '刪': 'aen', '山': 'ean',
    '肴': 'aew', '麻': 'ae', '庚': 'aeng', '耕': 'eang', '咸': 'eam', '銜': 'aem',
    '齊': 'ej', '先': 'en', '蕭': 'ew', '青': 'eng', '添': 'em',
    '支': 'je', '脂': 'ij', '之': 'i', '微': 'j+j', '魚': 'jo', '虞': 'ju',
    '祭': 'jej', '廢': 'joj', '宵': 'jew', '尤': 'juw', '幽': 'jiw',
    '鍾': 'jowng', '真': 'in', '臻': 'in', '文': 'jun', '殷': 'j+n', '元': 'jon',
    '仙': 'jen', '陽': 'jang', '清': 'jeng', '蒸': 'ing', '侵': 'im',
    '鹽': 'jem', '嚴': 'jaem', '凡': 'jom',
}


def fetch_historical(raw_dir):
    """Cache original sources on the caller's corpus volume."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for filename, url in (('guangyun.csv', GUANGYUN_URL), ('pingshui.html', PINGSHUI_URL)):
        target = raw_dir / filename
        if target.is_file():
            continue
        request = Request(url, headers={'User-Agent': 'shunkou research corpus builder/1.0'})
        with TemporaryDirectory(dir=raw_dir) as temporary:
            partial = Path(temporary) / filename
            with urlopen(request, timeout=60) as response, partial.open('wb') as output:
                shutil.copyfileobj(response, output)
            partial.replace(target)


def is_han(char):
    return unicodedata.name(char, '').startswith(('CJK UNIFIED IDEOGRAPH-', 'CJK COMPATIBILITY IDEOGRAPH-'))


def corrected_headword(display):
    """Normalize upstream correction brackets while leaving unencoded IDS out."""
    if display.startswith('［') and display.endswith('］'):
        display = display[1:-1]
    elif '〈' in display and display.endswith('〉'):
        display = display.split('〈', 1)[1][:-1]
    if len(display) == 1 and is_han(display):
        return display
    return None


def baxter_transcription(position):
    initial = BAXTER_INITIALS.get(position['initial'])
    family = position['family']
    final = BAXTER_FINALS.get(family)
    if initial is None or final is None:
        return None, None
    if family in '東歌麻庚' and position['grade'] in '三四':
        final = 'j' + final
    if position['initial'] in '章昌常書船日以' and final.startswith('j'):
        final = final[1:]
    if position['class'] == 'A' and family not in '麻幽陽':
        final = 'ji' + final[1:] if final.startswith('j') else 'j' + final
    if (position['mouth'] == '合' or family in '灰魂') and family not in '虞文凡':
        final = 'jw' + final[1:] if final.startswith('j') else 'w' + final
    if position['tone'] == '入':
        for nasal, stop in (('ng', 'k'), ('m', 'p'), ('n', 't')):
            if final.endswith(nasal):
                final = final[:-len(nasal)] + stop
                break
        else:
            return None, None
    return initial, final


def reading(identifier, tone, rhyme, revision, initial=None, final=None):
    return {
        'id': identifier,
        'tone': tone,
        'pingze': ('平' if tone == '平' else '仄') if tone else None,
        'rhyme': rhyme,
        'initial': initial,
        'final': final,
        'source_revision': revision,
    }


def load_guangyun(path):
    by_character = defaultdict(dict)
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        columns = {'字頭', '音韻地位', '韻目原貌', '小韻號', '小韻字號', '反切', '釋義'}
        if not columns.issubset(reader.fieldnames or []):
            raise ValueError(f'{path}: unsupported 廣韻 table header')
        for row in reader:
            char = corrected_headword(row['字頭'])
            if char is None:
                continue
            raw_position = row['音韻地位']
            position_match = POSITION.fullmatch(raw_position)
            position = position_match.groupdict() if position_match else None
            tone = position['tone'] if position else None
            rhyme = row['韻目原貌'] or None
            key = (raw_position, rhyme, tone)
            if key not in by_character[char]:
                identifier = f'guangyun:{char}:{raw_position}:{rhyme or ""}'
                initial, final = baxter_transcription(position) if position else (None, None)
                candidate = reading(identifier, tone, rhyme, GUANGYUN_REVISION, initial, final)
                candidate.update(position=raw_position or None, initial_category=position['initial'] if position else None,
                                 final_category=position['family'] if position else None,
                                 transcription='baxter-sagart-2014-mc' if final else None, entries=[])
                by_character[char][key] = candidate
            by_character[char][key]['entries'].append({
                'location': f"{row['小韻號']}/{row['小韻字號']}",
                'headword_as_transcribed': row['字頭'],
                'fanqie': row['反切'] or None,
                'gloss': row['釋義'] or None,
            })
    return {char: list(candidates.values()) for char, candidates in by_character.items()}


class RhymeParagraphs(HTMLParser):
    """Extract paragraphs and headings inside the MediaWiki article body."""

    block_tags = frozenset({'p', 'dt', 'dd', 'li', 'h2', 'h3', 'h4'})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.article_depth = 0
        self.block = None
        self.fragments = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'div' and (self.article_depth or 'mw-parser-output' in dict(attrs).get('class', '').split()):
            self.article_depth += 1
        if not self.article_depth:
            return
        if tag in self.block_tags:
            self.flush()
            self.block = tag
        if tag == 'br':
            self.flush()

    def handle_endtag(self, tag):
        if tag == 'div' and self.article_depth:
            self.article_depth -= 1
        if tag == self.block:
            self.flush()
            self.block = None

    def handle_data(self, data):
        if self.block:
            self.fragments.append(data)

    def flush(self):
        content = ''.join(self.fragments).strip()
        if content:
            self.paragraphs.append(content)
        self.fragments.clear()


def load_pingshui(path):
    by_character = defaultdict(dict)
    html = path.read_text(encoding='utf-8')
    if not re.search(rf'(?:oldid=|"wgRevisionId":\s*){PINGSHUI_REVISION}\b', html):
        raise ValueError(f'{path}: missing 平水韻 revision marker for {PINGSHUI_REVISION}')
    parser = RhymeParagraphs()
    parser.feed(html)
    groups = {}
    group = None
    for paragraph in parser.paragraphs:
        text = ''.join(paragraph.split())
        header = PINGSHUI_GROUP.match(text)
        if header:
            group = header[0]
            if group in groups:
                raise ValueError(f'{path}: repeated 平水韻 group {group}')
            groups[group] = (header[1], set())
            text = text[header.end():]
        text = text.partition('〖')[0]
        if group and text and all(is_han(char) for char in text):
            groups[group][1].update(text)
    group_counts = Counter(volume for volume, chars in groups.values() if chars)
    if group_counts != PINGSHUI_COUNTS:
        raise ValueError(f'{path}: expected 106 nonempty 平水韻 groups, found {dict(group_counts)}')
    for group, (volume, chars) in groups.items():
        tone = '平' if volume in ('上平', '下平') else volume
        for char in sorted(chars):
            identifier = f'pingshui:{char}:{group}'
            candidate = reading(identifier, tone, group, PINGSHUI_REVISION)
            by_character[char][group] = candidate
    return {char: list(candidates.values()) for char, candidates in by_character.items()}


def load_historical(raw_dir):
    """Return separate 廣韻 and 平水韻 indexes, each preserving multiple readings."""
    raw_dir = Path(raw_dir)
    guangyun_path = raw_dir / 'guangyun.csv'
    data = guangyun_path.read_bytes()
    blob = hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()
    if blob != GUANGYUN_BLOB:
        raise ValueError(f'{guangyun_path}: SHA does not match the pinned 廣韻 Git blob')
    return {
        'guangyun': load_guangyun(guangyun_path),
        'pingshui': load_pingshui(raw_dir / 'pingshui.html'),
    }
