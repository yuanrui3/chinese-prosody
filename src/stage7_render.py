"""Render transparent component reports and optional clause playback."""

from base64 import b64encode
import hashlib
from html import escape
from io import BytesIO
from math import ceil, floor
import wave

from src.text_metrics import METRIC_LABELS, slot_label


def number(value):
    return '—' if value is None else f'{value:.3f}'.rstrip('0').rstrip('.')


def window(clause):
    if clause.get('start_s') is not None:
        return f"{number(clause['start_s'])}–{number(clause['end_s'])} s"
    if clause.get('draft_span_start_s') is not None:
        return f"{number(clause['draft_span_start_s'])}–{number(clause['draft_span_end_s'])} s (linked part)"
    return '—'


def metric_rows(metrics):
    for name, label in METRIC_LABELS.items():
        cells = []
        for tier in ('guangyun', 'pingshui'):
            row = metrics[tier][name]
            interval = (f" [{number(row['lower'])}, {number(row['upper'])}]"
                        if row['lower'] is not None and row['lower'] != row['upper'] else '')
            cells.append(f"{number(row['value'])}{interval} ({row['usable']}/{row['eligible']})")
        yield label, *cells


def source_lines(text, audio):
    reference = text['reference']
    witness = reference['witness']
    result = [f"Passage {text['passage_id']} · {reference['annotation_source'].replace('_', ' ')}"]
    if witness:
        result.append(' · '.join(str(witness[key]) for key in ('title', 'author', 'revision_id', 'source_url')
                                 if witness.get(key)))
        rights = ' · '.join(str(witness[key]) for key in ('work_rights', 'license', 'attribution') if witness.get(key))
        if rights:
            result.append(rights)
    result.append('Historical candidates · ' + ' · '.join(
        f"{book['title']} {'available' if book['available'] else 'unavailable'}"
        for book in reference['historical'].values()
    ))
    if audio:
        recording = audio['recording']
        result.append('Recording · ' + ' · '.join(
            str(recording[key]) for key in ('recording_id', 'kind', 'speaker', 'style', 'variety', 'recording_rights')
            if recording.get(key)
        ))
        result.append(f"{audio['method']} · {number(audio['duration_s'])} s")
    return result


def clause_labels(indices):
    return ', '.join(f'C{index + 1}' for index in indices)


def findings(text, audio):
    return [('Text observations', text['observations']),
            *([('Audio observations', audio['observations'])] if audio else [])]


def clause_rows(paragraph, acoustic, show_audio):
    if not paragraph['clauses']:
        yield paragraph['text'], '', '', '', ''
    for item in paragraph['clauses']:
        index = item['clause_index']
        final = item['slots'][-1]
        ending = ' · '.join(label or '—' for label in (
            slot_label(final, 'guangyun', 'pingze'), slot_label(final, 'guangyun', 'rhyme')
        ))
        draft = acoustic.get(index, {})
        audio_support = (f"{window(draft)} · {number(draft.get('articulation_ms'))} ms linked articulation · "
                         f"{draft.get('slots_measured', 0)}/{len(item['slots'])} timed · "
                         f"{number(draft.get('matched_slots_per_s'))} linked slots/s" if show_audio else '')
        yield item['text'], f'C{index + 1}', str(len(item['slots'])), ending, audio_support


GAP_HEADER = ('After written slot', 'Recording interval', 'Gap (ms)', 'Location')


def quiet_gap_rows(audio):
    for row in audio['gaps']:
        if 150 in row['quiet_candidate_ms_thresholds']:
            yield (str(row['after_slot_index'] + 1), f"{number(row['start_s'])}–{number(row['end_s'])} s",
                   number(row['gap_ms']), 'Punctuation' if row['boundary_after'] else 'Within clause')


def md_cell(cell):
    return escape(str(cell), quote=False).replace('|', r'\|').replace('\n', ' ⏎ ').replace('\r', '')


def md_table(header, rows):
    return ['| ' + ' | '.join(map(md_cell, row)) + ' |'
            for row in [header, tuple('---' for _ in header), *rows]]


SUPPORT = 'Component values show determinate/eligible comparisons in parentheses. Brackets show feasible bounds where available.'
AUDIO_SCOPE = 'Draft timings, quiet gaps, slow spans, and decoder discrepancies mark places for review. Reviewed events are labeled in the audio data.'


def render_markdown(report):
    text, audio = report['text'], report['audio']
    acoustic = {row['clause_index']: row for row in audio['clauses']} if audio else {}
    headings = ('Clause', 'Text', 'Han slots', '廣韻 ending') + (('Audio timeline',) if audio else ())
    out = ['# Prosody report', '', *(md_cell(line) + '  ' for line in source_lines(text, audio)),
           '', SUPPORT, '', '## Document components', '',
           *md_table(('Component', '廣韻', '平水韻'), metric_rows(text['metrics']))]
    if audio:
        out.extend(['', AUDIO_SCOPE])
        gaps = list(quiet_gap_rows(audio))
        if gaps:
            out.extend(['', '## Quiet-gap candidates ≥150 ms', '', *md_table(GAP_HEADER, gaps)])
    for name, group in findings(text, audio):
        out.extend(['', f'## {name}', ''])
        out.extend(f"{rank}. **{clause_labels(row['clause_indices'])}** · {md_cell(row['reason'])}"
                   for rank, row in enumerate(group, 1))
        if not group:
            out.append('No ranked observations met the reporting criteria.')
    for paragraph in text['paragraphs']:
        out.extend(['', f"## Paragraph {paragraph['paragraph_index'] + 1}", '',
                    *md_table(headings, [
                        (code, wording, count, ending, timeline) if audio else (code, wording, count, ending)
                        for wording, code, count, ending, timeline in clause_rows(paragraph, acoustic, bool(audio))
                    ]), '', *md_table(('Component', '廣韻', '平水韻'), metric_rows(paragraph['metrics']))])
    return '\n'.join(out) + '\n'


