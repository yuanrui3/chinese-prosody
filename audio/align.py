"""Decode Mandarin phones from the waveform, then link syllables to text slots."""

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
from itertools import groupby
import json
import math
from pathlib import Path
import re
from statistics import mean
from tempfile import TemporaryDirectory
import unicodedata


MODEL = 'charsiu/zh_w2v2_tiny_fc_10ms'
MODEL_REVISION = 'dde9cc1a048e2cb16d0d741deeae5ea9bd634ffe'
VOCAB = 'charsiu/tokenizer_zh_pinyin'
VOCAB_REVISION = 'a370e90191d18be4035783a7b98c509666e5c058'
SAMPLE_RATE = 16_000
ONSET = re.compile(r'^(zh|ch|sh|[bpmfdtnlgkhjqxrzcs])')
FINAL = re.compile(r'^[a-zv:]+[1-5]$')
MIN_FINAL_S = 0.03
TONE_MARKS = {'\u0304': '1', '\u0301': '2', '\u030c': '3', '\u0300': '4'}


@dataclass(frozen=True)
class Phone:
    label: str
    start_s: float
    end_s: float
    confidence: float


@dataclass
class HeardSyllable:
    phones: list
    key: tuple
    tone: str


def lexical_key(reading):
    """Return comparable Charsiu onset, final and tone labels for lexical pinyin."""
    reading = reading.casefold().replace('u:', 'v')
    decomposed = unicodedata.normalize('NFD', reading).replace('u\u0308', 'v')
    tone = next((TONE_MARKS[mark] for mark in decomposed if mark in TONE_MARKS), None)
    plain = ''.join(char for char in decomposed if not unicodedata.combining(char))
    if plain and plain[-1] in '012345':
        tone, plain = plain[-1], plain[:-1]
    match = ONSET.match(plain)
    onset = match[0] if match else ''
    final = plain[len(onset):]
    if plain.startswith('y'):
        tail = plain[1:]
        if tail.startswith(('u', 'v')):
            final = 'v' + tail[1:]
        else:
            final = tail if tail.startswith('i') else 'i' + tail
    elif plain.startswith('w'):
        tail = plain[1:]
        final = tail if tail.startswith('u') else 'u' + tail
    elif onset in ('j', 'q', 'x') and final.startswith('u'):
        final = 'v' + final[1:]
    if final == 'i' and onset in ('z', 'c', 's', 'zh', 'ch', 'sh', 'r'):
        final = 'ii' if onset in ('z', 'c', 's') else 'iii'
    final = {'iu': 'iou', 'uei': 'ui', 'uen': 'un', 'u:e': 've', 'u:': 'v'}.get(final, final)
    return (onset, final), '5' if tone in (None, '0') else tone


def frame_runs(labels, confidence, step_s, duration_s):
    offset = 0
    for label, group in groupby(labels):
        size = sum(1 for _ in group)
        stop = offset + size
        end_s = min(duration_s, stop * step_s)
        if offset * step_s < end_s:
            yield Phone(label, offset * step_s, end_s, float(mean(confidence[offset:stop])))
        offset = stop


def heard_syllables(phones):
    """Group independently decoded onset and tone-bearing final runs."""
    result = []
    onset = None
    for phone in phones:
        label = phone.label
        if ONSET.fullmatch(label):
            onset = phone
        elif FINAL.fullmatch(label):
            adjacent = onset is not None and abs(onset.end_s - phone.start_s) < 1e-6
            final = label[:-1].replace('u:', 'v')
            tone = label[-1]
            if phone.end_s - phone.start_s + 1e-8 >= MIN_FINAL_S:
                key = (onset.label if adjacent else '', final)
                result.append(HeardSyllable([onset, phone] if adjacent else [phone], key, tone))
            onset = None
        elif label == 'rr' and result and abs(result[-1].phones[-1].end_s - phone.start_s) < 1e-6:
            result[-1].phones.append(phone)
            if result[-1].key == ('', 'e'):
                result[-1].key = ('', 'er')
        else:
            onset = None
    return result


def match_cost(candidates, observed):
    if (observed.key, observed.tone) in candidates:
        return 0, 'segment_and_tone'
    if any(key == observed.key for key, _ in candidates):
        return 0.24, 'segment_only'
    if not candidates:
        return 1.6, 'no_lexical_anchor'
    return 1.6, 'different_segments'


