#!/usr/bin/env python3
"""构建站内全文知识库（kb/）。

把开放获取论文的结构化全文（JATS XML）转成站内可读页面，并生成检索索引。
数据源：Europe PMC fullTextXML（OA 子集，许可明确）+ arXiv。

版权策略（OPS.md §3.2.5 的落地）：
  只转录许可明确的开放获取文献（CC BY / CC0 / CC BY-NC / CC BY-NC-ND）。
  格式转换不改动文字；每篇页面顶部标注许可、署名与原文地址。
  许可不明或闭源的，不转录正文，只给摘要与章节大纲，引导到原文。

用法:
    python3 tools/build_kb.py              # 抓取 + 解析 + 生成
    python3 tools/build_kb.py --no-fetch   # 只用本地缓存（tools/.kb-cache/）
    python3 tools/build_kb.py --only p01,p02
"""

import argparse
import concurrent.futures as cf
import glob
import html
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / ".kb-cache"
KB = ROOT / "kb"
ASSETS = ROOT / "assets"
UA = "aivc-insight-kb/1.0 (https://aivc.news; bot@aivc.news)"

# 允许站内转录的许可（本站无广告、无付费，属非商业用途）
ALLOW_LIC = {"CC BY", "CC0 1.0", "CC BY-NC", "CC BY-NC-ND"}

# JATS 里章节标题常是全大写，直接渲染可读性差。只对通用章节名做映射，
# 不做通用 Title Case——否则 AVICs / scRNA-seq 这类专有写法会被改坏。
SEC_NAMES = {
    "INTRODUCTION": "Introduction", "BACKGROUND": "Background",
    "METHODS": "Methods", "METHOD": "Method",
    "MATERIALS AND METHODS": "Materials and Methods",
    "RESULTS": "Results", "RESULTS AND DISCUSSION": "Results and Discussion",
    "DISCUSSION": "Discussion", "CONCLUSIONS": "Conclusions", "CONCLUSION": "Conclusion",
    "SUMMARY": "Summary", "ABSTRACT": "Abstract",
    "REFERENCES": "References", "ACKNOWLEDGMENTS": "Acknowledgments",
    "ACKNOWLEDGEMENTS": "Acknowledgements",
    "LIMITATIONS": "Limitations", "OUTLOOK": "Outlook",
    "DATA AVAILABILITY": "Data Availability", "CODE AVAILABILITY": "Code Availability",
    "SUPPLEMENTARY MATERIAL": "Supplementary Material",
}


# 全大写章节标题做 Title Case 时，这些缩写必须原样保留，否则 AIVC 会变成 Aivc
ABBR = {
    "AIVC", "AIVCS", "UR", "URS", "AI", "ML", "DL", "DNA", "RNA", "MRNA", "SCRNA",
    "ATAC", "GPT", "LLM", "GNN", "VAE", "PCA", "UMAP", "TSNE", "API", "DOI", "PDF",
    "GPU", "CPU", "SNP", "GWAS", "KO", "WT", "FDR", "AUC", "ROC", "TCGA", "GEO",
    "HCA", "CRISPR", "COVID", "SARS", "MHC", "NLP", "TBD", "PII", "SOTA", "OOD",
}
SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on",
         "or", "the", "to", "with", "via", "vs", "into", "over", "under"}


def norm_heading(h):
    h = h.strip()
    key = re.sub(r"\s+", " ", h).upper()
    if key in SEC_NAMES:
        return SEC_NAMES[key]
    # 只处理「全大写且两词以上」的标题；混合大小写的原样保留（多半是作者有意写的）
    if not (h.isupper() and len(h) > 6 and len(h.split()) >= 2):
        return h
    out = []
    for i, w in enumerate(h.split()):
        core = re.sub(r"[^A-Za-z0-9]", "", w).upper()
        if core in ABBR or (len(core) <= 5 and core.isdigit() is False and core.endswith("S") and core[:-1] in ABBR):
            out.append(w)
        elif i > 0 and core.lower() in SMALL:
            out.append(w.lower())
        else:
            out.append(w.capitalize())
    return " ".join(out)


