"""Score exact text spans and optionally attach draft audio evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def project_root(explicit):
    if explicit is not None:
        return explicit.resolve(strict=True)
    if os.environ.get('SHUNKOU_ROOT'):
        return Path(os.environ['SHUNKOU_ROOT']).resolve(strict=True)
    if os.environ.get('RCAC_SCRATCH'):
        candidate = Path(os.environ['RCAC_SCRATCH']) / 'shunkou'
        if candidate.is_dir():
            return candidate.resolve()
    return None


def pinned_passage(root, text, requested_id):
    index = root / 'data/pilot/annotated.jsonl' if root else None
    if index is None or not index.is_file():
        if requested_id:
            raise ValueError('--passage-id needs the annotated pilot under --root')
        return None
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    with index.open(encoding='utf-8') as source:
        rows = (json.loads(line) for line in source if line.strip())
        if requested_id:
            row = next((item for item in rows if item.get('passage_id') == requested_id), None)
            if row is None:
                raise ValueError(f'Unknown pilot passage {requested_id!r}')
            if row.get('text_sha256') != digest or row.get('text') != text:
                raise ValueError(f'Text differs from the pinned witness for {requested_id!r}')
            return row
        matches = [row for row in rows if row.get('text_sha256') == digest and row.get('text') == text]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValueError('Multiple pilot records have this exact text. Select one with --passage-id')
    return None


def available_lexicons(root):
    from data.phonology.historical import load_historical
    from data.phonology.modern import ARCHIVE, load_modern

    if root is None:
        return {}
    raw = root / 'data/raw/phonology'
    lexicons = {}
    if (raw / 'guangyun.csv').is_file() and (raw / 'pingshui.html').is_file():
        lexicons.update(load_historical(raw))
    if (raw / ARCHIVE).is_file():
        modern, variants = load_modern(raw)
        lexicons.update(mandarin=modern['mandarin'], variants=variants)
    return lexicons


def score(args, output_format):
    from src.stage7_text import annotate_text, score_passage

    root = project_root(args.root)
    if args.audio and root is None:
        raise ValueError('Audio scoring requires --root or SHUNKOU_ROOT for the Gilbreth project')
    if args.audio and output_format == 'html':
        if args.output is None or not args.output.resolve().is_relative_to(root):
            raise ValueError('Save audio HTML with --output inside the Gilbreth project')
    text = args.file.read_bytes().decode('utf-8')
    pinned = pinned_passage(root, text, args.passage_id)
    passage = annotate_text(text, pinned_passage=pinned, **({} if pinned else available_lexicons(root)))
    report = {'schema_version': 1, 'text': score_passage(passage), 'audio': None}
    if args.audio:
        from src.stage7_audio import score_audio

        report['audio'] = score_audio(
            root, args.audio, passage, manifest=args.audio_manifest, alignment=args.alignment,
            decode=args.decode, variety=args.variety, rights=args.rights,
            speaker=args.speaker, style=args.style,
        )
    return report


def write_output(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as staged:
        temporary = Path(staged.name)
        try:
            staged.write(content)
            staged.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='shunkou', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('score', help='Describe prosody and rank local observations')
    command.add_argument('file', type=Path, help='UTF-8 input text. Blank lines separate paragraphs')
    command.add_argument('--root', type=Path, help='Gilbreth project data root')
    command.add_argument('--passage-id', help='Require an exact Stage 3 text witness')
    command.add_argument('--audio', type=Path, help='WAV in the Gilbreth project')
    command.add_argument('--audio-manifest', type=Path, help='Optional exact recording manifest JSONL')
    alignment = command.add_mutually_exclusive_group()
    alignment.add_argument('--alignment', type=Path, help='Exact-waveform, exact-edition alignment JSONL')
    alignment.add_argument('--decode', action='store_true', help='Decode this waveform in an allocated Slurm GPU job')
    command.add_argument('--speaker', help='Speaker code for an unmanifested take')
    command.add_argument('--style', help='Reading style for an unmanifested take')
    command.add_argument('--variety', help='Spoken variety code for an unmanifested take, currently cmn')
    command.add_argument('--rights', help='Permission or reuse-rights record for an unmanifested take')
    command.add_argument('--format', choices=('markdown', 'json', 'html'))
    command.add_argument('-o', '--output', type=Path, help='Write the report to this path')
    args = parser.parse_args(argv)
    if args.audio is None and any((args.audio_manifest, args.alignment, args.decode, args.speaker,
                                   args.style, args.variety, args.rights)):
        parser.error('Recording options require --audio')
    if args.output is not None and args.output.resolve() in {
        path.resolve() for path in (args.file, args.audio) if path is not None
    }:
        parser.error('Choose an output distinct from the input text and recording')
    suffix = args.output.suffix.lower() if args.output else ''
    output_format = args.format or {'.json': 'json', '.html': 'html'}.get(suffix, 'markdown')
    try:
        report = score(args, output_format)
        if output_format == 'json':
            content = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
        else:
            from src.stage7_render import render_html, render_markdown

            content = (render_html(report, args.audio) if output_format == 'html'
                       else render_markdown(report))
        if args.output is not None:
            write_output(args.output, content)
        else:
            print(content, end='')
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
