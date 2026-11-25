"""Freeze an author-held-out sample of matched endings in formal Tang prose."""

from collections import Counter, defaultdict
from itertools import islice, zip_longest
from pathlib import Path
import re
import sys
from zipfile import ZipFile

from data.phonology.modern import ARCHIVE, MEMBERS, reading_rows

from .semantic_turn_pairs import normalized, prepare, select_pair
from .semantic_turn_quotation_audit import quoted_sentences
from .semantic_turn_sources import catalogue, exposure, fetch_works, parse_candidate, title_genre
from .yu_review_sources import digest, norm, save
from .yu_review_transfer import read


def closing_pair(text):
    pair = select_pair(text)
    if (pair and pair["route"] == "semicolon_closings" and pair["i"] >= 1
            and pair["j"] - pair["i"] >= 2):
        return pair
    return None


def variant_families(path):
    # Only for conservative exclusion. The edition and every scored character stay literal.
    parents = {}

    def representative(c):
        while c in parents:
            c = parents[c]
        return c

    chars = set()
    with ZipFile(path) as z:
        for char, _, value in reading_rows(z, MEMBERS[2], {"kTraditionalVariant", "kSimplifiedVariant"}):
            for token in value.split():
                other = chr(int(token[2:], 16))
                a, b = sorted((representative(char), representative(other)))
                if a != b:
                    parents[b] = a
                chars.update((char, other))
    return {ord(c): representative(c) for c in chars}


def reserve_previous(root, excluded_runs):
    authors, titles, protected, archive = exposure(root, excluded_runs)
    project = Path(__file__).resolve().parents[1]
    examples = project / "theory/foundations.md"
    demos = re.findall(r"^- [A-F]\. (\S+?), 《([^》]+)》", examples.read_text(), re.M)
    if len(demos) != 6:
        raise ValueError("Missing Stage 2 six-work demonstration")
    for a, t in demos:
        authors.add(norm(a))
        titles.add(norm(t))
    archive["code/theory/foundations.md"] = digest(examples.read_bytes())
    runs = sorted(root.glob("results/equal-phrase-turn-*/inputs/source-seal.json"))
    if not runs:
        raise ValueError("Missing preceding equal-phrase benchmark")
    for seal in runs:
        folder = seal.parent
        files = read(seal)
        for name, expected in files.items():
            if digest((folder / name).read_bytes()) != expected:
                raise ValueError(f"Changed preceding source packet: {name}")
        fetched = folder / "fetched-revisions.json"
        for title, revision in read(fetched).items():
            titles.add(norm(title))
            raw = (folder / "editions" / f"{revision}.wiki").read_text()
            author = re.search(r"\|\s*author\s*=\s*([^\n|}]+)", raw, re.I)
            if author:
                authors.add(norm(author[1]))
        groups = defaultdict(list)
        for row in read(folder / "corpus.json"):
            groups[row["work_id"], row["paragraph"]].append(normalized(row["text"]))
        protected.update("".join(g) for g in groups.values())
        for path in (seal, fetched, folder / "corpus.json"):
            archive[str(path.relative_to(root))] = digest(path.read_bytes())
    variants = root / "data/raw/phonology" / ARCHIVE
    table = variant_families(variants)
    archive[str(variants.relative_to(root))] = digest(variants.read_bytes())
    def unify(values):
        return {s.translate(table) for s in values}
    return unify(authors), unify(titles), unify(protected), archive, table


def candidates(catalog):
    volumes = [120 + (37 + 137 * k) % 760 for k in range(180)]
    copies = catalogue(catalog, volumes)
    pools = []
    for v in volumes:
        if v in copies:
            names = re.findall(r"^\s*\{\{:([^{}]+)\}\}\s*$", copies[v].read_text(), re.M)
            pools.append([n for n in names if title_genre(n) in set("表啟箋牋書序檄")])
    order = dict.fromkeys(n for level in zip_longest(*pools) for n in level if n)
    return {v: p.name for v, p in copies.items()}, list(islice(order, 2000))


def eligible_sentences(paragraphs, protected, table=None):
    units = [s for group in paragraphs for s in group]
    quotes = quoted_sentences([dict(id=i, work_id="candidate", text=s) for i, s in enumerate(units)])
    keys = [normalized(s).translate(table or {}) for s in units]
    counts = Counter(keys)
    return [i for i, s in enumerate(units) if i not in quotes and counts[keys[i]] == 1
            and closing_pair(s) and not any(keys[i] in p for p in protected)]


