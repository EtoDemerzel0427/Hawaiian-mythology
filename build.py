#!/usr/bin/env python3
"""夏威夷神话注疏 · 静态站点生成器

    python3 build.py              # 生成 _site/
    python3 build.py --serve      # 生成并在 http://localhost:8767 预览
    python3 build.py --check      # 只做校验（段落对齐、术语引用、交叉链接）

两本书：
    hm  Beckwith, Hawaiian Mythology (1940)
        source/en/NN.md               英文底本（¶ 段落号、{p:N} 页码、[^N] 原注）
        content/book/NN-*.md          中文译注
    ku  Beckwith, The Kumulipo (1951)
        source/kumulipo/en/NN.md      英文底本
        content/kumulipo/NN-*.md      中文译注
        data/kumulipo/haw-lines.json  夏威夷语原文（Kalākaua 1889 刊本，逐行编号）
        data/kumulipo/lines/*.json    逐行对读：{行号: {"en": Beckwith 英译, "zh": 中译, "note": 行注}}
        content/kumulipo/chant/waNN.md 全诗对读页各 wā 的导读（可选）
其他：
    content/essays/*.md   专栏          content/about/*.md   体例
    data/names/*.json     译名表        data/glossary/*.json 术语表（均在构建时合并）
"""
import argparse, html, json, os, re, shutil, sys, glob
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"
SITE_TITLE = "夏威夷神话注疏"
SITE_SUB = "Beckwith《夏威夷神话》《库穆利波》、Malo《夏威夷古俗》全译与导读"
REPO = "https://github.com/EtoDemerzel0427/Hawaiian-mythology"
CN_NUM = "零一二三四五六七八九"

