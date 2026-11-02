#!/usr/bin/env python3
"""夏威夷神话注疏 · 静态站点生成器

    python3 build.py              # 生成 _site/
    python3 build.py --serve      # 生成并在 http://localhost:8767 预览
    python3 build.py --check      # 只做校验（段落对齐、术语引用、交叉链接）

内容来源：
    source/en/NN.md       英文底本（Beckwith 1940，段落编号 ¶N，页码 {p:N}，原注 [^N]）
    content/book/NN-*.md  中文译注（与底本段落号一一对应）
    content/essays/*.md   专栏
    content/about/*.md    关于本站、体例
    data/names/*.json     人名神名地名译名表（构建时合并）
    data/glossary/*.json  术语表（构建时合并）
"""
import argparse, html, json, os, re, shutil, sys, glob, functools
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"
SCAN = "https://archive.org/details/hawaiianmytholog00beck_0/page/n{leaf}/mode/1up"
SITE_TITLE = "夏威夷神话注疏"
SITE_SUB = "Beckwith《Hawaiian Mythology》全译与导读"
REPO = "https://github.com/EtoDemerzel0427/hawaiian-mythology"

PARTS = {0: "", 1: "第一部 · 众神", 2: "第二部 · 神之子嗣", 3: "第三部 · 酋长", 4: "第四部 · 虚构故事中的英雄与恋人"}
PARTS_EN = {1: "Part One: The Gods", 2: "Part Two: Children of the Gods", 3: "Part Three: The Chiefs", 4: "Part Four: Heroes and Lovers in Fiction"}
CN_NUM = "零一二三四五六七八九"

WARN = []
def warn(msg):
    WARN.append(msg)

