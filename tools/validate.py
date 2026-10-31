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
NAV_EXPECT = [
    "index.html", "papers.html", "models.html", "companies.html", "china.html",
    "news.html", "benchmarks.html", "insight.html", "glossary.html",
    "posters.html", "search.html", "about.html",
]
for f in sorted(ROOT.glob("*.html")):
    txt = f.read_text(encoding="utf-8")
    nm = re.search(r'<div class="navlinks"[^>]*>(.*?)</div>', txt, re.S)
    if not nm:
        err(f"{f.name} 未找到主导航块")
        continue
    links = re.findall(r'href="([^"#]+\.html)"', nm.group(1))
    if links != NAV_EXPECT:
        err(f"{f.name} 主导航与站点标准不一致: {links}")
    # 页脚导航同样必须完整（新增栏目时最容易漏掉页脚）
    fm = re.search(r'<div class="fnav">(.*?)</div>', txt, re.S)
    if not fm:
        err(f"{f.name} 缺少页脚导航（fnav）")
    else:
        flinks = re.findall(r'href="([^"#]+\.html)"', fm.group(1))
        if flinks != NAV_EXPECT:
            err(f"{f.name} 页脚导航与站点标准不一致: {flinks}")

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
import tempfile

for _f in sorted(ROOT.glob("*.html")):
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
                f"{_f.name} 内联 <script>[{_i}] 存在 JS 语法错误"
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
