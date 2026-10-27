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

退出码：有 error 返回 1（CI 失败），仅有 warning 返回 0。
"""
import re
import subprocess
import sys
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
scan_files = sorted(ROOT.glob("*.html")) + [ROOT / "feed.xml", ROOT / "sitemap.xml"]
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

# ---------- 汇总 ----------
print("=" * 56)
print(f"文献总数: {len(entries)} | sitemap: {sitemap.count('paper?id=p')} 条 | 索引条目: {search.count(chr(123) + 's:')} 组")
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