def cn_num(n):
    if n < 10: return CN_NUM[n]
    if n < 20: return "十" + (CN_NUM[n % 10] if n % 10 else "")
    return CN_NUM[n // 10] + "十" + (CN_NUM[n % 10] if n % 10 else "")

def roman(n):
    out = ""
    for v, r in ((40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v: out += r; n -= v
    return out

BOOKS = {
    "hm": dict(
        key="hm", prefix="ch", title="夏威夷神话", en_title="Hawaiian Mythology", year=1940,
        src="source/en", zh="content/book", url="book",
        scan="https://archive.org/details/hawaiianmytholog00beck_0/page/n{leaf}/mode/1up", pagemap="source/en/_pagemap.json",
        parts={0: "", 1: "第一部 · 众神", 2: "第二部 · 神之子嗣", 3: "第三部 · 酋长", 4: "第四部 · 虚构故事中的英雄与恋人"},
        parts_en={1: "Part One: The Gods", 2: "Part Two: Children of the Gods", 3: "Part Three: The Chiefs", 4: "Part Four: Heroes and Lovers in Fiction"},
        special={0: "序", 40: "参考文献"}, refs=40,
        credit="Martha Warren Beckwith, <i>Hawaiian Mythology</i>, Yale University Press, 1940"),
    "ku": dict(
        key="ku", prefix="ku", title="库穆利波", en_title="The Kumulipo", year=1951,
        src="source/kumulipo/en", zh="content/kumulipo", url="kumulipo", scan=None, pagemap=None,
        parts={0: "", 1: "第一部 · 社会与历史背景", 2: "第二部 · 颂歌", 3: "第三部 · 波利尼西亚的创世颂歌", 4: "附录"},
        parts_en={1: "Part I: Social and Historical Background", 2: "Part II: The Chant", 3: "Part III: The Polynesian Chant of Creation", 4: "Appendixes"},
        special={0: "导言", 28: "结语", 29: "附录一", 30: "附录二", 31: "附录三"}, refs=31, chant_chapter=29,
        credit="Martha Warren Beckwith, <i>The Kumulipo: A Hawaiian Creation Chant</i>, University of Chicago Press, 1951"),
    "malo": dict(
        key="malo", prefix="ma", title="夏威夷古俗", en_title="Hawaiian Antiquities", year=1903,
        src="source/malo/en", zh="content/malo", url="malo",
        scan="https://archive.org/details/hawaiianantiquit00malorich/page/{p}/mode/1up", pagemap=None, scan_printed=True,
        parts={0: "", 1: "一 · 天地、自然与物产", 2: "二 · 社会、禁忌与财产", 3: "三 · 宗教、礼仪与生死", 4: "四 · 政治、生计与娱乐", 5: "五 · 洪水与古代诸王"},
        parts_en={1: "Chapters I–XVII", 2: "Chapters XVIII–XXII", 3: "Chapters XXIII–XXXVII", 4: "Chapters XXXVIII–LVII", 5: "Chapters LVIII–LXVII"},
        special={0: "卷首"}, refs=None,
        credit="David Malo, <i>Hawaiian Antiquities (Moolelo Hawaii)</i>, tr. N. B. Emerson, Honolulu: Hawaiian Gazette, 1903"),
}

WA_ZH = ["", "第一 wā", "第二 wā", "第三 wā", "第四 wā", "第五 wā", "第六 wā", "第七 wā", "第八 wā", "第九 wā", "第十 wā",
         "第十一 wā", "第十二 wā", "第十三 wā", "第十四 wā", "第十五 wā", "第十六 wā"]

WARN = []
def warn(msg): WARN.append(msg)

def chap_label(book, n):
    b = BOOKS[book]
    return b["special"].get(n) or f"第{cn_num(n)}章"

def esc(s): return html.escape(str(s), quote=True)

# ---------------------------------------------------------------- loading
def parse_fm(text):
    meta = {}
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        for line in text[4:end].splitlines():
            if ":" in line:
                k, v = line.split(":", 1); meta[k.strip()] = v.strip()
        text = text[end + 4:].lstrip("\n")
    return meta, text

def load_json_dir(pattern):
    merged = {}
    for f in sorted(glob.glob(str(ROOT / pattern))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            warn(f"{f}: JSON 解析失败 {e}"); continue
        for k, v in d.items():
            if k in merged and merged[k] != v:
                warn(f"{os.path.basename(f)}: 词条 {k} 与已有定义冲突，保留先出现者")
                continue
            merged[k] = v
    return merged

PARA_RE = re.compile(r"^¶(\d+)(?:[-–](\d+))?(?:[ \t]+|\n|$)", re.M)

def split_paras(body):
    """Return ([("md", text) | ["para", n, n_end, text]], notes{n: text}).
    A paragraph runs until the next ¶ marker or the next top-level block that is
    an admonition / heading / html block / footnote definition."""
    notes = {}
    def grab_note(m):
        txt = re.sub(r"\n(?:    |\t)", "\n", m.group(2))          # continuation lines: strip the 4-space indent
        notes[m.group(1)] = re.sub(r"\n[ \t]+\n", "\n\n", txt).strip(); return ""
    # a note runs on over indented lines, which may be separated by blank (or whitespace-only) lines
    body = re.sub(r"^\[\^(t?\d+)\]:[ \t]*((?:.*)(?:\n(?:[ \t]*\n)*(?:    |\t).*)*)", grab_note, body, flags=re.M)
    blocks = re.split(r"\n\s*\n", body.strip())
    out, cur = [], None
    for b in blocks:
        m = PARA_RE.match(b)
        if b.startswith(("    ", "\t")) and out:
            if out[-1][0] == "md": out[-1][1] += "\n\n" + b
            else: out[-1][3] += "\n\n" + b
            continue
        if m:
            cur = ["para", int(m.group(1)), int(m.group(2) or m.group(1)), b[m.end():]]
            out.append(cur)
        elif cur is not None and not re.match(r"^(!!!|\?\?\?|#|<|\{p:[0-9ivxl]+\}\s*$|---)", b):
            cur[3] += "\n\n" + b
        else:
            cur = None
            out.append(["md", b])
    return out, notes

def load_source(book, n):
    f = ROOT / BOOKS[book]["src"] / f"{n:02d}.md"
    if not f.exists(): return None
    meta, body = parse_fm(f.read_text(encoding="utf-8"))
    seq, notes = split_paras(body)
    paras, pending_page = {}, None
    for item in seq:
        if item[0] == "para":
            txt = item[3]
            if pending_page:
                sep = "\n\n" if txt.lstrip().startswith((">", "#", "|", "```")) else " "
                txt = "{p:%s}" % pending_page + sep + txt; pending_page = None
            paras[item[1]] = txt
        else:
            m = re.fullmatch(r"\{p:([0-9ivxl]+)\}", item[1].strip())
            if m: pending_page = m.group(1)
    return dict(meta=meta, paras=paras, notes=notes)

# ---------------------------------------------------------------- context
class Ctx:
    def __init__(self):
        self.names = load_json_dir("data/names/*.json")
        self.gloss = load_json_dir("data/glossary/*.json")
        self.pagemaps = {k: json.load(open(ROOT / b["pagemap"])) if b["pagemap"] else {} for k, b in BOOKS.items()}
        self.chapters = {}   # (book, n) -> dict
        self.essays = {}
        hl = ROOT / "data" / "kumulipo" / "haw-lines.json"
        self.haw = json.load(open(hl, encoding="utf-8")) if hl.exists() else {"lines": {}, "sections": []}
        lf = ROOT / "data" / "kumulipo" / "lili.json"   # Liliuokalani 1897, aligned by verse
        self.lili = json.load(open(lf, encoding="utf-8")) if lf.exists() else []
        self.lines = {}      # line -> {"en", "zh", "note"}
        for f in sorted(glob.glob(str(ROOT / "data" / "kumulipo" / "lines" / "*.json"))):
            try:
                for k, v in json.load(open(f, encoding="utf-8")).items():
                    if k in self.lines: warn(f"{os.path.basename(f)}: 第 {k} 行重复定义")
                    self.lines[k] = v
            except Exception as e:
                warn(f"{f}: JSON 解析失败 {e}")

    def book_chapters(self, book):
        return [(n, c) for (b, n), c in sorted(self.chapters.items()) if b == book]

ctx = None

def md_render(text):
    return markdown.markdown(text, extensions=["extra", "admonition", "sane_lists", "toc"],
                             extension_configs={"toc": {"permalink": False, "slugify": slugify}},
                             output_format="html5")

def slugify(value, sep="-"):
    v = re.sub(r"[^\w一-鿿\- ]", "", value).strip().lower()
    return re.sub(r"[\s]+", sep, v) or "s"

def verse_breaks(text):
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.startswith(">") and i + 1 < len(lines) and lines[i + 1].startswith(">") and lines[i+1].strip() != ">" and l.strip() != ">":
            lines[i] = l.rstrip() + "  "
    return "\n".join(lines)

def scan_link(book, p):
    b = BOOKS[book]
    pm = ctx.pagemaps.get(book) or {}
    leaf = pm.get(str(p))
    if not leaf and str(p).isdigit() and pm:
        nxt, prv = pm.get(str(int(p) + 1)), pm.get(str(int(p) - 1))
        leaf = (nxt - 1) if nxt else (prv + 1) if prv else None
    if b.get("scan_printed") and str(p).isdigit():
        return f'<a class="pg" href="{b["scan"].format(p=p)}" target="_blank" rel="noopener" title="查看 {b["year"]} 年原书第 {p} 页扫描">p.{p}</a>'
    if not leaf or not b["scan"]:
        return f'<span class="pg" title="{b["year"]} 年原书第 {p} 页">p.{p}</span>'
    return f'<a class="pg" href="{b["scan"].format(leaf=leaf-1)}" target="_blank" rel="noopener" title="查看 {b["year"]} 年原书第 {p} 页扫描">p.{p}</a>'

def chant_block(a, z, root):
    rows = []
    for k in range(a, z + 1):
        h = ctx.haw["lines"].get(str(k))
        if h is None: continue
        L = ctx.lines.get(str(k), {})
        rows.append(f'<div class="cl"><a class="ln" href="{root}kumulipo/chant.html#l{k}">{k}</a>'
                    f'<span class="haw" lang="haw">{esc(h)}</span><span class="lz">{esc(L.get("zh", ""))}</span></div>')
    if not rows:
        warn(f"chant:{a}-{z} 没有夏威夷语行"); return ""
    return (f'\n\n<div class="chant-block">{"".join(rows)}'
            f'<a class="chant-more" href="{root}kumulipo/chant.html#l{a}">全诗对读 · 第 {a}–{z} 行 →</a></div>\n\n')

def inline_pre(text, page_key, root, notes_used, en=False, book="hm"):
    codes = []
    def keep(m): codes.append(m.group(0)); return f"\x00{len(codes)-1}\x00"
    text = re.sub(r"`[^`\n]+`", keep, text)
    text = re.sub(r"\{\{chant:(\d+)(?:[-–](\d+))?\}\}", lambda m: chant_block(int(m.group(1)), int(m.group(2) or m.group(1)), root), text)
    text = re.sub(r"\{p:([0-9ivxl]+)\}", lambda m: scan_link(book, m.group(1)), text)
    def fn(m):
        k = m.group(1)
        notes_used.append(k)
        if k == "?": return '<sup class="fn unk" title="原注编号待核">?</sup>'
        cls = "tn" if k.startswith("t") else "fn"
        label = "译注" if k.startswith("t") else k
        pre = "en-" if en else ""
        return f'<sup class="{cls}"><a href="#{pre}fn-{k}" id="{pre}ref-{k}-{len(notes_used)}" data-fn="{k}">{label}</a></sup>'
    text = re.sub(r"\[\^(t?\d+|\?)\](?!:)", fn, text)
    text = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: xref_html(m.group(1), m.group(2), page_key, root), text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)

def xref_html(target, label, page_key, root):
    target = target.strip()
    if target.startswith("g:"):
        key = target[2:].strip()
        g = ctx.gloss.get(key) or ctx.gloss.get(key.lower())
        if not g:
            warn(f"{page_key}: 术语表无词条 [[g:{key}]]"); return esc(label or key)
        tip = g.get("zh", "") + "：" + g.get("def", "")
        return f'<a class="gl" href="{root}glossary.html#g-{esc(slugify(key))}" data-tip="{esc(tip)}">{esc(label or g.get("term", key))}</a>'
    m = re.fullmatch(r"(ch|ku|ma):(\d+)(?:#p?(\d+))?", target)
    if m:
        book = {"ch": "hm", "ku": "ku", "ma": "malo"}[m.group(1)]
        n, p = int(m.group(2)), m.group(3)
        c = ctx.chapters.get((book, n))
        if not c:
            warn(f"{page_key}: 无此章 [[{target}]]"); return esc(label or target)
        href = root + c["url"] + (f"#p{p}" if p else "")
        bk = {"hm": "", "ku": "《库穆利波》", "malo": "《夏威夷古俗》"}[book]
        text = label or (f"{bk}{chap_label(book, n)}「{c['title']}」" + (f" ¶{p}" if p else ""))
        return f'<a class="xref" href="{href}" title="{esc(c["en_title"])}">{esc(text)}</a>'
    m = re.fullmatch(r"line:(\d+)(?:[-–](\d+))?", target)
    if m:
        a, z = m.group(1), m.group(2)
        return f'<a class="xref" href="{root}kumulipo/chant.html#l{a}">{esc(label or ("第 " + a + ("–" + z if z else "") + " 行"))}</a>'
    if target == "chant":
        return f'<a class="xref" href="{root}kumulipo/chant.html">{esc(label or "《库穆利波》全诗对读")}</a>'
    m = re.fullmatch(r"essays/([\w\-]+)(?:#([\w\-]+))?", target)
    if m:
        e = ctx.essays.get(m.group(1))
        if not e:
            warn(f"{page_key}: 无此专栏 [[{target}]]"); return esc(label or target)
        href = root + e["url"] + (f"#{m.group(2)}" if m.group(2) else "")
        return f'<a class="xref essay" href="{href}" title="{esc(e["summary"])}">{esc(label or "专栏：" + e["title"])}</a>'
    if target in ("names", "glossary", "references", "ku-references"):
        url = {"names": "names.html", "glossary": "glossary.html",
               "references": ctx.chapters.get(("hm", 40), {}).get("url", ""),
               "ku-references": ctx.chapters.get(("ku", 31), {}).get("url", "")}[target]
        dflt = {"names": "神名人名对照表", "glossary": "术语表", "references": "参考文献", "ku-references": "《库穆利波》参考文献"}[target]
        return f'<a class="xref" href="{root}{url}">{esc(label or dflt)}</a>'
    warn(f"{page_key}: 无法解析的链接 [[{target}]]")
    return esc(label or target)

ADMON_TITLES = {"tldr": "本章导读", "culture": "文化背景", "language": "语言", "place": "地理",
                "compare": "比较神话", "modern": "今日视角", "source": "文献", "story": "故事梗概",
                "note": "注", "tip": "提示", "question": "思考", "chant": "吟唱", "summary": "小结",
                "warning": "注意", "people": "人物"}
KIND_TAGS = {"culture": "文化", "language": "语言", "place": "地理", "compare": "比较", "modern": "今日",
             "story": "故事", "people": "人物", "source": "文献", "note": "注", "chant": "吟唱", "question": "思考"}

def postprocess(h):
    def tfix(m):
        kind, title = m.group(1), m.group(2)
        k = kind.lower()
        if title.strip().lower() == k:
            title, tag = ADMON_TITLES.get(k, title), ""
        else:
            tag = f'<span class="kind">{KIND_TAGS[k]}</span>' if k in KIND_TAGS else ""
        return f'<div class="admonition {kind}">\n<p class="admonition-title">{tag}<span>{title}</span></p>'
    return re.sub(r'<div class="admonition (\w+)">\n<p class="admonition-title">(.*?)</p>', tfix, h)

def render_md(text, page_key, root, notes_used=None, en=False, book="hm"):
    notes_used = [] if notes_used is None else notes_used
    return postprocess(md_render(verse_breaks(inline_pre(text, page_key, root, notes_used, en, book))))

# ---------------------------------------------------------------- layout
def layout(title, body, root, active="", toc="", desc="", body_class="", book=None):
    side = sidebar(root, active, book)
    credit = " ".join(f'{BOOKS[k]["credit"]}；' for k in BOOKS)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Gloock&family=IBM+Plex+Mono:wght@400;500&family=Noto+Serif+SC:wght@400;700&family=Spectral:ital,wght@0,400;0,600;1,400&family=ZCOOL+XiaoWei&display=swap">
<title>{esc(title)}{' · ' + SITE_TITLE if title != SITE_TITLE else ''}</title>
<meta name="description" content="{esc(desc or SITE_SUB)}">
<link rel="icon" href="{root}static/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{root}static/css/site.css">
<script>try{{var t=localStorage.getItem('hm-theme');if(t)document.documentElement.dataset.theme=t;var m=localStorage.getItem('hm-mode');if(m)document.documentElement.dataset.mode=m;}}catch(e){{}}</script>
</head>
<body class="{body_class}" data-root="{root}">
<header class="topbar"><div class="topbar-row">
  <button class="icon-btn" id="nav-toggle" aria-label="目录">☰</button>
  <a class="brand" href="{root}index.html"><img src="{root}static/favicon.svg" alt=""><b>{SITE_TITLE}</b><i>Beckwith 1940 · 1951 · Malo 1903</i></a>
  <div class="search"><input id="q" type="search" placeholder="搜索：神名、地名、主题…" autocomplete="off"><div id="results" hidden></div></div>
  <div class="modes" role="group" aria-label="阅读模式">
    <button data-mode="zh" title="只看译文">中</button><button data-mode="both" title="中英对照">对照</button><button data-mode="en" title="只看原文">英</button>
  </div>
  <button class="icon-btn" id="theme-toggle" aria-label="切换明暗">◐</button>
</div><span class="niho" aria-hidden="true"></span></header>
<div class="shell">
<nav class="sidebar" id="sidebar">{side}</nav>
<main class="main"><article class="doc">{body}</article>
<footer class="foot"><span class="niho ink" aria-hidden="true"></span><p>底本：{credit}均为美国公有领域。译文、注释与专栏为本站撰写。<a href="{REPO}">GitHub</a></p></footer>
</main>
<aside class="outline">{toc}</aside>
</div>
<div id="tip" role="tooltip" hidden></div>
<script src="{root}static/js/site.js"></script>
</body>
</html>
"""

def book_nav(book, root, active):
    b = BOOKS[book]
    out, cur_part = [], None
    if book == "ku":
        out.append(f'<a class="side-link solo chant-link{" on" if active == "chant" else ""}" href="{root}kumulipo/chant.html">全诗对读 · 2102 行</a>')
    for n, c in ctx.book_chapters(book):
        if b.get("chant_chapter") == n: continue
        if c["part"] != cur_part and c["part"]:
            if cur_part not in (None, 0): out.append("</ol>")
            out.append(f'<div class="side-part">{b["parts"][c["part"]]}</div><ol class="side-list">')
            cur_part = c["part"]
        elif c["part"] == 0 and cur_part not in (None, 0):
            out.append("</ol>"); cur_part = 0
        st = "" if c["status"] != "source" else ' <span class="dot" title="尚未翻译，暂显示原文">·</span>'
        on = " on" if active == f"{book}{n}" else ""
        numbered = n not in b["special"]
        lab = f'<span class="n">{roman(n)}</span>' if numbered else ""
        a = f'<a class="side-link{on}" href="{root}{c["url"]}">{lab}{esc(c["title"])}{st}</a>'
        out.append(f"<li>{a}</li>" if c["part"] else a.replace('class="side-link', 'class="side-link solo', 1))
    if cur_part not in (None, 0): out.append("</ol>")
    return "".join(out)

def sidebar(root, active, book=None):
    out = ['<div class="side-sec"><a class="side-top' + (' on' if active == 'home' else '') + f'" href="{root}index.html">首页</a>'
           f'<a class="side-top{" on" if active == "about" else ""}" href="{root}about/index.html">体例与说明</a></div>']
    for k, b in BOOKS.items():
        is_open = " open" if (book == k or (book is None and k == "hm")) else ""
        out.append(f'<details class="side-sec book"{is_open}><summary class="side-h">《{b["title"]}》{b["year"]}</summary>{book_nav(k, root, active)}</details>')
    if ctx.essays:
        out.append('<div class="side-sec"><div class="side-h">专栏</div><ol class="side-list essays">')
        for slug, e in sorted(ctx.essays.items(), key=lambda kv: (kv[1]["order"], kv[0])):
            on = " on" if active == f"essay:{slug}" else ""
            out.append(f'<li><a class="side-link{on}" href="{root}{e["url"]}">{esc(e["title"])}</a></li>')
        out.append("</ol></div>")
    out.append('<div class="side-sec"><div class="side-h">工具</div>'
               f'<a class="side-link solo{" on" if active == "names" else ""}" href="{root}names.html">神名人名对照表</a>'
               f'<a class="side-link solo{" on" if active == "glossary" else ""}" href="{root}glossary.html">夏威夷语术语表</a></div>')
    return "\n".join(out)

def outline(html_s):
    items = re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', html_s)
    if len(items) < 2: return ""
    lis = "".join(f'<li class="l{lv}"><a href="#{i}">{re.sub("<[^>]+>", "", t)}</a></li>' for lv, i, t in items)
    return f'<div class="outline-h">本页</div><ol>{lis}</ol>'

def plain(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()

# ---------------------------------------------------------------- pages
def render_chapter(book, n, zh_path, src):
    root = "../"
    b = BOOKS[book]
    page_key = f"{b['prefix']}{n}"
    c = ctx.chapters[(book, n)]
    en_paras = src["paras"] if src else {}
    zh_notes, used, parts, covered = {}, [], [], set()
    R = lambda t, nu=None, en=False: render_md(t, page_key, root, nu, en, book)
    if zh_path:
        meta, body = parse_fm(zh_path.read_text(encoding="utf-8"))
        body = re.sub(r"(?<=\S)[ \t]*\{p:[0-9ivxl]+\}|\{p:[0-9ivxl]+\}[ \t]?", "", body)   # keep a line's leading indent
        seq, zh_notes = split_paras(body)
        for item in seq:
            if item[0] == "md":
                parts.append(R(item[1], used)); continue
            _, a, z, txt = item
            rng = range(a, z + 1)
            for k in rng:
                if k in covered: warn(f"{page_key}: ¶{k} 重复")
                if k not in en_paras: warn(f"{page_key}: ¶{k} 在英文底本中不存在")
                covered.add(k)
            en_html = "".join(f'<div class="en-p"><span class="en-n">{k}</span>' + R(en_paras.get(k, ""), [], True) + "</div>" for k in rng)
            lab = f"{a}" if a == z else f"{a}–{z}"
            parts.append(f'<section class="para" id="p{a}"><a class="pnum" href="#p{a}" title="点击显示/隐藏原文">¶{lab}</a>'
                         f'<div class="zh">{R(txt, used)}</div><div class="en" lang="en">{en_html}</div></section>')
        missing = sorted(set(en_paras) - covered)
        if missing:
            warn(f"{page_key}: 缺译段落 {compress(missing)}")
            if len(missing) > 0.5 * len(en_paras): c["status"] = "partial"
    else:
        for k in sorted(en_paras):
            parts.append(f'<section class="para only-en" id="p{k}"><a class="pnum" href="#p{k}">¶{k}</a>'
                         f'<div class="en" lang="en"><div class="en-p">{R(en_paras[k], [], True)}</div></div></section>')
    notes_html = ""
    src_notes = src["notes"] if src else {}
    beck = sorted({k for k in list(src_notes) + [k for k in zh_notes if not k.startswith("t")]}, key=lambda x: int(x))
    if beck:
        lis = []
        for k in beck:
            zh, en = zh_notes.get(k), src_notes.get(k, "")
            body = (R(zh) if zh else "") + (f'<div class="note-en" lang="en">{R(en, [], True)}</div>' if en else "")
            lis.append(f'<li id="fn-{k}" value="{k}">{body}</li>')
        if book == "malo":
            hint = "Emerson 的英译注释（1903），原书附在每章之后；正文中的上标数字对应 Malo 的小节编号。"
        else:
            hint = "Beckwith 的引文出处多用缩写，全称见" + xref_html("references" if book == "hm" else "ku-references", "参考文献", page_key, root) + "。"
        notes_html += f'<section class="notes" id="notes"><h2 id="yuan-zhu">{"Emerson 注" if book == "malo" else "原注"}</h2><p class="notes-hint">{hint}</p><ol>{"".join(lis)}</ol></section>'
    tns = sorted([k for k in zh_notes if k.startswith("t")], key=lambda x: int(x[1:]))
    if tns:
        notes_html += '<section class="notes tn-notes"><h2 id="yi-zhu">译注</h2><ol>' + "".join(f'<li id="fn-{k}">{R(zh_notes[k])}</li>' for k in tns) + "</ol></section>"
    banner = {"source": "本章译文尚在进行中，下面暂时显示英文原文。", "partial": "本章译文尚未完成，未译段落暂缺。"}.get(c["status"])
    banner = f'<div class="banner">{banner}</div>' if banner else ""
    big = f'<span class="roman" aria-hidden="true">{roman(n)}</span>' if n not in b["special"] else ""
    bookname = {"hm": "", "ku": "《库穆利波》 · ", "malo": "《夏威夷古俗》 · "}[book]
    head = (f'<header class="chap-head">{big}<div class="kicker">{bookname}{chap_label(book, n)} · {b["parts"].get(c["part"], "") or "附录"}</div>'
            f'<h1>{esc(c["title"])}</h1>'
            f'<div class="en-title" lang="en">{esc(c["en_title"])} · {"Malo" if book == "malo" else "Beckwith"} {b["year"]}, pp. {esc(src["meta"].get("pages", "") if src else "")}</div>'
            + (f'<p class="summary">{esc(c["summary"])}</p>' if c.get("summary") else "") +
            f'<div class="readhint">点击段首 <b>¶</b> 号可展开该段英文原文；右上角可切换「中 / 对照 / 英」。页边 <span class="pg">p.N</span> 标出原书页码。</div>'
            f'<div class="niho-pair" aria-hidden="true"><span class="niho"></span><span class="niho down ink"></span></div>'
            f'</header>{banner}')
    body = head + "\n".join(parts) + notes_html + pager(book, n, root)
    toc = outline(re.sub(r'<div class="en" lang="en">.*?</div></section>', "</section>", "\n".join(parts), flags=re.S) + notes_html)
    return layout(f"{bookname}{chap_label(book, n)} {c['title']}", body, root, active=f"{book}{n}", toc=toc,
                  desc=c.get("summary", ""), body_class="chapter", book=book)

def compress(nums):
    out, s = [], None
    for i, x in enumerate(nums):
        if s is None: s = x
        if i + 1 == len(nums) or nums[i + 1] != x + 1:
            out.append(f"{s}" if s == x else f"{s}-{x}"); s = None
    return ",".join(out)

def pager(book, n, root):
    keys = [k for k, _ in ctx.book_chapters(book)]
    i = keys.index(n)
    P = ctx.chapters.get((book, keys[i-1])) if i > 0 else None
    N = ctx.chapters.get((book, keys[i+1])) if i + 1 < len(keys) else None
    a = f'<a class="prev" href="{root}{P["url"]}"><small>上一章</small>{esc(P["title"])}</a>' if P else "<span></span>"
    z = f'<a class="next" href="{root}{N["url"]}"><small>下一章</small>{esc(N["title"])}</a>' if N else "<span></span>"
    return f'<nav class="pager">{a}{z}</nav>'

def chant_sections():
    raw = [dict(s) for s in ctx.haw.get("sections", [])]
    secs = []
    for s in raw:   # a heading with no lines of its own is followed by its subtitle: merge them
        if secs and secs[-1]["start"] is None:
            secs[-1]["start"] = s["start"]; secs[-1]["sub"] = s["title"]; continue
        secs.append(s)
    starts = [s["start"] for s in secs]
    for i, s in enumerate(secs):
        nxt = [x for x in starts[i+1:] if x and x > s["start"]]
        s["end"] = (nxt[0] - 1) if nxt else 2102
        s["idx"] = i + 1
    return [s for s in secs if s["end"] >= s["start"]]

def render_chant():
    root = "../"
    secs = chant_sections()
    body, toc_items, nzh = [], [], 0
    intro_f = ROOT / "content" / "kumulipo" / "chant" / "_intro.md"
    if intro_f.exists():
        body.append(render_md(parse_fm(intro_f.read_text(encoding="utf-8"))[1], "chant", root, book="ku"))
    lili_f = ROOT / "content" / "kumulipo" / "chant" / "_lili.md"
    if lili_f.exists():
        body.append('<details class="lili lili-intro"><summary>关于利留卡拉尼女王的 1897 年英译（各 wā 下的折叠栏）</summary>'
                    + render_md(parse_fm(lili_f.read_text(encoding="utf-8"))[1], "chant/lili", root, book="ku") + "</details>")
    for s in secs:
        sid = f"wa{s['idx']}"
        title = WA_ZH[s["idx"]] if s["idx"] < len(WA_ZH) else s["title"]
        body.append(f'<h2 id="{sid}">{title} <span class="haw-title" lang="haw">{esc(s["title"].title())}{(" " + esc(s["sub"].title())) if s.get("sub") else ""}</span>'
                    f'<small>第 {s["start"]}–{s["end"]} 行</small></h2>')
        toc_items.append((sid, title))
        f = ROOT / "content" / "kumulipo" / "chant" / f"wa{s['idx']:02d}.md"
        if f.exists():
            body.append(render_md(parse_fm(f.read_text(encoding="utf-8"))[1], f"chant/wa{s['idx']}", root, book="ku"))
        era = next((e for e in ctx.lili if e.get("wa") == s["idx"]), None)
        if era and era.get("verses"):
            vs = []
            for v in era["verses"]:
                rng = (f'<a href="#l{v["start"]}">第 {v["start"]}–{v["end"]} 行</a>' if v.get("start") else "（无对应行）")
                vs.append(f'<div class="lv"><div class="lv-h">{esc(v.get("label", ""))} · {rng}</div>'
                          + "".join(f'<div class="lv-l">{esc(l)}</div>' for l in v.get("lines", [])) + "</div>")
            body.append(f'<details class="lili"><summary>利留卡拉尼女王 1897 年英译 · {esc(era.get("title", ""))}</summary>'
                        f'<div class="lili-body" lang="en">{"".join(vs)}</div></details>')
        rows = []
        for k in range(s["start"], s["end"] + 1):
            h = ctx.haw["lines"].get(str(k))
            L = ctx.lines.get(str(k), {})
            if h is None:
                rows.append(f'<div class="cl gap" id="l{k}"><a class="ln" href="#l{k}">{k}</a><span class="haw">（底本缺此行）</span></div>'); continue
            if L.get("zh"): nzh += 1
            note = f'<div class="lnote">{render_md(L["note"], "chant", root, book="ku")}</div>' if L.get("note") else ""
            rows.append(f'<div class="cl" id="l{k}"><a class="ln" href="#l{k}">{k}</a>'
                        f'<span class="haw" lang="haw">{esc(h)}</span>'
                        f'<span class="lz">{esc(L.get("zh", ""))}</span>'
                        f'<span class="le" lang="en">{esc(re.sub(r"\[\^\d+\]", "", L.get("en", "")))}</span>{note}</div>')
        body.append(f'<div class="chant-table">{"".join(rows)}</div>')
    total = len(ctx.haw["lines"])
    head = (f'<header class="chap-head"><div class="kicker">《库穆利波》 · 附录一 · Kalākaua 刊本</div>'
            f'<h1>全诗对读</h1><div class="en-title" lang="en">He Kumulipo no Ka-‘ī-‘ī-mamao a ia Alapa‘i wahine</div>'
            f'<p class="summary">夏威夷语原文 {total} 行，逐行附中文译文；切换到「对照」或「英」可同时看 Beckwith 1951 年的英译。已译 {nzh} 行。</p>'
            f'<div class="readhint">行号可直接链接（如 <code>chant.html#l12</code>）。Beckwith 未逐行英译第十一、十二 wā 的长篇谱系，这些行只有原文与中文注音说明。</div>'
            f'<div class="niho-pair" aria-hidden="true"><span class="niho"></span><span class="niho down ink"></span></div></header>')
    toc = '<div class="outline-h">十六 wā</div><ol>' + "".join(f'<li class="l2"><a href="#{i}">{t}</a></li>' for i, t in toc_items) + "</ol>"
    h = head + "\n".join(body)
    return layout("《库穆利波》全诗对读", h, root, active="chant", toc=toc, desc="《库穆利波》夏威夷语原文、Beckwith 英译与中文逐行对读", body_class="chapter chant-page", book="ku"), plain(h)

def render_essay(slug, path):
    root = "../"
    meta, body = parse_fm(path.read_text(encoding="utf-8"))
    h = render_md(body, f"essays/{slug}", root)
    h = h.replace('<p class="admonition-title"><span>本章导读</span></p>', '<p class="admonition-title"><span>本文要点</span></p>')
    e = ctx.essays[slug]
    rel = [x.strip() for x in meta.get("chapters", "").split(",") if x.strip()]
    links = "、".join(xref_html(x if ":" in x else f"ch:{x}", None, slug, root) for x in rel)
    head = (f'<header class="chap-head"><div class="kicker">专栏</div><h1>{esc(e["title"])}</h1>'
            + (f'<p class="summary">{esc(e["summary"])}</p>' if e["summary"] else "")
            + (f'<div class="meta">相关章节：{links}</div>' if links else "") + "</header>")
    return layout(e["title"], head + h, root, active=f"essay:{slug}", toc=outline(h), desc=e["summary"], body_class="essay"), plain(h)

def names_page():
    root, cats = "", {}
    for k, v in sorted(ctx.names.items(), key=lambda kv: kv[0].lower().replace("‘", "")):
        cats.setdefault(v.get("cat", "其他"), []).append((k, v))
    order = ["神", "女神", "半神与英雄", "酋长", "人物", "地名", "其他"]
    body = ['<header class="chap-head"><div class="kicker">工具</div><h1>神名人名对照表</h1>'
            '<p class="summary">全站统一的译名。表中没有的名字，正文保留夏威夷语原拼写。夏威夷语中的 ‘（‘okina）表示喉塞音，与英文撇号不同。</p></header>']
    for cat in sorted(cats, key=lambda c: order.index(c) if c in order else 99):
        body.append(f'<h2 id="{slugify(cat)}">{esc(cat)}</h2><table class="names"><thead><tr><th>原名</th><th>译名</th><th>说明</th></tr></thead><tbody>')
        for k, v in cats[cat]:
            ch = "、".join(xref_html(f"ch:{x}", str(x), "names", root) for x in v.get("chapters", []))
            body.append(f'<tr id="n-{esc(slugify(k))}"><td lang="haw"><b>{esc(k)}</b>{("<br><small>" + esc(v["modern"]) + "</small>") if v.get("modern") else ""}</td><td>{esc(v.get("zh", ""))}</td><td>{esc(v.get("note", ""))}{(" <small>见 " + ch + "</small>") if ch else ""}</td></tr>')
        body.append("</tbody></table>")
    h = "\n".join(body)
    return layout("神名人名对照表", h, root, active="names", toc=outline(h))

def glossary_page():
    root = ""
    body = ['<header class="chap-head"><div class="kicker">工具</div><h1>夏威夷语术语表</h1>'
            '<p class="summary">正文中带虚线下划线的词悬停可见释义。拼写先列 Beckwith 的写法，括号内为现代正字法（带 ‘okina 与长音符 kahakō）。</p></header><dl class="gloss">']
    for k, g in sorted(ctx.gloss.items(), key=lambda kv: kv[0].lower().replace("‘", "")):
        mod = f' <span class="modern">（{esc(g["modern"])}）</span>' if g.get("modern") and g["modern"] != g.get("term", k) else ""
        see = ('<div class="see">相关：' + "、".join(xref_html(s, None, "glossary", root) for s in g["see"]) + "</div>") if g.get("see") else ""
        body.append(f'<dt id="g-{esc(slugify(k))}"><b lang="haw">{esc(g.get("term", k))}</b>{mod} <span class="zh">{esc(g.get("zh", ""))}</span></dt>'
                    f'<dd>{render_md(g.get("def", ""), "glossary", root)}{see}</dd>')
    body.append("</dl>")
    return layout("夏威夷语术语表", "\n".join(body), root, active="glossary")

def book_toc(book):
    b = BOOKS[book]
    cards = []
    for p in sorted(x for x in b["parts"] if x):
        items = [(n, c) for n, c in ctx.book_chapters(book) if c["part"] == p and n != b.get("chant_chapter")]
        if book == "ku" and p == 4:
            items = [(None, dict(url="kumulipo/chant.html", title="全诗对读（附录一 · Kalākaua 刊本）", en_title="The Kalakaua Text"))] + items
        lis = "".join(f'<li><a href="{c["url"]}"><span class="n">{roman(n) if n is not None and n not in b["special"] else ""}</span>{esc(c["title"])}</a><span class="en" lang="en">{esc(c["en_title"])}</span></li>' for n, c in items)
        cards.append(f'<section class="part-card"><h3>{b["parts"][p]}</h3><div class="en" lang="en">{b["parts_en"][p]}</div><ol>{lis}</ol></section>')
    solos = " · ".join(f'<a href="{c["url"]}">{esc(c["title"])}</a>' for n, c in ctx.book_chapters(book) if c["part"] == 0)
    return solos, "".join(cards)

def home_page():
    root = ""
    meta, body = parse_fm((ROOT / "content" / "_home.md").read_text(encoding="utf-8"))
    intro = render_md(body, "home", root)
    ess = "".join(f'<a class="essay-card" href="{e["url"]}"><b>{esc(e["title"])}</b><span>{esc(e["summary"])}</span></a>'
                  for slug, e in sorted(ctx.essays.items(), key=lambda kv: (kv[1]["order"], kv[0])))
    books_html = []
    for k, b in BOOKS.items():
        chs = ctx.book_chapters(k)
        done = sum(1 for _, c in chs if c["status"] not in ("source", "partial"))
        solos, cards = book_toc(k)
        books_html.append(f'<section class="book-block" id="book-{k}"><h2 id="mulu-{k}">《{b["title"]}》<span class="en" lang="en">{b["en_title"]} · {b["year"]}</span></h2>'
                          f'<p class="book-meta">已译 {done} / {len(chs)} 篇 · {solos}</p><div class="parts">{cards}</div></section>')
    h = (f'<header class="hero">'
         f'<p class="chant" lang="haw">O ke au i kahuli wela ka honua,<br>O ke au i kahuli lole ka lani</p>'
         f'<p class="chant-zh">{esc(ctx.lines.get("1", {}).get("zh") or "那时大地翻转而炽热")}，{esc(ctx.lines.get("2", {}).get("zh") or "那时诸天翻覆而倒转")}</p>'
         f'<div class="chant-src">《库穆利波》开篇 · <a href="kumulipo/chant.html#l1">Kumulipo 1–2</a></div>'
         f'<div class="niho-pair" aria-hidden="true"><span class="niho"></span><span class="niho down ink"></span></div>'
         f'<div class="kicker">Martha Warren Beckwith · Hawaiian Mythology 1940 · The Kumulipo 1951</div>'
         f'<h1>{SITE_TITLE}</h1><p class="sub">{SITE_SUB}</p>'
         f'<p class="progress">两本书 · 专栏 {len(ctx.essays)} 篇</p></header>'
         f'{intro}{"".join(books_html)}'
         + (f'<h2 id="zhuanlan">专栏</h2><div class="essays-grid">{ess}</div>' if ess else ""))
    return layout(SITE_TITLE, h, root, active="home", body_class="home")

def about_pages():
    out = []
    for f in sorted((ROOT / "content" / "about").glob("*.md")):
        meta, body = parse_fm(f.read_text(encoding="utf-8"))
        h = f'<header class="chap-head"><h1>{esc(meta.get("title", ""))}</h1></header>' + render_md(body, "about", "../")
        out.append((f"about/{f.stem}.html", layout(meta.get("title", ""), h, "../", active="about", toc=outline(h)), meta.get("title", ""), plain(h)))
    return out

# ---------------------------------------------------------------- build
def write(rel, text):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def build(check_only=False):
    global ctx
    WARN.clear()
    ctx = Ctx()
    zh_files = {}
    for k, b in BOOKS.items():
        meta_f = ROOT / b["src"] / "_chapters.json"
        if not meta_f.exists(): meta_f = ROOT / Path(b["src"]).parent / "_chapters.json"
        chmeta = json.load(open(meta_f, encoding="utf-8"))
        for f in (ROOT / b["zh"]).glob("*.md"):
            m = re.match(r"(\d+)", f.stem)
            if m: zh_files[(k, int(m.group(1)))] = f
        for cm in chmeta:
            n = cm["chapter"]
            zf = zh_files.get((k, n))
            meta = parse_fm(zf.read_text(encoding="utf-8"))[0] if zf else {}
            slug = zf.stem if zf else f"{n:02d}"
            url = "kumulipo/chant.html" if b.get("chant_chapter") == n else f"{b['url']}/{slug}.html"
            ctx.chapters[(k, n)] = dict(title=meta.get("title", cm["title"]), en_title=cm["title"], part=cm["part"], url=url,
                                        status=meta.get("status", "draft") if zf else "source", summary=meta.get("summary", ""))
    for f in sorted((ROOT / "content" / "essays").glob("*.md")):
        meta, _ = parse_fm(f.read_text(encoding="utf-8"))
        ctx.essays[f.stem] = dict(title=meta.get("title", f.stem), url=f"essays/{f.stem}.html",
                                  summary=meta.get("summary", ""), order=int(meta.get("order", 100)))
    search = []
    if not check_only:
        if OUT.exists(): shutil.rmtree(OUT)
        shutil.copytree(ROOT / "static", OUT / "static")
    for (k, n), c in sorted(ctx.chapters.items()):
        if BOOKS[k].get("chant_chapter") == n: continue
        page = render_chapter(k, n, zh_files.get((k, n)), load_source(k, n))
        if not check_only: write(c["url"], page)
        txt = plain(re.sub(r'<div class="en".*?</div></section>', "</section>", page.split('<article class="doc">')[1].split("</article>")[0], flags=re.S))
        pre = {"hm": "", "ku": "《库穆利波》", "malo": "《夏威夷古俗》"}[k]
        search.append(dict(t=f"{pre}{chap_label(k, n)} {c['title']}", e=c["en_title"], u=c["url"], s=c["summary"], x=txt[:20000]))
    page, txt = render_chant()
    if not check_only: write("kumulipo/chant.html", page)
    search.append(dict(t="《库穆利波》全诗对读", e="The Kumulipo", u="kumulipo/chant.html", s="夏威夷语原文与中文逐行对读", x=txt[:60000]))
    for slug in ctx.essays:
        page, txt = render_essay(slug, ROOT / "content" / "essays" / f"{slug}.md")
        if not check_only: write(ctx.essays[slug]["url"], page)
        search.append(dict(t="专栏：" + ctx.essays[slug]["title"], e="", u=ctx.essays[slug]["url"], s=ctx.essays[slug]["summary"], x=txt[:20000]))
    for rel, page, t, txt in about_pages():
        if not check_only: write(rel, page)
        search.append(dict(t=t, e="", u=rel, s="", x=txt[:5000]))
    for k, v in ctx.names.items():
        search.append(dict(t=f"{k} · {v.get('zh', '')}", e="对照表", u=f"names.html#n-{slugify(k)}", s=v.get("note", ""), x=""))
    for k, g in ctx.gloss.items():
        search.append(dict(t=f"{g.get('term', k)} · {g.get('zh', '')}", e="术语", u=f"glossary.html#g-{slugify(k)}", s=g.get("def", "")[:120], x=""))
    pages = [("names.html", names_page()), ("glossary.html", glossary_page()), ("index.html", home_page())]
    if not check_only:
        for rel, p in pages: write(rel, p)
        write("search.json", json.dumps(search, ensure_ascii=False, separators=(",", ":")))
        (OUT / ".nojekyll").write_text("")
    for w in WARN: print("warning:", w, file=sys.stderr)
    n_hm = len(ctx.book_chapters("hm")); n_ku = len(ctx.book_chapters("ku"))
    print(f"built {n_hm} + {n_ku} chapters, chant {len(ctx.haw['lines'])} lines ({sum(1 for v in ctx.lines.values() if v.get('zh'))} translated), "
          f"{len(ctx.essays)} essays, {len(ctx.gloss)} glossary terms; {len(WARN)} warnings")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--port", type=int, default=8767)
    a = ap.parse_args()
    build(check_only=a.check)
    if a.serve:
        import http.server, socketserver
        os.chdir(OUT)
        with socketserver.TCPServer(("", a.port), http.server.SimpleHTTPRequestHandler) as s:
            print(f"serving http://localhost:{a.port}"); s.serve_forever()
