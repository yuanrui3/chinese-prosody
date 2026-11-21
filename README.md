# 骈文诗词音律美量化研究

This project studies first-read ease (顺口) and the sound of a performance (音律美) in parallel prose (骈文) and period-matched comparison prose.

## What the pilot found

One person rated four pairs in each listening round and four passages in the read-aloud task.

### 音律美 · How pleasing it sounded

In the first listening round, the higher-rated pairs had shorter phrases on average and a little more audio time per written character. Both rounds averaged **5 out of 7**. Two pair scores rose, one fell, and one stayed the same. The second round used a slower male synthetic voice and made the Chinese text available. Those changes happened together, so the effect of the voice alone is still open.

### 顺口 · How easy it felt to say

Passages with shorter phrases tended to feel easier to read aloud on the first try. In one matched comparison, the passage that felt easier had **more characters overall** and much shorter phrases.

## Project resources

- [Final report and figures](reports/final.md)
- [Text, audio, and rating methods](theory/foundations.md)
- [Gilbreth setup, scoring, and reproduction](hpc/README.md)
- [Pilot editions and source attribution](data/pilot/DATA_CARD.md)

Run `./shunkou score passage.txt` for a text report. The Gilbreth runbook covers waveform alignment and audio reports. Run `make all` with Python and Gnuplot to check the source and regenerate the report figures.

The repository contains research code, source metadata, methods, and aggregate results. The Gilbreth project holds the audio, model cache, private survey keys, and individual responses.