def audio_clips(wav, acoustic, checksum):
    clips = {}
    waveform = wav.read_bytes()
    if hashlib.sha256(waveform).hexdigest() != checksum:
        raise ValueError('The waveform changed before rendering clause playback')
    try:
        with wave.open(BytesIO(waveform), 'rb') as media:
            rate = media.getframerate()
            for index, clause in acoustic.items():
                start, end = clause.get('start_s'), clause.get('end_s')
                if start is None:
                    start, end = clause.get('draft_span_start_s'), clause.get('draft_span_end_s')
                if start is None or end is None:
                    continue
                first = max(0, floor(start * rate))
                last = min(media.getnframes(), ceil(end * rate))
                if last <= first:
                    continue
                media.setpos(first)
                samples = media.readframes(last - first)
                encoded = BytesIO()
                with wave.open(encoded, 'wb') as clip:
                    clip.setnchannels(media.getnchannels())
                    clip.setsampwidth(media.getsampwidth())
                    clip.setframerate(rate)
                    clip.writeframes(samples)
                clips[index] = b64encode(encoded.getvalue()).decode('ascii')
    except (EOFError, wave.Error):
        return {}, 'Clause playback requires a PCM WAV supported by Python’s wave reader.'
    return clips, None


def html_table(header, rows):
    return ('<table><thead><tr>' + ''.join(f'<th scope="col">{escape(label)}</th>' for label in header)
            + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{escape(cell)}</td>' for cell in row)
                                             + '</tr>' for row in rows) + '</tbody></table>')


def render_html(report, wav=None):
    text, audio = report['text'], report['audio']
    acoustic = {row['clause_index']: row for row in audio['clauses']} if audio else {}
    clips, playback_note = (audio_clips(wav, acoustic, audio['recording']['audio_sha256'])
                            if audio and wav else ({}, None))
    groups = findings(text, audio)
    flagged = {f'C{index + 1}' for _, group in groups for row in group for index in row['clause_indices']}
    body = ['<h1>Prosody report</h1>', '<ul class="sources">',
            *(f'<li>{escape(line)}</li>' for line in source_lines(text, audio)), '</ul>',
            f'<p>{escape(SUPPORT)}</p>', '<h2>Document components</h2>',
            html_table(('Component', '廣韻', '平水韻'), metric_rows(text['metrics']))]
    if audio:
        body.append(f'<p>{escape(AUDIO_SCOPE)}</p>')
        gaps = list(quiet_gap_rows(audio))
        if gaps:
            body.extend(['<h2>Quiet-gap candidates ≥150 ms</h2>', html_table(GAP_HEADER, gaps)])
    if playback_note:
        body.append(f'<p>{escape(playback_note)}</p>')
    for name, group in groups:
        body.append(f'<h2>{name}</h2>')
        if group:
            body.append('<ol>')
            for row in group:
                links = ', '.join(f'<a href="#C{index + 1}">C{index + 1}</a>' for index in row['clause_indices'])
                body.append(f'<li>{links} · {escape(row["reason"])}</li>')
            body.append('</ol>')
        else:
            body.append('<p>No ranked observations met the reporting criteria.</p>')
    for paragraph in text['paragraphs']:
        body.append(f'<h2>Paragraph {paragraph["paragraph_index"] + 1}</h2>')
        for wording, code, count, ending, timeline in clause_rows(paragraph, acoustic, bool(audio)):
            if not code:
                body.append(f'<p class="wording">{escape(wording)}</p>')
                continue
            highlight = ' class="flagged"' if code in flagged else ''
            body.extend([f'<article id="{code}"{highlight}>', f'<h3>{code}</h3>',
                         f'<p class="wording" lang="zh-Hant">{escape(wording)}</p>',
                         f'<p>{count} Han slots · 廣韻 {escape(ending)}</p>'])
            if timeline:
                body.append(f'<p>{escape(timeline)}</p>')
            clip = clips.get(int(code[1:]) - 1)
            if clip:
                part = ' linked part' if acoustic[int(code[1:]) - 1].get('start_s') is None else ''
                body.append(f'<audio controls controlslist="nodownload" preload="none" aria-label="Play {code}{part}" '
                            f'src="data:audio/wav;base64,{clip}"></audio>')
            body.append('</article>')
        body.extend(['<details><summary>Paragraph components</summary>',
                     html_table(('Component', '廣韻', '平水韻'), metric_rows(paragraph['metrics'])), '</details>'])
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prosody report</title><style>
body { max-width: 52rem; margin: 2rem auto; padding: 0 1rem; color: #182b30;
  background: #faf9f5; font: 1rem/1.55 system-ui, sans-serif; overflow-wrap: anywhere; }
h1, h2, h3 { line-height: 1.2; } a { color: #135e61; }
table { width: 100%; border-collapse: collapse; } th, td { padding: .35rem .5rem;
  border-bottom: 1px solid #c4cecb; text-align: left; vertical-align: top; }
.sources { padding-left: 1.2rem; } article, details { border: 1px solid #c4cecb;
  background: white; border-radius: .45rem; margin: .55rem 0; padding: .65rem .85rem; }
article.flagged { border-inline-start: .3rem solid #8b561c; background: #fffaf0; }
article h3, article p { margin: .25rem 0; }
.wording { font-size: 1.2rem; white-space: pre-wrap; }
audio { width: min(100%, 25rem); } summary { cursor: pointer; }
</style></head><body><main>\n''' + '\n'.join(body) + '\n</main></body></html>\n'