def acquire(root, run, supersedes=None):
    out = run / "inputs"
    if (out / "source-seal.json").exists():
        raise FileExistsError("Use the sealed source packet or a new run")
    catalog, editions = out / "catalog", out / "editions"
    for folder in (catalog, editions):
        folder.mkdir(exist_ok=True)
    fetched = out / "fetched-revisions.json"
    manifest = read(fetched) if fetched.exists() else {}
    excluded = (run, supersedes) if supersedes is not None else (run,)
    authors, titles, protected, archive, table = reserve_previous(root, excluded)
    def key(name):
        return norm(name).translate(table)
    frozen_counts = dict(authors=len(authors), titles=len(titles), protected_spans=len(protected))
    index, order = candidates(catalog)
    accepted, fallback, log = [], [], []

    def admit(record, indices):
        a, t, _, _, _, paragraphs = record
        accepted.append((record, indices))
        authors.add(key(a))
        titles.add(key(t))
        protected.update("".join(key(s) for s in group) for group in paragraphs)

    def screen(name):
        revision = manifest.get(name)
        if revision is None:
            return "missing revision"
        raw = (editions / f"{revision}.wiki").read_text()
        author, title, edition, paragraphs = parse_candidate(raw, name)
        if key(author) in authors or key(title) in titles or key(name) in titles:
            return "reserved author or work"
        indices = eligible_sentences(paragraphs, protected, table)
        record = author, title, title_genre(name), revision, edition, paragraphs
        if len(indices) >= 4:
            admit(record, indices)
            return f"selected ({len(indices)})"
        if len(indices) >= 2:
            fallback.append(record)
        return f"eligible targets: {len(indices)}"

    for start in range(0, len(order), 14):
        batch = order[start:start+14]
        fetch_works(editions, [n for n in batch if key(n) not in titles], manifest)
        for name in batch:
            try:
                why = "reserved title" if key(name) in titles else screen(name)
            except ValueError as error:
                why = str(error)
            log.append((name, why))
            if len(accepted) == 10:
                break
        if start % 140 == 0 or len(accepted) == 10:
            print(f"Screened {len(log)}; accepted {len(accepted)}; reserve {len(fallback)}", flush=True)
        if len(accepted) == 10:
            break
    if len(accepted) < 10:
        for record in fallback:
            author, title, _, _, _, paragraphs = record
            if key(author) in authors or key(title) in titles:
                continue
            indices = eligible_sentences(paragraphs, protected, table)
            if len(indices) >= 2:
                admit(record, indices)
            if len(accepted) == 10:
                break
    if not accepted:
        save(out / "screening-log.json", log)
        raise ValueError("No work with at least two eligible targets")
    works, corpus, reading = [], [], []
    for number, (record, indices) in enumerate(accepted, 1):
        author, title, genre, revision, edition, paragraphs = record
        wid, n = f"W{number:02}", min(8, len(indices))
        selected = {indices[(2*i+1)*len(indices)//(2*n)] for i in range(n)}
        idx = 0
        for p, group in enumerate(paragraphs, 1):
            para = f"P{p:02}"
            rows = []
            for text in group:
                row = dict(id=f"{wid}S{idx+1:03}", text=text, target=idx in selected)
                corpus.append(dict(**row, work_id=wid, section=para, paragraph=para, order=idx+1))
                rows.append(row)
                idx += 1
            if any(r["target"] for r in rows):
                reading.append(dict(work_id=wid, paragraph=para, sentences=rows))
        works.append(dict(work_id=wid, author=author, title=title, genre=genre, revision=revision,
                          edition=edition, source_url=f"https://zh.wikisource.org/w/index.php?oldid={revision}",
                          wiki_sha256=digest((editions/f"{revision}.wiki").read_bytes()),
                          rights="Ancient text public domain; Wikisource contributors, CC BY-SA 4.0",
                          eligible=len(indices), targets=n, sentences=idx))
    save(out / "sources.json", dict(works=works, screened=log, frame_size=len(order),
                                    reserved=frozen_counts, earlier_files=archive, catalogs=index))
    save(out / "corpus.json", corpus)
    save(out / "reading.json", reading)
    prepare(run)
    save(out / "source-seal.json", {name: digest((out / name).read_bytes())
                                    for name in ("sources.json", "corpus.json", "reading.json", "pair-packet.json")})
    print(f"Sealed {len(works)} works, {len(corpus)} sentences, {sum(w['targets'] for w in works)} targets.", flush=True)


if __name__ == "__main__":
    acquire(*(Path(arg) for arg in sys.argv[1:]))
