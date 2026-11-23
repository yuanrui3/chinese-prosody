"""Stage reviewed classical readings from the frozen MCGA test shards."""

import argparse
from collections import defaultdict
from hashlib import sha256
from io import BytesIO
from itertools import groupby
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import unicodedata
import wave

from src.quantitative_mandi_fetch import preserve_file
from src.quantitative_pause_transfer import MCGA_REVISION, MCGA_WORKS


HAN = re.compile(r'[\u3400-\u9fff]')
METADATA = ('id', 'title', 'author', 'dynasty', 'gender', 'asr')
PRIOR_TITLES = {
    '北山移文', '与朱元思书', '與朱元思書', '与宋元思书', '與宋元思書', '陈情表', '陳情表',
    '芜城赋', '蕪城賦', '哀江南赋', '哀江南賦', '哀江南赋序', '哀江南賦序',
    '洛阳伽蓝记', '洛陽伽藍記', '颜氏家训', '顏氏家訓', '玉台新咏序', '玉臺新詠序',
    '滕王阁序', '滕王閣序', '大唐西域记', '大唐西域記', '秋日登洪府滕王阁饯别序',
    '为徐敬业讨武曌檄', '為徐敬業討武曌檄', '讨武曌檄', '讨武檄文', '討武曌檄', '史通',
    '岘山亭记', '峴山亭記', '大唐三藏圣教序', '大唐三藏聖教序', '续高僧传', '續高僧傳',
    '水经注', '水經注', '与陈伯之书', '與陳伯之書', '魏书', '魏書', '王勃集序', '北史',
    '文心雕龙', '文心雕龍', '广绝交论', '廣絕交論', '与梁武帝论书启', '與梁武帝論書啟',
    '谏太宗十思疏', '諫太宗十思疏', '上太宗疏', '本草序', '千金要方序', '兰亭集序', '蘭亭集序',
    '兰亭序', '蘭亭序', '别赋', '別賦', '恨赋', '恨賦',
}
# Candidate titles are verified through the deposited text, before reading any waveform.
CANDIDATE_TITLES = (
    '洛神赋', '洛神賦', '枯树赋', '枯樹賦',
    '小园赋', '小園賦', '竹林七贤论', '竹林七賢論', '答谢中书书', '答謝中書書',
    '思旧赋', '思舊賦', '孔雀东南飞并序', '孔雀東南飛并序', '祭妹文', '桃花源记', '桃花源記',
    '归去来兮辞', '歸去來兮辭', '三峡', '三峽',
    '河中石兽', '河中石獸', '报任安书', '報任安書', '送东阳马生序', '送東陽馬生序',
    '岳阳楼记', '岳陽樓記', '出师表', '出師表', '隆中对', '隆中對', '醉翁亭记', '醉翁亭記',
    '游褒禅山记', '遊褒禪山記', '赤壁赋', '赤壁賦', '阿房宫赋', '阿房宮賦', '阿房宫賦',
    '张中丞传后叙', '張中丞傳後敘', '师说', '師說', '马说', '馬說', '谏逐客书', '諫逐客書',
    '过秦论', '過秦論', '五柳先生传', '五柳先生傳', '陈涉世家', '陳涉世家', '种树郭橐驼传',
    '種樹郭橐駝傳', '与山巨源绝交书', '與山巨源絕交書', '得道多助', '生于忧患', '荀子·劝学',
)


def compact(text):
    return ''.join(unicodedata.normalize('NFC', text or '').split())


def han(text):
    return ''.join(HAN.findall(unicodedata.normalize('NFC', text)))


def metadata(archive):
    from pyarrow.parquet import ParquetFile

    paths = sorted(archive.glob('test-*-of-00003.parquet'))
    if len(paths) != 3:
        raise ValueError('Expected all three frozen MCGA test shards')
    for path in paths:
        shard = ParquetFile(path)
        for group in range(shard.num_row_groups):
            entries = shard.read_row_group(group, columns=list(METADATA)).to_pylist()
            for index, entry in enumerate(entries):
                if entry['asr'] and entry['id']:
                    yield path, shard, group, index, entry


def reader_group(gender):
    group = compact(gender).casefold()
    groups = {'female': 'F', 'male': 'M', 'f': 'F', 'm': 'M', '女': 'F', '男': 'M', '女性': 'F', '男性': 'M'}
    return f'MCGA-{groups[group]}' if group in groups else None


def candidates(archive, titles):
    groups = defaultdict(list)
    voices = defaultdict(set)
    for _, _, _, _, row in metadata(archive):
        title = compact(row['title'])
        gender = reader_group(row['gender'])
        if gender and title not in PRIOR_TITLES and any(name in title for name in titles):
            entry = {key: compact(row[key]) for key in METADATA}
            groups[title, gender].append(entry)
            voices[title, han(entry['asr'])].add(gender)
    for title, gender in sorted(groups):
        entries = groups[title, gender]
        entries.sort(key=lambda row: (len(voices[title, han(row['asr'])]) < 2, row['id']))
        for entry in entries[:3]:
            print(json.dumps(entry, ensure_ascii=False))


