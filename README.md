# 骈文诗词音律美量化研究

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24448783.svg)](https://doi.org/10.5281/zenodo.24448783)

This project tests claims about how Chinese parallel prose (骈文) sounds. It compares 骈文 with prose from the same period and asks three questions separately. How easily can someone read a passage aloud on a first try (顺口)? How pleasing is its cadence in a particular recording (听觉音律美)? Which lines would an editor single out for their written cadence (书面音律美)?

## What the research contributes

- **A historical reading can expose a blind spot in the score.** 沈約 favored the entering-tone reading of 霓 in 「駕雌霓之連蜷」. Selecting it shortens the longest run of level-tone syllables from five to three, yet the scorer gives both readings the same grade. [Documented reading and worked example](reports/final.md#what-historical-critics-let-us-test)
- **The same words can be heard with two different phrasings.** In one four-character recording, a single 80 ms pause gives a 2+2 grouping. Splitting it into two 40 ms pauses gives 1+1+2, with the voice and total time held fixed. This isolates a difference listeners can judge. [Waveform check](reports/stage-5.md#fixed-text-recitation-phrasing)
- **Recognizing a rhyme and predicting a preference give different results.** Nearby endings scored 81.1% on a two-choice test of historical rhyme groups in regulated rhapsodies (律賦), falling to 59.1% after shuffling. In a separate test on 80 sentences, including that rhyme feature slightly increased the error in predicting blind AI editorial grades. [Rhyme test](reports/masked-rhyme-recovery.md) · [Grade comparison](reports/written-rhyme-ablation.md)
- **Comparing two lines from one work shows promise.** On 38 fresh comparisons from seven works, the pair-trained model placed an editorial 7 above a 5 or 6 in 69.0% of comparisons when each work counted equally. The released scorer reached 43.6%, and always giving 6 earned 50.0% through ties. The uncertainty interval for the lead included zero, so the released scorer remains the benchmark. [Examples and uncertainty](reports/within-work-rank.md)

The latest ranking results measure written editorial judgment. Independent human listening and first-read studies are reserved for the final validation stage. [Contributions and prior work](reports/final.md#what-this-project-contributes) · [What the toolkit can test](reports/stage-7.md#what-the-toolkit-can-test)

## What the pilot found

One person rated four pairs in each listening round and four passages in the read-aloud task.

### 音律美 · How pleasing it sounded

In the first listening round, the higher-rated pairs had shorter phrases on average and a little more audio time per written character. Both rounds averaged **5 out of 7**. Two pair scores rose, one fell, and one stayed the same. The second round used a slower male synthetic voice and made the Chinese text available. Those changes happened together, so the effect of the voice alone is still open.

### 顺口 · How easy it felt to say

Passages with shorter phrases tended to feel easier to read aloud on the first try. In one matched comparison, the passage that felt easier had **more characters overall** and much shorter phrases.

## Project resources

- [Final report and figures](reports/final.md)
- [Research roadmap after the historical reading test](research/roadmap.md)
- [Written scores and the author’s memorization review of 《哀江南賦》](reports/stage-7.md#yu-xin-memorization-review)
- [Text, audio, and rating methods](theory/foundations.md)
- [Gilbreth setup, scoring, and reproduction](hpc/README.md)
- [Pilot editions and source attribution](data/pilot/DATA_CARD.md)

Run `./shunkou score passage.txt` for a text report. The Gilbreth runbook covers waveform alignment and audio reports. Run `make all` with Python and Gnuplot to check the source and regenerate the report figures.

On Gilbreth, the scorer recognizes documented readings in five exact quotations. For example, it reads 霓 as entering tone (入聲) in 沈約’s 「駕雌霓之連蜷」. The report shows the source, other dictionary readings, and the resulting 平仄. Add `--prototype` for a written 音律美 estimate per sentence or `--historical-readings reviews.json` to supply evidence for another passage. [Reading catalogue and evidence](data/phonology/HISTORICAL.md#documented-readings-in-a-passage) · [Gilbreth usage](hpc/README.md#scoring-documented-historical-readings)

The repository contains research code, source metadata, methods, and aggregate results. The Gilbreth project holds the audio, model cache, private survey keys, and individual responses.
