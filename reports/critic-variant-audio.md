# Timing of recited variants in ten literary examples

**Controlled result.** Su Shi’s four-character transposition 不意自全 → 不自意全 lengthened the changed phrase by 30, 30 and 20 ms in the three synthetic voices. Its final 全 actually shortened by 30, 20 and 20 ms. By comparison, adding the two characters 之上 and then the two characters 之淵 in the known 《峴山亭記》 example lengthened both affected phrases in every voice. The full clip grew by 750–800 ms. A timing change can be measured even where the critic gives no preference, as in the Su example. These data do not identify a better-sounding wording.

## Differences across all 13 comparisons

The three numbers in each row are the complete change in WAV duration in milliseconds, B minus A, in the order `zm_010`, `zf_001`, `zf_002`. The last column uses only phrases with different prescribed Mandarin syllables or syllable order and usable endpoints in both wordings in all three voices. It reports the phrase number and the median change across voices. An asterisk marks agreement on the direction by at least one 10 ms decoder frame in **each** voice. A dash means insufficient shared coverage. The same literary example can appear in more than one row. [Paired texts, witness links and endpoints](../research/critic-variants.json)

| A → B | Complete clip Δ in the three voices (ms) | Changed phrase, median elapsed Δ (ms) |
| --- | --- | --- |
| Xia-A → Xia-B | +250, +175, +75 | 3 +290* |
| Liu-A → Liu-B | −25, +125, 0 | — |
| Yang-A → Yang-B | +400, +575, +725 | 2 −40, 4 +80 |
| Ding-short → Ding-qiao | +450, +500, +500 | — |
| Ding-qiao → Ding-cun | +50, +25, +25 | — |
| Su-A → Su-B | +25, 0, +25 | 2 +30* |
| Wang-A → Wang-B | −50, +150, −100 | 1 +140* |
| Li → Hao | 0, +25, −75 | 2 −200* |
| Teng → Zheng | +50, −25, −100 | — |
| NS01 → NS02, known calibration | +750, +800, +750 | 2 +360*, 3 +200* |
| Ding-tails-A → Ding-tails-B | +925, +1,000, +1,000 | — |
| Zhao-A → Zhao-B | +150, +25, +50 | — |
| Zhao-A → Zhao-C | +25, −25, −25 | — |

Across the 13 rows, 27 phrase comparisons change the spoken input. Eight had a usable elapsed duration in all six relevant WAVs and six of those moved in the same direction by at least 10 ms in all voices. Twelve had a usable final-syllable duration in all six WAVs and five showed that level of directional agreement. In the 丁謂 example, 龔明之 preferred 寸心 because 寸 answers 眾 in the other half. The change 巧心 → 寸心 increased complete clip duration by 25–50 ms. We could not isolate the changed phrase across all three voices. The critic’s literary preference remains a separate outcome.

Of 17 changed **internal** phrase endings, five had evaluable pause incidence on both sides in all three voices. Two had no assigned interval in any recording. The other three had a mixture of detected and undetected events. No changed ending yielded six measured pause durations, so none supports a three-voice comparison of pause length.

## Coverage and checks

| Synthetic voice | Phrase elapsed / 86 | Final syllable / 86 | Internal pause incidence available / 62 | Assigned quiet intervals | Evaluable junctions with no assigned event |
| --- | ---: | ---: | ---: | ---: | ---: |
| `zm_010` | 50 | 59 | 39 | 12 | 27 |
| `zf_001` | 77 | 82 | 57 | 9 | 48 |
| `zf_002` | 61 | 73 | 42 | 8 | 34 |

Gilbreth A10 job `12540466` completed the 24-version set. All 72 analytical WAVs had distinct hashes. In 30 of 30 technical repeat checks, the repeated input reproduced the complete WAV byte for byte. Job `12540451` ran the earlier 19-version packet on another A10 node. All 84 WAVs present in both runs, including technical repeats, matched byte for byte. The analytical recordings yielded 1,073 linked syllables among 1,242 intended positions. Of the links, 969 matched the prescribed segments and tone, and 104 matched segments only. There were 158 substitutions, 11 omissions and 105 insertions. The three presets use one synthesis model. Voice agreement gauges robustness within that model. **音律美** still requires independently grounded aesthetic evidence. **顺口** requires a separate first reading. No participants took part.

## What the measurements mean

Each version is one continuous synthetic Standard Mandarin (普通話) reading with the punctuation and numbered pinyin in the source packet. Three established Kokoro presets read each version, at speed 0.9. Within each literary example, all voices and wordings use the same random seed and the same numerical index into each voice’s embedding table. The voice vectors themselves differ. The first version in every family is synthesized a second time in every voice to check reproducibility. Citation tones are input choices. The decoder can still hear a different tone, a different syllable or no matching syllable. [Source forms and reading decisions](../research/critic-variants.json) · [Pinned Kokoro model and voice assets](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/tree/01e7505bd6a7a2ac4975463114c3a7650a9f7218)

Complete clip duration comes directly from the number of samples in each original 24 kHz, mono, 16-bit WAV, including silence. For each written phrase, Charsiu first decodes phone runs from the waveform on a 10 ms grid. The runs are then linked to the prescribed syllables by segmental identity, allowing a tone mismatch. Phrase duration spans the first linked sound of the initial character to the last sound of the final character. It includes the time occupied by anything between those endpoints. Final-syllable duration includes its detected onset and final. Either measure is missing whenever an endpoint it needs is unavailable. [Pinned Charsiu classifier](https://huggingface.co/charsiu/zh_w2v2_tiny_fc_10ms/tree/dde9cc1a048e2cb16d0d741deeae5ea9bd634ffe) · [Waveform decoder and linking rules](../audio/align.py)

The frozen noise-aware detector searches the WAV for quiet intervals of at least 100 ms and attempts to assign each interval to an internal character junction. At an evaluable junction with two consecutive matched syllables we record whether an interval was assigned. Only an assigned interval supplies a pause duration. An unlinked junction, a detector failure or the end of the clip has unknown incidence and duration. Punctuation locates the positions we compare. [Detector](../src/quantitative_noise_aware_detector.py) · [Assignment rule](../src/quantitative_pause_match.py) · [Measurement code](../src/critical_variant_audio.py)

## Reproduction on Gilbreth

Under the project root, `results/critical-preferences-5JRVYyHR/audio-24/` holds the final run. The pinned packet used by the GPU is `acoustic-code/research/critic-variants-24.json` in the same run directory. `audio/manifests/synthetic.jsonl` identifies each waveform, voice, seed, embedding index, speed, pronunciation input, text edition, model license and content hash. The original WAVs, decoded phone sequences, slot-by-slot matches and exclusions stay on Gilbreth. `measured.json` contains the individual phrase results and `summary.json` the matched comparisons. Reproduce in a new project directory with the pinned Stage 4 environment. [Slurm runner](../hpc/critical-variant-audio.sbatch)

```bash
sbatch --account="$account" --qos=normal hpc/critical-variant-audio.sbatch \
  "$project" "$code" "$stage4_env" "$config" "$new_output"
```
