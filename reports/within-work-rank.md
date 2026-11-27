# Ranking exceptional sentences within the same work

**Finding.** The new model put the editorial 7 above a 5 or 6 from the same work **69.0%** of the time on the primary reading. The released model scored **43.6%**, and always giving 6 scored **50.0%** because every pair tied. The new model did better in six of the seven works that supplied a comparison. The paired 95% interval for its overall advantage over the released model extended from **−5.2 to +53.3 percentage points**. Keep the released scorer as the benchmark. These data support testing this ranking approach again, but do not meet the prospectively specified rule for advancing it.

## Results on fresh Tang works

Two blind AI editorial sessions each scored 128 sentences from sixteen different works and authors. The primary reader selected eight 7s and 33 distinct eligible lower-graded sentences in the same seven works. That produced 38 pairs. The second reader selected six 7s with 24 eligible lower-graded sentences across five works, producing 29 pairs. The percentages below give each informative work one vote. “Both genres” includes the regulated rhapsodies and their period-matched prose counterparts.

| Reader and contrast | Works | Pairs | Pair-trained | Released model | Always give 6 |
|---|---:|---:|---:|---:|---:|
| Primary, 7 above 5 or 6, both genres | 7 | 38 | **69.0%** | 43.6% | 50.0% |
| Primary, 7 above 5 | 7 | 25 | 67.9% | 55.4% | 50.0% |
| Primary, 7 above 6 | 7 | 13 | 69.0% | 23.8% | 50.0% |
| Primary, regulated 賦, 7 above 5 or 6 | 4 | 26 | 68.3% | 43.3% | 50.0% |
| Primary, discursive prose, 7 above 5 or 6 | 3 | 12 | 70.0% | 43.9% | 50.0% |
| Second, 7 above 5 or 6, both genres | 5 | 29 | **74.7%** | 48.0% | 50.0% |
| Second, 7 above 5 | 5 | 20 | 80.0% | 52.5% | 50.0% |
| Second, 7 above 6 | 5 | 9 | 63.3% | 40.0% | 50.0% |

On the primary reading, the new model won 26 of the 38 individual comparisons and the released model won 18. Giving every pair the same weight would give 68.4% and 47.4%. The prespecified percentages in the table average within works first. The two readers agreed on 100/128 exact grades, were within one point on all 128, and agreed on six 7s. Both readers chose the same five exceptional sentences in the 賦. The second reading supplied just one informative prose work, compared with three in the primary reading. It is a second judgment of the same sentences.

**Uncertainty and controls.** Across 10,000 paired resamples of whole works within genres, 9,997 primary draws contained an eligible comparison. The pair-trained advantage over the released model was **+25.5 percentage points** (95% interval **−5.2 to +53.3**). Its advantage over the constant was **+19.0 points** (**+2.4 to +35.0**). Resampling the eight intact, period-matched pairs gave intervals of −9.5 to +51.9 and +3.3 to +34.3 points respectively. Shuffling the grades within each work 999 times reduced the candidate’s average to 50.4% (one-sided permutation p = 0.056). The bootstrap measures variation across the sampled works. The shuffle asks what rankings would look like if grades were exchangeable within those works.

The second reading’s advantage over the released model was +26.7 points (95% interval −20.0 to +68.1) and over the constant +24.7 points (−1.1 to +40.0). Its shuffled mean was 50.0% (p = 0.045). The largest primary difference appeared on the 13 comparisons of 7 versus 6, +45.2 points over the released model. The second reading had nine such comparisons and a smaller +23.3-point difference. These subsets offer a direction for replication.

**Decision.** The primary reading met the minimum of two informative works in each genre. The lower confidence bound against the released model crossed zero, so the candidate missed the criterion for advancing it. Keep its coefficients frozen for replication on more independent works. The model produces relative rankings within a work. The experiment supplies no absolute 1–7 calibration or evidence about a listener’s preferences.

## What the comparison measures

Each test pair contains one sentence a blind AI editor graded 7 and another sentence from the same work that the same editor graded 5 or 6 for written musical beauty (音律美). If the model puts the 7 higher, it gets one point. If it ties them, it gets half. For example, a work with one 7, two 6s and one 5 offers three comparisons. A work with no 7 offers none. Each informative work gets the same vote, regardless of how many comparisons it supplies. Always giving 6 therefore scores 50% wherever the comparison is defined.

The released model supplies its unrounded written score. The new model learns from the feature difference between two sentences in one training work. It gives equal total weight to each of the seven training works and uses the released model’s features and training scales. Both models see the original paragraphs. The new model produces an ordering and has no numerical cutoff for recommending a line for memorization. This comparison changes both the training objective and how examples receive weight, so any difference in performance concerns the complete training procedure. [Frozen design and decision rule](../research/within-work-rank.md) · [Model and evaluation](../src/within_work_rank.py)

**Reading conditions.** Separate sessions of the same AI model read anonymous targets, each with up to two neighboring sentences on either side in the same paragraph. Every grade came with a quotation and a reason. The readers worked independently with the same rubric and no quota for 7s. These are written editorial preferences. First-read ease (顺口) and listening 音律美 remain separate outcomes for final participant testing.

## Training and source audit

