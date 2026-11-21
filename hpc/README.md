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
