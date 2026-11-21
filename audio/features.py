"""Compute timing and waveform features with explicit alignment coverage."""

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from statistics import mean, median, stdev
import tempfile


PITCH_STEP_S = 0.01
PITCH_FLOOR_HZ = 75.0
PITCH_CEILING_HZ = 600.0
PAUSE_THRESHOLDS_MS = (100, 150, 200)
QUIET_DB_RELATIVE = -25.0
SUCCESS = {'matched', 'reviewed'}
SPEECH = SUCCESS | {'insertion', 'repetition', 'substitution'}
HISTORICAL_TIERS = ('guangyun', 'pingshui')
BREATH_EVIDENCE = {'audible_inhalation', 'respiratory_signal'}


def read_jsonl(path):
    with path.open(encoding='utf-8') as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f'{path}:{line_number}: {error.msg}') from error


def write_jsonl(path, rows):
    with tempfile.TemporaryDirectory(dir=path.parent) as temporary:
        draft = Path(temporary) / path.name
        with draft.open('w', encoding='utf-8') as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        draft.replace(path)


def historical_categories(slot):
    result = {}
    for tier in HISTORICAL_TIERS:
        source = slot.get('readings', {}).get(tier, {})
        selected = source.get('selected')
        candidates = source.get('candidates', [])
        labels = {}
        for key in ('tone', 'pingze', 'rhyme'):
            possibilities = {candidate.get(key) for candidate in candidates}
            consensus = next(iter(possibilities)) if len(possibilities) == 1 else None
            labels[key] = selected.get(key) if selected else consensus
        result[tier] = {
            **labels,
            'status': source.get('status', 'missing'),
            'candidate_ids': [candidate['id'] for candidate in candidates],
        }
    return result


def interval(row, duration_s):
    start = row.get('start_s')
    end = row.get('end_s')
    if start is None and end is None:
        return None
    if (start is None or end is None or not math.isfinite(start) or not math.isfinite(end)
            or not 0 <= start < end <= duration_s + 1e-6 or start >= duration_s):
        raise ValueError(f"{row['recording_id']}: invalid interval [{start}, {end}] for {duration_s:.6f}s waveform")
    return start, min(end, duration_s)


def npvi(pairs):
    values = [100 * abs(left - right) / ((left + right) / 2) for left, right in pairs]
    return {'value': mean(values) if values else None, 'pairs': len(values)}


def rms_summary(samples):
    return math.sqrt(sum(value * value for value in samples) / len(samples)) if len(samples) else None


def relative_db(amplitude, reference):
    if amplitude is None or amplitude <= 0 or reference is None or reference <= 0:
        return None
    return 20 * math.log10(amplitude / reference)


class Waveform:
    def __init__(self, path):
        import parselmouth

        self.sound = sound = parselmouth.Sound(str(path)).convert_to_mono()
        self.duration_s = float(sound.duration)
        self.sample_centers = sound.xs()
        self.samples = sound.values[0]
        self.frame_centers = []
        self.frequencies = []
        self.octave_jump_count = 0
        if self.duration_s >= 3 / PITCH_FLOOR_HZ:
            pitch = sound.to_pitch_ac(
                time_step=PITCH_STEP_S, pitch_floor=PITCH_FLOOR_HZ, pitch_ceiling=PITCH_CEILING_HZ,
            )
            self.frame_centers = pitch.xs()
            self.frequencies = [float(value) if value > 0 else None for value in pitch.selected_array['frequency']]
            bad = set()
            for index, (left, right) in enumerate(zip(self.frequencies, self.frequencies[1:])):
                if left and right and abs(math.log2(right / left)) >= 0.8:
                    bad.update((index, index + 1))
                    self.octave_jump_count += 1
            for index in bad:
                self.frequencies[index] = None

    def samples_in(self, bounds):
        start, end = self.sample_centers.searchsorted(bounds)
        return self.samples[start:end]

    def pitch_in(self, bounds):
        start, end = (bisect_left(self.frame_centers, point) for point in bounds)
        return self.frequencies[start:end]


