# Prior exposure of the historical variants

**Archive finding.** The ten comparison families contain 24 distinct stimulus versions. Three complete versions occur in this project's earlier materials. Two are the deliberately reused Ouyang Xiu (歐陽修) calibration passages. The third is Li Cheng's (李程) opening to 《日五色賦》, which was shown in a previous screening packet. The eight remaining families have no full-version or tested-clause match in the file inventory below. None of the 24 complete versions appears in the frozen 337-row training reference. Exact matches allow traditional/simplified and listed graphic variants. [Stimulus texts and provenance](critic-variants.json) · [Original training expansion](../hpc/grammar-training-expansion.sbatch) · [Known Stage 2 comparison](../reports/stage-2.md)

| Comparison family | Previous work by the writer in scored material | Previous use of this passage or work | Consequence for analysis |
| --- | --- | --- | --- |
| 夏竦, 免奉使 | No credited target located. His name appears in an unrelated catalog entry. | No matching work or wording. | Eligible for the eight-family **work** sensitivity analysis. |
| 劉跂, 昭雪先公謝執政 | No credited target located. | No matching work or wording. | Eligible. |
| 楊億, 潘慎修墓誌 | An author page was in a source catalog. No credited target located. | 潘慎修 also appears in a catalog title for a different document. No matching epitaph or wording. | Eligible. |
| 丁謂, reported 謝表 / 齋僧疏 | No credited target located. | No matching work or wording across all five complete and tail stimuli. | Eligible as one family. |
| 蘇軾, 提舉玉局觀謝表 | Eight rows of 《記承天寺夜遊》 in the frozen training reference. | No matching memorial, whole wording, or constituent four-character clause. | Eligible on work wording. The writer was in training. |
| 王安石, 甘師顏傳宣撫問並賜藥謝表 | 《讀孟嘗君傳》 was previously scored in the grammatical-pattern benchmarks. | No matching memorial or wording. | Eligible on work wording. The writer was in an earlier benchmark. |
| 李程 / 浩虛舟, 日五色賦 | The previous exact-ties study scored two different passages in Li's work (`bb-sun-014`, `bb-sun-031`). No credit to Hao located. | Li's entire current opening occurs as source unit `bb-sun-001` and anonymous screening unit `W07-01-001`. Hao's opening had no hit. | Report the Tang example separately. Exclude the **whole pair** from a work-held-out claim. |
| 滕甫 / 鄭獬, 圜丘象天賦 | No credited target located for either writer. | No matching work or wording. | Eligible. Zheng also appears in a different **current** family. Count the two jointly in an author-held-out analysis. |
| 鄭獬, 富弼加侍中制 | No credited target located. | No matching work or wording for any of the three versions. | Eligible. Treat the three versions as one proclamation. |
| 歐陽修, 峴山亭記 | Thirty-five rows of 《秋聲賦》 in the frozen training reference. | The Stage 1 bibliography already recorded the critic's preference. The Stage 2 design quotes both endings. Both full current stimuli are in the archived pilot passage and annotation rows. | Calibration only. Its previous use went beyond seeing the same author. |

## How to reproduce the audit

Gilbreth Slurm job `12540502` checked 3,203 readable UTF-8 files. The study's `exposure/` directory retains the input stimulus manifest, exact Stage 1–2 documents, `audit.py`, the SHA-256 and path of every searched file in `inventory.json`, the matching spans and context in `hits.json`, structured author credits, and the omissions log. The run counts repeated file copies as searched files. It counts the literary evidence by work family.

| Search scope | Files |
| --- | ---: |
| Main training inputs and references, including earlier context reference and frozen enriched reference | 4 |
| Other prior benchmark materials, including forecasts, outputs, protocols and previous checkpoints | 471 |
| Prior candidate pools and screening packets | 31 |
| Sources, pinned editions, provenance and catalogs | 2,548 |
| Previous models, pilot and independent-work expansion | 143 |
| Stage 1–2 reports, bibliography, evidence synthesis, foundations and archived Stage 2 response file | 6 |

The scan searched each complete version, constituent half-lines of at least six characters, constituent clauses of at least four, author names, selected aliases and title variants. It removed punctuation, decoded URL escapes, unified graphic variants and checked structured author credits separately from incidental mentions. A second pass examined each apparent title or wording hit in context. The two Li target IDs above come directly from the prior scored rows. [Stage 1 bibliography](literature.md) · [Stage 2 foundations](../theory/foundations.md)

**Limits.** The file inventory covers the uncompressed research material under Gilbreth's `results/`, `model-development/`, `data/` and `pilot-expansions/`, plus the five early-stage project documents. Both current-study directories, generated audio and caches, program code, duplicate staging trees, compressed packages and binary images were excluded. No candidate file failed to decode or exceeded the 16 MiB search cap. A negative result leaves external model pretraining, oral familiarity, and witnesses with substantially different diction unknown.
