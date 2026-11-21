# Stage 3 reference text collections

This layer provides reference collections for later validation. The [matched prose pilot](../pilot/DATA_CARD.md) is the main Stage 3 design. The importers use Python 3.8 or later and the standard library. For the full verse import, run the following command from a CPU-capable compute allocation with access to the project storage. Keep the resulting corpus and raw cache in the Gilbreth project. [Gilbreth run guidance](../../hpc/README.md#stage-3-through-the-gateway)

```bash
root=/path/to/shunkou/project/storage
python3 data/collections/build.py --root "$root" --all
```

Use `--collection ID` one or more times for a smaller build. Use `--normalize-only` to rebuild from stored source files and `--archive PATH` to extract an already downloaded copy of the pinned archive. The script downloads the archive as a stream and retains the selected JSON and upstream `LICENSE` under `$root/data/raw/collections/REVISION/`. Each `$root/data/collections/ID.jsonl` has a companion `ID.manifest.json` with source checksums, record count, and output checksum. Raw and generated files belong in scratch.

## Acquisition sources and rights

The shared electronic source is the Chinese Poetry project (JackeyGao and contributors), snapshot `b8594f81a89752241442f2ce267d6f66f96704ee`, 17 June 2026. The classical texts are public domain. The project distributes its repository under MIT, and the build retains that notice. Upstream can identify its own snapshot precisely, but documents uneven or incomplete provenance to print editions. For later release, retain attribution and review inherited modern punctuation and editorial variants where the original digitization is unidentified. The normalized outputs contain classical body text and simple identifying metadata. They omit modern commentary, translations, author biographies, upstream notes and broad descriptive tags. [Chinese Poetry revision](https://github.com/chinese-poetry/chinese-poetry/commit/b8594f81a89752241442f2ce267d6f66f96704ee) · [Project notes](https://github.com/chinese-poetry/chinese-poetry/blob/b8594f81a89752241442f2ce267d6f66f96704ee/README.md) · [MIT notice](https://github.com/chinese-poetry/chinese-poetry/blob/b8594f81a89752241442f2ce267d6f66f96704ee/LICENSE)

| ID | Source and coverage | Limits |
| --- | --- | --- |
| `quan-tang-shi` | 《全唐诗》, 彭定求 and others, Qing compilation. Chinese Poetry `全唐诗/poet.tang.0.json` through `poet.tang.57000.json`. [Dataset notes](https://github.com/chinese-poetry/chinese-poetry/tree/b8594f81a89752241442f2ce267d6f66f96704ee/全唐诗) · [Public-domain edition index](https://zh.wikisource.org/wiki/全唐詩) | The raw corpus includes supplements and errors. The file offset is an electronic locator. Coverage by print volume remains unverified. |
| `tang-shi-300` | 《唐诗三百首》, 蘅塘退士 (孫洙), Qing selection. `全唐诗/唐诗三百首.json`. [Dataset](https://github.com/chinese-poetry/chinese-poetry/blob/b8594f81a89752241442f2ce267d6f66f96704ee/全唐诗/唐诗三百首.json) · [Public-domain anthology and original preface](https://zh.wikisource.org/wiki/唐詩三百首) | The selection is canonical in scope. Match and verify against a designated edition before published replication. |
| `quan-song-ci` | 《全宋词》 as distributed by Chinese Poetry. `宋词/ci.song.0.json` through `ci.song.21000.json`. [Dataset notes](https://github.com/chinese-poetry/chinese-poetry/tree/b8594f81a89752241442f2ce267d6f66f96704ee/宋词) | The historical lyrics are public domain. This is a research snapshot of electronic classical body text with no claim of matching 唐圭璋’s modern critical edition. Preserve the edition uncertainty and review upstream curation before redistribution. The separate `ci.song.2019y.json` and database are outside the numbered corpus. |
| `song-ci-300` | 《宋词三百首》, 朱孝臧 (朱祖謀), 1924 selection. `宋词/宋词三百首.json`. [Dataset](https://github.com/chinese-poetry/chinese-poetry/blob/b8594f81a89752241442f2ce267d6f66f96704ee/宋词/宋词三百首.json) · [Public-domain anthology](https://zh.wikisource.org/zh-hans/宋詞三百首) | Compare membership and variants to a specified witness before treating it as an edition. |
| `yuan-qu` | Chinese Poetry `元曲/yuanqu.json`, classical 曲 bodies. [Dataset](https://github.com/chinese-poetry/chinese-poetry/blob/b8594f81a89752241442f2ce267d6f66f96704ee/元曲/yuanqu.json) · [Upstream loader schema](https://github.com/chinese-poetry/chinese-poetry/blob/b8594f81a89752241442f2ce267d6f66f96704ee/loader/datas.json) | Anthology lineage and 散曲 versus 雜劇 coverage have yet to be verified. Leave subgenre unset. |

## Normalization and evidence limits

Each output row keeps corpus ID, title or tune label when available, author, broad genre, upstream period label, source path and one-based record ordinal, upstream ID when available, source segmentation, and a UTF-8 SHA-256 text fingerprint. Source segmentation comes from the upstream `paragraphs` array. Normalization is NFC, edge whitespace removal, and omission of empty strings. Preserve punctuation, archaic forms, script, and reading-ambiguous characters. Null metadata means unknown. No character readings or performance annotations are inferred by this importer.

The explicit upstream verse-form tags `五言古诗`, `七言古诗`, `五言律诗`, and `七言律诗` and their traditional equivalents supply provisional 古體 and 近體 subsets. Equivocal forms such as 絕句 and competing tags remain unclassified. The labels require source checks before they can serve as gold labels. Form labels are independent of project metric scores. Split training and evaluation by work after checking repeated text across the full collections and the anthology subsets, using exact-text fingerprints as a first pass and checking for differing punctuation, script, and variants.

## Pinned anthology seed

Run this small acquisition from the unpacked source tree with `root` pointing to the Gilbreth project.

```bash
python3 data/collections/build_anthologies.py --root "$root"
```

This build starts from [fourteen work spans](anthology_sources.json) in eleven pinned Chinese Wikisource pages. It stores API responses under `$root/data/raw/anthologies` and writes `$root/data/collections/anthology-seed.jsonl`. The underlying texts are public domain in the United States. Retain attribution to Chinese Wikisource contributors and CC BY-SA 4.0 for the transcription and inherited editorial contributions, as recorded per row. The raw response checksum identifies the rendered witness, including any templates in the response. Use `--normalize-only` with those bytes for a reproducible rebuild. [Wikimedia terms](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

Each span is delimited by two checked substrings in the pinned witness. The importer removes explicit `〈…〉` commentary and `一作「…」` variants, keeping them in raw. It preserves other transmitted characters and surviving punctuation. Some texts are unpunctuated. It records webpage blocks without assigning them the status of 句讀 or metrical lines. This intentionally small seed omits most volumes, author attributions and edition variants that require independent collation.

| Corpus group | Seed coverage | Source |
| --- | --- | --- |
| 《昭明文選》 and 《六朝文絜》 | 江淹's 《恨賦》 and 《別賦》 link the two anthologies. The work-level transcriptions are shared witnesses here. | [蕭統's anthology, 李善 commentary edition index](https://zh.wikisource.org/w/index.php?oldid=11123497) · [許槤's anthology index](https://zh.wikisource.org/w/index.php?oldid=2573077) · [《恨賦》 witness](https://zh.wikisource.org/w/index.php?oldid=2645152) · [《別賦》 witness](https://zh.wikisource.org/w/index.php?oldid=2366252) |
| 《駢體文鈔》 | Two Eastern Jin prefaces, 《蘭亭集序》 and 《抱朴子序》. The pinned page presents the bodies in simplified characters. | [李兆洛, volume 21](https://zh.wikisource.org/w/index.php?oldid=2609572) |
| 《古文觀止》 | 王勃's 《滕王閣序》 (preface span) and 杜牧's 《阿房宮賦》 (文賦 contrast). Use the sources above for 江淹's 賦 and the standalone witness below for 庾信's preface. | [吳楚材 and 吳調侯, volume 7](https://zh.wikisource.org/w/index.php?oldid=5978452) |
| 《哀江南賦序》 | 庾信's preface span from a transmission that also includes the 賦 body. | [《哀江南賦》](https://zh.wikisource.org/w/index.php?oldid=3656893) |
| 《文苑英華》 | 《蓋地圖賦》 and 《立春出土牛賦》 have explicit prescribed rhyme sequences in their headings. Store those sequences as witness metadata for a future 律賦 contrast. | [李昉 and others, volume 25](https://zh.wikisource.org/w/index.php?oldid=12758598) |
| 元曲 | 馬致遠's 《天淨沙·秋思》 as 散曲 and one 滾繡球 lyric from 關漢卿's 《竇娥冤》第三折 as 雜劇. The latter page lacks a proven print-edition lineage. | [《天淨沙·秋思》](https://zh.wikisource.org/w/index.php?oldid=1491130) · [《竇娥冤》](https://zh.wikisource.org/w/index.php?oldid=2571901) |
| Early Republic lyric controls | Two stanzas of 李叔同's 《送別》 (1915) and the poetic texts of 劉半農's 《教我如何不想她》 (1920) and 徐志摩's 《海韻》 (1925), later set by 趙元任. The latter two rows preserve the poem witnesses. A sung lyric may vary in text and repetitions. | [《送別》](https://zh.wikisource.org/w/index.php?oldid=12977730) · [《教我如何不想她》](https://zh.wikisource.org/w/index.php?oldid=2490079) · [《海韻》](https://zh.wikisource.org/w/index.php?oldid=2632828) · [趙元任's letter on the settings and the 1928 publication](https://xsg.tsinghua.edu.cn/info/1004/3431.htm) |

## Coverage still open

- Full anthology expansion requires checked work boundaries, page revisions, and separation of original text from commentary. 《文苑英華》 includes incomplete transcription and a separate 四庫全書 witness. [Transmission overview](https://zh.wikisource.org/wiki/文苑英華) · [四庫全書 witness](https://zh.wikisource.org/wiki/文苑英華_(四庫全書本))
- Wider marked 雜劇 coverage requires identifying sung lyrics among dialogue and stage directions. The available 竇娥冤 witness shows all three kinds of text. [第三折](https://zh.wikisource.org/wiki/竇娥冤#第三折)
- The lyric controls cover public-domain Early Republic texts. Contemporary lyrics remain open. A future source needs an explicit reuse grant for the lyric texts and their provenance.
