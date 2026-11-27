# Does equal training weight help find exceptional lines?

**Finding.** On 96 fresh Tang sentences, giving every training work equal influence raised the typical forecast and missed all nine sentences both blind AI readers graded 7. The released model also missed all nine, but came closer to the editorial grades overall and put more of the exceptional sentences above their neighbors. Retain the released model for comparisons. The test concerns written musical beauty (音律美). The listening judgment and first-read ease (顺口) remain for final participant testing.

## Scores on fresh works

A prediction counted as a 7 at 6.50 before rounding. Mean absolute error is the average distance from the reader’s grade, in points on the 1–7 scale. Each work contributed six targets and had equal weight at evaluation in all three comparisons.

| Method | Fresh score range | Overall SD | Mean within-work SD | Editorial 7s found | False 7s | Mean error, primary | Mean error, second |
|---|---:|---:|---:|---:|---:|---:|---:|
| Released model | 4.821–6.208 | 0.311 | 0.240 | 0/9 | 0 | **1.389** | **1.282** |
| Equal training weight per work | 4.942–6.356 | 0.300 | 0.251 | 0/9 | 0 | 1.514 | 1.393 |
| Always give 6 | 6.000–6.000 | 0 | 0 | 0/9 | 0 | 1.604 | 1.500 |

**Did the scores spread out?** The distance between the lowest and highest forecast widened by 0.026 points, while the overall standard deviation (SD) fell by 0.011. The mean spread within individual works rose by 0.011. Both SD changes were small relative to variation between works. In 10,000 paired resamples of works within genres, their 95% intervals were −0.050 to +0.027 overall and −0.019 to +0.042 within works. Resampling the eight intact period pairs gave the same interpretation.

**Did the scores find better lines?** Both readers selected exactly the same nine 7s across seven works. Four were in the rhapsodies and five in the prose. All three methods missed them all. With zero calls, recall was zero, precision was undefined and no non-7 was promoted. All 999 within-work shuffles necessarily produced zero hits. On an exploratory ranking check, an editorial 7 outranked a lower-graded sentence from its own work **61.4%** of the time under the released model, **38.9%** under equal training weights and **50.0%** under the constant score. Ties count as half and the seven eligible works count equally. This check uses the same nine 7s and has a small denominator.

| Primary reading | Units | Editorial 7s | Released mean error | Equal-work mean error | Always-6 mean error |
|---|---:|---:|---:|---:|---:|
| Regulated 賦 | 48 | 4 | 1.105 | 1.151 | 1.250 |
| Period-matched 記 and 議 | 48 | 5 | 1.674 | 1.877 | 1.958 |

The increase in primary mean error from changing the weights was **0.125** points (paired 95% interval **+0.055 to +0.200**). Keeping period pairs intact gave **+0.056 to +0.203**. Equal weighting still beat the constant by 0.090 points (95% interval 0.038 to 0.147 in its favor). The second reader also favored the released model over equal weights by 0.111 points (95% interval +0.033 to +0.192). The two readers agreed exactly on 72/96 grades and were within one point on all 96. They belong to the same AI model family. Independent sessions test consistency within that family.

### Two sentences behind the numbers