GROUP = {
    "g1": "纲领与路线图", "g2": "单细胞基础模型", "g3": "扰动响应预测", "g4": "批评与基准",
    "g5": "关键数据集", "g6": "经典基线方法", "g7": "空间与多组学", "g8": "衰老交叉",
}


# ---------- 元数据处理 ----------
def load_papers():
    src = (ASSETS / "papers-data.js").read_text(encoding="utf-8")
    pos = [(m.group(1), m.start()) for m in re.finditer(r'\{\s*id:\s*"(p\d+)"', src)]
    out = []
    for i, (pid, p) in enumerate(pos):
        end = pos[i + 1][1] if i + 1 < len(pos) else len(src)
        b = src[p:end]
        g = re.search(r'g:\s*"([^"]+)"', b)
        t = re.search(r't:\s*"([^"]*)"', b)
        a = re.search(r'a:\s*"([^"]*)"', b)
        v = re.search(r'v:\s*"([^"]*)"', b)
        d = re.search(r'd:\s*"([^"]*)"', b)
        doi = re.search(r'doi:\s*"([^"]+)"', b)
        sm = re.search(r'summary:\s*"([^"]*)"', b)
        out.append({
            "id": pid, "g": g.group(1) if g else "g1",
            "t": html.unescape(t.group(1)) if t else "",
            "a": html.unescape(a.group(1)) if a else "",
            "v": html.unescape(v.group(1)) if v else "",
            "d": html.unescape(d.group(1)) if d else "",
            "doi": doi.group(1) if doi else "",
            "summary": html.unescape(sm.group(1)) if sm else "",
        })
    return out


def load_route():
    f = ROOT / "tools" / ".kb-route.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def load_uploads():
    """投稿口入库的结果（kb/<id>.src.json，由 tools/inbox.py 写出）。

    外链抓不到的文献（bioRxiv 全站 403 的那批）、以及订阅期刊但作者/读者提供了
    合法全文的，走这条路进库。结构直接是 build_kb 的中间表示，渲染完全共用。
    """
    out = {}
    for f in KB.glob("*.src.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        out[f.name.split(".")[0]] = d
    return out


def write_uploaded(pid):
    """把一篇投稿入库落到 kb/ 与索引，不动其他文件。"""
    ups = load_uploads()
    if pid not in ups:
        return False
    d = ups[pid]
    meta, full = d["meta"], d["full"]
    (KB / f"{pid}.html").write_text(paper_page(meta, meta, full), encoding="utf-8")
    idx_page(load_papers(), all_parsed(), load_route())
    return True


def all_parsed():
    """已入库全文的统一视图：外链抓取的缓存 + 投稿口送来的。"""
    out = {}
    for p in load_papers():
        f = CACHE / f"{p['id']}.xml"
        if f.exists():
            try:
                out[p["id"]] = parse_xml(f)
            except Exception:
                pass
    for pid, d in load_uploads().items():
        # 投稿版优先：它是人工确认过许可与归属的
        if d.get("full", {}).get("chars", 0) > 500:
            out[pid] = d["full"]
    return out


def idx_page(papers, parsed, route):
    """写 assets/kb-index.js（文献页据此显示「读站内全文」）。"""
    idx = []
    for p in papers:
        f = parsed.get(p["id"])
        if not (f and f.get("lic") in ALLOW_LIC and f.get("chars", 0) > 500):
            continue
        idx.append({
            "id": p["id"], "t": p["t"], "a": p["a"], "v": p["v"], "d": p["d"],
            "g": GROUP.get(p["g"], ""), "n": f["chars"],
            "s": [s["h"] for s in f["secs"] if s["h"]],
        })
    (ASSETS / "kb-index.js").write_text(
        "// 全文库索引 —— 由 tools/build_kb.py 生成\nconst KBINDEX = "
        + json.dumps(idx, ensure_ascii=False, indent=0) + ";\n", encoding="utf-8")
    return len(idx)


def resolve_route(papers):
    """确定每篇的全文来源：epmc（PMC 全文）| arxiv | none。"""
    route = {}
    for p in papers:
        doi = p["doi"]
        if doi.startswith("10.48550/arXiv."):
            route[p["id"]] = {"route": "arxiv"}
    pending = [p for p in papers if p["id"] not in route]
    if not pending:
        return route

    def q(p):
        import urllib.parse
        u = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query="
             + urllib.parse.quote(f'DOI:"{p["doi"]}"')
             + "&format=json&resultType=core&pageSize=1")
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception:
            return p["id"], {"route": "none"}
        res = (d.get("resultList") or {}).get("result") or []
        if res and res[0].get("pmcid") and str(res[0].get("inEPMC", "")).upper() == "Y":
            return p["id"], {"route": "epmc", "pmcid": res[0]["pmcid"]}
        return p["id"], {"route": "none"}

    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for pid, v in ex.map(q, pending):
            route[pid] = v
    return route


