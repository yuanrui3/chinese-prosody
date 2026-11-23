# Fixed-text clause-ending experiments

**Project hypothesis.** A change to only the modern Mandarin tone or final at an internal clause ending may be recoverable in the synthesized waveform. A full resynthesis may also change adjacent sounds or timing. This experiment keeps sound-pattern beauty (音律美) and first-read ease (顺口) as separate outcomes for final human validation.

## Design

Use eight excerpts from the [fresh matched prose corpus](../data/pilot/DATA_CARD.md#fresh-works-for-the-historical-feature-benchmark). Two excerpts represent each combination of period and prose genre. Each excerpt has four takes:

- **Base and sham.** Render the same input twice. These takes must have identical WAV hashes.
- **Tone.** Switch the target between modern Mandarin falling tone and either rising or high-level tone. Keep its onset and final.
- **Rhyme.** Change the target's modern Mandarin final while keeping its onset and tone. Reverse final equality against one designated adjacent clause ending. The [site plan](../audio/minimal_ending_sites.json) gives seven intended additions and one intended removal of exact final matches.

All four takes use the same pinned text, number of characters, clauses, punctuation, word breaks, synthesis seed, voice embedding, and nominal speed. Kokoro normally selects an embedding based on phoneme-string length. Use the baseline index for every take in a group. The changed syllables are experimental sound prescriptions. In the tone and rhyme probes they may be unsuitable readings of the printed character. The historical annotation and the dictionary candidates stay tied to the source witness.

## Measurement

Decode the waveform first. The aligner receives the expected pinyin only for linking the single test slot after decoding. Preserve the independently decoded phone and tone labels as drafts. Compare verified whole-WAV duration, matched target duration, the target's late-minus-early F0, adjacent gap duration, and changes at unchanged nearby syllables. For tone, compare the falling-tone take against the rising or high-level take regardless of which was the baseline, and count directional agreement. For rhyme, compare vowel resonances (F1 and F2) using the median of at least three valid voiced frames in the central third of the target. Use the same 5 kHz formant ceiling and extraction settings in all arms. Central formants do not fully describe a nasal coda contrast. Report coverage, missing comparisons, disagreements between the expected and decoded sound, and sham reproducibility alongside the size of each effect. [Praat Burg formant analysis](https://www.fon.hum.uva.nl/praat/manual/Sound__To_Formant__burg____.html)

These are controlled input changes to a modern Mandarin synthesizer. A matching final in the edited recording does not establish historical rhyme practice or listener preference. Edition-level changes of ending words would introduce a lexical intervention and require their own interpretation.

## Direct pitch check

Whole-clip resynthesis did not consistently produce the intended contour. As a secondary check, resynthesize flat and falling pitch tiers from the same baseline recording and center F0. Splice only the target interval with short fades. Verify the same sample count and exact PCM equality outside the edit in each output. The early and late estimates require two voiced frames each. The flat output must stay within 1.25 semitones of zero, and the falling output and its difference from the flat output must each be at least 1.5 semitones downward.

The first pass uses the full linked syllable. The supplemental pass chooses the longest contiguous voiced run within that syllable from the original waveform, before constructing either edit. This improves voiced coverage when the early window includes an unvoiced onset. Preserve both analyses and their failures. The control isolates a pitch target within a known waveform window. Lexical-tone identification still requires separate evidence. [Praat manipulation and overlap-add](https://fon.hum.uva.nl/praat/manual/Manipulation.html) · [Gilbreth results](../reports/stage-5.md#fixed-text-tone-and-rhyme-minimal-pairs)

## Expanded pitch controls and rhyme alignment

Screen the original Mandarin WAVs of all 16 works. Exclude the previously tested ending slots. Select at most one new internal clause ending per work. Eligible sites require a unique linked syllable whose decoded segments match the original prescription, enough contiguous voiced frames for both pitch windows, and an in-band pitch range. Among eligible sites, use the longest voiced run and break ties by position. Site selection uses the original waveform alone. Apply the same flat-versus-falling checks and verify sample equality outside each edit window.

For rhyme, use the cached independent phone decode of the original and edited WAVs. Keep existing usable links and attempt to locate missing targets or adjacent rhyme anchors using the nearest trustworthy, unchanged segment matches. A bracket is accepted only if the interior decoded count agrees with the written slot count and the other interior syllables agree with their expected segments. A terminal anchor can use the end of the clip when two consecutive unchanged matches establish its position. Keep the original decoded final label and confidence. A test can be unavailable or show a different direction from the planned rhyme edit. Mask already linked context syllables in turn to check consistency of the recovery rule against the first pass.

For unresolved endpoints, re-decode the exact source PCM in two local windows with different context and one padded full take. Convert decoder times back to the original sample clock. Locate unchanged flanks by segment agreement and temporal overlap with the cached draft. Accept a new ending only if two or more anchored views agree on its final and timing, with no conflicting eligible view. Check that the new final interval does not compete with another endpoint. The views share the same model and waveform, so agreement checks stability of a draft.

As a separate check, measure spectral shape over central and late portions of the decoded final runs. Compare how far the target is from its rhyme anchor before and after the edit. The features use Hann-windowed log-mel spectra, with overall level excluded. Check whether the conclusion changes when the original anchor spectrum is held fixed. The distance calculation uses the waveform and decoded boundaries and does not read the expected or recognized final category. It is a continuous cue from draft intervals. [Extended analysis and coverage](../reports/stage-5.md#expanded-pitch-controls-and-rhyme-alignment)
