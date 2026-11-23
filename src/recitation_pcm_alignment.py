"""Transfer draft syllable coordinates through exact same-carrier pause edits."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
from statistics import median

from src.pilot_validation import write_json
from src.recitation_phrasing import BOUNDARY_ALLOWANCE_MS
from src.recitation_phrasing_analysis import MANIFEST, ROLES, locate_templates, make_template, placement_matches
from src.stage6_listening import digest, read_clip, read_json


OUTPUT = MANIFEST.with_name('pcm-alignment.json')


def matching_prefix(left, right):
    return next((index for index, (a, b) in enumerate(zip(left, right)) if a != b), min(len(left), len(right)))


def locate_silence(carrier, variant, added):
    """Find the whole range of removal positions that restore the carrier."""
    if added == 0:
        return 'unchanged' if carrier == variant else None
    if added < 0 or len(variant) != len(carrier) + added:
        return None
    first = len(carrier) - matching_prefix(carrier[::-1], variant[::-1])
    last = matching_prefix(carrier, variant)
    # Adjacent possible removal windows swap two equal samples, so all
    # candidate windows have identical energy if the first is silent.
    if first > last or any(variant[first:first + added]):
        return None
    return [first, last]


def project_edge(edge, splices, *, start):
    # A gap inserted at a start lies before the first syllable sample. A gap
    # inserted at an end lies after the last sample of the half-open interval.
    inclusive = int(not start)
    minimum = edge + sum(amount for first, last, amount in splices if last <= edge - inclusive)
    maximum = edge + sum(amount for first, last, amount in splices if first <= edge - inclusive)
    return [minimum, maximum]


def transfer(carrier, variant, bounds, templates, rate):
    added = len(variant) - len(carrier)
    if added <= 0:
        return {'status': 'nonpositive_pause_budget'}
    lags = locate_templates(templates, variant, added)
    if lags is None:
        return {'status': 'nonunique_or_disordered_anchors'}
    first_anchor, last_anchor = templates[0][0], templates[-1][0] + len(templates[-1][1]) // 2
    if (lags[0] != 0 or lags[-1] != added or carrier[:first_anchor] != variant[:first_anchor]
            or carrier[last_anchor:] != variant[last_anchor + added:]):
        return {'status': 'change_outside_anchored_region'}

    gaps, splices = [], []
    allowance = round(rate * BOUNDARY_ALLOWANCE_MS / 1000)
    for i, ((left, chunk), (right, _)) in enumerate(zip(templates, templates[1:])):
        left += len(chunk) // 2
        start, end = left + lags[i], right + lags[i + 1]
        increase = lags[i + 1] - lags[i]
        positions = locate_silence(carrier[left:right], variant[start:end], increase)
        if positions is None:
            return {'status': 'interanchor_samples_do_not_reconstruct'}
        low, high = bounds[i][1], bounds[i + 1][0]
        gap = {'after_relative_slot': i + 1, 'source_draft_gap_samples': [low, high],
               'added_samples': increase, 'added_ms': 1000 * increase / rate}
        if positions != 'unchanged':
            earliest, latest = (left + index for index in positions)
            if latest < low - allowance or earliest > high + allowance:
                return {'status': 'pause_outside_source_boundary_allowance'}
            splices.append((earliest, latest, increase))
            gap.update(source_insertion_position_range_samples=[earliest, latest],
                       variant_pause_start_range_samples=[earliest + lags[i], latest + lags[i]],
                       overlaps_source_draft_gap=earliest <= high and latest >= low)
        gaps.append(gap)

    syllables = []
    for i, (start, end) in enumerate(bounds):
        offset, chunk = templates[i]
        anchor_start = offset + lags[i]
        # An exact core can be transferred even if a draft full-syllable edge
        # falls on the other side of the disambiguated insertion.
        syllables.append({'source_draft_interval_samples': [start, end],
                          'variant_exact_core_samples': [anchor_start, anchor_start + len(chunk) // 2],
                          'variant_draft_start_range_samples': project_edge(start, splices, start=True),
                          'variant_draft_end_range_samples': project_edge(end, splices, start=False),
                          'possible_pause_inside_source_draft_interval': any(
                              max(first, start + 1) <= min(last, end - 1) for first, last, _ in splices),
                          'core_displacement_samples': lags[i]})
    return {'status': 'aligned', 'sample_count': len(variant), 'full_carrier_pcm_reconstructed': True,
            'syllables': syllables, 'gaps': gaps}


def align_pair(root, pair):
    source = pair['source']
    baseline = pair['syllables']
    indices = pair['slot_indices']
    if len(indices) != 4 or len(set(indices)) != 4 or [row['slot_index'] for row in baseline] != indices:
        raise ValueError('Expected four source draft intervals for the pinned clause')
    recovery = pair.get('baseline_recovery')
    if recovery is not None and recovery['slot_index'] not in indices:
        raise ValueError('Contextual recovery lies outside the target clause')

    row = {key: pair[key] for key in ('pair_id', 'passage_id', 'clause_text', 'work_id')}
    row.update(source_draft_syllables=baseline, baseline_recovery=recovery,
               baseline_link_quality=pair.get('placement_method',
                                              'contextual_recovery' if recovery else 'exact_segment_draft'))
    carrier_member = pair['sham']
    variant_members = [pair['variants'][role] for role in ROLES]
    fixed = ('passage_id', 'text_sha256', 'text_revision', 'intended_pinyin', 'speaker', 'speed', 'sample_rate')
    if any(member[field] != source[field] for member in (carrier_member, *variant_members) for field in fixed):
        raise ValueError('Carrier or variant differs from the pinned text and speaker condition')
    rate, carrier = read_clip(root, carrier_member, source['sample_rate'])
    if len(carrier) != source['sample_count'] or len(carrier) != carrier_member['sample_count']:
        raise ValueError('Carrier changed the source duration')
    bounds = [(round(syllable['start_s'] * rate), round(syllable['end_s'] * rate)) for syllable in baseline]
    if (any(not 0 <= left < right <= len(carrier) for left, right in bounds)
            or any(left[1] > right[0] for left, right in zip(bounds, bounds[1:]))):
        raise ValueError('Source draft intervals overlap or exceed the waveform')
    templates = [make_template(carrier, start, end, rate) for start, end in bounds]
    if any(template is None for template in templates):
        return {**row, 'status': 'insufficient_source_anchors'}

    variants = {}
    for role, member in zip(ROLES, variant_members):
        _, waveform = read_clip(root, member, rate)
        if len(waveform) != member['sample_count']:
            raise ValueError('Variant duration differs from its manifest')
        variants[role] = transfer(carrier, waveform, bounds, templates, rate)
    row['variants'] = variants
    if any(item['status'] != 'aligned' for item in variants.values()):
        return {**row, 'status': 'variant_abstention'}
    first, second = (variants[role] for role in ROLES)
    if first['sample_count'] != second['sample_count']:
        return {**row, 'status': 'different_variant_durations'}
    for item in variants.values():
        for slot, syllable in zip(indices, item['syllables']):
            syllable['slot_index'] = slot
    concentrated, split = ([gap['added_samples'] for gap in variants[role]['gaps']] for role in ROLES)
    return {**row, 'status': 'aligned', 'sample_rate': rate,
            'supports_pause_distribution': placement_matches(concentrated, split),
            'split_minus_concentrated_ms': [1000 * (a - b) / rate for a, b in zip(split, concentrated)]}


def identity(pair):
    """Require the same pinned clause and the exact same three audio files."""
    return (pair['passage_id'], pair['clause_text'], tuple(pair['slot_indices']), pair['source']['text_sha256'],
            pair['sham']['audio_sha256'], *(pair['variants'][role]['audio_sha256'] for role in ROLES))


def compare_decoder(pairs, rows, decoder_path, decoder_manifest):
    decoder = read_json(decoder_path)
    if decoder['manifest_sha256'] != digest(decoder_manifest):
        raise ValueError('Decoder and reference stimuli manifest have different hashes')
    reference = {pair['pair_id']: pair for pair in read_json(decoder_manifest)['pairs']}
    by_id = {row['pair_id']: row for row in decoder['pairs']}
    if len(by_id) != len(decoder['pairs']) or reference.keys() != by_id.keys():
        raise ValueError('Decoder and reference stimuli have different pair inventories')
    compatible = {pair['pair_id'] for pair in pairs if pair['pair_id'] in reference
                  and identity(pair) == identity(reference[pair['pair_id']])}
    draft = {key for key in compatible if None not in by_id[key]['split_minus_concentrated_ms'][:2]}
    pcm = {row['pair_id'] for row in rows if row['pair_id'] in compatible and row['status'] == 'aligned'}
    return {'decoder_reference_pairs': len(reference), 'same_waveform_pairs': len(compatible),
            'decoder_complete_pairs': len(draft), 'pcm_complete_pairs': len(pcm),
            'complete_in_both': len(pcm & draft), 'additional_pcm_pairs': len(pcm - draft),
            'decoder_sha256': digest(decoder_path), 'reference_stimuli_sha256': digest(decoder_manifest)}


def analyze(root, decoder=None, decoder_manifest=None):
    manifest = root / MANIFEST
    pairs = read_json(manifest)['pairs']
    if not pairs or len({pair['pair_id'] for pair in pairs}) != len(pairs):
        raise ValueError('Expected a nonempty set of unique phrasing pairs')
    rows = [align_pair(root, pair) for pair in pairs]
    aligned = [row for row in rows if row['status'] == 'aligned']
    spans = [syllable for row in aligned for item in row['variants'].values() for syllable in item['syllables']]
    spread = [1000 * (gap['source_insertion_position_range_samples'][1]
                      - gap['source_insertion_position_range_samples'][0]) / row['sample_rate']
              for row in aligned for item in row['variants'].values() for gap in item['gaps'] if gap['added_samples']]
    summary = {'pairs': len(pairs), 'fully_aligned_pairs': len(aligned),
               'fully_aligned_by_baseline': dict(Counter(row['baseline_link_quality'] for row in aligned)),
               'statuses': dict(Counter(row['status'] for row in rows)), 'transferred_syllable_intervals': len(spans),
               'transferred_intervals_that_may_span_pause': sum(
                   slot['possible_pause_inside_source_draft_interval'] for slot in spans),
               'full_placement_matches': sum(row['supports_pause_distribution'] for row in aligned),
               'median_splice_position_range_ms': median(spread) if spread else None,
               'maximum_splice_position_range_ms': max(spread) if spread else None}
    if decoder is not None:
        summary['decoder_comparison'] = compare_decoder(pairs, rows, decoder, decoder_manifest or manifest)
    write_json(root / OUTPUT, {'stimuli_sha256': digest(manifest),
               'scope': 'Exact waveform coordinate transfer from carrier draft; no independent phone recognition.',
               'summary': summary, 'pairs': rows})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--decoder', type=Path)
    parser.add_argument('--decoder-manifest', type=Path)
    args = parser.parse_args()
    if args.decoder_manifest is not None and args.decoder is None:
        parser.error('--decoder-manifest requires --decoder')
    os.umask(0o077)
    summary = analyze(args.root.resolve(strict=True), args.decoder, args.decoder_manifest)
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
