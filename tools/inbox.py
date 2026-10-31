#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""投稿口入库：把投递来的全文解析成站内可读页面，并入 kb/ 全文库。

设计上刻意「不给第二条渲染路径」：这里只负责 **任意格式 → build_kb 的中间结构**，
页面由 tools/build_kb.py 同一个函数渲染。这样子再长，产出永远是同一种版式、
同一套许可标注、同一个 validate 第 19 项能管住的东西。

流水线（每一步失败都落到 inbox/<rid>/report.json，没有人看得到但是可查）：

    取件 → 许可判定 → 归属确认 → 解析（pdf/docx/html/xml/txt/md）→ 渲染 → 索引

许可判定只有三种结局，没有第四种：
    ● 允许  白名单许可（CC BY / CC0 / CC BY-NC*），且与全文里的版权行不冲突
    ● 拒绝  明确保留版权（All rights reserved）或 DC 排除项——**不入库，直接退回**
    ● 待确认 用户声明与正文版权行矛盾，或只填了「其他」——人工核，不进正文

「归属确认」是防投错的关键：全文里必须能找到该文献的 DOI、URL，或标题前 40 个字符，
且识别出的 DOI 若与目标文献不符就当场退回。投错文件比不投更麻烦——读者会以为那是
这篇论文的内容。
"""

import argparse
import html as htmlmod
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_kb as BK          # noqa: E402  共用解析/渲染规则，不重写第二套
import uploader as UP          # noqa: E402

INBOX = ROOT / "inbox"

# 用户可选的许可项。前四个自动放行，A 开头与「不确知」一律人工核。
ALLOW_CLAIM = {"cc-by", "cc0", "cc-by-nc", "cc-by-nc-nd"}
MANUAL_CLAIM = {"other", "unknown"}

# 正文里出现这些字样，说明版权归出版方或使用了版权扩展（CC BY-ND 或 ND 条款）
DENY_MARKS = [
    "all rights reserved", "© the author(s) 20", "exclusive licensee",
]

# 一句式说明写给人看，不写「错误码」——投递的是读者，不是运维
MSG = {
    "ok": "已入库",
    "blocked_license": "版权声明不允许转载",
    "blocked_manual": "许可类型需人工确认",
    "blocked_mismatch": "文件内容与所选文献不符",
    "blocked_noid": "正文里找不到这篇论文的标识",
    "blocked_unreadable": "文件读不出来（可能是扫描件或加密 PDF）",
    "blocked_too_short": "正文过短，不足 800 字",
    "blocked_dup": "该文献已有质量更高的全文",
}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ---------------------------------------------------------------- 取文本

def pdf_text(path):
    with tempfile.TemporaryDirectory() as td:
        txt = Path(td) / "o.txt"
        r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(path), str(txt)],
                           capture_output=True)
        if r.returncode != 0 or not txt.exists():
            return ""
        return txt.read_text(encoding="utf-8", errors="ignore")


def docx_text(path):
    import zipfile
    import xml.etree.ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
    except Exception:
        return ""
    root = ET.fromstring(xml)
    out = []
    for p in root.iter(W + "p"):
        t = "".join(n.text or "" for n in p.iter(W + "t"))
        if t.strip():
            out.append(t.strip())
    return "\n".join(out)


def html_text(path):
    raw = path.read_bytes()
    if b"<!--" in raw or b"-->" in raw:
        # 双保险：.gitattributes 的清道过滤已把闭合序列换掉，这一步是「不相信它」
        raise ValueError("含 HTML 注释定界符，拒绝解析")
    s = raw.decode("utf-8", errors="ignore")
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h[1-6]>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = htmlmod.unescape(s)
    return re.sub(r"[ \t]+", " ", s)


def jats_text(path):
    """JATS：直接走 build_kb 的解析器，拿到的就是最终版式所需的中间结构。"""
    return BK.parse_xml(path)


def plain(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def extract(path):
    ext = path.suffix.lower().lstrip(".")
    if ext == "pdf":
        return pdf_text(path), "pdf"
    if ext == "docx":
        return docx_text(path), "docx"
    if ext in ("html", "htm"):
        return html_text(path), "html"
    if ext in ("md", "txt"):
        return plain(path), ext
    return "", ""


# ---------------------------------------------------------------- 纯文本 → 结构

# 章节标题识别：学术 PDF 抽出来的文本，标题往往和正文粘在同一行（"2. Results  The ..."），
# 也可能独占一行。所以既认「整行就是标题」，也认「行首是编号标题 + 后面接正文」。
SEC_LINE = re.compile(
    r"^\s*(?:(?:\d{1,2})(?:\.\d{1,2})*\.?\s+)?"
    r"(abstract|summary|introduction|background|related work|"
    r"materials? and methods|methods?|approach|results?(?: and discussion)?|discussion|"
    r"conclusions?|limitations?|future work|outlook|references|acknowledge?ments?|"
    r"data availability|code availability|supplementary(?: material)?|"
    r"supplementary information|funding|author contributions|competing interests)"
    r"\s*[:.]?\s*",
    re.I,
)
NUM_LINE = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2})*\.?\s+[A-Z][A-Za-z0-9 ,/&:\-]{2,80}$")


def _split_heading(line):
    """返回 (标题, 同行正文) 或 (None, line)。只用行首判断，不改正文一个字。"""
    raw = line.strip()
    if not raw:
        return None, ""
    # 形如 "2.1 Benchmark construction  正文正文…"：标题取到双空格/句点后为止
    m = SEC_LINE.match(raw)
    if m and m.end() > 0:
        head = m.group(0).strip()
        rest = raw[m.end():].lstrip(" :.")
        # 「Results show that …」这种是正文，不是标题：标题名后面必须有分隔或第二个大写词
        if rest and raw[m.end():m.end() + 1] in ("", " "):
            return head, rest
        if not rest:
            return head, ""
    if len(raw) < 90 and NUM_LINE.match(raw):
        return raw, ""
    return None, raw


def blocks_to_secs(text):
    """把纯文本切成「节 + 段」，供 build_kb.paper_page 渲染。

    只做结构判断，不改文字：识别出的标题单独成节，其余按空行/换行聚成段。
    识别不出来就整篇一节——宁可少分节，不可把正文错标成标题。
    """
    secs, cur = [], None
    paras, buf = [], []

    def flush_para():
        nonlocal buf
        if buf:
            paras.append(" ".join(buf).strip())
            buf = []

    stream = []          # (kind, payload)
    for ln in text.splitlines():
        if not ln.strip():
            flush_para()
            stream.append(("blank", ""))
            continue
        head, rest = _split_heading(ln)
        if head:
            flush_para()
            stream.append(("head", head))
            if rest:
                buf.append(rest)
        else:
            buf.append(ln.strip())
    flush_para()

    # 把 paras 与 heads 按出现顺序合并
    order = []
    pi = 0
    for kind, payload in stream:
        if kind == "head":
            order.append(("head", payload))
        elif kind == "blank":
            if pi < len(paras) and (not order or order[-1][0] != "blank"):
                order.append(("para", paras[pi])); pi += 1
    while pi < len(paras):
        order.append(("para", paras[pi])); pi += 1

    for kind, val in order:
        if kind == "head":
            cur = {"id": f"s{len(secs)}", "h": val, "p": [], "n": []}
            secs.append(cur)
        elif kind == "para" and val:
            if cur is None:
                cur = {"id": "s0", "h": "", "p": [], "n": []}
                secs.append(cur)
            cur["p"].append(val)
    return [x for x in secs if x["p"]]


# ---------------------------------------------------------------- 许可与归属

def lic_from_claim(claim):
    claim = (claim or "").strip().lower()
    if claim in ALLOW_CLAIM:
        # 注意别写成集合字面量——花括号在这里是 dict 语法，返回 set 会让后面 .replace 崩
        if claim == "cc-by":
            return "CC BY"
        if claim == "cc0":
            return "CC0 1.0"
        return "CC " + claim.split("-", 1)[1].upper()
    return None


def judge_license(claim, text):
    """返回 (verdict, 详情)。verdict ∈ allow / deny / manual，详情在 allow 时就是许可名。"""
    lic = lic_from_claim(claim)
    low = (text or "").lower()
    if claim in MANUAL_CLAIM or not lic:
        return "manual", "投稿人选择的许可类型需人工核实"
    # 用户说 CC BY，正文却写着保留版权——以更严的一方为准
    for mark in DENY_MARKS:
        if mark in low:
            return "deny", f"正文含「{mark}」，与声明的 {lic} 冲突"
    if re.search(r"\bcc\s*by[- ]?nd\b", low) and lic == "CC BY":
        return "deny", "正文标注 CC BY-ND，不得转录全文"
    return "allow", lic


def judge_identity(paper, text):
    """全文里必须能对上这篇论文。返回 (ok, 说明)。"""
    flat = norm(text)
    if paper.get("doi") and norm(paper["doi"]) in flat:
        return True, "DOI 命中"
    title_key = norm(paper["t"])[:40]
    if title_key and title_key in flat:
        return True, "标题命中"
    if norm(paper["t"])[:24] and norm(paper["t"])[:24] in flat:
        return True, "标题前缀命中"
    # 退一步：正文里若出现另一个 DOI 且与目标不同，直接判投错
    m = re.search(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", text or "", re.I)
    if m:
        return False, f"正文 DOI 为 {m.group(0)}，与目标 {paper.get('doi', '')} 不符"
    return False, "正文里找不到该文献的 DOI 或标题"


# ---------------------------------------------------------------- 主流程

def find_paper(pid):
    for p in BK.load_papers():
        if p["id"] == pid:
            return p
    return None


def process(rid):
    rep = json.loads(UP.report_path(rid).read_text(encoding="utf-8"))
    raw = INBOX / rid / "raw"
    bodies = sorted(x for x in raw.glob("body.*")) if raw.exists() else []
    if not bodies:
        rep.update(state="blocked", reason="没有可解析的正文文件", msg=MSG["blocked_unreadable"])
        UP.save_report(rep)
        return rep

    body = bodies[0]
    ext = body.suffix.lower().lstrip(".")
    man = rep.get("meta") or {}
    pid = (man.get("paper_id") or rep.get("paper_id") or "").strip()
    rep["paper_id"] = pid
    paper = find_paper(pid) if pid else None

    # 形态一：投的是 JATS XML（最理想，直接进解析器）
    if ext == "xml":
        try:
            full = jats_text(body)
        except Exception as e:
            rep.update(state="blocked", reason=f"JATS 解析失败：{type(e).__name__}", msg=MSG["blocked_unreadable"])
            UP.save_report(rep)
            return rep
        text = " ".join(x for s in full["secs"] for x in s["p"])
        lic_verdict, lic = judge_license(man.get("license"), text + " " + full.get("abstract", ""))
        if full.get("lic") in BK.ALLOW_LIC:
            lic_verdict, lic = "allow", full["lic"]
    else:
        text, fmt = extract(body)
        if not text.strip():
            rep.update(state="blocked", reason="抽取不到文本（扫描件/加密/格式不支持）",
                       msg=MSG["blocked_unreadable"])
            UP.save_report(rep)
            return rep
        full = {
            "id": pid, "title": "", "journal": "", "year": "", "doi": "",
            "authors": [], "abstract": "", "secs": blocks_to_secs(text),
            "lic": "", "licUrl": "", "chars": sum(len(x) for s in blocks_to_secs(text) for x in s["p"]),
            "nsec": 0, "npar": 0,
        }
        lic_verdict, lic = judge_license(man.get("license"), text)

    # 归属：投错比不投更糟
    if paper:
        ok, why = judge_identity(paper, text)
    else:
        ok, why = False, "投递单未指定有效文献编号"
    if not ok:
        rep.update(state="blocked", reason=why, msg=MSG["blocked_mismatch"])
        UP.save_report(rep)
        return rep

    if full["chars"] < 800:
        rep.update(state="blocked", reason=f"正文仅 {full['chars']} 字", msg=MSG["blocked_too_short"])
        UP.save_report(rep)
        return rep

    if lic_verdict != "allow":
        rep.update(state="blocked", reason=why if lic_verdict == "deny" else why + "：" + str(lic),
                   msg=MSG["blocked_license"] if lic_verdict == "deny" else MSG["blocked_manual"],
                   lic=lic)
        UP.save_report(rep)
        return rep

    full["lic"] = lic
    full["licUrl"] = "https://creativecommons.org/licenses/" + lic.replace("CC ", "").lower() + "/"
    full["chars"] = sum(len(x) for s in full["secs"] for x in s["p"])

    # 现有站内全文是否更好？比字数——投来的比现状短就不覆盖，避免劣化
    cur = ROOT / "kb" / f"{pid}.html"
    if cur.exists():
        m = re.search(r"共收录|(\d+)K 字", cur.read_text(encoding="utf-8"))
        existing_chars = 0
        cm = re.search(r"<!-- kb-chars:(\d+) -->", cur.read_text(encoding="utf-8"))
        if cm:
            existing_chars = int(cm.group(1))
        if existing_chars and full["chars"] < existing_chars * 0.95:
            rep.update(state="blocked", reason=f"现有全文 {existing_chars} 字，投递 {full['chars']} 字",
                       msg=MSG["blocked_dup"])
            UP.save_report(rep)
            return rep

    # 入库：在 kb/ 写 .src.json 让 build_kb 下次重建时保留这一篇
    # src 必须同时写进 meta 与 full：paper_page(full) 从 full 取它来决定来源标注，
    # 只写 meta 会让页面把投稿全文误标成「转录自 Europe PMC」——那是另一条来源，不能混。
    meta = dict(paper)
    meta["src"] = "投稿口"
    full["src"] = "投稿口"
    (ROOT / "kb" / f"{pid}.src.json").write_text(
        json.dumps({"meta": meta, "full": full}, ensure_ascii=False), encoding="utf-8")
    BK.write_uploaded(pid)
    try:
        import publish_inbox
        publish_inbox.write(publish_inbox.build())
    except Exception as e:  # 回执写失败不影响入库，但要在报告里留痕
        rep["steps"].append(f"回执写入失败：{type(e).__name__}")

    rep.update(state="done", lic=lic, chars=full["chars"],
               reason="", msg=MSG["ok"], kb=f"kb/{pid}.html")
    UP.save_report(rep)
    return rep


# ---------------------------------------------------------------- Git 清道过滤
#
# .gitattributes 把 _inbox/** 与 inbox/** 指向 filter=kbscrub。下面两个子命令就是
# 这个过滤器的两端（smudge = checkout 时跑，clean = add 时跑）。
# 作用：把 HTML 注释定界符替换成同名但不可解析的字符，原文其余字节一个不改。
# PDF 里这些序列出现的概率极低；一旦出现，被改坏的只是文件里那 4 个字节，肉眼可见。

SCRUB = [
    (b"<!--", "\u2039!\u2039\u2039".encode("utf-8")),
    (b"-->", "\u2039!\u2039\u2039-".encode("utf-8")),
]


def scrub(data):
    for a, b in SCRUB:
        data = data.replace(a, b)
    return data


def cli():
    ap = argparse.ArgumentParser(description="投稿口：取件 / 入库 / Git 清道过滤")
    ap.add_argument("--rid", help="只处理指定批次")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("fetch", help="从收件箱取件到隔离区")
    sub.add_parser("process", help="把隔离区里待处理的批次入库")
    sub.add_parser("status", help="列出全部批次与状态")
    for name in ("scrub", "clean", "smudge"):
        sub.add_parser(name, help="Git filter" if name != "scrub" else "清道过滤（stdin→stdout）")
    a = ap.parse_args()

    if a.cmd in ("scrub", "clean", "smudge"):
        sys.stdout.buffer.write(scrub(sys.stdin.buffer.read()))
        return
    if a.cmd == "status":
        for r in UP.load_reports():
            print(f"{r['id']:<18} {r.get('state', ''):<13} {r.get('paper_id', ''):<5} "
                  f"{r.get('msg') or r.get('reason', '')}")
        return
    if a.cmd == "fetch":
        import os
        # 取件源：drops/ 下的 .eml / .txt（读者邮件导出）；设了 KBINBOX_IMAP_HOST 则先直连邮箱拉信。
        # 全程不需要任何凭据——邮件是读者天然有的通道，我们天然能收。
        n_mail = UP.fetch_imap()
        if n_mail:
            print(f"从邮箱拉到 {n_mail} 封")
        got = UP.fetch_all(os.environ.get("KBINBOX_DROPS", ""))
        print(f"取件 {len(got)} 批")
        for r in got:
            print(f"  {r['id']} {r['state']} {r.get('reason', '')}")
        return
    if a.cmd == "process" or a.rid:
        targets = [a.rid] if a.rid else [r["id"] for r in UP.load_reports() if r.get("state") == "quarantined"]
        for rid in targets:
            r = process(rid)
            print(f"{rid} → {r['state']} {r.get('msg') or r.get('reason', '')}")
        return
    ap.print_help()


if __name__ == "__main__":
    cli()