def pitch_features(frequencies, reference):
    reliable = [value for value in frequencies if value is not None]
    result = {
        'voiced_frames': len(reliable),
        'pitch_frames': len(frequencies),
        'f0_median_hz': median(reliable) if reliable else None,
        'f0_median_st': None,
        'f0_early_st': None,
        'f0_late_st': None,
        'f0_curvature_st_per_s2': None,
        'f0_curvature_triples': 0,
    }
    if not reliable or reference is None:
        return result
    semitones = [12 * math.log2(value / reference) if value else None for value in frequencies]
    smoothed = list(semitones)
    for index in range(1, len(semitones) - 1):
        window = semitones[index - 1:index + 2]
        if all(value is not None for value in window):
            smoothed[index] = median(window)
    curvature = [abs(right - 2 * center + left) / PITCH_STEP_S**2
                 for left, center, right in zip(smoothed, smoothed[1:], smoothed[2:])
                 if all(value is not None for value in (left, center, right))]
    edge_frames = max(1, math.ceil(len(frequencies) / 3))
    early = [value for value in semitones[:edge_frames] if value is not None]
    late = [value for value in semitones[-edge_frames:] if value is not None]
    return {
        **result,
        'f0_median_st': 12 * math.log2(result['f0_median_hz'] / reference),
        'f0_early_st': median(early) if early else None,
        'f0_late_st': median(late) if late else None,
        'f0_curvature_st_per_s2': mean(curvature) if curvature else None,
        'f0_curvature_triples': len(curvature),
    }


def summarize_intervals(waveform, labels, speech_bounds):
    """Use only explicit reviewed labels for breath and V/C metrics."""
    reviewed = []
    for row in labels:
        if row['label'] not in {'vowel', 'consonant', 'silence', 'breath', 'unclassified'}:
            raise ValueError(f"{row['recording_id']}: unknown interval label {row['label']!r}")
        bounds = interval(row, waveform.duration_s)
        if bounds is None:
            raise ValueError(f"{row['recording_id']}: annotation interval needs times")
        if row.get('reviewed') is True:
            reviewed.append((*bounds, row['label'], row.get('evidence')))
    reviewed.sort(key=lambda item: item[:2])
    runs = []
    previous_end = 0.0
    for start, end, label, _ in reviewed:
        if start < previous_end - 1e-6:
            raise ValueError('Reviewed intervals in the same recording overlap')
        previous_end = end
        if runs and label == runs[-1][2] and abs(start - runs[-1][1]) <= 1e-6:
            runs[-1] = runs[-1][0], end, label
        else:
            runs.append((start, end, label))
    vowels = [1000 * (end - start) for start, end, label in runs if label == 'vowel']
    consonants = [1000 * (end - start) for start, end, label in runs if label == 'consonant']
    classified_ms = sum(vowels) + sum(consonants)
    # Other classes, missing time, or interruption prevent adjacency of vowel runs.
    vowel_pairs = [(1000 * (end - start), 1000 * (next_end - next_start))
                   for (start, end, label), (cs, ce, cl), (next_start, next_end, nl)
                   in zip(runs, runs[1:], runs[2:])
                   if (label, cl, nl) == ('vowel', 'consonant', 'vowel')
                   and abs(end - cs) <= 1e-6 and abs(ce - next_start) <= 1e-6]
    breaths = [(start, end) for start, end, label, evidence in reviewed
               if label == 'breath' and evidence in BREATH_EVIDENCE]
    groups = []
    for (_, left_end), (right_start, _) in zip(breaths, breaths[1:]):
        internal = [(start, end) for start, end in speech_bounds if start < right_start and end > left_end]
        if all(start >= left_end and end <= right_start for start, end in internal):
            groups.append({'start_s': left_end, 'end_s': right_start, 'aligned_realizations': len(internal)})
    return {
        'percent_v': 100 * sum(vowels) / classified_ms if vowels and consonants else None,
        'delta_c_ms': stdev(consonants) if len(consonants) > 1 else None,
        'vowel_npvi': npvi(vowel_pairs),
        'classified_segment_ms': classified_ms,
        'vowel_runs': len(vowels),
        'consonant_runs': len(consonants),
        'documented_inhalations': len(breaths),
        'complete_breath_groups': groups,
        'segment_status': 'measured_reviewed_intervals' if classified_ms else 'no_reviewed_vowel_consonant_intervals',
        'breath_status': 'aligned_groups' if groups else 'no_complete_reviewed_breath_groups',
    }


def timing_by_clause(syllables, slots):
    expected = Counter(slot['clause_index'] for slot in slots)
    measured = defaultdict(list)
    for row in syllables:
        if row['duration_ms'] is not None:
            measured[row['clause_index']].append(row)
    clauses = []
    for index, slots_expected in sorted(expected.items()):
        observed = measured[index]
        complete = len(observed) == slots_expected
        articulation = sum(row['duration_ms'] for row in observed) if complete else None
        elapsed = 1000 * (observed[-1]['end_s'] - observed[0]['start_s']) if complete else None
        tracked = [row for row in observed if row['f0_curvature_triples']]
        tracked_triples = sum(row['f0_curvature_triples'] for row in tracked)
        curvature = sum(row['f0_curvature_st_per_s2'] * row['f0_curvature_triples'] for row in tracked)
        clauses.append({
            'clause_index': index, 'slots_expected': slots_expected, 'slots_measured': len(observed),
            'articulation_ms': articulation, 'elapsed_ms': elapsed,
            'within_syllable_f0_curvature_st_per_s2': curvature / tracked_triples if tracked_triples else None,
            'f0_curvature_triples': tracked_triples,
        })
    return clauses


