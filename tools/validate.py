#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aivc.news 站点数据校验器
=======================
每次 PR / push 自动运行（.github/workflows/validate.yml），在合并前拦截以下合并级错误：

  1. papers-data.js JS 语法错误（如合并边界缺逗号产生的 `}{`）
  2. 文献编号断档 / 重复（编号纪律）
  3. 文献条目字段不完整（g/t/a/v/d/doi/summary/background/method/results/limits/debate/takeaway/further）
  4. sitemap.xml 未覆盖全部文献
  5. further[] 交叉引用指向不存在的文献（重映射后最容易漏）
  6. 全站（*.html + feed.xml + sitemap.xml）paper 链接指向不存在的文献
  7. search.html 检索索引条目链接与文献标题/描述不匹配（指错文献，如重映射错位）
  8. papers.html 计数与实际文献数不符
  9. glossary-data.js 术语数据：语法、分类合法性、定义完整、术语名唯一、延伸文献引用有效
 10. sitemap.xml 未收录 glossary.html
 11. 全站页面主导航项与站点标准不一致（新增/漏改栏目）
 12. search.html 术语索引条目指向不存在的术语
 13. 文献标题精简索引必须覆盖全部文献
 14–15. 术语海报清单与海报页一致性
 16. HTML 内联 <script> 的 JS 语法（2026-10-31 事故后新增：见下方说明）
 20. 投稿口（kb-inbox）自洽：配置无凭据、脚本引入顺序、挂载点、清道规则、CSP 放行

