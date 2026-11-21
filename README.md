# 骈文诗词音律美量化研究

This project studies first-read ease (顺口) and the sound of a performance (音律美) in parallel prose (骈文) and period-matched comparison prose.

- [Final report and figures](reports/final.md)
- [Text, audio, and rating methods](theory/foundations.md)
- [Gilbreth setup, scoring, and reproduction](hpc/README.md)
- [Pilot editions and source attribution](data/pilot/DATA_CARD.md)

Run `./shunkou score passage.txt` for a text report. The Gilbreth runbook covers waveform alignment and audio reports. Run `make all` with Python and Gnuplot to check the source and regenerate the report figures.

The repository contains research code, source metadata, methods, and aggregate results. The Gilbreth project holds the audio, model cache, private survey keys, and individual responses.
