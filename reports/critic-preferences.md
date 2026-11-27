# Do historical critics and the written scorer prefer the same wording?

**The current model recovers the known cadence example. This study provides no fresh estimate of how often it agrees with historical critics about the sound of parallel prose (骈文).** The source screen distinguishes a judgment about the sound of two wordings from praise for a particular line, preference for its meaning, or a decision about how to pronounce one character. The 24 wordings below supplied 13 comparisons from 10 literary examples. Nine comparisons have equal character counts. Of the 13, nine are unranked, three have literary preferences and one was already in the pilot. Each of the three literary comparisons and the calibration belongs to a different family. A half credit means a tie. The sources supply no numerical human ratings. [Frozen comparison rules](../research/critic-preferences.md) · [Source and pronunciation manifest](../research/critic-variants.json)

## A sound judgment the current scorer cannot express

In a passage of Shen Yue’s 《郊居賦》, Wang Yun (王筠) read 霓 with a checked tone (入聲). The biography says Shen applauded and had worried that readers would use the level tone (平聲). The difference is audible in principle even though both readers see the same character. The biography preserves the readings by fanqie (反切). 《梁書》 also transmits the work itself with different graphs. We used **駕雌霓之連蜷** on both sides, following the wording in Sun’s anthology. [《梁書》, Wang Yun’s biography](https://zh.wikisource.org/w/index.php?oldid=762672) · [《梁書》, Shen Yue and the text of the fu](https://zh.wikisource.org/w/index.php?oldid=1494993) · [Sun's source and edition audit](../research/critics-sun.md)

| Reading of 霓 | Historical 平仄 of the six characters | Longest run of 平 | Current written score |
| --- | --- | ---: | ---: |
| Checked, approved in this account | 仄平仄平平平 | 3 | 5.298 |
| Level, the alternative Shen mentions | 仄平平平平平 | 5 | 5.298 |

These counts came from running each reading through the historical dictionary on Gilbreth. The later 《廣韻》 has three candidates for 霓, in 平、去、入. The biography identifies the two relevant categories. The current scorer receives the same characters and the same unresolved dictionary entry twice. Supplying the reading separately lets us describe a two-syllable difference in the longest run of level tones. A later account explicitly relates Shen’s choice to the passage’s sound. This one example cannot tell us how strongly to reward breaking up level tones elsewhere. The study made no Mandarin recording purporting to reproduce this historical distinction. [Sima Guang, 《范景仁傳》](https://zh.wikisource.org/w/index.php?oldid=706025) · [Pinned historical dictionary](https://github.com/nk2028/tshet-uinh-data/tree/21585e22c8a730ca2fd175112f4d18e16d5ce578) · [Reproducible reading test](../src/critical_reading_probe.py)

## What happened when the wording changed

In the known Song prose example, Zhang Dun (章惇), as reported by Wang Zhi, objected to the abrupt ending of 一置茲山，一投漢水. The received text has 一置茲山之上，一投漢水之淵. The current scorer prefers the expanded version, **6.140 to 5.926**. Counting characters alone also prefers it, by 0.000402 points. That agreement cannot isolate a benefit from tone or rhyme. The surrounding wording matches the previous pilot exactly. [《默記》卷下](https://www.shidianguji.com/zh/book/CZBZZ051/chapter/1kxs7vmwg6230) · [Received 《峴山亭記》](https://zh.wikisource.org/wiki/峴山亭記)

| Documented comparison | Current model | Character count alone | Always 6 |
| --- | --- | --- | --- |
| Six Dynasties or Tang parallel prose, explicit sound preference between different wordings | No eligible pair | No eligible pair | No eligible pair |
| Song parallel prose, same criterion | No eligible pair | No eligible pair | No eligible pair |
| All three literary choices, including one previously seen Tang work | Two ties, one reversal (0.333 credit) | Three ties (0.500) | Three ties (0.500) |
| Two literary choices on previously unused works, both Song | Two ties, 0.500 | Two ties, 0.500 | Two ties, 0.500 |
| Previously used Song prose cadence comparison | Preferred version higher | Preferred version higher | Tie |

For **寸心／巧心**, Gong Mingzhi’s note prefers 寸 because of its relationship to 眾 across the couplet. The scorer gives both full passages 5.970. It also ties the two word orders in the Song examination fu. In the Tang examination anecdote the reported preference is Li Cheng’s for his own opening. The model prefers Hao Xuzhou’s opening. The two examination cases compare different writers, and Li’s is a self-assessment. They carry a different evidential weight from Gong’s one-character correction. An independent search found Li’s opening in a previous screening packet. The two previously unused works both tied under all three methods. This estimates agreement with these two literary decisions only. [Gong’s entry](https://zh.wikisource.org/w/index.php?oldid=752813) · [Chen Zhensun’s account of the Song examination](https://zh.wikisource.org/w/index.php?oldid=2359094) · [Sun’s account of the Tang examination](https://www.shidianguji.com/book/CADAL02110211/chapter/1lcn2qekr9lib)

## All paired written results

The two scores in each cell follow the order A, B. Figures show the continuous model output before rounding to a 1–7 grade. The comparison used full precision. All 24 versions were scored as isolated quotations. Two versions never supplied context for one another. The historical text table on Gilbreth retains admissible dictionary readings at each clause ending. [Scoring code](../src/critical_preferences.py)

| Comparison | A | B | Critic’s direction and use | Han counts | Current score A / B | Witnesses |
| --- | --- | --- | --- | ---: | ---: | --- |
| Xia | 義不戴天，難下單于之拜；哀深陟屺，忍聞禁佅之音。 | 義不戴天，難下穹廬之拜；禮當枕塊，忍聞夷樂之聲。 | Unranked | 20 / 20 | 5.788 / 5.788 | [A](https://zh.wikisource.org/w/index.php?oldid=699715) · [B](https://zh.wikisource.org/w/index.php?oldid=2599511) |
| Liu | 晚歳離騷，難招魂於鬼域；平生精爽，或見夢於故人。 | 晚歳離騷，魂竟招于異域；平生精爽，夢猶託于故人。 | Unranked | 20 / 20 | 5.677 / 5.714 | [A](https://zh.wikisource.org/w/index.php?oldid=2098020) · [B](https://zh.wikisource.org/w/index.php?oldid=770542) |
| Yang | 喬木不勝，空悲故國；曳裾王府，猶見故君。 | 思喬木於故國，尚見世臣；曵長裾于王門，兼掌記室。 | Unranked | 16 / 20 | 6.072 / 5.654 | [A](https://zh.wikisource.org/w/index.php?oldid=2098020) · [B](https://zh.wikisource.org/w/index.php?oldid=709753) |
| Ding-witnesses | 補仲山之袞，雖罄一心；調傅說之羹，難諧眾口。 | 補仲山之袞，雖曲盡於巧心；和傅說之羹，實難調於眾口。 | Unranked | 18 / 22 | 5.918 / 5.970 | [A](https://zh.wikisource.org/w/index.php?oldid=682652) · [B](https://zh.wikisource.org/w/index.php?oldid=787704) |
| Ding-word | 補仲山之袞，雖曲盡於巧心；和傅說之羹，實難調於眾口。 | 補仲山之袞，雖曲盡於寸心；和傅說之羹，實難調於眾口。 | B · literary | 22 / 22 | 5.970 / 5.970 | [A](https://zh.wikisource.org/w/index.php?oldid=787704) · [B](https://zh.wikisource.org/w/index.php?oldid=752813) |
| Su | 七年遠謫，不意自全；萬里生還，適有天幸。 | 七年遠謫，不自意全；萬里生還，適有天幸。 | Unranked | 16 / 16 | 6.044 / 6.044 | [A](https://zh.wikisource.org/w/index.php?oldid=781274) · [B](https://www.shidianguji.com/book/HY0641/chapter/1mb8i6weau6uj) |
| Wang | 信使恩言，有華原隰；寶奩珍劑，增賁丘園。 | 膚使寵辭，載華原隰；寶奩珍劑，加賁丘園。 | Unranked | 16 / 16 | 6.154 / 6.154 | [A](https://zh.wikisource.org/w/index.php?oldid=682652) · [B](https://zh.wikisource.org/w/index.php?oldid=856848) |
| Exam-Tang | 德動天鑒，祥開日華。 | 麗日焜煌，中含瑞光。 | A · literary | 8 / 8 | 5.650 / 5.813 | [A](https://www.shidianguji.com/book/CADAL02110211/chapter/1lcn2qekr9lib) · [B](https://www.shidianguji.com/book/CADAL02110211/chapter/1lcn2qekr9lib) |
| Exam-Song | 大禮必簡，圜丘自然。 | 禮大必簡，丘圜自然。 | B · literary | 8 / 8 | 5.721 / 5.721 | [A](https://zh.wikisource.org/w/index.php?oldid=2359094) · [B](https://zh.wikisource.org/w/index.php?oldid=2359094) |
| Calibration | 元凱銘功於二石，一置茲山，一投漢水，是知陵谷有變，而不知石有時而磨滅也。 | 元凱銘功於二石，一置茲山之上，一投漢水之淵，是知陵谷有變，而不知石有時而磨滅也。 | B · calibration | 31 / 35 | 5.926 / 6.140 | [A](https://www.shidianguji.com/zh/book/CZBZZ051/chapter/1kxs7vmwg6230) · [B](https://zh.wikisource.org/wiki/峴山亭記) |
| Ding-revision | 雖罄一心，難諧眾口。 | 雖曲盡於巧心，終難諧於眾口。 | Unranked | 8 / 12 | 5.944 / 5.993 | [A](https://zh.wikisource.org/w/index.php?oldid=682652) · [B](https://zh.wikisource.org/w/index.php?oldid=682652) |
| Proclamation-alternative | 近則，諸夏仰德以承流；逺則，四夷傾心而待命。 | 近則，諸夏仰德以承流；逺則，四夷聞風而待命。 | Unranked | 18 / 18 | 5.258 / 5.258 | [A](https://zh.wikisource.org/w/index.php?oldid=2098020) · [B](https://zh.wikisource.org/w/index.php?oldid=2098020) |
| Proclamation-collected | 近則，諸夏仰德以承流；逺則，四夷傾心而待命。 | 近則，諸夏仰徳以承流；逺則，四夷傾風以待命。 | Unranked | 18 / 18 | 5.258 / 5.269 | [A](https://zh.wikisource.org/w/index.php?oldid=2098020) · [B](https://zh.wikisource.org/w/index.php?oldid=677490) |

Each version’s count-only score equals 5.689598249 + 0.000100480 × its Han count, clipped to the 1–7 range. These coefficients use 337 previous editorial scores. Always giving 6 ties every pair. The current model exactly replayed all 291 archived 《哀江南賦》 predictions before scoring the new packet. Across the three literary comparisons, flipping the reported winner independently in every family gives eight possibilities. All eight produce at least as much ordering credit for the current scorer as the observed 0.333. The tiny sample and mixed grounds limit any generalization. [Checkpoint implementation](../src/yu_review_baseline.py) · [Prior exposure audit](../research/critic-variant-exposure.md)

## Coverage and pronunciation

Wang’s two juan contain 58 entries. Xie’s one juan survives in recensions that differ in content. Sun’s 33 juan received OCR screening across 686 scanned pages. A targeted source check recovered the Shen Yue reading that the automated search missed. The individual source reports identify what was read, what was checked against a second witness, and which cases remain **UNVERIFIED**. Two of Wang Tao’s explicit recommendations about sound survive without a rejected wording. The 焜煌 opening differs in word order across witnesses. The Song examination anecdote uses 圜 in Chen’s edition and 圓 in Sun’s. Both differences are recorded at the witness level. [Wang Zhi evidence](../research/critics-wang.md) · [Xie Ji evidence](../research/critics-xie.md) · [Sun Mei evidence](../research/critics-sun.md)

For read-aloud ease (顺口), Sun preserves the report that Emperor Xiaozong found Yang Wanli’s ceremonial address difficult to deliver and preferred You Mao’s for that occasion. The account names the writers and the delivery difficulty but does not quote both scripts. It supplies a historical observation about public reading under particular conditions. It gives no line-level production score and enters no 音律美 comparison. Participant validation remains the final stage. [Zhang Duanyi’s 《貴耳集》](https://zh.wikisource.org/w/index.php?oldid=793294)

## What the recordings add

All 24 wordings were rendered in three controlled Mandarin voices. All 30 repeat renders matched the corresponding WAV byte for byte. Across the four comparisons that added characters, all 12 whole clips became longer. Only two of the eight expanded clause positions had matched endpoints in both wordings and every voice. Both belonged to the known 《峴山亭記》 pair. Its two clauses lengthened by a median of 360 ms and 200 ms respectively across voices. The recordings establish the change in timing. The historical report supplies the direction of the aesthetic preference. [Acoustic measurements and coverage by voice](critic-variant-audio.md)

Su Shi’s two versions illustrate why a complete-clip duration can hide a local difference. Both have 16 characters. 意 and 自 are both fourth-tone syllables in the Mandarin prompt. Changing **不意自全** to **不自意全** left the written score at 6.044. The altered clause took 30, 30 and 20 ms longer in the three voices, while its final syllable shortened by 30, 20 and 20 ms respectively. The complete clips differed by only 25, 0 and 25 ms. The sources give no preference between the two orders. Across all comparisons, no changed clause had an assigned positive pause after it in both wordings in all three voices. [Su Shi’s witnesses and the critic’s actual comment](../research/critics-xie.md) · [Phrase measurements](critic-variant-audio.md)

A sung-lyric (詞) example in Sun’s collection verifies that the search could retrieve a critic who actually discussed two different wordings and their sound. Zhou Mi defended **寄與** against **寄取** in Ye Mengde’s 《賀新郎》. He explained the different pronunciation of the second 與 in 容與 and also objected to the emendation on grounds of meaning. This is a separate Song lyric case. The prose results above use their own genre and comparison criteria. [Zhou Mi’s account](https://zh.wikisource.org/w/index.php?oldid=787891) · [Source collation](../research/critics-sun.md)

**Decision.** Retain the current written scorer. The subsequent Stage 7 check implemented a source-cited reading for a particular character and tested its effect under the frozen scoring weights. Establishing its value for predicting aesthetic preference requires further cases where a critic actually ranks the readings. [Documented-reading results](stage-7.md#scoring-a-documented-historical-reading)

## Gilbreth archive

The run is `$SHUNKOU_ROOT/results/critical-preferences-5JRVYyHR`. It holds the source witnesses, seals, diagnostic readings, text scores, recordings and acoustic measurements. The SHA-256 of the frozen main comparison packet is `32cd6594934478976e6a87c827e2f95e9d26bcbdd5e5c2aaeea9936c1ec07ce4`. Text scoring and the reading probe ran in Slurm job `12540529`. [Three-voice acoustic results](critic-variant-audio.md) · [Reproduction instructions](../hpc/README.md#historical-critics-and-alternative-wordings)
