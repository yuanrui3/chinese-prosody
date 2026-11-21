"""Run the installed scoring entry point on the matched Gilbreth pilot."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from src.stage7_cli import write_output


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_jsonl(path):
    with path.open(encoding='utf-8') as source:
        return [json.loads(line) for line in source if line.strip()]


def run_pilot(root, output, reuse_drafts=False):
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'shunkou'), 'score']
    pilot = [row for row in read_jsonl(root / 'data/pilot/annotated.jsonl') if row['subset'] == 'matched']
    recordings = read_jsonl(root / 'audio/manifests/synthetic.jsonl')
    if len(pilot) != 12 or len({row['pair_id'] for row in pilot}) != 6:
        raise ValueError('Expected the 12 passages in the six matched Stage 3 pairs')
    audio_ids = {'ET01', 'ET02'}
    if {row['passage_id'] for row in pilot if row['pair_id'] == 'M04'} != audio_ids:
        raise ValueError('The edition-checked audio demonstration uses the M04 pair')

    output.mkdir(parents=True, exist_ok=True)
    results = []
    with TemporaryDirectory(dir=output) as directory:
        temporary = Path(directory)
        for row in pilot:
            identifier = row['passage_id']
            source = temporary / f'{identifier}.txt'
            source.write_text(row['text'], encoding='utf-8')
            options = [*command, str(source), '--root', str(root), '--passage-id', identifier]
            target = output / f'{identifier}.json'
            subprocess.run([*options, '-o', str(target)], check=True)
            result = read_json(target)
            if (result['audio'] is not None or result['text']['text_sha256'] != row['text_sha256']
                    or result['text']['reference']['annotation_source'] != 'pinned_pilot'):
                raise ValueError(f'{identifier} did not preserve the pinned witness')
            clauses = [clause for paragraph in result['text']['paragraphs'] for clause in paragraph['clauses']]
            if sum(len(clause['slots']) for clause in clauses) != len(row['slots']):
                raise ValueError(f'{identifier} lost slots in document segmentation')
            check = {'passage_id': identifier, 'pair_id': row['pair_id'], 'clauses': len(clauses),
                     'text_observations': len(result['text']['observations'])}
            results.append(check)
            if identifier not in audio_ids:
                continue
            selected = [take for take in recordings if take['passage_id'] == identifier
                        and take['speaker'] == 'zf_001' and take['speed'] == 1.0]
            if len(selected) != 1:
                raise ValueError(f'{identifier} lacks one exact Stage 4 waveform at the selected voice and speed')
            record = selected[0]
            audio_options = [*options, '--audio', str(root / record['audio_path'])]
            decoded = output / f'{identifier}-audio.json'
            decode = [] if reuse_drafts else ['--decode']
            subprocess.run([*audio_options, *decode, '-o', str(decoded)], check=True)
            audio = read_json(decoded)['audio']
            with_audio = output / f'{identifier}-audio.html'
            subprocess.run([*audio_options, '-o', str(with_audio)], check=True)
            copy = with_audio.read_text(encoding='utf-8')
            playable = sum(clause['draft_span_start_s'] is not None for clause in audio['clauses'])
            if (audio['recording']['audio_sha256'] != record['audio_sha256'] or not playable
                    or copy.count('<audio controls') != playable or 'data:audio/wav;base64,' not in copy):
                raise ValueError(f'{identifier} did not reproduce the exact waveform and timed clause players')
            check.update(recording_id=record['recording_id'], playable_clauses=playable,
                         slots_timed=sum(clause['slots_measured'] for clause in audio['clauses']),
                         slots_written=len(row['slots']), audio_observations=len(audio['observations']))
            print(json.dumps(check, ensure_ascii=False), flush=True)

        novel = temporary / 'plain.txt'
        novel.write_text('山高水長。天朗氣清。\n\n東風吹水，西日照林。', encoding='utf-8')
        novel_result = temporary / 'plain.json'
        subprocess.run([*command, str(novel), '--root', str(root), '-o', str(novel_result)], check=True)
        plain = read_json(novel_result)['text']
        if (len(plain['paragraphs']) != 2 or plain['reference']['witness'] is not None
                or not all(item['available'] for item in plain['reference']['historical'].values())):
            raise ValueError('The cached-lexicon plain-text path failed')
        subprocess.run([*command, str(novel), '--root', str(root), '-o', str(output / 'plain-example.md')], check=True)

    summary = {'matched_passages': len(results), 'matched_pairs': len({row['pair_id'] for row in results}),
               'waveform_reports': len(audio_ids), 'new_waveform_decodes': 0 if reuse_drafts else len(audio_ids),
               'plain_text_paragraphs': len(plain['paragraphs']), 'passages': results}
    write_output(output / 'pilot-summary.json', json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    source = 'cached' if reuse_drafts else 'newly decoded'
    print(f"Verified {len(results)} pinned texts and {len(audio_ids)} {source} waveforms with HTML playback.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--reuse-drafts', action='store_true', help='Rebuild reports from verified waveform caches')
    args = parser.parse_args()
    root, output = args.root.resolve(strict=True), args.output.resolve()
    if not output.is_relative_to(root / 'results/stage7'):
        parser.error('Output must stay under the Gilbreth project results/stage7')
    run_pilot(root, output, args.reuse_drafts)


if __name__ == '__main__':
    main()
