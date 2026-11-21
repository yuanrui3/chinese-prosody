# Stage 4 · Pilot audio and acoustics

The controlled Mandarin audio pilot ran on Gilbreth through the Gateway. Slurm job `12471829` completed on one A10 with exit code `0:0` and elapsed time `00:03:56`, including environment setup. The resulting waveforms, licence metadata, alignment drafts, and acoustic tables are under `${RCAC_SCRATCH}/shunkou/audio/`. [Audio guide](../audio/README.md) · [Rebuild commands](../hpc/README.md#stage-4-audio-through-the-gateway)

## Established source and corpus evidence

- **Synthetic corpus.** The edition-pinned pilot produced **90** WAVs from 15 passages, two Kokoro voice presets and three speed settings, totalling 619.08 seconds. Every WAV passed its PCM header, duration and SHA-256 checks. The input pronunciation prescription is retained in each manifest row. Open discrepancies with the Stage 3 dictionary are available for review. [Synthetic source and prescription](../audio/SYNTHETIC.md)
- **Human recording.** One verified U.S. public-domain LibriVox reading of 王羲之’s 《蘭亭集序》 was acquired and checksummed. It matches a reference work at the work level. The spoken variety and exact performed spans remain unverified. The rights search established **zero** reusable human recordings at the 15 exact matched-pilot excerpts. Professional recitation (朗誦), traditional chanting (吟誦), and Cantonese or Minnan comparisons remain open. [Human source and rights card](../audio/HUMAN_SOURCES.md)
- **Listening material.** The verified comparison index includes **36** pairs of same-period prose and **six** historical wording-variant pairs. All are matched on synthetic preset and speed. An additional **12** timing-only pairs extend a low-amplitude gap by 120 ms at punctuation sites in SD01 or SD04. The edit check recovered the original samples exactly after removing the inserted zeros. The critic-marked turn in NS03 supplied no eligible draft gap and remains unedited. [Listening files and method](../audio/README.md#paths-under-rcac_scratchshunkou)

## Acoustic draft results

The Charsiu frame classifier decoded onset and tone-bearing final candidates from each waveform before edit alignment to the text slots. Phonetic evidence comes from the waveform. Historical tone and rhyme enter only after the alignment, when the acoustic rows are joined to Stage 3. The decoder generated 2,508 event rows and linked **2,102 of 2,370 expected slots (88.7%)** closely enough for draft syllable measurements. It also flagged 209 substitutions, 59 omissions and 138 insertions. These labels are alignment discrepancies pending review. Praat produced voiced F0 measures for 2,099 linked syllables. [Alignment method](../audio/README.md#pronunciation-and-alignment) · [Feature definitions](../audio/ACOUSTIC_FEATURES.md)

| Diagnostic | Observed in the synthetic pilot |
| --- | ---: |
| Draft timing coverage at speed 0.9 | 710 / 790 (89.9%) |
| Draft timing coverage at speed 1.0 | 708 / 790 (89.6%) |
| Draft timing coverage at speed 1.1 | 684 / 790 (86.6%) |
| Eligible adjacent-slot intervals | 1,719 |
| Quiet gap candidates of at least 150 ms | 76 |
| Those quiet candidates at punctuation | 67 |
| Median recording-level 《廣韻》 平/仄 geometric-duration ratio | 1.031 |

**Sample inspection.** At speed 1.0, both presets yielded the waveform-derived `h` + `uan2` draft for 還, with intervals of 220 and 240 ms. For 潦, which was supplied as `lao3`, the classifier returned `l` + `ao2` and `l` + `ao1`, with intervals of 120 and 140 ms. Across draft matched slots, the observed and intended labels agreed on segments and tone 1,919 times. There were 180 tone-only differences and three segment differences. These comparisons inspected decoded labels and intervals. Independent auditory checks of pronunciations and interval edges remain pending. [Synthetic readings](../audio/synthetic_readings.json)

## Interpretation and remaining coverage

**Contested measurement.** The 10 ms model grid and syllable grouping give draft timings. Confusions, tone sandhi, and genuine output differences can yield the same discrepancy. Faster readings had lower coverage, so speed comparisons must retain usable denominators at each condition. Quiet-gap candidates require acoustic review before use as pauses or hesitations. The aggregate 平/仄 ratio describes this synthetic corpus. Separate independently reviewed segment intervals, inhalations, and note anchors are required for %V, ΔC, breath groups, and 依字行腔.

**Project hypotheses.** With verified matched human readings, test historical-tone duration contrasts by variety and delivery style. Test punctuation, nested clause structure, and critic-marked turns against reviewed pauses and boundary lengthening. Treat effort and sound preference as separate outcomes in the later production and listening studies.
