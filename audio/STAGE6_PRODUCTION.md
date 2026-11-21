# Stage 6 reading aloud

Reading ease (順口, 顺口) is how easily a reader can produce a passage on a first read. This task measures production separately from the listening task on sound-pattern beauty (音律美). The read-aloud excerpts come from two period-matched pairs of parallel prose (駢文, 骈文) and comparison prose (散文). The four excerpts and their source works are separate from the listening set. The text uses the exact edition and punctuation pinned in Stage 3. Reader materials show only the prompt codes and text. The research key with sources, pairings, and genres stays under the restricted directory.

## First-read task

1. Use the reading task after finishing and submitting the blind listening judgments. Open one prompt at a time, with the others closed. Use your usual pronunciation for Classical Chinese and read at a natural pace. Begin as soon as the text appears. Keep going through pauses, starts, corrections, and repetitions. Read once and keep that take. A reader can skip any item. Avoid rereading the prompts, looking up characters, or listening to a model before the first attempt.
2. For an optional recorded trial, use a quiet room and one file per passage. Start recording before revealing the text and stop after the passage. Use consent below first. The research copy and its derivatives stay in the Gilbreth project directory. Names and personal information should stay out of recordings and filenames.
3. After each attempt, rate how easy it felt on a 1–7 scale. Give 1 for very difficult to say, 4 for moderate, and 7 for very easy to say. Mark any passage you remember having read before and any items you skipped. Example response `R01=6 R02=3 R03=4 R04=5 以前讀過=R02`. The rating-only self-test can be done without recording. Self-ratings and objective measures are separate outcomes.

## Optional author self-trial and consent

An author self-trial checks usability, intake, and feasibility. Existing familiarity should be logged. This stage does not invite, enroll, or record other people. Before any reader study, obtain the applicable institutional determination, define project access, retention and withdrawal terms, and use the approved consent materials.

Proposed consent for the author's voluntary self-trial, to be affirmed before uploading a recording:

> 我自願參加這次初次朗讀試測。我可以跳過任一段，也可以隨時停止。我同意把這次朗讀錄音及相關評分、標註與衍生測量資料保存在 Gilbreth 的研究專案中，供經授權的研究人員分析語速、停頓、猶豫、改口和重讀。我知道聲音可能使人辨認出我的身分。研究方須另行取得我的同意，才能公開或另作他用。若要撤回，我可用讀者代號聯絡研究負責人，要求刪除仍能連結到我的試測資料。

Keep the affirmative record with the protocol version, speaker code, variety, style, consent ID and scope. Limit access to the researcher and authorized reviewers for this use. For future study consent, also record the approved scope and retention and withdrawal details. Treat WAVs as identifiable by voice even when they lack names. Do not put consent records, question responses, voice data, or drafts linked to an individual in Git or a public survey. The participant task contains no tracking or upload code.

## Gilbreth operation

Run from the project source directory with the Gilbreth data path set as `SHUNKOU_ROOT`. Prepare the task with the annotated pilot in place.

```bash
python3 -m src.stage6_production prepare --root "$SHUNKOU_ROOT"
```

The reader files are `audio/stage6/production/read-aloud.html` and `task.json` under the data root. The key is `audio/stage6/restricted/production-key.json`. Provide the reader files separately from the key and preserve the Git-tracked attribution in the [pilot data card](../data/pilot/DATA_CARD.md). The four texts are in the public domain. The pinned Wikisource transcription and punctuation layer carries CC BY-SA 4.0.

After affirmative consent and human recordings are available, use a private directory for the reader's data. Create it on Gilbreth with read/write permissions reserved for the owner and place each PCM WAV there as `R01.wav` through `R04.wav`. Readers can provide a subset of the four. Keep only the first take. Any conversion to PCM should occur on Gilbreth, preserving the original and recording its relationship to the PCM file in the local study log.

```text
$SHUNKOU_ROOT/audio/raw/human/stage6/<reader_code>/R01.wav
$SHUNKOU_ROOT/audio/stage6/restricted/production/<reader_code>/consent.json
```

For example, the matching consent record can use the following fields. Set `affirmed` only after obtaining consent. The sample codes are placeholders for the reader's study code and recorded consent identifier. `variety` records the actual reading pronunciation variety. Use `cmn` only for a confirmed Mandarin reading. The future-use scope `approved_research_study` requires separate authorization.

```json
{
  "version": "stage6-read-aloud-v1",
  "reader_code": "author-01",
  "consent_id": "consent-01",
  "scope": "author_self_trial",
  "affirmed": true,
  "variety": "cmn",
  "style": "usual cold read-aloud"
}
```

Use file mode 600 for consent and WAV files, and 700 for each reader folder. The manifest verifies source text, rights and the checksum and duration of each actual waveform. Review and output files are private by default.

