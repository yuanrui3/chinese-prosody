"""Recognize PCM flanks independently of the transcripts used for pause assignment."""

import argparse
from array import array
from collections import Counter, defaultdict
from hashlib import sha256
from importlib.metadata import version
import json
from math import gcd
import os
from pathlib import Path
import sys
import unicodedata
from zipfile import ZipFile

from data.phonology.annotate import han, sha256 as file_sha256
from data.phonology.modern import ARCHIVE, MEMBERS, VERSION, reading_rows
from src.quantitative_join_control import EXPERIMENT as JOIN_EXPERIMENT, TRANSFER, compose_pcm
from src.quantitative_report import FILES, index
from src.quantitative_waveform_reference import WAVEFORM_REFERENCE_SETTINGS, waveform_reference
from src.stage6_listening import digest, read_clip, read_json, read_rows, write_json
from src.stage7_cli import write_output


MODELS = {
    'base': {'id': 'openai/whisper-base',
             'revision': 'e37978b90ca9030d5170a5c07aadb050351a65bb',
             'weights_sha256': '07cadb9f25677c8d50df603e66a98fbd842cce45047139baeb16e6219a1e807b'},
    'small': {'id': 'openai/whisper-small',
              'revision': '973afd24965f72e36ca33b3055d56a652f456b4d',
              'weights_sha256': '1d7734884874f1a1513ed9aa760a4f8e97aaa02fd6d93a3a85d27b2ae9ca596b'},
}
MODEL_FILES = ('model.safetensors', 'config.json', 'generation_config.json', 'preprocessor_config.json',
               'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'added_tokens.json',
               'merges.txt', 'vocab.json', 'normalizer.json')
ORIGINAL = Path('model-development/quantitative-report')
RESULTS = Path('results/quantitative-report')
NATIVE = RESULTS / 'native-pause-boundaries.json'
PRIMARY = RESULTS / 'report-v4.json'
JOIN_REPORT = JOIN_EXPERIMENT / 'results/join-control/report.json'
FLANK = 3
MAX_SECONDS = 30
DECODE = {'language': 'zh', 'task': 'transcribe', 'do_sample': False, 'num_beams': 1,
          'return_timestamps': False, 'max_new_tokens': 192}


def conservative_variants(path):
    """Only collapse reversible one-to-one Traditional/Simplified variant pairs."""
    relations = defaultdict(dict)
    with ZipFile(path) as archive:
        for char, field, content in reading_rows(archive, MEMBERS[2], {'kTraditionalVariant', 'kSimplifiedVariant'}):
            relations[field][char] = {chr(int(token[2:], 16)) for token in content.split()}
    substitutions = {}
    for simple, traditional in relations['kTraditionalVariant'].items():
        if len(traditional) == 1:
            target = next(iter(traditional))
            if simple != target and relations['kSimplifiedVariant'].get(target) == {simple}:
                substitutions[simple] = target
    # A character may itself be both a source and a target. Retain disjoint pairs only.
    targets = set(substitutions.values())
    return {source: target for source, target in substitutions.items()
            if target not in substitutions and source not in targets}


def unpunctuated(text):
    """Skip punctuation and whitespace but preserve non-Han material as a barrier."""
    return ''.join(char for char in unicodedata.normalize('NFC', text)
                   if not char.isspace() and not unicodedata.category(char).startswith('P'))


def matching_positions(expected, left, right):
    return [gap for gap in range(FLANK, len(expected) - FLANK + 1)
            if expected[gap - FLANK:gap] == left and expected[gap:gap + FLANK] == right]


