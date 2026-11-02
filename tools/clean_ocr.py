"""Split the archive.org OCR of Beckwith, *Hawaiian Mythology* (1940) into
per-chapter English source files, using the line geometry in *_djvu.xml.

    python3 -I tools/clean_ocr.py hawaiianmytholog00beck_0_djvu.xml source/en

Source: https://archive.org/details/hawaiianmytholog00beck_0 (public domain in
the US per the HathiTrust copyright review). The output is a first pass:
chapter translators proofread it (OCR errors in Hawaiian names, footnote marks).

File format (source/en/NN.md):
    {p:17}                 a new printed page starts here (also inline, mid-paragraph)
    ¶12 text               numbered paragraph
    ¶13 > line / > line    verse or block quotation, one "> " line per printed line
    [^?]                   probable footnote mark (OCR glyph such as * ° ®); numbering to be fixed by hand
    [^4]: text             footnote 4 of this chapter
"""
import re, sys, json, html, statistics as st

def load(path):
    x = open(path, encoding="utf-8").read()
    pages = []
    for o in re.findall(r"<OBJECT.*?</OBJECT>", x, re.S):
        lines = []
        for ln in re.findall(r"<LINE>(.*?)</LINE>", o, re.S):
            ws = re.findall(r'<WORD coords="(\d+),(\d+),(\d+),(\d+)"[^>]*>(.*?)</WORD>', ln, re.S)
            if not ws: continue
            hs = sorted(int(w[1]) - int(w[3]) for w in ws)
            lines.append(dict(x0=int(ws[0][0]), x1=int(ws[-1][2]),
                              top=min(int(w[3]) for w in ws), h=hs[len(hs)//2],
                              t=html.unescape(" ".join(w[4] for w in ws)).strip()))
        pages.append(lines)
    return pages

HEAD = re.compile(r"^(?:(\d{1,3})\s+HAWA\S*\s+MYTHOLOGY|([A-Z][A-Z‘’'\-, .]{2,}?)\s+([\dIlOoSsB]{1,3}))$")
TITLES = ["COMING OF THE GODS","KU GODS","THE GOD LONO","THE KANE WORSHIP","KANE AND KANALOA",
 "MYTHICAL LANDS OF THE GODS","LESSER GODS","SORCERY GODS","GUARDIAN GODS","THE SOUL AFTER DEATH",
 "THE PELE MYTH","THE PELE SISTERS","PELE LEGENDS","KAMAPUA","HINA MYTHS","MAUI THE TRICKSTER",
 "AIKANAKA","LAKA CYCLE","HAUMEA","PAPA AND WAKEA","GENEALOGIES","ERA OF OVERTURNING",
 "MU AND MENEHUNE PEOPLE","RUNNERS","MOIKEHA","HAWAIILOA AND PAAO MIGRATIONS","RULING CHIEFS",
 "USURPING CHIEFS","KUPUA STORIES","TRICKSTER STORIES","VOYAGE TO THE LAND OF THE GODS",
 "RIDDLING CONTESTS","THE KANA LEGEND","STRETCHING-TREE KUPUA","ROMANCE OF THE SWIMMER",
 "ROMANCE OF THE ISLAND OF VIRGINS","ROMANCES OF MATCH-MAKING","ROMANCES OF THE DANCE",
 "WOOING ROMANCES","REFERENCES","INDEX"]
EN_TITLES = ["Preface","Coming of the Gods","Ku Gods","The God Lono","The Kane Worship","Kane and Kanaloa",
 "Mythical Lands of the Gods","Lesser Gods","Sorcery Gods","Guardian Gods","The Soul after Death",
 "The Pele Myth","The Pele Sisters","Pele Legends","Kamapua‘a","Hina Myths","Maui the Trickster",
 "Aikanaka-Kaha‘i Cycle","Wahieloa-Laka Cycle","Haumea","Papa and Wakea","Genealogies","Era of Overturning",
 "Mu and Menehune People","Runners, Man-Eaters, Dog-Men","The Moikeha-La‘a Migration",
 "Hawaiiloa and Paao Migrations","Ruling Chiefs","Usurping Chiefs","Kupua Stories","Trickster Stories",
 "Voyage to the Land of the Gods","Riddling Contests","The Kana Legend","The Stretching-Tree Kupua",
 "Romance of the Swimmer","Romance of the Island of Virgins","Romances of Match-Making",
 "Romances of the Dance","Wooing Romances","References"]
PART = lambda n: 0 if n in (0,40) else 1 if n <= 10 else 2 if n <= 19 else 3 if n <= 28 else 4

def page_number(line):
    m = HEAD.match(line["t"])
    if not m: return None
    s = m.group(1) or m.group(3)
    s = s.translate(str.maketrans("IlOoSsB", "1100558"))
    return int(s) if s.isdigit() else -1

PAGEMAP = {}

def main(xml, out):
    pages = load(xml)
    # locate chapter openings: a page whose first lines contain a roman numeral and the title
    starts = {}
    ci = 0
    for leaf, lines in enumerate(pages):
        if leaf < 14 or ci >= len(TITLES): continue
        top = " ".join(l["t"] for l in lines[:4]).upper()
        if TITLES[ci] in top and not HEAD.match(lines[0]["t"]) or (TITLES[ci] in top and ci == 39):
            starts[ci+1] = leaf; ci += 1
    assert ci == len(TITLES), f"found only {ci} chapters; next {TITLES[ci]}"
    pref = next(i for i, ls in enumerate(pages) if ls and ls[0]["t"].strip() == "PREFACE")
    starts[0] = pref
    order = sorted(starts.items(), key=lambda kv: kv[1])
    meta = []
    for k, (num, leaf) in enumerate(order):
        if num == 41: continue
        end = order[k+1][1] if k+1 < len(order) else len(pages)
        if num == 0:  # preface ends before the contents
            end = next(i for i in range(leaf, end) if pages[i] and "CONTENTS" in " ".join(l["t"] for l in pages[i][:3]))
        text, info = chapter(pages[leaf:end], num, leaf)
        with open(f"{out}/{num:02d}.md", "w", encoding="utf-8") as f:
            f.write(f"---\nchapter: {num}\ntitle: {EN_TITLES[num]}\npart: {PART(num)}\npages: {info['first']}-{info['last']}\n---\n\n{text}\n")
        info.update(chapter=num, title=EN_TITLES[num], part=PART(num))
        meta.append(info)
        print(f"{num:02d} {EN_TITLES[num]:36s} pp.{info['first']}-{info['last']} paras={info['paras']} notes={info['notes']} marks={info['marks']}")
    json.dump(meta, open(f"{out}/_chapters.json", "w"), ensure_ascii=False, indent=1)
    json.dump(PAGEMAP, open(f"{out}/_pagemap.json", "w"), indent=0)

MARK = re.compile(r"(?<=[\w.,;:!?”’)\]])([*°®¹²³⁴⁵⁶⁷⁸⁹⁰†‡§]+|™)(?=\s|$)")
NOTE_START = re.compile(r"^(\d{1,3})[.,]\s+")

def chapter(pages, num, leaf0):
    items = []          # ("para", [lines...]) / ("verse", [...]) / ("page", n)
    notes = []
    prev_no = None
    first = last = None
    for i, lines in enumerate(pages):
        if not lines: continue
        pn = page_number(lines[0])
        body = lines[1:] if pn is not None else lines
        if pn is None or pn < 0:
            pn = (prev_no + 1) if prev_no else None
        if i == 0:
            # chapter opening: drop roman numeral + title lines
            while body and (re.fullmatch(r"[IVXLC1l|\s.]+", body[0]["t"]) or body[0]["t"].upper() == body[0]["t"] and len(body[0]["t"]) < 50):
                body = body[1:]
        prev_no = pn
        if pn: PAGEMAP[pn] = leaf0 + i + 1
        first = first or pn; last = pn or last
        if not body: continue
        heights = [l["h"] for l in body]
        H = st.median(heights)
        margin = st.median(sorted(l["x0"] for l in body)[: max(3, len(body)//2)])
        right = st.median(sorted((l["x1"] for l in body), reverse=True)[: max(3, len(body)//2)])
        gaps = [body[j+1]["top"] - body[j]["top"] for j in range(len(body)-1)]
        G = st.median(gaps) if gaps else 80
        # footnote block: first line after a big gap that starts with "N." and is near the bottom
        cut = len(body)
        for j in range(1, len(body)):
            if body[j]["top"] - body[j-1]["top"] > 1.35 * G and NOTE_START.match(body[j]["t"]) \
               and all(NOTE_START.match(b["t"]) or b["h"] <= H * 1.05 for b in body[j:]):
                cut = j; break
        else:
            # footnotes with no visible gap (rare): trailing lines with small type starting "N."
            pass
        for b in body[cut:]:
            for part in re.split(r"(?<=[.\d])\s+(?=\d{1,3}\.\s)", b["t"]):
                m = NOTE_START.match(part)
                if m: notes.append([int(m.group(1)), part[m.end():]])
                elif notes: notes[-1][1] += "\n" + part
        if i > 0 and pn: items.append(("page", pn))
        for j, l in enumerate(body[:cut]):
            t = l["t"].lstrip("|_ ").strip()
            if not t or (len(t) <= 2 and not t.isalnum()): continue
            ind = l["x0"] - margin
            short = l["x1"] < right - 0.12 * (right - margin)
            gap_before = j > 0 and body[j]["top"] - body[j-1]["top"] > 1.35 * G
            verse = ind > 0.06 * (right - margin) and (short or (items and items[-1][0] == "verse")) \
                    and not (ind < 0.06*(right-margin) + 40 and not short)
            if ind > 0.025 * (right - margin) and ind < 0.06 * (right - margin):
                verse = False
            if verse and items and items[-1][0] == "verse" and not gap_before:
                items[-1][1].append(t)
            elif verse:
                # a single indented short line is usually a heading ("LEGEND OF ..."), else verse
                items.append(("verse", [t]))
            elif ind > 0.025 * (right - margin) or gap_before or not items or items[-1][0] in ("verse",):
                if items and items[-1][0] == "page" and len(items) > 1 and items[-2][0] == "para" \
                   and continues(items[-2][1][-1], t) and ind <= 0.025 * (right - margin):
                    pg = items.pop(); items[-1][1].append(f"{{p:{pg[1]}}}"); items[-1][1].append(t)
                else:
                    items.append(("para", [t]))
            else:
                if items[-1][0] == "page":
                    pg = items.pop()
                    if items and items[-1][0] == "para":
                        items[-1][1].extend([f"{{p:{pg[1]}}}", t])
                    else:
                        items.append(pg); items.append(("para", [t]))
                else:
                    items[-1][1].append(t)
    # drop-cap repair for the first paragraph ("OW traditional ... / H a nature-...")
    if items and items[0][0] in ("para", "verse") and len(items[0][1]) > 1:
        a, b = items[0][1][0], items[0][1][1]
        m = re.match(r"^([A-Z])\s+(.*)", b)
        if re.match(r"^[A-Z]{1,3}\b", a) and m:
            items[0] = ("para", [m.group(1) + a, m.group(2)] + items[0][1][2:])
    out, n, marks = [], 0, 0
    for kind, pl in items:
        if kind == "page": out.append(f"{{p:{pl}}}"); continue
        n += 1
        if kind == "verse" and len(pl) == 1 and pl[0].upper() == pl[0] and len(pl[0]) > 6:
            out.append(f"¶{n} ### {pl[0]}"); continue
        if kind == "verse":
            txt = "\n".join("> " + mark(x) for x in pl)
            marks += txt.count("[^?]")
            out.append(f"¶{n}\n{txt}")
        else:
            txt = mark(join(pl)); marks += txt.count("[^?]")
            out.append(f"¶{n} {txt}")
    for k, t in notes:
        out.append(f"[^{k}]: " + join(t.split("\n")))
    return "\n\n".join(out), dict(first=first, last=last, paras=n, notes=len(notes), marks=marks)

def continues(prev, nxt):
    return prev.endswith("-") or nxt[:1].islower() or not re.search(r"[.?!:”\"’)\]—]$", prev)

def join(pl):
    s = ""
    for x in pl:
        if not s: s = x
        elif s.endswith("-") and not s.endswith("--") and re.match(r"[a-z]", x) and not re.search(r"[A-Z][a-z]*-$", s.split()[-1] if s.split() else ""):
            s = s[:-1] + x          # soft hyphen at line end
        elif s.endswith("-"):
            s = s + x               # real hyphen in a Hawaiian compound name (Ku-moku-) – keep
        else:
            s = s + " " + x
    return re.sub(r"\s+", " ", s).strip()

def mark(s):
    return MARK.sub("[^?]", s)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
