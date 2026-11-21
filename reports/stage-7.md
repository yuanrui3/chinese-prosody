# Stage 7 checkpoint

The toolkit and the final report are ready for the edition-pinned parallel-prose (骈文) and period-matched comparison pilot. `./shunkou score INPUT.txt` reports interpretable components for the document, its paragraphs and its clauses. It preserves exact witness and text offsets, unresolved reading candidates, and support for historical estimates under 《廣韻》 and 《平水韻》. Ranked text observations give the reason and affected clauses. Annotated pairs use the independent Stage 3 pairings. General plain-text input uses the cached candidates when available. [Command and runbook](../hpc/README.md#stage-7-scoring-through-the-gateway)

`--audio` adds the recording provenance, exact waveform check, linked intervals, timing coverage, observed pronunciation drafts, low-energy gap candidates, and places for review. The optional HTML highlights ranked clauses and plays their timed portions. Some intervals cover only linked parts of a clause. The recording and the HTML containing its excerpts remain on Gilbreth. `--decode` uses the cached Stage 4 model in a Slurm GPU allocation. Repeat scoring can reuse the checksum-bound draft. Verified human events use an explicit review record. [Acoustic definitions](../audio/ACOUSTIC_FEATURES.md) · [Production protocol](../audio/STAGE6_PRODUCTION.md)

## Live verification

- Gateway Slurm job `12472945` completed on one A10 with exit code `0:0` in `00:03:05`. The job scored all 12 edition-matched texts in six pairs, scored a new two-paragraph text using the cached lexicons, and freshly decoded the M04 pair at the same synthetic voice and speed.
- The ET01 parallel-prose take had 24 of 26 written slots linked and four clause players covering whole clauses or linked portions. The ET02 comparison take had 23 of 24 slots linked and five clause players. Each report gave one audio review cue. The HTML output was checked for a player for every available interval. These counts describe the test takes.
- The final deployed version reran the tests on Gilbreth and all 24 passed, including the live historical annotation check. A second verified run rebuilt both audio reports and all 12 text reports from cached drafts. The GPU run is in `$SHUNKOU_ROOT/results/stage7/job-12472945`, the final release in `$SHUNKOU_ROOT/results/stage7/release`, and the GPU log in `$SHUNKOU_ROOT/logs/stage7-12472945.log`.
- `make all` passed locally. It ran the tests and shell syntax checks and rebuilt both figures. The live historical-annotation test was skipped locally because it needs the Gilbreth corpus.

## Scope

The research separates ease of oral production (顺口) from sound-pattern beauty (音律美). The release scores describe structural components and highlight acoustically observable review cues. Syntactic parallelism still relies on independent annotation. Timing, pitch, and alignment discrepancies from this pilot characterize synthetic readings, and the two human outcomes still need independent validation. The report records the shuffled controls, text–sound disagreements, failures, and a design for that validation. [Final report and figures](final.md)
