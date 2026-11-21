# Stage 4 pilot audio

The [matched prose pilot](../data/pilot/DATA_CARD.md) supplies the 15 passage IDs and exact text witnesses. Keep waveforms, model caches, environments, manifests and derived data within the private Gilbreth project. Git contains source, rights records and the experiment design. [Human recording sources](HUMAN_SOURCES.md) · [Synthetic recordings](SYNTHETIC.md) · [Acoustic feature definitions](ACOUSTIC_FEATURES.md)

## Pronunciation and alignment

`align.py` analyzes the waveform before it accesses the lexical candidates for aligning syllables. It resamples each Mandarin recording to 16 kHz, normalizes its samples and decodes onset, tone-bearing final, silence and other frame labels with the Charsiu Mandarin frame classifier. The model and its label vocabulary are pinned separately. Its inference head is structurally identical to the Hugging Face Wav2Vec2 CTC head described in the upstream code. The pipeline keeps the 10 ms phone runs, groups acoustic onsets and finals into candidate syllables, and links those events to edition-pinned Han slots with edit alignment. It keeps substitutions, insertions, and omissions as discrepancies. Shared segments with different decoded tones are flagged separately. Historical tone and rhyme play no role in choosing the acoustic events or the links. [Zhu, Zhang and Jurgens, ICASSP 2022](https://doi.org/10.1109/ICASSP43922.2022.9746112) · [Upstream Charsiu project and license](https://github.com/lingjzhu/charsiu) · [Pinned checkpoint](https://huggingface.co/charsiu/zh_w2v2_tiny_fc_10ms/tree/dde9cc1a048e2cb16d0d741deeae5ea9bd634ffe) · [Pinned label vocabulary](https://huggingface.co/charsiu/tokenizer_zh_pinyin/tree/a370e90191d18be4035783a7b98c509666e5c058)

The audio rows distinguish the synthesized input, the model's independent observations (`observed_phone_draft`), and a reviewer-confirmed pronunciation (`realized_reading`). Acoustic decoding can confuse constituents or miss syllables, especially across repeated finals, uncommon diction or phrase boundaries. The tiny frame model was trained with expected phonetic labels. Its tone output is a model inference and must be checked against the waveform and heard speech. `confidence` is a frame posterior summary with no interpretation as calibrated timing accuracy. The pilot Mandarin decoder does not align Cantonese, Minnan, or chanting as if they were Mandarin. Review actual pronunciation and written correspondence before creating a human-passage manifest.

For a hand check, compare the original clip with both the phone and syllable draft intervals. Sample both genres, early and late clause boundaries, a short and an extended acoustic gap, and the context-reviewed readings for 潦 and 還. Mark agreement, timing corrections and readings heard on the waveform in an independent reviewed alignment. Treat low-confidence substitutions and repeated syllables as review candidates. The [feature extractor](features.py) can run with a reviewed alignment file and reviewed interval labels for V/C segments, audible breaths and silence. A tone-bearing final can include a coda, so the automatic final run alone supplies no vowel/consonant segmentation.

## Paths under `${RCAC_SCRATCH}/shunkou`

| Path | Data |
| --- | --- |
| `audio/raw/synthetic/` | Full passage WAVs for the controlled voice and speed conditions |
| `audio/raw/human/` | Rights-cleared source recordings |
| `audio/manifests/synthetic.jsonl` | Text revision, intended pinyin, model provenance, speed, voice and WAV checksum |
| `audio/manifests/human-reference.jsonl` | Independent work-level recordings and rights evidence |
| `audio/derived/alignment/` | Frame-derived phone drafts and linked syllable intervals |
| `audio/derived/features/` | Syllable acoustics, time gaps and per-recording summaries |
| `audio/manifests/listening-pairs.jsonl` | Matched same-voice/speed comparisons plus the multifeature historical wording contrast |
| `audio/manifests/pause-probes.jsonl` | Sample-preserving timing edits and their unchanged waveform counterparts |
| `audio/derived/listening/pause/` | Alternate synthetic WAVs for the pause comparisons |
| `audio/derived/pilot-summary.jsonl` | Audio checksum verification, alignment coverage and aggregate diagnostics |

The paired full-passage WAVs retain their original levels and timings. `pause_probe.py` adds 120 ms of zeros at low-amplitude splice points inside eligible quiet gaps of at least 100 ms. It verifies that removing the inserted samples restores the baseline sample for sample. After checking gap coverage, two punctuation sites in the pilot were selected as technical controls. The annotated Northern Song boundary remains a critic-led test location. Timing-edit WAVs still need listening review. Use the [Gilbreth launch instructions](../hpc/README.md#stage-4-audio-through-the-gateway) for reproduction. The timing distributions of these controlled stimuli do not establish how humans read or judge the passages.