# ---------- 抓取 ----------
def fetch_xml(item):
    pid, pmcid = item
    dest = CACHE / f"{pid}.xml"
    if dest.exists() and dest.stat().st_size > 2000:
        return pid, "cached"
    u = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    for attempt in range(3):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                data = r.read()
            if len(data) < 2000:
                raise ValueError("响应过短")
            dest.write_bytes(data)
            return pid, "ok"
        except Exception as e:
            if attempt == 2:
                return pid, f"{type(e).__name__}:{getattr(e, 'code', '')}"
    return pid, "?"


# ---------- 解析 JATS ----------
def _text(el):
    if el is None:
        return ""
    parts = []

    def walk(e):
        if e.text:
            parts.append(e.text)
        for ch in e:
            tag = ch.tag.split("}")[-1]
            if tag == "xref":
                pass
            elif tag in ("inline-formula", "disp-formula"):
                alt = ch.find("alternatives")
                if alt is not None:
                    walk(alt)
            elif tag in ("graphic", "object-id", "supplementary-material"):
                pass
            else:
                walk(ch)
            if ch.tail:
                parts.append(ch.tail)

    walk(el)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _license(root):
    perms = root.find(".//permissions")
    if perms is None:
        return None, None
    blob = ET.tostring(perms, encoding="unicode")
    m = re.search(r"creativecommons\.org/(licenses|publicdomain)/([a-z0-9\-]+)", blob)
    if not m:
        return None, None
    kind, code = m.group(1), m.group(2)
    url = f"https://creativecommons.org/{kind}/{code}/"
    if kind == "publicdomain":
        return ("CC0 1.0" if code == "zero" else f"PD {code}"), url
    return "CC " + code.upper(), url