Of 337 archived training units, 310 received 5, 6 or 7, including 50 grade-7 units. They formed 4,232 same-work pairs. 《拉法叶赋》 contributed 3,680 pairs and the six other works contributed 552. Each work received one seventh of the fitting weight. The model correctly ordered 78.6% of the comparisons it trained on, averaging works equally. Only the fresh comparisons enter the decision. The fitted model uses 16 features and a fixed penalty. On Gilbreth the CPU and GPU rankings agreed to within 8.9 × 10⁻¹⁶ on the same inputs.

The test covered eight Tang regulated rhapsodies (律賦), representing parallel prose (駢文), and eight works of discursive prose. Each pair belongs to the same broad period of author activity in the 《全唐文》 notices. These author dates do not establish identical composition dates. Six pairs come from the middle stratum, one from the earlier stratum and one from the later stratum. The selection excluded prior material against an inventory of 554 author names, 2,073 titles, 1,380 edition revisions and 5,366 protected long spans. The code also screened for exact prior sentences of six or more characters. The sampler logged 79 candidates across 150 anthology volume catalogues. It drew eight intact targets per work, including ornate and plainer writing in the prose comparison. The models saw all 452 sentences in their original paragraph order. Freshness refers to the project’s training and study archives. Exposure in the AI readers’ pretraining is unknown. [Source screen](../src/within_work_sources.py) · [Middle-period author notices for 樊陽源, 范傳正 and 陳諷](https://zh.wikisource.org/w/index.php?oldid=8735430)

| Pair | Regulated rhapsody and author period | Discursive prose and author period |
|---|---|---|
| 1 | 袁不約 [《胡越同舟賦》](https://zh.wikisource.org/w/index.php?oldid=1980884) · 長慶 | 盧簡求 [《禪門大師碑陰記》](https://zh.wikisource.org/w/index.php?oldid=1975263) · 長慶 |
| 2 | 樊陽源 [《江漢朝宗賦》](https://zh.wikisource.org/w/index.php?oldid=1980570) · 貞元 | 董晉 [《冠冕制論》](https://zh.wikisource.org/w/index.php?oldid=1976434) · 德宗朝 |
| 3 | 林琨 [《駕幸溫泉宮賦》](https://zh.wikisource.org/w/index.php?oldid=1980529) · 代宗朝 | 韋宗卿 [《隱山六峒記》](https://zh.wikisource.org/w/index.php?oldid=1981595) · 元和 |
| 4 | 顏舒 [《刻漏賦》](https://zh.wikisource.org/w/index.php?oldid=1975783) · 天寶 | 韋述 [《宗廟加籩豆議》](https://zh.wikisource.org/w/index.php?oldid=1981168) · 天寶 |
| 5 | 范傳正 [《進善旌賦》](https://zh.wikisource.org/w/index.php?oldid=8735760) · 憲宗朝 | 劉肅 [《大唐新語後總論》](https://zh.wikisource.org/w/index.php?oldid=1974544) · 元和 |
| 6 | 陳諷 [《新築峨和城賦》](https://zh.wikisource.org/w/index.php?oldid=1980188) · 貞元 | 劉宇 [《河東鹽池靈慶公神祠碑陰記》](https://zh.wikisource.org/w/index.php?oldid=1980312) · 貞元 |
| 7 | 韋肇 [《駕幸春明樓試武藝絕倫賦》](https://zh.wikisource.org/w/index.php?oldid=1974804) · 大曆 | 嚴涚 [《武成王祀典議》](https://zh.wikisource.org/w/index.php?oldid=1971409) · 貞元 |
| 8 | 侯喜 [《鳥擇木賦》](https://zh.wikisource.org/w/index.php?oldid=1975290) · 貞元 | 李顧行 [《上元縣開善寺修誌公和尚堂石柱記》](https://zh.wikisource.org/w/index.php?oldid=8728484) · 元和 |

## Two 7-versus-6 decisions both readers agreed on

In 盧簡求’s 《禪門大師碑陰記》, both readers gave **7** to 「啟有為而悟無為，來無從而去無至。」 and **6** to 「而檀施景隨，嚐功百態，楚材山委，郢匠星馳。」 The first sentence turns 有為 into 無為, then balances 來 against 去 under the repeated 無. The pair-trained model preferred it. The released model placed it lower, 5.96 against 6.14. [Pinned text](https://zh.wikisource.org/w/index.php?oldid=1975263)

In 侯喜’s 《鳥擇木賦》, both readers gave **7** to 「水隔山而猶遠，煙拂樹而漸分。」 and **6** to 「或淩雲之幹而不可集，或在庭之柯而必可止。」 The primary reader heard a lingering movement from distance to clearing mist in the first sentence. The pair-trained model preferred the second sentence with its repeated 或…而… frame. The released model ordered this pair correctly, 6.17 against 6.02. These are observed orderings. A reason an editor gives for a grade does not identify the model feature that caused its choice. [Pinned text](https://zh.wikisource.org/w/index.php?oldid=1975290)

## Gilbreth archive

The archive is `$SHUNKOU_ROOT/results/within-work-rank-hifqn0Ob`. Job `12591378` selected the works, `12591403` froze the model and predictions, `12591510` evaluated both editorial readings and `12591511` independently verified the results. The forecast SHA-256 is `8db4478395fea5bda172c9db54d3dc2dfa3b2d6b2f389f9b05e64055db2be3c7`. The verifier checked the original anonymous submissions and pinned editions, recalculated every pair ordering and counted the training pairs from the original reference. Source witnesses, reader evidence, detailed predictions and compute outputs are on Gilbreth. [Reproduction instructions](../hpc/README.md#ranking-exceptional-lines-within-a-work)
