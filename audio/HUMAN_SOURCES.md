# Human recording sources for Stage 4

## Pilot coverage

As of 21 November 2026, source discovery has verified **0 of 15** pilot passages with both a human performance and a recording reuse grant. The search covered the work titles in simplified and traditional forms, selected text anchors, LibriVox, Wikimedia Commons, and Mandarin and Cantonese recitation sources. The [pilot manifest](../data/pilot/passages.json) identifies the pinned targets. The rights of a historical work and the rights of a new performance are independent.

| Pilot IDs | Work | Human audio leads and intake status |
| --- | --- | --- |
| SD01, SD03 | 《哀江南賦序》 | A published uploader description contains the relevant text. Recording rights, reader, variety, and performed wording remain unverified. A separate uploader describes a historical pronunciation reconstruction, which is a distinct reading condition. [Reading lead](https://www.youtube.com/watch?v=bKoYB3upVdc) · [Reconstructed reading lead](https://www.youtube.com/watch?v=UsdVFLCot68) |
| SD02, SD06 | 《洛陽伽藍記》 | An ebook advertises read-aloud functionality. The medium, human reader, reuse rights, and coverage of the target spans are unverified. [Catalog entry](https://www.igetget.com/eBook/%E6%B4%9B%E9%98%B3%E4%BC%BD%E8%93%9D%E8%AE%B0%EF%BC%88%E4%B8%AD%E5%8D%8E%E7%BB%8F%E5%85%B8%E5%90%8D%E8%91%97%E5%85%A8%E6%9C%AC%E5%85%A8%E6%B3%A8%E5%85%A8%E8%AF%91%E4%B8%9B%E4%B9%A6%EF%BC%89?param=0RmFGKFwf7) |
| SD04 | 《顏氏家訓》 | A recorded series covers part of 《教子》. A recording of the target text and a reuse grant remain unverified. [Uploader's series entry](https://www.youtube.com/watch?v=42mEdN2spQU) |
| SD05 | 《玉臺新詠序》 | Searches turned up text and commentary. No exact-span human recording was verified. |
| ET01, ET05 | 《滕王閣序》 | Hong Kong Education Bureau item 127 lists `127_c.mp3` as Mandarin (普通話) and `127_a.mp3` as script recitation (台詞誦). The directory does not name speakers or pin the performed edition. The site notice permits local downloads of government copyright content for personal or non-commercial internal use under conditions, and restricts other uses. A grant covering project storage and derived audio remains unverified. Separately, 好書留聲 credits 潘碧雲 for a Cantonese (粵語) reading and identifies the producer. Its recording grant and performed wording remain unverified. [Education Bureau listing](https://www.edb.gov.hk/tc/curriculum-development/kla/chi-edu/resources/secondary-edu/lang/reciting-mp3.html) · [Copyright notice](https://www.edb.gov.hk/en/important-notices/index.html) · [Producer's Cantonese audiobook](https://www.youtube.com/watch?v=C0ZrPILqQs0) |
| ET02, ET04 | 《大唐西域記》 | Available leads include adaptation and commentary. No exact-span human recording was verified. [Publisher's adaptation](https://tphcc.ebook.hyread.com.tw/bookDetail.jsp?id=448900) |
| ET03 | 《為徐敬業討武曌檄》 | 畢仙蓉 published a reading and notes variation in the text. Target spoken wording and a recording grant remain unverified. Taiwan's national language contest published a written Mandarin reading prompt. [Reader's upload](https://www.youtube.com/watch?v=G_IGxE582fU) · [Contest prompts](https://language113.eduweb.tw/downloadfile.php?aid=9&code=00f2515f9c8058a2714a80880ec24395&download=195) |
| ET06 | 《史通》 | Located explanatory audio. No reading of the target span was verified. [Producer catalog](https://www.vistopia.com.cn/en/article/679766) |
| NS01–NS03 | 《峴山亭記》 | No exact-span human recording was verified. NS01 is an edition-controlled alternative with specific shorter wording and needs its own performance. |

## Rights-verified reference

LibriVox's 2009 volunteer audiobook has a recording of 王羲之's 《蘭亭集序》 by Semantic Nuance, section 5, 3:09 in the catalog. The catalog declares its recordings public domain in the United States and labels this track Chinese (`zh`). The spoken variety remains pending an audio check. Internet Archive lists the VBR file `chinese_lantingjixu_wang_sn.mp3` and marks the item public domain. Its companion track, 《曹劌論戰》, uses the same reader and provides a potential historical prose reference outside the matched pilot. [LibriVox catalog](https://librivox.org/multilingual-short-story-collection-001/) · [Reader credit](https://librivox.org/reader/3887) · [Archive audio and rights](https://archive.org/details/multilingual_short_stories_0906_librivox) · [LibriVox public-domain policy](https://librivox.org/pages/public-domain/)

The [reference registry](human_reference_sources.json) describes the full 《蘭亭集序》 track and its work-level relation to Stage 3 reference text `pian-ti-wen-chao-lan-ting`. LibriVox links a Wikisource e-text without a revision ID. The exact historical text in the recording, its reading boundaries, opening or closing announcements, and any omissions or variants remain pending audio review. Compare a transcription of the heard speech against the Stage 3 witness and assign segment timestamps before treating this recording as an alignment or feature reference. Keep it out of matched-pilot comparisons. [Stage 3 reference sources](../data/collections/anthology_sources.json)

On Gilbreth, run the reference download from the unpacked project scripts.

```bash
root="${RCAC_SCRATCH:-$(findscratch)}/shunkou"
python3 audio/acquire_human.py --root "$root"
```

The script saves the recording under `audio/raw/human/` in the project and writes source metadata, file size, and SHA-256 to `audio/manifests/human-reference.jsonl`.

## Optional author recordings

If the author opts to supply human pilot audio, start with both sides of one matched pair and preserve passage IDs and reading condition. Use the same speaker and equipment for both sides. Record the variety, style, take number, edition, and whether the take was read, recited (朗诵), or chanted (吟诵). Record a reading as performed, including audible repetitions or slips. Preserve the original audio and document permission for storage and analysis on Gilbreth. Clear any separate release of recordings or derived clips with the rights holder. Place recording bytes and intake metadata under the Gilbreth project directory.