def parse_xml(path):
    pid = path.stem
    root = ET.parse(path).getroot()

    def q(tag):
        return root.find(f".//{tag}")

    title = _text(q("article-title"))
    journal = _text(q("journal-title")) or _text(q("journal-title-group"))
    authors = []
    for c in root.findall(".//contrib-group/contrib"):
        n = c.find("name")
        if n is None:
            continue
        sn = _text(n.find("surname"))
        gn = _text(n.find("given-names"))
        if sn:
            authors.append(f"{sn} {gn}".strip())
    year = ""
    for pd in root.findall(".//pub-date"):
        y = pd.find("year")
        if y is not None and y.text:
            year = y.text.strip()
            break
    doi = ""
    for aid in root.findall(".//article-id"):
        if aid.get("pub-id-type") == "doi" and aid.text:
            doi = aid.text.strip()
            break
    abstract = " ".join(_text(p) for p in root.findall(".//abstract//p"))

    secs = []

    def add_sec(el, prefix):
        kids = [c for c in el if c.tag.split("}")[-1] in ("sec", "p", "fig", "table-wrap")]
        for i, ch in enumerate(kids):
            tag = ch.tag.split("}")[-1]
            if tag == "sec":
                tt = ch.find("title")
                heading = _text(tt) if tt is not None else ""
                sid = f"{prefix}{i}"
                paras, notes = [], []
                for sub in ch:
                    st = sub.tag.split("}")[-1]
                    if st == "p":
                        t = _text(sub)
                        if t:
                            paras.append(t)
                    elif st in ("fig", "table-wrap"):
                        lab = sub.find("label")
                        cap = sub.find("caption")
                        ct = _text(cap) if cap is not None else ""
                        lt = _text(lab) if lab is not None else ""
                        if ct:
                            notes.append((lt + " " + ct).strip())
                    elif st == "sec":
                        pass
                secs.append({"id": sid, "h": heading, "p": paras, "n": notes})
                for j, sub in enumerate(ch):
                    if sub.tag.split("}")[-1] == "sec":
                        tt2 = sub.find("title")
                        h2 = _text(tt2) if tt2 is not None else ""
                        ps = [_text(x) for x in sub.findall("p")]
                        ps = [x for x in ps if x]
                        secs.append({"id": f"{sid}-{j}", "h": h2, "p": ps, "n": []})
            elif tag == "p":
                t = _text(ch)
                if not t:
                    continue
                if secs and secs[-1].get("loose"):
                    secs[-1]["p"].append(t)
                else:
                    secs.append({"id": f"{prefix}L{i}", "h": "", "p": [t], "n": [], "loose": True})
            elif tag in ("fig", "table-wrap"):
                lab = ch.find("label")
                cap = ch.find("caption")
                ct = _text(cap) if cap is not None else ""
                if ct:
                    lt = _text(lab) if lab is not None else ""
                    secs.append({"id": f"{prefix}F{i}", "h": "", "p": [], "n": [(lt + " " + ct).strip()], "loose": True})

    body = root.find(".//body")
    if body is not None:
        add_sec(body, "s")

    # 去掉空节、合并连续空标题
    cleaned = []
    for s in secs:
        if s["p"] or s["n"]:
            cleaned.append(s)
    chars = sum(len(x) for s in cleaned for x in s["p"])
    lic, lic_url = _license(root)
    return {
        "id": pid, "title": title, "journal": journal, "year": year, "doi": doi,
        "authors": authors, "abstract": abstract, "secs": cleaned,
        "lic": lic, "licUrl": lic_url, "chars": chars,
        "nsec": len([s for s in cleaned if s["h"]]),
        "npar": sum(len(s["p"]) for s in cleaned),
    }


# ---------- 渲染 ----------
def esc(s):
    return html.escape(s, quote=False)


NAV = """<nav class="main"><div class="wrap">
  <div class="navlinks">
  <a href="{up}index.html">首页</a>
  <a href="{up}papers.html" class="active">文献库</a>
  <a href="{up}models.html">模型谱系</a>
  <a href="{up}companies.html">企业解剖</a>
  <a href="{up}china.html">中国生态</a>
  <a href="{up}news.html">前沿速递</a>
  <a href="{up}benchmarks.html">数据与基准</a>
  <a href="{up}insight.html">深度解读</a>
  </div>
  <div class="navsub">
  <a href="{up}glossary.html">术语表</a>
  <a href="{up}posters.html">术语海报</a>
  <a href="{up}kb/index.html" class="active">全文库</a>
  <a href="{up}search.html">搜索</a>
  <a href="{up}about.html">关于</a>
  </div>
</div></nav>"""

