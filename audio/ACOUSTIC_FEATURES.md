# Stage 4 acoustic measurements

Run the extraction on Gilbreth with `praat-parselmouth==0.4.6` in the audio environment. Paths for inputs and outputs are relative to the project scratch directory in this example.

```bash
python audio/features.py \
  --root "$SHUNKOU_ROOT" \
  --passages "$SHUNKOU_ROOT/data/pilot/annotated.jsonl" \
  --alignments "$SHUNKOU_ROOT/audio/derived/alignment/alignments.jsonl" \
  --out-dir "$SHUNKOU_ROOT/audio/derived/features"
```

The input assigns one record to each alignment event. A recording uses one `recording_id`, `passage_id`, and `audio_path`. Each event has `status`, `slot_index`, `start_s`, and `end_s`. `slot_index` is zero-based and null for unmapped audio. Omission times are null. `realized_reading` records the pronunciation of that take when available. Its evidence fields and any `confidence` pass through unchanged. Order events as heard and preserve unmatched events between aligned tokens.

## Outputs

- `syllables.jsonl` contains every alignment event, including missing and extra syllables. Each mapped event joins to its source character, clause position, punctuation level, paired phrase marker, and 廣韻 and 平水韻 categories. A historical label uses a reviewed selection or a value shared by every candidate for that field. Historical ambiguity and the observed pronunciation remain separate. Duration and waveform measurements use a uniquely matched or reviewed event with an interval. Duplicate successful matches to the same slot remain visible and receive missing measurements pending adjudication.
- `gaps.jsonl` contains positive and zero gaps between adjacent successful events that also map to adjacent source slots. Omissions, substitutions, insertions, and other intervening events break eligibility. Quiet-gap candidates have root-mean-square (RMS) level at least 25 dB below the measured span reference and duration at or above each reported threshold of 100, 150, and 200 ms. The 150 ms threshold is the initial summary setting. These are waveform candidates for review. `reviewed_silence` requires a separately annotated silence interval. `adjacent_pitch_reset_st` is the next syllable’s early F0 minus the previous syllable’s late F0 in semitones when both are trackable.
- `recordings.jsonl` contains alignment coverage, acoustic reference levels, duration by historical tone and 平仄, and normalized pairwise variability indices (nPVI) with eligible-pair counts. Syllable nPVI uses adjacent syllables within the same clause and gaps below 150 ms. Clause articulation sums the measured syllable durations of each complete clause. Elapsed clause timing also captures internal gaps and any intervening speech. Clause nPVI compares adjacent complete articulation values. Grouped levels report token counts and geometric mean durations. Empty estimates are JSON null.

## Waveform choices and limits

The waveform is averaged to mono. RMS intensity is reported in dB relative to the interval from the first to last measured syllable, including any gaps. Exact digital zero yields no finite relative dB. Microphone gain and the span’s silence ratio affect this reference. Praat’s raw autocorrelation estimates fundamental frequency (F0) with a 10 ms frame step and a 75–600 Hz search band. Missing or unvoiced frames remain missing. Both frames around an adjacent jump of at least 0.8 octaves are removed from the pitch summaries and the potential jump count is retained. This screen catches some tracking errors and needs checking on creaky and sung audio. [Parselmouth 0.4.6 release](https://pypi.org/project/praat-parselmouth/0.4.6/) · [Praat raw autocorrelation manual](https://www.fon.hum.uva.nl/praat/manual/pitch_analysis_by_raw_autocorrelation.html)

Relative pitch uses the median eligible voiced F0 of the take. Early and late estimates use the first and last thirds of a syllable's pitch frame positions, respectively, with any available reliable values. Curvature averages absolute second differences on contiguous reliable triples after a three-frame median filter. The clause summary weights syllable curvature by the number of triples and keeps pitch resets separate. These analytic choices describe pitch movement. Tone-target deviations require a separate reference level and matched contextual contours, and lexical-tone classification of the actual performance requires independent review. [Stage 2 acoustic definitions](../theory/foundations.md#6-acoustic-measurements-from-actual-readings)

## Optional interval evidence

Use `--intervals PATH` for independent reviewed acoustic labels with fields `recording_id`, `start_s`, `end_s`, `label`, and `reviewed`. Labels are `vowel`, `consonant`, `silence`, `breath`, or `unclassified`. Use `reviewed: true` for accepted intervals and include `evidence: "audible_inhalation"` or `"respiratory_signal"` for a corroborated breath. Reviewed intervals are nonoverlapping. Mark difficult or uncertain intervals `unclassified` rather than deriving their class from a grapheme or historical reading.

Adjacent, touching segments in the same class merge into one run. `%V` uses reviewed V and C durations only, and ΔC is the sample standard deviation of consonant-run duration. Vowel nPVI requires a contiguous V–C–V configuration in reviewed intervals. Classified duration and run counts accompany the estimates. Breath groups count aligned realizations between corroborated inhalations, including timed insertions, substitutions, and repeats when present. Incomplete edge groups and groups with speech intervals crossing a breath boundary receive no measure. Syllable-only alignments leave V/C and breath metrics unavailable. [Stage 2 rhythm and respiration references](../theory/foundations.md#timing-variability-at-several-scales)

Listen to a stratified sample before using the output for performance inference. Check a time-aligned waveform at punctuation boundaries, model substitutions, unusually long gaps, and potential octave jumps. Mark source edition discrepancies separately from repairs. Keep human renditions and synthetic stimuli separate in analysis. [Stage 2 validation design](../theory/foundations.md#7-criticism-led-tests-for-骈文)
