"""Re-decode original PCM context windows to check unresolved phrasing boundaries."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory

from audio.align import MODEL_REVISION, MandarinDecoder, lexical_key
from src.pilot_validation import write_json
from src.recitation_phrasing_analysis import locate_templates, make_template
from src.recitation_phrasing_decode import RESULTS, ROLES
from src.rhyme_final_recovery import MIN_FINAL_CONFIDENCE, observation_key
from src.rhyme_window_redecode import decode_view
from src.stage6_listening import digest, read_clip, read_json


STIMULI = RESULTS / 'stimuli.json'
PRIOR = RESULTS / 'decoder.json'
OUTPUT = RESULTS / 'context-decoder.json'
# The extra sub-frame pads change the decoder's frame lattice as well as context.
VIEWS = (('left_context', 0.70, 0.23, 0.113, 0.097),
         ('right_context', 0.23, 0.70, 0.187, 0.123))
MAX_EDGE_DISAGREEMENT_S = 0.03


def identities(pair):
    keys = ('audio_sha256', 'sample_rate', 'sample_count')
    takes = [pair['sham'], *(pair['variants'][role] for role in ROLES[1:])]
    return ([pair[field] for field in ('passage_id', 'clause_text', 'slot_indices')],
            [tuple(take[key] for key in keys) for take in takes])


def unique_rows(rows):
    indexed = {row['pair_id']: row for row in rows}
    if not indexed or len(indexed) != len(rows):
        raise ValueError('Expected a nonempty set of unique phrasing pairs')
    return indexed


def register(decoded, templates, lags, expected, rate):
    """Use independently heard labels and a PCM anchor to address each written slot."""
    registrations = []
    for (start, chunk), lag, key in zip(templates, lags, expected):
        left = (start + lag) / rate
        duration = len(chunk) / (2 * rate)
        right = left + duration
        candidates = [
            (index, row) for index, row in enumerate(decoded)
            if min(right, row['end_s']) - max(left, row['start_s']) >= duration / 2 - 1e-7
        ]
        if len(candidates) != 1:
            reason = 'ambiguous_anchor' if candidates else 'no_decoded_syllable_at_anchor'
            registrations.append({'status': reason, 'candidates': [row for _, row in candidates]})
        else:
            index, row = candidates[0]
            status = ('no_matching_segment' if observation_key(row) != key else
                      'low_final_confidence' if row['final_confidence'] < MIN_FINAL_CONFIDENCE else 'anchored')
            registrations.append({'status': status, 'decoded_index': index, 'observation': row})
    return registrations


def draft_gaps(registrations):
    gaps = []
    for left, right in zip(registrations, registrations[1:]):
        if left['status'] != 'anchored' or right['status'] != 'anchored':
            gaps.append({'status': 'missing_flank'})
            continue
        if right['decoded_index'] != left['decoded_index'] + 1:
            gaps.append({'status': 'nonconsecutive_flanks'})
            continue
        end = left['observation']['end_s']
        start = right['observation']['start_s']
        gaps.append({'status': 'measured', 'left_end_s': end, 'right_start_s': start,
                     'gap_ms': round(1000 * (start - end), 6)})
    return gaps


def consensus(attempts):
    if len(attempts) != len(VIEWS) or any(row['status'] != 'measured' for row in attempts):
        return None, 'insufficient_consistent_views'
    first, second = attempts
    if any(abs(first[k] - second[k]) > MAX_EDGE_DISAGREEMENT_S + 1e-7
           for k in ('left_end_s', 'right_start_s')):
        return None, 'conflicting_edges'
    # Keep the first actual observation. Do not select a gap by its direction.
    return first['gap_ms'], 'two_view_agreement'


def decode_contexts(decoder, folder, pcm, rate, bounds, templates, lags, expected):
    attempts = []
    for name, before, after, prefix, suffix in VIEWS:
        left = max(0, bounds[0][0] + lags[0] - round(rate * before))
        right = min(len(pcm), bounds[-1][1] + lags[-1] + round(rate * after))
        decoded = decode_view(decoder, folder, pcm, rate, left, right, prefix, suffix)
        registrations = register(decoded, templates, lags, expected, rate)
        attempts.append({'view': name, 'source_sample_range': [left, right],
                         'registrations': registrations, 'boundaries': draft_gaps(registrations)})
    return attempts


def recheck(decoder, folder, waveforms, rate, pair, gaps):
    bounds = [(round(row['start_s'] * rate), round(row['end_s'] * rate)) for row in pair['syllables']]
    indices = pair['slot_indices']
    if (len(bounds) != 4 or len(indices) != 4
            or [row['slot_index'] for row in pair['syllables']] != indices
            or any(not 0 <= left < right <= len(waveforms[0]) for left, right in bounds)
            or any(a[1] > b[0] for a, b in zip(bounds, bounds[1:]))):
        raise ValueError('Invalid four-syllable baseline intervals')
    expected = [lexical_key(pair['source']['intended_pinyin'][index])[0] for index in indices]
    templates = [make_template(waveforms[0], left, right, rate) for left, right in bounds]
    if any(template is None for template in templates):
        return {}, 'insufficient_source_templates', gaps
    roles = {}
    for role, pcm in zip(ROLES, waveforms):
        lags = locate_templates(templates, pcm, len(pcm) - len(waveforms[0]))
        if lags is None:
            roles[role] = {'status': 'nonunique_pcm_anchors', 'views': []}
            continue
        contexts = decode_contexts(decoder, folder, pcm, rate, bounds, templates, lags, expected)
        measures = [consensus([view['boundaries'][index] for view in contexts]) for index in range(3)]
        roles[role] = {'status': 'redecoded', 'views': contexts,
                       'consensus': [{'gap_ms': value, 'status': status} for value, status in measures]}
    supported = []
    for index, prior in enumerate(gaps):
        if prior is not None:
            supported.append(prior)
        elif all(result.get('consensus', [{}] * 3)[index].get('gap_ms') is not None
                 for result in roles.values()):
            supported.append({role: row['consensus'][index]['gap_ms'] for role, row in roles.items()})
        else:
            supported.append(None)
    return roles, 'redecoded', supported


def analyze(project, root, prior):
    if not root.is_relative_to(project) or not prior.is_relative_to(project):
        raise ValueError('Both recitation experiments must be on the project filesystem')
    manifest = root / STIMULI
    pairs = unique_rows(read_json(manifest)['pairs'])
    earlier = read_json(prior / PRIOR)
    if earlier['model_revision'] != MODEL_REVISION or earlier['manifest_sha256'] != digest(prior / STIMULI):
        raise ValueError('The earlier phone report does not match its manifest and decoder')
    earlier_pairs = unique_rows(read_json(prior / STIMULI)['pairs'])
    earlier_rows = unique_rows(earlier['pairs'])
    if earlier_rows.keys() != earlier_pairs.keys() or earlier_pairs.keys() - pairs.keys():
        raise ValueError('The earlier pairs must be represented in both experiments')

    decoder = None
    rows = []
    with TemporaryDirectory(dir=root, prefix='phrasing-context-') as temporary:
        folder = Path(temporary)
        for pair_id, pair in pairs.items():
            shared = pair_id in earlier_pairs
            rate = pair['sham']['sample_rate']
            takes = [pair['sham'], *(pair['variants'][role] for role in ROLES[1:])]
            waveforms = [read_clip(root, take, rate)[1] for take in takes]
            if (len(waveforms[1]) != len(waveforms[2]) or min(map(len, waveforms[1:])) <= len(waveforms[0])
                    or [len(pcm) for pcm in waveforms] != [take['sample_count'] for take in takes]):
                raise ValueError(f'{pair_id}: pair durations differ from the intended comparison')
            if shared and identities(pair) != identities(earlier_pairs[pair_id]):
                raise ValueError(f'{pair_id}: earlier pair differs from its current WAVs or text')
            before = earlier_rows[pair_id]['gaps_ms'] if shared else [None] * 3
            if len(before) != 3:
                raise ValueError(f'{pair_id}: expected three internal boundary measures')
            attempts, status, after = {}, 'prior_two_boundaries_preserved', before
            if None in before[:2]:
                if decoder is None:
                    decoder = MandarinDecoder(project, offline=True)
                attempts, status, after = recheck(decoder, folder, waveforms, rate, pair, before)
            change = [None if gap is None else round(gap['one_one_two'] - gap['two_two'], 6)
                      for gap in after]
            rows.append({'pair_id': pair_id, 'clause_text': pair['clause_text'], 'in_prior': shared,
                         'status': status, 'context_views': attempts,
                         'prior_gaps_ms': before, 'gaps_ms': after, 'split_minus_concentrated_ms': change,
                         'boundary_methods': [('prior' if old is not None else
                                               'context_consensus' if new is not None else 'unresolved')
                                              for old, new in zip(before, after)]})

    shared = [row for row in rows if row['in_prior']]
    complete = [row for row in rows if None not in row['gaps_ms'][:2]]
    summary = {
        'pairs': len(rows), 'prior_pairs': len(shared),
        'prior_two_boundary_coverage': sum(None not in row['prior_gaps_ms'][:2] for row in shared),
        'current_coverage_on_prior_pairs': sum(row['in_prior'] for row in complete),
        'two_boundary_coverage': len(complete),
        'both_directions_recovered': sum(row['split_minus_concentrated_ms'][0] > 0
                                         and row['split_minus_concentrated_ms'][1] < 0 for row in complete),
        'boundary_methods': [dict(Counter(row['boundary_methods'][i] for row in rows)) for i in range(3)],
    }
    values = [[row['split_minus_concentrated_ms'][i] for row in rows
               if row['split_minus_concentrated_ms'][i] is not None] for i in range(3)]
    summary['median_gap_changes_ms'] = [median(group) if group else None for group in values]
    write_json(root / OUTPUT, {
        'model_revision': MODEL_REVISION, 'manifest_sha256': digest(manifest),
        'prior_report_sha256': digest(prior / PRIOR), 'frame_ms': earlier['frame_ms'],
        'max_consensus_edge_difference_ms': 1000 * MAX_EDGE_DISAGREEMENT_S,
        'context_views': VIEWS, 'summary': summary, 'pairs': rows,
    })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--prior', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(analyze(args.project.resolve(strict=True), args.root.resolve(strict=True),
                             args.prior.resolve(strict=True)), allow_nan=False))


if __name__ == '__main__':
    main()
