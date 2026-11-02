# 夏威夷神话注疏 · Hawaiian Mythology, Annotated

Martha Warren Beckwith《夏威夷神话》（*Hawaiian Mythology*, Yale University Press, 1940）的中文全译与注疏：逐段中英对照，在原文相应位置加文化背景、夏威夷语构词、地理、比较神话与今日研究的注释，另有一组专题专栏。

纯静态站点，Python 生成，无前端构建步骤。

## 本地运行

```bash
pip install markdown
python3 build.py --serve      # http://localhost:8767
python3 build.py --check      # 只校验：段落对齐、术语、链接
```

## 部署到 GitHub Pages

在仓库 Settings → Pages 里把 Source 设为 **GitHub Actions**。`.github/workflows/pages.yml` 会在每次推送 `main` 时构建并发布。

## 目录

```
build.py                 静态站点生成器
AUTHORING.md             写作与翻译规范
source/en/NN.md          英文底本（OCR 清理并人工校对；¶ 段落号、{p:N} 页码、[^N] 原注）
content/book/NN-*.md     中文译注，段落号与英文底本一一对应
content/essays/*.md      专栏
content/about/           体例说明
data/names/*.json        神名人名地名译名表（构建时合并）
data/glossary/*.json     夏威夷语术语表（构建时合并）
tools/clean_ocr.py       从 archive.org 的 djvu.xml 生成英文底本初稿
static/                  CSS / JS / 图标
```

## 底本与版权

底本为 Internet Archive 上的 1940 年初版扫描（[hawaiianmytholog00beck_0](https://archive.org/details/hawaiianmytholog00beck_0)）。该版在美国出版且版权未续展，HathiTrust 版权审查结论为公有领域。1970 年重印本所附 Katharine Luomala 序言仍受版权保护，不收录。Beckwith 卒于 1959 年：在“作者终身加七十年”的法域，原书于 2030 年进入公有领域。

本站撰写的译文、注释与专栏采用 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可；代码采用 MIT 许可。
