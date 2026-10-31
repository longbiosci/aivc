#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把站内全文页转成 IMA 知识库友好的 Markdown。

为什么要转换而不是直接推 HTML：IMA 里做的是检索与问答，需要的是可切分的
论点段落，不是带导航栏的整页 HTML。这里只保留「标题 / 元信息 / 分节正文」，
去掉导航、目录、页脚——那些在知识库里是噪声，会稀释检索命中率。

用法：
    python3 tools/push_ima.py p12            # 生成并打印预览
    python3 tools/push_ima.py p12 --out      # 写到 ima_out/p12.md
    python3 tools/push_ima.py --all --out    # 批量（只含有正文的篇）
"""
import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "kb"
OUT = ROOT / "ima_out"
SITE = "https://aivc.news"
CHARS_MIN = 200          # 低于此数视为空壳页，没有正文可推


def clean(s):
    s = re.sub(r"\s+", " ", (s or "")).strip()
    # 去标签后常见「句号后丢了空格」，只在小写.大写 处补，不动 i.e. / e.g. 这类缩写
    s = re.sub(r"(?<=[a-z])\.(?=[A-Z])", ". ", s)
    return s


def split_long(text, limit=600):
    """把超长段落按句切成小段。

    两个原因：一是知识库检索按段切块，一段几千字会稀释命中率；二是原文里
    被压平的表格会变成一行上万字，读起来也没有意义。
    """
    if len(text) <= limit:
        return [text]
    # 中文按句号切；英文只在「句点 + 空白 + 大写/引号」处切，避免 i.e. / e.g. / et al. 被切断
    pieces = re.split(r"(?<=[。！？；])|(?<=[.!?])\s+(?=[A-Z“\"'(])", text)
    parts, buf = [], ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        joiner = ""
        if buf and re.match(r"[A-Za-z0-9(]", piece) and re.search(r"[A-Za-z0-9.,;:]$", buf):
            joiner = " "        # 英文句间补回被 split 吃掉的空格
        if len(buf) + len(piece) > limit and buf:
            parts.append(buf)
            buf = piece
        else:
            buf += joiner + piece
    if buf:
        parts.append(buf)
    return parts or [text]


def extract(pid):
    """从 kb/<pid>.html 抽标题、元信息、分节正文。"""
    src = KB / f"{pid}.html"
    if not src.exists():
        return None
    soup = BeautifulSoup(src.read_text(encoding="utf-8"), "html.parser")

    h1 = soup.find("h1")
    title = clean(h1.get_text()) if h1 else pid

    # h1 之后、<section> 之前的那两行：作者行 + 期刊/编号/DOI 行
    author, cite = "", ""
    if h1:
        tail = []
        for sib in h1.next_siblings:
            if getattr(sib, "name", None) == "section":
                break
            if getattr(sib, "name", None):
                t = clean(sib.get_text())
                if t:
                    tail.append(t)
        if len(tail) >= 1:
            author = tail[0]
        if len(tail) >= 2:
            cite = tail[1]

    meta = soup.select_one(".kbmeta")
    lic, note = "", ""
    if meta:
        pill = meta.select_one(".kbpill")
        lic = clean(pill.get_text()) if pill else ""
        rest = [clean(sp.get_text()) for sp in meta.find_all("span") if sp is not pill]
        note = " ".join(x for x in rest if x)

    # 正文：只走 h2/h3/p/li，跳过目录块
    body = []
    sec = soup.find("section")
    if sec:
        for el in sec.find_all(["h2", "h3", "p", "li"]):
            if el.find_parent(class_="kbtoc") or el.find_parent(class_="kbside"):
                continue
            if el.find_parent("nav"):
                continue
            txt = clean(el.get_text())
            if not txt:
                continue
            if el.name == "h2":
                body.append(f"\n## {txt}\n")
            elif el.name == "h3":
                body.append(f"\n### {txt}\n")
            elif el.name == "li":
                body.append(f"- {txt}")
            else:
                body.append(txt)

    # 去重相邻重复行（排版残留），并把超长段切成可检索的小段
    dedup = []
    for line in body:
        chunks = split_long(line) if not line.startswith("#") else [line]
        for c in chunks:
            if dedup and c == dedup[-1]:
                continue
            dedup.append(c)

    # 站内一句话摘要（正文首个短中文段）单列出来，别和原文混成一段
    blurb = ""
    for i, line in enumerate(dedup):
        plain = re.sub(r"^#+\s*", "", line).strip()
        if not plain:
            continue
        if len(plain) < 200 and re.search(r"[\u4e00-\u9fff]", plain):
            blurb = plain
            del dedup[i]
        break

    text = "\n\n".join(x for x in dedup if x.strip())
    if blurb:
        text = f"## 站内摘要\n\n> {blurb}\n\n{text}"
    chars = len(re.sub(r"[\s#>\-]", "", text))
    if chars < CHARS_MIN:
        return None

    doi = ""
    m = re.search(r"10\.\d{4,9}/[^\s·）)]+", cite)
    if m:
        doi = m.group(0)

    # 出处行里的「· p12 ·」和「DOI xxx」是页面排版用的，元信息里已单列，去掉避免重复
    cite = re.sub(r"\s*·\s*" + re.escape(pid) + r"\s*·?\s*", " · ", cite)
    cite = re.sub(r"\s*·?\s*DOI\s*\S+\s*$", "", cite).strip(" ·")

    head = [f"# {title}", ""]
    meta_lines = [f"- 文献编号：{pid}"]
    if author:
        meta_lines.append(f"- 作者：{author}")
    if cite:
        meta_lines.append(f"- 出处：{cite}")
    if doi:
        meta_lines.append(f"- DOI：{doi}")
    if lic:
        meta_lines.append(f"- 许可：{lic}")
    meta_lines.append(f"- 站内全文：{SITE}/kb/{pid}.html")
    if note:
        meta_lines.append(f"- 转录说明：{note}")
    meta_lines.append("- 收录方：AIVC Insight 全文库")

    tail = [
        "",
        "---",
        "",
        f"> 来源：AIVC Insight 全文库（{SITE}/kb/{pid}.html）。"
        f"文字取自原刊开放获取版本，仅做格式转换，未改动原文。"
        f"引用与转载请以原刊为准；本文件的可用范围受上述许可（{lic or '见原刊'}）约束。",
    ]
    return "\n".join(head + meta_lines) + "\n\n" + text + "\n" + "\n".join(tail) + "\n"


def has_body(pid):
    f = KB / f"{pid}.html"
    if not f.exists():
        return False
    s = f.read_text(encoding="utf-8")
    m = re.search(r"kb-chars:(\d+)", s)
    return bool(m) and int(m.group(1)) > CHARS_MIN


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pids", nargs="*", help="篇号，如 p12")
    ap.add_argument("--all", action="store_true", help="全部有正文的篇")
    ap.add_argument("--out", action="store_true", help="写到 ima_out/<pid>.md")
    a = ap.parse_args()

    pids = a.pids
    if a.all:
        pids = sorted(p.stem for p in KB.glob("p*.html"))
        pids = [p for p in pids if has_body(p)]
    if not pids:
        print("没有指定篇号（用 p12 或 --all）", file=sys.stderr)
        return 1

    OUT.mkdir(exist_ok=True)
    made = 0
    for pid in pids:
        md = extract(pid)
        if not md:
            print(f"  跳过 {pid}（无正文或不足 {CHARS_MIN} 字）")
            continue
        chars = len(re.sub(r"[\s#>\-]", "", md))
        if a.out:
            (OUT / f"{pid}.md").write_text(md, encoding="utf-8")
            print(f"  {pid}.md  {chars:,} 字")
        else:
            print(f"===== {pid}（{chars:,} 字）=====")
            print(md[:1500] + ("\n…（后略）" if len(md) > 1500 else ""))
        made += 1
    print(f"\n完成 {made} 篇")
    return 0


if __name__ == "__main__":
    sys.exit(main())