In 章孝標’s 《王師如時雨賦》, **「龍旗電掣，疑驅蔚矣之雲；鼉鼓雷奔，似送沛然之雨。」** received a 7 from both readers. Each noted the movement from the short strokes 龍旗電掣 and 鼉鼓雷奔 into the longer cloud and rain phrases. The released model gave it **5.71**, equal weighting **5.86**. [Primary text](https://zh.wikisource.org/w/index.php?oldid=1980844)

The highest equal-weight forecast, **6.36**, went to 劉承慶’s explanation of the number of ancestral temples. Both readers gave it **2**. They recognized the balanced ending, **「本由太祖有遠近之異，故初建有多少之殊」**, and found the layered qualifications before it slowed the sentence. The released forecast was **5.96**. These examples explain why raising all high-end predictions or lowering the 7 cutoff would still leave a ranking problem. [Primary text](https://zh.wikisource.org/w/index.php?oldid=8732458)

## Earlier-work check and decision

The released scorer reproduced all 80 forecasts from the earlier eight-rhapsody, eight-memorial study exactly. Equal weighting moved the maximum from 6.38746 to **6.49951**, just below the fixed cutoff. Both fits caught zero of the primary reader’s nine and the second reader’s seven exceptional lines. Primary mean errors were 1.332 for the released fit, 1.355 for equal weighting and 1.425 for always giving 6. This previously seen sample had no vote in the fresh decision. [Earlier study](written-rhyme-ablation.md)

**Decision.** The candidate met two of six prespecified conditions, a larger average within-work SD and no increase in false 7s. It missed the requirements for overall dispersion, additional correct 7s, newly caught 7s across at least two works and mean error. The current model remains the benchmark. A new project hypothesis is to train a within-work comparison on earlier graded lines and test whether it ranks exceptional passages above nearby 5s and 6s on another untouched set, before calibrating a numerical cutoff. The 96 target grades in this report can no longer serve as an untouched test for that hypothesis. No participant ratings were collected and no audio was used here.

## What changed in training

The seven works supplied the same 337 editorially graded passages in both fits. The released model gave one vote to each passage, so 《拉法叶赋》 supplied 209/337, or 62.0% of the weight. The candidate gave each work one seventh, or 14.3%. An individual sentence in the shortest work, with eight passages, therefore received about 26 times the weight of one sentence in 《拉法叶赋》. Both fits used the same text features, historical dictionaries, ridge penalty of 10, grade bounds and unrounded 6.50 cutoff for a 7. No test grades entered either fit. [Prospective design](../research/work-weighted-training.md)

Equal weighting increased the training share of 7s from 14.8% to 19.0%, increased the share of 6s from 47.5% to 50.2%, and reduced the share of 4s from 8.0% to 3.6%. Neither training distribution contained grades 1–3. The fitted average training grade rose from 5.691 to 5.846. On the fresh works the average forecast rose from 5.658 to 5.837. Giving the shorter works more influence mainly shifted the typical prediction upward.

## Works and reading conditions

Eight Tang regulated rhapsodies (律賦) represent parallel prose (駢文). Each has a discursive prose counterpart from the same broad period of author activity. Four records (記) and four deliberative pieces (議) make up the comparison arm. These prose authors can also use parallel phrasing or quote verse. The comparison is between literary forms. Six of the eight pairs fall between the reigns of Suzong and Xianzong, one in the earlier stratum and one in the later stratum. The dates in the table record the anthology's evidence for the author. Individual works can be dated less precisely. [Anthology author notices for 王履貞, 林藻, 張嗣初 and 李遜](https://zh.wikisource.org/w/index.php?oldid=8735956) · [Author notices for 韋充 and 韋端符](https://zh.wikisource.org/w/index.php?oldid=1159630)

| Pair | Regulated 賦 and dating evidence | Discursive prose and dating evidence |
|---|---|---|
| 1 | 王履貞 [《辟雍賦》](https://zh.wikisource.org/w/index.php?oldid=1980670) · 貞元 | 蕭定 [《袁州文宣王廟記》](https://zh.wikisource.org/w/index.php?oldid=1973237) · 大曆 |
| 2 | 林藻 [《冰池照寒月賦》](https://zh.wikisource.org/w/index.php?oldid=8735953) · 貞元 | 崔祐甫 [《奏貓鼠議》](https://zh.wikisource.org/w/index.php?oldid=1975743) · 德宗朝 |
| 3 | 張嗣初 [《鄉老獻賢能書賦》](https://zh.wikisource.org/w/index.php?oldid=2079731) · 貞元 | 閻伯瑾 [《黃鶴樓記》](https://zh.wikisource.org/w/index.php?oldid=1974233) · 永泰 |
| 4 | 張莒 [《紫宸殿前櫻桃樹賦》](https://zh.wikisource.org/w/index.php?oldid=1980404) · 大曆 | 韋彤 [《太廟朔望進食議》](https://zh.wikisource.org/w/index.php?oldid=1973192) · 德宗時 |
| 5 | 章孝標 [《王師如時雨賦》](https://zh.wikisource.org/w/index.php?oldid=1980844) · 元和 | 程皓 [《駁顏真卿論韋陟不得諡忠孝議》](https://zh.wikisource.org/w/index.php?oldid=1972917) · 代宗朝 |
| 6 | 呂令問 [《金莖賦》](https://zh.wikisource.org/w/index.php?oldid=1979689) · 元宗時 | 劉承慶 [《七廟議》](https://zh.wikisource.org/w/index.php?oldid=8732458) · 聖曆 |
| 7 | 陳詡 [《西掖瑞柳賦》](https://zh.wikisource.org/w/index.php?oldid=8733618) · 大曆 | 李遜 [《遊妙喜寺記》](https://zh.wikisource.org/w/index.php?oldid=2079716) · 元和 |
| 8 | 韋充 [《庾氏子碎玉賦》](https://zh.wikisource.org/w/index.php?oldid=1979727) · 長慶 | 韋端符 [《衛公故物記》](https://zh.wikisource.org/w/index.php?oldid=1974553) · 穆宗朝 |

The screen reserved 490 earlier author names, 1,946 titles, 1,313 edition revisions and 4,260 earlier text spans of at least twelve characters. The source log covers 115 candidate records and 100 anthology volume catalogues. Six distinct sentences of at least six characters were selected at spaced positions in each work. The scoring models received all 385 sentences in paragraph order. Each anonymous reader saw the target and up to two adjacent sentences on each side within the paragraph. Each supplied an integer grade, an exact quotation and a reason. A 7 meant “exceptional and worth memorizing.” Two sessions of the same AI model provide two editorial readings. Historical expert consensus and human listening preferences have separate evidentiary requirements. [Source selection](../src/work_weighted_sources.py) · [Scoring and decision rule](../src/work_weighted_scores.py)

**Source correction before grading.** The first packet included 王士詹’s 《五臺山設萬僧供記》. The edition marks missing characters in three sentences, two selected for grading. We kept that packet and its forecasts in a separate archive, excluded works containing explicit lacunae, and reran the same selection procedure before releasing anything to the readers. 李遜’s 《遊妙喜寺記》 entered the final sixteen. The forecast fit, cutoff and decision criteria stayed fixed. [王士詹’s witness](https://zh.wikisource.org/w/index.php?oldid=8665988)

## Gilbreth record

The reproducible archive is `$SHUNKOU_ROOT/results/equal-work-FvEkoQYG`. Job `12590614` produced the first source screen, `12590666` froze the corrected forecasts, `12590758` joined the two readings and evaluated the fits, and `12590759` independently verified the results. Job `12590615` replayed the earlier 80 targets. The final forecast SHA-256 is `3d0bfebfe39b97352102574b55cec70531d2bcbbe787e47b3a7e10912fa6cc1f`. The independent verifier checked the source seals, the two original grade files, each comparison and the earlier forecast archive. GPU and CPU predictions differed by at most 8.9 × 10⁻¹⁶ points. The ratings, source witnesses and per-target forecasts are kept on Gilbreth. [Reproduction instructions](../hpc/README.md#giving-each-training-work-equal-weight)
