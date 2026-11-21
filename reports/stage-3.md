# Stage 3 · Data checkpoint

The initial corpus is built on Gilbreth. It contains **12 matched excerpts** from sixth-century and Early Tang texts, **three Northern Song critic probes**, and **14 reference spans**. The [pilot data card](../data/pilot/DATA_CARD.md) gives the match design, verified digital witnesses, rights, and critical provenance. The [collection cards](../data/collections/DATA_CARDS.md) describe the reference spans and the broader acquisition pipeline.

## Corpus design

**Established source evidence.** Six pairs each contain a parallel-prose (骈文) passage and a piece of comparison prose from the same broad period and subject. Matched excerpts have 20–28 Han characters, with a difference of 0–4 characters per pair. The 15 excerpts were recovered from nine pinned Wikisource pages and passed the reviewed SHA-256 checks. Two Northern Song probes preserve the shorter and longer variants discussed in connection with 《峴山亭記》. The third preserves a point annotated as 文氣一頓. [Source and passage manifest](../data/pilot/passages.json) · [《默記》卷下](https://www.shidianguji.com/zh/book/CZBZZ051/chapter/1kxs7vmwg6230)

**Contested scope.** Genre labels apply to selected passages. Comparison prose can contain local parallelism. Thirteen manually proposed ordered clause pairings capture local syntax and rhetoric without reference to historical tone conformity. The six matches do not control allusions, lexical familiarity, or editorial punctuation. Group by work in future holdouts and keep paired variants together.

**Project hypothesis.** Regular four- and six-character phrasings with unfamiliar words, uneven narrative prose, and rhythmically balanced comparison prose should give the next trial more opportunities to distinguish 音律美 from 顺口. The set includes one excerpt overlapping the earlier author trial for a repeat reading. The two questions and the hypothesized spread of ratings remain to be tested on this set.

## Annotation coverage

The 15 pilot excerpts contain 395 Han slots. Historical tone and rhyme come from the pinned 《廣韻》 and 《平水韻》 sources. The 《廣韻》 tier includes Middle Chinese initial and final transcriptions where supported. Unihan 17.0.0 provides modern Mandarin pinyin and Cantonese Jyutping candidates. [Historical lexicon card](../data/phonology/HISTORICAL.md) · [Modern readings card](../data/phonology/MODERN.md)

| Reading tier | One lookup candidate | Multiple unresolved candidates | Context reviewed | Missing |
| --- | ---: | ---: | ---: | ---: |
| 《廣韻》 | 278 | 111 | 1 | 5 |
| 《平水韻》 | 293 | 90 | 0 | 12 |
| Mandarin | 192 | 202 | 1 | 0 |
| Cantonese | 395 | 0 | 0 | 0 |

One 《平水韻》 slot uses a documented traditional-variant lookup. A single candidate describes coverage in the dictionaries, particularly for customary Cantonese readings. Context reviews select the rainwater sense of 潦 in 《滕王閣序》 and the Mandarin return sense of 還 in 《哀江南賦序》. Unchosen candidates remain in the outputs. Actual pronunciation belongs to the audio layer. [Context decisions](../data/pilot/context-reviews.json)

## Gilbreth verification and expansion

The authenticated Gateway file manager and built-in shell verified access to the scratch project. Python 3.9.25 built `data/pilot/passages.jsonl`, `data/pilot/annotated.jsonl`, and `data/pilot/annotation-summary.json` under `${RCAC_SCRATCH}/shunkou`. The summary gives checksums for the three cached lexicon inputs. The small seed build produced `data/collections/anthology-seed.jsonl` from eleven pinned source revisions. It includes 赋 and parallel prose, prescribed-rhyme 律赋, 散曲 and 雜劇 excerpts, and three early twentieth-century lyric contrasts. The first seed attempt encountered HTTP 429 after caching ten revisions. A later run reused those responses and acquired the final revision. Run logs are `logs/stage3-20261121-r2.log` and `logs/stage3-anthologies.log`. The working corpus and reserved audio directories are both in the project scratch. [Gateway and rebuild instructions](../hpc/README.md)

The pinned bulk 唐诗, 宋词, and 元曲 importers passed local fixture checks. Bulk acquisition and normalization on an eligible compute allocation, full anthology coverage, and additional rights-cleared modern lyrics remain open. Purdue requires batch jobs on Gilbreth to use GPUs. The small text verification used the Gateway shell and no Slurm allocation. Audio collection and acoustic validation are Stage 4 work. [Purdue cluster guidance](https://docs.rcac.purdue.edu/workshops/hpc_exchange/week2/clusters/#gilbreth)
