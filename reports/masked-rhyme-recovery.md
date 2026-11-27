# Recovering a hidden rhyme in Tang parallel prose

**Measured result.** On twelve held-out regulated rhapsodies (律賦) from 《全唐文》, checking the two sentence endings on either side recovered the hidden 《廣韻》 category better than requiring a recurring pattern. The nearby-ending rule won in every work. Its work-weighted score was **81.1%**, against **60.5%** for the stricter rule. Keep the existing historical rhyme measure. This test establishes how much the written surroundings reveal about a hidden ending. The written 1–7 musical beauty (音律美) score and first-read ease (顺口) require different evidence. [Prospective roadmap](../research/roadmap.md)

**Period qualification from the follow-up.** 徐寅 passed the Tang examinations and also wrote after the Tang fell. The composition date of F11, 《豐年為上瑞賦》, is uncertain. Omitting F11 leaves 208 eligible endings in eleven works. The nearby rule still leads in every work, with 81.2% overall credit against 61.5% for the stricter rule. The prospective figures below retain the original twelve-work roster. [徐寅’s biography in 《十國春秋》](https://www.shidianguji.com/zh/book/SK0960/chapter/1la06088x7jmx)

## What the methods saw

In 趙昂’s 《攻玉賦》 five sentences end **磨、波、他、何、多**. We hid 他 and offered **歌** and **麻**, two level-tone categories. The nearby-ending rule chose 歌, the attested category. The stricter rule abstained. The work’s heading names 他 among its prescribed rhymes. Both predictors received only the candidate categories and the surrounding endings. In 徐元弼’s 《靈囿賦》, both methods recovered **屋** for masked 牧 following 育 and 築, against the same-tone alternative 質. [趙昂’s text](https://zh.wikisource.org/w/index.php?oldid=8729771) · [徐元弼’s text](https://zh.wikisource.org/w/index.php?oldid=8729773)

## Results on untouched works

The task was to choose between the true historical rhyme group and a different group of the same historical tone. Each correct choice earned one point, an incorrect choice zero, and a tie or abstention half a point. Percentages give every work the same weight. The counts below pool endings and therefore use a different denominator.

| Method | 12 regulated 賦 · 228 endings | 10 Tang memorials (表) · 150 endings | 賦 after shuffling within sections |
|---|---:|---:|---:|
| Exact matches in the two rows on each side | **81.1%** | 54.3% | 59.1% |
| Require a recurring group nearby | 60.5% | 50.0% | 50.9% |
| More frequent of the two groups elsewhere in the work | 76.8% | 54.6% | 76.8% |
| Historical tone alone | 50.0% | 50.0% | 50.0% |

- On the 228 賦 trials, the nearby rule made **147 correct choices, 5 errors, 75 ties and 1 abstention**. The stricter rule made **49 correct choices, 4 errors and 175 abstentions**. Its decisive coverage averaged 23.8% per work. The work-weighted accuracy on the decisions it made was 80.3% across the eleven works with any decision. The pooled success rate on its 53 choices was 92.5%.
- The stricter rule scored **20.6 percentage points lower** than the nearby rule. The paired 95% interval from 10,000 whole-work bootstrap resamples was **−24.9 to −16.0 points**. Shuffling reduced the stricter rule’s score by 9.6 points, above the development-set tolerance of 4.5 points. It still scored below both prespecified comparators on intact works. The promotion criteria failed.
- In the memorials, the nearby rule chose correctly 15 times, erred 3 times and tied 132 times. The stricter rule abstained on all 150. After excluding the 24 prose trials with the same end character elsewhere within four rows, the nearby rule had zero wins, three errors and 123 ties, giving 49.3% work-weighted credit. In the 賦, removing the two such trials left the nearby rule at **80.9%**. Literal repetition explains much of the small prose result.
- On the **65** held-out endings that literally appear in the work’s assigned rhyme characters, the nearby rule scored **87.6%**, work frequency **86.7%**, and the stricter rule **58.9%**. All twelve 賦 contributed. These source-backed examples are a narrower test and can overrepresent echoes of the assigned wording.

The nearby rule’s intact advantage over work frequency was 4.4 points in the 賦. It beat frequency in six works, tied it in four and lost in two. Shuffling dropped the nearby rule from 81.1% to 59.1% while preserving the candidate pairs and each work’s vocabulary. Both the local arrangement and the work’s choice of rhyme groups carry information in this two-choice task.

## Corpus and validation

We screened 240 candidate records from 135 revision-pinned 《全唐文》 volume catalogues. Eight works supplied development data. Twenty-two other works from different authors supplied the test. Each selected rhapsody has an explicit prescribed-rhyme heading. The comparison works have no rhyme rubric or signalled verse insert, and each contains at least three sentences with adjacent phrases of comparable length. All ten held-out comparisons are memorials. The match is by dynasty and anthology. The sample does not pair individual authors by decade. [Source rules](../src/masked_rhyme_sources.py)

The search reserved 217 author names, 1,469 titles and 6,450 text spans from project records and planning exclusions. The source manifest indexes 64 earlier inputs. A separate review of 184 local project files found no matching held-out title or revision and no matching held-out author under the checked names and aliases. The thirty admitted works have thirty different credited authors. 浩虛舟 had appeared in an earlier critic study on a different work and entered only the development set here. Freshness concerns this project’s recorded evaluations. [Earlier critical study](critic-preferences.md)

Editorial sentence stops (。！？) determined the positions before dictionary lookup. All 301 held-out 賦 endings and 192 memorial endings remained in the texts. Of these, 228 and 150 respectively had one resolved 《廣韻》 tone and rhyme group and could enter the comparison. Ambiguous and missing endings stayed in their original positions as context. The assigned-rhyme heading was withheld. Alternatives came from the same tone, weighted by development frequencies. A single reproducible alternative was frozen per ending. Work frequency excludes the hidden occurrence. These conditions test two-choice recovery among dictionary-resolved endings. Identifying the true historical rhyme position in every sentence, predicting a group freely, and adjudicating disputed pronunciations are further tasks. [Historical dictionary and lookup policy](../data/phonology/HISTORICAL.md) · [Analysis](../src/masked_rhyme_recovery.py)

The stricter rule looks for two equal unambiguous groups at nearby consecutive or alternating positions. It needs one group to receive the most support and to match an offered category. On 56.6% of 賦 targets, averaged across works, it inferred a group, including groups outside the two choices. It ultimately chose an answer on 23.8%. Exact group identity was used throughout. Historically licensed combinations (同用) would require a separately sourced comparison.

We ran 200 within-section permutations and a separate 200 whole-work permutations that preserved the original section sizes. Each held-out 賦 has one editorial text block, so both controls randomize across the same positions with different seeds. The second produced 59.0% for nearby matches and 50.9% for the stricter rule. Punctuation is an editorial proxy. A prescribed rhyme can precede a final particle, as in 滕邁’s 「重輪交映者哉」. This design example was excluded from the sample. [Whole-work shuffle](../src/masked_rhyme_shuffle_check.py) · [滕邁’s text](https://zh.wikisource.org/w/index.php?oldid=2079753)

## Held-out editions

| Author and 賦 | Eligible / all endings | Nearby | Recurring pattern |
|---|---:|---:|---:|
| 趙昂 [《攻玉賦》](https://zh.wikisource.org/w/index.php?oldid=8729771) | 17 / 24 | 88.2% | 61.8% |
| 周渭 [《金精百煉賦》](https://zh.wikisource.org/w/index.php?oldid=1973062) | 14 / 23 | 78.6% | 57.1% |
| 徐元弼 [《靈囿賦》](https://zh.wikisource.org/w/index.php?oldid=8729773) | 29 / 32 | 89.7% | 72.4% |
| 沈封 [《指佞草賦》](https://zh.wikisource.org/w/index.php?oldid=1974931) | 18 / 23 | 80.6% | 61.1% |
| 薛勝 [《孔子彈文王操賦》](https://zh.wikisource.org/w/index.php?oldid=1973753) | 26 / 29 | 75.0% | 46.2% |
| 周鉞 [《積土成山賦》](https://zh.wikisource.org/w/index.php?oldid=1980629) | 17 / 28 | 76.5% | 70.6% |
| 徐寅 [《豐年為上瑞賦》](https://zh.wikisource.org/w/index.php?oldid=1980677) | 20 / 31 | 80.0% | 50.0% |
| 胡權 [《飲貪泉賦》](https://zh.wikisource.org/w/index.php?oldid=1979710) | 17 / 25 | 79.4% | 67.6% |
| 李方叔 [《南風之薰賦》](https://zh.wikisource.org/w/index.php?oldid=1980614) | 23 / 27 | 78.3% | 58.7% |
| 崔損 [《飲至賦》](https://zh.wikisource.org/w/index.php?oldid=8733705) | 13 / 14 | 96.2% | 69.2% |
| 李蟾 [《烹小鮮賦》](https://zh.wikisource.org/w/index.php?oldid=1973887) | 23 / 30 | 78.3% | 47.8% |
| 崔琪 [《擊柝賦》](https://zh.wikisource.org/w/index.php?oldid=1980457) | 11 / 15 | 72.7% | 63.6% |

The ten comparison memorials are available in the pinned editions. [元固《為鄭相請朝覲表》](https://zh.wikisource.org/w/index.php?oldid=1979206) · [周行先《為陝州盧中丞請朝覲第一表》](https://zh.wikisource.org/w/index.php?oldid=1975681) · [令狐綯《請詔男滈就試表》](https://zh.wikisource.org/w/index.php?oldid=1975897) · [崔元翰《為河東副元帥馬司徒謝實封表》](https://zh.wikisource.org/w/index.php?oldid=1979447) · [王仲周《代杜司徒謝妻封邑表》](https://zh.wikisource.org/w/index.php?oldid=1978703) · [唐元度《九經字樣序表》](https://zh.wikisource.org/w/index.php?oldid=1971911) · [柳宗元《禮部為百官上尊號第二表》](https://zh.wikisource.org/w/index.php?oldid=481337) · [狄仁傑《請拔安東表》](https://zh.wikisource.org/w/index.php?oldid=1970783) · [邵說《讓吏部侍郎表》](https://zh.wikisource.org/w/index.php?oldid=1981254) · [梁鎮《諫罷違典左道呂祠表》](https://zh.wikisource.org/w/index.php?oldid=1981429)

## Archive and next decision

Gilbreth Slurm jobs `12589507` and `12589593` produced the corpus and scores in `$SHUNKOU_ROOT/results/masked-rhyme-f8xpyOCv`. The pinned editions, row-level decisions, discarded candidates, seeds, shuffled results and source checksums are archived there. An independent NVIDIA A10 calculation reconstructed the twelve paired work differences from individual decisions and reproduced the primary interval to within 10⁻¹². The sealed rows have SHA-256 prefix `e7daa9d3a157` and the results summary `a5ab01aac0e5`. [Gilbreth reproduction](../hpc/README.md#masked-historical-rhyme-recovery)

**Next written-score question.** Compare training-only fits with and without the existing nearby rhyme feature against always giving 6 on independently held-out written ratings. The present experiment supplies evidence for recognizing historical rhyme. Listening judgments of 音律美 and the separate cold read-aloud test for 顺口 remain for the final participant stage.