def duration_by_tone(syllables):
    def describe(durations):
        return {'tokens': len(durations), 'geomean_ms': math.exp(mean(map(math.log, durations))) if durations else None}

    result = {}
    for tier in HISTORICAL_TIERS:
        grouped = {'平': [], '仄': []}
        tone_classes = {tone: [] for tone in ('平', '上', '去', '入')}
        for row in syllables:
            if row['duration_ms'] is not None:
                categories = row['historical'][tier]
                if categories['pingze'] in grouped:
                    grouped[categories['pingze']].append(row['duration_ms'])
                if categories['tone'] in tone_classes:
                    tone_classes[categories['tone']].append(row['duration_ms'])
        summary = {tone: describe(durations) for tone, durations in grouped.items()}
        ratio = (summary['平']['geomean_ms'] / summary['仄']['geomean_ms']
                 if all(grouped.values()) else None)
        result[tier] = {'groups': summary, 'tone_classes': {tone: describe(durations) for tone, durations in tone_classes.items()},
                        'geomean_ping_ze_ratio': ratio}
    return result


def extract_recording(events, passage, waveform, labels):
    slots = {row['slot_index']: row for row in passage['slots']}
    pair_ends = {side[-1] for group in passage.get('parallel_clause_groups', []) for side in group}
    last_slots_by_clause = {slot['clause_index']: index for index, slot in slots.items()}
    pair_end_slots = {last_slots_by_clause[clause] for clause in pair_ends}
    counts = Counter(row['slot_index'] for row in events if row['status'] in SUCCESS)
    observations = []
    previous_end = 0.0
    for event in events:
        bounds = interval(event, waveform.duration_s)
        if event['status'] == 'omission' and bounds is not None:
            raise ValueError(f"{event['recording_id']}: an omitted syllable cannot have an audio interval")
        if bounds is not None:
            if bounds[0] < previous_end - 1e-6:
                raise ValueError(f"{event['recording_id']}: audio intervals overlap or are out of order")
            previous_end = bounds[1]
        index = event['slot_index']
        if index is not None and index not in slots:
            raise ValueError(f"{event['recording_id']}: unknown slot {index}")
        eligible = bounds is not None and index is not None and counts[index] == 1 and event['status'] in SUCCESS
        observations.append((event, bounds, eligible))
    speech_bounds = [bounds for event, bounds, _ in observations if bounds and event['status'] in SPEECH]
    usable = [bounds for _, bounds, eligible in observations if eligible]
    f0_samples = [value for bounds in usable for value in waveform.pitch_in(bounds) if value is not None]
    f0_reference = median(f0_samples) if f0_samples else None
    reference_rms = None
    if usable:
        speech_samples = waveform.samples_in((usable[0][0], usable[-1][1]))
        reference_rms = rms_summary(speech_samples)
    syllables = []
    for event, bounds, eligible in observations:
        slot = slots.get(event['slot_index'])
        acoustics = pitch_features(waveform.pitch_in(bounds) if eligible else [], f0_reference)
        syllables.append({
            **event,
            'char': slot['char'] if slot else None,
            'clause_index': slot['clause_index'] if slot else None,
            'boundary_after': slot['boundary_after'] if slot else None,
            'marks_after': slot['marks_after'] if slot else None,
            'pair_side_end': event['slot_index'] in pair_end_slots,
            'historical': historical_categories(slot) if slot else None,
            'duration_ms': 1000 * (bounds[1] - bounds[0]) if eligible else None,
            'rms_db_relative_to_span': relative_db(rms_summary(waveform.samples_in(bounds)), reference_rms)
            if eligible else None,
            **acoustics,
        })
    gaps = []
    syllable_pairs = []
    for left, right in zip(syllables, syllables[1:]):
        if (left['duration_ms'] is None or right['duration_ms'] is None
                or left['slot_index'] + 1 != right['slot_index']):
            continue
        start, end = left['end_s'], right['start_s']
        gap_ms = 1000 * max(0.0, end - start)
        rms = rms_summary(waveform.samples_in((start, end))) if end > start else None
        gap_db = relative_db(rms, reference_rms)
        quiet = (rms == 0 and bool(reference_rms)) or (gap_db is not None and gap_db <= QUIET_DB_RELATIVE)
        silence_reviewed = any(row['label'] == 'silence' and row.get('reviewed') is True
                               and row['start_s'] <= start and row['end_s'] >= end for row in labels) if gap_ms else False
        pitch_reset = None
        if left['f0_late_st'] is not None and right['f0_early_st'] is not None:
            pitch_reset = right['f0_early_st'] - left['f0_late_st']
        gaps.append({
            'recording_id': left['recording_id'], 'passage_id': left['passage_id'],
            'after_slot_index': left['slot_index'], 'start_s': start, 'end_s': max(start, end),
            'gap_ms': gap_ms, 'rms_db_relative_to_span': gap_db,
            'quiet_candidate_ms_thresholds': [threshold for threshold in PAUSE_THRESHOLDS_MS
                                              if quiet and gap_ms >= threshold - 1e-6],
            'reviewed_silence': silence_reviewed,
            'boundary_after': left['boundary_after'], 'pair_side_end': left['pair_side_end'],
            'adjacent_pitch_reset_st': pitch_reset,
        })
        if left['clause_index'] == right['clause_index'] and gap_ms < PAUSE_THRESHOLDS_MS[1] - 1e-6:
            syllable_pairs.append((left['duration_ms'], right['duration_ms']))
    clauses = timing_by_clause(syllables, slots.values())
    clause_times = [row['articulation_ms'] for row in clauses]
    complete_clause_times = [value for value in clause_times if value is not None]
    first = events[0]
    provenance = {key: first[key] for key in ('kind', 'speaker_id', 'variety', 'style', 'timing_method') if key in first}
    summary = {
        **provenance,
        'recording_id': first['recording_id'], 'passage_id': first['passage_id'], 'audio_path': first['audio_path'],
        'waveform_duration_s': waveform.duration_s,
        'slots_expected': len(slots), 'slots_measured': len(usable),
        'events_by_status': dict(Counter(row['status'] for row in events)),
        'pronunciations_recorded': sum(row.get('realized_reading') is not None for row in syllables
                                       if row['duration_ms'] is not None),
        'f0_reference_hz': f0_reference,
        'potential_octave_jumps': waveform.octave_jump_count,
        'rms_reference_span': reference_rms,
        'clauses': clauses,
        'syllable_duration_npvi': npvi(syllable_pairs),
        'clause_articulation_npvi': npvi((left, right) for left, right in zip(clause_times, clause_times[1:])
                                        if left is not None and right is not None),
        'clause_articulation_sd_ms': stdev(complete_clause_times) if len(complete_clause_times) > 1 else None,
        'eligible_gaps': len(gaps),
        'quiet_gap_candidates': sum(PAUSE_THRESHOLDS_MS[1] in row['quiet_candidate_ms_thresholds'] for row in gaps),
        'punctuation_boundary_quiet_gap_candidates': sum(
            row['boundary_after'] > 0 and PAUSE_THRESHOLDS_MS[1] in row['quiet_candidate_ms_thresholds'] for row in gaps),
        'ping_ze_duration': duration_by_tone(syllables),
        **summarize_intervals(waveform, labels, speech_bounds),
    }
    return syllables, gaps, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Project root for root-relative audio paths')
    parser.add_argument('--alignments', type=Path, required=True)
    parser.add_argument('--passages', type=Path, required=True, help='Stage 3 annotated JSONL')
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--intervals', type=Path, help='Optional reviewed acoustic interval JSONL')
    args = parser.parse_args()
    passages = {row['passage_id']: row for row in read_jsonl(args.passages)}
    by_recording = defaultdict(list)
    for row in read_jsonl(args.alignments):
        by_recording[row['recording_id']].append(row)
    if not by_recording:
        parser.error('alignment input has no recording rows')
    labels = defaultdict(list)
    if args.intervals:
        for row in read_jsonl(args.intervals):
            if row['recording_id'] not in by_recording:
                parser.error(f"unexpected recording_id in interval labels: {row['recording_id']}")
            labels[row['recording_id']].append(row)
    all_syllables = []
    all_gaps = []
    summaries = []
    for recording_id, events in by_recording.items():
        first = events[0]
        passage_id = first['passage_id']
        path = args.root / first['audio_path']
        if any(row['passage_id'] != passage_id or args.root / row['audio_path'] != path for row in events):
            raise ValueError(f'{recording_id}: one recording must refer to one source passage and one waveform')
        rows, gaps, summary = extract_recording(events, passages[passage_id], Waveform(path), labels[recording_id])
        all_syllables.extend(rows)
        all_gaps.extend(gaps)
        summaries.append(summary)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / 'syllables.jsonl', all_syllables)
    write_jsonl(args.out_dir / 'gaps.jsonl', all_gaps)
    write_jsonl(args.out_dir / 'recordings.jsonl', summaries)
    print(f'{len(summaries)} recordings, {len(all_syllables)} alignment rows, {len(all_gaps)} eligible gaps')


if __name__ == '__main__':
    main()
