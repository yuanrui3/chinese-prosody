"""Build the two participant pages for an authenticated Gilbreth server."""

import argparse
from base64 import b64encode
from hashlib import sha256
from html import escape
import os
from pathlib import Path

from src.stage6_listening import PRIVATE_DIR, STIMULUS_DIR, check_staged, read_json, read_rows


def clip_texts(root, staged, survey):
    key = read_json(root / PRIVATE_DIR / 'unblinding.json')
    if check_staged(staged, key) != survey or [
        trial['trial_id'] for trial in key['trials']
    ] != [trial['trial_id'] for trial in survey['trials']]:
        raise ValueError('Private key and anonymous trial order disagree')
    passages = {row['passage_id']: row for row in read_rows(root / 'data/pilot/annotated.jsonl')}
    texts = {}
    for trial in key['trials']:
        code = trial['trial_id']
        texts[code] = {}
        for side in 'AB':
            provenance = trial[side]['text_provenance']
            passage = passages[provenance['passage_id']]
            text = passage['text']
            if not sha256(text.encode('utf-8')).hexdigest() == passage['text_sha256'] == provenance['text_sha256']:
                raise ValueError(f'Pinned text differs from clip provenance for {code} {side}')
            texts[code][side] = text
    return texts


def listening_page(survey, staged, *, overall=False, transcripts=None, form_code=None):
    if overall:
        options = [(number, number) for number in range(1, 8)] + [('略', '略過')]
        directions = '每組先聽 A、再聽 B，可重聽一次。請考慮兩段的節奏、停頓和聲音搭配，給整組一個分數。'
        reply = '複製下方一行回覆。1＝整組很不悅耳，7＝整組很悅耳，略＝跳過。'
        blank = ' '.join(f"{escape(trial['trial_id'])}=＿" for trial in survey['trials'])
    else:
        options = [('A', 'A'), ('B', 'B'), ('=', '差不多'), ('略', '略過')]
        directions = '每組先聽 A、再聽 B。哪一段的節奏、停頓和聲音搭配更好聽？可重聽一次。聽完這份再開始朗讀。'
        reply = '把這一行回覆到對話中。A 或 B＝較好聽，＝表示差不多，略＝跳過。'
        blank = 'L01=＿ L02=＿ L03=＿ L04=＿'
    title = '音律美盲聽'
    form_note = ''
    transcript_style = ''
    if transcripts is not None:
        title = '音律美試聽（附原文）'
        directions = '每組先聽 A、再聽 B，可對照播放器下方的原文。聽完兩段，給整組一個分數。'
        transcript_style = '\n  .transcript { margin: .35rem 0; line-height: 1.7; white-space: pre-wrap; }'
    if form_code is not None:
        title = '音律美試聽'
        directions = '每組先聽 A、再聽 B，可重聽一次。請考慮兩段的節奏、停頓和聲音搭配，給整組一個分數。'
        form_note = (f'<p>回覆時附上試測代號 <code>{escape(form_code)}</code>。'
                     '如果以前讀過其中一段，或聽過這段錄音，請註明組別和 A 或 B。</p>\n')
    trials = []
    for trial in survey['trials']:
        code = escape(trial['trial_id'])
        players = []
        for side in 'AB':
            # Jupyter sandboxes served HTML. An embedded source needs no separate
            # credentialed browser request, and the HTML itself stays on Gilbreth.
            audio = b64encode((staged / trial[side]).read_bytes()).decode('ascii')
            player = (f'<label>{side}<audio aria-label="{code} {side}" '
                      f'controls controlslist="nodownload" preload="none" '
                      f'src="data:audio/wav;base64,{audio}"></audio></label>')
            if transcripts is not None:
                line = escape(transcripts[trial['trial_id']][side])
                player = f'<div>{player}<p class="transcript">{line}</p></div>'
            players.append(player)
        choices = ''.join(
            f'<label><input type="radio" name="{code}" value="{value}"> {label}</label>'
            for value, label in options
        )
        trials.append(f'<fieldset><legend>{code}</legend><div class="players">{"".join(players)}</div>'
                      f'<div class="choices">{choices}</div></fieldset>')
    content = '\n'.join(trials)
    return f'''<!doctype html>
<html lang="zh-Hant">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ background: #f6f5f1; color: #162733; font: 1rem/1.65 system-ui, sans-serif;
    max-width: 44rem; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ font-size: 1.75rem; line-height: 1.25; margin-bottom: .5rem; }}
  fieldset {{ margin: .8rem 0; padding: .65rem .85rem; background: white;
    border: 1px solid #c9cfce; border-radius: .5rem; }}
  legend {{ font-weight: 650; padding: 0 .3rem; }}
  .players {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); gap: .55rem; }}
  audio {{ display: block; width: 100%; height: 2.4rem; }}
  .choices {{ display: flex; flex-wrap: wrap; gap: .25rem 1rem; margin-top: .65rem; }}
  output {{ display: block; color: #1a514b; font: 600 .95rem/1.6 ui-monospace, monospace; }}{transcript_style}
</style>
<main>
<h1>{title}</h1>
<p>{directions}</p>
{form_note}<form id="survey">
{content}
</form>
<p>{reply}</p>
<output id="response">{blank}</output>
</main>
<script>
const survey = document.getElementById('survey');
survey.addEventListener('change', () => {{
  const choices = new FormData(survey);
  document.getElementById('response').textContent = Array.from(survey.elements)
    .filter(element => element.tagName === 'FIELDSET')
    .map(element => {{
      const code = element.querySelector('legend').textContent;
      return code + '=' + (choices.get(code) || '＿');
    }}).join(' ');
}});
</script>
</html>
'''


def prepare(root, *, overall=False, with_text=False):
    if with_text and not overall:
        raise ValueError('A transcript page requires --overall')
    staged = root / STIMULUS_DIR
    production = staged.parent / 'production/read-aloud.html'
    survey = read_json(staged / 'survey.json')
    if not overall and not production.is_file():
        raise FileNotFoundError(production)
    prefix = 'M' if overall else 'L'
    for index, trial in enumerate(survey['trials'], 1):
        code = f'{prefix}{index:02d}'
        if trial != {'trial_id': code, 'A': f'{code}-A.wav', 'B': f'{code}-B.wav'}:
            raise ValueError('Expected only anonymous trial codes and file names')
        if not all((staged / trial[side]).is_file() for side in 'AB'):
            raise ValueError(f'Missing media for {code}')
    presentation = staged.parent / 'web'
    presentation.mkdir(exist_ok=True, mode=0o700)
    if not overall:
        destination = presentation / 'read-aloud.html'
        if not destination.is_symlink():
            destination.symlink_to(production)
        if destination.resolve(strict=True) != production:
            raise ValueError(f'Unexpected participant link {destination}')
    transcripts = clip_texts(root, staged, survey) if with_text else None
    path = presentation / ('with-text.html' if with_text else 'index.html')
    path.write_text(listening_page(survey, staged, overall=overall, transcripts=transcripts), encoding='utf-8')
    return path


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--overall', action='store_true', help='Build a listening-only, 1–7 pair rating page for M trials')
    parser.add_argument('--with-text', action='store_true', help='Add the exact Chinese text below each overall clip')
    args = parser.parse_args()
    if args.with_text and not args.overall:
        parser.error('--with-text requires --overall')
    print(prepare(args.root.resolve(strict=True), overall=args.overall, with_text=args.with_text))


if __name__ == '__main__':
    main()
