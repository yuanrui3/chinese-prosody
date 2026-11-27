# Does neighboring rhyme help the written score?

**Decision.** Keep neighboring rhyme visible as evidence when reading a passage. In two blind AI editorial readings of 80 fresh sentences, including it in the written musical beauty (音律美) estimate gave slightly larger errors. The current model still improved on always giving 6. The experiment gives no support for increasing the rhyme weight or reversing its sign. Published scores stay on the frozen model for comparability. [Prospective decision rule](../research/written-rhyme-ablation.md) · [Earlier test of rhyme recognition](masked-rhyme-recovery.md)

## How close were the scores?

The test included eight Tang regulated rhapsodies (律賦) and eight Tang memorials (表), each by a different author. Each reader rated five sentences per work. The table shows mean absolute error in points on the 1–7 scale, averaging works equally. Smaller values indicate closer agreement with that reader.

| Model | Primary reader, all 80 | Primary, 賦 | Primary, 表 | Second reader, all 80 |
|---|---:|---:|---:|---:|
| Full model with neighboring rhyme | 1.332 | 1.189 | 1.474 | 1.465 |
| Refit without neighboring rhyme | **1.318** | **1.184** | 1.452 | **1.451** |
| Refit without either neighboring or within-sentence rhyme | 1.324 | 1.196 | **1.451** | 1.457 |
| Always give 6 | 1.425 | 1.250 | 1.600 | 1.587 |

The primary comparison removed the two features that match an ending against endings up to two sentences away, one each for 《廣韻》 and 《平水韻》. It retained both within-sentence rhyme features, historical tone, length, parallelism and grammar. All model variants used the same seven training works, ridge penalty and preprocessing. Each fitted model could adjust its other coefficients after a feature was removed. Predictions were bounded to 1–7 and evaluated before rounding.

- **Primary reading.** Including neighboring rhyme raised average error by **0.014** points. The paired 95% interval across works was **+0.003 to +0.025**. It lowered error in seven works and raised it in nine. Against always giving 6, the full model reduced error by **0.093** points, with a 95% interval of **0.030 to 0.158** for that reduction. The prespecified decision required improvement over both comparators.
- **Genre.** On the eight 賦, the neighboring term raised error by 0.005 points, with an interval of −0.006 to +0.019. The 賦 alone leave the effect uncertain. On the eight memorials, it raised error by 0.022 points, with an interval of +0.004 to +0.039. Removing all four rhyme features gave a less decisive comparison overall. The full model’s error minus that model’s error was +0.008, with an interval of −0.008 to +0.023.
- **Second reading.** Including neighboring rhyme again raised error by 0.014 points, with an interval of +0.005 to +0.023. The two AI sessions gave identical grades on 55 of 80 sentences and differed by one point on the other 25. They agreed exactly on 33 of 40 賦 sentences and 22 of 40 memorial sentences. Both read the same anonymous packet using the same rubric. These two passes measure the reproducibility of an AI editorial judgment.

## What limits the model now?

The full model gave the 80 sentences scores from **5.02 to 6.39**. The primary reader used **2 through 7**, including nine 7s. The second used **1 through 7**, including seven 7s. The full model reached the project’s 6.50 cutoff for rounding to 7 on **zero sentences**. Its mean estimate was 5.79, compared with 4.80 for the primary reader. Removing neighboring rhyme changed an individual forecast by only **0.045 points on average** and at most 0.088. The compressed range is a larger practical limitation than the choice between these two rhyme models.

