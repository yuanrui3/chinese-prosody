"""Render controlled Mandarin pilot stimuli from explicit, versioned syllable inputs."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile


REPO = 'hexgrad/Kokoro-82M-v1.1-zh'
REVISION = '01e7505bd6a7a2ac4975463114c3a7650a9f7218'
CHECKPOINT = 'kokoro-v1_1-zh.pth'
ASSET_SHA256 = {
    CHECKPOINT: 'b1d8410fa44dfb5c15471fd6c4225ea6b4e9ac7fa03c98e8bea47a9928476e2b',
    'voices/zf_001.pt': '9bdc9a87e13e9bb1ea3e7803259c2ecbfebaeeb2ff80b5d0c76df1a464c1c962',
    'voices/zf_002.pt': '2c8cf221ff2e0915fc807cac5f233f42798ee8e2bd58bc5ad0259fd95e405a26',
    'voices/zm_010.pt': 'd2eeba86192eee269f600ca6821038034abd017532a1fe68ff7b0e86c2983b2a',
}
VOICES = ('zf_001', 'zf_002')
MALE_VOICE = 'zm_010'
SPEEDS = ('0.9', '1.0', '1.1')
SAMPLE_RATE = 24_000
PUNCTUATION = str.maketrans('，。、；：？！', ',.,;:?!')
READINGS = Path(__file__).with_name('synthetic_readings.json')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def encode_syllable(pinyin, phoneme_map, to_initials, to_finals_tone3):
    if not re.fullmatch(r'[a-z]+[1-5]', pinyin):
        raise ValueError(f'Expected numbered pinyin: {pinyin!r}')
    initial = to_initials(pinyin)
    final = to_finals_tone3(pinyin, neutral_tone_with_five=True)
    if not final or final[-1] != pinyin[-1]:
        raise ValueError(f'Kokoro syllable front end cannot encode {pinyin!r}')
    if final[:-1] == 'i' and initial in ('z', 'c', 's', 'zh', 'ch', 'sh', 'r'):
        final = ('ii' if len(initial) == 1 and initial != 'r' else 'iii') + final[-1]
    try:
        return ''.join(phoneme_map[part] for part in (initial, final[:-1], final[-1]) if part)
    except KeyError as exc:
        raise ValueError(f'Kokoro syllable front end cannot encode {pinyin!r}') from exc


def prepare_passage(passage, prescription, encode, to_tone3):
    """Join declared syllables to exact source slots and preserve source punctuation."""
    identifier = passage['passage_id']
    if prescription['text_sha256'] != passage['text_sha256']:
        raise ValueError(f'{identifier}: pronunciation prescription is for a different text')
    slots = passage['slots']
    syllables = []
    phones = []
    conflicts = []
    for index, clause in enumerate(prescription['clauses']):
        start_index = len(syllables)
        for word_index, word in enumerate(clause.split('/')):
            if word_index:
                phones.append('/')
            for pinyin in word.split():
                if len(syllables) >= len(slots):
                    raise ValueError(f'{identifier}: too many prescribed syllables')
                slot = slots[len(syllables)]
                if slot['clause_index'] != index:
                    raise ValueError(f'{identifier}: prescription disagrees with source clause {index}')
                lexical = slot['readings']['mandarin']
                selected = lexical['selected']
                if selected and to_tone3(selected['reading'], neutral_tone_with_five=True) != pinyin:
                    raise ValueError(f'{identifier}/{slot["slot_index"]}: contradicts reviewed Mandarin reading')
                candidates = [to_tone3(item['reading'], neutral_tone_with_five=True)
                              for item in lexical['candidates']]
                if pinyin not in candidates:
                    conflicts.append({'slot_index': slot['slot_index'], 'char': slot['char'],
                                      'input_pinyin': pinyin, 'lexical_candidates': candidates})
                syllables.append(pinyin)
                phones.append(encode(pinyin))
        if len(syllables) == start_index or (len(syllables) < len(slots) and
                slots[len(syllables)]['clause_index'] == index):
            raise ValueError(f'{identifier}: incomplete pronunciation for source clause {index}')
        phones.append(slots[len(syllables) - 1]['marks_after'].translate(PUNCTUATION))
    if len(syllables) != len(slots):
        raise ValueError(f'{identifier}: prescription has {len(syllables)} syllables, expected {len(slots)}')
    sequence = ''.join(phones)
    if not sequence or len(sequence) > 510:
        raise ValueError(f'{identifier}: invalid Kokoro input length {len(sequence)}')
    return syllables, sequence, conflicts


def run(args):
    from misaki.zh_frontend import ZH_MAP
    from pypinyin.contrib.tone_convert import to_finals_tone3, to_initials, to_tone3

    root = args.root.resolve(strict=True)
    source = root / 'data' / 'pilot' / 'annotated.jsonl'
    passages = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line.strip()]
    prescribed = json.loads(args.readings.read_text(encoding='utf-8'))
    requested = set(args.passage_id or prescribed)
    selected = {p['passage_id']: p for p in passages if p['passage_id'] in requested}
    missing = requested - selected.keys() | requested - prescribed.keys()
    if missing or not selected:
        raise ValueError(f'Requested passages without a witness or a pronunciation prescription: {sorted(missing)}')

    def encode(pinyin):
        return encode_syllable(pinyin, ZH_MAP, to_initials, to_finals_tone3)

    prepared = {identifier: prepare_passage(passage, prescribed[identifier], encode, to_tone3)
                for identifier, passage in selected.items()}
    for identifier, (syllables, _, conflicts) in prepared.items():
        print(f'{identifier}: {len(syllables)} intended syllables, {len(conflicts)} open lexical disagreements', flush=True)
        if conflicts:
            print(json.dumps(conflicts, ensure_ascii=False), flush=True)
    if args.validate_only:
        return

    from huggingface_hub import hf_hub_download
    from kokoro import KModel
    from loguru import logger
    import soundfile as sf
    import torch

    logger.disable('kokoro')
    if not torch.cuda.is_available():
        raise RuntimeError('A CUDA GPU is required for synthesis. Run inside the Gilbreth Slurm allocation.')
    cache = root / 'cache' / 'hf' / 'hub'
    voices = tuple(dict.fromkeys(args.voice or VOICES))
    speeds = tuple(dict.fromkeys(args.speed or SPEEDS))

    def download(filename):
        path = Path(hf_hub_download(REPO, filename, revision=REVISION, cache_dir=cache,
                                    local_files_only=args.offline))
        expected = ASSET_SHA256.get(filename)
        if expected and sha256(path) != expected:
            raise ValueError(f'SHA-256 mismatch for pinned Kokoro asset {filename}')
        return path

    config_path = download('config.json')
    model = KModel(repo_id=REPO, config=str(config_path), model=str(download(CHECKPOINT))).to('cuda').eval()
    for identifier, (_, sequence, _) in prepared.items():
        unknown = set(sequence) - model.vocab.keys()
        if unknown:
            raise ValueError(f'{identifier}: Kokoro does not support {sorted(unknown)}')
    voice_tensors = {voice: torch.load(download(f'voices/{voice}.pt'), map_location='cpu', weights_only=True)
                     for voice in voices}
    raw = root / 'audio' / 'raw' / 'synthetic'
    manifest = root / 'audio' / 'manifests' / 'synthetic.jsonl'
    raw.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for identifier, passage in selected.items():
        pinyin, sequence, conflicts = prepared[identifier]
        for voice, pack in voice_tensors.items():
            for speed in speeds:
                clip_id = f'kokoro-{identifier}-{voice}-{speed.replace(".", "p")}'
                destination = raw / f'{clip_id}.wav'
                seed = int(hashlib.sha256(clip_id.encode()).hexdigest()[:8], 16)
                torch.manual_seed(seed)
                waveform = model(sequence, pack[len(sequence) - 1], speed=float(speed))
                if waveform.ndim != 1 or waveform.numel() == 0 or not torch.isfinite(waveform).all():
                    raise ValueError(f'{clip_id}: invalid synthesized waveform')
                with NamedTemporaryFile(dir=raw, suffix='.wav', delete=False) as temporary:
                    staged = Path(temporary.name)
                try:
                    sf.write(staged, waveform.numpy(), SAMPLE_RATE, subtype='PCM_16')
                    staged.replace(destination)
                finally:
                    staged.unlink(missing_ok=True)
                rows.append({
                    'recording_id': clip_id, 'passage_id': identifier,
                    'audio_path': str(destination.relative_to(root)),
                    'audio_sha256': sha256(destination), 'sample_rate': SAMPLE_RATE,
                    'duration_s': waveform.numel() / SAMPLE_RATE,
                    'kind': 'synthetic', 'variety': 'cmn', 'style': 'controlled_read_speech',
                    'speaker': voice, 'speed': float(speed), 'seed': seed,
                    'source_url': f'https://huggingface.co/{REPO}/tree/{REVISION}',
                    'model_revision': REVISION, 'model_license': 'Apache-2.0',
                    'text_sha256': passage['text_sha256'], 'text_revision': passage['revision_id'],
                    'text_source_url': passage['source_url'], 'text_license': passage['license'],
                    'intended_pinyin': pinyin, 'intended_model_phonemes': sequence,
                    'lexical_disagreements': conflicts, 'pronunciation_status': 'input_only',
                })
    with NamedTemporaryFile('w', dir=manifest.parent, encoding='utf-8', delete=False) as staged:
        try:
            for row in rows:
                staged.write(json.dumps(row, ensure_ascii=False) + '\n')
            staged.flush()
            Path(staged.name).replace(manifest)
        finally:
            Path(staged.name).unlink(missing_ok=True)
    print(f'Wrote {len(rows)} synthetic WAV recordings to {raw}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--readings', type=Path, default=READINGS)
    parser.add_argument('--passage-id', action='append')
    parser.add_argument('--voice', action='append', choices=(*VOICES, MALE_VOICE))
    parser.add_argument('--speed', action='append', choices=SPEEDS)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--offline', action='store_true')
    run(parser.parse_args())


if __name__ == '__main__':
    main()