FOOT = """<footer><div class="wrap">
  <div class="fnav"><a href="{up}index.html">首页</a><a href="{up}papers.html">文献库</a><a href="{up}models.html">模型谱系</a><a href="{up}companies.html">企业解剖</a><a href="{up}china.html">中国生态</a><a href="{up}news.html">前沿速递</a><a href="{up}benchmarks.html">数据与基准</a><a href="{up}insight.html">深度解读</a><a href="{up}glossary.html">术语表</a><a href="{up}posters.html">术语海报</a><a href="{up}kb/index.html">全文库</a><a href="{up}search.html">搜索</a><a href="{up}about.html">关于</a></div>
  <div>AIVC Insight · 全文库只收录许可明确的开放获取文献，格式转换未改动原文文字</div>
  <div>aivc.news · <a href="{up}assets/feed.xml">RSS 订阅</a> · © 2026 AIVC Insight Team</div>
</div></footer>"""


def paper_page(p, d, full):
    """d = papers-data 元数据；full = 解析后的全文；full=None 表示只给摘要大纲。"""
    lic = (full or {}).get("lic") or ""
    lic_url = (full or {}).get("licUrl") or ""
    has_text = bool(full and lic in ALLOW_LIC and full.get("chars", 0) > 500)
    # 来源：投稿口送来的与境外抓取来的，版式一致、标注不同——读者有权知道谁说是开放获取的
    src = (full or {}).get("src") or ""
    chars_mark = f"<!-- kb-chars:{full.get('chars', 0)} -->" if has_text else ""

    # 目录
    toc = ""
    body = ""
    if has_text:
        items = []
        for s in full["secs"]:
            if s["h"]:
                cls = ' class="sub"' if "-" in s["id"] else ""
                items.append(f'<li{cls}><a href="#{s["id"]}">{esc(norm_heading(s["h"]))}</a></li>')
        toc = '<nav class="kbtoc"><b>本文目录</b><ol>' + "".join(items) + "</ol></nav>"
        chunks = []
        for s in full["secs"]:
            if s["h"]:
                lv = "h3" if "-" in s["id"] else "h2"
                chunks.append(f'<{lv} id="{s["id"]}">{esc(norm_heading(s["h"]))}</{lv}>')
            for i, x in enumerate(s["p"]):
                chunks.append(f'<p id="{s["id"]}p{i}">{esc(x)}</p>')
            for nt in s["n"]:
                chunks.append(f'<p class="kbnote">{esc(nt)}</p>')
        body = '<div class="kbtext">' + "".join(chunks) + "</div>"

    # 许可条
    if has_text:
        origin = (f'由读者投稿并经本刊核验许可（非转载自数据库），仅做格式转换，未改动原文文字'
                  if src else
                  f'站内转录自 {esc(full.get("journal") or d["v"])}（Europe PMC），仅做格式转换，未改动原文文字')
        licline = (f'<div class="kbmeta">'
                   f'<span class="kbpill ok">{esc(lic)}</span>'
                   f'<span>开放获取全文 · {origin}</span>'
                   f'</div>')
    elif full and full.get("chars", 0) > 500 and lic not in ALLOW_LIC:
        licline = (f'<div class="kbmeta"><span class="kbpill warn">许可不明</span>'
                   f'<span>该文在 Europe PMC 有全文，但许可类型未标注，本站不转录正文，'
                   f'仅列章节大纲；请前往原文阅读</span></div>')
    else:
        licline = (f'<div class="kbmeta"><span class="kbpill none">未收录全文</span>'
                   f'<span>本站未转录该文全文（非开放获取，或未取到授权清楚的载体）。'
                   f'下列为本站解读与原文摘要，正文请走详情页的全文入口</span></div>')

    abs_block = ""
    if d["summary"]:
        abs_block += f'<div class="kbsum"><b>本站解读要点</b><p>{esc(d["summary"])}</p></div>'
    if d.get("abstract") or (full and full.get("abstract")):
        a = (full or {}).get("abstract") or d.get("abstract") or ""
        abs_block += f'<div class="kbsum"><b>原文摘要</b><p>{esc(a)}</p></div>'

    outline = ""
    if not has_text and full and full.get("secs"):
        ol = "".join(f'<li>{esc(s["h"])} <i>（{len(s["p"])} 段）</i></li>'
                     for s in full["secs"] if s["h"])
        outline = f'<div class="kboutline"><b>原文结构</b><ol>{ol}</ol></div>'

    authors = "、".join(p["a"].split("、")[:4]) if p["a"] else ""
    cite = f'{authors}（{d["d"]}）. {d["t"]}. {d["v"]}. https://doi.org/{d["doi"]}'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(d["t"])} · 全文 · AIVC Insight</title>
