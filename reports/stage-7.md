# Stage 7 checkpoint

The toolkit and the final report are ready for the edition-pinned parallel-prose (骈文) and period-matched comparison pilot. `./shunkou score INPUT.txt` reports interpretable components for the document, its paragraphs and its clauses. It preserves exact witness and text offsets, unresolved reading candidates, and support for historical estimates under 《廣韻》 and 《平水韻》. Ranked text observations give the reason and affected clauses. Annotated pairs use the independent Stage 3 pairings. General plain-text input uses the cached candidates when available. [Command and runbook](../hpc/README.md#stage-7-scoring-through-the-gateway)

`--audio` adds the recording provenance, exact waveform check, linked intervals, timing coverage, observed pronunciation drafts, low-energy gap candidates, and places for review. The optional HTML highlights ranked clauses and plays their timed portions. Some intervals cover only linked parts of a clause. The recording and the HTML containing its excerpts remain on Gilbreth. `--decode` uses the cached Stage 4 model in a Slurm GPU allocation. Repeat scoring can reuse the checksum-bound draft. Verified human events use an explicit review record. [Acoustic definitions](../audio/ACOUSTIC_FEATURES.md) · [Production protocol](../audio/STAGE6_PRODUCTION.md)

## Live verification

- Gateway Slurm job `12472945` completed on one A10 with exit code `0:0` in `00:03:05`. The job scored all 12 edition-matched texts in six pairs, scored a new two-paragraph text using the cached lexicons, and freshly decoded the M04 pair at the same synthetic voice and speed.
- The ET01 parallel-prose take had 24 of 26 written slots linked and four clause players covering whole clauses or linked portions. The ET02 comparison take had 23 of 24 slots linked and five clause players. Each report gave one audio review cue. The HTML output was checked for a player for every available interval. These counts describe the test takes.
- The final deployed version reran the tests on Gilbreth and all 24 passed, including the live historical annotation check. A second verified run rebuilt both audio reports and all 12 text reports from cached drafts. The GPU run is in `$SHUNKOU_ROOT/results/stage7/job-12472945`, the final release in `$SHUNKOU_ROOT/results/stage7/release`, and the GPU log in `$SHUNKOU_ROOT/logs/stage7-12472945.log`.
- `make all` passed locally. It ran the tests and shell syntax checks and rebuilt both figures. The live historical-annotation test was skipped locally because it needs the Gilbreth corpus.

## Scope

The research separates ease of oral production (顺口) from sound-pattern beauty (音律美). The release scores describe structural components and highlight acoustically observable review cues. Syntactic parallelism still relies on independent annotation. Timing, pitch, and alignment discrepancies from this pilot characterize synthetic readings, and the two human outcomes still need independent validation. The report records the shuffled controls, text–sound disagreements, failures, and a design for that validation. [Final report and figures](final.md)

## Quantitative diagnostics on fresh works

The report combines exact written lengths and clause rhythm, coverage-qualified historical ending measures under 《廣韻》 and 《平水韻》, WAV durations, and articulation timing for fully linked clauses. It binds each measurement to the pinned text and the checksummed recording. It compares two synthetic Mandarin voices on the same written and intended phoneme sequence. Only complete clauses available in both voices enter the timing comparison and the held-out timing benchmark. Rhyme and tone values remain descriptive. The report preserves ambiguous readings, missing links, and exact clause locations. [Report command](../hpc/README.md#quantitative-report-on-fresh-works-and-two-voices)

**Project hypothesis.** A count-only model predicts complete-clause articulation better than a constant-duration baseline on works excluded from each fit. Both models weight works equally. The shuffle redistributes clause lengths within each work and uses the same shuffled slot counts for both voices. It refits every fold for 999 draws. This benchmark measures a timing relationship and supplies no preference or read-aloud outcome. Participant testing remains reserved for final validation.

### Live validation on Gilbreth

**Controlled result.** Job `12484292` finished in 3 min 51 s on one A10. It verified eight distinct works by eight authors against four archived inventories and rendered 16 recordings. The passages form four period- and topic-matched pairs with 229 written slots and 42 clauses. The two voices linked 190 and 206 of 229 slots, respectively. The written four-or-six-character share was higher in parallel prose in three pairs and tied in one. The four differences were +0.75, +0.30, 0 and +0.17. This describes the chosen excerpts. [Sources and editorial punctuation](../data/pilot/DATA_CARD.md#fresh-works-for-the-two-voice-quantitative-report)

| Timing measure | Shared clauses | Works | Across-voice Spearman ρ | Median absolute difference across voices |
| --- | ---: | ---: | ---: | ---: |
| Complete clause articulation | 10/42 | 7/8 | 0.830 | 50 ms |
| Exploratory elapsed time between matched endpoints | 22/42 | 8/8 | 0.973 | 45 ms |

Character count reduced work-held-out articulation error from 330 to 72 ms in the original voice and from 321 to 79 ms in the second. The complete clauses had constant length within each usable work, so a within-work length shuffle could not test that endpoint. The result applies to the shared complete subset.

After inspecting alignment coverage, the separate elapsed check used matched first and last characters and included any intervening gaps or speech. The corresponding held-out errors fell from 274 to 56 ms and from 276 to 58 ms. The median shuffled errors were 166 and 160 ms, respectively. Three works supplied within-work length variation. In each voice, the observed error was at the lower 0.003 tail of the seeded shuffle distribution with the finite-sample correction. This exploratory comparison supports broader timing coverage in these two synthetic voices. The complete and bracketed measures retain separate denominators and meanings.

The verified files are `report-v2.md` and `report-v2.json` under `$SHUNKOU_ROOT/model-development/quantitative-report/results/quantitative-report`. The initial complete-articulation report and the freshness record are also preserved there. The new report describes rhythmic structure and timing for 音律美 research. The 顺口 section records the separate first-read evidence still required. The WAVs and alignment drafts remain on Gilbreth.

### Second-aligner coverage across both voices

The rerun uses the same 16 checksum-bound WAVs and all eight full passages. FunASR estimates timestamp intervals from audio and the expected character count on a nominal 20 ms grid. The pipeline then attaches the supplied characters to those estimates in order. The spans can include pauses. Confirming realized pronunciation requires separate phonetic evidence. [Model files and revision](https://huggingface.co/funasr/fa-zh/tree/d7701644d6e336f093501241beca010519c0986f) · [FunASR inference source](https://github.com/modelscope/FunASR/blob/main/funasr/models/monotonic_aligner/model.py#L212-L235)

The coverage rule was set before this run. A clause endpoint with a Charsiu phone link must agree with FunASR within 60 ms by midpoint. When the link is missing, the nearest linked character on each side must be within two Han positions, both aligners must agree on those anchors within 60 ms, and the FunASR endpoint midpoint must fall between the observed anchor midpoints. The audit compares span differences on the original common elapsed clauses and checks whether the new common FunASR subset supports the held-out count and grouped length shuffle. Model agreement is an exploratory timing check. [Gilbreth reproduction](../hpc/README.md#second-alignment-on-the-existing-recordings)

**Controlled result.** Job `12484865` ran in 3 min 4 s on one A10. FunASR produced usable ordered intervals for all 229 written positions in each voice across 16 unchanged recordings.

| Clauses with timing (of 42) | `zm_010` | `zf_001` | Both voices |
| --- | ---: | ---: | ---: |
| Complete Charsiu articulation | 15 | 22 | 10 |
| Original Charsiu elapsed spans | 26 | 32 | 22 |
| Raw FunASR elapsed spans | 42 | 42 | 42 |
| Anchor-supported FunASR elapsed spans | 1 | 3 | 1 |
| Elapsed spans available from either method | 27 | 33 | 23 |

The one shared addition was 必浚其泉源 in Wei Zheng’s 《諫太宗十思疏》. FunASR estimated a span of 1,060 ms in both voices. The first character met the direct agreement rule, and neighboring links bracketed the estimated midpoint of 源 in both voices. Both of the original elapsed spans for this clause were unavailable. The remaining 19 clauses without shared elapsed spans stayed unresolved by the agreement rule.

FunASR midpoints were a median 80 ms later than Charsiu in each voice. The 60 ms rule held at 47 of 190 and 55 of 206 directly linked positions, respectively. On the 22 original shared clauses, the median absolute difference in elapsed span was 55 ms for `zm_010` and 40 ms for `zf_001`. These differences compare two estimators. Exact speech boundaries would require separate waveform verification. The one shared FunASR-supported clause permits no work-held-out estimate or shuffle. A larger FunASR comparison would still be conditional on its expected-count input.

The post-alignment rerun verified the same input hashes and reproduced the previous timing checks to numerical precision. The updated files are `report-v3.md`, `report-v3.json`, and `secondary-alignment.json` in the private results directory on Gilbreth. These timing checks belong with the 音律美 diagnostics. 顺口 still awaits separate first-read measurements in final participant validation.

### Waveform check of the 80 ms offset

**Project hypothesis.** Moving FunASR timestamps 80 ms earlier may improve their agreement with the audio. The 80 ms value came from the two aligners' midpoint difference on these eight works. The fit-free −80 ms comparison tests that proposal. Each fitted correction excludes the evaluated work in both voices and weights the training works equally. The pooled shift uses all eligible clip edges from the other works, and the transfer fit uses only their other-voice readings. After inspecting the difference in coverage between clip onsets and offsets, an exploratory fit treats them separately.

The waveform reference uses 5 ms PCM energy windows with a primary −50 dBFS cutoff. Edges must reach nearby clear activity and agree within 15 ms across −55, −50 and −45 dBFS. Internal use requires quiet intervals lasting at least 100 ms. A take supplies provisional internal labels in order when the number of stable pauses matches the number of written clause breaks and no quiet candidate was rejected. These landmarks measure energy transitions. Phonetic labeling requires its own evidence. FunASR treats the sequence's start and end separately when assembling token timestamps. The Stage 5 sample-matching controls verified relative shifts, which are invariant to a constant time translation. [Timestamp estimation method](https://arxiv.org/html/2301.12343#S4.SS2) · [FunASR implementation](https://github.com/modelscope/FunASR/blob/main/funasr/utils/timestamp_tools.py) · [Exact PCM controls](stage-5.md#transfer-to-a-second-synthetic-voice)

**Controlled result.** The waveform check found six stable clip onsets in `zm_010` and seven in `zf_001`, with six works represented in both. FunASR started late by a median 40 and 35 ms on these landmarks. The table gives work-weighted mean absolute error, in milliseconds.

| Voice | Onsets | Raw FunASR | Fixed −80 ms | Held-out pooled shift | Held-out onset-only shift |
| --- | ---: | ---: | ---: | ---: | ---: |
| `zm_010` | 6 | 37.50 | 42.50 | 53.54 | 26.67 |
| `zf_001` | 7 | 32.14 | 50.71 | 60.36 | 17.50 |

The fixed shift cut the median absolute difference between the two aligners' character midpoints from 80 to 20 ms for each voice, while worsening onset error against the waveform. The onset-only fit moved timestamps earlier by 28.75–35 ms in the held-out folds. It improved clip-onset error in both voices on this sample. The four eligible clip offsets all came from `zf_001`. Their raw error was 360 ms and fell to 25 ms with a separately fitted offset shift. Only one take, `VET1C` in `zf_001`, supplied count-matched internal pauses. Its four edges yielded 51.25 ms error with or without the fixed shift. A held-out internal fit requires additional works. Both sets of observations are limited to one voice.

The waveform results support exploring a clip-onset adjustment. A shared correction for clause endpoints still lacks corroboration. A constant translation would also leave each elapsed duration unchanged. The report retains 23 shared elapsed spans and 10 complete-articulation clauses, with v3 results verified against v4. The waveform audit supplements the 音律美 timing diagnostics. 顺口 remains a separate first-read outcome, and participant testing is reserved for final validation. [Gilbreth rerun](../hpc/README.md#waveform-check-of-the-alignment-offset)

### Independent onset transfer and internal boundary controls

**Project hypothesis.** A frozen adjustment might transfer to recording onsets on different works and voices. Before scoring the new takes, the work-balanced median from the v4 onset landmarks fixed the correction at −35 ms. The eight v4 works served as the calibration cohort, with stable onsets in seven of those works. The transfer used all 16 historical-increment works in eight matched sixth-century and Early Tang pairs. These works had featured in earlier historical checks and were disjoint from v4 by work and credited author. Both voices used the same text, intended readings, nominal speed and seed for each passage. Scoring compared raw FunASR, the frozen shift, and the earlier −80 ms proposal on the same works in both voices. [Historical source inventory](../data/pilot/DATA_CARD.md#fresh-works-for-the-historical-feature-benchmark) · [Gilbreth commands](../hpc/README.md#independent-onset-transfer)

**Controlled result.** Job `12485050` rendered 32 takes and found stable waveform onsets in 14 of 16 works in `zm_010` and 11 in `zf_001`. The common cohort was 10 works. On that cohort, the frozen shift reduced mean absolute onset error from 40.5 to 25.5 ms in `zm_010` and from 27.5 to 22.5 ms in `zf_001`. Per-work error fell in seven and five works, respectively. The −80 ms comparator gave 40.5 and 53.5 ms.

Job `12485217` added `zf_002`, a Kokoro voice excluded from the fit and the earlier two-voice check. It used the same 16 evaluation works and the frozen correction. The three-voice intersection was nine works. Raw and corrected errors on that intersection were 45.00 and 24.44 ms for `zm_010`, 30.00 and 20.56 ms for `zf_001`, and 45.00 and 20.00 ms for `zf_002`. The correction helped seven, five and eight works, respectively. This tests a new voice from the same synthesizer. [Third-voice command](../hpc/README.md#recording-onset-in-a-held-out-voice)

The gains stayed positive across the entire retained waveform-onset ranges. Using the latest qualifying edge for every recording, the minimum average gains were 19.4, 7.2 and 20.6 ms in the three voices. These values bound sensitivity to the three energy thresholds.

The absolute internal control used the same recorded speech in different contexts. Job `12485122` assembled both orders of each matched pair in both voices, preserving the complete PCM of both passages with 400 ms of zeros between them. The onset reference for the second passage was its independently measured waveform onset plus its exact sample offset in the composite. Errors weight literary pairs equally. [Join control reproduction](../hpc/README.md#absolute-timing-at-exact-waveform-joins)

| Voice | Raw join error (ms) | Frozen −35 ms (ms) | Fixed −80 ms (ms) | Median absolute onset movement with context (ms) |
| --- | ---: | ---: | ---: | ---: |
| `zm_010` | 20.71 | 42.86 | 87.86 | 50 |
| `zf_001` | 21.71 | 52.57 | 97.57 | 40 |

Ten target works across seven matched pairs had stable reference onsets and model estimates in both voices. The −35 ms shift worsened nine of ten targets in each voice. The movement compares the start estimate for the same speech standalone and after the known join, with the exact placement removed. This confines the positive transfer result to recording onsets in isolation.

Even using the earliest qualifying waveform edge for each join, which maximizes the apparent benefit of moving a timestamp earlier, the shift increased pair-weighted error by at least 18.6 and 30.1 ms.

For native pauses, job `12485075` regenerated all 16 v4 takes byte for byte and recorded Kokoro's predicted token durations. A label required a unique written punctuation site across the nominal −25 ms origin and its adjacent 25 ms frames. Zero of 13 stable quiet intervals met that rule. Their centers lay a median 115 ms outside the nearest nominal punctuation window. The duration draft estimates alignment frames upstream of the waveform decoder, so matching the final WAV byte for byte establishes input consistency without establishing a lexical boundary. The v4 clause timings and coverage remain the reference. [Kokoro inference source](https://github.com/hexgrad/kokoro/blob/main/kokoro/model.py) · [Native pause timing command](../hpc/README.md#internal-pauses-with-generator-assisted-labels)

### Transfer of historical descriptors for synthetic clip duration

The 16 historical-increment works supplied separate fits for the two voices. The eight v4 works were held out as complete works. The baseline predicts exact WAV duration from character count and a fitted mean rate. Each candidate adds one historical descriptor to that rate. Rhyme concentration is the share of pairs of resolved written positions that belong to the same historical rhyme group, measured across the complete excerpt. The comparison used 999 seeded shuffles within genre and period, with the same assignments in both voices. The primary family used the two 廣韻 descriptors across both voices and Holm adjustment. 平水韻 served as a sensitivity tier.

| Voice | Count-only MAE (ms) | With 廣韻 level-tone share (ms) | With 廣韻 rhyme concentration (ms) | Adjusted rhyme tail fraction |
| --- | ---: | ---: | ---: | ---: |
| `zm_010` | 206.27 | 300.47 | 192.25 | 0.020 |
| `zf_001` | 241.38 | 297.94 | 227.53 | 0.129 |

Rhyme concentration lowered error in six of eight works in each voice. The gain stayed positive when dropping any one held-out literary pair with the fit frozen, ranging from 9.4 to 16.7 ms in `zm_010` and 8.5 to 21.1 ms in `zf_001`. Both 平水韻 candidates increased error in both voices. The 廣韻 rhyme finding merits replication as a small, reference-dependent timing effect. The experiment measured synthetic WAV duration, which includes pauses. Ratings and read-aloud behavior remain separate outcomes.

Job `12485319` repeated the same duration comparison in `zf_002`, with the same work split and shuffle assignments. Count-only error was 216.90 ms. 廣韻 rhyme concentration lowered it to 199.99 ms, a 16.91 ms gain with a Holm-adjusted shuffle fraction of 0.076 across the two primary descriptors in this follow-up. 廣韻 level-tone share raised error to 321.30 ms. Both 平水韻 candidates again increased error. This extends the direction of the small rhyme gain across voices while retaining the same eight evaluation works. [Third-voice reproduction](../hpc/README.md#historical-duration-in-the-third-voice)

### Written four- and six-character clauses

**Project hypothesis.** A higher share of four- and six-character clauses (四六句) distinguishes the selected parallel prose excerpts within their literary matches. The fixed-count control randomly places the same number of internal cuts among the same Han positions within each passage. It preserves total Han count and clause count, with an exact expectation from uniform positive integer compositions and 999 simulated cut assignments for each cohort. A second control independently swaps genre labels within each literary pair to test how consistent the paired direction is.

| Matched cohort | Parallel higher / ties / comparison higher | Mean parallel advantage | Fixed-count cut tail fraction | Genre-swap tail fraction |
| --- | ---: | ---: | ---: | ---: |
| Historical-increment, eight pairs | 6 / 0 / 2 | 29.8 percentage points | 0.001 | 0.0156 |
| v4, four separate pairs | 3 / 1 / 0 | 30.4 percentage points | 0.011 | 0.125 |

The smallest attainable one-sided genre-swap fraction in v4 is 0.125 with one tied pair. Removing the four marked project-added punctuation breaks increased the v4 advantage to 36.7 percentage points and retained the same pair directions. This supports 四六句 share as a written structural descriptor for these excerpts and editions. Relating it to either 音律美 or 顺口 requires the separate outcome tests. [Fixed-count control command](../hpc/README.md#fixed-count-written-clause-control)

### Assigning native pauses and testing held-out clause boundaries

**Project hypothesis.** The end of a stable quiet interval may identify the next written position more reliably than the center of the interval identifies a generator punctuation frame. The original PCM check verified the 16 WAV checksums and reproduced every edge of the 13 stable quiet intervals using the frozen v4 thresholds. The new rule screens all adjacent Han positions before consulting written punctuation. The proposed position must follow a Han start before the quiet interval. Its unshifted FunASR start must be within 60 ms of the entire measured resume-edge range and 40 ms closer than the next candidate. These are three and two nominal FunASR frames, respectively. Native phone corroboration also requires Charsiu to pick the same position, directly adjacent linked events on each side, and agreement within 60 ms between the left event's end and the waveform quiet onset. [FunASR timestamp method](https://arxiv.org/html/2301.12343#S4.SS2) · [Charsiu phone alignment](https://arxiv.org/abs/2110.03876)

**Original recordings.** FunASR proposed 11 written clause breaks and one within-clause position, with one interval unmatched. Seven of the 11 clause candidates met the Charsiu corroboration rule. All seven were in `zf_001`, which supplied ten of the original quiet intervals. The same written break, 「遇倉卒，求檢至」 in 《千金要方序》, was proposed in both voices and corroborated in `zf_001`. The corroborated break after 「方而來」 in 《論語集解義疏》 is one of the project's punctuation additions to an unpunctuated witness. The reports preserve each interval, the adjacent Chinese text and the reason for weak or missing phonetic support. These are draft correspondences between waveform timing and text. [Edition and punctuation notes](../data/pilot/DATA_CARD.md#fresh-works-for-the-two-voice-quantitative-report)

**Held-out controls.** Job `12486164` reconstructed 32 sample-identical joins from 16 different works in the two voices, each with the same 400 ms zero guard. The automatic detector accepted one of 16 guards in `zm_010` and nine of 16 in `zf_001`. The matcher chose the exact break for every accepted guard. The voices accepted disjoint sets of works. Replaying the detector checks on the exact guard showed that ten of the 15 misses in `zm_010` were sensitive to the energy cutoff, and five lacked sustained activity just before the quiet interval. In `zf_001`, four of the seven misses were cutoff-sensitive and three lacked sustained activity just after the quiet interval.

Job `12486275` isolated assignment by supplying the sample-defined guard start and the right donor's PCM-measured onset at its exact placement. It used the same thresholds and searched all adjacent Han positions. The matcher picked the correct break for 13 of 14 eligible joins in `zm_010` and 11 of 11 in `zf_001`. The remaining eligible join yielded an abstention. Both voices chose the correct break in all ten jointly eligible works. Masking the true written break produced zero alternative clause labels. This conditional result tests the matcher given measured edges. The full detector results show its limits as an automatic pipeline.

On the 32 unedited held-out WAVs, the method proposed six clause positions in `zm_010` and 19 in `zf_001` from six and 19 stable intervals, respectively. Two of the proposed positions recurred in both voices. These counts describe native coverage and cross-voice consistency. Native assignments require independently labeled boundaries for accuracy estimates. The pause results belong to the timing diagnostics for 音律美. 顺口 remains a separate first-read outcome, and participant testing is reserved for final validation. [Gilbreth runbook](../hpc/README.md#native-pauses-and-held-out-clause-assignment)

### Relative-energy pause detection and independent transcripts

**Project hypothesis.** A detector that adapts to each recording's level may reduce the voice-dependent misses. The rule measures 5 ms RMS frames, using the 90th percentile of frame power as a level reference. A quiet interval requires at least 100 ms at 30 dB below that level and 30 ms of cumulative clear activity in each of two 160 ms flanks. The detector records a separate eligibility flag for the speech-resumption edge. It must be present and vary by at most 40 ms across quiet thresholds of −35, −30 and −25 dB relative to the reference. The existing Han assignment rule was frozen. [Detector commands](../hpc/README.md#recording-relative-pause-detection)

**Independent works.** Job `12486551` used four expansion works disjoint in work and author from the original and historical development cohorts. All three voices had the same inputs, nominal speed, and seed per passage. Joining both orders of each pair at 150, 250 and 400 ms kept the original samples and yielded 12 targets per voice. Correct assignments increased from 0 to 11 in `zm_010`, 6 to 12 in `zf_001`, and 6 to 9 in `zf_002`. The new rule detected all 36 guards. It abstained on one usable resumption and withheld three uncertain resumptions. Every proposed position agreed with the known splice in this controlled test.

Nine of 12 targets were correct in all three voices with the relative detector. The fixed detector had zero such targets. On the same 12 unedited WAVs, the relative detector and matcher proposed four clause positions that recurred across all voices, up from one. This is native coverage. Both detectors found every exact 120, 240 and 400 ms insertion at the chosen energetic interior sites in clean speech at both levels, with zero false detections at the unchanged and 60 ms control sites.

**Noise stress.** With smoothed background noise 36 dB below the clean recording's reference power, the relative detector found all 36 inserted quiet intervals. Eleven had usable speech-resumption edges. The fixed detector found and retained 21. At −24 dB relative to the reference, both detectors missed all 36 insertions. Neither produced a long-pause match at the tested unchanged or 60 ms control sites at either noise level. These are controlled noise conditions on the same four works. The clean-join advantage therefore supports diagnostic use in clean synthetic audio, with edge eligibility reported separately in noisier material. [Noise reproduction](../hpc/README.md#recording-relative-pause-detection)

**Fresh replication.** Job `12488533` applied the original thresholds and matcher to four newly sourced works, two period-matched pairs from the late Southern Liang and Early Tang. The fixed detector correctly assigned 12 of 36 clean joins. The relative detector correctly assigned all 36, including all 12 targets in each voice. Across the two cohorts the totals were 24 of 72 and 68 of 72. Trials reuse the same eight works, so those totals do not represent 72 independent works. On the fresh, unedited WAVs, six candidate positions recurred across all three voices with the relative detector, compared with one for the fixed detector. The live manifest predates the addition of explicit edition and license URL fields. Witness revisions, text hashes, punctuation and reading recipes are identical. [Corpus provenance](../data/pilot/DATA_CARD.md#fresh-works-for-the-pause-detector-replication)

**Independent transcription.** Whisper separately transcribed the waveform before and after each original measured pause, with no transcript, character count, or punctuation provided. A label required a unique three-Han match on both sides after retaining only conservative one-to-one Unihan orthographic equivalents. Whisper-base agreed with one of the 13 original interval assignments, and abstained on the other 12. It returned no unique labels on 25 native held-out intervals or 32 known join trials. This is a coverage limit of the strict lexical procedure. The recognizer's abstentions supply no evidence for or against the candidate boundaries. [Model files](https://huggingface.co/openai/whisper-base/tree/e37978b90ca9030d5170a5c07aadb050351a65bb) · [Recognition audit command](../hpc/README.md#independent-transcription-at-pause-boundaries)

Whisper-small used the same matching rules. It supplied one agreeing position among the 13 originals, one among the 25 native held-out intervals, and one correct position in the 32 known join trials. The strict transcription approach therefore supplies only isolated additional evidence on these recordings. The timing results belong to 音律美 research. 顺口 remains a separate first-read outcome, with participation reserved for final validation. [Whisper-small publisher files](https://huggingface.co/openai/whisper-small/tree/973afd24965f72e36ca33b3055d56a652f456b4d)

### Noise-aware pause timing across three voices

**Project hypothesis.** Estimating the background floor directly may recover pauses and speech-resumption timing under controlled noise. The frozen detector measures 5 ms frame powers and uses whole-recording P10 and P90 for background and speech-level references. It reuses the prior relative detector when the floor is below its quiet thresholds, and abstains when the level is less than 15 dB above the floor. Otherwise it uses a three-frame median and quiet cutoffs at least 4, 5 and 6 dB above background. A long pause needs 100 ms of quiet and sustained clear activity on each flank. A usable resumption needs edge spread no greater than 40 ms and confirmation from raw frames after the latest edge. The noise estimate assumes roughly stationary background and enough low-energy frames. [Background estimation precedent](https://www.iks.rwth-aachen.de/publikationen/publications-detail//martin01c/)

The noise settings were fixed before evaluating the four newly sourced replication works. The clean recordings had already been used in the clean-join benchmark. All three voice takes of each work contributed the same type of controls. The interior test gives all detectors identical PCM with 120, 240 and 400 ms guards at independently chosen energetic cuts. The unchanged and 60 ms cases are negative controls at the same sites. The exact inserted end is the timing reference. The join test instead uses the known Han ordinal at an exact splice and a separate clean donor waveform-onset band when available. The matcher and tolerances remain frozen. Noise levels are relative to clean 5 ms P90 frame power. [Gilbreth reproduction](../hpc/README.md#noise-aware-pause-detection)

**Interior edge result.** Job `12488871` finished in 4 min 1 s on an A10. All 12 source recordings supplied an energetic cut. The table reports usable resumptions within 20 ms of the sample-exact end, over all positive controls.

| Noise relative to clean P90 | Fixed | Relative | Noise-aware |
| --- | ---: | ---: | ---: |
| Clean | 36/36 | 36/36 | 36/36 |
| −36 dB | 23/36 | 13/36 | 36/36 |
| −24 dB | 0/36 | 0/36 | 36/36 |

The noise-aware detector recovered the same four works at each of the three durations in all three voices at both noise levels. It produced zero false long-pause matches at 24 negative sites per condition. At −36 dB the relative detector found all 36 guards, with 13 timing edges eligible and within tolerance. At −24 dB the earlier detectors found zero guards.

**Clause joins.** The joins preserved the source speech and exact placement of a 150, 250 or 400 ms noise-only guard. Stationary noise was mixed into the donor samples as well. At −36 dB, the fixed detector and matcher recovered four of 36 known breaks and the relative pipeline recovered zero. Both recovered zero at −24 dB. The noise-aware pipeline recovered all 36 known breaks at each level, including all 12 work-by-duration cases jointly across the three voices. It also returned an eligible resumption band within 20 ms of the full independent onset reference on all 33 joins with a stable clean donor reference at each level. One donor take in `zm_010` lacked that reference, accounting for the other three joins. The two earlier methods reproduced their archived clean assignment results on the exact same PCM.

This establishes recovery on sample-defined stationary-noise controls for four works and three synthetic voices. Other noise types and naturally produced boundaries require their own validation. The two report pairs in the private replication directory preserve the individual masks and measured errors. These are timing diagnostics for 音律美. 顺口 remains a separate first-read outcome, and participant testing is reserved for final validation.

### Noise-aware pause detection in natural Mandarin readings

**Established result for this sample.** On Gilbreth, the frozen detector matched 12 of 29 independently reviewed interior pauses across five readers. All 12 proposals in the reviewed windows matched a reference pause. Recall was 41% and F1 was 0.585. The full eligible resumption band was within 20 ms for three of 29 pauses, with the same three within 50 ms. The detector judged four of the matched edges eligible. The matched central start and end errors averaged 76.9 and 19.3 ms in absolute value. All five recordings took the noise-aware path and passed the recording-level signal check.

| Reader background | Detected / reviewed pauses | Matched / proposed pauses | Eligible resumption within 20 ms |
| --- | ---: | ---: | ---: |
| Beijing | 1/7 | 1/1 | 0 |
| Chengdu | 6/8 | 6/6 | 1 |
| Jinan | 1/5 | 1/1 | 0 |
| Taiyuan | 3/5 | 3/3 | 2 |
| Xi’an | 1/4 | 1/1 | 0 |

**Pause reference.** Five ManDi readers each recorded the same published Mandarin rendering of *The North Wind and the Sun* at home on a smartphone. We used the released mono PCM files with their internal timing intact, verified all five WAV hashes, and ran the unchanged detector on each complete file. AI reviewers annotated speech-free intervals of at least 100 ms from waveform and spectrogram views of the first six prompt rows, with detector output and aligner tiers hidden. We scored 59.34 seconds after masking 2.01 seconds of uncertain signal. The reviews included clear gaps containing diffuse breath or room sound. Two independently cross-reviewed windows agreed on all nine clear gaps and placed their resumptions within 10 ms of each other at the recorded annotation precision. The interval match maximized the number of time-ordered pairs with at least 0.5 intersection over union, then minimized resumption error. A prediction or reference entered the scoring window by its midpoint. The visual times are review estimates. [Recording and annotation protocol](https://aclanthology.org/2022.lrec-1.213.pdf) · [Source and selection](../data/pilot/DATA_CARD.md#natural-mandarin-pause-transfer)

**Clause reference.** A separate text-only review froze 12 clear interior syntactic clause endings. The archive’s Montreal Forced Aligner (MFA) times linked those written positions to audio across the complete readings. The manually checked Praat input tier contains one body span per file. Endpoints of internal lexical spans come from MFA. Of 60 clause endings across the five readings, 51 had an archived gap of at least 100 ms. A detector interval matched 16 of these 51 gaps. Nine endings had shorter or zero gaps, so coverage was 16 of 60 across all marked endings. This is a time-overlap check using archived lexical alignment. Independent verification of the spoken character at each junction is still needed to estimate end-to-end clause identification accuracy. [Stimulus edition, Appendix d, p. 170](https://etheses.whiterose.ac.uk/id/eprint/34805/1/Zhao_203000563_Thesis_Final.pdf) · [Reproduction](../hpc/README.md#natural-mandarin-pause-benchmark)

Recovery was substantially lower on this modern prose work than on the exact synthetic controls. The detector can propose intervals for review, with recall and precise timing strongly limited across these readers. The benchmark concerns acoustic timing for 音律美. 顺口 remains a separate first-read measure. Participant validation remains the final step.

### Miss audit and weak-interruption bridge on held-out readings

**Established result for the original ManDi sample.** Replaying the archived detector and checking its output against the exact WAVs accounted for all 17 missed visual reference pauses. Ten had a quiet run that covered too little of the reference to meet the 0.5 intersection-over-union rule. Seven of those ten contained multiple quiet runs separated by at most 20 ms within the reference interval. Three other pauses had several quiet runs shorter than 100 ms, two had only one such short run, one failed the adjacent-activity gate despite a sufficiently overlapping run, and one had no frame below the quiet cutoff. These are detector-side explanations. The waveform audit could distinguish many interfering transients from speech, with breath and room sound often visually ambiguous.

**Project hypothesis.** Joining quiet runs across a brief, weak interruption can recover continuous lexical gaps. The opt-in bridge joins interruptions of at most 20 ms if both neighboring original runs contain at least 20 ms of quiet and the interruption contains fewer than two consecutive clear raw frames. It applies the same rule at all three noise-aware cutoffs and then runs the existing duration, flank activity, and resumption checks. On the original five-reader development sample, it recovered five extra pauses and retained all 12 prior matches. There were zero unmatched proposals in either pass. The number of reference pauses with an eligible resumption band within 20 ms increased from three to four. [Runbook and code](../hpc/README.md#miss-audit-and-held-out-pause-transfer)

**Held-out test.** Seven original recordings covered four MCGA classical works and one THCHS-30 modern reading prompt repeated by three independently identified speakers. AI reviewers marked acoustic intervals from waveform and spectrogram views with both detectors' outputs hidden. The scored windows contained 67.34 seconds after masking 3.50 seconds of ambiguous signal. The detector received each complete distributed WAV. Both methods used the same 35 pauses and bounded windows. An eligible timing hit requires the entire resumption band to fall within the stated tolerance of the visually marked return of speech. [Corpora, texts, and rights](../data/pilot/DATA_CARD.md#fresh-recordings-for-the-pause-bridge)

| Held-out subset | Frozen detector | With bridge | Unmatched proposals, frozen → bridge | Eligible resumptions within 20 ms, frozen → bridge |
| --- | ---: | ---: | ---: | ---: |
| All seven recordings | 16/35 | 21/35 | 5 → 4 | 6 → 12 |
| Four MCGA classical excerpts | 10/25 | 15/25 | 4 → 3 | 6 → 10 |
| Two 骈文 excerpts within MCGA | 10/16 | 14/16 | 2 → 1 | 6 → 9 |
| THCHS-30, one prompt and three speakers | 6/10 | 6/10 | 1 → 1 | 0 → 2 |

On all held-out recordings the bridge retained all 16 prior matches, raised precision from 76% to 84% and recall from 46% to 60%, and raised F1 from 0.571 to 0.700. At 50 ms it provided usable resumptions for 14 of 35 reference pauses, up from seven. The additional detections came from the classical sample. Both 骈文 excerpts carry female voice labels and the public MCGA release lacks individual reader IDs. The THCHS-30 sample supplies known speaker separation and only one text. One MCGA recording used the relative fallback and received identical treatment from both runs. The bridge is an experimental improvement for 音律美 timing diagnostics, with clause identification and listening judgments requiring further validation. The separate 顺口 first-read outcome is reserved for final participant validation.

### Pre-boundary syllable duration on held-out readings

**Project hypothesis.** A reader can mark a structural boundary by lengthening the preceding syllable with little audible pause. On original Mandarin recordings, we compared a model using the noise-aware detector’s measured pause duration with the same model adding the preceding syllable’s estimated articulation duration divided by a local median. Zhang, Feng and Xu found that duration cues vary with line length and recitation style in classical poetry. They used a current-to-previous syllable duration ratio. We use nearby matched syllables because the immediate previous or following syllable can itself be extended or unavailable. [Primary recitation study](https://www.isca-archive.org/speechprosody_2026/zhang26c_speechprosody.pdf) · [Reproduction](../hpc/README.md#pre-boundary-syllable-duration)

The duration excludes the following intersyllable gap. The original method used 10 ms Charsiu phone frames and required matched consecutive heard syllables at the junction, plus at least two other matched syllables within three characters. It searched all joined character positions before scoring the reviewed candidates. A reported zero means the detector assigned no qualifying pause at that position. Both ridge logistic models were fitted and evaluated on the same available rows. Each fit excluded the test work and reader. For MCGA, we exclude the entire matching published voice group since individual speaker IDs are unavailable. The waveform models receive the performed Standard Mandarin, with punctuation removed from the transcript. Historical tone and rhyme categories remain separate. [Text and recording provenance](../data/pilot/DATA_CARD.md#pre-boundary-duration-corpora)

**Established results for the selected recordings.** The classification target is an independently marked structural junction. For MCGA, a text-only review marked clear clause or parallel arm endings and within-unit controls before audio analysis. For DEBATE, the authors' prompts prescribed alternative parses on the exact same Han characters. The DEBATE comparison used only positions with different intended boundaries in the two takes. The study uses these corpora for distinct tests. [MCGA release](https://aclanthology.org/2026.findings-acl.1543/) · [DEBATE release](https://zenodo.org/records/15609922)

| Sample | Scorable / marked sites | Average precision, pause → pause + duration | Brier loss, pause → pause + duration |
| --- | ---: | ---: | ---: |
| First MCGA sample, all lexical forms | 80 / 190 | .715 → .933 | .220 → .137 |
| MCGA parallel prose 骈文 | 33 / 65 | .740 → .926 | .235 → .164 |
| MCGA parallel rhapsody 骈赋 | 23 / 59 | .837 → .976 | .174 → .100 |
| MCGA classical prose 散文 | 24 / 66 | .526 → .909 | .244 → .137 |
| DEBATE same-text readings | 331 / 624 | .753 → .896 | .192 → .133 |

The MCGA genre rows describe the selected excerpts. The samples are small and their reading styles vary. Across the 113 complete DEBATE pairs at the exact same text, position, and reader, the intended-boundary take received the higher score in 92.5% of comparisons counting ties as half credit, up from 69.5%. The difference was 23.0 percentage points, with a descriptive crossed work-and-reader bootstrap interval of 13.5 to 31.8 points. In 65 complete pairs with no detector hit in either take, the pause model tied every pair. Duration gave 57 wins, one tie and seven losses, for 88.5%. The remaining pairs lacked one or both required measurements. This is a prompted parse test with newly aligned durations and no independently marked exact acoustic syllable intervals.

**Rate control and external modern replication.** A raw-duration crossover within each text and reader cancels a recording-wide multiplicative rate difference between takes. It compares the A-only target positions with the B-only positions in the same pair, using no local duration denominator. On the first DEBATE sample it estimated 55.2% longer pre-boundary syllables in 24 eligible text-reader cells under the stricter screen and 59.1% longer in 66 cells with the wider matched-left screen. The wider-screen work-level sign-swap result was one-sided Monte Carlo \(p < .001\). Even on the six eligible cells without detected pauses, the estimated difference was 47.9%. This small no-pause crossover is exploratory. The 10 cells with a scorable nonboundary placebo had a 51.8% target estimate and a 10.3% placebo estimate. These are contrasts on the observed decoder spans.

Job `12493446` decoded another 192 original DEBATE recordings. The 24 texts and four identified readers were all absent from fitting. Charsiu supplied both features at 232 of 408 marked candidate positions. Adding duration increased AP from .723 to .915 and reduced Brier loss from .180 to .123. In the 88 complete same-position pairs, concordance rose from 70.5% to 94.3%. In 50 complete pairs with no detected pauses on either take, concordance rose from chance to 92.0%. This replication uses the original Charsiu path, leaving coarse-fallback transfer to distinct identified readers untested. [Corpus and selection](../data/pilot/DATA_CARD.md#pre-boundary-duration-corpora)

**External classical replication.** The original pipeline’s 110 abstentions on the first sample came from 36 missing left links, 45 missing right links, 14 with both links missing, and 15 without consecutive heard events. We tested Qwen3-ForcedAligner as a second source of character intervals. It takes waveform and exact unpunctuated Han transcript, with an 80 ms timestamp grid. With Charsiu as the source of acoustics, each recovered link had to be the only eligible event for that character and the only eligible character for that event. Two existing neighboring anchors had to agree, interval overlap had to be at least 0.50 and centers at most 80 ms apart. With strict phonetic compatibility this recovered no additional links. Permitting a disagreement with Charsiu’s draft phone label recovered some local links. A separate fallback retained every usable Charsiu row and used coarse Qwen timing for the remaining rows with two available adjacent characters and a valid local duration reference. Zero-width spans remained unavailable. [Qwen methods, §3](https://arxiv.org/html/2601.21337v2#S3) · [Pinned Qwen model](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B/tree/c7cbfc2048c462b0d63a45797104fc9db3ad62b7)

The test set consisted of ten fresh works and authors, with five male-coded and five female-coded recordings. The individual readers are unidentified. Each test model was fitted on the opposite voice group from the **first** MCGA sample only. No replication works informed the fit. We applied the same feature scales and ridge penalty across all four methods. The threshold of 0.5 was fixed before reading the transfer results. The 193 sites include 100 structural junctions and 93 within-unit controls.

| External MCGA timing path | Eligible sites | AP, pause → +duration | Brier loss, pause → +duration | True positives / proposed, at 0.5 | True positives / all positive sites |
| --- | ---: | ---: | ---: | ---: | ---: |
| Charsiu original | 85 / 193 | .679 → .876 | .209 → .159 | 32 / 43 | 32 / 100 |
| Charsiu with bounded Qwen identity rescue | 113 / 193 | .664 → .860 | .223 → .172 | 44 / 64 | 44 / 100 |
| Qwen coarse timing only | 191 / 193 | .688 → .870 | .215 → .152 | 74 / 87 | 74 / 100 |
| Charsiu first, Qwen coarse fallback | 192 / 193 | .680 → .889 | .213 → .151 | 78 / 92 | 78 / 100 |

On the 85 shared sites the combined model had AP .876 with Charsiu alone and .879 with the coarse fallback. On the 107 newly eligible sites, pause-only AP was .690 and adding duration raised it to .902. The 80 ms fallback is suitable for the boundary ranking experiment. Its spans remain draft acoustic durations. A controlled structural boundary is distinct from a perceptual rating for 音律美, and these tests supply no first-read labels for 顺口. The timing feature is ready as an experimental diagnostic. Both outcomes await final-stage participant validation.

### Mixed-genre external holdout candidate

**Established textual facts.** 《唐董韶容墓誌銘（並序）》 is a 737 Tang inscription excavated at Xi’an in 2022. The excavation results became public in 2025. The transcribed text includes a dated death and burial account beginning 「開元廿五年」, a stretch of parallel praise beginning 「夫人積柔成行」, and a seven-line rhymed inscription starting at 「詞曰」. The witness retains two lacunae, including one in the verse. The original stone lacks modern punctuation. The current digital transcription supplies it. [Transcription of the inscription](https://zh.wikisource.org/wiki/唐董韶容墓誌銘#橫排) · [Newspaper reproduction and excavation context](https://ep.ycwb.com/epaper/ycwb/html/2025-11/14/content_2979_731180.htm)

**Project hypothesis.** The dated account, parallel praise, and verse give audible contrasts in phrasing and rhyme under the same reader and recording conditions. Retain the opening genealogy as another prose candidate, with lacuna-bearing sentences unavailable for complete-text comparison. Separate close readings from controlled changes in recitation. A straight reading may leave the lowest rating categories empty. The 1–7 音律美 range is a question for final listening judgments. The same work can independently test first-read 顺口 with an unfamiliar passage. Neither the text nor variants of it informed the project’s fitted models. Foundation-model pretraining exposure is unverifiable.

**Written benchmark.** The horizontal witness at revision `8738056` supplies 15 prose sentences delimited by the edition's full stops and seven verse lines following 詞曰. The title and verse marker identify sections. Two units contain lacunae and stay visible with blank scores. The editorial pass, made before viewing any prototype output and using the earlier 《拉法叶赋》 rubric, scored three units 4, five 5, seven 6, and five 7. The lowest judgments went to functional prose with uneven pacing. The higher judgments cited sustained parallel arms or a return to the main verse rhyme. The documentary reading uses written cadence and constitutes no participant result. [Transcription](https://zh.wikisource.org/wiki/唐董韶容墓誌銘#橫排) · [Independent published transcription](https://m.thepaper.cn/newsDetail_forward_33668086) · [Historical rhyme reference](https://wk.100ke.info/zh-hant/重修廣韻_(四庫全書本)/卷3)

On Gilbreth, the fixed ridge prototype fitted 209 earlier editorial sentence scores of 《拉法叶赋》 from the published revision `0a163a6`. Those labels range from 4–7. The regression uses group lengths and historical tone and rhyme descriptors computed at sentence or verse-line level, with reference-only standardization and mean imputation where the feature is unavailable. It rounds each prediction on the original scale without adjusting to the holdout's distribution. The new work supplied no labels, scaling terms, or feature weights. Tone and rhyme were looked up in the cached 《廣韻》 and 《平水韻》 with the Unihan variant data. The separate Stage 7 component report preserves the historical reading candidates. [Prototype](../src/quantitative_editorial_transfer.py)

**Established result for this witness.** The rounded prototype scores span 4–6 and the raw predictions span 4.321–6.269. Two complete units received 4, eleven 5, and seven 6. All complete prose units received 5 or 6. The six complete verse lines received two 4s and four 5s. The prototype was within one point of the editorial check at 16 of 20 scored units. Three of the four larger differences were verse lines in the principal rhyme. V02 received 4 from the prototype and 7 from the editorial pass, which cited the balance across 兮 and the ending 祉. A single-line input supplies no cross-line rhyme term. These observations support improving the context representation and measuring the rating scale with low anchors in final validation. They supply no direct ratings of recorded 音律美. First-read 顺口 remains its own outcome.

The original transcription, reference labels, input hashes, component and prediction JSONs are under `$SHUNKOU_ROOT/results/dong-shaorong-holdout-20261122`. The workbook places the source text, rounded predictions and independently assigned editorial scores side by side.

### Cross-line rhyme and parallelism on two new Tang works

**Design.** All four written models learned from the same 209 scored units in 27 sections of 《拉法叶赋》. Two complete early ninth-century works supplied the external test. 劉禹錫’s 《佛衣銘（並序）》 supplied a preface and 21 inscription lines. 白居易’s 《荔枝圖序》 supplied 12 units across two paragraphs. We split Bai’s long catalogue at existing commas so that neighboring units could be compared. A separate GPT reading of the complete texts assigned each unit a written sound-pattern beauty (音律美) rating before the prototype ran or any audio was heard. The two works had no role in the written fit. Bai appears in a separate, earlier timing study through another work. The two electronic transcriptions were checked against their corresponding 《全唐文》 entries. [Liu, pinned witness](https://zh.wikisource.org/wiki/Special:PermanentLink/1978293) · [Bai, pinned witness](https://zh.wikisource.org/wiki/Special:PermanentLink/2273816)

The rhyme features count matches between the final character and endings up to two units away in the same section. Each historical dictionary has its own feature. Ambiguous comparisons contribute only when every candidate combination gives the same answer. The structural parallelism features measure the lengths of corresponding punctuation groups, characters recurring in the same position, and balance between two arms of a unit. The features do not identify semantic oppositions or grammatical roles. All variants use the original ridge penalty, training-only scaling, and the same rounding rule. [Context scorer](../src/quantitative_editorial_context.py)

**Established results for these witnesses.** Mean absolute error compares each unrounded prediction with GPT’s fixed written score on the seven-point scale. Lower is closer. Each unit counts once in the pooled row.

| Fresh text | Units | Single-line model | Add rhyme | Add parallelism | Add both |
| --- | ---: | ---: | ---: | ---: | ---: |
| 《佛衣銘（並序）》 | 22 | 0.726 | 0.730 | 0.648 | 0.640 |
| 《荔枝圖序》 | 12 | 1.155 | 1.177 | 1.215 | 1.185 |
| Both works | 34 | 0.878 | 0.888 | 0.848 | 0.832 |

Two constant forecasts computed from the training work provide a scale check. Predicting the training mean of 5.541 for every unit gave an error of 0.719. Predicting the training median of 6 gave an error of 0.529, with errors of 0.500 on Liu and 0.583 on Bai. Eighteen of the 34 editorial judgments were 6. The prototype has yet to beat these simple forecasts on this sample.

Exact agreement after rounding rose from 10 to 13 of 34 units. Agreement within one point rose from 26 to 28. The combined model still assigned only 4–6. In 199 shuffles of intact units within their sections, 160 shuffles in Liu and 165 in Bai matched or beat the error for the original order. This control preserves the internal arms of each unit. The gains on Liu therefore give little evidence that the model is sensitive to the intended sequence. On Bai’s 「葉如桂，冬青」「華如橘，春榮」「實如丹，夏熟」, GPT gave each unit 6. Both prototype versions gave each unit 4. The repeated grammatical frame across the three units remains a specific gap.

On the previously examined 《唐董韶容墓誌銘》, 「神有禍兮人無祉」 moved from 4.496 to 4.850, or 4 to 5 after rounding. Parallelism alone gave 4.820, and cross-line rhyme alone gave 4.494. The written editorial judgment was 7. This is a diagnostic of the example that motivated the change. Only the two Tang works above supply fresh transfer results.

**Across-voice audio comparison.** Gilbreth Slurm job `12494569` produced 68 synthetic Standard Mandarin (普通話) WAVs, one recording per unit in each fixed Kokoro voice (`zm_010`, `zf_001`). The two readings shared the intended pronunciation, punctuation, seed and speed setting of 0.9. Charsiu decoded the waveforms. The acoustic comparison used internal punctuation with consecutive linked syllables, usable detector output and at least two local syllables for a duration reference. Of 36 internal junctions, 19 at identical text positions qualified in both voices, covering 12 of Liu’s 22 units and 7 of Bai’s 12. Across works, 25 junctions qualified in the male preset and 29 in the female preset. A measured zero means the detector found no qualifying pause. Separate clips supply no evidence about pauses between units.

The target was the same frozen written GPT score for both deliveries of each unit. Each fold fitted a correction using only the other work in the other voice. All three recalibrated models used the same held-out units and training intercept. Duration measures the last syllable before an internal junction relative to its local median. The table gives mean absolute error by held-out work and voice. The final row weights the four folds equally.

| Work | Voice | Eligible units | Recalibrated text | Add pause | Add pause and duration |
| --- | --- | ---: | ---: | ---: | ---: |
| 《佛衣銘》 | `zm_010` | 12 | 0.750 | 0.809 | 0.847 |
| 《佛衣銘》 | `zf_001` | 12 | 0.750 | 0.797 | 0.706 |
| 《荔枝圖序》 | `zm_010` | 7 | 1.016 | 1.016 | 0.937 |
| 《荔枝圖序》 | `zf_001` | 7 | 1.016 | 1.055 | 1.175 |
| Four-fold mean | | | 0.883 | 0.919 | 0.916 |

The frozen context model before recalibration gave a four-fold mean error of 0.875 on the same subset. The audio increment helped in two folds and hurt in two. In 199 within-work shuffles, we reassigned each unit’s two-voice acoustic measurements together, kept the editorial target and text prediction fixed, and refitted each fold. For both acoustic features together the observed gain was −0.033 points. The median shuffled gain was −0.030, with an add-one upper-tail fraction of 0.55. Excluding the unit containing the edition’s anomalous 愨, rendered literally as `que4`, left the errors unchanged. [Acoustic evaluator](../src/quantitative_editorial_audio.py) · [Gilbreth reproduction instructions](../hpc/README.md#written-editorial-scores-and-the-two-voice-acoustic-comparison)

**Interpretation.** Structural parallelism helped reproduce written judgments on one of the two works. Ordinary clause timing remains a diagnostic for how a rendering groups syllables. This experiment found no consistent gain from adding that timing to a written beauty score. The target gives both voices the same value by design, so listeners’ preferences between deliveries remain unmeasured. Reading ease (顺口) has its own first-read outcome. Participant testing remains reserved for the final stage. The original texts, frozen ratings, line-level comparisons, pronunciation choices, WAVs, alignment and shuffle outputs are in `$SHUNKOU_ROOT/results/editorial-context-20261122`.

### Repeated grammatical patterns on four fresh Northern Song works

**Question and design.** Can detecting a grammatical construction shared by neighboring lines bring the written 音律美 prototype closer to a frozen editorial reading than giving every unit 6? The primary comparison gives each work equal weight and uses mean absolute error on the unrounded 1–7 scale. All fits used the same 209 scored units of 《拉法叶赋》. The matcher was designed using the known Bai example. An independent GPT close reading of the four fresh works assigned all 74 scores before predictions. It gave ten 4s, twenty-three 5s, thirty 6s and eleven 7s. A separate interpretive review classified all 62 pairs of consecutive units within their printed paragraphs before seeing detector decisions.

The test includes three Northern Song records (記) and a short historical argument from four authors. Units end at a printed full stop, question mark, exclamation point or semicolon. Colophons, dates and short exclamations stay in the evaluation. The witnesses are four whole works selected to include both recurrent constructions and continuous prose. Generalization to 骈文 as a genre remains open. [《黃岡竹樓記》](https://zh.wikisource.org/wiki/Special:PermanentLink/7913645) · [《墨池記》](https://zh.wikisource.org/wiki/Special:PermanentLink/7911098) · [《袁州州學記》](https://zh.wikisource.org/wiki/Special:PermanentLink/2438135) · [《讀孟嘗君傳》](https://zh.wikisource.org/wiki/Special:PermanentLink/1741370)

The rule represents selected functional characters by their possible role, such as a comparison, negation or modal expression. An initial season word in a multi-character punctuation group occupies a time slot. A match requires corresponding positions and lengths, at least one recognized cue and some changing lexical material. Three features record a whole-line match, the share of matching characters in corresponding punctuation groups, and a run of at least three matching units. This approximates a subset of grammatical parallelism. Polyfunctional particles and changes of clause length can mislead it. [Grammar scorer](../src/quantitative_editorial_grammar.py)

**Established scoring results for these witnesses.** Lower error indicates closer agreement with the written GPT rating. The grammar extension lost to always-6 on all four works. Within-work concordance, the fraction of differently rated pairs correctly ordered with half credit for ties, was identical before and after adding grammar on every work.

| Work | Units | Always 6 | Prior context model | Add grammatical patterns |
| --- | ---: | ---: | ---: | ---: |
| 王禹偁《黃岡竹樓記》 | 27 | 0.704 | 0.821 | 0.816 |
| 曾鞏《墨池記》 | 15 | 0.733 | 0.755 | 0.755 |
| 李覯《袁州州學記》 | 27 | 0.778 | 0.862 | 0.860 |
| 王安石《讀孟嘗君傳》 | 5 | 0.600 | 1.517 | 1.516 |
| Equal weight per work (primary) | 74 | **0.704** | 0.989 | **0.987** |
| Equal weight per unit | 74 | **0.730** | 0.870 | **0.867** |

**Why recognition had little effect on scores.** Eight of the 209 training units contained a partial grammatical match across lines. None contained a whole-line match or belonged to a three-line run under the frozen rule. The ridge fit therefore assigned zero weight to those last two observations. The direct alternative of predicting separate training medians assigned 5.5 when the rule detected a match and 6 otherwise. Its equal-work error was 0.750. The model using only the three grammatical features had an error of 0.772. Back on the development example 「葉如桂，冬青」「華如橘，春榮」「實如丹，夏熟」, the rule recognized the full three-unit run. Each prediction rose from 4.175 to 4.249, still rounding to 4 against the earlier written judgment of 6.

**Recognition check.** On the fresh works the rule flagged six adjacent pairs. Five were among the nine clear parallels in the separately frozen reading. One was among 46 pairs judged absent at clause level. The seven uncertain pairs had no detector match. One miss was 「有屈力殫慮，祗順德意；有假官借師，苟具文書」, where the repeated construction introduces two contrasting kinds of official. One success was the pair starting 「夏宜急雨」「冬宜密雪」. The commentary in 《古文觀止》 separately identifies six successive 宜 expressions ending in the summary with 助. The detector caught four of the five transitions among those six units. It missed the transition from weather to activities. The historical note evaluates the sequence as a whole and was withheld from the editorial rater. [《古文觀止》卷九, commentary on 《黃岡竹樓記》](https://zh.wikisource.org/wiki/Special:PermanentLink/2520741#黃岡竹樓記)

**Shuffled controls.** Each control used 199 reproducible draws, fixed weights and unchanged target scores. The observed equal-work gain over the previous model was 0.0020 points. Only two within-paragraph line-order shuffles matched or exceeded that *increment* over the context model recomputed on the same shuffled order. However, on absolute error, 186 of those shuffles matched or beat the grammar model on the authentic order. In the second control, rearranging characters within each punctuation group altered only the grammar inputs. None of those 199 shuffles equaled the authentic grammar increment. These contrasts distinguish sensitivity to marker position from the practical ability to predict a score. The source units and adjacent pairs in a work are related, so the draws do not constitute 199 additional works.

**Interpretation.** Keep repeated frames as a descriptive reading aid. To learn a numerical weight, the training corpus needs more separately scored works containing both strong and ordinary passages with repeated constructions. Those future works require a newly reserved test set. This experiment measures written editorial agreement. Heard 音律美 and first-read ease (顺口) remain separate final-stage participant outcomes. Private line scores (`$SHUNKOU_ROOT/results/grammatical-patterns-20261122/line-scores.txt`) · [Gilbreth reproduction](../hpc/README.md#grammar-transfer-on-four-fresh-works)

### Expanding the grammatical-pattern training set

The earlier fit had 209 written editorial scores from one work, 《拉法叶赋》. It had no examples of a repeated whole-line frame under the frozen detector. The expansion selected patterned historical passages for training and included ordinary narration. The primary test reserved two entire eighth-century Tang works by other authors before feature inspection or rating. The previously tested four Northern Song works supplied a secondary comparison. Neither test set contributed training scores.

| New training source | Units collected | Coverage |
|---|---:|---|
| 謝惠連《雪賦》 | 12 | Two consecutive paragraphs from 《文選》卷十三. [Edition](https://zh.wikisource.org/wiki/Special:PermanentLink/8729816) |
| 孫綽《遊天台山賦》 | 19 | Two consecutive paragraphs from 《文選》卷十一. [Edition](https://zh.wikisource.org/wiki/Special:PermanentLink/49565) |
| 陶淵明《閑情賦》 | 24 | Two consecutive paragraphs from 《陶淵明集》. [Edition](https://zh.wikisource.org/wiki/Special:PermanentLink/2452606) |
| 魏徵《諫太宗十思疏》 | 30 | Complete memorial. This edition had previously supplied audio research material. [Edition](https://zh.wikisource.org/wiki/Special:PermanentLink/9884512) |
| 歐陽修《秋聲賦》 | 36 | Complete work, including its conversational prose. [Edition](https://zh.wikisource.org/wiki/Special:PermanentLink/2371985) |
| 蘇軾《記承天寺夜遊》 | 8 | Complete personal narrative, including the signed colophon identified as a supplement in this edition. [Edition](https://zh.wikisource.org/wiki/Special:PermanentLink/8732064) |

The two fresh works are 王維’s landscape letter 《山中與裴迪秀才書》 (15 units) and 元結’s landscape record 《右溪記》 (7). They provide a period-matched test in two prose forms. The letter includes parallel description. A source unit ends at a sentence boundary or semicolon under the recorded segmentation policy. Original units, edition revisions, rights, attribution and scope are in the Gilbreth manifests. The six training extracts or complete works were selected for coverage, so the observed frequency of a pattern does not estimate its prevalence in classical prose. [Wang’s letter](https://zh.wikisource.org/wiki/Special:PermanentLink/1975451) · [Yuan’s record](https://zh.wikisource.org/wiki/Special:PermanentLink/1976651)

One GPT editorial reader rated written 音律美 from the Chinese text in its original order. Each of the 151 new ratings includes a quoted span and a reason. IDs and supplied source metadata were masked. The original signatures and recognizable wording were visible. The reader saw neither split assignments nor predictions. All three packets were frozen before fitting. The study used the previous marker rules, historical lexicons, ridge penalty and raw predictions. Its primary error is the average absolute difference from the frozen written scores, averaging the two works equally. The archive includes both sets of predictions, fitted weights and 199 draws for each of the two previous shuffle controls.

The selected examples include 歐陽修’s 「其容清明，天高日晶」「其氣慄冽，砭人肌骨」「其意蕭條，山川寂寥」, where each unit starts with 其 and divides into two four-character members. 謝惠連 uses a different construction in 「酌湘吳之醇酎，御狐貉之兼衣」「對庭鵾之雙舞，瞻雲鴈之孤飛」「踐霜雪之交積，憐枝葉之相違」. Both halves place 之 in the same position while the surrounding words change. [《秋聲賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/2371985) · [《雪賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/8729816)

**Measured training coverage.** The archive contains 129 new training units and their frozen scores. One unit, 歐陽修’s O26 「嗟乎！」, also occurs in the earlier Song test (王安石 D02). It opens its source paragraph. Excluding it from the fit preserved all test units and the original adjacency of the other training lines. The fit used 337 units across seven works. Whole-line frame support rose from zero to 22 units across five works. Three-line runs rose from zero to 18 units across four works, nine from 孫綽 alone. Aligned member matches rose from 8 to 49 units. The fitted score distribution was 27 fours, 100 fives, 160 sixes and 50 sevens. Scores 1–3 remain unrepresented.

| Test, raw mean absolute error | Units | Always 6 | Original model with grammar | Expanded model without grammar | Expanded model with grammar |
|---|---:|---:|---:|---:|---:|
| 王維《山中與裴迪秀才書》 | 15 | 0.667 | 0.655 | 0.686 | 0.689 |
| 元結《右溪記》 | 7 | 0.714 | 0.963 | 0.835 | 0.835 |
| **Fresh Tang, equal weight per work** | **22** | **0.690** | **0.809** | **0.761** | **0.762** |
| Fresh Tang, equal weight per unit | 22 | 0.682 | 0.753 | 0.734 | 0.735 |
| Earlier Northern Song, equal weight per work | 74 | 0.704 | 0.987 | 0.727 | 0.734 |
| Earlier Northern Song, equal weight per unit | 74 | 0.730 | 0.867 | 0.668 | 0.683 |

**What transferred.** The expanded grammar model moved closer to the frozen reading of 《右溪記》 and farther from the reading of Wang’s letter. It improved on the original fit across the two works on average. Refitting the context model without the three grammatical features performed just as well. The detector found a partial match on two of the 22 fresh units, and found zero whole-line matches and zero three-line runs. These two texts test performance on ordinary held-out prose and leave the value of the newly learned whole-line and three-line features unresolved. On the secondary Song set, the expanded grammar model beat always-6 on three of four individual works. The large miss on the fourth, 王安石’s work (0.909 versus 0.600), left always-6 ahead on the predefined equal-work metric. Weighting lines equally would reverse that secondary comparison.

**Shuffled controls.** On the fresh pair, only 17 of 199 within-section line-order shuffles equaled or improved the expanded model’s observed error of 0.762 (median shuffled 0.797). This control moves contextual rhyme and structure along with grammar. Shuffling character positions for the grammatical features alone gave a median error of 0.762, with all 199 draws equaling or improving the observed error. On the earlier Song set the corresponding counts were 92 and 199. These draws share the same works and labels.

**Supplementary test on passages with detected patterns.** After seeing zero whole-line matches in the fresh Tang pair, we withheld each of the six historical training works in turn, fitting on 《拉法叶赋》 and the other five. Each test score came from a model fitted without that work or author. Scores and feature definitions were frozen. These passages were originally selected for training, several specifically for their patterns. This post-hoc comparison therefore answers a narrower question than the two-work external test.

| Held-out units within the six additions | Units | Eligible works | Always 6 | Without grammar | With grammar |
|---|---:|---:|---:|---:|---:|
| All | 128 | 6 | 0.510 | 0.689 | 0.670 |
| In a repeated whole-line frame | 22 | 5 | 0.572 | 0.781 | 0.740 |
| In a run of at least three | 18 | 4 | 0.528 | 0.907 | 0.864 |

On whole-line matches, adding grammar moved the score closer to the written judgment in four of five work averages. The improvement was about 0.04 points on both patterned subsets. Always predicting 6 was closer on average in both. The mean editorial ratings on the two subsets were 5.96 and 6.14, respectively, giving each eligible work equal weight. The three-line subset is contained within the whole-line subset. Gilbreth Slurm job 12495739 ran the six folds. Fold results (`$SHUNKOU_ROOT/results/grammatical-training-expansion-20261122/results/within-training-work-holdout.json`)

**Previously seen design example.** The identical forecasts for 白居易’s 「葉如桂，冬青」「華如橘，春榮」「實如丹，夏熟」 rose from 4.249 to 5.478 (rounded 4 to 5). The frozen editorial score was 6 on each. The expanded context model without the grammar features gave each 5.406. The change specifically attributable to including grammar in these two expanded fits was therefore about 0.072 points per unit. This passage guided the original rule design and cannot establish transfer. Saved predictions (`$SHUNKOU_ROOT/results/grammatical-training-expansion-20261122/results/development-anchor.json`)

**Scope.** The improvement in agreement belongs to the broader written training set as a whole. A future test of three-line constructions needs separate, previously unscored authors with independently identified examples and neighboring ordinary prose. Written GPT judgments from a single reader supply the target here. Heard 音律美 and first-read ease (顺口) retain their separate final-stage participant protocols. Gilbreth Slurm job 12495640 completed on gilbreth-h009. Fresh line-by-line results (`$SHUNKOU_ROOT/results/grammatical-training-expansion-20261122/results/reading-comparison.txt`) · All comparisons (`$SHUNKOU_ROOT/results/grammatical-training-expansion-20261122/results/summary.txt`) · [Reproduction](../hpc/README.md#expanded-grammatical-pattern-training)

### Fresh parallel prose with verified three-line constructions

**Question.** Does the frozen 337-unit model come closer to a written 音律美 reading on a fresh passage when it uses its three grammatical features? The earlier external Tang pair contained zero whole-line matches. For this targeted challenge, selection used grammatical evidence from the original text before any new scores or predictions. The primary comparison covers the unique units in confirmed consecutive runs across three historical works. A separate comparison restricts the question to the two parallel argumentative essays (骈体论说). The third work is a parallel rhapsody (骈赋). Each historical period also has an ordinary prose comparison chosen for period and source coverage before feature inspection.

| Period and parallel witness | Confirmed units / excerpt | Ordinary prose comparison | Extent |
|---|---:|---|---:|
| Western Jin, 成公綏《嘯賦》 | 4 / 17 | 陳壽《三國志·華佗傳》, three consecutive narratives | 12 |
| Southern Qi to early Liang, 劉勰《文心雕龍·詔策》 | 4 / 16 | 沈約《宋書·戴顒傳》, its opening two paragraphs | 10 |
| Early Liang, 劉峻《辯命論》 | 3 / 17 | 阮孝緒《七錄序》, a paragraph on bibliographical history | 7 |

The Western Jin pair uses the composition period of the works. 《華佗傳》 recounts earlier events. Shen Yue records submission of the biographies in 488, and Ruan Xiaoxu dates the start of his compilation project to 523. Matching is by literary period, with independent authors, genres and topics. All six passages are fresh to the written scoring tests. Other chapters by 劉勰 had supplied past historical or acoustic research material. Source cards record the exact digital edition, attribution, rights and paragraph hashes. [成公綏](https://zh.wikisource.org/w/index.php?oldid=2005025) · [陳壽](https://zh.wikisource.org/wiki/Special:PermanentLink/10048966) · [劉勰](https://zh.wikisource.org/w/index.php?oldid=2098044) · [沈約](https://zh.wikisource.org/wiki/Special:PermanentLink/1962755) · [沈約’s dating evidence](https://zh.wikisource.org/wiki/Special:PermanentLink/2083420) · [劉峻](https://zh.wikisource.org/w/index.php?oldid=48434) · [阮孝緒](https://zh.wikisource.org/wiki/Special:PermanentLink/2228794)

**What counted as a run.** The Liu Xie passage describes kinds of imperial writing in the argumentative text, before the closing 贊. Four units begin with a four-character description. The second member starts with 則 and links a natural image to a quality through 之, as in 「則氣含風雨之潤」 and 「則筆吐星漢之華」. Liu Jun links three successive perceptions to three inferences through 「聞……謂……」「視……謂……」「見……謂……」. A longer preceding unit introduces the same argument, but its extra material breaks the detector’s fixed pattern. Chenggong Sui puts 而 fourth in each six-character member, twice per unit across four consecutive units. Each accepted three-unit window has two consecutive whole-line matches under the original rule and a documented grammatical reading. Overlapping windows contribute each original unit once. [《詔策》](https://zh.wikisource.org/w/index.php?oldid=2098044) · [《辯命論》](https://zh.wikisource.org/w/index.php?oldid=48434) · [《嘯賦》](https://zh.wikisource.org/w/index.php?oldid=2005025)

**Design.** All 79 units passed the screen against the 337-unit reference and previous written holdouts. Original paragraph boundaries and punctuation were kept. The model loaded the archived coefficients, training means, scales and historical dictionaries. The two text models share context features for line structure and historical rhyme. The grammar version adds whole-line frame matches, aligned member coverage and three-line runs. Always-6 is a third forecast on exactly the same units. A single GPT reader received all six passages in mixed work order with their internal text order intact. The packet hid source metadata, genre assignments, detector decisions and model predictions. Recognizable words remained visible. Each complete unit received a frozen holistic 1–7 judgment with an exact Chinese quotation and explanation. The endpoint is raw mean absolute error, first averaged within each work, then equally over works. Both controls use the same original unit IDs throughout 199 fixed-seed draws.

**Established results for the selected witnesses.** The table gives mean absolute error in points on the written 1–7 scale. Lower is closer to the frozen editorial reading. Every row uses the same units for all three forecasts. Rows overlap.

| Scored units | Units | Works | Always 6 | Without grammar | With grammar |
|---|---:|---:|---:|---:|---:|
| Confirmed runs in strict parallel prose | 7 | 2 | 0.125 | 0.414 | 0.426 |
| Confirmed runs including the parallel fu | 11 | 3 | 0.167 | 0.368 | 0.384 |
| Full excerpts of strict parallel prose | 33 | 2 | 0.607 | 0.654 | 0.657 |
| Full parallel excerpts including the fu | 50 | 3 | 0.542 | 0.582 | 0.598 |
| Period-matched ordinary prose | 29 | 3 | 0.870 | 0.799 | 0.800 |
| All fresh excerpts | 79 | 6 | 0.706 | 0.690 | 0.699 |

| Confirmed run by author | Written scores, source order | Always 6 | Without grammar | With grammar |
|---|---|---:|---:|---:|
| 劉勰《詔策》 | 6, 6, 7, 6 | 0.250 | 0.739 | 0.472 |
| 劉峻《辯命論》 | 6, 6, 6 | 0.000 | 0.089 | 0.379 |
| 成公綏《嘯賦》 | 6, 6, 7, 6 | 0.250 | 0.276 | 0.300 |

**Why the direction changed across works.** Adding grammar raised the prediction for each of the eleven run units. In 《詔策》 the context model scored all four below 6. The grammar fit moved them toward the editorial reading. For 「治戎燮伐，則聲有洊雷之威」, scored 7, the forecast rose from 5.62 to 5.92. The reader singled out the turn from the previous line’s celestial brightness to the sound of thunder. In 《辯命論》 the context model already assigned 6.02–6.19 to three units rated 6. Adding grammar raised them to 6.30–6.49, increasing each error. In 《嘯賦》 the grammar fit helped the unit rated 7 and increased absolute error on each of the three units rated 6. A constant forecast performed well because this reader gave 6 to nine of eleven run units. Across the full six excerpts the scores ranged from 4 to 7. These observations describe one reader and three deliberately selected constructions.

**Controls and interpretation.** On the 11 confirmed units, 29 of 199 section-order shuffles matched or beat the authentic combined-model error (median shuffled 0.486). This control changes both contextual and grammatical predictors. In the grammar-only position shuffle, 151 of 199 matched or beat the authentic error (median 0.373). On the seven strict-prose run units, the corresponding counts were 69 and 148. The original sequence was selected for having confirmed matches, so these comparisons describe sensitivity to perturbations and do not measure significance across the genre. The small advantage from the earlier within-training comparison failed to replicate on these new authors. The prototype identifies grammatical correspondences, but the data give no support for automatically awarding a higher written 音律美 score every time a pattern recurs. First-read ease (顺口) and heard 音律美 retain separate participant protocols for the final stage.

Gilbreth Slurm job 12496108 completed on gilbreth-h008. The archive includes the frozen reader packet and verdict, the eligibility screen, exact model and dictionary hashes, line-level forecasts, and shuffle summaries. Original Chinese, editorial reasons and forecasts (`$SHUNKOU_ROOT/results/fresh-three-line-transfer-20261122/results/reading-comparison.txt`) · Full results (`$SHUNKOU_ROOT/results/fresh-three-line-transfer-20261122/results/results.json`) · [Reproduce on Gilbreth](../hpc/README.md#fresh-three-line-challenge)

### Does a change at the end of a pattern distinguish a written 7 from a 6?

**Question.** Repetition alone pushed the forecast up on every patterned unit in the previous test. Here the unit of interest is the *end* of a grammatical series. The score is still the holistic written 音律美 judgment for the complete original sentence or semicolon-delimited unit that contains that ending.

**Selection and prediction blinding.** Source editors chose fresh authors and intact paragraphs, recorded at least three adjacent comparable arms, and explained where each series ended. The first six works contributed 174 source units and 14 distinct run endings. None of those endpoints duplicated a unit in the previous written training or evaluation sets. The opening of 杜牧’s collection preface includes narrative as well as parallel criticism. 李世民’s and 盧照鄰’s source editions had previously been used in non-editorial timing or historical-feature studies. The present freshness claim concerns the written score. One 盧照鄰 unit explicitly lacks twelve characters and was left unscored.

| Initially selected source | Source units | Run endings |
|---|---:|---:|
| [鮑照《登大雷岸與妹書》](https://zh.wikisource.org/wiki/Special:PermanentLink/2458769) | 13 | 2 |
| [江淹《獄中上建平王書》](https://zh.wikisource.org/wiki/Special:PermanentLink/47755) | 17 | 1 |
| [王融《三月三日曲水詩序》](https://zh.wikisource.org/wiki/Special:PermanentLink/48704) | 42 | 5 |
| [杜牧《李賀集序》](https://zh.wikisource.org/wiki/Special:PermanentLink/2646714) | 31 | 2 |
| [李世民《大唐三藏聖教序》](https://zh.wikisource.org/wiki/Special:PermanentLink/7902383) | 29 | 1 |
| [盧照鄰《南陽公集序》](https://zh.wikisource.org/wiki/Special:PermanentLink/8730572) | 42 | 3 |

**Two fixed change signals.** The rhythm signal counts Han characters in each punctuation group of a rhetorical arm. It fires when the terminal grouping is new within the run and the last change exceeds the median change between earlier neighbors. The wording signal fires when the last arm abandons the first or last character shared by its two immediate predecessors, or introduces a prespecified discourse cue at the opening. For example, 「一處所／一物候／一日夕／一觴一飯」 lengthens the last arm while keeping 一 in the opening position. In 杜牧’s more elaborate series ending 「不足為其虛荒誕幻也」, the previous arm already has the longer shape, so the detector gives no rhythm bonus at the terminal unit. These are text measures. Performed timing and broader changes of image or meaning require different evidence. [杜牧’s text](https://zh.wikisource.org/wiki/Special:PermanentLink/2646714)

The model adjustment was fixed before any editorial scores or predictions. Each flagged family adds 0.25 points to the archived expanded grammar model, for at most 0.50. Forecasts are bounded to 1–7. Rhythm-only and wording-only adjustments use the same weights. The primary test asks how often a unit rated 7 outranks an ending rated 6 **from the same work**. Ties get half credit and eligible works receive equal weight. A work with only one of the two ratings supplies no such contrast. Secondary checks include pooled ranking, the number of sevens called at the 6.5 threshold, error across all endings, and the subset where the pattern reaches the end of the original scoring unit. Score-6/7 filtering applies only to their specific comparison.

**Checking that wording could actually be tested.** The first six works had two rhythm flags and zero wording flags. Before inspecting any rating, the project retained those works intact and added four independently authored works chosen to supply an observable wording change. Their 81 units contained twelve endpoints. This second stratum deliberately favors examples with the proposed feature. It cannot estimate how often such changes occur in 骈文. All eligible series in the chosen paragraphs were annotated, including unchanged endings. One unresolved glyph in the 李商隱 edition was left unscored. The combined study therefore contains 255 original units, two visibly incomplete units and 26 distinct scored endpoints. The pre-rating overlap check admitted all 26. The first six works were delivered to the reader as one anonymous packet and the four additions as a second. The reader saw the original Chinese and paragraph order, with work metadata, run markings, feature values and forecasts hidden.

| Additional source | Source units | Run endings | Basis for including the work |
|---|---:|---:|---|
| [陳琳《為袁紹檄豫州》](https://zh.wikisource.org/wiki/Special:PermanentLink/7428891) | 9 | 3 | A causal chain repeats 事 as a result and the next premise, then arrives at 功. |
| [曹植《求自試表》](https://zh.wikisource.org/wiki/Special:PermanentLink/307847) | 16 | 2 | A third paired statement about father and ruler opens with 故 and lengthens both arms. |
| [李商隱《為滎陽公謝賜冬衣狀》](https://zh.wikisource.org/wiki/Special:PermanentLink/1979089) | 15 | 3 | An inventory lists two articles counted in 副, then a written order counted in 通. |
| [杜佑《省官議》](https://zh.wikisource.org/wiki/Special:PermanentLink/1972679) | 41 | 4 | The last comparison moves from named officers to military organization. Its two preceding names begin with 伯. A narrower reading ends the personal series one unit earlier. |

In the combined sample, nineteen endpoints triggered neither flag, three triggered rhythm alone, one wording alone and three both. The wording flag responds to an argument’s turn, a classifier change or recurring initials in personal names under the same literal rule. Separate results exclude both mixed compositions (杜牧 and 杜佑), and another sensitivity check keeps only run endings that coincide with the end of the whole scored unit. Two wording-positive runs finish their entire unit in the 陳琳/曹植 supplement, while the other three endings from those two works occur inside an original unit. Among these two authors, terminal position and the wording signal are confounded.

**Measured results on Gilbreth.** The independent reader assigned seven 7s, twelve 6s, four 5s and three 4s to the 26 target units. Five works supplied both a 7 and a 6, yielding nine within-work comparisons. All nine retained their original forecast ordering after the proposed adjustment. A constant forecast ties every pair. In the table, the ranking statistic gives a tie half credit and each eligible work equal weight. For absolute error, lower is better.

| Forecast | Within-work 7/6 ranking | Pooled 7/6 ranking (84 pairs) | Error on all 26 endpoints | Error on 6/7 endpoints |
|---|---:|---:|---:|---:|
| Always 6 | 0.500 | 0.500 | 0.632 | 0.324 |
| Current expanded model | 0.500 | 0.381 | 0.803 | 0.571 |
| Add rhythm change only | 0.500 | 0.369 | 0.769 | 0.503 |
| Add wording change only | 0.500 | 0.369 | 0.794 | 0.531 |
| Add both | 0.500 | 0.405 | 0.785 | 0.524 |

At the preset threshold of 6.5, all three main methods called zero of the seven editorial 7s and raised zero false alarms among the twelve 6s. The unrounded scores still allow a ranking test below that threshold. In a descriptive check using only the observed change flags, without a baseline score, within-work concordance was 0.450 for rhythm, 0.500 for wording and 0.450 for the number of flags.

| Evaluation subset | Endings | Eligible works / within-work pairs | Within-work ranking, current → add both | Absolute error, always 6 / current / add both |
|---|---:|---:|---:|---|
| Six initially selected works | 14 | 2 / 5 | 0.500 → 0.500 | 0.539 / 0.764 / 0.729 |
| Four works added for wording coverage | 12 | 3 / 4 | 0.500 → 0.500 | 0.771 / 0.860 / 0.868 |
| Run reaches the full unit’s end | 16 | 2 / 3 | 0.500 → 0.500 | 0.600 / 0.743 / 0.724 |
| Exclude both mixed compositions | 20 | 5 / 9 | 0.500 → 0.500 | 0.508 / 0.689 / 0.686 |

**Interpretation from the lines.** 陳琳’s repeated 事 serves twice, first as the result and then as the premise for 「然後立非常之功」. The reader gave the concluding unit 7 and cited the move from 有 to 立 and from 事 to 功. The wording adjustment raised its forecast from 5.78 to 6.03. 李商隱’s gift inventory also changes its ending, 「賜臣冬衣一副／大將衣四副／兼賜臣手詔一通」. That shift changes the classifier because the third object is a written order. The reader gave the containing unit 4 for its functional enumeration, and the combined adjustment moved the forecast farther away, from 5.55 to 6.05. In 杜牧, the lengthening to 「一觴一飯」 moved the forecast from 5.40 to 5.65 toward a 7. The reader also cited 「不覺出涕」 later in the same unit. These observations motivate a hypothesis about the role the ending plays in the larger sentence; they do not independently validate a semantic scoring rule. [陳琳](https://zh.wikisource.org/wiki/Special:PermanentLink/7428891) · [李商隱](https://zh.wikisource.org/wiki/Special:PermanentLink/1979089) · [杜牧](https://zh.wikisource.org/wiki/Special:PermanentLink/2646714)

**Controls and decision.** The combined rule gained zero on within-work ranking. In 999 draws, 890 restricted permutations of the bonuses among the 6/7 endings within mixed works achieved at least that gain. The counts were 729 when bonuses were permuted across all endings within each work and 999 when the roles of arms were shuffled inside the original runs. These are conditional perturbations of the same small sample. The data do not justify adding an automatic ending bonus to the current scorer. This test covered two narrow written signals and one editorial reading. Heard rhythm and first-read ease (顺口) retain their own participant protocols for the final stage. Gilbreth job 12496433 completed on gilbreth-h010. All 26 original endpoints, quotes, ratings and predictions (`$SHUNKOU_ROOT/results/pattern-ending-transfer-20261122/results/reading-comparison.txt`) · Full comparison and controls (`$SHUNKOU_ROOT/results/pattern-ending-transfer-20261122/results/results.json`) · [Reproduction](../hpc/README.md#ending-changes-in-parallel-prose)


## Argument conclusions and list endings

**Project hypothesis.** An ending that draws a consequence from preceding clauses may earn a higher written sound-pattern beauty (音律美) score than one that completes a catalogue. The previous experiment supplied the hypothesis. Its passages were excluded from this test. Each newly selected passage contains parallel prose (骈文). The selection favors sections with opportunities for both functions, so it cannot establish their frequency across the genre.

| Source and pinned edition | Passage | Original units | Eligible endings |
|---|---|---:|---:|
| [任昉《為蕭揚州薦士表》](https://zh.wikisource.org/w/index.php?oldid=47732) | Two paragraphs of a recommendation memorial | 16 | 7 |
| [顏延之《陶徵士誄》](https://zh.wikisource.org/w/index.php?oldid=1495368) | Two preface paragraphs, including two incomplete or transitional units | 23 | 9 |
| [陸機《豪士賦序》](https://zh.wikisource.org/w/index.php?oldid=48699) | Two paragraphs of the argumentative preface | 18 | 10 |
| [李康《運命論》](https://zh.wikisource.org/w/index.php?oldid=48427) | Second paragraph of the essay | 22 | 11 |
| [李白《春夜宴桃李園序》](https://zh.wikisource.org/w/index.php?oldid=7904990) | Complete banquet preface | 12 | 4 |
| [李華《弔古戰場文》](https://zh.wikisource.org/w/index.php?oldid=12612752) | Last two paragraphs of the rhymed lament in the 古文觀止 witness | 29 | 10 |
| [李清照《投翰林學士綦崈禮啟》](https://zh.wikisource.org/w/index.php?oldid=111628) | Closing address beginning 此蓋伏遇 | 19 | 3 |

**Method.** Curators recorded terminal quotations and at least two preceding textual anchors. Of 55 candidates, 54 ended their entire scored unit. 李清照’s 「人間第一」 closes a string of epithets, but the same unit continues with an allusion to 陸贄. The structural screen excluded that candidate before comparison. All seven authors and titles cleared the project's prior written benchmark checks. The archived witnesses and predictions support claims of freshness relative to those datasets.

Two separately prompted AI annotators saw the marked span and the surrounding Chinese, without the source cards, aesthetic rubric, predictions or each other’s decisions. Both had to agree on a pure argument conclusion or list closure for the primary test. An ending that combined roles or admitted competing readings could abstain. A third AI reader saw all 139 text units in source order, grouped by anonymous work and paragraph. It rated the 137 complete units under the existing 1–7 written rubric. No marked spans or role labels appeared in that packet. The three readings are separate model judgments and can share interpretive biases. Recognition of famous passages was possible.

The comparison was fixed before the aesthetic scores were inspected. It applied +0.25 to the frozen model’s score for an agreed argument and −0.25 for an agreed list, capping forecasts at 1 and 7. For each work, the primary comparison pairs a 7 with a 6 of the opposite role. A tie earns half credit. Each informative work gets equal weight. Secondary checks include same-role pairs, pooled cross-work rankings, error on the full range of observed ratings, both annotators individually and 999 shuffles within works.

**Measured results on Gilbreth.** The two AI annotators gave identical four-way roles to 51 of 54 endings (Cohen’s κ = 0.904). They agreed on 31 pure argument endings and 13 pure list endings. They agreed on a mixed role once and an uncertain role six times, and differed on three. Of the 31 arguments, seven received a written 7, fourteen a 6, eight a 5 and two a 4. Of the 13 list endings, five received a 7 and eight a 6. The ten abstentions remained in the all-ending error calculation. These proportions describe a deliberately selected sample.

| Forecast | Opposite-role 7/6 ranking within work | Any-role 7/6 ranking within work | Mean absolute error on all 54 endings |
|---|---:|---:|---:|
| Always give 6 | 0.500 | 0.500 | **0.585** |
| Frozen current model | **0.750** | **0.667** | 0.655 |
| Current plus ending function | 0.458 | 0.483 | 0.682 |

All three columns give works equal weight. The primary comparison contains 22 pairs from six informative works. Among these pairs the argument received the 7 ten times and the list twelve times. A rule using only the role ranked 0.417 with equal work weights. The frozen model ordered 18/22 pairs correctly when every pair counted equally. Adding function repaired four errors, spoiled eleven correct orderings, and preserved seven, leaving 11/22 correct. The broader within-work comparison included 35 pairs. Across all 54 endings, the single reader awarded fourteen 7s. Every forecast stayed below the 6.5 cutoff. Ranking relative strength and assigning the correct top score therefore give different pictures of model performance.

| Work | Opposite-role 7/6 pairs | Argument received 7 | Current ranking | With function |
|---|---:|---:|---:|---:|
| 任昉 | 4 | 0 | 1.000 | 0.250 |
| 顏延之 | 3 | 1 | 0.667 | 0.333 |
| 陸機 | 2 | 2 | 0.000 | 1.000 |
| 李康 | 6 | 1 | 0.833 | 0.167 |
| 李白 | 1 | 0 | 1.000 | 0.000 |
| 李華 | 6 | 6 | 1.000 | 1.000 |
| 李清照 | 0 | — | — | — |

**Controls.** Across 999 within-work shuffles of the role signals, 881 matched or exceeded the observed change of −0.292. The shuffled median change was −0.111. The one-sided permutation estimate for an improvement was 0.882. It is a check of the proposed positive direction, and supplies no test of a general penalty. Pooling authors gave 126 cross-role pairs and a ranking of 0.690 for the current model and 0.468 with the adjustment. Using the first annotator alone reproduced the primary result. Using the second admitted 47 pure endings and 25 pairs, moving the comparison from 0.764 to 0.486. In the 44 consensus-pure endings, mean absolute error with works equally weighted was 0.596 for always 6, 0.678 for current and 0.710 with function.

**Interpretation from the writing.** In 任昉, 「故以暉映先達，領袖後進」 resolves earlier praise and its full unit received 6. The following list ends with 「室邇人曠，物踈道親」 and received 7. The two four-character clauses turn twice on distance and closeness. The frozen scores put the passages in the reader’s order (5.88 and 6.14). Adding the roles reversed it (6.13 and 5.89). 陸機 gives the opposite example. The reader gave 7 to the unit ending 「豈不謬哉！」 and cited the preceding expansion into opposing images of river and mountain, followed by the abrupt question. The rule correctly raised that unit from 5.85 to 6.10 while lowering the 6-rated list ending 「暗成敗之有會」 from 6.04 to 5.79. Whether an ending makes an inference is reproducibly annotatable here, but neither role carries a reliable fixed preference in the written rubric. [任昉](https://zh.wikisource.org/w/index.php?oldid=47732) · [陸機](https://zh.wikisource.org/w/index.php?oldid=48699)

**Decision.** Keep ending function available for commentary and retain the current numerical weights. This experiment measures one AI close reader’s response to written cadence. Heard 音律美 and first-read ease (顺口) still require their respective final-stage participant tests. Gilbreth Slurm job 12496692 completed on gilbreth-h007 with exit code 0. All 54 original endings with ratings and forecasts (`$SHUNKOU_ROOT/results/ending-function-transfer-20261122/results/reading-comparison.txt`) · Full results and controls (`$SHUNKOU_ROOT/results/ending-function-transfer-20261122/results/results.json`) · [Reproduce on Gilbreth](../hpc/README.md#argument-conclusions-and-list-endings-in-parallel-prose)


## Calibrating the decision to report a written 7

**Project hypothesis.** The current grammar-and-context model may recognize some exceptional written cadence (音律美) below its original 6.5 reporting threshold. This test changes only the decision to flag a 7. All base predictions, coefficients, historical dictionaries and rankings stay fixed. The comparison uses the original cutoff and always giving 6 on identical units.

**Operating rule.** For this pilot we chose a maximum false-7 rate of one in five among the reader's 6s, both pooled across units and averaged equally across works. We froze this choice before checking fresh scores. On earlier works the procedure maximizes work-balanced recall of true 7s within both limits. Ties favor a lower work-balanced and then pooled false-six rate, then the existing cutoff, then the more conservative cutoff. Equal model scores move together. A no-call candidate is eligible. On fresh works the prespecified pass also requires both more 7s caught and higher work-balanced recall than the current model. Lower-rated false positives and precision are secondary outcomes. Precision counts every false 7, including ratings 1–5.

**Development data.** The two preceding experiments supplied 394 original units from 17 works by separate authors. All 390 complete units entered calibration, including context units outside the former endpoint tests. The four exclusions were incomplete units. The fit used none of the fresh editorial labels. The earlier selection produced the inclusive cutoff **5.990074700458586**. It caught 12 of 51 earlier sevens, promoted 37 of 204 sixes and promoted 21 of 135 lower scores. The corresponding work-balanced recall and false-six rate were 25.9% and 19.0%. The code and model hashes, earlier predictions, and chosen cutoff were sealed on Gilbreth. Each earlier work also had a separate prediction round in which its cutoff was fitted on the other sixteen works.

**Fresh written reference.** The six credited authors and titles cleared the prior written corpora. The source check covered 962 distinct normalized prior units. Curators chose intact short works or continuous passages before aesthetic ratings. A separately prompted AI reader scored every complete unit in the original within-work order under the existing seven-point rubric. Its packet hid titles, credited authors, predictions and operating cutoffs. A reader could still recognize a work. These are editorial reference judgments. No participant took a listening or read-aloud test.

| Fresh primary source | Selected passage | Source units |
|---|---|---:|
| [傅亮《爲宋公至洛陽謁五陵表》](https://zh.wikisource.org/w/index.php?oldid=2458768) | Complete memorial written on behalf of 劉裕 | 18 |
| [何遜《爲衡山侯與婦書》](https://zh.wikisource.org/w/index.php?oldid=2228875) | Complete letter | 13 |
| [沈炯《經通天臺奏漢武帝表》](https://zh.wikisource.org/w/index.php?oldid=2458745) | Complete memorial | 20 |
| [王棨《江南春賦》](https://zh.wikisource.org/w/index.php?oldid=496211) | Opening of a parallel rhapsody (駢賦) | 17 |
| [溫庭筠《謝襄州李尚書啟》](https://zh.wikisource.org/w/index.php?oldid=1976248) | Complete letter, including the salutation | 13 |
| [汪藻《皇太后布告天下手書》](https://zh.wikisource.org/w/index.php?oldid=1860886) | Closing passage of a proclamation | 14 |

On Gilbreth, the project retrieved all six pinned primary-source revisions from Wikisource. Every selected paragraph matched the archived text in its revision, including punctuation after page-layout whitespace was removed. The archive retains the revision responses and paragraph hashes. The 汪藻 edition identifies its initial punctuation as machine-generated, which can affect unit boundaries and features. The results below include a sensitivity check that omits each fresh work in turn.

**Measured results.** Gilbreth evaluated all 95 fresh units. The six works supplied 13 reference 7s, 43 reference 6s and 39 lower ratings. Lowering the cutoff recovered five additional 7s, but the proportion of 6s promoted to 7 exceeded 20% both pooled (27.9%) and with works equally weighted (28.4%). The cutoff failed the prespecified fresh test.

| Top-score rule | Fresh editorial 7s caught | Editorial 6s promoted | Lower ratings promoted | Precision among 7 calls |
|---|---:|---:|---:|---:|
| Always give 6 | 0/13 | 0/43 | 0/39 | Undefined, no calls |
| Current cutoff 6.5 | 0/13 | 0/43 | 0/39 | Undefined, no calls |
| Earlier-work cutoff 5.990074700458586 | 5/13 (38.5%) | 12/43 (27.9%) | 15/39 (38.5%) | 5/32 (15.6%) |

| Fresh author | Units | 7s caught | 6s promoted | Lower ratings promoted |
|---|---:|---:|---:|---:|
| 傅亮 | 18 | 1/1 | 1/6 | 2/11 |
| 何遜 | 13 | 2/3 | 3/7 | 2/3 |
| 沈炯 | 20 | 1/2 | 3/9 | 4/9 |
| 王棨 | 17 | 0/4 | 1/9 | 1/4 |
| 溫庭筠 | 13 | 0/1 | 1/6 | 2/6 |
| 汪藻 | 14 | 1/2 | 3/6 | 4/6 |

**Earlier cross-validation and controls.** With each earlier work withheld from its own calibration, the adjusted rule caught 13/51 earlier 7s, promoted 38/204 sixes, and promoted 21/135 lower ratings. Equal-work recall was 27.1% and the equal-work false-six rate was 19.5%. The 17 fold cutoffs ranged from 5.9545 to 6.0067. The original rule in those same 17 held-out folds called one earlier 6 a 7 and found no 7s. Always giving 6 made no calls. On fresh works, omitting any one author still left the pooled false-six rate between 24.3% and 32.4% and its equal-work counterpart between 24.1% and 31.9%. This includes omitting the machine-punctuated proclamation. The observed fresh equal-work recall was 44.4%. The median was 33.3% when grades were shuffled within works and both forecasts held fixed. Of 999 draws, 254 reached or exceeded 44.4% (one-sided permutation estimate 0.255). Six fresh works and a single editorial reference limit generalization.

**Why a cutoff alone struggles.** Eleven fresh units shared the exact same model score of 6.101362964972654. The reader assigned them one 4, five 5s, one 6 and four 7s. Any threshold on this score must accept all eleven or reject all eleven. In 何遜 the reader gave 「鏡想分鸞，琴悲《別鶴》」 a 6 for its paired images and 「思等流波，終朝不息」 a 7 for how 不息 carries forward the preceding thought. The current model gave them the same score to full precision. Conversely, all four of 王棨’s editorial 7s stayed below the new cutoff, including 「麗日遲遲，江南春兮春已歸」 (model 5.240). A global shift can change the number of flags. It cannot resolve these ties. [何遜’s letter](https://zh.wikisource.org/w/index.php?oldid=2228875) · [王棨’s rhapsody](https://zh.wikisource.org/w/index.php?oldid=496211)

**Decision.** Retain the earlier-fit cutoff as an experimental result. The evidence does not support using it to assign 7 automatically. A further computational test can target the specific situations where the current features give identical predictions to passages with different editorial ratings, with new works reserved for evaluation. This experiment measured written 音律美. First-read ease (顺口) and listening judgments require distinct final-stage participant tasks. Gilbreth jobs 12496836 (fit) and 12496930 (test) completed successfully. All 95 original units and decisions (`$SHUNKOU_ROOT/results/top-score-calibration-20261122/results/reading-comparison.txt`) · Full results and controls (`$SHUNKOU_ROOT/results/top-score-calibration-20261122/results/results.json`) · [Reproduce on Gilbreth](../hpc/README.md#calibrating-the-decision-to-report-a-7)


## Does developing the preceding thought help distinguish a 7 from a 6?

**Measured cause of the earlier tie.** On Gilbreth, replaying the original Chinese in source order reproduced all 95 previous frozen forecasts exactly. All 11 passages at 6.101362964972654 had an identical vector of **16 observed raw features**. Each had two groups of four characters, perfectly balanced arms, and the same three measured 廣韻 level/oblique pattern values. Each had zero measured group-end and cross-line rhyme repetition under both 廣韻 and 平水韻, a shape match with a neighboring unit, zero positional character echo, and zero on all three grammatical-frame measures. These zeros describe what the particular detectors registered. Every input was present, every coefficient was nonzero, and no output was clipped. The equality was already present before imputation, standardization, weighting or display rounding. The 11 lines came from three works and spanned editorial grades 4 through 7. The two neighbor shape and positional-echo measures take the best match on either side, and the across-line rhyme measures pool neighbors. None of the 16 inputs encodes *what happens to the preceding thought*. Full per-passage and per-feature audit on Gilbreth (`$SHUNKOU_ROOT/results/adjacent-thought-transfer-20261122/tie-audit.json`)

**Fresh project hypothesis.** The second of two adjacent units may gain cadence by carrying an identifiable thought, situation or image forward. We tested an externally annotated feature before considering an automated score. Two independently prompted AI readers classified masked pairs as advancement, restatement, a coordinate or separate point, or uncertain. They quoted exact words in each unit and gave a textual warrant. Semantic advancement could include a consequence, extension, answer, reversal or concrete realization. Sharing a topic or connective alone was insufficient. The aesthetic reader separately saw the complete passages in source order with author, title, target marks, annotations and forecasts hidden. It rated the original units for written 音律美 under the established 1–7 rubric. Recognition of individual classical texts and correlated model judgments remain possible.

The frozen test added 0.25 points to the current bounded forecast when both annotators marked advancement. Two restatement/coordinate judgments counted as consensus non-advancement. Disagreement or uncertainty received no adjustment and was excluded from the primary role contrast. The primary comparison matches an advance and a non-advance by the same author, one rated 7 and the other 6. Each informative work counts equally and a tie earns half credit. Secondary comparisons cover all agreed targets, all structurally eligible targets, both annotators separately, original exact-score ties, absolute error and the 6.5 top-score threshold. The negative controls use 999 within-work shuffles of the advance signal and a masked comparison of true versus more distant predecessors for the same targets. No sentences from the preceding calibration study entered the fresh test.

**Fresh sources.** Gilbreth verified the characters and punctuation for all seven selected paragraph spans directly against their pinned primary-source revisions. The six works contributed 72 complete units. Seven paragraph openings supplied context. The other 65 had an immediately preceding complete unit in the same paragraph and all cleared the prior-text screen. Twelve decoys gave two randomly selected targets per work a more distant predecessor in the same paragraph. In the sources below, the opening of 文天祥’s piece identifies him and two other works contain given names. Source anonymity therefore depended on the text. The digital reading 「陛古」 in 常袞 was retained.

| Credited author and pinned text | Scope | Units / authentic adjacent targets |
|---|---|---:|
| [羊祜《讓開府表》](https://zh.wikisource.org/w/index.php?oldid=47670) | Complete opening paragraph | 11 / 10 |
| [謝朓《辭隨王子隆牋》](https://zh.wikisource.org/w/index.php?oldid=1962711) | Two contiguous paragraphs after the salutation | 15 / 13 |
| [祖鴻勳《與陽休之書》](https://zh.wikisource.org/w/index.php?oldid=2004505) | Complete opening paragraph | 10 / 9 |
| [陸贄《奉天改元大赦制》](https://zh.wikisource.org/w/index.php?oldid=8735459) | First twelve complete units of the opening paragraph | 12 / 11 |
| [常袞《久旱陳讓相表》](https://zh.wikisource.org/w/index.php?oldid=8735561) | Complete memorial | 12 / 11 |
| [文天祥《門謝表》](https://zh.wikisource.org/w/index.php?oldid=808097) | First twelve complete units | 12 / 11 |

**Measured fresh result.** The two relation readers chose exactly the same four-way category on 60/65 true pairs (unweighted Cohen’s κ = 0.850). They agreed on 42 advances, three restatements and fourteen coordinate/separate points. Six targets abstained under the numerical rule. The independent aesthetic reader gave the 65 target units ten 7s, thirty-five 6s, nineteen 5s and one 4. Seven of the 42 advances and two of the 17 agreed non-advances received 7. One abstention received 7.

| Ranking scope | Same-work 7/6 comparisons | Always give 6 | Frozen model | Add 0.25 for an agreed advance |
|---|---:|---:|---:|---:|
| Primary, one advance and one non-advance | 16 in 5 works | 0.500 | 0.367 | 0.433 |
| All pairs with agreed categories, including same-category pairs | 43 in 6 works | 0.500 | 0.586 | 0.600 |
| All true adjacent targets, including abstentions | 55 in 6 works | 0.500 | 0.534 | 0.567 |
| Exact same current score, one 7 and one 6 within a work | 0 | — | — | — |

The primary gain came from **one** corrected ordering in 常袞. The frozen model got six of sixteen pairs right and the adjustment got seven right. All six previously correct pairs remained correct. Averaging within each work and then across works yields the table. The role by itself ranked 0.600 when works counted equally, but the advance received the 7 in only eight of the sixteen individual comparisons. No fresh same-work 7 and 6 shared an exactly equal current score, even when including abstentions. Thus this sample assesses ordering among distinct forecasts and gives no fresh estimate of tie-breaking performance.

| Work | Primary pairs | Current | With advance |
|---|---:|---:|---:|
| 羊祜 | 6 | 0.333 | 0.333 |
| 謝朓 | 2 | 0.500 | 0.500 |
| 祖鴻勳 | 2 | 0.000 | 0.000 |
| 陸贄 | 0 | — | — |
| 常袞 | 3 | 0.000 | 0.333 |
| 文天祥 | 3 | 1.000 | 1.000 |

**Controls and sensitivity.** In 64 of 999 shuffles, with roles permuted among eligible 6/7 targets within each work, the primary ranking gain matched or exceeded the observed 0.067 (median 0, one-sided permutation estimate 0.065). Pooling all authors would give 110 cross-role pairs and a larger-looking ranking of 0.555 → 0.609. Those pairs answer a different question. With only the first relation reader, the primary result was 0.317 → 0.383 across 18 pairs in five works. With only the second reader, it was 0.444 → 0.528 across 25 pairs in six works. The comparison depends in part on which disputed cases enter it.

For the twelve targets paired twice, consensus advancement fell from 8/12 with the true predecessor to 5/12 with a more distant predecessor. Of the eight original advances, three stayed advances and five became ambiguous under the consensus rule. Two other targets became advances after substitution. A more distant sentence can still support a real connection. The control measures specificity to the adjacent sentence, not an expected score of zero for every substitute. At the existing 6.5 decision threshold, all three methods missed all ten 7s and made no false-7 calls. Mean absolute errors with works weighted equally were 0.472 for always 6, 0.5867 for current and 0.5869 with the feature.

**Interpretation from the Chinese.** In 常袞, 「臣尚以愚劣偷安廟堂」 admits the speaker’s failure. The next unit turns that admission into a petition, 「伏乞解臣所職，更擇良才」. The aesthetic reader gave the full unit 7, citing the matched 省 and 求 clauses, the turn at 則, and the closing 上 and 下 pair. The adjustment raised its forecast from 6.027 to 6.277, above the same work’s 6-rated 「變理之任，虧紊固多，邦畿之間，愆亢特甚」 (6.152). A different pattern appears in 羊祜. The unit ending 「則使勞臣不勸」 answers the preceding 「則使才臣不進」 with a coordinate second example. Both role readers saw a parallel, and the aesthetic reader still gave it a 7. A thought can stand beside its predecessor and make a strong rhythmic answer. [常袞’s memorial](https://zh.wikisource.org/w/index.php?oldid=8735561) · [羊祜’s memorial](https://zh.wikisource.org/w/index.php?oldid=47670)

**Decision.** Preserve the textual relation as an interpretable annotation. A gain of one primary pair, a ranking below the constant baseline on that comparison, and no fresh comparable exact ties give insufficient grounds for an automatic bonus. This comparison concerns a single AI reader’s written 音律美 ratings. First-read ease (顺口) and listening outcomes remain separate. Gilbreth jobs 12497121 (tie audit) and 12497229 (fresh test) completed successfully. The 65 original transitions with forecasts and judgments (`$SHUNKOU_ROOT/results/adjacent-thought-transfer-20261122/results/reading-comparison.txt`) · Full benchmark and controls (`$SHUNKOU_ROOT/results/adjacent-thought-transfer-20261122/results/results.json`) · [Reproduction](../hpc/README.md#identical-forecasts-and-development-of-the-preceding-thought)

## Can thought development break exact 7/6 ties?

**Project hypothesis.** When the current model gives two genuinely different passages the exact same score, development of the preceding thought may identify the stronger written cadence (音律美). The preceding fresh study supplied no same-work 7/6 pair with identical forecasts, so it could not answer the tie-breaking question. The eleven original tied examples and the rest of the earlier written corpora were held out of the new pool.

**Selection and blinding.** Curators selected new parallel prose (骈文) for sufficient stretches of paired clauses. Separate metrical verse sections were excluded. The current model scored complete source passages on Gilbreth. A target had to have a complete immediate predecessor in the same source paragraph. The screen excluded exact normalized target or predecessor text from earlier written studies, duplicate target texts in the pool, and previously used works or authors. Every eligible target that shared its full binary64 forecast with another eligible target in its own work entered the challenge. Ties were identified before assigning any new editorial or relation judgments. This selection supports a conclusion about tied passages, not about how often a 7 occurs in the genre.

The project fixed the targets, sources, exact scores and three anonymous reading packets on Gilbreth. One AI close reader saw the designated units in their original paragraph context and rated written cadence on the existing 1–7 scale. Two other AI readers independently classified the relationship between each target and its immediately preceding unit in randomly ordered pairs. Their choices were advance, restate, parallel or uncertain, each requiring specific evidence in both units. They saw neither scores nor tie groups. Source titles and author fields were masked, although recognizable words remained. The numerical intervention was unchanged from the preceding study: add 0.25 only for two advance judgments and cap the forecast at 7. Every other case, including disagreements, received zero adjustment.

**What counts as a successful resolution.** The primary test pairs every 7 with every 6 inside the same work and exact-score group. A correct resolution ranks the 7 higher. An incorrect resolution ranks the 6 higher. An unresolved tie receives half credit. The primary ranking averages pair accuracy within each informative work, then gives those works equal weight. Both unchanged forecasts and always giving 6 tie every comparison by construction. The results also report pooled counts, how many distinct targets supplied those comparisons, how often a broken tie was correct, individual-coder sensitivity, and 999 within-group shuffles. Pair counts can reuse the same passage and are not counts of independent works.

**Source screen.** The pool included 651 units from 22 works and independently credited authors. Of those, 48 opened a selected paragraph and four targets or predecessors repeated normalized text from an earlier written benchmark. That left 599 eligible targets. Exactly 62 targets in 21 same-work groups from 10 works qualified before rating. Sixteen groups had two members, with one group each of size 3, 4, 5, 6 and 12. The groups spanned twelve distinct numerical forecasts. Five pre-Tang works supplied 48 targets and five Tang works supplied 14. No Song work supplied a qualifying same-work group.

| Pinned primary source | Source units | Exact-tie targets |
|---|---:|---:|
| [孔稚珪《北山移文》](https://zh.wikisource.org/w/index.php?oldid=2693496) | 39 | 0 |
| [劉孝儀《北使還與永豐侯書》](https://zh.wikisource.org/w/index.php?oldid=2368827) | 14 | 5 |
| [伏知道《爲王寬與婦義安主書》](https://zh.wikisource.org/w/index.php?oldid=2458742) | 20 | 10 |
| [陳叔寶《與詹事江總書》](https://zh.wikisource.org/w/index.php?oldid=2011861) | 27 | 4 |
| [江總《爲陳六宮謝表》](https://zh.wikisource.org/w/index.php?oldid=2458743) | 11 | 0 |
| [周弘讓《復王少保書》](https://zh.wikisource.org/w/index.php?oldid=2458741) | 34 | 17 |
| [王褒《與周弘讓書》](https://zh.wikisource.org/w/index.php?oldid=519284) | 27 | 12 |
| [潘勗《冊魏公九錫文》](https://zh.wikisource.org/w/index.php?oldid=2307054) | 43 | 0 |
| [鍾會《檄蜀文》](https://zh.wikisource.org/w/index.php?oldid=1967185) | 31 | 0 |
| [李庾《兩都賦》](https://zh.wikisource.org/w/index.php?oldid=2692708) | 64 | 4 |
| [謝偃《塵賦》](https://zh.wikisource.org/w/index.php?oldid=1971585) | 35 | 0 |
| [蔣防《任公子釣魚賦》](https://zh.wikisource.org/w/index.php?oldid=1978227) | 35 | 2 |
| [仲子陵《清簟賦》](https://zh.wikisource.org/w/index.php?oldid=8376095) | 37 | 0 |
| [李程《日五色賦》](https://zh.wikisource.org/w/index.php?oldid=2132588) | 36 | 2 |
| [李德裕《劍池賦》](https://zh.wikisource.org/w/index.php?oldid=1977648) | 25 | 0 |
| [孫逖《簾賦》](https://zh.wikisource.org/w/index.php?oldid=1974999) | 24 | 0 |
| [岑勛《西京千福寺多寶佛塔感應碑》](https://zh.wikisource.org/w/index.php?oldid=2273034) | 36 | 4 |
| [王起《庭燎賦》](https://zh.wikisource.org/w/index.php?oldid=1979678) | 35 | 2 |
| [李誡《進新修營造法式序》](https://zh.wikisource.org/w/index.php?oldid=460817) | 25 | 0 |
| [司馬光《進書表》](https://zh.wikisource.org/w/index.php?oldid=2118053) | 19 | 0 |
| [孟元老《東京夢華錄序》](https://zh.wikisource.org/w/index.php?oldid=2503718) | 10 | 0 |
| [鄭樵《通志總序》](https://zh.wikisource.org/w/index.php?oldid=2432855) | 24 | 0 |

The pool includes parallel rhapsodies as well as letters, memorials, proclamations and parallel preface passages. Previous acoustic use of 孔稚珪’s text was documented in its source card. It contributed no tied targets. 王褒 and 周弘讓 were correspondents, so their letters may share conventions or wording. The counts of works do not imply equal stylistic independence. Source cards on Gilbreth (`$SHUNKOU_ROOT/results/exact-tie-targets-20261122/inputs/works.json`) · The sealed exact-score screen (`$SHUNKOU_ROOT/results/exact-tie-targets-20261122/screen/screen.json`)

**Measured result on Gilbreth.** All 48 selected source paragraphs were matched to their pinned revisions. The 62 targets generated 116 possible same-work pairs with equal forecasts. The independent reader assigned five 7s, thirty-one 6s, twenty-four 5s and two 4s. Each 7 occurred in a different numerical group within its work. In four of those groups the 7 was accompanied only by one or two 5s. **Exactly one same-work model tie contained both an editorial 7 and a 6.**

| Method | Informative 7/6 pairs | Correctly resolved | Incorrectly resolved | Still tied | Ordering score |
|---|---:|---:|---:|---:|---:|
| Always give 6 | 1 | 0 | 0 | 1 | 0.50 |
| Current model | 1 | 0 | 0 | 1 | 0.50 |
| Current plus 0.25 for agreed advancement | 1 | 0 | 0 | 1 | 0.50 |

All results in the table come from the same pair of targets in 伏知道. Half credit records a tie. Accuracy among resolved cases is undefined because none was resolved. The two role readers agreed exactly on 55/62 four-way classifications (Cohen’s κ = 0.825). They agreed on advancement in 27 targets and non-advancement in 23, with 12 abstentions under the rule. Overall agreement did not guarantee agreement on the informative pair.

**The two passages.** Both received the identical frozen model forecast **6.001927528386828**. In the passage the editorial reader rated 7, 「九重千日，詎憶倡家；單枕一宵，便如蕩子。」, the target is the second half. The reader cited the answering numbers 九／千 and 單／一, and the turn from 詎憶 to 便如. Both relation readers classified the second half as a coordinate contrast. In the 6-rated target, 「輕扇初開，欣看笑靨；」 follows 「人慚蕭史，相偶成仙。」. One relation reader saw the smile as a concrete development of the preceding union. The other found the link uncertain. Neither target received the consensus bonus. The aesthetic reader also noted the 6-rated unit’s relation to the *following* clause, a legitimate part of the full-context written rubric beyond the scope of the predecessor-only feature. [伏知道《爲王寬與婦義安主書》](https://zh.wikisource.org/w/index.php?oldid=2458742)

**Controls and limits.** The consensus-only and opposite-consensus subsets had zero 7/6 comparisons. Using the first role reader alone preserved the tie. Using the second alone raised the 6 above the 7. All 999 shuffles reproduced the zero work-balanced gain because there was no exchangeable mix of agreed advance and non-advance flags for the informative pair. Accordingly, its upper-tail estimate of 1.0 supplies no evidence for or against the literary hypothesis. In the separate cross-work descriptive check, three additional 7/6 pairs among the already selected targets had identical forecasts across different authors. One was resolved correctly, two stayed tied, and none was wrongly resolved. These comparisons do not control for author or genre. None of the three methods issued a 7 at the 6.5 cutoff on any of the 62 targets.

**Decision.** The fixed carry-forward bonus left the one informative same-work tie unresolved. The study establishes that exact forecast ties can be located prospectively, but the scarcity of ties with the required editorial grades prevents a reliable estimate of the feature’s performance. The scorer retains its existing weights. These results concern written 音律美 under one AI editorial reading. Listening and first-read ease (顺口) remain separate final-stage participant outcomes. Gilbreth jobs 12497588 (complete screen) and 12497658 (locked evaluation) completed successfully. Tied groups, original preceding lines, editorial ratings and decisions (`$SHUNKOU_ROOT/results/exact-tie-targets-20261122/results/reading-comparison.txt`) · Full results and controls (`$SHUNKOU_ROOT/results/exact-tie-targets-20261122/results/results.json`) · [Reproduce on Gilbreth](../hpc/README.md#targeting-exact-same-work-forecast-ties)

## Does an answer through contrast break an exact 7/6 tie?

**Project hypothesis.** A line that answers the preceding line by reversing an expectation or supplying a counterexample may deserve a higher written 音律美 score. The earlier 伏知道 example suggested this distinction and was excluded from the test. A contrast within a single line, an ordinary question and answer, and parallel descriptions of opposing objects were outside the proposed feature unless the target also answered the preceding thought.

**Screen and readers.** Gilbreth acquired 1,573 units from 54 edition-pinned works. The pool covered the prose genres in volumes 2–9 of 許槤's anthology, two further letters and six parallel rhapsodies. The standalone transcription of 《與周弘讓書》 could not be extracted by the source parser and was recorded separately; its author was already in the previous pool. After excluding earlier authors and works and retaining one work per new author, 12 fresh works supplied 816 units. The screen excluded 57 paragraph openings and one incomplete edge. Of 758 eligible targets, 162 belonged to 54 groups tied within work at the full binary64 precision of the frozen context-plus-grammar model. A seeded sample across works retained 95 targets in 33 groups from seven works. The selected targets, adjacent pairs, full source paragraphs and scores were sealed before the editorial reading. [Source anthology](https://zh.wikisource.org/wiki/Special:PermanentLink/2573077) · [Selection protocol and scoring rule](../research/contrast-answer.md)

One GPT editorial reader rated the written cadence on the existing 1–7 scale in paragraph context, with the tie groups, scores and relation decisions hidden. The reader knew the research question. The ratings were fifteen 7s, fifty-one 6s, twenty-six 5s and three 4s. On a Gilbreth A10, Qwen2.5-7B-Instruct separately classified each anonymous predecessor and target. Two Chinese prompts described the same relation with different wording and reversed the A/B answer order. Both had to classify the target as a contrasting answer for it to gain 0.25, capped at 7. The classifier saw no editorial ratings or prototype forecasts. [Pinned classifier](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/tree/a09a35458c702b33eeacc393d103063234e8bc28) · [Exact prompts and inference code](../src/contrast_answer_relation.py)

**Measured result on Gilbreth.** Eight exact-score groups across six works contained both a 7 and a 6. These supplied 13 comparisons involving 21 distinct passages. Each work contributed equal weight to the ordering score. An unresolved tie earns half credit.

| Method | 7 above 6 | 6 above 7 | Still tied | Work-weighted ordering |
|---|---:|---:|---:|---:|
| Always give 6 | 0 | 0 | 13 | 0.500 |
| Current model | 0 | 0 | 13 | 0.500 |
| Current model plus agreed contrasting answer | 0 | 0 | 13 | 0.500 |

| Primary source | Rated exact-tie targets | 7/6 comparisons |
|---|---:|---:|
| [何晏《景福殿賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/2004491) | 25 | 5 |
| [班固《西都賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/2395759) | 23 | 3 |
| [左思《蜀都賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/2551687) | 15 | 2 |
| [王延壽《魯靈光殿賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/2004308) | 14 | 1 |
| [楊暕《召王貞書》](https://zh.wikisource.org/wiki/Special:PermanentLink/1776396) | 8 | 1 |
| [郭璞《江賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/2248217) | 6 | 1 |
| [劉裕《與臧燾敕》](https://zh.wikisource.org/wiki/Special:PermanentLink/2458773) | 4 | 0 |

Twelve comparisons came from five parallel rhapsodies and one from a letter. The five further eligible works without a rated target were 木華《海賦》, 吳質《答東阿王書》, 元宏《與太子論彭城王詔》, 蕭賾《敕條制禁奢靡詔》 and 高洋《禁浮華詔》. These results have little coverage of ordinary correspondence and official prose.

**Reading the letter.** In 楊暕, the editor gave 「茂陵謝病，非無封禪之文」 a 6 and 「彭澤遺榮，先有《歸來》之作」 a 7. Both had a current forecast of 5.686211125086334. The first establishes the short-then-long shape. The second completes it, with 茂陵／彭澤 opening the two lines, 非無／先有 turning in the same position, and 之文／之作 closing them. The relation prompts split in opposite directions on these two targets. The editorial reading shows how a line can earn its effect by completing an allusive pair even when its status as a rebuttal is debatable. [Pinned original](https://zh.wikisource.org/wiki/Special:PermanentLink/1776396)

**Diagnostics and interpretation.** The two prompts agreed on 64 of 95 authentic pairs, including 63 joint negatives. Only one target received the bonus, 班固’s 「草木無餘，禽獸殄夷」 after 「松栢仆，叢林摧」. A close reading suggests an intensification of devastation. That target and both of its tied partners were rated 6. The first prompt alone resolved one primary comparison correctly and left 12 tied (work-weighted 0.583). The second alone resolved five correctly, inverted three and left five tied (0.517). Each used the same model. The prompt differences confound wording and answer order, and choosing a prompt by its retrospective performance would require a new holdout. Among 89 targets with a same-paragraph displaced predecessor, the consensus classifier flagged one true edge and two displaced edges. All three occurred on different targets. All 999 within-group shuffles yielded zero gain; the one consensus flag belonged to a group without a 7. Omitting any one informative work also left the primary ordering at 0.500. [Original hunting passage](https://zh.wikisource.org/wiki/Special:PermanentLink/2395759)

**Decision.** The agreement rule contributed no evidence for ranking an editorial 7 above a 6. The rarity of positive classifications and their weak specificity to the actual predecessor limit what this says about literary contrast itself. We retained the existing scorer. These are written editorial ratings. Listening and first-read ease (顺口) remain separate final-stage participant outcomes. Slurm jobs 12509017 (screen), 12509033 (GPU relation classification) and 12509208 (evaluation) completed with exit code zero. The private archive contains the source snapshots, sealed packets, model outputs and joined examples. All 95 original lines and decisions on Gilbreth (`$SHUNKOU_ROOT/results/contrast-answer-20261123/results/readings.txt`) · [Reproduction instructions](../hpc/README.md#testing-whether-contrast-answers-the-preceding-line)

## Does completing the preceding cadence distinguish written 7s from 6s?

**Project hypothesis.** When the current model gives two passages the same forecast, a line that takes up an earlier grammatical beat and completes a corresponding closing phrase may be the stronger passage. The 楊暕 example 非無／先有 and 之文／之作 suggested the hypothesis. Its entire source pool was excluded from the fresh comparison.

**Selection and reference.** Gilbreth extracted 2,316 units from 35 attributed, revision-pinned witnesses of Tang official prose and earlier parallel rhapsodies. The source filter admitted punctuated paragraphs with at least three units and some internal balance. After excluding earlier authors and titles and retaining one witness per author, 1,850 units in 21 works remained. Removing 145 paragraph openings, 22 duplicate targets, four incomplete edges and two previously seen edges yielded 1,677 eligible targets. Exactly 340 targets belonged to 117 same-work groups with identical unrounded binary64 forecasts. The frozen sampling rule selected 95 from 34 groups and 11 source pages. One GPT editor rated written 音律美 in paragraph context, without the group identities, forecasts or feature outputs. The editor knew the hypothesis. The reference contains twenty-two 7s, forty-five 6s, twenty-seven 5s and one 4. [Frozen protocol](../research/cadence-completion.md) · [Sources, prompts, formulas and controls](../src/cadence_completion.py)

**What the bonus measures.** Two Chinese prompts asked the same pinned Qwen classifier whether the target repeats an earlier beat and completes the closing construction with varied words. A bonus of 0.25 required agreement. The two prompts reversed the A/B order. One transparent comparator checked only whether the two lines shared the full sequence of arm lengths, where an arm is a punctuation-delimited phrase counted in characters. A stricter spelling-based comparator additionally required an earlier aligned cue and a changed closing foot with a corresponding cue. All three used the genuine immediate predecessor. The current model and always giving 6 tie every eligible pair by design. This comparison measures ordering near the top of the written scale. A correct ranking can occur while both numerical forecasts still round to 5 or 6. [Classifier checkpoint](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/tree/a09a35458c702b33eeacc393d103063234e8bc28)

**Verified prose comparison.** While reading the masked texts and before inspecting predictions, the editor flagged two edition problems. 張九齡’s page contains a series of edicts, including variant versions of the same passage, and 李邕’s inscription has a verse coda introduced by 其詞曰, a spelling the extraction rule missed. Checking the originals confirmed both. A second analysis omitted all four rated targets from the composite page and all six rated targets in the coda. It retained the rest of 李邕’s prose preface, with no replacement passages. Of 85 remaining targets from ten works, 43 contributed to 33 comparisons across 16 groups in nine works. The composite page had no informative pair; the coda had one unresolved pair. [張九齡’s numbered edicts](https://zh.wikisource.org/wiki/Special:PermanentLink/1496221) · [李邕’s preface and inscription](https://zh.wikisource.org/wiki/Special:PermanentLink/2487350)

| Method on verified prose | 7 above 6 | 6 above 7 | Still tied | All pairs, half credit per tie | Equal weight per informative work |
|---|---:|---:|---:|---:|---:|
| Always give 6 | 0 | 0 | 33 | 0.500 | 0.500 |
| Current model | 0 | 0 | 33 | 0.500 | 0.500 |
| Current plus agreed cadence completion | 6 | 5 | 22 | 0.515 | 0.714 |
| Current plus matching phrase lengths | 12 | 3 | 18 | 0.636 | 0.745 |
| Current plus matched lengths and two spelling cues | 2 | 1 | 30 | 0.515 | 0.607 |

The unfiltered frozen screen gave 6 correct, 5 inverted and 23 unresolved among 34 pairs, with work-weighted ordering 0.687 and pooled ordering 0.515. Matching phrase lengths alone gave 12 correct, 3 inverted and 19 unresolved, with work-weighted ordering 0.717. The two individual Qwen prompts respectively produced 9/6/19 and 15/5/14 correct/inverted/tied on the unfiltered screen. The agreement rule was fixed in advance. Neither diagnostic prompt replaced it after evaluation.

| Informative work in the verified prose analysis | 7/6 pairs | Completion correct / inverted / tied |
|---|---:|---:|
| [上官儀《為朝臣賀涼州瑞石表》](https://zh.wikisource.org/wiki/Special:PermanentLink/1971314) | 1 | 1 / 0 / 0 |
| [李邕《國清寺碑》 prose preface](https://zh.wikisource.org/wiki/Special:PermanentLink/2487350) | 1 | 1 / 0 / 0 |
| [張鷟《滄州弓高縣實性寺釋迦像碑》](https://zh.wikisource.org/wiki/Special:PermanentLink/1971840) | 3 | 1 / 0 / 2 |
| [魏元忠《請解職表》](https://zh.wikisource.org/wiki/Special:PermanentLink/8729554) | 1 | 1 / 0 / 0 |
| [嵇康《琴賦》 prose preface](https://zh.wikisource.org/wiki/Special:PermanentLink/1962997) | 1 | 1 / 0 / 0 |
| [潘岳《西征賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/2279801) | 3 | 1 / 0 / 2 |
| [張衡《西京賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/2001020) | 8 | 0 / 0 / 8 |
| [謝莊《月賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/1809104) | 2 | 0 / 1 / 1 |
| [司馬相如《上林賦》](https://zh.wikisource.org/wiki/Special:PermanentLink/7908985) | 13 | 0 / 4 / 9 |

**Why the two summaries differ.** Four works had one informative pair each, and the classifier got all four right. By contrast, 《上林賦》 supplied 13 pairs and four inversions. A work-weighted average prevents one long work from dominating. A pooled average answers what happened to an individual pair in this sample. In the additional check on the 18 pairs where the length rule gave both targets the same signal, the classifier ranked one correctly, three incorrectly and left 14 tied. This comparison spans five works and gives little evidence for a gain beyond phrase lengths.

**What happened in the text.** The model gave both lines of 上官儀 the exact score 5.395070289176697. The editorial 6, 「致德至仁，乘拱岩廊之上」, sets out a short invocation and a longer location. The editorial 7, 「乃聖乃神，遠算廟堂之下」, repeats the invocation’s two beats and lands on 之下 where the first line landed on 之上. The classifier correctly raised the second. The matching-length rule also got this pair right. In 司馬相如, 「撞千石之鐘，立萬石之虡」 earned 7 for the force of 撞 and the escalation from 千 to 萬. 「建翠華之旗，樹靈鼉之鼓」 earned 6 and plainly continues the construction. Both had a forecast of 5.717670222685737. Rewarding continuation promoted the 6 above the 7. The written reference sometimes valued the line that establishes a cadence more than the line that completes it. [上官儀](https://zh.wikisource.org/wiki/Special:PermanentLink/1971314) · [司馬相如](https://zh.wikisource.org/wiki/Special:PermanentLink/7908985)

**Control results.** On the 95 frozen targets the prompts agreed to award 16 bonuses, split on 26 cases and agreed to withhold 53. Both accepted the motivating and constructed positive examples. Their agreement rule rejected a same-length mismatch and a verbatim copy. For 55 verified-prose targets, an earlier nonadjacent line from the same paragraph had exactly the same arm lengths as the real predecessor. The classifier flagged the real predecessor only eight times, the substituted one only three times, both four times, and neither 40 times. This small control favors genuine adjacency on balance. Among 999 within-work, within-exact-score shuffles of the 6/7 flags, 39 equaled or exceeded the observed work-weighted gain on verified prose (one-sided permutation estimate 0.040). The corresponding estimate on the original frozen screen was 0.045. These shuffles test the placement of bonuses against random assignment; the direct comparison with phrase lengths addresses a different question.

**Decision.** Keep cadence completion as an explanation a close reader can inspect. Matching phrase lengths did better on this fresh challenge under both aggregation schemes. A single editorial reference, repeated use of passages in several pairs, and four informative works with only one pair each limit generalization. The scorer retains its existing weights. This round measured written 音律美. Listening and first-read ease (顺口) await separate final-stage participant testing. Slurm jobs 12509500 (screen and GPU classification), 12509587 (sealed evaluation) and 12509640 (edition audit) all completed with exit code zero. All original lines with forecasts and judgments on Gilbreth (`$SHUNKOU_ROOT/results/cadence-completion-20261123/results/readings.txt`) · Verified-prose analysis (`$SHUNKOU_ROOT/results/cadence-completion-20261123/results/edition-audit.json`) · [Reproduction instructions](../hpc/README.md#testing-cadence-completion-across-adjacent-lines)

## Yu Xin memorization review

**Scope and reference.** The 23 November 2026 review covers every punctuated sentence in 庾信’s 《哀江南賦並序》, including 32 sentences of preface and 259 of the main rhapsody. The 25 edition paragraphs supply context. A full stop, question mark or exclamation mark ends a sentence. The two sides of an internal semicolon stay together in all 18 such sentences. The AI close reading was divided into three blocks. Each sentence received one written 音律美 grade from 1 to 7, with 7 recommending memorization. The frozen text prototype produced one continuous score for each of the same 291 sentences. Its training reference comprised GPT editorial grades on 337 passages from seven other works. No normalized complete sentence matched a training row. The project had previously used preface excerpts in pilot research. [Pinned edition, revision 3656893](https://zh.wikisource.org/w/index.php?oldid=3656893)

**Expert evidence.** 顧偉列 discusses variation in phrase length and parallel constructions across the preface. 王若虛 and 李錫鎮 disagree about the diction of particular lines. These references give readers reasons to examine or contest a reading. We found no expert source assigning a 1–7 musicality score to every sentence. [顧偉列 on the preface](https://www.kekeshici.com/guji/gwgz/51541.html) · [王若虛, 《滹南集》卷三十四](https://zh.wikisource.org/wiki/滹南集_(四庫全書本)/卷34) · [李錫鎮, pp. 107–110](https://www.cl.ntu.edu.tw/uploads/root/臺大中文學報/第十一期/庾信哀江南賦若干負面評價之商榷.pdf#page=3)

**Observed author edits.** The author entered a score only when they wished to change the AI close reading. A join on sentence ID and original text matched all 291 rows. The returned file contained 22 numeric edits, each by one point, and no written objections. The remaining 269 rows have no observed author score.

| Close reading → author score | Preface | Main rhapsody | Total |
|---|---:|---:|---:|
| 5 → 6 | 1 | 4 | 5 |
| 6 → 7 | 8 | 3 | 11 |
| 7 → 6 | 0 | 6 | 6 |
| **All edited sentences** | **9** | **13** | **22** |

The close reading initially recommended 42 sentences, nine in the preface and 33 in the main rhapsody. Applying only the explicit changes gives a working shortlist of **47** (17 preface, 30 main). This comprises 11 explicit author 7s and 36 original recommendations on which the author entered no rating.

**Prototype comparison.** Gilbreth scored all 291 sentences, with a range of 4.718 to 6.302. None reached the fixed 6.50 threshold. Among the 22 edited sentences, the mean prediction was 5.73 on the eleven author 7s and 5.79 on the eleven author 6s. This describes the selected disagreements of one reader. The sampling design leaves whole-work agreement, recall and accuracy against that reader unmeasured.

**Restart point.** The scoring run completed as Gilbreth Slurm job `12510636`. Its private archive is under `$SHUNKOU_ROOT/results/ai-jiangnan-complete-20261123-N0QpQKI1`. The archive holds the edition units, frozen predictions and model provenance. The access-restricted `author-review.json` records the close-reading grades, the explicit author edits and hashes for both workbook files. Blank author scores are stored as null. The review belongs to written 音律美. On resumption, use the disagreements to formulate a testable distinction between 6 and 7, then evaluate it on fresh works before considering a change to the scorer. Listening and first-read ease (顺口) retain their separate final-stage protocols.
