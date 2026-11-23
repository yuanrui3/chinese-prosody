"""Render a detector-blind waveform and spectrogram audit from original ManDi PCM."""

import argparse
import json
from math import ceil
from pathlib import Path
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import spectrogram


def render_window(root, output, row):
    with wave.open(str(root / row['path']), 'rb') as handle:
        if (handle.getnchannels(), handle.getsampwidth()) != (1, 2):
            raise ValueError('Expected original mono 16-bit PCM')
        rate = handle.getframerate()
        pcm = np.frombuffer(handle.readframes(handle.getnframes()), dtype='<i2').astype('float32') / 32768
    import colorsys

    span = 3.0
    start = row['visual_start_s']
    end = row['visual_end_s']
    origin = np.floor(start * 10) / 10
    sections = ceil((end - origin) / span)
    size = round(rate * 0.014)
    frequencies, times, power = spectrogram(pcm, fs=rate, nperseg=size, noverlap=size - round(rate * 0.003))
    log_power = 10 * np.log10(np.maximum(power, 1e-14))
    ceiling = np.percentile(log_power[(frequencies > 100) & (frequencies < 6500)], 99.6)
    limit = min(1.0, max(0.05, np.percentile(np.abs(pcm), 99.8)))
    width, row_height, margin = 1050, 137, 35
    image = Image.new('RGB', (width + 2 * margin, row_height * sections + 31), '#f8fafc')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((margin, 7), f"{row['id']}  |  scored window {start:.3f} to {end:.3f} s  |  time in seconds",
              font=font, fill='#102a43')
    palette = np.array([[round(255 * x) for x in colorsys.hsv_to_rgb((0.68 + 0.45 * i / 255) % 1,
                                                                    0.84, (i / 255) ** 0.76)]
                        for i in range(256)], dtype='uint8')
    for index in range(sections):
        lo = origin + span * index
        hi = lo + span
        y = 27 + index * row_height
        frame_times = np.linspace(lo, hi, width, endpoint=False)
        spec_bins = np.minimum(len(times) - 1, np.searchsorted(times, frame_times))
        last_equal = np.abs(times[spec_bins] - frame_times) <= np.abs(times[spec_bins - 1] - frame_times)
        spec_bins = np.maximum(0, spec_bins - ~last_equal)
        freq = np.searchsorted(frequencies, np.linspace(7000, 0, 77))
        band = log_power[np.ix_(freq, spec_bins)]
        pixels = np.clip((band - ceiling + 64) * (255 / 64), 0, 255).astype('uint8')
        image.paste(Image.fromarray(palette[pixels]), (margin, y + 36))
        draw.line((margin, y + 16, margin + width, y + 16), fill='#acb0b9')
        stride = max(1, round(rate * span / width))
        bounds = np.round(frame_times * rate).astype('int64')
        for i, beginning in enumerate(bounds):
            if beginning >= len(pcm):
                break
            chunk = pcm[beginning:beginning + stride]
            upper = 16 * min(1.0, chunk.max() / limit)
            lower = 16 * max(-1.0, chunk.min() / limit)
            draw.line((margin + i, y + 16 - upper, margin + i, y + 16 - lower), fill='#172c3f')
        for j in range(31):
            x = margin + j * width // 30
            draw.line((x, y + 112, x, y + 119), fill='#536575')
            draw.line((x, y, x, y + 4), fill='#536575')
            draw.text((x, y + 119), f'{lo + j / 10:.1f}', anchor='mt', font=font, fill='#172c3f')
        for a, b in ((lo, min(hi, start)), (max(lo, end), hi)):
            if b > a:
                x1 = margin + round((a - lo) * width / span)
                x2 = margin + round((b - lo) * width / span)
                draw.rectangle((x1, y, x2, y + 112), fill='#d7dde5')
    image.save(output / (row['id'] + '.png'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio-root', type=Path, required=True)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True)
    for row in json.loads(args.references.read_text(encoding='utf-8'))['recordings']:
        render_window(args.audio_root, args.output, row)
        print(row['id'], flush=True)


if __name__ == '__main__':
    main()