def lexical_match(expected, left_raw, right_raw, variants):
    left, right = unpunctuated(left_raw)[-FLANK:], unpunctuated(right_raw)[:FLANK]
    result = {'left_tail': left, 'right_head': right, 'exact_candidates': [], 'variant_candidates': [],
              'right_slot': None}
    if len(left) != FLANK or len(right) != FLANK or not all(map(han, left + right)):
        return {**result, 'status': 'missing_han_flank'}
    exact = matching_positions(expected, left, right)
    translator = str.maketrans(variants)
    normalized = matching_positions(*(text.translate(translator) for text in (expected, left, right)))
    candidates = sorted(set(exact) | set(normalized))
    result.update(exact_candidates=exact, variant_candidates=normalized)
    if len(candidates) != 1:
        return {**result, 'status': 'ambiguous_gap' if candidates else 'no_gap_match'}
    return {**result, 'status': 'unique_exact' if exact else 'unique_variant', 'right_slot': candidates[0]}


def pcm_digest(samples):
    if sys.byteorder != 'little':
        samples = array('h', samples)
        samples.byteswap()
    return sha256(samples.tobytes()).hexdigest()


class WhisperRecognizer:
    def __init__(self, cache, variant='base'):
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoProcessor, WhisperForConditionalGeneration

        if not torch.cuda.is_available():
            raise RuntimeError('Run the lexical audit in a Slurm GPU allocation')
        pin = MODELS[variant]
        snapshot = cache
        if not (snapshot / 'model.safetensors').is_file():
            snapshot = Path(snapshot_download(pin['id'], revision=pin['revision'], cache_dir=cache,
                                              local_files_only=True, allow_patterns=MODEL_FILES))
        self.hashes = {name: file_sha256(snapshot / name) for name in MODEL_FILES if (snapshot / name).is_file()}
        if self.hashes.get('model.safetensors') != pin['weights_sha256']:
            raise ValueError(f"{pin['id']} checkpoint differs from the pinned publisher digest")
        self.processor = AutoProcessor.from_pretrained(snapshot, local_files_only=True)
        self.model = WhisperForConditionalGeneration.from_pretrained(
            snapshot, local_files_only=True, use_safetensors=True).to('cuda').eval()
        self.torch = torch

    def __call__(self, samples, rate):
        import numpy as np
        from scipy.signal import resample_poly

        if not 0 < len(samples) <= rate * MAX_SECONDS:
            raise ValueError('Expected one nonempty waveform of at most 30 seconds')
        common = gcd(rate, 16000)
        waveform = np.asarray(samples, dtype=np.float32) / 32768
        if rate != 16000:
            waveform = resample_poly(waveform, 16000 // common, rate // common)
        encoded = self.processor(waveform, sampling_rate=16000, return_tensors='pt',
                                 return_attention_mask=True, truncation=False)
        with self.torch.inference_mode():
            tokens = self.model.generate(**encoded.to('cuda'), **DECODE)
        return self.processor.batch_decode(tokens, skip_special_tokens=True)[0]


def recognized_view(recognize, pcm, rate, start, end):
    segment = pcm[start:end]
    return {'sample_range': [start, end], 'pcm16le_sha256': pcm_digest(segment),
            'raw_transcript': recognize(segment, rate)}


def audit_pause(recognize, passage, pcm, rate, pause, prior, variants):
    start, end = pause['start_sample'], pause['end_sample']
    if not 0 < start < end < len(pcm):
        raise ValueError('Expected an internal quiet interval')
    midpoint = (start + end) // 2
    left = recognized_view(recognize, pcm, rate, 0, midpoint)
    right = recognized_view(recognize, pcm, rate, midpoint, len(pcm))
    slots = passage['slots']
    expected = ''.join(slot['char'] for slot in slots)
    result = lexical_match(expected, left['raw_transcript'], right['raw_transcript'], variants)
    gap = result['right_slot']
    is_clause = None if gap is None else slots[gap]['clause_index'] != slots[gap - 1]['clause_index']
    draft = prior['funasr']['right_slot'] if 'funasr' in prior else prior['assignment']['right_slot']
    phone = prior.get('charsiu', {}).get('right_slot')
    return {'quiet_interval': pause, 'split_sample': midpoint, 'left': left, 'right': right,
            'asr': {**result, 'is_written_clause_break': is_clause,
                    'matched_text_flanks': None if gap is None else [expected[gap-FLANK:gap], expected[gap:gap+FLANK]]},
            'prior_funasr_right_slot': draft, 'prior_charsiu_right_slot': phone,
            'comparison_with_funasr': ('unresolved' if gap is None or draft is None else
                                       'agrees' if gap == draft else 'differs')}


def verify_cohort(root, report, original, manifest):
    if original:
        expected = {'passages': digest(root / FILES['passages']), 'takes': digest(manifest),
                    'v4': digest(root / PRIMARY)}
        rows = report['recordings']
    else:
        expected = {'annotations': digest(root / FILES['passages']), 'manifest': digest(manifest)}
        rows = report['native_transfer']['rows']
    if any(report['source_sha256'][name] != checksum for name, checksum in expected.items()):
        raise ValueError('Native pause report has different pinned inputs')
    return index(rows, lambda row: row['recording_id'])


def audit_cohort(recognize, root, report_path, original, variants):
    manifest = root / FILES['takes']
    annotations = root / FILES['passages']
    sources = {'manifest': manifest, 'annotations': annotations, 'pause_report': report_path}
    if original:
        sources['primary_report'] = root / PRIMARY
    inputs = {key: digest(path) for key, path in sources.items()}
    passages = index(read_rows(annotations), lambda row: row['passage_id'])
    members = index(read_rows(manifest), lambda row: row['recording_id'])
    report = read_json(report_path)
    prior = verify_cohort(root, report, original, manifest)
    if members.keys() != prior.keys():
        raise ValueError('Expected the original recordings from the pinned pause report')
    takes = []
    for rid, take in members.items():
        prior_take = prior[rid]
        passage = passages[take['passage_id']]
        if (prior_take['audio_sha256'] != take['audio_sha256'] or prior_take['passage_id'] != take['passage_id']
                or prior_take['voice'] != take['speaker'] or take['text_sha256'] != passage['text_sha256']):
            raise ValueError(f'{rid}: waveform or witness differs from the pause report')
        rate, pcm = read_clip(root, take, take['sample_rate'])
        measured = waveform_reference(pcm, rate)['pauses']
        previous = prior_take['checked_pauses' if original else 'observations']
        if (len(measured) != len(previous)
                or any(any(saved[key] != value for key, value in now.items()) for now, saved in zip(measured, previous))):
            raise ValueError(f'{rid}: remeasured stable quiet intervals differ from the report')
        full = recognized_view(recognize, pcm, rate, 0, len(pcm)) if measured else None
        intervals = [audit_pause(recognize, passage, pcm, rate, pause, draft, variants)
                     for pause, draft in zip(measured, previous)]
        takes.append({'recording_id': rid, 'passage_id': take['passage_id'], 'voice': take['speaker'],
                      'audio_sha256': take['audio_sha256'], 'full': full, 'intervals': intervals})
    intervals = sum(len(row['intervals']) for row in takes)
    if original and intervals != 13:
        raise ValueError('Expected exactly 13 stable native quiet intervals in the original recordings')
    if inputs != {key: digest(path) for key, path in sources.items()}:
        raise ValueError('A pinned audit input changed during inference')
    summary = defaultdict(Counter)
    for row in takes:
        counts = summary[row['voice']]
        counts['takes'] += 1
        for pause in row['intervals']:
            counts['intervals'] += 1
            counts[f"asr_{pause['asr']['status']}"] += 1
            counts[f"comparison_{pause['comparison_with_funasr']}"] += 1
    return {'source_sha256': inputs, 'recordings': takes, 'by_voice': dict(summary)}


def audit_controls(recognize, project, audited_holdout, variants):
    corpus = project / TRANSFER
    manifest = corpus / FILES['takes']
    annotations = corpus / FILES['passages']
    sources = {'manifest': manifest, 'annotations': annotations, 'joins': project / JOIN_REPORT}
    hashes = {name: digest(path) for name, path in sources.items()}
    audited = index(audited_holdout['recordings'], lambda row: row['recording_id'])
    members = index(read_rows(manifest), lambda row: row['recording_id'])
    passages = index(read_rows(annotations), lambda row: row['passage_id'])
    archived = read_json(sources['joins'])
    if (any(archived['source_sha256'][name] != hashes[name] for name in ('manifest', 'annotations'))
            or archived['composites'] != 32 or len(archived['rows']) != 32):
        raise ValueError('Expected the pinned sample-known 32-join inventory')
    donors = {}
    for rid, take in members.items():
        rate, pcm = read_clip(corpus, take, take['sample_rate'])
        chars = ''.join(slot['char'] for slot in passages[take['passage_id']]['slots'])
        heard = audited[rid]['full']
        if heard is None:
            heard = recognized_view(recognize, pcm, rate, 0, len(pcm))
        elif heard['pcm16le_sha256'] != pcm_digest(pcm):
            raise ValueError(f'{rid}: cached donor transcript does not describe this PCM')
        donors[rid] = (rate, pcm, chars, heard)

    trials = []
    totals = defaultdict(Counter)
    for trial in archived['rows']:
        left_id, right_id = (trial[f'{side}_recording_id'] for side in ('left', 'right'))
        left, right = donors[left_id], donors[right_id]
        _, resume, checksum = compose_pcm(left[1], right[1], left[0])
        expected = len(left[2])
        if (left[0] != right[0] or trial['voice'] != members[left_id]['speaker']
                or trial['voice'] != members[right_id]['speaker']
                or trial['left_sample_count'] != len(left[1]) or trial['right_sample_count'] != len(right[1])
                or trial['right_start_sample'] != resume or trial['right_slot_index'] != expected
                or trial['composite_pcm16le_sha256'] != checksum):
            raise ValueError('Remeasured control differs from its pinned samples or lexical boundary')
        checked = lexical_match(left[2] + right[2], left[3]['raw_transcript'], right[3]['raw_transcript'], variants)
        found = checked['right_slot']
        outcome = 'unresolved' if found is None else 'correct' if found == expected else 'wrong'
        trials.append({'voice': trial['voice'], 'work_id': trial['work_id'], 'left_recording_id': left_id,
                       'right_recording_id': right_id, 'right_start_sample': resume,
                       'expected_right_slot': expected, 'composite_pcm16le_sha256': checksum,
                       'outcome': outcome, 'asr': checked})
        totals[trial['voice']]['trials'] += 1
        totals[trial['voice']][outcome] += 1
    if hashes != {name: digest(path) for name, path in sources.items()}:
        raise ValueError('A pinned control input changed during inference')
    return {'source_sha256': hashes, 'by_voice': dict(totals), 'trials': trials,
            'donor_transcripts': {rid: donor[3] for rid, donor in donors.items()}}


def analyze(project, cache, heldout=None, variant='base'):
    unihan = project / 'data/raw/phonology' / ARCHIVE
    if not unihan.is_file():
        raise ValueError(f'Expected the already pinned Unihan lexicon at {unihan}')
    variants = conservative_variants(unihan)
    recognizer = WhisperRecognizer(cache, variant)
    cohorts = {'original': audit_cohort(recognizer, project / ORIGINAL, project / ORIGINAL / NATIVE,
                                        True, variants)}
    controls = None
    if heldout is not None:
        cohorts['heldout'] = audit_cohort(recognizer, project / TRANSFER, heldout, False, variants)
        controls = audit_controls(recognizer, project, cohorts['heldout'], variants)
    return {'model': {**MODELS[variant], 'variant': variant,
                     'transformers_version': version('transformers'), 'decode': DECODE,
                     'local_file_sha256': recognizer.hashes},
            'settings': {'flank_han': FLANK, 'waveform': WAVEFORM_REFERENCE_SETTINGS,
                         'orthographic_variant_rule': 'disjoint reciprocal one-to-one Unihan mappings',
                         'unihan_version': VERSION, 'unihan_sha256': digest(unihan),
                         'literal_and_variant_positions_checked_for_ambiguity': True},
            'cohorts': cohorts, 'controlled_joins': controls,
            '音律美': {'evidence': 'independent recognizer correspondence for timing diagnostics'},
            '顺口': {'evidence': 'requires_first_read', 'first_read_measures': None}}


def render(result):
    lines = ['# Independent transcript check for native quiet intervals', '',
             f"Model checkpoint: `{result['model']['id']}` at revision `{result['model']['revision']}`.", '',
             'Whisper transcribed the original take and both PCM flanks independently. The flanks split at the '
             'midpoint of each measured quiet interval. Recognition was given Mandarin as the language. '
             'A match requires three adjacent Han characters on each side and one position in the unpunctuated '
             'witness across exact spelling and conservative Unihan equivalence.', '',
             '| Cohort | Voice | Intervals | Exact gap matches | Variant gap matches | Agrees with FunASR | '
             'Different gap | Unresolved comparison |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    fields = ('intervals', 'asr_unique_exact', 'asr_unique_variant', 'comparison_agrees', 'comparison_differs',
              'comparison_unresolved')
    for group, cohort in result['cohorts'].items():
        for voice, counts in cohort['by_voice'].items():
            lines.append(f'| {group} | {voice} | ' + ' | '.join(str(counts.get(key, 0)) for key in fields) + ' |')
    if result['controlled_joins'] is not None:
        lines += ['', '## Known join references', '',
                  'The source waveform slices of 32 controlled joins were reconstructed and verified. '
                  'The same lexical rule compared independently transcribed, unpadded donors '
                  'with the exact reference text ordinal at each splice.', '',
                  '| Voice | Trials | Correct | Wrong | Unresolved |', '| --- | ---: | ---: | ---: | ---: |']
        for voice, counts in result['controlled_joins']['by_voice'].items():
            lines.append(f'| {voice} | ' + ' | '.join(str(counts.get(key, 0))
                                                      for key in ('trials', 'correct', 'wrong', 'unresolved')) + ' |')
    lines += ['', 'Agreement supplies additional model evidence. Native accuracy needs independent labels. '
              'The transcripts and disagreements remain in the private JSON report. These diagnostics concern 音律美 '
              'timing research. 顺口 requires independent first-read evidence.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--model-cache', type=Path, required=True)
    parser.add_argument('--variant', choices=MODELS, default='base')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--markdown', type=Path)
    parser.add_argument('--heldout-report', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    project, cache = [path.resolve(strict=True) for path in (args.project, args.model_cache)]
    output, markdown = args.output.resolve(), args.markdown.resolve() if args.markdown else None
    heldout = args.heldout_report.resolve(strict=True) if args.heldout_report else None
    destinations = [output] + ([markdown] if markdown else [])
    if (not cache.is_relative_to(project) or len(set(destinations)) != len(destinations)
            or (heldout and not heldout.is_relative_to(project))
            or output.suffix != '.json' or (markdown and markdown.suffix != '.md')
            or any(path.exists() or not path.is_relative_to(project) for path in destinations)):
        parser.error('Use the private Gilbreth cache and distinct, new result files under the project')
    result = analyze(project, cache, heldout, variant=args.variant)
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
    if markdown:
        write_output(markdown, render(result))
    write_json(output, result)
    summary = {group: rows['by_voice'] for group, rows in result['cohorts'].items()}
    if result['controlled_joins'] is not None:
        summary['controlled_joins'] = result['controlled_joins']['by_voice']
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
