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

## Known-text fixtures

The tests exercise preserved heteronyms, context evidence, both historical annotation tiers, the five- and seven-character tonal templates, and syntactic parallelism (對仗) in the verified 《登高》 couplet. The fixtures also cover the different first-line rhyme branches and the weighted edit cost. Duanmu and Stiennon’s seven-character corpus supplies an external benchmark. Its 114 poems contain 216/672 independently scanning strict lines and 610/672 under the literal odd-position rule without alternate readings. Reproduction needs that edition, its membership, and the reading decisions. The wider verse, fu, canon, and historical-period contrasts remain open. [Known verse tests](../tests/test_verse_templates.py) · [Historical annotation tests](../tests/test_historical_annotation.py) · [Duanmu and Stiennon, 2005, Tables 21–23](https://websites.umich.edu/~duanmu/PingZe05.pdf)
