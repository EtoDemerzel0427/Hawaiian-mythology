"""Convert the sacred-texts HTML of Beckwith, *The Kumulipo* (1951) into source files.

    python3 -I tools/import_kumulipo.py <dir with ku00.htm..ku33.htm> <repo root>

Writes
    source/kumulipo/en/NN.md          one file per chapter (same format as source/en/)
    source/kumulipo/_chapters.json
    data/kumulipo/haw-lines.json      Appendix I (Kalakaua text): {line_no: hawaiian}, plus section starts
"""
import html, json, re, sys
from pathlib import Path

# file index -> (chapter number, part, English title); titles taken from the book's contents
CHAPTERS = {
    2: (0, 0, "Introduction"),
    3: (1, 1, "The Prose Note"), 4: (2, 1, "Rank in Hawaii"), 5: (3, 1, "The First-Born Son and the Taboo"),
    6: (4, 1, "Lono of the Makahiki"), 7: (5, 1, "Captain Cook as Lono"), 8: (6, 1, "Two Dynasties"),
    9: (7, 2, "The Master of Song"), 10: (8, 2, "Prologue to the Night World"), 11: (9, 2, "The Refrain of Generation"),
    12: (10, 2, "Birth of Sea and Land Life"), 13: (11, 2, "The World of Infancy"), 14: (12, 2, "Winged Life"),
    15: (13, 2, "The Crawlers"), 16: (14, 2, "The Night-Digger"), 17: (15, 2, "The Nibblers"),
    18: (16, 2, "The Dog Child"), 19: (17, 2, "The Dawn of Day"), 20: (18, 2, "The Woman Who Sat Sideways"),
    21: (19, 2, "The Flood"), 22: (20, 2, "The Woman Who Bore Children through the Brain"),
    23: (21, 2, "Papa and Wakea"), 24: (22, 2, "Maui the Usurper"), 25: (23, 2, "The Dedication"),
    26: (24, 2, "The Genealogies"), 27: (25, 3, "Hawaiian Accounts of Creation"),
    28: (26, 3, "Other Polynesian Accounts of Creation"), 29: (27, 3, "Ceremonial Birth Chants in Polynesia"),
    30: (28, 0, "Conclusion"), 31: (29, 4, "Appendix I: The Kalakaua Text"), 32: (30, 4, "Appendix II: Textual Notes"),
    33: (31, 4, "Appendix III: References"),
}

SKIP_HEADS = {"social and historical background", "the chant", "the polynesian chant of creation", "appendixes"}

def clean(s):
    s = re.sub(r"\s+", " ", s)                       # source line breaks are not significant
    s = re.sub(r"(?is)<i>(.*?)</i>", r"*\1*", s)
    s = re.sub(r"(?is)<b>(.*?)</b>", r"**\1**", s)
    s = re.sub(r"(?i)\s*<br\s*/?>\s*", "\n", s)      # <BR> marks a verse line
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"\*\s*\*", "", s)
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in s.split("\n")).strip()

def blocks(src):
    body = src[src.lower().find("<body"):]
    # content lies between the first <HR> (after top nav) and the last <HR> before the bottom nav
    hrs = [m.start() for m in re.finditer(r"(?i)<hr", body)]
    body = body[hrs[0]:]
    end = re.search(r"(?is)<hr>\s*<nav", body)
    if end: body = body[:end.start()]
    out = []
    for m in re.finditer(r"(?is)<(h[1-6]|p)\b([^>]*)>(.*?)(?=<(?:h[1-6]|p)\b|\Z)", body):
        tag, attrs, inner = m.group(1).lower(), m.group(2), m.group(3)
        inner = re.sub(r"(?is)</(p|h[1-6])>.*", "", inner) if tag == "p" else re.sub(r"(?is)</h[1-6]>.*", "", inner)
        txt = clean(inner)
        if not txt: continue
        small = bool(re.search(r"(?i)<font size=2>\s*$", body[max(0, m.start()-40):m.start()]))
        out.append((tag, txt, "center" in attrs.lower(), small))
    return out

def extract_notes(src):
    """Footnotes sit in <FONT SIZE=2> regions as "[1. ...  2. ...]"; pull them out of the body."""
    notes = {}
    def grab(m):
        t = clean(re.sub(r"(?i)</?p[^>]*>", "\n", m.group(1))).replace("\n", " ")
        t = t.strip().lstrip("[").rstrip("]").strip()
        for num, body in re.findall(r"(?:^|\s)(\d{1,2})\.\s+(.*?)(?=\s\d{1,2}\.\s+[A-Z*\"']|$)", t):
            notes[int(num)] = body.strip().rstrip("]").strip()
        return ""
    src = re.sub(r"(?is)<font size=2>(.*?)</font>", grab, src)
    return src, notes