<link rel="stylesheet" href="../assets/style.css?v=7">
<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">
<link rel="canonical" href="https://aivc.news/kb/{p['id']}.html">
</head>
<body>
{chars_mark}
{NAV.format(up="../")}

<div class="pagehead"><div class="wrap">
  <div class="crumb"><a href="index.html">全文库</a> / {esc(GROUP.get(d["g"], ""))}</div>
  <h1>{esc(d["t"])}</h1>
  <div class="kbauth">{esc(d["a"])}</div>
  <div class="kbven">{esc(d["v"])} · {esc(d["d"])} · DOI <a href="https://doi.org/{esc(d["doi"])}" target="_blank" rel="noopener">{esc(d["doi"])}</a></div>
</div></div>

<section><div class="wrap">
  {licline}
  <div class="kblayout">
    <aside class="kbside">{toc}</aside>
    <article class="kbmain">
      {abs_block}
      {outline}
      {body}
      <div class="kbcite"><b>引用格式</b><p>{esc(cite)}</p></div>
      <div class="kbfoot">
        <a href="../paper.html?id={p['id']}">← 回到本站七层解读</a>
        <a href="{esc(d.get("link") or "https://doi.org/" + d["doi"])}" target="_blank" rel="noopener">原文地址 →</a>
        <a href="../paper.html?id={p['id']}&amp;upl=1#kv-upload">这篇的全文我也有 → 投稿口</a>
      </div>
    </article>
  </div>
</div></section>