退出码：有 error 返回 1（CI 失败），仅有 warning 返回 0。
"""
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def norm(s: str) -> str:
    """归一化：小写，仅保留字母数字与 CJK。"""
    return "".join(ch for ch in s.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def latin_probes(s: str, min_len: int = 5) -> list[str]:
    """提取探针词；连字符在归一化时会被剔除，故探针同样去连字符后再比对。"""
    out = []
    for t in re.findall(r"[a-z][a-z0-9\-]{2,}", s.lower()):
        t = t.replace("-", "")
        if len(t) >= min_len:
            out.append(t)
    return out


# ---------- 读取核心文件 ----------
papers_js = ROOT / "assets" / "papers-data.js"
src = papers_js.read_text(encoding="utf-8")

# ---------- 1. JS 语法 ----------
r = subprocess.run(
    ["node", "--check", str(papers_js)], capture_output=True, text=True
)
if r.returncode != 0:
    err(f"papers-data.js 语法错误: {r.stderr.strip()[:300]}")

# ---------- 2. 解析文献条目 ----------
entries = []
for m in re.finditer(
    r'\{\s*id:\s*"(p\d+)"\s*,\s*g:\s*"([^"]+)"\s*,\s*t:\s*"([^"]*)"', src
):
    entries.append({"id": m.group(1), "g": m.group(2), "t": m.group(3)})
ids = [e["id"] for e in entries]

if not ids:
    err("papers-data.js 未解析到任何文献条目")
else:
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        err(f"文献编号重复: {dup}")
    nums = {int(i[1:]) for i in ids}
    hi = max(nums)
    gaps = [f"p{n:02d}" for n in range(1, hi + 1) if n not in nums]
    if gaps:
        err(f"文献编号断档（应为 p01..p{hi:02d} 连续无断档）: {gaps}")

    # ---------- 3. 字段完整性 ----------
    starts = [m.start() for m in re.finditer(r'\{\s*id:\s*"p\d+"', src)]
    required = [
        "g:", "t:", "a:", "v:", "d:", "doi:", "summary:", "background:",
        "method:", "results:", "limits:", "debate:", "takeaway:", "further:",
    ]
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(src)
        chunk = src[s:e]
        pid = re.search(r'id:\s*"(p\d+)"', chunk).group(1)
        missing = [k for k in required if k not in chunk]
        if missing:
            err(f"{pid} 字段缺失: {missing}")
        haystack = norm(chunk)

        # ---------- 5. further[] 交叉引用 ----------
        fm = re.search(r"further:\s*\[([^\]]*)\]", chunk)
        if fm:
            for ref in re.findall(r'"(p\d+)"', fm.group(1)):
                if ref not in ids:
                    err(f"{pid} 的 further 引用不存在的文献: {ref}")

# ---------- 4. sitemap 覆盖 ----------
sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
for i in ids:
    if f"paper?id={i}" not in sitemap:
        err(f"sitemap.xml 缺少文献 {i} 的 /paper?id={i} 条目")

# ---------- 6. 全站 paper 链接有效性 ----------
# 2026-10-31 修复：此处原写作 ROOT / "feed.xml"（文件不存在，被下方 exists()
# 判断静默跳过），导致 feed.xml 的链接检查自建立起就是死代码——旧版从未真正
# 校验过订阅源。实际路径为 assets/feed.xml。
scan_files = sorted(ROOT.glob("*.html")) + [
    ROOT / "assets" / "feed.xml",
    ROOT / "sitemap.xml",
]
_missing = [f for f in scan_files if not f.exists()]
if _missing:
    # 显式报错而非静默跳过：路径一旦写错必须立刻暴露，不得再次退化为死代码
    for f in _missing:
        err(f"待检文件不存在，链接校验无法执行: {f.relative_to(ROOT)}")
for f in scan_files:
    if not f.exists():
        continue
    txt = f.read_text(encoding="utf-8")
    for m in re.finditer(r"paper(?:\.html)?\?id=(p\d+)", txt):
        if m.group(1) not in ids:
            err(f"{f.name} 链接到不存在的文献: {m.group(1)}")

# ---------- 7. 检索索引条目 ↔ 文献一致性 ----------
search = (ROOT / "search.html").read_text(encoding="utf-8")
if "const IDX=[" in search:
    blob = search[
        search.index("const IDX=[") : search.index("];", search.index("const IDX=["))
    ]
    # 每篇文献的全文 haystack（用于标题/描述比对）
    hay = {}
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(src)
        pid = re.search(r'id:\s*"(p\d+)"', src[s:e]).group(1)
        hay[pid] = norm(src[s:e])
    idx_links = re.findall(r'u:"(paper(?:\.html)?\?id=p\d+)"', blob)
    for m in re.finditer(
        r'\{s:"文献库",t:"([^"]+)",d:"([^"]*)",u:"paper(?:\.html)?\?id=(p\d+)"', blob
    ):
        t, d, pid = m.group(1), m.group(2), m.group(3)
        probes = latin_probes(t + " " + d)
        if not probes:
            continue
        hits = sum(1 for p in probes if p in hay.get(pid, ""))
        need = max(1, (len(probes) + 2) // 3)
        if hits < need:
            err(
                f"IDX 条目「{t[:36]}」指向 {pid}，但标题/描述关键词在该文献中几乎不存在"
                f"（命中 {hits}/{len(probes)}）——疑似重映射指错文献"
            )
        elif hits < len(probes):
            warn(f"IDX 条目「{t[:36]}」→ {pid} 仅部分命中（{hits}/{len(probes)}），请人工确认")
    for link in sorted(set(idx_links)):
        if idx_links.count(link) > 1:
            warn(f"IDX 中 {link} 被 {idx_links.count(link)} 条条目引用，请确认是否有重复条目")

# ---------- 8. papers.html 计数 ----------
papers_html = (ROOT / "papers.html").read_text(encoding="utf-8")
cm = re.search(r"共收录\s*<b>(\d+)</b>\s*篇", papers_html)
if cm and len(entries) and int(cm.group(1)) != len(entries):
    err(f"papers.html 计数为 {cm.group(1)}，与实际文献数 {len(entries)} 不符")

# ---------- 9. 术语表数据 ----------
glossary_terms: list[dict] = []
glossary_js = ROOT / "assets" / "glossary-data.js"
if glossary_js.exists():
    r = subprocess.run(["node", "--check", str(glossary_js)], capture_output=True, text=True)
    if r.returncode != 0:
        err(f"glossary-data.js 语法错误: {r.stderr.strip()[:300]}")
    gsrc = glossary_js.read_text(encoding="utf-8")
    VALID_CATS = {"core", "model", "task", "metric", "data", "bio", "org"}
    seen_names: dict[str, int] = {}
    for m in re.finditer(
        r'\{c:"(\w+)",t:"([^"]+)",z:"([^"]*)",a:"([^"]*)",\s*'
        r's:"([^"]*)",\s*b:"([^"]*)",\s*r:\[([^\]]*)\],k:"([^"]*)"\}',
        gsrc,
    ):
        c, t, z, a, s, b, refs, k = m.groups()
        glossary_terms.append({"c": c, "t": t})
        if c not in VALID_CATS:
            err(f"术语「{t}」分类非法: {c}（合法值 {sorted(VALID_CATS)}）")
        if len(s.strip()) < 8:
            err(f"术语「{t}」一句话定义缺失或过短")
        if len(b.strip()) < 30:
            err(f"术语「{t}」详解缺失或过短")
        if t in seen_names:
            err(f"术语名重复: {t}")
        seen_names[t] = seen_names.get(t, 0) + 1
        for ref in re.findall(r'"(p\d+)"', refs):
            if ref not in ids:
                err(f"术语「{t}」引用不存在的文献: {ref}")
    if not glossary_terms:
        err("glossary-data.js 未解析到任何术语条目")
    gh = (ROOT / "glossary.html").read_text(encoding="utf-8") if (ROOT / "glossary.html").exists() else ""
    gm = re.search(r"共收录\s*<b>(\d+)</b>\s*条", gh)
    if gm and int(gm.group(1)) != len(glossary_terms):
        err(f"glossary.html 声明 {gm.group(1)} 条术语，数据实际 {len(glossary_terms)} 条")
else:
    err("缺少 assets/glossary-data.js")

# ---------- 10. sitemap 覆盖术语表 ----------
if "glossary.html" not in sitemap:
    err("sitemap.xml 缺少 glossary.html 条目")

# ---------- 11. 全站导航一致性 ----------
# 导航拆成两层：主栏目行（.navlinks）+ 工具行（.navsub）。
# 两个列表都必须按上表顺序出现，页脚仍要求 12 项齐全（.fnav）。
NAV_EXPECT = [
    "index.html", "papers.html", "models.html", "companies.html", "china.html",
    "news.html", "benchmarks.html", "insight.html",
]
NAVSUB_EXPECT = ["glossary.html", "posters.html", "kb/index.html", "search.html", "about.html"]
NAV_ALL = NAV_EXPECT + NAVSUB_EXPECT

def _nav_links(html_txt, cls):
    m = re.search(r'<div class="%s"[^>]*>(.*?)</div>' % cls, html_txt, re.S)
    if not m:
        return None
    # kb/ 等子目录页用 ../ 相对路径引用根目录页面，归一化后再与标准列表比对；
    # 不做这一步，把检查范围扩到子目录就等于制造满屏误报。
    return [re.sub(r"^(?:\.\./)+", "", h)
            for h in re.findall(r'href="([^"#]+\.html)"', m.group(1))]

# 2026-11-01 加固（ops）：原先只扫根目录 13 页，kb/ 下 111 个页面（含全文库首页）
# 的导航没有任何机器护栏。它们现在同样带两层导航，理应受同一约束。
for f in sorted(p for p in ROOT.rglob("*.html") if ".git" not in p.parts):
    txt = f.read_text(encoding="utf-8")
    # 报错用仓库相对路径：子目录页与根页面可能同名（如 kb/index.html），只写文件名无法定位
    _loc = f.relative_to(ROOT)
    links = _nav_links(txt, "navlinks")
    if links is None:
        err(f"{_loc} 未找到主导航块（.navlinks）")
    elif links != NAV_EXPECT:
        err(f"{_loc} 主栏目导航与站点标准不一致: {links}")
    sublinks = _nav_links(txt, "navsub")
    if sublinks is None:
        err(f"{_loc} 未找到工具导航块（.navsub）")
    elif sublinks != NAVSUB_EXPECT:
        err(f"{_loc} 工具导航与站点标准不一致: {sublinks}")
    # 页脚导航顺序不设限（常按工具/栏目混排），但 13 项（8 主栏目 + 5 工具）必须一个不缺
    flinks = _nav_links(txt, "fnav")
    if flinks is None:
        err(f"{_loc} 缺少页脚导航（fnav）")
    elif sorted(flinks) != sorted(NAV_ALL):
        miss = [x for x in NAV_ALL if x not in flinks]
        extra = [x for x in flinks if x not in NAV_ALL]
        err(f"{_loc} 页脚导航与站点标准不一致（缺 {miss}，多 {extra}）")

# ---------- 12. 检索索引中的术语条目指向真实术语 ----------
if glossary_terms:
    known = {x["t"] for x in glossary_terms}
    for m in re.finditer(r'\{s:"术语表",t:"([^"]+)",d:"[^"]*",u:"glossary\.html\?q=([^"]*)"', search):
        if m.group(1) not in known:
            err(f"IDX 术语条目「{m.group(1)}」在 glossary-data.js 中不存在")

# ---------- 13. 文献标题精简索引必须覆盖全部文献 ----------
titles_js = ROOT / "assets" / "paper-titles.js"
if titles_js.exists():
    r = subprocess.run(["node", "--check", str(titles_js)], capture_output=True, text=True)
    if r.returncode != 0:
        err(f"paper-titles.js 语法错误: {r.stderr.strip()[:200]}")
    tsrc = titles_js.read_text(encoding="utf-8")
    covered = set(re.findall(r'"(p\d+)":\{', tsrc))
    missing = [i for i in ids if i not in covered]
    if missing:
        err(f"paper-titles.js 未覆盖文献（术语表延伸阅读会显示编号而非标题）: {missing}")
    if "var PAPER_TITLES=" not in tsrc:
        err("paper-titles.js 必须用 var 声明（const 不会挂到 window，术语页取不到标题）")
else:
    err("缺少 assets/paper-titles.js")

# ---------- 14. 术语海报清单 ----------
manifest_js = ROOT / "assets" / "posters-manifest.js"
poster_count = 0
if manifest_js.exists():
    r = subprocess.run(["node", "--check", str(manifest_js)], capture_output=True, text=True)
    if r.returncode != 0:
        err(f"posters-manifest.js 语法错误: {r.stderr.strip()[:200]}")
    msrc = manifest_js.read_text(encoding="utf-8")
    mm = re.search(r"window\.POSTER_MANIFEST=(\[.*?\]);", msrc, re.S)
    if not mm:
        err("posters-manifest.js 未解析到 POSTER_MANIFEST 数组")
    else:
        import json as _json
        try:
            manifest = _json.loads(mm.group(1))
        except Exception as e:
            manifest = []
            err(f"posters-manifest.js 解析失败: {e}")
        poster_count = len(manifest)
        if poster_count != len(glossary_terms):
            err(f"海报清单 {poster_count} 条，与术语数 {len(glossary_terms)} 不符")
        tnames = {x["t"] for x in glossary_terms}
        for p in manifest:
            if p.get("t") not in tnames:
                err(f"海报清单条目「{p.get('t')}」在 glossary-data.js 中不存在")
            for key in ("f", "u"):
                if not p.get(key):
                    err(f"海报清单条目「{p.get('t')}」缺字段 {key}")
        # 清单中的文件必须真实存在
        missing_files = []
        for p in manifest:
            for key in ("f",):
                fp = ROOT / p[key]
                if not fp.exists():
                    missing_files.append(p[key])
        if missing_files:
            err(f"海报清单引用的文件缺失（{len(missing_files)} 个）: {missing_files[:5]}")
        # 海报页与术语页链接必须一致
        for p in manifest:
            expect = "glossary.html?q=" + urllib.parse.quote(p["t"])
            if p.get("u") != expect:
                err(f"海报「{p.get('t')}」的词条链接不正确: {p.get('u')}")
else:
    err("缺少 assets/posters-manifest.js")

# ---------- 15. 海报页面与术语数据一致性 ----------
posters_html = ROOT / "posters.html"
if not posters_html.exists():
    err("缺少 posters.html（术语海报墙页面）")
else:
    ph = posters_html.read_text(encoding="utf-8")
    if "assets/posters-manifest.js" not in ph:
        err("posters.html 未加载 posters-manifest.js")
    if poster_count:
        mm2 = re.search(r"共\s*<b>(\d+)</b>\s*张", ph)
        if mm2 and int(mm2.group(1)) != poster_count:
            err(f"posters.html 声明海报数 {mm2.group(1)}，与清单 {poster_count} 不符")

# ---------- 16. HTML 内联脚本的 JS 语法 ----------
# 背景（2026-10-31 事故根因）：search.html 的 `const IDX=[...]` 在新增 p100–p103 条目时
# 漏写分隔逗号，整个内联脚本抛 SyntaxError，搜索页功能完全瘫痪；而旧版校验器只检查
# .js 文件、从不检查内联 <script>，该错误一路通过 CI 上了生产。故补此道防线。
#
# 2026-11-01 加固（ops）：原写作 ROOT.glob("*.html")，只覆盖仓库根目录的 13 个页面，
# kb/ 下 111 个全文库页面全部落在扫描范围之外——其中 kb/index.html 带 617 字符的
# 内联检索脚本，一旦语法出错，全文库检索整个失效而 CI 依然放行。改为全站 rglob
# 并排除 .git，与「内联脚本即代码」的判断保持一致：凡是页面里执行的脚本都要查。
import tempfile

for _f in sorted(p for p in ROOT.rglob("*.html") if ".git" not in p.parts):
    _txt = _f.read_text(encoding="utf-8")
    for _i, _body in enumerate(re.findall(r"<script[^>]*>(.*?)</script>", _txt, re.S)):
        if not _body.strip():
            continue
        with tempfile.NamedTemporaryFile(
            "w", suffix=".js", encoding="utf-8", delete=False
        ) as _tf:
            _tf.write(_body)
            _tmp = _tf.name
        try:
            _r2 = subprocess.run(["node", "--check", _tmp], capture_output=True, text=True)
        finally:
            Path(_tmp).unlink(missing_ok=True)
        if _r2.returncode != 0:
            _detail = [ln for ln in _r2.stderr.strip().split("\n") if ln.strip()][:3]
            err(
                f"{_f.relative_to(ROOT)} 内联 <script>[{_i}] 存在 JS 语法错误"
                f"（会导致整段页面脚本静默失效）: {' | '.join(_detail)}"
            )

# ---------- 17. feed lastBuildDate 与最新条目一致 ----------
# 背景（2026-10-31）：合并 #26 后 feed lastBuildDate 停在 10-28，而最新条目已是
# 10-30。订阅端据此判断「有没有更新」，日期不前进等于新文章推不出去。此项原先
# 靠人记得补（今日由总管手工发现），现改为机器强制。
_feed_path = ROOT / "assets" / "feed.xml"
if _feed_path.exists():
    _ftxt = _feed_path.read_text(encoding="utf-8")
    _lb = re.search(r"<lastBuildDate>([^<]+)</lastBuildDate>", _ftxt)
    _pubs = re.findall(r"<pubDate>([^<]+)</pubDate>", _ftxt)
    if _lb and _pubs:
        try:
            from email.utils import parsedate_to_datetime as _pdt

            _lb_d = _pdt(_lb.group(1)).date()
            _newest = max(_pdt(p).date() for p in _pubs)
            if _lb_d < _newest:
                err(
                    f"assets/feed.xml lastBuildDate={_lb_d} 早于最新条目 {_newest}，"
                    f"订阅端会认为无更新（请同步为 {_newest}）"
                )
        except (TypeError, ValueError):
            warn("assets/feed.xml 日期格式无法解析，跳过 lastBuildDate 一致性检查")
else:
    # 与第 6 项同一类防线：文件不在就必须报错。此前该分支只写 `if exists():` 没有
    # else，路径一旦写错（2026-10-31 实况：写成 ROOT/"feed.xml"）整段检查即退化为
    # 死代码，且不会有任何提示——第 6 项当时恰好也扫 feed.xml 才兜住，属侥幸。
    # 两道防线各自独立报警，任何一道失效都不能静默。
    err("缺少 assets/feed.xml，订阅源一致性检查无法执行")

# ---------- 18. 全文可达性数据（assets/fulltext-data.js） ----------
# 由 tools/fulltext.py 自动生成。这里只校验「数据自洽 + 链接形态合法」，
# 不做联网探测（联网巡检由 tools/fulltext.py --check 承担）。
_ft_js = ROOT / "assets" / "fulltext-data.js"
if not _ft_js.exists():
    err("缺少 assets/fulltext-data.js（运行 python3 tools/fulltext.py 生成）")
else:
    r = subprocess.run(["node", "--check", str(_ft_js)], capture_output=True, text=True)
    if r.returncode != 0:
        err(f"fulltext-data.js 语法错误: {r.stderr.strip()[:200]}")
    _ftsrc = _ft_js.read_text(encoding="utf-8")
    _ftrec = {
        m.group(1): m.group(2)
        for m in re.finditer(r"(p\d+):\s*\{(.*?)\},", _ftsrc, re.S)
    }
    _ftids = set(_ftrec)
    _paperids = set(ids)
    if _ftids - _paperids:
        err(f"fulltext-data.js 含不存在的文献 id: {sorted(_ftids - _paperids)}")
    if _paperids - _ftids:
        err(f"fulltext-data.js 漏掉文献: {sorted(_paperids - _ftids)}")
    _KINDS = {"pdf", "page", "closed"}
    _HOSTS = (
        "biorxiv.org", "medrxiv.org", "arxiv.org", "europepmc.org", "ncbi.nlm.nih.gov",
        "nature.com", "cell.com", "sciencedirect.com", "science.org", "springer.com",
        "wiley.com", "acs.org", "nih.gov", "escholarship.org", "elifesciences.org",
        "biomedcentral.com", "oup.com", "jci.org", "pnas.org", "plos.org", "doi.org",
    )
    for _pid, _body in sorted(_ftrec.items()):
        _k = re.search(r'k:"([^"]*)"', _body)
        _u = re.search(r'u:"([^"]*)"', _body)
        _t = re.search(r't:"([^"]*)"', _body)
        _k = _k.group(1) if _k else ""
        _u = _u.group(1) if _u else ""
        _t = _t.group(1) if _t else ""
        if _k not in _KINDS:
            err(f"fulltext-data.js {_pid} 的 k 值非法: {_k!r}（只允许 pdf/page/closed）")
        if _k == "closed":
            if _u:
                err(f"fulltext-data.js {_pid} 标为 closed 却又给了链接，语义矛盾")
        else:
            if not _u:
                err(f"fulltext-data.js {_pid} 标为 {_k} 但缺少 u 链接")
            elif not _u.startswith("https://"):
                err(f"fulltext-data.js {_pid} 链接非 https: {_u[:40]}")
            elif not any(h in _u for h in _HOSTS):
                err(f"fulltext-data.js {_pid} 链接域名不在白名单: {_u[:60]}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", _t or ""):
            err(f"fulltext-data.js {_pid} 的核验日期格式应为 YYYY-MM-DD，实为 {_t!r}")
    for _pg in ("paper.html", "papers.html"):
        if "fulltext-data.js" not in (ROOT / _pg).read_text(encoding="utf-8"):
            err(f"{_pg} 未引入 assets/fulltext-data.js，全文入口/角标不会显示")

# ---------- 19. 全文库（kb/）自洽 ----------
# kb/ 下每篇必须有对应的文献条目，索引与页面必须一一对应——否则站内会出现
# 「点进去 404」或「索引里有、页面没有」这类只有读者才会踩到的问题。
_kb_dir = ROOT / "kb"
_kb_idx = ROOT / "assets" / "kb-index.js"
if not _kb_dir.exists() or not (_kb_dir / "index.html").exists():
    err("缺少 kb/index.html（运行 python3 tools/build_kb.py 生成全文库）")
else:
    _kbpages = {p.stem for p in _kb_dir.glob("p*.html") if re.fullmatch(r"p\d+", p.stem)}
    _paperids = set(ids)
    if _kbpages - _paperids:
        err(f"kb/ 下存在无对应文献的页面: {sorted(_kbpages - _paperids)}")
    if not _kb_idx.exists():
        err("缺少 assets/kb-index.js（全文库索引，由 build_kb.py 生成）")
    else:
        r = subprocess.run(["node", "--check", str(_kb_idx)], capture_output=True, text=True)
        if r.returncode != 0:
            err(f"kb-index.js 语法错误: {r.stderr.strip()[:200]}")
        _kbsrc = _kb_idx.read_text(encoding="utf-8")
        _kbids = set(re.findall(r'"id":\s*"(p\d+)"', _kbsrc))
        if _kbids - _paperids:
            err(f"kb-index.js 含不存在的文献 id: {sorted(_kbids - _paperids)}")
        _missing_page = {i for i in _kbids if not (_kb_dir / f"{i}.html").exists()}
        if _missing_page:
            err(f"kb-index.js 引用的页面不存在: {sorted(_missing_page)}")
    # 每篇 kb 页必须能回到解读页与原文
    _bad_back = []
    for _f in _kb_dir.glob("p*.html"):
        _t = _f.read_text(encoding="utf-8")
        if "../paper.html?id=" not in _t:
            _bad_back.append(_f.name)
    if _bad_back:
        err(f"kb 页面缺少返回解读页的链接: {_bad_back[:5]}")
    # 导航入口由第 11 项（NAVSUB_EXPECT）统一强制，此处不重复校验

# ---------- 20. 投稿口（kb-inbox）自洽 ----------
# 背景（2026-10-31）：文献页上线「这篇的全文我也有」上传口，读者投来的原件只落在
# inbox/<批次>/ 分支（不部署），核验后由 tools/inbox.py 转成 kb/<id>.src.json 入库。
# 这条链路上任何一环断了，页面会出现「投了没反应」或「点进去 404」——只有读者才会踩到。
# 所以这里把四件事钉成机器检查：
_C_CFG = ROOT / "assets" / "kb-inbox-cfg.js"
_C_JS = ROOT / "assets" / "kb-inbox.js"
_C_DATA = ROOT / "assets" / "kb-inbox-data.js"
_C_PAPER = (ROOT / "paper.html").read_text(encoding="utf-8")

if not _C_JS.exists():
    err("缺少 assets/kb-inbox.js（文献页投稿口脚本）")
if not _C_DATA.exists():
    err("缺少 assets/kb-inbox-data.js（运行 python3 tools/publish_inbox.py 生成）")
else:
    r = subprocess.run(["node", "--check", str(_C_DATA)], capture_output=True, text=True)
    if r.returncode != 0:
        err(f"kb-inbox-data.js 语法错误: {r.stderr.strip()[:200]}")
    _dsrc = _C_DATA.read_text(encoding="utf-8")
    if "var KBINBOX_STATUS" not in _dsrc:
        err("kb-inbox-data.js 必须用 var 声明（const 不会挂到 window，投稿状态条取不到）")
    _paperids = set(ids)
    for m in re.finditer(r'"p":\s*"(p\d+)"', _dsrc):
        if m.group(1) not in _paperids:
            err(f"kb-inbox-data.js 的回执指向不存在的文献: {m.group(1)}")
    for m in re.finditer(r'"s":\s*"([^"]+)"', _dsrc):
        if m.group(1) not in ("done", "wait", "blocked"):
            err(f"kb-inbox-data.js 的状态值非法: {m.group(1)}（只允许 done/wait/blocked）")
    for m in re.finditer(r'"r":\s*"([^"]+)"', _dsrc):
        if not re.fullmatch(r"u\d{14}[a-z0-9]{0,4}", m.group(1)):
            err(f"kb-inbox-data.js 的投稿编号格式不对: {m.group(1)}（应为 u+14 位时间戳[+4 位随机]）")

if not _C_CFG.exists():
    err("缺少 assets/kb-inbox-cfg.js（投稿口开关与仓库名）")
else:
    r = subprocess.run(["node", "--check", str(_C_CFG)], capture_output=True, text=True)
    if r.returncode != 0:
        err(f"kb-inbox-cfg.js 语法错误: {r.stderr.strip()[:200]}")
    _csrc = _C_CFG.read_text(encoding="utf-8")
    # 前端只能放公开信息：出现任何形似令牌的串都是事故，不是配置
    if re.search(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", _csrc):
        err("kb-inbox-cfg.js 含疑似 GitHub 令牌 —— 前端配置里不得出现任何凭据（见 OPS.md §3.2.6）")
    if "enabled:" not in _csrc:
        err("kb-inbox-cfg.js 缺 enabled 开关（关掉时页面应退回邮件模式）")
    # 收件邮箱必须是真实地址——写错了读者点了发不出去，而页面上看不出来
    _m = re.search(r'reviewer:\s*"([^"]+)"', _csrc)
    if not _m:
        err("kb-inbox-cfg.js 缺 reviewer（收件邮箱）")
    elif not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", _m.group(1)):
        err(f"kb-inbox-cfg.js 的 reviewer 不是合法邮箱：{_m.group(1)}")
    # 邮箱通道不需要仓库名；留 `owner:` / `repo:` 说明旧通道没清干净
    for _k in ("owner", "repo"):
        if re.search(rf'{_k}:\s*"', _csrc):
            err(f"kb-inbox-cfg.js 仍保留 {_k} —— 投稿口已改为邮件通道，仓库配置应删除")

# paper.html 必须按序引入三件套并留挂载点，顺序错了脚本跑不起来（无报错的静默失效）
if "kb-inbox-cfg.js" not in _C_PAPER:
    err("paper.html 未引入 assets/kb-inbox-cfg.js（投稿口不会出现）")
if "kb-inbox.js" not in _C_PAPER:
    err("paper.html 未引入 assets/kb-inbox.js")
if 'id="kv"' not in _C_PAPER:
    err("paper.html 缺少投稿口挂载点 <div id=\"kv\">")
_ord = [_C_PAPER.find("papers-data.js"), _C_PAPER.find("kb-inbox-cfg.js"),
        _C_PAPER.find("kb-inbox-data.js"), _C_PAPER.find("kb-inbox.js")]
if all(x >= 0 for x in _ord) and _ord != sorted(_ord):
    err("paper.html 脚本引入顺序不对：需要 papers-data → kb-inbox-cfg → kb-inbox-data → kb-inbox")

# 投稿口走邮件（mailto:），页面不该有任何跨域请求。CSP 里若还留着 API 域，
# 说明代码里有旧通道的残留——那意味着又有人在往前端塞网络凭据的路子。
_hdr = ROOT / "_headers"
if _hdr.exists():
    _htxt = _hdr.read_text(encoding="utf-8")
    if "api.github.com" in _htxt:
        err("_headers 仍放行 api.github.com —— 投稿口已改为邮件通道，页面不该发跨域请求")
else:
    err("缺少 _headers（安全响应头）")

# 收件箱路径的 Git 层隔离：没有这条规则，原文里的注释定界符能随文件进工作区
_ga = ROOT / ".gitattributes"
if not _ga.exists() or "filter=kbscrub" not in _ga.read_text(encoding="utf-8"):
    err(".gitattributes 缺少收件箱清道规则（inbox/** filter=kbscrub），原文可注入 HTML 注释")

# 隔离区必须逐条在 .gitignore 里：原文只该存在于运维机器上，不该有机会被误提交
_gi = ROOT / ".gitignore"
_gi_lines = (_gi.read_text(encoding="utf-8").splitlines() if _gi.exists() else [])
for _need in ("inbox/", "drops/"):
    if _need not in _gi_lines:
        err(f".gitignore 未忽略 {_need}（收件原文可能被误提交）")

# 前端脚本里出现令牌 = 把写权限公开在网页源码里（本功能第一版正因此被密钥扫描拦下）
_JS_TOK = re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")
for _js in (ROOT / "assets").glob("kb-inbox*.js"):
    _m = _JS_TOK.search(_js.read_text(encoding="utf-8"))
    if _m:
        err(f"{_js.name} 含 GitHub 令牌 —— 前端不得出现任何凭据（见 OPS.md §3.2.6）")

# 投稿入库的页面必须与内联进来的正文一致：.src.json 存在的篇章，kb/ 页里得真有正文
for _sf in (ROOT / "kb").glob("p*.src.json"):
    _pid = _sf.name.split(".")[0]
    if _pid not in _paperids:
        err(f"kb/{_pid}.src.json 对应的文献不存在")
    elif not (ROOT / "kb" / f"{_pid}.html").exists():
        err(f"kb/{_pid}.src.json 存在但未生成 kb/{_pid}.html（重跑 tools/build_kb.py）")
    elif "kb-chars:" not in (ROOT / "kb" / f"{_pid}.html").read_text(encoding="utf-8"):
        err(f"kb/{_pid}.html 未渲染出正文（投稿已入库但页面为空）")

# ---------- 汇总 ----------
print("=" * 56)
print(
    f"文献总数: {len(entries)} | 术语总数: {len(glossary_terms)} | "
    f"海报: {poster_count} 张 | sitemap: {sitemap.count('paper?id=p')} 条 | "
    f"索引条目: {search.count(chr(123) + 's:')} 组"
)
if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for w in warnings:
        print(f"  - {w}")
if errors:
    print(f"\n❌ ERRORS ({len(errors)}):")
    for e in errors:
        print(f"  - {e}")
    print("\n校验未通过：请修复后再合并。")
    sys.exit(1)
print("\n✅ 全部校验通过")
sys.exit(0)