```bash
reader_data="$SHUNKOU_ROOT/audio/stage6/restricted/production/author-01"
python3 -m src.stage6_production draft-manifest --root "$SHUNKOU_ROOT" \
    --consent "$reader_data/consent.json"
```

For actual Mandarin audio, the Stage 4 waveform-first decoder may run inside a Slurm GPU job using the current `audio/align.py` and the existing Stage 4 environment. The produced draft links retain the waveform hash. Other varieties can use manual waveform review. Neither the historical tone/rhyme categories nor a synthetic reference define the pronunciation the reviewer must hear.

```bash
python3 audio/align.py --root "$SHUNKOU_ROOT" --offline \
    --recordings "$reader_data/recordings.jsonl" --out-dir "$reader_data/alignment"
```

Review the waveform and record neutral event labels with timestamps. Draft substitutions and omissions can point to regions to review. They are not disfluency labels or evidence that a specific pronunciation was performed. An acceptable variant pronunciation is not itself a disfluency. Keep ambiguous readings unresolved where they cannot be heard reliably. Assign `reviewer_code` and copy `review-template.jsonl` to `reviewed-clauses.jsonl` before making edits. Keep the original recording ID, waveform hash, and zero-based clause index. Mark every reference clause `verified`, `omitted`, or `unscorable`. Leave time, syllable count, and event data empty for omitted or unscorable clauses. The latter covers clipping, noise, or uncertainty that defeats time or event coding.

For a verified clause, enter the onset and offset of the initial attempt in seconds from WAV start and the number of actual syllables heard during that interval. Count complete syllables in starts and repairs, repeated syllables, and syllabic fillers. Exclude partial non-syllabic starts. A later complete restart of a clause can be timestamped separately as a `reread`. If this takes place after the initial clause interval, its syllables do not contribute to the first-attempt rate. Use an event object such as `{"type":"hesitation","start_s":1.12,"end_s":1.48}` for each occurrence. Apply the following codes consistently.

| Code | Rule |
| --- | --- |
| `pause` | Within-clause silence of at least 200 ms between speech, without treating low-amplitude closure as an extra pause. |
| `hesitation` | Audible filler or marked hesitation lengthening before continuation. An ordinary boundary lengthening is insufficient on its own. |
| `false_start` | An incomplete or abandoned onset before the reader continues. |
| `repair` | Audible self-correction of produced material, including a changed word or reading. |
| `reread` | Deliberate repeat of a complete phrase or clause anchored to the clause first attempted. Assign each event once. |

If a single interruption fits multiple disfluency codes, apply the primary category (`reread`, then `repair`, then `false_start`, then `hesitation`) and optionally add a separate timed silent pause. Standardize these rules on a few approved calibration recordings before coding study data. Omission here describes a missing entire clause. Partial omissions and pronunciation choices can be preserved in separate waveform-review notes without equating them with observable hesitation.

```bash
python3 -m src.stage6_production analyze --root "$SHUNKOU_ROOT" \
    --reader-code author-01 --review "$reader_data/reviewed-clauses.jsonl"
```

Add `--alignments "$reader_data/alignment/alignments.jsonl"` when waveform-derived links are available for these exact files. The optional draft counts in the private `summary.json` remain separate from the reviewed clause measures.

## Measures and analysis

The primary timing measure is actual heard syllables per second between reviewed clause onset and offset, including internal pauses. A second rate excludes only logged silent gaps at or above the specified 200 ms threshold. The per-clause data include internal pause locations and durations, the gap between adjacent scored clauses, and timed counts of hesitations, false starts, repairs, and re-reads. The inter-clause gap excludes leading and trailing recording silence and is unavailable when either neighboring clause is missing or unscorable. Audible breathing can fall inside that gap, so it is a gap between speech intervals. A zero count means the reviewer heard no events. Missing or unscorable measures stay null.

For an author self-trial, display the four prompt ratings and scored clause measures with coverage. Examine alignment disagreements at the affected spans. Describe within-reader contrasts and any familiar excerpts. No population inference is supported by one reader and four texts.

For a later reader study, counterbalance prompt orders while preserving no preview and the order of the two tasks. Record self-reported variety, prior familiarity and Classical Chinese reading experience. Preserve genre masking for coders when feasible, report agreement in event type and timing on an independently coded subset, and adjudicate disagreements. For an expanded corpus, estimate effects using reader and work as grouping factors with within-pair comparisons. Include length, unfamiliar vocabulary, familiarity, and period. Compare rates and counts separately with the ordinal ease ratings. Keep listening ratings as a separate outcome. The project hypothesis is that some formal or lexical features predict production difficulty even in passages with favorable listening judgments. English read-aloud experiments support coding production errors and self-correction separately. Their reading manipulations and findings do not establish the proposed link in Chinese. [Gollan and Goldrick, 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6367048/)
