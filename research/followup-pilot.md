# Human validation protocol for 骈文 and matched prose

**Study status.** Computational model development and automated validation come first. The prepared listening and read-aloud forms are reserved for the final validation study, after the model reaches the readiness checkpoint below.

**Pilot observation.** The author's two listening pairs differed in sound-pattern beauty (音律美) ratings while sharing pooled clause length and nearly the same playback time per written character. The passages rated easier to read aloud (顺口) had more four- or six-character clauses in both period matches. The direction of mean clause length differed by period. These ratings provide exploratory observations. [Expanded pilot results](../reports/final.md#independent-work-expansion)

**Project hypotheses.** Seeing the Chinese lines may change how listeners rate the same recordings. The proportion of four- or six-character clauses may track first-read ease across works after accounting for familiarity and other lexical and structural differences. These prepared forms cover two listening pairs and four reading excerpts. They can check the instruments on those items as part of the final validation stage.

## Model readiness

- Check historical text measures against controlled and shuffled inputs, preserve reading ambiguity, and assess performance on held-out works and authors against simple length and structure baselines.
- Verify acoustic measures against waveform controls with known changes. Report alignment coverage, missing measurements, and sensitivity to recording conditions. Treat synthetic takes as evidence about the measurement pipeline.
- Freeze the supported features, baselines, and analysis for each outcome before collecting new ratings. Keep listening judgments and cold-read ease as separate validation outcomes. [Formal and acoustic validation](../reports/stage-5.md) · [Scoring toolkit](../reports/stage-7.md)

## Listening

Each listener gets one of eight forms (L01–L08). The forms cross two conditions (audio-only and audio with the original Chinese lines), two pair orders, and the original or reversed A/B clip order within both pairs. Both conditions use the same four WAVs. Each listener encounters both pairs once and hears A before B. Assign forms in randomly ordered blocks of eight so that each form appears once per complete block. Use listeners who have yet to see these study forms. Allow an optional replay under the same instructions in both conditions. Log familiarity with an excerpt and any reported prior exposure to a study clip.

After hearing both clips, the listener gives the whole pair a single rating from 1 (very displeasing) to 7 (very pleasing), with an option to skip. Save the pseudonymous listener code, assigned form, pair codes, ratings, skips and any reported prior exposure. The form ID recovers the visibility and order conditions from the private key. Treat each listener as the unit of assignment and retain their two ratings together in analysis. Summarize ratings and missingness by pair and condition and compare assigned arms over the same two pairs. Report skips separately from scored ratings. If prior exposure emerges after assignment, retain the response and report a sensitivity summary for unexposed listeners when feasible. A/B swaps balance presentation order. Whole-pair ratings leave individual clip preferences unresolved. Report the visibility contrast for these recordings and keep broader genre interpretation for data from more independent works and speakers. [Listening and analysis framework](../theory/foundations.md#production-listening-and-detection)

## First read aloud

Use four different works from those in listening. Each reader gets one of four forms (P01–P04) in randomly ordered blocks of four. The forms rotate R01–R04 so each prompt occupies each position once per complete block. Use fresh readers. Reveal one prompt when the reader is ready, read it aloud once with the person's usual pronunciation, and give a 1–7 ease rating afterward. Record variety, prior familiarity for each item, and skips. Keep the production ratings separate from the listening ratings.

A voluntary first-take recording under the applicable consent can support measurements of pace, pauses, hesitations, repairs, and repetitions. Keep these measurements distinct from the ease rating. Compare ease within the two period matches and describe how the patterns vary with familiarity. Before adding participants or collecting recordings, use the applicable institutional determination and approved consent, access, retention, and withdrawal procedures. [First-read and consent protocol](../audio/STAGE6_PRODUCTION.md)

## Gilbreth materials

To regenerate the reserved forms from the project checkout on Gilbreth, run:

```bash
python3 -B -m src.followup_pilot --root "$root/pilot-expansions/independent-works"
```

The expansion root holds `followup-pilot/participant/listening`, `followup-pilot/participant/read-aloud`, and `followup-pilot/restricted/design.json`. The build verifies the anonymous audio against the existing WAV hashes and checks that listening and reading use separate works. Serve only the assigned participant form through authenticated access. Keep the unblinding key, assignment log, individual responses, any consent records and recordings, and audio-bearing HTML on Gilbreth. [Gateway instructions](../hpc/README.md#independent-work-pilot-expansion) · [Stage 6 materials](../reports/stage-6.md#independent-work-pilot-expansion)