def cn_num(n):
    if n < 10: return CN_NUM[n]
    if n < 20: return "十" + (CN_NUM[n % 10] if n % 10 else "")
    return CN_NUM[n // 10] + "十" + (CN_NUM[n % 10] if n % 10 else "")

def roman(n):
    out = ""
    for v, r in ((40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v: out += r; n -= v
    return out

def chap_label(n):
    if n == 0: return "序"
    if n == 40: return "参考文献"
    return f"第{cn_num(n)}章"

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
    """Return (preamble, [(num, num_end, text)], notes{n:text}).
    A paragraph runs until the next ¶ marker or the next top-level block that is
    an admonition / heading / html block / footnote definition."""
    notes = {}
    def grab_note(m):
        notes[m.group(1)] = m.group(2).strip(); return ""
    body = re.sub(r"^\[\^(t?\d+)\]:[ \t]*((?:.*)(?:\n(?:    |\t).*)*)", grab_note, body, flags=re.M)
    blocks = re.split(r"\n\s*\n", body.strip())
    pre, paras, cur = [], [], None
    out = []   # sequence of ("md", text) / ("para", n, n2, text)
    for b in blocks:
        m = PARA_RE.match(b)
        if b.startswith(("    ", "\t")) and out:
            # indented continuation (admonition body / nested block) belongs to the previous block
            if out[-1][0] == "md": out[-1][1] += "\n\n" + b
            else: out[-1][3] += "\n\n" + b
            continue
        if m:
            cur = ["para", int(m.group(1)), int(m.group(2) or m.group(1)), b[m.end():]]
            out.append(cur)
        elif cur is not None and not re.match(r"^(!!!|\?\?\?|#|<|\{p:[0-9ivxl]+\}\s*$|---)", b) and not b.startswith("    "):
            cur[3] += "\n\n" + b
        else:
            cur = None
            out.append(["md", b])
    return out, notes

def load_source(n):
    f = ROOT / "source" / "en" / f"{n:02d}.md"
    if not f.exists(): return None
    meta, body = parse_fm(f.read_text(encoding="utf-8"))
    seq, notes = split_paras(body)
    paras = {}
    pages = []   # (para_num, page) for standalone page markers
    last = 0
    pending_page = None
    for item in seq:
        if item[0] == "para":
            txt = item[3]
            if pending_page:
                sep = "\n\n" if txt.lstrip().startswith((">", "#", "|", "```")) else " "
                txt = "{p:%s}" % pending_page + sep + txt; pending_page = None
            paras[item[1]] = txt; last = item[1]
        else:
            m = re.fullmatch(r"\{p:([0-9ivxl]+)\}", item[1].strip())
            if m: pending_page = m.group(1)
    return dict(meta=meta, paras=paras, notes=notes)

# ---------------------------------------------------------------- rendering
class Ctx:
    def __init__(self):
        self.names = load_json_dir("data/names/*.json")
        self.gloss = load_json_dir("data/glossary/*.json")
        self.pagemap = json.load(open(ROOT / "source" / "en" / "_pagemap.json"))
        self.chapters = {}   # n -> dict(title, en_title, url, status, summary)
        self.essays = {}     # slug -> dict(title, url, summary)
        self.used_gloss = set()

ctx = None

def md_render(text):
    return markdown.markdown(text, extensions=["extra", "admonition", "sane_lists", "toc"],
                             extension_configs={"toc": {"permalink": False, "slugify": slugify}},
                             output_format="html5")

def slugify(value, sep="-"):
    v = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", value).strip().lower()
    return re.sub(r"[\s]+", sep, v) or "s"

def verse_breaks(text):
    # consecutive "> " lines are verse: force a line break at the end of each
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.startswith(">") and i + 1 < len(lines) and lines[i + 1].startswith(">") and lines[i+1].strip() != ">" and l.strip() != ">":
            lines[i] = l.rstrip() + "  "
    return "\n".join(lines)

def scan_link(p):
    leaf = ctx.pagemap.get(str(p))
    if not leaf and str(p).isdigit():   # chapter-opening pages carry no running head; infer from neighbours
        nxt, prv = ctx.pagemap.get(str(int(p) + 1)), ctx.pagemap.get(str(int(p) - 1))
        leaf = (nxt - 1) if nxt else (prv + 1) if prv else None
    if not leaf: return f'<span class="pg">p.{p}</span>'
    return f'<a class="pg" href="{SCAN.format(leaf=leaf-1)}" target="_blank" rel="noopener" title="查看 1940 年原书第 {p} 页扫描">p.{p}</a>'

def inline_pre(text, page_key, root, notes_used, en=False):
    """Expand site macros before markdown. Returns markdown-safe text."""
    # protect code spans
    codes = []
    def keep(m): codes.append(m.group(0)); return f"\x00{len(codes)-1}\x00"
    text = re.sub(r"`[^`\n]+`", keep, text)
    text = re.sub(r"\{p:([0-9ivxl]+)\}", lambda m: scan_link(m.group(1)), text)
    def fn(m):
        k = m.group(1)
        notes_used.append(k)
        cls = "tn" if k.startswith("t") else "fn"
        label = "译注" if k.startswith("t") else k
        if k == "?": return '<sup class="fn unk" title="原注编号待核">?</sup>'
        return f'<sup class="{cls}"><a href="#{"en-" if en else ""}fn-{k}" id="{"en-" if en else ""}ref-{k}-{len(notes_used)}" data-fn="{k}">{label}</a></sup>'
    text = re.sub(r"\[\^(t?\d+|\?)\](?!:)", fn, text)
    def xref(m):
        target, label = m.group(1), m.group(2)
        return xref_html(target, label, page_key, root)
    text = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", xref, text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)
    return text

def xref_html(target, label, page_key, root):
    target = target.strip()
    if target.startswith("g:"):
        key = target[2:].strip()
        g = ctx.gloss.get(key) or ctx.gloss.get(key.lower())
        if not g:
            warn(f"{page_key}: 术语表无词条 [[g:{key}]]")
            return esc(label or key)
        ctx.used_gloss.add(key)
        shown = label or g.get("term", key)
        tip = g.get("zh", "") + "：" + g.get("def", "")
        return f'<a class="gl" href="{root}glossary.html#g-{esc(slugify(key))}" data-tip="{esc(tip)}">{esc(shown)}</a>'
    m = re.fullmatch(r"ch:(\d+)(?:#p?(\d+))?", target)
    if m:
        n = int(m.group(1)); p = m.group(2)
        c = ctx.chapters.get(n)
        if not c:
            warn(f"{page_key}: 无此章 [[{target}]]"); return esc(label or target)
        href = root + c["url"] + (f"#p{p}" if p else "")
        text = label or (f"{chap_label(n)}「{c['title']}」" + (f" ¶{p}" if p else ""))
        return f'<a class="xref" href="{href}" title="{esc(c["en_title"])}">{esc(text)}</a>'
    m = re.fullmatch(r"essays/([\w\-]+)(?:#([\w\-]+))?", target)
    if m:
        e = ctx.essays.get(m.group(1))
        if not e:
            warn(f"{page_key}: 无此专栏 [[{target}]]"); return esc(label or target)
        href = root + e["url"] + (f"#{m.group(2)}" if m.group(2) else "")
        return f'<a class="xref essay" href="{href}" title="{esc(e["summary"])}">{esc(label or "专栏：" + e["title"])}</a>'
    if target in ("names", "glossary", "references"):
        url = {"names": "names.html", "glossary": "glossary.html", "references": ctx.chapters.get(40, {}).get("url", "")}[target]
        dflt = {"names": "神名人名对照表", "glossary": "术语表", "references": "参考文献"}[target]
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
    # default admonition titles in Chinese
    def tfix(m):
        kind, title = m.group(1), m.group(2)
        k = kind.lower()
        if title.strip().lower() == k:
            title = ADMON_TITLES.get(k, title)
            tag = ""
        else:
            tag = f'<span class="kind">{KIND_TAGS[k]}</span>' if k in KIND_TAGS else ""
        return f'<div class="admonition {kind}">\n<p class="admonition-title">{tag}<span>{title}</span></p>'
    h = re.sub(r'<div class="admonition (\w+)">\n<p class="admonition-title">(.*?)</p>', tfix, h)
    return h

def render_md(text, page_key, root, notes_used=None, en=False):
    notes_used = [] if notes_used is None else notes_used
    return postprocess(md_render(verse_breaks(inline_pre(text, page_key, root, notes_used, en))))

# ---------------------------------------------------------------- layout
def layout(title, body, root, active="", toc="", desc="", body_class=""):
    side = sidebar(root, active)
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
  <a class="brand" href="{root}index.html"><img src="{root}static/favicon.svg" alt=""><b>{SITE_TITLE}</b><i>Hawaiian Mythology · 1940</i></a>
  <div class="search"><input id="q" type="search" placeholder="搜索：神名、地名、主题…" autocomplete="off"><div id="results" hidden></div></div>
  <div class="modes" role="group" aria-label="阅读模式">
    <button data-mode="zh" title="只看译文">中</button><button data-mode="both" title="中英对照">对照</button><button data-mode="en" title="只看原文">英</button>
  </div>
  <button class="icon-btn" id="theme-toggle" aria-label="切换明暗">◐</button>
</div><span class="niho" aria-hidden="true"></span></header>
<div class="shell">
<nav class="sidebar" id="sidebar">{side}</nav>
<main class="main"><article class="doc">{body}</article>
<footer class="foot"><span class="niho ink" aria-hidden="true"></span><p>底本：Martha Warren Beckwith, <i>Hawaiian Mythology</i>, Yale University Press, 1940（美国公有领域）。扫描本见 <a href="https://archive.org/details/hawaiianmytholog00beck_0">Internet Archive</a>。译文、注释与专栏为本站撰写。<a href="{REPO}">GitHub</a></p></footer>
</main>
<aside class="outline">{toc}</aside>
</div>
<div id="tip" role="tooltip" hidden></div>
<script src="{root}static/js/site.js"></script>
</body>
</html>
"""

def sidebar(root, active):
    out = ['<div class="side-sec"><a class="side-top' + (' on' if active == 'home' else '') + f'" href="{root}index.html">首页</a>'
           f'<a class="side-top{" on" if active == "about" else ""}" href="{root}about/index.html">体例与说明</a></div>']
    cur_part = None
    out.append('<div class="side-sec"><div class="side-h">原书全译</div>')
    for n in sorted(ctx.chapters):
        c = ctx.chapters[n]
        if c["part"] != cur_part and c["part"]:
            if cur_part is not None and cur_part != 0: out.append("</ol>")
            out.append(f'<div class="side-part">{PARTS[c["part"]]}</div><ol class="side-list">')
            cur_part = c["part"]
        elif c["part"] == 0 and cur_part not in (None, 0):
            out.append("</ol>"); cur_part = 0
        st = "" if c["status"] != "source" else ' <span class="dot" title="尚未翻译，暂显示原文">·</span>'
        on = " on" if active == f"ch{n}" else ""
        lab = "" if n in (0, 40) else f'<span class="n">{roman(n)}</span>'
        out.append(f'<li><a class="side-link{on}" href="{root}{c["url"]}">{lab}{esc(c["title"])}{st}</a></li>' if c["part"] else
                   f'<a class="side-link solo{on}" href="{root}{c["url"]}">{esc(c["title"])}{st}</a>')
    if cur_part not in (None, 0): out.append("</ol>")
    out.append("</div>")
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
def render_chapter(n, zh_path, src):
    root = "../"
    page_key = f"ch{n}"
    c = ctx.chapters[n]
    en_paras = src["paras"] if src else {}
    zh_notes, used = {}, []
    parts = []
    covered = set()
    if zh_path:
        meta, body = parse_fm(zh_path.read_text(encoding="utf-8"))
        body = re.sub(r"[ \t]*\{p:[0-9ivxl]+\}[ \t]*", "", body)   # page markers belong to the English side only
        seq, zh_notes = split_paras(body)
        for item in seq:
            if item[0] == "md":
                parts.append(render_md(item[1], page_key, root, used))
                continue
            _, a, b, txt = item
            rng = range(a, b + 1)
            for k in rng:
                if k in covered: warn(f"{page_key}: ¶{k} 重复")
                if k not in en_paras: warn(f"{page_key}: ¶{k} 在英文底本中不存在")
                covered.add(k)
            en_html = "".join(f'<div class="en-p"><span class="en-n">{k}</span>' + render_md(en_paras.get(k, ""), page_key, root, [], en=True) + "</div>" for k in rng)
            lab = f"{a}" if a == b else f"{a}–{b}"
            parts.append(f'<section class="para" id="p{a}">'
                         f'<a class="pnum" href="#p{a}" title="点击显示/隐藏原文">¶{lab}</a>'
                         f'<div class="zh">{render_md(txt, page_key, root, used)}</div>'
                         f'<div class="en" lang="en">{en_html}</div></section>')
        missing = sorted(set(en_paras) - covered)
        if missing:
            warn(f"{page_key}: 缺译段落 {compress(missing)}")
            if len(missing) > 0.5 * len(en_paras):
                c["status"] = "partial"
    else:
        meta = {}
        for k in sorted(en_paras):
            parts.append(f'<section class="para only-en" id="p{k}"><a class="pnum" href="#p{k}">¶{k}</a>'
                         f'<div class="en" lang="en"><div class="en-p">{render_md(en_paras[k], page_key, root, [], en=True)}</div></div></section>')
    # notes
    notes_html = ""
    src_notes = src["notes"] if src else {}
    beck = sorted({k for k in list(src_notes) + [k for k in zh_notes if not k.startswith("t")]}, key=lambda x: int(x))
    if beck:
        lis = []
        for k in beck:
            zh = zh_notes.get(k); en = src_notes.get(k, "")
            body = render_md(zh, page_key, root) if zh else ""
            body += f'<div class="note-en" lang="en">{render_md(en, page_key, root, [], en=True)}</div>' if en else ""
            lis.append(f'<li id="fn-{k}" value="{k}">{body}</li>')
        notes_html += f'<section class="notes" id="notes"><h2 id="yuan-zhu">原注</h2><p class="notes-hint">Beckwith 的引文出处多用缩写，全称见{xref_html("references", "参考文献", page_key, root)}。</p><ol>{"".join(lis)}</ol></section>'
    tns = sorted([k for k in zh_notes if k.startswith("t")], key=lambda x: int(x[1:]))
    if tns:
        lis = "".join(f'<li id="fn-{k}">{render_md(zh_notes[k], page_key, root)}</li>' for k in tns)
        notes_html += f'<section class="notes tn-notes"><h2 id="yi-zhu">译注</h2><ol>{lis}</ol></section>'
    title = c["title"]
    status_banner = ""
    if c["status"] == "source":
        status_banner = '<div class="banner">本章译文尚在进行中，下面暂时显示英文原文。</div>'
    elif c["status"] == "partial":
        status_banner = '<div class="banner">本章译文尚未完成，未译段落暂缺。</div>'
    big = f'<span class="roman" aria-hidden="true">{roman(n)}</span>' if n not in (0, 40) else ""
    head = (f'<header class="chap-head">{big}<div class="kicker">{chap_label(n)} · {PARTS.get(c["part"], "") or "附录"}</div>'
            f'<h1>{esc(title)}</h1>'
            f'<div class="en-title" lang="en">{esc(c["en_title"])} · Beckwith 1940, pp. {esc(src["meta"].get("pages", "") if src else "")}</div>'
            + (f'<p class="summary">{esc(c["summary"])}</p>' if c.get("summary") else "") +
            f'<div class="readhint">点击段首 <b>¶</b> 号可展开该段英文原文；右上角可切换「中 / 对照 / 英」。页边 <span class="pg">p.N</span> 链接到原书扫描页。</div>'
            f'<div class="niho-pair" aria-hidden="true"><span class="niho"></span><span class="niho down ink"></span></div>'
            f'</header>{status_banner}')
    body = head + "\n".join(parts) + notes_html + pager(n, root)
    return layout(f"{chap_label(n)} {title}", body, root, active=f"ch{n}", toc=outline(re.sub(r'<div class="en" lang="en">.*?</div></section>', "</section>", "\n".join(parts), flags=re.S) + notes_html), desc=c.get("summary", ""), body_class="chapter")

def compress(nums):
    out, s = [], None
    for i, x in enumerate(nums):
        if s is None: s = x
        if i + 1 == len(nums) or nums[i + 1] != x + 1:
            out.append(f"{s}" if s == x else f"{s}-{x}"); s = None
    return ",".join(out)

def pager(n, root):
    keys = sorted(ctx.chapters)
    i = keys.index(n)
    prev_ = ctx.chapters[keys[i-1]] if i > 0 else None
    next_ = ctx.chapters[keys[i+1]] if i + 1 < len(keys) else None
    a = f'<a class="prev" href="{root}{prev_["url"]}"><small>上一章</small>{esc(prev_["title"])}</a>' if prev_ else "<span></span>"
    b = f'<a class="next" href="{root}{next_["url"]}"><small>下一章</small>{esc(next_["title"])}</a>' if next_ else "<span></span>"
    return f'<nav class="pager">{a}{b}</nav>'

def render_essay(slug, path):
    root = "../"
    meta, body = parse_fm(path.read_text(encoding="utf-8"))
    used = []
    h = render_md(body, f"essays/{slug}", root, used)
    h = h.replace('<p class="admonition-title"><span>本章导读</span></p>', '<p class="admonition-title"><span>本文要点</span></p>')
    e = ctx.essays[slug]
    notes = ""
    _, zn = split_paras(body)
    head = (f'<header class="chap-head"><div class="kicker">专栏</div><h1>{esc(e["title"])}</h1>'
            + (f'<p class="summary">{esc(e["summary"])}</p>' if e["summary"] else "")
            + (f'<div class="meta">相关章节：' + "、".join(xref_html(f"ch:{x.strip()}", None, slug, root) for x in meta.get("chapters", "").split(",") if x.strip()) + "</div>" if meta.get("chapters") else "")
            + "</header>")
    return layout(e["title"], head + h, root, active=f"essay:{slug}", toc=outline(h), desc=e["summary"], body_class="essay"), plain(h)

def names_page():
    root = ""
    rows = []
    cats = {}
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
            '<p class="summary">正文中带虚线下划线的词悬停可见释义。拼写先列 Beckwith 1940 年的写法，括号内为现代正字法（带 ‘okina 与长音符 kahakō）。</p></header><dl class="gloss">']
    for k, g in sorted(ctx.gloss.items(), key=lambda kv: kv[0].lower().replace("‘", "")):
        mod = f' <span class="modern">（{esc(g["modern"])}）</span>' if g.get("modern") and g["modern"] != g.get("term", k) else ""
        see = ""
        if g.get("see"):
            see = '<div class="see">相关：' + "、".join(xref_html(s, None, "glossary", root) for s in g["see"]) + "</div>"
        body.append(f'<dt id="g-{esc(slugify(k))}"><b lang="haw">{esc(g.get("term", k))}</b>{mod} <span class="zh">{esc(g.get("zh", ""))}</span></dt>'
                    f'<dd>{render_md(g.get("def", ""), "glossary", root)}{see}</dd>')
    body.append("</dl>")
    return layout("夏威夷语术语表", "\n".join(body), root, active="glossary")

def home_page():
    root = ""
    meta, body = parse_fm((ROOT / "content" / "_home.md").read_text(encoding="utf-8"))
    intro = render_md(body, "home", root)
    cards = []
    for p in (1, 2, 3, 4):
        lis = "".join(f'<li><a href="{c["url"]}"><span class="n">{roman(n)}</span>{esc(c["title"])}</a><span class="en" lang="en">{esc(c["en_title"])}</span></li>'
                      for n, c in sorted(ctx.chapters.items()) if c["part"] == p)
        cards.append(f'<section class="part-card"><h3>{PARTS[p]}</h3><div class="en" lang="en">{PARTS_EN[p]}</div><ol>{lis}</ol></section>')
    ess = "".join(f'<a class="essay-card" href="{e["url"]}"><b>{esc(e["title"])}</b><span>{esc(e["summary"])}</span></a>'
                  for slug, e in sorted(ctx.essays.items(), key=lambda kv: (kv[1]["order"], kv[0])))
    done = sum(1 for c in ctx.chapters.values() if c["status"] not in ("source", "partial"))
    h = (f'<header class="hero">'
         f'<p class="chant" lang="haw">O ke au i kahuli wela ka honua,<br>O ke au i kahuli lole ka lani</p>'
         f'<p class="chant-zh">那时大地翻转而炽热，那时诸天翻覆而倒转</p>'
         f'<div class="chant-src">《库穆利波》开篇 · <a href="essays/kumulipo.html">Kumulipo 1–2</a></div>'
         f'<div class="niho-pair" aria-hidden="true"><span class="niho"></span><span class="niho down ink"></span></div>'
         f'<div class="kicker">Martha Warren Beckwith · Hawaiian Mythology · 1940</div>'
         f'<h1>{SITE_TITLE}</h1><p class="sub">{SITE_SUB}</p>'
         f'<p class="progress">已译 {done} / {len(ctx.chapters)} 篇 · 专栏 {len(ctx.essays)} 篇</p></header>'
         f'{intro}<h2 id="mulu">目录</h2>'
         f'<p><a href="{ctx.chapters[0]["url"]}">作者序</a> · <a href="{ctx.chapters[40]["url"]}">参考文献</a></p>'
         f'<div class="parts">{"".join(cards)}</div>'
         + (f'<h2 id="zhuanlan">专栏</h2><div class="essays-grid">{ess}</div>' if ess else ""))
    return layout(SITE_TITLE, h, root, active="home", body_class="home")

def about_pages():
    out = []
    for f in sorted((ROOT / "content" / "about").glob("*.md")):
        meta, body = parse_fm(f.read_text(encoding="utf-8"))
        h = render_md(body, "about", "../")
        h = f'<header class="chap-head"><h1>{esc(meta.get("title", ""))}</h1></header>' + h
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
    chmeta = json.load(open(ROOT / "source" / "en" / "_chapters.json", encoding="utf-8"))
    zh_files = {}
    for f in (ROOT / "content" / "book").glob("*.md"):
        m = re.match(r"(\d+)", f.stem)
        if m: zh_files[int(m.group(1))] = f
    for cm in chmeta:
        n = cm["chapter"]
        zf = zh_files.get(n)
        meta = parse_fm(zf.read_text(encoding="utf-8"))[0] if zf else {}
        slug = zf.stem if zf else f"{n:02d}"
        ctx.chapters[n] = dict(title=meta.get("title", cm["title"]), en_title=cm["title"], part=cm["part"],
                               url=f"book/{slug}.html", status=meta.get("status", "draft") if zf else "source",
                               summary=meta.get("summary", ""))
    for f in sorted((ROOT / "content" / "essays").glob("*.md")):
        meta, _ = parse_fm(f.read_text(encoding="utf-8"))
        ctx.essays[f.stem] = dict(title=meta.get("title", f.stem), url=f"essays/{f.stem}.html",
                                  summary=meta.get("summary", ""), order=int(meta.get("order", 100)))
    search = []
    if not check_only:
        if OUT.exists(): shutil.rmtree(OUT)
        shutil.copytree(ROOT / "static", OUT / "static")
    for n in sorted(ctx.chapters):
        src = load_source(n)
        page = render_chapter(n, zh_files.get(n), src)
        c = ctx.chapters[n]
        if not check_only: write(c["url"], page)
        txt = plain(re.sub(r'<div class="en".*?</div></section>', "</section>", page.split('<article class="doc">')[1].split("</article>")[0], flags=re.S))
        search.append(dict(t=f"{chap_label(n)} {c['title']}", e=c["en_title"], u=c["url"], s=c["summary"], x=txt[:20000]))
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
    if not check_only:
        write("names.html", names_page())
        write("glossary.html", glossary_page())
        write("index.html", home_page())
        write("search.json", json.dumps(search, ensure_ascii=False, separators=(",", ":")))
        (OUT / ".nojekyll").write_text("")
    else:
        names_page(); glossary_page(); home_page()
    for w in WARN: print("warning:", w, file=sys.stderr)
    print(f"built {len(ctx.chapters)} chapters, {len(ctx.essays)} essays, {len(ctx.gloss)} glossary terms; {len(WARN)} warnings")

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
