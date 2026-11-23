# Stage 5 · Pilot metric validation

The primary analysis uses the **12 matched prose passages** in six period- and subject-matched pairs. The three Northern Song probes remain case studies. The input is the edition-pinned [Stage 3 annotations](stage-3.md) and the [Stage 4 synthetic Mandarin waveform tables](stage-4.md). Audio for all inferential units is controlled synthesis, and the waveform labels and timestamps remain drafts.

**Run.** Slurm job `12472662` completed on one A10 in `00:01:49`, with exit code `0:0` and all 12 tests passing, including the live historical annotation check. The Gateway job moved from standby to the available normal project allocation. Full effects, uncertainty bounds, controls, paired contrasts and audio disagreements are in `${RCAC_SCRATCH}/shunkou/results/stage5/validation.json`. The file includes source hashes for the pilot and waveform tables. [Rebuild instructions](../hpc/README.md#stage-5-validation-through-the-gateway)

## Validation design

The pilot computes 17 structural, historical-tone, and recurrence descriptors. 《廣韻》 supplies the main historical tier and 《平水韻》 supplies a sensitivity tier. A primary value uses determinate comparisons only. Each estimate also reports support and feasible lower and upper bounds when the dictionary readings permit alternatives. Structural pair annotations are required for pair-specific metrics. [Metric implementation](../src/text_metrics.py)

The randomization checks use 999 seeded draws per control and tier. The within-clause control moves character and reading bundles while holding clause lengths and boundaries fixed. The clause-order control moves intact clauses into the original boundary and pair positions. The tone control permutes resolved binary historical 平仄 labels within period and genre and holds the unresolved positions, reconstructed phones, and rhyme groups fixed. Both the observed passage set and the weight of each represented work are fixed within a test. A draw is included when all those passages have a computable statistic. Report work-weighted real-minus-control effects, two-sided Monte Carlo p-values, and percentile intervals from resampling works. Holm correction applies to the tests within each historical tier. The saved output also checks the metrics invariant under a control by construction. [Randomization tests](../src/pilot_validation.py) · [Phipson and Smyth, 2010](https://arxiv.org/abs/1603.05766) · [Holm, 1979](https://doi.org/10.2307/4615733)

The known-groups check estimates paired differences between parallel prose (骈文) and period-matched comparison prose (散文). Pairs that share a source work flip as a block in the exact sign check. The audio analysis recomputes both measures on shared usable positions, aggregates within each voice and speed condition, and summarizes by the median across available conditions for each passage. It reports descriptive Spearman rank correlations, complete-condition sensitivity, and the largest rank disagreements. Annotation and acoustics have different units, so these correlations describe ordering agreement. [Text and audio implementation](../src/audio_validation.py)

## Shuffled controls and matched genres

**Pilot observation.** None of the 21 《廣韻》 or 19 《平水韻》 tests passed Holm correction at 0.05. In the main tier, every determinate annotated paired ending was opposed across the five represented passages, compared with a work-weighted mean of 0.513 under tone reassignment. All six annotated passages had exactly balanced side lengths, compared with 0.893 after reordering whole clauses. These are promising formal diagnostics for a larger sample. They remain outside a validated score.

| 《廣韻》 descriptor | Control | Passages | Real minus control | Raw p | Holm p |
| --- | --- | ---: | ---: | ---: | ---: |
| Opposed 平仄 at annotated paired ends | Stratified tone reassignment | 5 | +0.487 | 0.005 | 0.105 |
| Paired-side length similarity | Whole-clause reorder | 6 | +0.107 | 0.010 | 0.200 |
| Opposed 平仄 at annotated paired ends | Within-clause syllable shuffle | 5 | +0.485 | 0.014 | 0.273 |
| Alternation across successive clause ends | Stratified tone reassignment | 12 | +0.198 | 0.035 | 0.630 |

《平水韻》 gives the same broad pattern. Its smallest adjusted p is 0.103 for paired-end opposition under the within-clause shuffle. Acceptance of that randomization test required computable comparisons for all six observed passages, so it used 551 out of 999 draws. The full output gives the accepted count for each test. Clause-length mean, spread, four/six share, and punctuation density stayed invariant under all three controls by construction.

The matched difference in four/six share averaged **+15 percentage points** for 骈文. Two pairs favored 骈文, one favored comparison prose, and three tied. Clause-end tone alternation showed a mean difference of −2.5 points, and successive even-slot tone alternation showed +6.4 points. Shared work IDs reduce the six pairs to two connected blocks, leaving four exact sign assignments. The smallest attainable two-sided p is 0.5. The genre contrasts are therefore descriptive. Paired-side metrics require independent annotations, which this corpus supplies unevenly across genres.

## Text against Stage 4 sound

**Pilot observation.** Written clause length and variability give a strong baseline for the corresponding timings in the controlled recordings. Historical tonal alternation and reconstructed segment recurrence show weak or mixed agreement with the present-day acoustic measures. The 平 share correlation is partly definitional because both measures reuse each syllable's historical label.

| Text measure and acoustic counterpart | Passages | Spearman ρ |
| --- | ---: | ---: |
| Mean clause length and mean articulation time | 11 | 0.952 |
| Clause-length SD and clause articulation-time SD | 11 | 0.950 |
| Clause-length nPVI and articulation-time nPVI | 11 | 0.921 |
| Internal punctuation density and 150 ms quiet-gap candidate density | 12 | 0.320 |
| Historical 平 share by count and by articulation duration | 12 | 0.932 |
| Syllable-level 平仄 alternation and adjacent absolute pitch reset | 12 | −0.287 |
| Even-slot 平仄 alternation and late-F0 differences | 12 | −0.028 |
| Clause-end 平仄 alternation and late-F0 differences | 12 | 0.190 |
| Adjacent reconstructed initial recurrence and draft Mandarin onset recurrence | 12 | −0.190 |
| Adjacent reconstructed final recurrence and draft Mandarin final recurrence | 12 | 0.088 |

Only six passages had usable clause nPVI in all six conditions. For that subset ρ was 0.986. Paired-side length and paired-end opposition had only three and four usable passages, respectively, and constant values precluded a correlation. Exact adjacent character repetition and clause-end rhyme recurrence also produced constant series on at least one side.

All **43** quiet-gap candidates at 150 ms or longer fell at punctuation in the matched set. The denominator was 180 eligible punctuation locations and 1,090 eligible nonpunctuation locations pooled across the takes. Punctuation entered the synthesis input. This alignment is therefore a diagnostic of the generator and feature pipeline. Median matched-passage 平/仄 geometric-duration ratios were 1.065 under 《廣韻》 and 1.099 under 《平水韻》. These describe the synthetic takes.

**Largest disagreements.** ET01 had equal written lengths in its one usable adjacent clause comparison, giving nPVI 0. The corresponding draft timing nPVI was 16.59. ET03 and ET04 were at opposite extremes of the ranks for within-clause 平仄 alternation and pitch reset. ET03 had a contrast rate of 0.706 and mean absolute reset of 1.33 semitones. ET04 had 0.236 and 2.06. Each used all six conditions. The two 《峴山亭記》 variants both had end-tone opposition of 1, while the ordered 仄平 indicator changed from 0 to 1. Their median absolute terminal F0 differences were 9.86 and 4.52 semitones. Wording and clause length also change in that case. [Passage identities and critic provenance](../data/pilot/DATA_CARD.md)

**Contested measurement and project hypotheses.** Clause timing is a useful baseline for separating what can be predicted from character count from any incremental effect of historical form. Paired-side balance and ending-tone opposition remain hypotheses for independent annotated passages. The small work-block count, synthetic delivery, and alignment-dependent coverage limit all inference. Human pronunciation, independently reviewed segment and breath intervals, and listener judgments remain open. No feature weights or composite 音律美 score were fitted.

## Work-held-out synthetic timing benchmark

**Pilot observation.** Gilbreth fit two timing baselines on five matched excerpts from four original works and tested them on four distinct works from the expansion listening set. Calibration and test authors, works, texts, and WAVs were disjoint. All nine recordings used the same Kokoro model revision, male Mandarin preset (`zm_010`), and speed (0.9). The endpoint was total verified WAV duration, including pauses and padding. The fit used milliseconds per written slot and gave each calibration work equal weight. The expanded model also used the count of internal punctuation-defined clause breaks. Errors are absolute duration errors averaged by work.

| Predictor | Mean absolute error on four held-out works |
| --- | ---: |
| Written character count | 207 ms |
| Written character count and clause breaks | 406 ms |

Adding clause breaks improved one of four works. The added coefficient was negative in this small fit, which describes covariation in the original recordings. The count-only baseline remains the reference for this synthetic timing endpoint. A controlled edit with the same words would be needed to estimate a punctuation effect. The held-out works had appeared in earlier descriptive analyses, so this is a development check. No human ratings entered the fit or evaluation. The exact input hashes and detailed errors are in `$SHUNKOU_ROOT/results/model-development/synthetic-timing.json`. [Benchmark code](../src/timing_benchmark.py) · [Gilbreth command](../hpc/README.md#synthetic-timing-benchmark)

## Known-text fixtures

The tests exercise preserved heteronyms, context evidence, both historical annotation tiers, the five- and seven-character tonal templates, and syntactic parallelism (對仗) in the verified 《登高》 couplet. The fixtures also cover the different first-line rhyme branches and the weighted edit cost. Duanmu and Stiennon’s seven-character corpus supplies an external benchmark. Its 114 poems contain 216/672 independently scanning strict lines and 610/672 under the literal odd-position rule without alternate readings. Reproduction needs that edition, its membership, and the reading decisions. The wider verse, fu, canon, and historical-period contrasts remain open. [Known verse tests](../tests/test_verse_templates.py) · [Historical annotation tests](../tests/test_historical_annotation.py) · [Duanmu and Stiennon, 2005, Tables 21–23](https://websites.umich.edu/~duanmu/PingZe05.pdf)

## Historical tone and rhyme on fresh works

**Pilot observation.** The development set used nine matched recordings from eight earlier works. The holdout used 16 new works in eight subject- and length-matched pairs, with four pairs from each period and no repeated credited authors across the split. The 460 written slots retain the candidate readings from 《廣韻》 and 《平水韻》. The audio uses the same Kokoro male Mandarin voice and speed as development. The computational benchmark uses no human ratings. The first submission was stopped after a preflight check and the prescription for 詮 was corrected to *quán* for the analyzed run. [Fresh corpus and primary witnesses](../data/pilot/DATA_CARD.md#fresh-works-for-the-historical-feature-benchmark) · [Fixed benchmark design](../research/historical-increment.md) · [Mandarin reference for 詮](https://dict.revised.moe.edu.tw/dictView.jsp?ID=6704&q=1&word=%E8%A9%AE)

### Beyond character count for synthetic duration

The character-count baseline averaged **758 ms absolute error** per held-out work. The tone model adds the share of determinate historical level-tone slots. The rhyme model adds the rate at which two determinate slots anywhere in a passage share an exact rhyme-book group. All 16 held-out works were eligible in each comparison. For each descriptor, all 999 shuffled refits were usable. Shuffles exchange descriptors across works with matched period, genre, and excerpt count and keep the audio, character counts, and evaluation cohort fixed.

| Historical tier and added feature | Average absolute error | Works with lower error | Shuffled-tail probability | Holm adjusted |
| --- | ---: | ---: | ---: | ---: |
| 《廣韻》 level-tone share | 781 ms | 7/16 | 0.150 | 0.234 |
| 《廣韻》 rhyme-group concentration | 819 ms | 7/16 | 0.117 | 0.234 |
| 《平水韻》 level-tone share | 757 ms | 8/16 | 0.323 | Sensitivity |
| 《平水韻》 rhyme-group concentration | 753 ms | 9/16 | 0.839 | Sensitivity |

The primary features increased average error by 23 and 61 ms. The sensitivity tier lowered error by approximately 1 and 5 ms, respectively, well within its shuffled distributions. Character count remains the baseline for total duration in this synthetic condition. Passage-wide level-tone composition and rhyme-group concentration are distinct from ordering at clause endings. [Code and shuffled comparisons](../src/historical_increment.py)

### Ordered text controls and waveform checks

None of the fresh set's 21 《廣韻》 or 19 《平水韻》 structural shuffle tests passed Holm correction at 0.05. The smallest adjusted values were 0.126 and 0.608, respectively. For 《廣韻》, resolved adjacent clause endings alternated at a passage-weighted rate of 0.50, compared with 0.48 after shuffling within clauses, 0.51 after shuffling intact clauses, and 0.48 after reassigning resolved tones within period and genre. Exact adjacent rhyme-group recurrence was zero in the observed prose and about 0.01 in both ordering controls. These are text controls on the fresh matched sample.

The draft alignment linked 370 of 460 written slots across the 16 fresh clips. On shared usable positions, written clause length tracked synthetic articulation time (Spearman ρ = 0.955, 15 works and 32 complete clauses). Historical clause-end 平仄 alternation had a smaller descriptive association with the difference in late pitch (ρ = 0.333, 12 works and 22 usable transitions). Exact historical rhyme-group recurrence stayed at zero across the 44 acoustically comparable clause-end transitions from 15 works, so an association with modern final recurrence could not be estimated. The clause-ending checks compare text descriptors with waveform features on the same positions. They are separate from the held-out total-duration prediction.

Slurm job `12474276` completed on one A10 in 2 minutes 30 seconds. The corpus, all 16 WAVs, annotation and alignment tables, and per-work results are in `$SHUNKOU_ROOT/model-development/historical-increment`. The duration and structural analysis JSON files are under `results/historical-increment/` in that directory. This is evidence from one synthetic Mandarin delivery. Sound-pattern beauty (音律美) and first-read ease (顺口) remain distinct outcomes for final human validation. [Gilbreth run and output locations](../hpc/README.md#historical-tone-and-rhyme-on-fresh-works)

## Fixed-text tone and rhyme minimal pairs

**Pilot observation.** Slurm job `12474367` rendered 32 WAVs at eight internal clause endings across sixth-century and Early Tang parallel and comparison prose. Each site supplied a baseline, an identical-input repeat, a target-tone edit, and a target-final edit. The eight repeats matched their baseline WAVs byte for byte. Text, character count, punctuation, phrasing input, seed, and reference voice embedding were fixed within each group. The two interventions target modern Mandarin synthesis. The edited readings may be inappropriate for the printed character, and the historical annotations stay tied to the witness. [Site plan](../audio/minimal_ending_sites.json) · [Design and waveform checks](../research/minimal-endings.md)

| Median absolute change | Tone edit | Rhyme edit |
| --- | ---: | ---: |
| Whole WAV duration | 25 ms across 8 pairs | 25 ms across 8 pairs |
| Target syllable duration | 20 ms across 7 linked pairs | 30 ms across 5 linked pairs |
| Target late-minus-early pitch | 7.11 semitones across 5 usable pairs | 0.69 semitones across 3 usable pairs |
| Target second vowel formant | 22 Hz across 3 usable pairs | 670 Hz across 3 usable pairs |
| Gap immediately after the ending | 70 ms across 5 usable pairs | 10 ms across 4 usable pairs |

The large pitch shifts in the tone arm were inconsistent in direction. Only two of five measurable pairs produced a more negative late-minus-early pitch change in the prescribed falling-tone take. Both draft target labels matched their respective prescriptions in two of the eight tone pairs. Rhyme recurrence could be compared at both the edited ending and its unchanged anchor in three pairs. The decoder recovered two intended additions and one intended removal of exact modern final agreement. Five rhyme comparisons lacked sufficient links. Changes in the gap after the target and timing at unchanged neighbors show that an isolated input edit can affect more than the target sound during full resynthesis.

The alignment linked 762 of 920 written slots across all 32 takes. The decoder processed each waveform before the linker used a target-only pronunciation hint. The acoustic values use the linked intervals. Vowel resonances capture part of the difference between finals, with separate evidence needed for coda realization. [Acoustic definitions](../audio/ACOUSTIC_FEATURES.md) · [Detailed analyzer](../src/minimal_ending_analysis.py)

**Direct pitch check.** Local Praat overlap-add produced engineered flat and falling contours with identical sample counts and byte-identical PCM outside the edit window. One full-syllable control passed the waveform checks, with a falling-minus-flat pitch change of −4.18 semitones. A separate pass used the longest contiguous voiced run in each source syllable to avoid the unvoiced onset. Two sites passed, both in Early Tang comparison prose, with a median difference of −3.53 semitones. One also passed the full-syllable check. The other six sites in the voiced-run pass lacked sufficient baseline voiced support or a target link. These checks verify engineered pitch contours in those windows. They leave the lexical tone and perceived naturalness open. [Direct-pitch protocol](../research/minimal-endings.md#direct-pitch-check)

All audio and analysis outputs are in `$SHUNKOU_ROOT/model-development/minimal-endings`. The GPU run completed in 3 minutes 48 seconds. Both direct-pitch checks ran on Gilbreth with the cached audio. Sound-pattern beauty (音律美) and first-read ease (顺口) remain separate outcomes. Participant testing follows computational development. [Gilbreth run instructions](../hpc/README.md#fixed-text-tone-and-rhyme-controls)

## Expanded pitch controls and rhyme alignment

**Pilot observation.** The extension screened the original Mandarin WAVs of all 16 works for linked, sufficiently voiced internal clause endings. It excluded the previously edited slots and chose at most one new site per work using only the original waveform. Fifteen new flat-versus-falling pairs passed the earlier acoustic thresholds, including seven works absent from the earlier pitch controls. Eight verified sites were in sixth-century prose, seven in Early Tang prose, and eight in parallel prose. The falling-minus-flat contrast had a median of −3.51 semitones and a range of −4.00 to −2.53. All controls held the edition and character count fixed, kept the original sample count, and preserved the PCM outside the edit window. One passage had no eligible site. The coverage applies to source endings that passed the voicing screen. [Eligibility and measurement protocol](../research/minimal-endings.md#expanded-pitch-controls-and-rhyme-alignment)

**Rhyme alignment from the original phone drafts.** Matching unchanged context on both sides recovered two missing endpoints while preserving all 22 originally usable target and anchor links. Three of eight pairs still had both endpoints available in both takes. On the internal consistency check, the method recovered 205 of 342 temporarily hidden original links. All 205 accepted proposals agreed with the original draft index, and the method abstained on the other 137. The check measures agreement with cached draft links.

**Re-decode with different surrounding audio.** Gilbreth Slurm job `12474448` rechecked the eight unresolved endpoints using two local waveform windows and a zero-padded copy of the full take. The copied speech samples were identical to the originals. No endpoint had the two qualifying views needed for acceptance. Depending on the view, the neighboring sounds failed to give a unique position or the decoder was uncertain about the final. The three complete pairs retained their original draft directions, with two gains and one loss of exact modern final agreement. The three views use the same model, so the test checks stability under changes in the supplied audio context. [Recovery protocol](../research/minimal-endings.md#expanded-pitch-controls-and-rhyme-alignment)

**Waveform corroboration.** The three complete cases all moved in the intended direction in the central spectral window and two did so in the late window. Both direction counts held when the original anchor spectrum was used for both versions. This comparison uses the waveform within the decoded final intervals and keeps its distance calculation separate from decoded labels. Five pairs remain unscored for rhyme. The experiment measures one synthetic Mandarin delivery at fixed character counts. It supplies acoustic controls for eventual 音律美 listening tests. 顺口 remains a separate first-read outcome. Participant testing is reserved for final validation.

The 30 new pitch WAVs and the pitch, initial rhyme, and re-decode reports are under `$SHUNKOU_ROOT/model-development/ending-control-extension`. The original rhyme WAVs remain under `$SHUNKOU_ROOT/model-development/minimal-endings`. [Gilbreth runbook](../hpc/README.md#expanded-pitch-controls-and-rhyme-alignment)

## Fixed-text recitation phrasing

**Established source evidence.** 賴金時 gives 日暮／途窮 as 2+2 and 人／間／何世 as 1+1+2 in a guide to prepared competition recitation. She illustrates different readings of different clauses and invites variation to avoid a mechanical delivery. The pilot witness reads 日暮途遠. We retained its edition and used her contrasting groupings as the starting point for an intervention on the same four characters. [Guide, pp. 72–73](https://teric.naer.edu.tw/wSite/PDFReader?fileName=1527062437051&format=pdf&xmlId=#page=6) · [Pinned 《哀江南賦序》 witness](https://zh.wikisource.org/zh-hant/哀江南賦)

**Project hypothesis.** At sites located in the original male Mandarin take, 2+2 adds 80 ms of silence after slot 2. The 1+1+2 condition adds 40 ms after each of slots 1 and 2. Both use the same text, original speech, and total duration. Screening requires consecutive draft syllables that match the intended onset and final, followed by locally quiet or low-energy cuts. Where a quiet splice is unavailable, both variants and a zero-added-pause reference use the same two 10 ms amplitude tapers. Checks reconstruct the reference by removing the pauses and compare the reference with the original outside the taper windows. The third internal boundary is a timing control. [Gilbreth runbook](../hpc/README.md#fixed-text-recitation-phrasing)

**Controlled result.** The initial screen found no site with both a complete draft link and two quiet cuts. With the shared tapers, 12 of 43 screened clauses were rendered, one per work, including 人間何世 and 11 additional passages. Seven were sixth-century, five were Early Tang, and nine were parallel prose. Fifteen clauses qualified in total, and three were passed over to keep one per fresh work. Of the 28 ineligible clauses, 24 lacked an exact segment link, three had nonconsecutive draft syllables, and one lacked a sufficiently low-energy cut even with the taper. The available SD01 male take for 日暮途遠 was excluded because the decoder did not reliably link 途. Both versions of all 12 retained clauses had the same sample count. Outside the two shared windows, the source PCM was unchanged. The median whole-take energy removed by the tapers was 0.087%, with a maximum of 0.263%.

The waveform check followed unique speech templates through each WAV without reading the insertion offsets. It recovered the 80 ms budget and exact placement in **12 of 12** pairs. At the primary low-energy threshold (−45 dBFS), the median added quiet time relative to the tapered reference was:

| Phrasing | After slot 1 | After slot 2 | After slot 3 |
| --- | ---: | ---: | ---: |
| 2+2 | 0 ms | 80 ms | 0 ms |
| 1+1+2 | 40 ms | 40 ms | 0 ms |

Both directions of redistribution held in all 12 pairs at −50, −45, and −40 dBFS. At −45 dBFS, the mean split-versus-concentrated change in the first gap minus the second gap was 79.2 ms. Across all 4,096 label swaps blocked by work, the shuffled median was 0 ms and the 95th percentile was 39.2 ms. Only one assignment reached the observed contrast. This measures recovery of the engineered pause placement in short synthetic takes. The natural grouping cues of a practiced reader can include changes in pitch, stress, and syllable duration as well as pauses.

**Phone-draft check.** Gilbreth Slurm job `12481142` decoded the two variants and the tapered reference directly from their WAVs. A gap was eligible only when the draft linked the same neighboring segments across all three takes. Both edited boundaries were measurable in five of 12 pairs, including 人間何世, and all five changed in both planned directions. Across the individually measurable gaps, the median split-minus-concentrated change was +35 ms after slot 1 (8 pairs), −40 ms after slot 2 (6 pairs), and 0 ms after slot 3 (9 pairs). The lower coverage shows where the phone drafts lose links even when waveform timing is recoverable. [Decoder check](../src/recitation_phrasing_decode.py)

The 36 WAVs, screening manifest, and waveform results stay under `$SHUNKOU_ROOT/model-development/recitation-phrasing`. The stimuli can support a later sound-pattern beauty (音律美) listening contrast. First-read ease (顺口) requires its own read-aloud task. Participant testing is reserved for final validation.

### Alignment extension and 日暮途遠

**Controlled result.** The extended set has 13 pairs across 12 works. All 36 WAVs from the earlier experiment are byte-identical. For 日暮途遠, the draft links for 暮 and 遠 bracket the interval from 0.570 to 0.780 s in the original male Mandarin recording. The raw decoder runs inside it are `t`, `u2`, `ong2`, and `u2`. A conservative contextual check recovered one timing interval for 途 and kept the contradictory final label and original alignment events. Its pronunciation remains a draft with competing evidence. The two new variants keep the pinned wording and both contain 160,920 samples at 24 kHz (6.705 s). They redistribute the same 80 ms pause budget. [Pinned witness](https://zh.wikisource.org/zh-hant/哀江南賦) · [Recovery rule](../src/recitation_guide_recovery.py)

Exact waveform matches tracked four syllable cores in each version and verified that removing the inferred silent intervals reconstructed the common recording. The alignment recovered the intended pause distribution in all 13 pairs, including the seven original pairs whose phone drafts lacked both edited boundaries. This transfers timings for identical speech samples. For 33 of the 104 transferred syllable intervals, the underlying draft window may span an inserted pause, so the aligned cores and the possible edge ranges are stored separately. The median width of a possible splice location was 0.17 ms and the maximum was 1.67 ms. Low-energy gap measurements also recovered both intended directions in all 13 pairs at all three thresholds. [Exact-sample alignment](../src/recitation_pcm_alignment.py)

**Phone-draft check.** Gilbreth Slurm job `12481431` re-decoded the incomplete cases in two fixed audio contexts. A new gap required uniquely supported neighboring segments and agreement within 30 ms at both edges across the views in all three takes. No additional gaps qualified. Both edited boundaries are still available from the phone decoder for five pairs, and 日暮途遠 has timing coverage through the waveform alignment. [Context-window check](../src/recitation_context_decode.py)

#### Second Mandarin aligner

FunASR's `fa-zh` timestamp predictor uses the supplied Han-character count to estimate a sequence of times on a nominal 20 ms grid. We used the exact carrier and both pause variants for each of the 13 pairs. The comparison tests whether the change in spacing between adjacent character midpoints follows the displacement of identical waveform cores. The waveform reference gives +40 ms after the first character, −40 ms after the second, and 0 ms after the third when comparing 1+1+2 with 2+2. The analysis also reports literal gaps between predicted spans. The model commonly assigns short pauses to an adjacent character's span, so those gaps and the waveform silences have different definitions. [FunASR predictor](https://github.com/modelscope/FunASR/blob/main/funasr/models/monotonic_aligner/model.py#L212-L235) · [Pinned model](https://huggingface.co/funasr/fa-zh/tree/d7701644d6e336f093501241beca010519c0986f) · [Comparison code](../src/recitation_second_aligner_analysis.py)

**Controlled result.** Gilbreth Slurm job `12481714` completed on one NVIDIA A10 in 4 min 43 s with exit code `0:0`. FunASR returned character spans for all 39 takes. From midpoint spacing, it recovered both planned directions in 9 of 13 pairs. From literal gaps between model spans, it recovered both in 2 of 13. The waveform recovered the exact placement in all 13. Across the 104 carrier-relative comparisons for the four target slots, the median absolute error of the model's midpoint shifts was 10 ms against the waveform core shifts.

| Split minus concentrated, median across pairs | After slot 1 | After slot 2 | After slot 3 |
| --- | ---: | ---: | ---: |
| Waveform pause | +40 ms | −40 ms | 0 ms |
| FunASR midpoint spacing | +20 ms | −40 ms | 0 ms |
| FunASR gaps between spans | 0 ms | −40 ms | 0 ms |

**途 in 日暮途遠.** FunASR returned 0.690–0.890 s in the carrier and 0.750–0.990 s in both edited takes. The midpoint moved 80 ms in each, matching the shift of the shared waveform core. The matched 20 ms core lies at 0.7265–0.7465 s in both edited takes, ending 3.5 ms before the model span begins. The timestamp agreement is strongest for relative displacement. The absolute edges remain uncertain, and the supplied character label gives no new evidence about the conflicting phone drafts. Both edited WAVs are still 6.705 s.

The WAVs and analysis stay on Gilbreth under `$SHUNKOU_ROOT/model-development/recitation-phrasing-alignment`. These are timing measurements for synthetic listening stimuli. 音律美 remains a listening outcome and 顺口 a separate first-read outcome, with participant testing reserved for final validation. [Gilbreth runbook](../hpc/README.md#recitation-alignment-extension)

#### Measuring pauses from a single recording

**Project hypothesis.** A low-energy waveform measurement can improve on the FunASR timestamp estimates for the engineered phrase shifts. The estimator locates each search window between two adjacent predicted character midpoints and measures the longest run of consecutive 5 ms frames below the RMS threshold. It scores one WAV at a time. The common carrier and exact PCM matches enter only in the benchmark reference. The two edited WAVs in each pair keep text, voice, and duration fixed. We used the existing −45 dBFS threshold for the primary comparison and compared it with a threshold selected from −50, −45, and −40 dBFS on other works. Each fold left out a whole work. Calibration and aggregate error give equal weight to works. [Estimator](../src/recitation_pause_estimator.py) · [Gilbreth runbook](../hpc/README.md#single-recording-pause-benchmark)

**Controlled result.** The bounded Gilbreth CPU run measured all 26 edited WAVs, representing 13 pairs across 12 works. The exact PCM reference is +40/−40/0 ms after the first, second, and third characters when comparing 1+1+2 with 2+2.

| Method | Pairs with both edited directions | Work-weighted mean absolute error |
| --- | ---: | ---: |
| Predict zero change | 0/13 | 26.67 ms |
| FunASR midpoint spacing | 9/13 | 14.03 ms |
| FunASR gaps between spans | 2/13 | 19.72 ms |
| Waveform at fixed −45 dBFS | 9/13 | 10.56 ms |
| Waveform threshold selected on other works | 10/13 | 9.38 ms |

All 12 held-out folds selected −50 dBFS. Both waveform methods recovered a median change of +20/−40/0 ms, so they still underestimated the first change. The median absolute error after the second slot fell from 10 ms with FunASR midpoint spacing to 0 ms with the waveform methods. Estimates for the unedited third gap moved by at most 20 ms in every pair. With the fixed threshold, the mean within-work contrast between the two edited boundaries was 51.67 ms. The 95th percentile across 4,096 work-block label swaps was 26.67 ms, with one assignment reaching the observed contrast. This shuffle check uses the fixed threshold. The fold-selected results are descriptive.

The results support continued testing of waveform pause measurements with a frozen threshold on a new delivery. The same 12 works and one male synthetic voice supplied these controls. Absolute gap edges, natural read-aloud ease (顺口), and perceived sound-pattern beauty (音律美) still require their own evidence. The audio and `single-take-pauses.json` stay in the existing phrasing experiment on Gilbreth.

#### Transfer to a second synthetic voice

**Project hypothesis.** The −50 dBFS threshold selected in every original work-held-out fold can detect the same pause redistribution in a second delivery. The test freezes the threshold and carries over the exact 13 target clauses, editions, intended Mandarin syllables and encoded phonemes. It uses Kokoro `zf_001` with the same model, RNG seed and nominal speed 0.9 as each original `zm_010` take. Within each voice, both variants share a carrier and add the same 80 ms, with duration equal to the sample. Each voice keeps its own synthesized timing. [Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) · [Gilbreth runbook](../hpc/README.md#second-voice-pause-transfer)

Where the second voice has four consecutive matching phone drafts, use them to locate the splice candidates. Other sites use token durations from the Kokoro forward pass, aligned by the median offset to the same recording's matching phone drafts. Low-energy cuts and, when needed, identical 10 ms tapers place both variants on the same carrier. The generator's timings are approximate and carry no new pronunciation judgment. The exact PCM check tests sample reconstruction and the +40/−40/0 ms contrast. The −50 dBFS estimator uses each edited WAV with FunASR timing windows, independently of the construction coordinates. [Kokoro duration frames](https://github.com/hexgrad/kokoro/blob/main/kokoro/pipeline.py#L277-L313) · [Benchmark implementation](../src/recitation_voice_transfer_report.py)

**Controlled result.** Slurm job `12484079` rendered and phone-decoded all 12 source passages. Its initial splice screen recovered 11 of 13 sites and rejected two using a bound centered at the raw generator origin. Centering that check on the documented Kokoro leading timestamp adjustment supported the two remaining sites, including 日暮途遠. Slurm job `12484106` completed the comparison on one GPU in 51 s using the cached second-voice recordings. Exact waveform matching recovered the intended +40/−40/0 ms placement in all 13 pairs in each voice. Both variants in each voice matched in text and sample count, while the complete takes differed between voices by a median of +50 ms at the same nominal speed. The 11 Charsiu-guided sites and the two generator-guided sites are recorded separately in the manifest.

| Voice at −50 dBFS | Both edited directions | Work-weighted mean absolute error | Median shifts by boundary |
| --- | ---: | ---: | ---: |
| Original `zm_010` | 10/13 | 9.38 ms | +20/−40/0 ms |
| Second `zf_001` | 6/13 | 14.03 ms | +10/−40/0 ms |

All six second-voice successes also succeeded in the original voice. Four succeeded only in the original voice and three succeeded in neither. The new voice's first-boundary median absolute error was 30 ms, compared with 20 ms in the original voice. The second-boundary median absolute error was 0 ms in both voices. One second-voice estimate at the unedited third boundary moved by more than 20 ms. The second-voice work-averaged difference between the two edited boundaries was 43.75 ms, compared with a 24.58 ms 95th percentile across 4,096 work-block label swaps. The waveform feature reduced mean error for the second voice from 23.47 ms using FunASR midpoints alone, and both methods recovered both directions in six pairs.

For 日暮途遠, the exact waveform again verified the full contrast. The frozen estimator measured −5/−10/0 ms in the original voice and −10/−20/0 ms in the second, missing the increase after 日 in both deliveries. Versions within the second voice each last 6.830 s. FunASR's second-voice span for 途 overlaps the 20 ms matched core in both variants. This improves local time coverage while leaving the gap redistribution error visible in the benchmark.

The signal is measurable across these two synthetic deliveries. The frozen threshold's precision and directional coverage depend on delivery, especially for the shorter first-boundary change. The acoustic comparison supplies evidence for feature selection in 音律美 listening research. 顺口 remains a separate first-read outcome. The new WAVs, model drafts, and `voice-transfer.json` remain on Gilbreth under `$SHUNKOU_ROOT/model-development/recitation-voice-transfer`. Participant testing stays reserved for final validation.