def link_slots(slots, heard, *, ending_pinyin=None):
    # Edit alignment preserves discrepancies instead of assigning all source syllables times.
    n, m = len(slots), len(heard)
    expected = []
    for slot in slots:
        if ending_pinyin is not None and slot['slot_index'] == ending_pinyin[0]:
            expected.append({lexical_key(ending_pinyin[1])})
            continue
        lookup = slot['readings']['mandarin']
        choices = [lookup['selected']] if lookup.get('selected') else lookup['candidates']
        expected.append({lexical_key(item['reading']) for item in choices})
    costs = [[0.0] * (m + 1) for _ in range(n + 1)]
    steps = [[''] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        costs[i][0], steps[i][0] = float(i), 'omission'
    for j in range(1, m + 1):
        costs[0][j], steps[0][j] = float(j), 'insertion'
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            change, _ = match_cost(expected[i - 1], heard[j - 1])
            options = [(costs[i - 1][j - 1] + change, 'linked'),
                       (costs[i - 1][j] + 1, 'omission'), (costs[i][j - 1] + 1, 'insertion')]
            costs[i][j], steps[i][j] = min(options, key=lambda option: option[0])
    result = []
    i, j = n, m
    while i or j:
        step = steps[i][j]
        if step == 'linked':
            change, basis = match_cost(expected[i - 1], heard[j - 1])
            result.append((slots[i - 1], heard[j - 1], 'matched' if change < 1 else 'substitution', basis))
            i, j = i - 1, j - 1
        elif step == 'omission':
            result.append((slots[i - 1], None, 'omission', None))
            i -= 1
        else:
            result.append((None, heard[j - 1], 'insertion', None))
            j -= 1
    return list(reversed(result))


class MandarinDecoder:
    def __init__(self, root, offline):
        import torch
        from huggingface_hub import hf_hub_download, snapshot_download
        from transformers import Wav2Vec2ForCTC

        if not torch.cuda.is_available():
            raise RuntimeError('Run acoustic decoding on an allocated Gilbreth GPU')
        cache = root / 'cache' / 'hf' / 'hub'
        model_path = snapshot_download(MODEL, revision=MODEL_REVISION, cache_dir=cache,
                                       allow_patterns=['config.json', 'pytorch_model.bin'], local_files_only=offline)
        vocab_path = Path(hf_hub_download(VOCAB, 'vocab.json', revision=VOCAB_REVISION,
                                         cache_dir=cache, local_files_only=offline))
        vocab = json.loads(vocab_path.read_text(encoding='utf-8'))
        self.labels = {index: label for label, index in vocab.items()}
        self.torch = torch
        # The upstream frame classifier subclasses ForCTC and shares its inference head.
        model, load_info = Wav2Vec2ForCTC.from_pretrained(
            model_path, output_loading_info=True, local_files_only=True, use_safetensors=False,
        )
        if load_info['missing_keys'] or load_info['mismatched_keys']:
            raise ValueError(f'Incomplete Charsiu weights: {load_info}')
        if set(range(model.config.vocab_size)) - self.labels.keys():
            raise ValueError('Charsiu vocabulary does not cover all output channels')
        self.step_s = math.prod(model.config.conv_stride) / SAMPLE_RATE
        self.model = model.to('cuda').eval()

    def decode(self, path):
        import numpy as np
        from scipy.signal import resample_poly
        import soundfile as sf

        samples, rate = sf.read(path, dtype='float32', always_2d=True)
        duration = len(samples) / rate
        if not 0.1 <= duration <= 60:
            raise ValueError(f'{path}: cut a licensed passage clip of 0.1 to 60 seconds before alignment')
        samples = samples.mean(axis=1)
        if rate != SAMPLE_RATE:
            divisor = math.gcd(rate, SAMPLE_RATE)
            samples = resample_poly(samples, SAMPLE_RATE // divisor, rate // divisor)
        variance = samples.var()
        if not np.isfinite(variance) or variance < 1e-12:
            raise ValueError(f'{path}: audio is silent or invalid')
        samples = (samples - samples.mean()) / np.sqrt(variance + 1e-7)
        with self.torch.inference_mode():
            logits = self.model(self.torch.from_numpy(samples[None]).to('cuda')).logits[0]
            confidence, ids = logits.float().softmax(dim=-1).max(dim=-1)
        return list(frame_runs((self.labels[index] for index in ids.cpu().tolist()),
                               confidence.cpu().tolist(), self.step_s, duration))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        with temporary.open('w', encoding='utf-8') as output:
            for row in rows:
                output.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        temporary.replace(path)


def experimental_ending_hint(recording, passage):
    ending = recording['experimental_ending']
    index = ending['target_slot_index']
    slots = passage['slots']
    pinyin = recording['intended_pinyin']
    if (recording['kind'] != 'synthetic' or ending['role'] not in ('base', 'sham', 'tone', 'rhyme')
            or len(pinyin) != len(slots) or not 0 <= index < len(slots) - 1
            or slots[index]['slot_index'] != index or not slots[index]['boundary_after']):
        raise ValueError('Expected a checked synthetic ending recipe at an internal boundary')
    segments, tone = lexical_key(pinyin[index])
    if tuple(ending['candidate_key']) != (*segments, tone):
        raise ValueError('The prescribed ending and the experimental key disagree')
    return index, pinyin[index]


def run(args):
    root = args.root.resolve(strict=True)
    passages = {row['passage_id']: row for row in read_rows(root / 'data/pilot/annotated.jsonl')}
    recordings = read_rows(args.recordings or root / 'audio/manifests/synthetic.jsonl')
    if not recordings or len({row['recording_id'] for row in recordings}) != len(recordings):
        raise ValueError('A nonempty recording manifest with unique recording IDs is required')
    if any(('experimental_ending' in row) != args.experimental_endings for row in recordings):
        raise ValueError('Use --experimental-endings with a manifest of experimental ending takes')
    decoder = MandarinDecoder(root, args.offline)
    alignments, drafts = [], []
    for recording in recordings:
        passage = passages[recording['passage_id']]
        if recording.get('variety') not in ('cmn', 'cmn-Hans', 'cmn-Hant'):
            raise ValueError('This decoder requires a confirmed Mandarin recording variety')
        if recording.get('text_sha256') != passage['text_sha256']:
            raise ValueError(f"{recording['recording_id']}: manifest does not match the pilot edition")
        media = (root / recording['audio_path']).resolve(strict=True)
        if not media.is_relative_to(root / 'audio' / 'raw'):
            raise ValueError('Recording waveform must resolve inside the Gilbreth project audio directory')
        if 'audio_sha256' in recording:
            digest = hashlib.sha256()
            with media.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            checksum = digest.hexdigest()
            if checksum != recording['audio_sha256']:
                raise ValueError(f"{recording['recording_id']}: waveform hash differs from the manifest")
        phones = decoder.decode(media)
        heard = heard_syllables(phones)
        hint = experimental_ending_hint(recording, passage) if args.experimental_endings else None
        base = {key: recording[key] for key in ('recording_id', 'passage_id', 'audio_path', 'variety')}
        base['kind'] = recording.get('kind', 'human')
        if 'audio_sha256' in recording:
            base['audio_sha256'] = checksum
        drafts.append({**base, 'frame_s': decoder.step_s, 'model_revision': MODEL_REVISION,
                       'phones': [vars(phone) for phone in phones]})
        for index, (slot, sound, status, basis) in enumerate(link_slots(passage['slots'], heard, ending_pinyin=hint)):
            observed = None if not sound else {'onset': sound.key[0], 'final': sound.key[1], 'tone': sound.tone}
            alignments.append({**base, 'event_index': index, 'status': status, 'match_basis': basis,
                               'slot_index': slot['slot_index'] if slot else None,
                               'start_s': sound.phones[0].start_s if sound else None,
                               'end_s': sound.phones[-1].end_s if sound else None,
                               'confidence': mean(phone.confidence for phone in sound.phones) if sound else None,
                               'observed_phone_draft': observed, 'realized_reading': None,
                               'reading_status': 'acoustic_draft' if sound else 'unobserved',
                               'alignment_source': ('charsiu_waveform_then_experimental_ending_link' if hint
                                                    else 'charsiu_waveform_only_then_lexical_link')})
    destination = args.out_dir or root / 'audio/derived/alignment'
    write_rows(destination / 'phone-drafts.jsonl', drafts)
    write_rows(destination / 'alignments.jsonl', alignments)
    print(json.dumps({'recordings': len(recordings), 'events': dict(Counter(row['status'] for row in alignments)),
                      'match_basis': dict(Counter(row['match_basis'] for row in alignments if row['match_basis'])),
                      'sample_grid_s': decoder.step_s, 'model_revision': MODEL_REVISION}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--recordings', type=Path)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--experimental-endings', action='store_true')
    run(parser.parse_args())


if __name__ == '__main__':
    main()
