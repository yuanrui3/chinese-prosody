# Running on Gilbreth

Gilbreth is the working location for GPU synthesis, GPU-based alignment and inference, and bulk research data. Keep source, manifests, data cards, and compact reports in Git. Keep downloaded corpora, model weights, environments, working audio, intermediate alignments, and job logs in `${RCAC_SCRATCH}/shunkou`. Copy rights-cleared originals that cannot be reconstructed, reviewed alignment labels, and release outputs to a project-owned Data Depot location or to Fortress. RCAC can purge scratch files after 60 days of inactivity. [RCAC file storage](https://docs.rcac.purdue.edu/userguides/gilbreth/storage/) · [Scratch policy](https://docs.rcac.purdue.edu/userguides/gilbreth/storage/scratch_space/)

On Gilbreth, use `myquota` to verify available space and `slist` to find your Slurm account and GPU allocation. Use standby for short jobs that can wait for idle capacity. Run all substantive workloads through Slurm. [Slurm accounts, partitions, and QOS](https://docs.rcac.purdue.edu/userguides/gilbreth/run_jobs/queues/) · [Submitting jobs](https://docs.rcac.purdue.edu/userguides/gilbreth/run_jobs/submit_script/)

## Stage 3 through the Gateway

Use the Purdue career account to sign in to the [Gilbreth Gateway](https://gateway.gilbreth.rcac.purdue.edu/). In **Files → Scratch → shunkou**, upload a copy of `data/` and `hpc/stage3-pilot.sh` packaged with their repository-relative paths. Open the Gateway shell to unpack the source bundle and run the bounded pilot build. Python 3.9.25 on Gilbreth was used for the verified build and there are no third-party Python dependencies.

```bash
root="${RCAC_SCRATCH:-$(findscratch)}/shunkou"
bash /path/to/unpacked-source/hpc/stage3-pilot.sh "$root"
```

The build writes the pinned passage corpus, candidate readings, and coverage summary to `$root/data/pilot/` and creates the directories for future audio under `$root/audio/`. The code and data cards stay in Git. The two anthology and verse importers are described in the [Stage 3 collection cards](../data/collections/DATA_CARDS.md). Use a CPU-capable compute allocation for bulk CPU-only normalization and keep the resulting corpus in the Gilbreth project. Gilbreth batch jobs require GPU use. [Gateway documentation](https://docs.rcac.purdue.edu/userguides/gilbreth/gateway/) · [Purdue cluster guidance](https://docs.rcac.purdue.edu/workshops/hpc_exchange/week2/clusters/#gilbreth)

## Stage 4 audio through the Gateway

Upload a source bundle containing `audio/` and `hpc/stage4.sbatch` to the same scratch project through the Gateway. Unpack it in the Gateway shell. Submit from the shell using the Slurm account displayed by `slist`.

```bash
root="${RCAC_SCRATCH:-$(findscratch)}/shunkou"
source_root="$root/path-to-unpacked-stage4"
sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=standby \
  --chdir="$root" --output="$root/logs/stage4-%j.log" \
  "$source_root/hpc/stage4.sbatch" "$root" "$source_root"
```

That invocation targets all 15 passages. Append specific passage IDs for a smaller test. The script uses one GPU, builds or reuses a pinned Python 3.12 and CUDA environment in scratch, and writes `installed.txt` alongside the environment. Model assets and installed dependencies are cached in scratch. Check completion with `sacct -X -j JOB_ID --format=JobID,State,ExitCode,Elapsed,AllocTRES` and review the job log. The [Stage 4 data card](../audio/README.md) describes the audio and how to review pronunciation evidence.

```bash
module load anaconda/2024.10-py312
PYTHONDONTWRITEBYTECODE=1 python "$source_root/audio/check_pilot.py" --root "$root"
PYTHONDONTWRITEBYTECODE=1 python "$source_root/audio/pause_probe.py" --root "$root"
```

The batch job also runs these two checks. Run them separately to rebuild the listening manifest and timing-only probes from existing audio and features. The standard-library tools verify the WAV headers, checksums, and sample preservation.

## Stage 5 validation through the Gateway

Upload `src/`, `tests/`, `data/phonology/*.py`, `data/pilot/context-reviews.json`, and `hpc/stage5.sbatch` together with their repository paths. The job reads the existing pilot annotations and Stage 4 derived tables in scratch. It reuses the completed Stage 4 Python environment and batches the control-statistic reductions on one GPU.

```bash
root="${RCAC_SCRATCH:-$(findscratch)}/shunkou"
source_root="$root/path-to-unpacked-stage5"
stage4_env="$root/env/path-to-completed-stage4-environment"
sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=standby \
  --chdir="$root" --output="$root/logs/stage5-%j.log" \
  "$source_root/hpc/stage5.sbatch" "$root" "$source_root" "$stage4_env"
```

The job runs the fixtures and the live annotation check, then writes `results/stage5/validation.json`, including input hashes, control tests, matched-pair effects, and audio comparisons. The default run uses seed `20261121` and 999 draws per control and reference tier. `python -m src.pilot_validation --root "$root" --device cpu` runs the same reductions for a local or CPU-equipped execution environment with the inputs present. Use a Slurm compute job for substantive validation on Purdue systems.

### Synthetic timing benchmark

From a source checkout on Gilbreth, run the bounded benchmark against the existing male-voice and independent-work WAVs. It reads nine short recordings and requires no GPU. The benchmark checks exact text and audio hashes, a common synthesis condition, and disjoint works and authors. It fits on the original matched prose and saves the expansion predictions and per-work errors under `$root/results/model-development/synthetic-timing.json`. [Measured results](../reports/stage-5.md#work-held-out-synthetic-timing-benchmark)

```bash
python3 -B -m src.timing_benchmark --root "$root"
```

### Historical tone and rhyme on fresh works

Upload the code archive with `data/pilot/historical-increment.json`, `audio/historical_increment_readings.json`, the Stage 3 and Stage 4 builders, the source modules, and `hpc/historical-increment.sbatch`. The isolated output directory is `$root/model-development/historical-increment`. With restricted Wikimedia access, keep the reviewed pre-edit witness spans in `data/pilot/reviewed-witnesses.json` under that directory. The builder verifies every excerpt against the manifest and reuses the pinned lexicon and audio caches.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/historical-increment-%j.log" \
  "$code/hpc/historical-increment.sbatch" "$root" "$code" "$stage4_env"
```

The job renders and aligns the fresh WAVs on one GPU. It writes the work-held-out duration predictions and feature-permutation controls to `results/historical-increment/duration.json`, and the Stage 5 structural control and audio checks to `results/historical-increment/stage5.json`, both under the isolated output directory. No participant input is used. [Benchmark design](../research/historical-increment.md) · [Corpus and primary witnesses](../data/pilot/DATA_CARD.md#fresh-works-for-the-historical-feature-benchmark)

### Fixed-text tone and rhyme controls

Use the pinned Stage 4 environment and the annotated fresh prose from the historical-feature benchmark. Upload the `audio/` Python modules, `audio/minimal_ending_sites.json`, `audio/historical_increment_readings.json`, `src/`, and `hpc/minimal-endings.sbatch` with their repository paths.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/minimal-endings-%j.log" \
  "$code/hpc/minimal-endings.sbatch" "$root" "$code" "$stage4_env"
```

The job renders, decodes, and measures four takes at each of eight sites, with the tones and finals varied in separate arms. The exact audio, synthetic prescriptions, draft alignments, and `results/minimal-endings/analysis.json` remain under `$root/model-development/minimal-endings`. The analysis verifies WAV hashes and matches each sham to its baseline. [Design and measurement limits](../research/minimal-endings.md)

Run the two bounded direct pitch checks from the same source checkout after loading Anaconda and the pinned Stage 4 interpreter. These CPU checks reuse the baseline WAVs and draft target windows. They write the two pitch-control JSON files alongside the main analysis and keep the edited WAVs under the experiment's `audio/raw/pitch-controls/`.

```bash
experiment="$root/model-development/minimal-endings"
module load anaconda/2024.10-py312
"$stage4_env/bin/python" -B -m src.minimal_pitch_control --root "$experiment"
"$stage4_env/bin/python" -B -m src.minimal_pitch_control --root "$experiment" --voiced-core
```

### Expanded pitch controls and rhyme alignment

Run these bounded CPU checks from the source checkout in the same pinned environment. They read the original and edited WAVs and cached phone drafts. All new WAVs and JSON files go to the isolated extension directory.

```bash
original="$root/model-development/historical-increment"
experiment="$root/model-development/minimal-endings"
extension="$root/model-development/ending-control-extension"
results="$extension/results/minimal-endings"
"$stage4_env/bin/python" -B -m src.pitch_control_extension --source "$original" --root "$extension" \
  --previous-sites audio/minimal_ending_sites.json
"$stage4_env/bin/python" -B -m src.rhyme_final_recovery --root "$experiment" --output "$results/rhyme-alignment.json"
"$stage4_env/bin/python" -B -m src.rhyme_spectral --root "$experiment" \
  --recovery "$results/rhyme-alignment.json" --output "$results/rhyme-spectral.json"
```

The supplemental step uses one GPU to check unresolved ends with different audio context. Upload `hpc/rhyme-window-redecode.sbatch` and the source modules with the extension checkout. The bounded job keeps the initial recovery report and writes separate rhyme-window alignment and spectral reports in the extension's results directory.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/rhyme-window-%j.log" \
  "$code/hpc/rhyme-window-redecode.sbatch" "$root" "$code" "$stage4_env"
```

### Fixed-text recitation phrasing

Deploy the three `src/recitation_phrasing*.py` modules and `hpc/recitation-phrasing-audit.sbatch` with the existing Stage 5 checkout. The bounded waveform checks read the existing male Mandarin WAVs and alignments. They write derived WAVs, screening results, and the independent waveform measurements under the experiment directory. The optional phone re-decode requires one GPU and uses the pinned Stage 4 environment.

```bash
experiment="$root/model-development/recitation-phrasing"
umask 077
cd "$code"
python3 -B -m src.recitation_phrasing --root "$experiment" \
  --guide "$root/listening-rounds/mandarin-male" --fresh "$root/model-development/historical-increment"
python3 -B -m src.recitation_phrasing_analysis --root "$experiment"
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/recitation-phrasing-%j.log" \
  "$code/hpc/recitation-phrasing-audit.sbatch" "$root" "$code" "$stage4_env"
```

### Recitation alignment extension

Deploy the updated phrasing builder, `src/recitation_phrasing_extension.py`, `src/recitation_guide_recovery.py`, `src/recitation_pcm_alignment.py`, `src/recitation_context_decode.py`, and `hpc/recitation-alignment-audit.sbatch` with the prior phrasing checkout. Use the existing waveform and decoder reports in the original experiment. The extension retains the original WAVs by hash and adds a new pair only if the guide clause passes contextual recovery and the original splice checks. Exact sample alignment and context-window phone decoding write separate results.

```bash
prior="$root/model-development/recitation-phrasing"
experiment="$root/model-development/recitation-phrasing-alignment"
comparison="results/recitation-phrasing"
umask 077
cd "$code"
python3 -B -m src.recitation_phrasing_extension --root "$experiment" --prior "$prior" \
  --guide "$root/listening-rounds/mandarin-male"
python3 -B -m src.recitation_pcm_alignment --root "$experiment" \
  --decoder "$prior/$comparison/decoder.json" --decoder-manifest "$prior/$comparison/stimuli.json"
python3 -B -m src.recitation_phrasing_analysis --root "$experiment"
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/recitation-alignment-%j.log" \
  "$code/hpc/recitation-alignment-audit.sbatch" "$root" "$code" "$stage4_env"
```

#### Second Mandarin aligner

Deploy `src/recitation_second_aligner.py`, `src/recitation_second_aligner_analysis.py`, `hpc/recitation-funasr.sbatch`, and `hpc/requirements-funasr.txt` with the alignment extension. The runner uses the pinned Stage 4 interpreter and builds a separate FunASR 1.2.7 overlay. It pins the model revision and verifies the model weights by SHA-256. The first run needs outbound access to the PyTorch CUDA wheel index, PyPI, and Hugging Face. All caches live in the Gilbreth project directory. [Model checkpoint](https://huggingface.co/funasr/fa-zh/tree/d7701644d6e336f093501241beca010519c0986f)

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/recitation-funasr-%j.log" \
  "$code/hpc/recitation-funasr.sbatch" "$root" "$code" "$stage4_env"
```

The job reads the verified carrier and both variants from each pair. It writes `forced-alignment.json` and `second-aligner-comparison.json` alongside the waveform report in `model-development/recitation-phrasing-alignment/results/recitation-phrasing/`. The comparison pairs character midpoint shifts with shifts of identical waveform cores. It also reports model span gaps separately. The predictor uses the supplied character count to estimate timing, so a time span assigned to a character does not verify its pronunciation.

#### Single-recording pause benchmark

Deploy `src/recitation_pause_estimator.py` with the second-aligner checkout. This bounded CPU check reads the 26 existing treatment WAVs and their hash-bound alignments. Each feature computation uses one WAV and its FunASR timings. The benchmark separately compares the inferred changes to exact PCM shifts and selects a quiet threshold with each work held out. It writes `single-take-pauses.json` in the same results directory. [Measured results](../reports/stage-5.md#measuring-pauses-from-a-single-recording)

```bash
cd "$code"
python3 -B -m src.recitation_pause_estimator --root "$root/model-development/recitation-phrasing-alignment"
```

#### Second-voice pause transfer

Deploy `hpc/recitation-voice-transfer.sbatch` with both `src/recitation_voice_transfer*.py` modules, the updated synthesis and phrasing modules, and the original `audio/synthetic_readings.json` and `audio/historical_increment_readings.json` recipes. Use the checksum-bound first-voice results, Stage 4 environment and the existing FunASR overlay. The job runs offline using the project model caches. It renders the same passages in Kokoro `zf_001` at speed 0.9 using the original voice's seeds. New audio and outputs are isolated in `model-development/recitation-voice-transfer`.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/recitation-voice-transfer-%j.log" \
  "$code/hpc/recitation-voice-transfer.sbatch" "$root" "$code" "$stage4_env"
```

The job records how it located both splices in each original clause and checks the exact waveform change before scoring. Both versions of a given pair have the same sample count. Each voice retains its own synthesized timing. `render-screen.json` records every requested site and `voice-transfer.json` compares the two voices using the same frozen −50 dBFS threshold, FunASR model and exact PCM reference. These files, the model's draft timestamps, and the WAVs stay on Gilbreth.

If synthesis and the source phone drafts finished before a later step failed, pass `resume` after `"$stage4_env"` to reuse those checksum-bound baselines. The job rechecks stimulus lineage and exact PCM before estimating the pauses.

### Quantitative report on fresh works and two voices

Deploy `src/quantitative_report.py`, `hpc/quantitative-report.sbatch`, `data/pilot/voice-report.json`, `audio/voice_report_readings.json` and their Stage 3 and Stage 4 dependencies. If using an offline source snapshot, stage `model-development/quantitative-report/data/pilot/reviewed-witnesses.json` inside the project directory. The builder checks its passages against the exact pinned anchors and hashes. The job checks the new works and credited authors against four existing inventories before synthesis. Both voices use speed 0.9, the same intended phonemes and the same seed per passage. [Source inventory](../data/pilot/voice-report.json)

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/quantitative-report-%j.log" \
  "$code/hpc/quantitative-report.sbatch" "$root" "$code" "$stage4_env"
```

The job writes `report.md`, `report.json` and `freshness.json` under `model-development/quantitative-report/results/quantitative-report`. The WAVs and phone drafts stay within the same project experiment. To rebuild the report from the completed feature tables, invoke the report module against that experiment. Use an output name distinct from the existing verified release if comparing versions.

```bash
experiment="$root/model-development/quantitative-report"
cd "$code"
"$stage4_env/bin/python" -B -m src.quantitative_report --root "$experiment" \
  --output "$experiment/results/quantitative-report/recheck.json"
```

#### Second alignment on the existing recordings

Deploy `hpc/quantitative-report-secondary.sbatch`, `hpc/requirements-funasr.txt`, and the current `src/` into the same source checkout with the original witness and reading files. This job requires the pinned Stage 4 environment and the cached FunASR overlay and model from the recitation experiment. It reads the 16 existing WAVs with their original checksums and runs full-passage timestamp inference on one A10.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/quantitative-second-%j.log" \
  "$code/hpc/quantitative-report-secondary.sbatch" "$root" "$code" "$stage4_env"
```

The job writes `secondary-alignment.json`, `report-v3.json`, and `report-v3.md` under the same private results directory. If inference succeeded and report generation failed, resubmitting reuses the saved alignment after checking its input hashes, model identity, and exact WAV and text links. Raw timestamp coverage, anchor-supported elapsed spans, and the original complete articulation remain distinct measures. The report includes separate voice counts, intersection coverage and timings, and the work-held-out count comparison.

#### Waveform check of the alignment offset

Deploy `hpc/quantitative-report-offset.sh` with the updated source into the same checkout. Run this bounded CPU check from a Gilbreth Gateway shell. It uses the existing 16 WAVs and saved alignments. It checks the v3 report and alignment hashes before and after the rerun and writes `report-v4.md` and `report-v4.json` in the private results directory.

```bash
bash "$code/hpc/quantitative-report-offset.sh" "$root" "$code" "$stage4_env"
```

The JSON preserves the waveform landmarks and threshold ranges, the matching rule for internal pauses, the estimates and errors by voice, and the correction fitted for each held-out work. [Method and results](../reports/stage-7.md#waveform-check-of-the-80-ms-offset)

#### Independent onset transfer

Stage the v4 source checkout, `hpc/quantitative-onset-transfer.sbatch`, `hpc/requirements-funasr.txt`, and the historical-increment source and reading files. This run copies the archived annotations into a private experiment and renders both voices for the complete 16-work cohort. It uses the same intended pronunciations, nominal speed, and per-passage seed in both voices. The scorer freezes the onset adjustment using v4 and verifies that the evaluation works and authors are disjoint from v4.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/onset-transfer-%j.log" \
  "$code/hpc/quantitative-onset-transfer.sbatch" "$root" "$code" "$stage4_env"
```

The private output is under `model-development/quantitative-onset-transfer/results/onset-transfer`. Use `resume` after the environment argument if synthesis finished and a downstream step needs a retry. The Markdown and JSON reports include the same-work comparison in both voices, abstentions, and the raw and fixed-shift baselines.

#### Recording onset in a held-out voice

After the two-voice transfer completes, deploy `hpc/quantitative-third-voice.sbatch` and the third-voice scorer. The job renders the same 16 evaluation works using `zf_002` and scores it with the frozen v4 correction. It reports both individual denominators and the same-work intersection across all three voices. Results live in `model-development/quantitative-onset-third-voice/results/third-voice`.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/quantitative-third-%j.log" \
  "$code/hpc/quantitative-third-voice.sbatch" "$root" "$code" "$stage4_env"
```

#### Internal pauses with generator-assisted labels

Stage `hpc/quantitative-internal-check.sbatch` and the current source with the original voice-report reading file. The job regenerates the v4 takes in a dedicated private directory to capture Kokoro's token-duration draft. It only uses the draft for punctuation correspondence when the regenerated WAV and its samples match the original exactly. The audio itself supplies the pause edges.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/quantitative-internal-%j.log" \
  "$code/hpc/quantitative-internal-check.sbatch" "$root" "$code" "$stage4_env"
```

The separate `internal-pause-check.json` stays alongside report v4. The original report and waveforms remain available for comparison.

#### Native pauses and held-out clause assignment

Deploy `src/quantitative_pause_match.py`, both pause report modules and the Slurm runner atop the controlled-join checkout. The bounded CPU check remeasures the 13 pauses from the original private WAVs and joins each proposed match to the saved phone evidence. It expects the original v4 and generator-check results.

```bash
exp="$root/model-development/quantitative-report"
res="$exp/results/quantitative-report"
cd "$code"
umask 077
flock -n "$exp/.quantitative-report.lock" timeout 90s "$stage4_env/bin/python" -B \
  -m src.quantitative_pause_native --root "$exp" --output "$res/native-pause-boundaries.json" \
  --markdown "$res/native-pause-boundaries.md"
```

The held-out GPU check replays the archived controlled joins in memory using the cached FunASR model. It gives the matcher all character starts and checks its chosen position against the sample-exact join. It reports the full detection pipeline and a second test that supplies a sample-defined splice and stable waveform resumption. It also runs the same matcher on the unchanged donor WAVs to record native coverage.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/quantitative-pause-%j.log" \
  "$code/hpc/quantitative-pause-benchmark.sbatch" "$root" "$code" "$stage4_env"
```

The benchmark reports remain under `model-development/quantitative-pause-benchmark/results-v2`. The initial detector-only report remains in the adjacent `results` directory. The WAVs remain in their original private experiments.

#### Recording-relative pause detection

Deploy both detectors, the control modules, and `hpc/quantitative-pause-detector.sbatch` with the expansion source and reading pins and the earlier onset-transfer modules. The job copies the expansion annotation inventory unchanged and renders only the four works with pinned synthesis recipes in three voices. It tests exact insertions within a waveform and known positions at the join between two full original recordings. The job leaves the participant materials untouched.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/pause-detector-%j.log" \
  "$code/hpc/quantitative-pause-detector.sbatch" "$root" "$code" "$stage4_env"
```

Run the additional noise stress test against the same checksum-bound carriers with the pinned interpreter.

```bash
experiment="$root/model-development/quantitative-pause-detector"
cd "$code"
umask 077
flock -n "$experiment/.detector.lock" timeout 120s "$stage4_env/bin/python" -B \
  -m src.quantitative_pause_noise --project "$root" --root "$experiment" \
  --output "$experiment/results/noise.json" --markdown "$experiment/results/noise.md"
```

The reports are in the experiment's private `results` directory. Variants are assembled in memory.

For the second, newly sourced four-work cohort, deploy `data/pilot/pause-replication.json`, `audio/pause_replication_readings.json`, and the same detector and control modules. Place the reviewed witness snapshot under `$root/sources` when using the offline builder.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/pause-replication-%j.log" \
  "$code/hpc/quantitative-pause-replication.sbatch" "$root" "$code" "$stage4_env" "$snapshot"
```

The replication results remain in `model-development/quantitative-pause-replication/results`. The build checks the new source inventory against all four earlier cohorts.

#### Noise-aware pause detection

Deploy the noise-aware detector, both assessment modules, and `hpc/quantitative-noise-aware.sbatch` atop the completed fresh-work replication checkout. The job reads the same 12 verified WAVs and replays their clean joins before testing paired background noise. It leaves the previous results and recordings in place. The exact interior-insertion test scores both timing edges without a decoder. The join test checks clause assignment and compares the estimated resumption with the independently measured clean donor onset where available.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/noise-aware-%j.log" \
  "$code/hpc/quantitative-noise-aware.sbatch" "$root" "$code" "$stage4_env"
```

The reports are `noise-aware-inserts.md`, `noise-aware-joins.md`, and their JSON counterparts in `model-development/quantitative-pause-replication/results`. The job stages output pairs privately and reuses a completed pair on retry. Mixed waveforms are assembled in memory. The original audio and model caches stay on Gilbreth.

#### Natural Mandarin pause benchmark

The November 22 run is in `$root/results/native-pause-20261122`. Use the pinned Stage 4 Python from a checkout with `src/quantitative_mandi_*.py`, `src/quantitative_native_pause_eval.py`, and the frozen detector. The import and scoring are small CPU runs. The archive manifest includes the corpus terms, file version metadata, and WAV checksums. Verify the source hashes in every evaluation against that manifest. [ManDi archive](https://osf.io/fgv4w/)

```bash
umask 077
prior="$root/results/native-pause-20261122"
run=$(mktemp -d "$root/results/native-pause-rerun.XXXXXX")
py="$stage4_env/bin/python"
cd "$code"
timeout 140s "$py" -B -m src.quantitative_mandi_fetch --output "$run/corpus"
"$py" -B -m src.quantitative_mandi_references --corpus "$run/corpus" \
  --output "$run/archive-reference.json"
"$py" -B -m src.quantitative_mandi_references --corpus "$run/corpus" \
  --visual-annotations "$prior/mandi-visual-annotations-20261122.json" \
  --output "$run/visual-reference.json"
for tier in archive visual; do
  timeout 30s "$py" -B -m src.quantitative_native_pause_eval --audio-root "$run/corpus" \
    --references "$run/$tier-reference.json" --output "$run/$tier-evaluation.json"
done
```

Reuse the frozen labels with the same WAV hashes and scored windows. If the release changes, use the preserved archive or create a new review. To reproduce the blind views, run `src.quantitative_mandi_waveforms` as a module with `--audio-root`, `--references` pointing to the archive reference, and `--output` pointing to a private plot directory. The render uses the pinned Stage 4 NumPy and SciPy plus Pillow 11.3.0 in a scratch-only package directory. Review the images before opening detector outputs. Full archive association and waveform-review results have separate JSON files. [Checkpoint](../reports/stage-7.md#noise-aware-pause-detection-in-natural-mandarin-readings)

#### Miss audit and held-out pause transfer

Use the staged archives and original developed and held-out labels on Gilbreth. The run compares whole decoded PCM files using the same two reference inventories and masks. The CPU commands use the pinned Stage 4 Python and an updated checkout with the diagnostics, transfers and opt-in bridge. [Held-out checkpoint](../reports/stage-7.md#miss-audit-and-weak-interruption-bridge-on-held-out-readings)

```bash
umask 077
prior="$root/results/native-pause-20261122"
saved="$root/results/native-pause-transfer-20261122"
run=$(mktemp -d "$root/results/native-pause-bridge-rerun.XXXXXX")
py="$stage4_env/bin/python"
cd "$code"
"$py" -B -m src.quantitative_native_pause_diagnose --evaluation "$prior/visual-evaluation.json" \
  --audio-root "$prior/mandi-complete" --output "$run/mandi-miss-diagnostic.json"
"$py" -B -m src.quantitative_pause_transfer references --audio-root "$saved" \
  --inventory "$saved/mcga-inventory.json" "$saved/references.json" \
  --annotations "$saved/mandarin-transfer-independent-pauses-20261122.json" \
  --output "$run/heldout-references.json"
"$py" -B -m src.quantitative_native_pause_eval --references "$run/heldout-references.json" \
  --audio-root "$saved" --output "$run/heldout-frozen.json"
"$py" -B -m src.quantitative_native_pause_eval --bridge-weak-ms 20 --references "$run/heldout-references.json" \
  --audio-root "$saved" --output "$run/heldout-bridge.json"
```

The staged Parquet archives are pinned to the MCGA revision `75908a9464828207c37ce8bb5e2223b190134c7a` and the THCHS-30 repack revision `c8b881592bd339e9cf0483e9d686c832d4e60361`. Use `src.quantitative_pause_transfer mcga` and `src.quantitative_thchs_transfer` with PyArrow 20.0.0 to reextract untouched WAVs. Use the two inventories with the same blind renderer as above. The saved `heldout-summary.txt` and paired JSON files document counts, timing, checksums, and proposal changes. [MCGA distribution](https://huggingface.co/datasets/yxdu/MCGA/tree/main/data) · [THCHS-30 distribution](https://huggingface.co/datasets/changelinglab/thchs30-segment)

## Pre-boundary syllable duration

The experiment uses `$SHUNKOU_ROOT/results/preboundary-duration-20261122`. The staged MCGA archives come from the earlier transfer. Resupply the archived text-only reviews to `src.quantitative_boundary_mcga` with PyArrow 20.0.0. The separate DEBATE importer uses the pinned archive and workbook with xlrd 2.0.2. Pass `--exclude-manifest` pointing to the first prepared manifest to exclude its exact texts and all six reader IDs from a second set. Both importers preserve distributed original PCM under the project. Run the Charsiu feature extraction and the pause comparison in the pinned Stage 4 Python environment. [Model definition and results](../reports/stage-7.md#pre-boundary-syllable-duration-on-held-out-readings)

```bash
sbatch -A "$GILBRETH_ACCOUNT" hpc/quantitative-preboundary-duration.sbatch \
    "$SHUNKOU_ROOT" "$RESEARCH_CODE" "$STAGE4_ENV" "$RECORDINGS_MANIFEST" "$RESULT_DIRECTORY"
```

Run `hpc/quantitative-qwen-character-draft.sbatch` with the same project, code, and environment, followed by the project-local Qwen wheel overlay, the pinned model snapshot, the same corpus manifest, and the Qwen draft output JSON. For the bounded rescue, append that JSON and `compatible` or `qwen_only` to the benchmark submission. The coarse version reads the same draft with `src.quantitative_preboundary_features --qwen-draft DRAFT --rescue-mode qwen_coarse` under Slurm. Combine the coarse and original candidates with `src.quantitative_preboundary_fallback`. A separate `src.quantitative_preboundary_duration --training TRAIN_CANDIDATES --input TEST_CANDIDATES --output RESULT` fits only earlier works and excludes the held-out voice or voice group. Use `src.quantitative_preboundary_rescue_eval` to check the common and newly eligible sites. Use `src.quantitative_preboundary_contrasts` and `src.quantitative_preboundary_crossover` for same-voice same-text comparisons and raw-duration crossover controls.

#### Independent transcription at pause boundaries

Cache the pinned Whisper checkpoint and processor files in `$root/cache/recognizers/whisper-base` or `whisper-small`. The lexical runner verifies the weight digests, uses the Stage 4 Torch and Transformers installation, and reads only the active experiment WAVs, pinned text and existing timing results. It saves access-restricted transcriptions and scored matches on Gilbreth. [Whisper-base publisher files](https://huggingface.co/openai/whisper-base/tree/e37978b90ca9030d5170a5c07aadb050351a65bb) · [Whisper-small publisher files](https://huggingface.co/openai/whisper-small/tree/973afd24965f72e36ca33b3055d56a652f456b4d)

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/pause-lexical-%j.log" \
  "$code/hpc/quantitative-pause-lexical.sbatch" "$root" "$code" "$stage4_env" base
```

Use `small` as the final argument for the second checkpoint. Results are under `model-development/quantitative-pause-lexical/results` and `results-small`, respectively.

#### Absolute timing at exact waveform joins

Stage `hpc/quantitative-join-control.sbatch` with the onset-transfer source and completed artifacts. The job checks the same donor WAVs and uses both directions of each historical matched pair. Each in-memory waveform places 400 ms of zero PCM between two complete unchanged recordings in the same voice. It evaluates the first Han position of the second donor against its independently detected PCM onset at the known sample offset.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/quantitative-join-%j.log" \
  "$code/hpc/quantitative-join-control.sbatch" "$root" "$code" "$stage4_env"
```

The reports and sample checksums remain under `model-development/quantitative-join-control/results/join-control`. The benchmark uses controlled joins. Native internal pauses are covered by the separate generator-assisted check.

Once the held-out recordings exist, the historical descriptor and clip-duration comparison uses a bounded CPU pass and verifies the original WAVs and both text inventories.

```bash
cd "$code"
"$stage4_env/bin/python" -B -m src.quantitative_historical_transfer --project "$root" \
  --output "$root/model-development/quantitative-onset-transfer/results/onset-transfer/historical-duration-transfer.json"
```

#### Historical duration in the third voice

After the two-voice duration and third-voice onset reports exist, use the same Slurm runner in `duration` mode. This renders the eight v4 evaluation works using `zf_002` and repeats the same count baseline, historical descriptors, and seeded shuffles. The existing `zf_002` renderings of the 16 calibration works supply the training outcomes.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/historical-third-%j.log" \
  "$code/hpc/quantitative-third-voice.sbatch" "$root" "$code" "$stage4_env" duration
```

The private output is `model-development/quantitative-historical-third-voice/results/historical-third-voice/report.json`.

#### Fixed-count written clause control

This CPU pass reads the two pinned Chinese annotation inventories and compares the share of four- and six-character clauses within the matched literary pairs. The control randomizes punctuation positions with each passage's Han count and clause count fixed. It also tracks the effect of removing project-added punctuation.

```bash
cd "$code"
"$stage4_env/bin/python" -B -m src.quantitative_clause_structure --project "$root" \
  --output "$root/model-development/quantitative-onset-transfer/results/onset-transfer/clause-structure.json"
```

## Stage 6 pilot through the Gateway

Upload `src/` and the updated `audio/align.py` to the existing Gilbreth source checkout. From the deployed source, use the annotated Stage 3 pilot and the Stage 4 recordings and features already in scratch.

```bash
root="${RCAC_SCRATCH}/shunkou"
umask 077
python3 -B -m src.stage6_listening prepare --root "$root"
python3 -B -m src.stage6_production prepare --root "$root"
python3 -B -m src.stage6_survey_page --root "$root"
python3 -B -m src.stage6_proxies --root "$root"
python3 -B -m src.stage6_pause_audit prepare --root "$root"
```

The files app does not render these HTML pages. Gateway Jupyter can render them from an authenticated session. Expose only the two participant pages in the Jupyter file browser with an owner-controlled symlink `ln -sT "$root/audio/stage6/web" "$HOME/shunkou-stage6-pilot"`. Once connected, open `shunkou-stage6-pilot/index.html` for listening and `read-aloud.html` after listening. The player embeds the eight exact anonymous WAVs in the HTML on Gilbreth. Already loaded pages carry their audio and text, so the session expiry affects new page loads. The project audio, page and keys remain in scratch. Share only with the authorized author. The Jupyter job for this run also performed the actual GPU audit. The Gateway rejected a zero-GPU Jupyter request on the A10 partition. Do not leave a GPU job running solely for survey delivery.

Run the audit in a Slurm GPU allocation with the Stage 4 environment and cached model. After its decoder exits successfully, summarize the paired drafts.

```bash
python audio/align.py --root "$root" --offline \
  --recordings "$root/audio/manifests/stage6-pause-audit.jsonl" \
  --out-dir "$root/audio/derived/stage6/pause-audit"
python3 -B -m src.stage6_pause_audit analyze --root "$root"
```

For listening responses, keep a private JSONL file with `participant_id`, `survey_id`, `trial_id` and `choice` (`A`, `B`, `tie` or `skip`). Run `python3 -B -m src.stage6_listening score --root "$root" --responses PATH` and save the aggregate on Gilbreth. First-read consent, waveform intake and review are described in the [production protocol](../audio/STAGE6_PRODUCTION.md).

### Male Mandarin listening round

Use `hpc/male-listening.sbatch` with the main project directory, the uploaded source snapshot and the pinned Stage 4 environment. Run it as a Slurm job or from an authenticated Jupyter terminal with a GPU allocated. It reuses the Stage 3 annotations and Stage 4 cache. It verifies the publisher's male voice embedding, renders seven excerpts with a nominal speed of 0.9, aligns their waveforms, and builds an overall 1–7 listening page. Its project directory is `$root/listening-rounds/mandarin-male`.

```bash
sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --output="$root/logs/male-listening-%j.log" \
  "$code/hpc/male-listening.sbatch" "$root" "$code" "$stage4_env"
```

To play the generated page in an authenticated Gateway Jupyter browser, link the participant directory to `$HOME/shunkou-male-listening` and open its `index.html`. The eligible participant directory is `$root/listening-rounds/mandarin-male/audio/stage6/web`. The generated page carries the clips for ordinary browser playback after it is loaded. Keep the WAVs, rendered HTML, and unblinding key on Gilbreth. Keep any new responses with their own survey ID and record them as overall pair ratings.

For the text-supported version, run the following command from the source checkout on Gilbreth. Open `with-text.html` in the same participant directory. It places the verified original wording beneath each player. Record those scores as text-supported listening.

```bash
python3 -B -m src.stage6_survey_page \
  --root "$root/listening-rounds/mandarin-male" --overall --with-text
```

### Compare author ratings

For the author follow-up, keep the overall listening ratings and the first-read ease ratings in an owner-only response JSON in `$root/results/stage6/responses/`. From the project source checkout on Gilbreth, run the comparison against the existing Stage 3 text annotations, the Stage 4 synthetic feature tables, and the Stage 6 survey key and pause audit. The command checks the exact survey WAV hashes and editions. It prints an aggregate summary and saves a private `-comparison.json` beside the response. It uses the existing feature tables and requires no new GPU run.

```bash
python3 -B -m src.stage6_author_comparison --root "$root" \
  --response "$root/results/stage6/responses/RESPONSE.json"
```

To compare the two rounds of overall listening ratings, run the listening-only command below. It verifies the exact survey stimuli and matches the pair designs across different anonymous labels. It saves the per-pair joins beside the follow-up response under owner-only permissions and prints an aggregate summary. Retain the follow-up presentation metadata so the scores show that Chinese text was available.

```bash
round="$root/listening-rounds/mandarin-male"
python3 -B -m src.stage6_round_comparison --root "$root" \
  --first-response "$root/results/stage6/responses/RESPONSE.json" \
  --followup-root "$round" \
  --followup-response "$round/results/stage6/responses/RESPONSE.json"
```

### Independent-work pilot expansion

Upload a source archive with the expansion manifest, audio recipes, `src/`, `data/phonology/`, `data/pilot/build.py`, `audio/` Python modules, and `hpc/expand-pilot.sbatch`. Extract it on Gilbreth. The job reuses the pinned historical and modern lexicon caches and the validated Stage 4 GPU environment. The expansion is isolated under `$root/pilot-expansions/independent-works`.

```bash
sbatch --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --output="$root/logs/expand-%j.log" \
  "$code/hpc/expand-pilot.sbatch" "$root" "$code" "$stage4_env"
```

The builder can use a short reviewed witness snapshot at `data/pilot/reviewed-witnesses.json` under the expansion root when Wikimedia is unavailable. Its passage IDs, anchors and hashes must match the [pinned source manifest](../data/pilot/expansion-passages.json). The snapshot contains the spans before any project punctuation. Keep the snapshot and the derived corpus under the expansion root.

The listening materials are `audio/stage6/listening-web/index.html` for blind playback and `with-text.html` for Chinese text alongside the same four clips. Serve that directory inside the authenticated Gateway Jupyter session. Keep the text-supported condition with any listening responses. The separate `audio/stage6/production/read-aloud.html` prompts the first read of four other works. The consented recording intake described in the [production protocol](../audio/STAGE6_PRODUCTION.md) can use the expansion root and its private prompt key. Keep responses, keys, recordings, and rendered listening HTML on Gilbreth.

For the text-supported author response, use the expansion checkout and the existing waveform features. The command verifies the exact survey page and read-aloud prompt hashes. It writes the two sets of item-level comparisons in separate fields in an owner-only file beside the response. The console summary omits individual ratings.

```bash
round="$root/pilot-expansions/independent-works"
python3 -B -m src.expansion_response --root "$round" \
  --response "$round/results/stage6/responses/author-expanded-pilot.json"
```

The [follow-up feasibility protocol](../research/followup-pilot.md#gilbreth-materials) gives the command to build the counterbalanced listening and read-aloud forms under the same expansion. The builder uses the four existing WAVs without a new GPU run.

## Stage 7 scoring through the Gateway

Run `./shunkou score INPUT.txt` from the source checkout. UTF-8 text and blank lines define the input and its paragraphs. Markdown is the default report. Set `--format json` or use `-o REPORT.json` for exact offsets, candidate readings, support, and component values. Use `-o REPORT.html` for highlighted clauses and playback when the input includes a waveform. A text-only run needs Python 3.9 or later and the standard library. `make all` also uses Gnuplot 5.4.3 to rebuild the two report figures.

From the Gateway shell, point the command at the existing annotations and lexicon caches. Exact pilot text is recognized automatically. `--passage-id` requires an exact byte-equivalent UTF-8 witness, including wording, punctuation, and line breaks. New text uses the cached 《廣韻》, 《平水韻》, and Unihan candidate data. Without those caches the CLI can still report structural components and shows unavailable historical measures.

```bash
root="${RCAC_SCRATCH:-$(findscratch)}/shunkou"
code="$root/sources/stage7-20261121"
stage4_env="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108"
"$code/shunkou" score "$root/input.txt" --root "$root" -o "$root/results/stage7/input.md"
```

Work on WAVs under `$root/audio/raw/`. The CLI checks the exact text, recording hash, and manifest against the acoustic input. For an unmanifested recording give its documented reuse permission or consent with `--rights` and supply `--speaker` (use a code), `--style`, and `--variety cmn` for confirmed Mandarin. `--audio-manifest` accepts an alternative exact recording manifest. `--alignment FILE.jsonl` accepts only events bound to the exact waveform and text. Match Stage 4's event schema and retain both `text_sha256` and `audio_sha256`. Reviewed human events use `status=reviewed` and may supply `realized_reading`.

For a new decoded WAV, load `anaconda/2024.10-py312` inside an allocated Gilbreth Slurm GPU job and use the pinned Stage 4 interpreter. `--decode` uses the offline cache for the pinned Charsiu checkpoint and writes a private alignment cache. It currently accepts Mandarin WAV excerpts of 0.1–60 seconds. After that run, reuse the exact draft by omitting `--decode`. Save audio HTML under the project root and open it only in an authenticated environment that renders HTML. Gateway Files can list the file and preview the Markdown report. Its plain-text HTML preview does not support playback. An already authorized Gateway Jupyter session can render the HTML in-browser while running the associated compute workflow.

```bash
"$stage4_env/bin/python" "$code/shunkou" score "$root/input.txt" --root "$root" \
  --audio "$root/audio/raw/reading.wav" -o "$root/results/stage7/reading.html"
```

For the full verification, upload `shunkou`, `src/`, `tests/`, `audio/*.py`, `data/phonology/*.py`, `data/pilot/context-reviews.json`, and `hpc/stage7.sbatch` with their source paths. Submit with the available account and partition. It scores all 12 matched texts and decodes one matched pair on a GPU. The job writes JSON, HTML and a short verification summary under `results/stage7/job-JOB_ID`. From that checkout, `python -m src.stage7_pilot --root "$root" --output "$root/results/stage7/verification" --reuse-drafts` verifies the same reports using exact cached drafts.

```bash
sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal \
  --chdir="$root" --output="$root/logs/stage7-%j.log" \
  "$code/hpc/stage7.sbatch" "$root" "$code" "$stage4_env"
```

### Written editorial scores and the two-voice acoustic comparison

The archived run is in `$root/results/editorial-context-20261122`. Its `inputs/` directory contains the 209 section-labelled reference units, two complete Tang works, frozen GPT written scores and edition records. The release snapshot in `release/code/` includes both scoring modules and the Slurm runner. For a fresh rerun from the authenticated Gateway, set `root` to the private project and `stage4_env` to its pinned Stage 4 environment. Use a new output directory so the original forecasts remain available for comparison.

```bash
archive="$root/results/editorial-context-20261122"
code="$archive/release/code"
run=$(mktemp -d "$root/results/editorial-rerun-XXXXXXXX")
cd "$code"
OPENBLAS_NUM_THREADS=1 "$stage4_env/bin/python" -B -m src.quantitative_editorial_context \
  --root "$root" --reference "$archive/inputs/reference-context.json" \
  --witness "$archive/inputs/fresh-witness.json" --labels "$archive/inputs/fresh-labels.json" \
  --output "$run/text-results.json"
sbatch --parsable --account=YOUR_SLURM_ACCOUNT --output="$run/audio-%j.log" \
  "$code/hpc/quantitative-editorial-audio.sbatch" "$root" "$code" "$stage4_env" \
  "$archive/inputs/fresh-witness.json" "$run/acoustic" "$run/text-results.json"
```

The text report includes four feature sets, training-only constant forecasts and 199 within-section order controls. The GPU runner stores the WAVs, pronunciation prescriptions, checksums, timing evidence and matched-line forecasts in the private run directory. It fits the acoustic increment on the other work and the other voice, with a paired shuffle control. The reference outcome throughout is a written judgment. [Stage 7 results](../reports/stage-7.md#cross-line-rhyme-and-parallelism-on-two-new-tang-works)

### Grammar transfer on four fresh works

The archived run is in `$root/results/grammatical-patterns-20261122`. The frozen protocol, historical note, edition manifest, original units, independent editorial labels and separate pair review are stored there. The script reports predictions and both shuffle controls in one JSON file. This is a small CPU calculation using the pinned Stage 4 Python and the historical dictionaries on Gilbreth.

```bash
grammar="$root/results/grammatical-patterns-20261122"
training="$root/results/editorial-context-20261122/inputs/reference-context.json"
rerun=$(mktemp -d "$root/results/grammar-rerun-XXXXXXXX")
cd "$grammar/code"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$stage4_env/bin/python" -B -m src.quantitative_editorial_grammar \
  --root "$root" --reference "$training" --witness "$grammar/inputs/fresh-witness.json" \
  --labels "$grammar/inputs/fresh-labels.json" --shuffles 199 --output "$rerun/fresh-results.json"
```

The archive also includes `development-results.json` from a separate pass over the already examined Tang works. The original 74-line prediction table is `line-scores.txt`. The independent judgment and model decision for all 62 adjacent pairs appear in `frame-audit.txt`. [Checkpoint](../reports/stage-7.md#repeated-grammatical-patterns-on-four-fresh-northern-song-works)

### Expanded grammatical-pattern training

The private expansion archive contains six training witnesses, two Tang test works, their edition and license manifests, the masked reading packets and their keys. The Python runner verifies the labels against the corresponding Chinese text before fitting. It writes the expanded training reference and the results for both the new Tang test and the previously examined Northern Song comparison. Both models are tested against the same written editorial judgments of 音律美. First-read ease (顺口) has its own protocol. The authors and text of the two fresh works were reserved in advance. One training interjection also occurs in the earlier Song test. Its original row and score stay in the archive, and the runner records its exclusion from fitting.

```bash
root=/scratch/gilbreth/$USER/shunkou
run="$root/results/grammatical-training-expansion-20261122"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
rerun=$(mktemp -d "$root/results/grammar-expansion-rerun-XXXXXXXX")
sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
  --output="$rerun/slurm-%j.log" "$run/grammar-training-expansion.sbatch" \
  "$root" "$run" "$python" "$rerun/results"
```

After the main job finishes, the six-work diagnostic can reuse its expanded reference. Each fold holds out one whole historical work. For each subset it compares the same rows across models, averaging over the works with eligible rows.

```bash
cd "$run/code"
srun --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
  --ntasks=1 --cpus-per-task=1 --mem=2G --time=00:02:00 \
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 "$python" -B -m src.quantitative_grammar_work_holdout \
  --root "$root" --reference "$rerun/results/enriched-reference.json" \
  --output "$rerun/results/within-training-work-holdout.json"
```

Gilbreth's A10 partition requires a GPU reservation. The text fits and 199 shuffles use a single CPU thread and the existing historical lexicons. [Stage 7 comparison](../reports/stage-7.md#expanding-the-grammatical-pattern-training-set)

### Fresh three-line challenge

The archive stores the six source witnesses and editions, independently reviewed windows, a pre-rating eligibility file, the masked reading packet, its key and frozen verdict. The runner loads the two expanded fits directly from the previous archive and verifies the model and historical-dictionary checksums. It reports all three forecasts, per-work and equal-work errors, separate results for strict parallel prose, and two 199-draw controls. To reproduce on Gilbreth:

```bash
root=/scratch/gilbreth/$USER/shunkou
run="$root/results/fresh-three-line-transfer-20261122"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
rerun=$(mktemp -d "$root/results/fresh-three-line-rerun-XXXXXXXX")
sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
  --output="$rerun/job-%j.log" "$run/code/hpc/fresh-grammar-triples.sbatch" "$root" "$run" "$python" "$rerun/results"
```

The admission check is also available separately through the runner’s `--screen` option, which writes an eligibility JSON before loading labels or making predictions. A10 requires a GPU reservation. The computations use one CPU thread. [Stage 7 results](../reports/stage-7.md#fresh-parallel-prose-with-verified-three-line-constructions)

### Ending changes in parallel prose

The private Gilbreth directory stores the source text, selected arms and boundary judgments, both masked reading packets, frozen verdicts and feature screen. The runner verifies the expanded model checksum, the historical dictionaries and the pre-rating endpoint manifest. Raw comparisons cover the unchanged model, two single-feature adjustments, their sum, and always-6.

```bash
root=/scratch/gilbreth/$USER/shunkou
run="$root/results/pattern-ending-transfer-20261122"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
rerun=$(mktemp -d "$root/results/pattern-ending-rerun-XXXXXXXX")
sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
  --output="$rerun/job-%j.log" "$run/code/hpc/pattern-endings.sbatch" "$root" "$run" "$python" "$rerun/results"
```

The `--screen` option to `src.quantitative_pattern_endings` separately checks original quotation positions and work/line independence without loading verdicts or making predictions. The text analysis uses one CPU thread on a Slurm allocation. [Checkpoint](../reports/stage-7.md#does-a-change-at-the-end-of-a-pattern-distinguish-a-written-7-from-a-6)

### Argument conclusions and list endings in parallel prose

The Gilbreth archive contains the pinned Chinese witnesses, paragraph checksums, pre-scoring protocol, anonymous packets, two independent function annotations, the separate editorial ratings, and predictions for each ending. The runner checks the source quotations, screening against the previous written corpora, historical dictionary hashes and frozen model checksum before joining the three sets of judgments. The compute job uses one CPU thread within the partition's required GPU reservation.

```bash
root=/scratch/gilbreth/$USER/shunkou
run="$root/results/ending-function-transfer-20261122"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
rerun=$(mktemp -d "$root/results/ending-function-rerun-XXXXXXXX")
sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
  --output="$rerun/job-%j.log" "$run/code/hpc/ending-functions.sbatch" "$root" "$run" "$python" "$rerun/results"
```

The module's `--screen` option checks eligibility without opening the judgments. The full run saves per-work results, all 999 control draws summarized against the observed improvement, the individual-annotator sensitivities, and original lines beside forecasts. [Stage 7 checkpoint](../reports/stage-7.md#argument-conclusions-and-list-endings)

### Calibrating the decision to report a 7

The private `top-score-calibration-20261122` archive holds the frozen protocol, six fresh witnesses, anonymous editorial packet, source and score checksums, and row-level decisions. The fit reads all complete units from the two preceding parallel-prose experiments. The test verifies the earlier fit checksum, reconstructs the base predictions from the archived model and dictionaries, and verifies that refitting on the archived earlier units reproduces the signed-off cutoff. Both phases use a single CPU thread on a Slurm allocation.

```bash
root=/scratch/gilbreth/$USER/shunkou
run="$root/results/top-score-calibration-20261122"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
rerun=$(mktemp -d "$root/results/top-score-rerun-XXXXXXXX")
job=$(sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
  --output="$rerun/fit-%j.log" "$run/code/hpc/top-score-calibration.sbatch" "$root" "$run" "$python" fit "$rerun/frozen")
sbatch --parsable --dependency="afterok:$job" --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
  --output="$rerun/test-%j.log" "$run/code/hpc/top-score-calibration.sbatch" "$root" "$run" "$python" test "$rerun/results" \
  --freeze "$rerun/frozen/freeze.json"
```

The test outputs the full benchmark JSON, a plain-text summary, and each original unit beside its editorial rating, frozen forecast and top-score calls. [Stage 7 checkpoint](../reports/stage-7.md#calibrating-the-decision-to-report-a-written-7)

### Identical forecasts and development of the preceding thought

The private archive stores the old tie audit, protected sources, fresh Chinese witnesses and anonymous reading packets, quoted relation judgments, separate editorial ratings, and fixed comparisons. The first phase replays the 95 previous model forecasts and traces the 11 equal scores. The second phase scores source-adjacent targets and tests the predeclared role bonus and controls. Run both against the pinned environment on Gilbreth.

```bash
root=/scratch/gilbreth/$USER/shunkou
run="$root/results/adjacent-thought-transfer-20261122"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
rerun=$(mktemp -d "$root/results/adjacent-thought-rerun-XXXXXXXX")
for phase in audit test; do
  if [[ "$phase" == audit ]]; then output="$rerun/tie-audit.json"; else output="$rerun/results"; fi
  sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
    --output="$rerun/$phase-%j.log" "$run/code/hpc/adjacent-thought.sbatch" "$root" "$run" "$python" "$phase" "$output"
done
```

Each single-threaded job uses the A10 partition's required reservation. The fresh results JSON includes both coder sensitivities, same-score comparisons, within-work permutations, and matched predecessor substitutions. [Stage 7 checkpoint](../reports/stage-7.md#does-developing-the-preceding-thought-help-distinguish-a-7-from-a-6)

### Targeting exact same-work forecast ties

The Gilbreth archive holds the fresh pool, selection protocol, frozen model scores, separately masked reader packets, judgments and line-by-line outcomes. The screen groups eligible targets by author/work and the complete hexadecimal representation of the original binary64 forecast. It runs before the readers receive their packets. The test validates the sealed target manifest, witnesses, packet hashes and quoted judgments. Each job uses one CPU thread on a Slurm allocation.

```bash
root=/scratch/gilbreth/$USER/shunkou
run="$root/results/exact-tie-targets-20261122"
python="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
rerun=$(mktemp -d "$root/results/exact-tie-rerun-XXXXXXXX")
job=$(sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
  --output="$rerun/screen-%j.log" "$run/code/hpc/exact-tie-carry.sbatch" "$root" "$run" "$python" screen "$rerun/screen")
sbatch --parsable --dependency="afterok:$job" --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 \
  --output="$rerun/test-%j.log" "$run/code/hpc/exact-tie-carry.sbatch" "$root" "$run" "$python" test "$rerun/results" \
  --seal "$rerun/screen"
```

The results distinguish correct resolutions, incorrect resolutions and unchanged ties. Both the current model and always giving 6 receive half credit for every exact 7/6 tie. [Stage 7 checkpoint](../reports/stage-7.md#can-thought-development-break-exact-76-ties)

### Testing whether contrast answers the preceding line

The [frozen design](../research/contrast-answer.md) specifies the corpus, exact-score screen, blind written-cadence rubric, two contrast prompts, predecessor substitutions and 7/6 comparison. The experiment directory is `$SHUNKOU_ROOT/results/contrast-answer-20261123`. It contains the pinned Wikisource editions, prior-study exclusion inputs, anonymous editorial packet, Qwen decisions and joined results. On the first run the screen precedes both readers. Copy the sealed screen hash to `inputs/screen.sha256` before the relation and evaluation phases. The relation model runs entirely on Gilbreth with the Qwen2.5-7B-Instruct checkpoint `a09a35458c702b33eeacc393d103063234e8bc28` in the project Hugging Face cache.

To reproduce the completed comparison without changing the original, make a new directory on Gilbreth, reuse the archived source and editorial inputs, and submit these Slurm jobs. The two reports distinguish written 音律美 from the later listening and first-read measures.

```bash
root=/scratch/gilbreth/$USER/shunkou
source_run="$root/results/contrast-answer-20261123"
rerun=$(mktemp -d "$root/results/contrast-answer-rerun-XXXXXXXX")
py="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
ln -s "$source_run/code" "$rerun/code"
mkdir "$rerun/inputs"
cp -a "$source_run/inputs/." "$rerun/inputs/"
runner="$rerun/code/hpc/contrast-answer.sbatch"
opts=(--parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 --output="$rerun/%x-%j.log")
screen=$(sbatch "${opts[@]}" --mem=3G -c 1 -t 00:03:00 "$runner" "$root" "$rerun" "$py" screen)
relation=$(sbatch "${opts[@]}" --dependency="afterok:$screen" "$runner" "$root" "$rerun" "$py" relation)
sbatch "${opts[@]}" --dependency="afterok:$relation" --mem=3G -c 1 -t 00:03:00 "$runner" "$root" "$rerun" "$py" evaluate
```

### Testing cadence completion across adjacent lines

Gilbreth keeps the frozen inputs, historical-scoring dependencies, source editions, two classifier prompts, length-matched earlier-line controls, masked rating packet and individual written judgments in `results/cadence-completion-20261123`. The [protocol](../research/cadence-completion.md) describes the passage screen and comparisons. To reproduce from the archived inputs, create an independent output directory before submitting the jobs.

```bash
root=/scratch/gilbreth/$USER/shunkou
archive="$root/results/cadence-completion-20261123"
rerun=$(mktemp -d "$root/results/cadence-completion-rerun-XXXXXXXX")
ln -s "$archive/code" "$rerun/code"
cp -a "$archive/inputs" "$rerun/inputs"
py="$root/env/stage4-py312-torch-2.7.1+cu126-13cbdafce108/bin/python"
opts=(--parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=normal --gres=gpu:1 --output="$rerun/%x-%j.log")
runner="$rerun/code/hpc/cadence-completion.sbatch"
screen=$(sbatch "${opts[@]}" "$runner" "$root" "$rerun" "$py" screen relation)
evaluation=$(sbatch "${opts[@]}" --dependency="afterok:$screen" --mem=3G -t 00:03:00 "$runner" "$root" "$rerun" "$py" evaluate)
sbatch "${opts[@]}" --dependency="afterok:$evaluation" --cpus-per-task=1 --mem=3G -t 00:03:00 \
  --wrap="cd '$rerun/code' && '$py' -B -m src.cadence_completion_audit '$rerun'"
```

The written comparisons use the original model and equal-weight informative works. The screen and relation stages each produce a new seal. The evaluation verifies the source packet, predictions and blinded editorial-rating hash before joining them. Participant listening and read-aloud responses belong to the final validation stage.

## Re-run the GPU smoke test

From the repository root, set the SSH destination and use the Slurm account shown by `slist` for the A10 partition. The job requests a single GPU for up to two minutes.

```bash
shunkou_ssh_host=YOUR_GILBRETH_SSH_ALIAS
ssh "$shunkou_ssh_host" 'set -eu
  scratch="${RCAC_SCRATCH:-$(findscratch)}"
  test -d "$scratch"
  root="$scratch/shunkou"
  umask 077
  mkdir -p "$root/logs"
  sbatch --parsable --account=YOUR_SLURM_ACCOUNT --partition=a10 --qos=standby \
    --chdir="$root" --output="$root/logs/gpu-smoke-%j.out"' < hpc/gpu-smoke.sbatch
```

On Gilbreth, check `squeue -j JOB_ID` while it runs, then `sacct -X -j JOB_ID --format=JobID,State,ExitCode,Elapsed,AllocTRES`. For a successful job, the scratch log names the compute node and GPU. `findscratch` supplies the scratch path for SSH command sessions where `RCAC_SCRATCH` is unset.