The largest change occurred in 長孫無忌’s 「又且孩童嗣職，義乖師儉之方；任以褰帷，寧無傷錦之弊？」. Both readers gave it **5**. The full model gave **5.986** and the refit without neighboring rhyme gave **5.898**. All four measured rhyme features were zero on this sentence. The small change records the effect of refitting the model, including its training averages and other weights. [Original memorial](https://zh.wikisource.org/w/index.php?oldid=2578312)

Training contained **337 written ratings from seven works**, including **209 from 《拉法叶赋》**. In the fitted model, taking the neighboring-rhyme measure from 0 to 1 changes the estimate by −0.060 points for 《廣韻》 and −0.110 for 《平水韻》, holding other features fixed. Omitting 《拉法叶赋》 from training changed the 《廣韻》 coefficient to **+0.427**. The combined change when both measures rise went from **−0.169 to +0.070**. Across 2,000 whole-training-work resamples, the central 95% of combined slopes ranged from **−0.424 to +0.515**. With only seven training works, these figures show sensitivity to the composition of the reference set. They offer little basis for assigning rhyme a general reward or penalty.

**Earlier comparison.** A separately sealed set of 64 ratings on eight other formal prose works gave errors of **1.123** for the full model, **1.090** without neighboring rhyme and **1.234** for always giving 6. The refit without neighboring rhyme was closer in all eight works. The release scorer reproduced all 64 original target forecasts exactly. These works had already informed other project hypotheses, so their results were kept outside the prospective decision. [Original archived study](stage-7.md#transfer-from-the-yu-xin-review)

## Sampling, historical period and blinding

The final draw screened 175 candidate records across 102 《全唐文》 volume catalogues. The project reserved 449 author names, 1,744 titles, 1,112 edition revisions and 7,143 earlier text spans. All thirty authors in the previous masked-rhyme experiment were reserved. Across the 16 new works, all 393 sentences stayed in their original paragraph order for scoring. Five eligible, distinct sentences of at least six Han characters were chosen at evenly spaced positions in each work. The sampled positions were chosen before any rating or feature calculation. [Source selection](../src/written_rhyme_sources.py)

An initial draw admitted 王樸’s Later Zhou calendar memorial and 徐鉉’s memorial on the Southern Tang emperor. The anthology’s editors explicitly include Five Dynasties material. The first packet and its unopened automated forecasts were archived before either reader received any text. The corrected draw linked each work to its own author heading and required a biographical passage attesting activity under a Tang ruler. The matching is at dynasty level. Exact dates of composition can remain uncertain. [Anthology editorial principles](https://zh.wikisource.org/wiki/全唐文凡例) · [王樸, 《新五代史》](https://www.shidianguji.com/zh/book/NGJ8924119990225562058/chapter/1loz4nli3ke8a) · [徐鉉, 《全唐文》卷八七八](https://ctext.org/wiki.pl?chapter=171505&if=en)

Each of two separate AI editorial sessions saw only the anonymized target, up to two preceding and following sentences in the same paragraph, and the written 1–7 rubric. The primary session was designated in advance. Each supplied a verbatim quotation and a sentence-specific reason. The packet omitted assigned-rhyme headings, titles, credited authors, model outputs and the research hypothesis. Familiar lines and official formulas could still identify a genre or work. Forecasts were sealed before either session received the corrected packet. Confidence intervals resample whole works within each genre, using the same 10,000 draws for paired model comparisons. They describe variation across these works conditional on the given editorial reading. [Frozen protocol](../research/written-rhyme-ablation.md) · [Fitting and evaluation](../src/written_rhyme_ablation.py)

## Held-out works

Each row represents five graded targets. The final two columns report mean absolute error for the designated primary reader. The author notices in the archive establish historical activity for each credited writer.

| Work and credited author | Form | Sentences in context | Full | Without neighboring rhyme |
|---|---|---:|---:|---:|
| 尹樞 [《華山仙掌賦》](https://zh.wikisource.org/w/index.php?oldid=1980786) | 賦 | 34 | 1.199 | 1.214 |
| 劉積中 [《樂德教胄子賦》](https://zh.wikisource.org/w/index.php?oldid=8733483) | 賦 | 31 | 2.111 | 2.103 |
| 皇甫威 [《回文錦賦》](https://zh.wikisource.org/w/index.php?oldid=1972824) | 賦 | 31 | 0.635 | 0.645 |
| 獨孤良器 [《放馴象賦》](https://zh.wikisource.org/w/index.php?oldid=1974017) | 賦 | 22 | 2.099 | 2.102 |
| 李為 [《握中有元璧賦》](https://zh.wikisource.org/w/index.php?oldid=1974040) | 賦 | 28 | 0.600 | 0.592 |
| 呂牧 [《子擊磬賦》](https://zh.wikisource.org/w/index.php?oldid=1980678) | 賦 | 35 | 1.072 | 1.026 |
| 李琚 [《公孫宏開東閣賦》](https://zh.wikisource.org/w/index.php?oldid=8735793) | 賦 | 19 | 0.748 | 0.732 |
| 張仲方 [《披沙揀金賦》](https://zh.wikisource.org/w/index.php?oldid=8733403) | 賦 | 29 | 1.051 | 1.057 |
| 張廷珪 [《請河北遭旱澇州準式折免表》](https://zh.wikisource.org/w/index.php?oldid=2280418) | 表 | 18 | 1.054 | 1.057 |
| 高適 [《謝上彭州刺史表》](https://zh.wikisource.org/w/index.php?oldid=484518) | 表 | 17 | 1.665 | 1.635 |
| 房元齡 [《諫伐高麗表》](https://zh.wikisource.org/w/index.php?oldid=2140144) | 表 | 43 | 0.726 | 0.746 |
| 長孫無忌 [《辭功臣襲封刺史表》](https://zh.wikisource.org/w/index.php?oldid=2578312) | 表 | 22 | 1.149 | 1.118 |
| 苑咸 [《為李林甫讓中書令表》](https://zh.wikisource.org/w/index.php?oldid=518702) | 表 | 23 | 1.305 | 1.243 |
| 王徽 [《請車駕還京表》](https://zh.wikisource.org/w/index.php?oldid=1970886) | 表 | 17 | 2.150 | 2.151 |
| 劉仁軌 [《諫幸同州校獵表》](https://zh.wikisource.org/w/index.php?oldid=1970928) | 表 | 10 | 1.265 | 1.227 |
| 劉知古 [《進日月元樞論表》](https://zh.wikisource.org/w/index.php?oldid=1979173) | 表 | 14 | 2.481 | 2.440 |

## Verification and scope

Gilbreth jobs `12590214` and `12590297` produced the corrected corpus, forecasts and final comparisons. Job `12590024` replayed the earlier eight-work comparison. The archive is `$SHUNKOU_ROOT/results/written-rhyme-DvfWnBBA`. It holds the edition texts and dates, blind packet, ratings with evidence, model fits, work-level errors and all checksums. The full refit reproduced the release forecasts exactly. An NVIDIA A10 independently reproduced the numerical forecasts to within 9 × 10⁻¹⁶ and verified the paired evaluation intervals. The corrected anonymous packet hash begins `1d87a95ee0e2`, and the fixed forecasts hash begins `302e479ba240`. [Gilbreth reproduction](../hpc/README.md#written-score-with-and-without-neighboring-rhyme)

**Next distinction.** A work-balanced training comparison can test whether reliance on one dominant work explains the narrow score range. The roadmap’s acoustic comparison can test whether written rhyme is audible in the actual recorded variety. Listener judgments of 音律美 and the independent cold read-aloud task for 顺口 remain reserved for final participant validation.
