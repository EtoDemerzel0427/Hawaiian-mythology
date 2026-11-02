<div align="center">

<img src="static/favicon.svg" width="72" alt="">

# 夏威夷神话注疏

**Martha Warren Beckwith《夏威夷神话》（*Hawaiian Mythology*, 1940）、《库穆利波》（*The Kumulipo*, 1951）与 David Malo《夏威夷古俗》（*Hawaiian Antiquities*, 1903）中文全译与注疏**

*O ke au i kahuli wela ka honua* — 那时大地翻转而炽热

[在线阅读](https://etodemerzel0427.github.io/Hawaiian-mythology/) · [体例说明](content/about/index.md) · [写作规范](AUTHORING.md)

</div>

---

Beckwith 的《夏威夷神话》是英文世界关于夏威夷口头传统最全面的综述：四十章，从诸神的来临、佩蕾与毛伊的神话、酋长谱系与远航传说，一直写到浪漫传奇，引用了数百种夏威夷语报纸、手稿与南太平洋民族志。它也以难读著称：名字长、头绪多，作者默认读者熟悉大量背景知识。

本站把全书译成中文，并在原文相应位置加注，帮助没有波利尼西亚背景的读者读懂它。

第二本是 Beckwith 1951 年的《库穆利波》：夏威夷王室的创世颂歌，2102 行，从深海的珊瑚虫一路唱到神、人与酋长的谱系。本站译出了她的全部导论、各章讨论与附录，并把颂歌做成逐行对读：夏威夷语原文、Beckwith 英译与中文三栏对照。

## 内容

| | |
|---|---|
| **全译** | 作者序、39 章正文与参考文献，约 39 万字；每段译文与英文原文一一对应 |
| **注释** | 900 余处就地注释，按类型着色：文化背景、夏威夷语构词、地理、比较神话、故事梗概、人物、今日视角 |
| **原文** | 英文底本由 1940 年初版的 OCR 整理，逐章对照扫描页人工校对，保留原书页码与全部原注 |
| **专栏** | 21 篇专题长文（含航海、刺青、藏骨、羽衣、莫纳克亚、1893 年政变、月相历法等写作参考）：怎样读这本书、夏威夷语入门、神与守护神与半神、kapu 制度、四大神、《库穆利波》、佩蕾史诗、毛伊、库克与洛诺之争、航海、草裙舞与吟诵、谱系与等级、巫术与冥界、文献来源 |
| **《库穆利波》** | 导言、27 章、结语与附录全译；全诗 2102 行逐行对读（夏威夷语 / 英译 / 中译），附行注与十六 wā 导读 |
| **《夏威夷古俗》** | David Malo 原书 67 章与 Emerson 注释全译：天地物产、等级与 kapu、神庙与丧葬、历法、竞技、古代诸王 |
| **工具** | 神名人名地名对照表、夏威夷语术语表（悬停释义）、全文搜索 |

阅读时可以在「中 / 对照 / 英」三种模式间切换，点击段首 ¶ 号展开单段原文，页边页码直接链接到原书扫描页。

## 本地运行

纯静态站点，Python 生成，无前端构建步骤。

```bash
pip install markdown
python3 build.py --serve      # http://localhost:8767
python3 build.py --check      # 只校验：段落对齐、术语、链接
```

推送到 `main` 后，GitHub Actions（`.github/workflows/pages.yml`）会自动构建并发布到 GitHub Pages（需在 Settings → Pages 中把 Source 设为 GitHub Actions）。

## 目录结构

```
build.py                 静态站点生成器
AUTHORING.md             翻译与注释规范
source/en/NN.md          英文底本（¶ 段落号、{p:N} 页码、[^N] 原注）
content/book/NN-*.md     中文译注，段落号与英文底本一一对应
content/essays/*.md      专栏
source/kumulipo/en/NN.md 《库穆利波》英文底本
content/kumulipo/        《库穆利波》中文译注；chant/ 为全诗对读页各 wā 导读
data/kumulipo/           夏威夷语原文（haw-lines.json）与逐行对读数据（lines/*.json）
tools/import_kumulipo.py 从 sacred-texts 的 HTML 导入《库穆利波》
source/malo/en/NN.md     《夏威夷古俗》英文底本（¶ = Malo 小节号，[^N] = Emerson 注）
content/malo/            《夏威夷古俗》中文译注
data/kumulipo/lili.json  利留卡拉尼女王 1897 年《库穆利波》英译（按诗节对齐行号）
content/about/           体例说明
data/names/*.json        译名表（构建时合并）
data/glossary/*.json     术语表（构建时合并）
tools/clean_ocr.py       从 archive.org 的 djvu.xml 生成英文底本初稿
static/                  样式、脚本、图标
```

## 参与

发现译文错误、OCR 错误或不准确的注释，欢迎提 issue 或 PR。所有章节目前为初稿（`status: draft`），校订后改为 `done`。改动前请先读 [AUTHORING.md](AUTHORING.md)，提交前运行 `python3 build.py --check`。

## 底本与版权

- 底本：Martha Warren Beckwith, *Hawaiian Mythology*, New Haven: Yale University Press, 1940。扫描与 OCR 来自 Internet Archive（[hawaiianmytholog00beck_0](https://archive.org/details/hawaiianmytholog00beck_0)）。
- 该版在美国出版且版权未续展，HathiTrust 版权审查结论为美国公有领域。Beckwith 卒于 1959 年，在“作者终身加七十年”的法域，原书于 2030 年进入公有领域。
- 1970 年重印本所附 Katharine Luomala 序言仍受版权保护，本站不收录。
- 《库穆利波》（University of Chicago Press, 1951）：一般认为其版权未续展，在美国属于公有领域；这一判断没有 HathiTrust 的正式审查结论。底本取自 sacred-texts 的人工校对本。1972 年影印本所附 Luomala 序言不收录。
- 《夏威夷古俗》（Malo 著，Emerson 译，1903）：美国公有领域。扫描与 OCR 来自 Internet Archive（hawaiianantiquit00malorich）。
- 利留卡拉尼女王《库穆利波》英译（1897）：美国公有领域。
- 本站撰写的译文、注释与专栏采用 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可；代码采用 MIT 许可。