{FOOT.format(up="../")}
</body>
</html>
"""


def index_page(papers, parsed, route):
    rows = []
    by_g = {}
    for p in papers:
        f = parsed.get(p["id"])
        has = bool(f and f.get("lic") in ALLOW_LIC and f.get("chars", 0) > 500)
        if not has:
            continue
        by_g.setdefault(p["g"], []).append((p, f))
    total_chars = sum(f["chars"] for _, f in [x for v in by_g.values() for x in v])

    secs = []
    order = ["g2", "g3", "g7", "g4", "g5", "g6", "g1", "g8"]
    for g in order:
        items = by_g.get(g)
        if not items:
            continue
        li = "".join(
            f'<li><a href="{p["id"]}.html">{esc(p["t"])}</a>'
            f'<span class="kbli-meta">{esc(p["v"])} · {esc(p["d"])} · {f["chars"] // 1000}K 字 · {esc(f.get("lic") or "")}</span></li>'
            for p, f in items)
        secs.append(f'<div class="kbgroup"><h3 class="g">{esc(GROUP.get(g, g))}（{len(items)}）</h3><ul class="kblist">{li}</ul></div>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>全文库 · AIVC Insight</title>
<link rel="stylesheet" href="../assets/style.css?v=7">
<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">
<link rel="canonical" href="https://aivc.news/kb/index.html">
<meta name="description" content="AIVC Insight 全文库：开放获取论文的站内可读全文，按主题分类，支持章节定位与引用。">
</head>
<body>
{NAV.format(up="../")}

<div class="pagehead"><div class="wrap">
  <div class="crumb">栏目 01b · FULL TEXT</div>
  <h1>全文库</h1>
  <p class="lede">把开放获取论文的全文搬进站内，不用跳出去、不用等 PDF 加载。当前 <b>{sum(len(v) for v in by_g.values())}</b> 篇可读全文，共 <b>{total_chars // 1000}</b> 千字。仅收录许可明确（CC BY / CC0 / CC BY-NC / CC BY-NC-ND）的文献；格式转换未改动原文文字，每篇页首标注许可与来源。</p>
  <div class="kbnav"><input id="kbq" type="search" placeholder="在全文库中检索标题、作者、期刊…"><span id="kbcount"></span></div>
</div></div>

<section><div class="wrap">
  <div id="kbgroups">
  {''.join(secs)}
  </div>
  <div class="kbwhy">
    <b>为什么只有这些篇有全文</b>
    <p>本站不镜像、不托管论文 PDF——原文权威地址是 DOI，由出版方永久解析。全文库做的是另一件事：把<b>许可允许转载</b>的开放获取论文，从 JATS XML 转成站内可读的 HTML，让检索、引用、跨文献对照不必反复跳转。未收录的文献，详情页仍有七层解读与直达链接。</p>
  </div>
</div></section>

{FOOT.format(up="../")}

<script>
(function(){{
  var q=document.getElementById('kbq'),c=document.getElementById('kbcount');
  if(!q)return;
  var groups=[].slice.call(document.querySelectorAll('.kbgroup'));
  function run(){{
    var kw=q.value.trim().toLowerCase(),hit=0;
    groups.forEach(function(g){{
      var n=0;
      g.querySelectorAll('li').forEach(function(li){{
        var ok=!kw||li.textContent.toLowerCase().indexOf(kw)>=0;
        li.classList.toggle('hide',!ok);
        if(ok)n++;
      }});
      g.classList.toggle('hide',n===0);
      hit+=n;
    }});
    c.textContent=kw?(hit+' 篇命中'):'';
  }}
  q.addEventListener('input',run);
}})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="构建站内全文知识库")
    ap.add_argument("--no-fetch", action="store_true", help="只用本地缓存，不联网抓取")
    ap.add_argument("--only", default="", help="只处理指定 id，逗号分隔")
    a = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    KB.mkdir(exist_ok=True)
    papers = load_papers()
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        papers = [p for p in papers if p["id"] in want]

    route = load_route()
    missing = [p for p in papers if p["id"] not in route]
    if missing and not a.no_fetch:
        print(f"解析全文来源 {len(missing)} 篇…", flush=True)
        route.update(resolve_route(papers))
        (ROOT / "tools" / ".kb-route.json").write_text(
            json.dumps(route, ensure_ascii=False, indent=1), encoding="utf-8")

    targets = [(p["id"], route[p["id"]]["pmcid"]) for p in papers
               if route.get(p["id"], {}).get("route") == "epmc" and route[p["id"]].get("pmcid")]
    if targets and not a.no_fetch:
        print(f"抓取 JATS 全文 {len(targets)} 篇…", flush=True)
        fails = []
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            for pid, st in ex.map(fetch_xml, targets):
                if st.startswith(("HTTP", "URLError", "Timeout", "ValueError")):
                    fails.append((pid, st))
        if fails:
            print(f"  抓取失败 {len(fails)}: {fails[:6]}")

    parsed = all_parsed()

    n_full = 0
    for p in papers:
        full = parsed.get(p["id"])
        page = paper_page(p, p, full)
        (KB / f"{p['id']}.html").write_text(page, encoding="utf-8")
        if full and full.get("lic") in ALLOW_LIC and full.get("chars", 0) > 500:
            n_full += 1

    (KB / "index.html").write_text(index_page(load_papers(), parsed, route), encoding="utf-8")

    # 检索索引：标题级（轻）
    idx = idx_page(load_papers(), parsed, route)

    print(f"\n生成 {len(papers)} 个页面 → kb/")
    print(f"  站内可读全文 : {n_full}")
    print(f"  仅摘要/大纲  : {len(papers) - n_full}")
    print(f"  索引条目     : {idx}")


if __name__ == "__main__":
    main()
