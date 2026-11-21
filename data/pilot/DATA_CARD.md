# Pilot corpus of parallel and comparison prose

## Contents and purpose

The matched pilot contains 12 excerpts across six pairs. Three pairs compare sixth-century texts and three compare Early Tang texts, with the latest comparison work completed in the early eighth century. Each pair has one specimen of parallel prose (駢文, 骈文) and one comparison passage from historical, travel, or argumentative prose (散文). The Latin IDs are stable. The matched texts run from 20 to 28 Han characters, and texts within a pair differ by at most four. Three Northern Song probes sit outside this matched portion.

| Pair | Shared subject | Parallel prose | Comparison prose | Han counts |
| --- | --- | --- | --- | ---: |
| M01 | Loss and upheaval | SD01 庾信, 《哀江南賦序》 | SD02 楊衒之, 《洛陽伽藍記》 | 24 / 24 |
| M02 | Political danger | SD03 庾信, 《哀江南賦序》 | SD04 顏之推, 《顏氏家訓》 | 20 / 23 |
| M03 | Ornate buildings and objects | SD05 徐陵, 《玉臺新詠序》 | SD06 楊衒之, 《洛陽伽藍記》 | 26 / 22 |
| M04 | Landscape and travel | ET01 王勃, 《滕王閣序》 | ET02 玄奘、辯機, 《大唐西域記》 | 26 / 24 |
| M05 | Court accusations | ET03 駱賓王, 《為徐敬業討武曌檄》 | ET04 玄奘、辯機, 《大唐西域記》 | 28 / 26 |
| M06 | Reflection and judgment | ET05 王勃, 《滕王閣序》 | ET06 劉知幾, 《史通》 | 20 / 24 |

The passages were chosen to put regular, transparent phrasing alongside regular yet allusive phrasing, and to include uneven as well as fairly rhythmic comparison prose. SD01 serves as a repeat anchor for the author because it contains part of the earlier rating stimulus. SD03 and SD05 add allusions or rare vocabulary within regular pairs. SD04 and ET04 add prose with less familiar vocabulary and less predictable phrasing. ET06 has fairly even clause lengths within argumentative prose. These are sampling choices aimed at wider use of the two rating scales. Reader familiarity, pronunciation effort, and listener preferences remain to be measured.

Matching is by historical period, approximate length, and broad subject. The geography, composition dates, punctuation, syntax, and vocabulary differ within pairs. Dynastic labels cover the works' formation periods rather than the periods that they narrate. Genre tags follow the passage's function and form in its source. Local parallel phrases in the comparison prose are retained. Keep excerpts from repeated works together when splitting data. Mask source, critic, and genre labels in rating and listening tasks.

## Critical probes

- ET01 and ET05 use the received-text portion of the pinned 《滕王閣序》 transcription. 莫道才’s judgment concerns the whole work, so there is no excerpt-level preferred label. [Published essay](https://news.gxnu.edu.cn/2025/0802/c1330a319711/page.psp)
- NS01 and NS02 use a 1070 《峴山亭記》 passage and the two clause-ending variants that 王銍 attributes to 章惇. NS02 follows the pinned received text. NS01 inserts the reported shorter wording into the same context, using the received text’s 茲 form where the anecdote prints 兹. The manifest records both the edit and its scope. The pair changes clause length and final syllables together. [Received text](https://zh.wikisource.org/w/index.php?title=峴山亭記&oldid=870702) · [王銍, 《默記》卷下](https://www.shidianguji.com/zh/book/CZBZZ051/chapter/1kxs7vmwg6230)
- NS03 preserves the point after 皆足以垂于不朽 that 《古文評註》 marks 文氣一頓. This is a documented boundary cue. The corresponding lengthening or pause in a reading remains to be measured. [《古文評註》 annotations](https://zh.wikisource.org/w/index.php?title=峴山亭記&oldid=870702#註釋)

## Provenance and rights

Each source record in [the manifest](passages.json) names the historical work, author, period, digital edition, Wikisource revision, and attribution. The underlying works are public domain. Retain the Wikisource contributors' attribution and [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) license for the transcription and punctuation layer. The 《洛陽伽藍記》 and 《玉臺新詠序》 pages use the project-wide terms even where there is no separate public-domain badge on the transcription page. We store a derived excerpt and note the boundaries and any editorial change. Modern commentary is linked and coded as evidence in the manifest. [Wikimedia Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use) · [Wikisource reuse policy](https://en.wikisource.org/wiki/Wikisource:Reusing_Wikisource_content)

The matched excerpts preserve witness characters and punctuation and strip whitespace. Source spans begin and finish at witnessed clause or sentence boundaries, including the final semicolon of SD04. The parser excludes citation notes and ruby pronunciation glosses. Selected spans avoid inline variant commentary. Unicode NFC and the manifest's reviewed hash lock each output. Reader-facing character-script conversion would be a separate presentation version and should acquire a separate ID. `pair_id` links matched stimuli or critic variants. `parallel_clause_groups` records analyst-selected rhetorical pairings within a single excerpt using zero-based indices into the punctuation segmenter. These proposals reflect parallel wording and syntax and are independent of tone candidates and rating outcomes. Comparison passages can contain local parallelism and have no reviewed within-passage pairings in this release.

## Rebuilding on Gilbreth

Use Python 3.8 or later and the standard library. Run from a copy of the source tree on Gilbreth.

```bash
root="${RCAC_SCRATCH:-$(findscratch)}/shunkou"
python3 data/pilot/build.py --root "$root"
```

The build caches MediaWiki parse responses under `$root/data/pilot/raw/` and writes `$root/data/pilot/passages.jsonl`. Each passage carries a stable work ID and a source revision ID, plus its pair, subset, underlying rights, and Wikisource attribution.

For a host without Wikimedia egress, use `--snapshot /path/on/gilbreth/to/reviewed-spans.json`. The snapshot is a UTF-8 JSON object mapping each passage ID to its reviewed witness span, before the recorded edit for NS01. This input stays on Gilbreth with the data. Both paths validate excerpt boundaries, lengths, and SHA-256 before writing the passage corpus. If a check fails, review the pinned source and the reported ID. See the [MediaWiki parsing API](https://www.mediawiki.org/wiki/API:Parsing_wikitext) for the underlying retrieval operation.