def positions(review, text):
    """Map reviewed two-sided text anchors to the preceding Han ordinal."""
    def locate(pair):
        left, right = (han(text) for text in pair)
        window = left + right
        index = text.find(window)
        if not left or not right or index < 0 or text.find(window, index + 1) >= 0:
            raise ValueError(f'No unique two-sided anchor for {pair!r} in {text!r}')
        return index + len(left)

    ends = sorted(locate(pair) for pair in review['boundaries'])
    controls = sorted(locate(pair) for pair in review['controls'])
    if not ends or not controls or len(set(ends + controls)) != len(ends) + len(controls):
        raise ValueError('Expect nonempty disjoint boundary and control sites')
    return ends, controls


def store_pcm(path, original):
    with wave.open(BytesIO(original), 'rb') as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) != (1, 2, 'NONE'):
            raise ValueError(f'Expected released mono PCM16 WAV for {path.name}')
        rate = wav.getframerate()
        count = wav.getnframes()
        if not rate or not count or len(wav.readframes(count)) != 2 * count:
            raise ValueError(f'Incomplete PCM for {path.name}')
    checksum = sha256(original).hexdigest()
    with NamedTemporaryFile(dir=path.parent) as handle:
        handle.write(original)
        handle.flush()
        preserve_file(Path(handle.name), path, checksum)
    return checksum, rate, count


def extract(archive, output, reviews):
    selected = []
    seen = set()
    for path, shard, group, index, row in metadata(archive):
        key = row['id']
        if key not in reviews:
            continue
        title, author = compact(row['title']), compact(row['author'])
        gender = reader_group(row['gender'])
        review = reviews[key]
        text = han(row['asr'])
        if (not re.fullmatch(r'[0-9]+-[0-9]+', key) or key in seen or key in MCGA_WORKS or title in PRIOR_TITLES or not gender
                or (title, author) != (review['title'], review['author']) or text != han(review['transcript'])):
            raise ValueError(f'Unexpected new work or deposited text for {key}')
        seen.add(key)
        selected.append((path, shard, group, index, row, gender, positions(review, text)))
    if seen != set(reviews):
        raise ValueError(f'Missing reviewed MCGA clip metadata for {sorted(set(reviews) - seen)}')
    if len({gender for _, _, _, _, _, gender, _ in selected}) != 2:
        raise ValueError('Expected both documented MCGA voice groups')
    paths = output / 'mcga-wav'
    paths.mkdir(parents=True, exist_ok=True)
    inventory = []
    for (path, shard, group), items in groupby(selected, key=lambda item: item[:3]):
        audio = shard.read_row_group(group, columns=['audio'])['audio']
        for _, _, _, index, row, gender, (ends, controls) in items:
            key = row['id']
            review = reviews[key]
            row_id = f'MCGA-{key}'
            wav = paths / f'{row_id}.wav'
            checksum, rate, count = store_pcm(wav, audio[index].as_py()['bytes'])
            inventory.append({
                'id': row_id, 'recording_id': row_id, 'speaker': gender, 'speaker_identity_known': False,
                'gender': compact(row['gender']), 'work': review['title'], 'author': review['author'],
                'dynasty': compact(row['dynasty']), 'genre': review['genre'], 'transcript': compact(row['asr']),
                'performing_variety': 'Standard Mandarin', 'style': 'prompted classical recitation',
                'path': wav.relative_to(output).as_posix(), 'sample_rate': rate, 'sample_count': count,
                'wav_sha256': checksum, 'source_shard': path.name, 'source_id': key,
                'edition': 'MCGA released clip and transcript', 'license': 'CC BY-NC-SA 4.0',
                'text_label_source': review['label_source'],
                'boundaries': ends, 'controls': controls,
            })
    return {'corpus': 'MCGA', 'revision': MCGA_REVISION, 'recordings': sorted(inventory, key=lambda row: row['id']),
            'provenance': 'Released PCM and transcript with text-only reviewed clause and within-constituent anchors. '
                          'Public voice groups preserve disjoint male/female train and test folds without identifying readers.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--list-candidates', action='store_true')
    parser.add_argument('--title', action='append', help='Limit metadata list by title substrings')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--reviews', type=Path, help='JSON object keyed by clip ID with two-sided text anchors')
    args = parser.parse_args()
    if args.list_candidates:
        candidates(args.archive, args.title or CANDIDATE_TITLES)
        return
    if not (args.output and args.manifest and args.reviews):
        parser.error('Extraction requires --output, --manifest and --reviews')
    reviews = json.loads(args.reviews.read_text(encoding='utf-8'))
    inventory = extract(args.archive, args.output, reviews)
    with args.manifest.open('x', encoding='utf-8') as handle:
        json.dump(inventory, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'recordings': len(inventory['recordings']),
                      'works': len({row['work'] for row in inventory['recordings']})}))


if __name__ == '__main__':
    main()
