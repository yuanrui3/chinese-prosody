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

## Independent-work pilot expansion

**Established source evidence.** The follow-up adds eight excerpts from eight works by eight credited authors absent from the original corpus. Taken together the matched pilot now has 20 excerpts, ten pairs, and 16 source works. The three Northern Song probes remain outside those totals. The four new pairs cover sixth-century and Early Tang works, with one example of each period in each task. Within-pair lengths differ by at most two Han characters. The release checks the reviewed Wikisource spans against the project’s pinned excerpt hashes. The annotated corpus and coverage summary are in `$SHUNKOU_ROOT/pilot-expansions/independent-works/data/pilot`. [Matching design and primary witnesses](../data/pilot/DATA_CARD.md#independent-work-expansion)

The eight passages contain 199 Han slots. Lookup candidates were available for 196 slots in 《廣韻》 and 194 in 《平水韻》. There are 63 and 52 unresolved multiple-candidate slots, respectively. The modern Mandarin lookup has candidates for 199 slots, with 93 unresolved multiple-candidate slots. Cantonese has one dictionary candidate per slot. The text files preserve these alternatives alongside the separate synthetic reading prescriptions.

**Project hypothesis.** Sampling new works helps test whether earlier observations recur outside passages by the original authors. This expansion uses different works for the two tasks. It supports separate follow-up tests for each outcome. Estimating how the outcomes relate on the same works would require independent readers and listeners or counterbalanced assignments.

## Source-checked reading flags from the Gemini review

On 2026-11-22, the free, signed-out Gemini web app in Auto mode reviewed five short public-domain excerpts. Google AI Studio required sign-in. The public-text prompt asked for context-sensitive historical readings and traceable critics' comments. The app supplied six flags. Four have multiple readings in the pinned rhyme book, and two have just one attested candidate there. The review used public text only. Audio stayed on Gilbreth. [Criticism results](stage-2.md#source-checked-criticism-from-the-gemini-review) · [Pilot witness manifest](../data/pilot/passages.json) · [Fresh-work witness manifest](../data/pilot/historical-increment.json)

**Established source evidence.** The following entries use the exact rhyme labels and entry IDs from the project's pinned 《廣韻》 transcription. The glosses and positions are dictionary evidence. Context preferences in the right-hand column are project interpretations. None depend on which reading would make a clause pair more regular. [Pinned 《廣韻》 transcription](https://github.com/nk2028/tshet-uinh-data/blob/21585e22c8a730ca2fd175112f4d18e16d5ce578/韻書/廣韻.csv)

| Passage and character | Attested 《廣韻》 readings | Context review |
| --- | --- | --- |
| SD01 人間何**世** | 祭/去, 舒制切 (2410/1), glossed 代也 | One candidate. Gemini's suggestion of an entering-tone remnant supplies no alternate historical annotation. [Passage witness](https://zh.wikisource.org/w/index.php?oldid=3656893) |
| SD01 壯士不**還** | 刪/平, 戶關切 (543/1), includes 反也 and 復也. 仙/平, 似宣切 (624/13), explicitly glosses 還返. | The ordinary return sense supports 戶關, with both historical candidates retained. Both are 平. The existing modern Mandarin review selects *huán*. [Passage witness](https://zh.wikisource.org/w/index.php?oldid=3656893) · [Modern reading review](../data/pilot/context-reviews.json) |
| HSD2P 五言流**調** | 嘯/去, 徒弔切 (2762/4), includes 韻調. 蕭/平, 徒聊切 (651/13), includes 和也. 尤/平, 張流切 (1013/7), glossed 朝也. | Prefer 嘯/去 for the noun describing the form or style of five-character verse. The synthesis prescription is *diào*. Choosing the 蕭 reading would reverse the 平仄 label. [Passage witness](https://zh.wikisource.org/w/index.php?oldid=2096346) |
| ET01 **潦**水盡 | 晧/上, 盧晧切 (1715/6), glossed 雨水. 号/去, 郎到切 (2814/3), refers back to 澇. | The existing selection 晧/上 fits pooled rainwater. Both attested candidates are 仄. The supplied 蕭/平 river-name entry is absent from the pinned book. The modern dictionary gives *lǎo* for pooled water. [Passage witness](https://zh.wikisource.org/w/index.php?oldid=12697774) · [Ministry of Education dictionary](https://dict.revised.moe.edu.tw/dictView.jsp?ID=3297&q=1&word=%E6%BD%A6) · [Context review](../data/pilot/context-reviews.json) |
| HET2P **應**接如響 | 證/去, 於證切 (3009/1), includes 物相應也. 蒸/平, 於陵切 (950/2), glossed 當也. | Prefer 證/去 for responding like an echo. This token is inside its clause. The modern *yìngjiē* is attested for the compound. [Passage witness](https://zh.wikisource.org/zh-hant/唐昭容上官氏文集序) · [Ministry of Education dictionary](https://dict.revised.moe.edu.tw/dictView.jsp?ID=158525&la=0&powerMode=0) |
| HET1P 遐**該**於有識 | 咍/平, 古哀切 (387/1), includes 備也 and 兼也. | One candidate. The context supports 'encompass' as the lexical sense. Gemini identified a sense distinction here. [Passage witness](https://zh.wikisource.org/w/index.php?oldid=494677) |

Four further flags came from a separate check of the source texts and rhyme book.

| Passage and character | Attested 《廣韻》 readings | Context review |
| --- | --- | --- |
| HET2P 顧問不**遺** | 脂/平, 以追切 (166/4), includes 失也 and 亡也. 至/去, 以醉切 (2244/1), glossed 贈. | Prefer 脂/平 for omission. The synthesis prescription is *yí*. The alternative would reverse 平仄 at this clause ending. [Passage witness](https://zh.wikisource.org/zh-hant/唐昭容上官氏文集序) |
| HET1P 遐該於有**識** | 職/入, 賞職切 (3702/1), glossed 知也. 志/去, 職吏切 (2251/7), glossed 標識. | Prefer 職/入 for knowledge or awareness. The synthesis prescription is *shí*. Both alternatives are 仄. [Passage witness](https://zh.wikisource.org/w/index.php?oldid=494677) |
| HSD4P **三**復九思 | 談/平, 蘇甘切 (1090/1), for the numeral. 闞/去, 蘇暫切 (3127/1), glossed 三思. | Keep both. 陸德明 records both readings for 三復 in his commentary on a different occurrence in the *Analects*. [Passage witness](https://zh.wikisource.org/w/index.php?oldid=2627304) · [《經典釋文·論語音義》](https://zh.wikisource.org/zh-hant/經典釋文_(四部叢刊本)/卷第二十四) |
| HSD4P 三復九**思** | 之/平, 息兹切 (190/1), glossed 思念. 志/去 (2255/3), glossed 念. | Keep both. The possible 九思 allusion clarifies the sense without settling the historical tone here. [Passage witness](https://zh.wikisource.org/w/index.php?oldid=2627304) · [《論語·季氏》](https://zh.wikisource.org/zh-hant/論語/季氏第十六) |

The review records candidate sets and proposed contextual choices for later text analyses. The original annotations and completed holdout results retain their recorded inputs. Synthetic reading prescriptions belong to the modern Mandarin layer. The historical entries supply no timing or pronunciation measurements for the recordings. [Rhyme-book data card](../data/phonology/HISTORICAL.md) · [Historical-feature benchmark](stage-5.md#historical-tone-and-rhyme-on-fresh-works)
