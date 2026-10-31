#!/usr/bin/env python3
"""全文链接生成与巡检。

用法:
    python3 tools/fulltext.py            # 生成/刷新 assets/fulltext-data.js
    python3 tools/fulltext.py --check    # 只巡检现有记录，不改文件

为什么不在站内托管 PDF：
  1. 6 篇为订阅闭源，托管即侵权；
  2. 110 篇 PDF 累计数百 MB，仓库与 Pages 带宽都不划算；
  3. 原文的权威地址是 DOI，由出版方永久解析，比我们复制的副本更可靠。
本站只做「把免费全文的真实地址接出来并标明可得性」，不复制内容。

数据来源优先级（全部可核验，不做猜测）：
  预印本 → bioRxiv/medRxiv API 取 version → 规则拼 PDF 直链
  arXiv  → DOI 前缀 10.48550 规则拼 PDF 直链
  期刊   → Europe PMC（PMC 免费全文）→ OpenAlex best_oa_location → 出版商落地页
  都无   → closed
"""

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPERS_JS = ROOT / "assets" / "papers-data.js"
OUT_JS = ROOT / "assets" / "fulltext-data.js"
UA = "aivc-insight-fulltext/1.0 (https://aivc.news; bot@aivc.news)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT = 25


def get_json(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_papers():
    """从 papers-data.js 抽 id / doi / 卷期，保持文件顺序。"""
    src = PAPERS_JS.read_text(encoding="utf-8")
    pos = [(m.group(1), m.start()) for m in re.finditer(r'\{\s*id:\s*"(p\d+)"', src)]
    out = []
    for i, (pid, p) in enumerate(pos):
        end = pos[i + 1][1] if i + 1 < len(pos) else len(src)
        body = src[p:end]
        doi = re.search(r'doi:\s*"([^"]+)"', body)
        venue = re.search(r',\s*v:\s*"([^"]*)"', body)
        out.append({
            "id": pid,
            "doi": doi.group(1) if doi else "",
            "v": venue.group(1) if venue else "",
        })
    return out


def preprint_pdf(doi):
    """bioRxiv / medRxiv / arXiv 的免费 PDF 直链（先经 API 确认真实存在）。"""
    if doi.startswith("10.48550/arXiv."):
        aid = doi.split("arXiv.")[-1]
        return f"https://arxiv.org/pdf/{aid}", "arXiv", "pdf"
    if doi.startswith(("10.1101/", "10.64898/")):
        for server in ("biorxiv", "medrxiv"):
            try:
                d = get_json(f"https://api.{server}.org/details/{server}/{doi}")
            except Exception:
                continue
            coll = d.get("collection") or []
            if coll and coll[0].get("doi"):
                ver = coll[0].get("version") or "1"
                host = "www.biorxiv.org" if server == "biorxiv" else "www.medrxiv.org"
                return (f"https://{host}/content/{doi}v{ver}.full.pdf",
                        "bioRxiv" if server == "biorxiv" else "medRxiv", "pdf")
    return None


def europepmc(doi):
    """Europe PMC：优先返回可免费下载的 PDF，其次 PMC 全文页。"""
    q = urllib.parse.quote(f'DOI:"{doi}"')
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=" + q
           + "&format=json&resultType=core&pageSize=1")
    try:
        d = get_json(url)
    except Exception:
        return None
    res = (d.get("resultList") or {}).get("result") or []
    if not res:
        return None
    x = res[0]
    pmcid = x.get("pmcid")
    for t in ((x.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
        if t.get("availability") == "Free" and t.get("documentStyle") == "pdf" and t.get("url"):
            return t["url"], "Europe PMC", "pdf"
    if pmcid and str(x.get("inEPMC", "")).upper() == "Y":
        return f"https://europepmc.org/article/PMC/{pmcid.lstrip('PMCpmc')}", "Europe PMC", "page"
    return None


def openalex(doi):
    """OpenAlex：best_oa_location 的 pdf_url（若有）否则落地页。"""
    d = urllib.parse.quote(doi, safe="")
    try:
        w = get_json(f"https://api.openalex.org/works/doi:{d}"
                     "?select=open_access,best_oa_location,primary_location")
    except Exception:
        return None
    bo = w.get("best_oa_location") or {}
    pl = w.get("primary_location") or {}
    host = ((bo.get("source") or {}).get("display_name")
            or (pl.get("source") or {}).get("display_name") or "出版商")
    if bo.get("pdf_url"):
        return bo["pdf_url"], host, "pdf"
    if bo.get("landing_page_url"):
        return bo["landing_page_url"], host, "page"
    if (w.get("open_access") or {}).get("is_oa") and (w.get("open_access") or {}).get("oa_url"):
        return w["open_access"]["oa_url"], host, "page"
    return None


def resolve(paper):
    """单篇解析，返回 {u,k,s} 或 {k:"closed"}。"""
    doi = paper["doi"]
    if not doi:
        return paper["id"], {"k": "closed", "s": "无 DOI"}

    hit = preprint_pdf(doi)
    if hit:
        return paper["id"], {"u": hit[0], "s": hit[1], "k": hit[2]}

    for fn in (europepmc, openalex):
        try:
            hit = fn(doi)
        except Exception:
            hit = None
        if hit:
            return paper["id"], {"u": hit[0], "s": hit[1], "k": hit[2]}

    return paper["id"], {"k": "closed", "s": "订阅期刊"}


def probe(url):
    """实测链接：True=可达（含反爬 403/429），False=明确失效。"""
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status < 400, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        # 403/429 多为 Cloudflare 反爬——链接本身是好的，浏览器可打开
        if e.code in (401, 403, 429):
            return True, f"HTTP {e.code}（反爬，浏览器可开）"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return True, f"{type(e).__name__}（无法判定，保留）"


def build():
    papers = parse_papers()
    print(f"解析到 {len(papers)} 篇文献，开始解析全文地址…", flush=True)
    data, fails = {}, []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(resolve, p): p["id"] for p in papers}
        for i, f in enumerate(cf.as_completed(futs), 1):
            pid = futs[f]
            try:
                k, v = f.result()
                data[k] = v
            except Exception as e:
                fails.append((pid, str(e)[:80]))
                data[pid] = {"k": "closed", "s": "解析失败"}
            if i % 25 == 0:
                print(f"  ...{i}/{len(papers)}", flush=True)

    today = date.today().isoformat()
    for v in data.values():
        v["t"] = today

    lines = [
        "// 全文可达性数据 —— 由 tools/fulltext.py 自动生成，请勿手改。",
        "// k: pdf=免费 PDF 直链 / page=免费全文页 / closed=需订阅",
        "// s: 来源站点；t: 核验日期。重新生成：python3 tools/fulltext.py",
        "const FULLTEXT = {",
    ]
    for p in papers:
        v = data[p["id"]]
        parts = [f'k:"{v["k"]}"', f's:"{v["s"]}"', f't:"{v["t"]}"']
        if v.get("u"):
            parts.insert(0, f'u:"{v["u"]}"')
        lines.append(f'  {p["id"]}: {{{", ".join(parts)}}},')
    lines.append("};")
    OUT_JS.write_text("\n".join(lines) + "\n", encoding="utf-8")

    st = {"pdf": 0, "page": 0, "closed": 0}
    for v in data.values():
        st[v["k"]] = st.get(v["k"], 0) + 1
    print(f"\n已写入 {OUT_JS.relative_to(ROOT)}")
    print(f"  免费 PDF 直链 : {st['pdf']}")
    print(f"  免费全文页    : {st['page']}")
    print(f"  需订阅        : {st['closed']}")
    print(f"  可免费获取合计: {st['pdf'] + st['page']}/{len(papers)} "
          f"({(st['pdf'] + st['page']) * 100 // len(papers)}%)")
    if fails:
        print(f"  ⚠ 解析异常 {len(fails)} 篇: {fails[:5]}", file=sys.stderr)
    return 0


def check():
    """巡检现有 fulltext-data.js 里的链接，报告明确失效项。"""
    if not OUT_JS.exists():
        print("尚未生成 fulltext-data.js，请先运行不带参数的命令。", file=sys.stderr)
        return 2
    src = OUT_JS.read_text(encoding="utf-8")
    recs = []
    for m in re.finditer(r'(p\d+):\s*\{(.*?)\},', src, re.S):
        body = m.group(2)
        u = re.search(r'u:"([^"]+)"', body)
        if u:
            recs.append((m.group(1), u.group(1)))
    print(f"巡检 {len(recs)} 个全文链接…", flush=True)
    bad = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for (pid, url), (ok, msg) in zip(recs, ex.map(lambda r: probe(r[1]), recs)):
            if not ok:
                bad.append((pid, url, msg))
    for pid, url, msg in bad:
        print(f"  ✗ {pid} {msg} {url}")
    print(f"\n结果：{len(recs) - len(bad)} 可用 / {len(bad)} 失效")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="生成或巡检文献全文链接")
    ap.add_argument("--check", action="store_true", help="只巡检，不重新生成")
    a = ap.parse_args()
    return check() if a.check else build()


if __name__ == "__main__":
    sys.exit(main())