def to_md(blks, chap, notes=None):
    items, notes, n = [], dict(notes or {}), 0
    for tag, txt, center, small in blks:
        pm = re.fullmatch(r"\{p\.\s*([0-9ivxlc]+)\}", txt)
        if pm:
            items.append(f"{{p:{pm.group(1)}}}"); continue
        fm = re.fullmatch(r"(?s)\[(\d+)\.\s*(.*)\]", txt)
        if fm:
            notes[int(fm.group(1))] = re.sub(r"\s+", " ", fm.group(2)); continue
        if tag.startswith("h"):
            if tag in ("h1",) or txt.lower() in SKIP_HEADS or re.fullmatch(r"(?i)(part|chapter|appendix)\b.*", txt) and len(txt) < 30:
                continue                         # part / chapter-number headings; the chapter title is in frontmatter
            n += 1; items.append(f"¶{n} ### {txt.title() if txt.isupper() else txt}"); continue
        txt = re.sub(r"(?<=[^\s\[])\[(\d{1,3})\]", r"[^\1]", txt)
        lines = txt.split("\n")
        # a paragraph broken by a page boundary continues in lower case: join it to the previous one
        if len(lines) == 1 and txt[:1].islower() and len(items) >= 2 and items[-1].startswith("{p:") and items[-2].startswith("¶") and "\n> " not in items[-2]:
            pg = items.pop()
            items[-1] = items[-1] + " " + pg + " " + txt
            continue
        n += 1
        if len(lines) > 1 or re.match(r"^\d+\.\s", txt):
            items.append(f"¶{n}\n" + "\n".join("> " + l for l in lines))
        else:
            items.append(f"¶{n} " + txt)
    for k in sorted(notes):
        items.append(f"[^{k}]: {notes[k]}")
    return "\n\n".join(items), n, len(notes)

def main(d, root):
    d, root = Path(d), Path(root)
    out = root / "source" / "kumulipo" / "en"; out.mkdir(parents=True, exist_ok=True)
    meta = []
    for k, (num, part, title) in sorted(CHAPTERS.items()):
        src = (d / f"ku{k:02d}.htm").read_text(encoding="utf-8", errors="replace")
        src, notes = extract_notes(src)
        blks = blocks(src)
        # the chapter's own title heading duplicates the frontmatter title: drop it
        key = lambda t: re.sub(r"[^a-z]", "", t.lower())
        blks = [b for i, b in enumerate(blks) if not (i < 4 and b[0].startswith("h") and key(b[1]) and key(b[1]) in key(title))]
        text, paras, nnotes = to_md(blks, num, notes)
        pages = re.findall(r"\{p:(\d+)\}", text)
        (out / f"{num:02d}.md").write_text(f"---\nchapter: {num}\ntitle: {title}\npart: {part}\npages: {pages[0] if pages else ''}-{pages[-1] if pages else ''}\n---\n\n{text}\n", encoding="utf-8")
        meta.append(dict(chapter=num, title=title, part=part, paras=paras, notes=nnotes))
        print(f"{num:02d} {title:48s} paras={paras:4d} notes={nnotes}")
    (root / "source" / "kumulipo" / "_chapters.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    # Hawaiian lines from Appendix I
    app = (d / "ku31.htm").read_text(encoding="utf-8", errors="replace")
    app = app[:app.find("APPENDIX II")] if "APPENDIX II" in app else app
    app, _ = extract_notes(app)                      # Appendix I has a few footnotes of its own
    app = re.sub(r"(?<=\S)\[\d{1,2}\]", "", app)    # and their markers
    # genealogies are printed in two columns (husband | wife) as HTML tables: zip them into "husband / wife" lines
    def merge_table(m):
        out = []
        for tr in re.findall(r"(?is)<tr\b.*?(?=<tr\b|</table>)", m.group(0)):
            cols = [[l for l in clean(td).split("\n") if l.strip()] for td in re.findall(r"(?is)<td\b[^>]*>(.*?)(?=<td\b|</tr>|$)", tr)]
            cols = [c for c in cols if c]
            if not cols: continue
            if len(cols) == 1: out += cols[0]; continue
            L, R = cols[0], cols[1]
            for i in range(max(len(L), len(R))):
                a = L[i] if i < len(L) else ""
                b = re.sub(r"^\d+\.\s*", "", R[i]) if i < len(R) else ""
                out.append(f"{a} / {b}" if a and b else (a or b))
        return "<P>" + "<BR>".join(html.escape(x) for x in out) + "</P>"
    app = re.sub(r"(?is)<table\b.*?</table>", merge_table, app)
    lines, sections, cur = {}, [], None
    for tag, txt, center, small in blocks(app):
        if tag in ("h3", "h4") and txt.upper().startswith(("KA WA", "(HE LALA")): sections.append(dict(title=txt, start=None)); continue
        last = max(lines) if lines else 0
        for l in txt.split("\n"):
            l = l.strip()
            if not l or l.startswith("{p."): continue
            m = re.match(r"^(\d+)\.\s*(.*)$", l)
            if m:
                ln = int(m.group(1)); text = m.group(2).strip()
                if last and abs(ln - (last + 1)) > 5: ln = last + 1     # misprinted number (e.g. "1889" for 1989)
            elif last: ln = last + 1; text = l          # only every fifth line is numbered in the genealogies
            else: continue
            lines[ln] = text; last = ln
            if sections and sections[-1]["start"] is None: sections[-1]["start"] = ln
    dd = root / "data" / "kumulipo"; dd.mkdir(parents=True, exist_ok=True)
    ov = dd / "haw-overrides.json"          # hand-checked corrections against the scan
    if ov.exists():
        for k, v in json.load(open(ov, encoding="utf-8"))["lines"].items(): lines[int(k)] = v
    (dd / "haw-lines.json").write_text(json.dumps(dict(sections=sections, lines=lines), ensure_ascii=False, indent=0))
    print("hawaiian lines:", len(lines), "max", max(lines), "sections", [(s["title"], s["start"]) for s in sections])

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
