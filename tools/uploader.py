#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""投稿口取件：把读者邮件里的全文取回本地隔离区，供 tools/inbox.py 入库。

公开静态站（Cloudflare Pages）没有任何服务端可收文件，前端也不能带任何凭据，
所以投稿走**邮件**：文献页生成一张结构化的投递单，读者把全文作为附件发出。

投递单（纯文本，机读头 + 人读尾）：

    AIVC-INSIGHT-UPLOAD v1
    rid: u20261031T093015ab12
    paper: p98
    license: cc-by
    file: paper.pdf (1203 KB)
    sha256: 3f9a…

后台从三种来源取件，解析规则完全相同（都先归一成「正文 + 附件」再看）：

    drops/*.eml        导出的邮件文件（最省事：邮件客户端「另存为 .eml」）
    drops/*.txt        只贴了正文的情况（附件另放 drops/<同名目录>/）
    IMAP               可选：设 KBINBOX_IMAP_HOST 后直连邮箱拉取

为什么不在前端直接传：静态站把写权限放进网页源码，等于公开给人用；GitHub 的 issue
写接口（POST /issues、POST /comments）也一律要求认证，匿名返回 401。邮件是唯一
「读者天然有、我们天然能收、且不需要任何凭据」的通道。
"""

import email
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from email import policy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIND = "paper-upload"
DROPS = ROOT / "drops"          # 邮件落地区，同样在 .gitignore 里

# 投递单机读头。改这里必须同步改 assets/kb-inbox.js 的 slip()。
RID = re.compile(r"^rid:\s*([A-Za-z0-9\-]{6,40})\s*$", re.M)
PAPER = re.compile(r"^paper:\s*(p\d{1,3})\s*$", re.M)
LIC = re.compile(r"^license:\s*([a-z0-9\-]{2,20})\s*$", re.M)
FILE = re.compile(r"^file:\s*(.+?)\s*$", re.M)
SHA = re.compile(r"^sha256:\s*([0-9a-f]{64}|n/a)\s*$", re.M)
SUBJ = re.compile(r"\[全文投稿\]\s*(p\d{1,3})\s+([A-Za-z0-9\-]{6,40})")

BODY_EXT = {"pdf", "xml", "docx", "html", "htm", "md", "txt", "json"}
MAX_BYTES = 40 * 1024 * 1024


# ---------------------------------------------------------------- 基本工具

def now():
    return datetime.now(timezone.utc)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(name, maxlen=72):
    """把附件文件名收敛成可安全用于目录与链接的形式，但保留原始名用于回执。"""
    name = unicodedata.normalize("NFKC", name or "").strip()
    name = name.replace("\\", "/").split("/")[-1]
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff\-_]+", "-", stem).strip("-") or "paper"
    ext = re.sub(r"[^A-Za-z0-9]", "", ext).lower()[:8]
    stem = stem[:maxlen]
    return f"{stem}.{ext}" if ext else stem


def report_path(rid):
    return ROOT / "inbox" / rid / "report.json"


def load_reports():
    out = []
    for f in sorted((ROOT / "inbox").glob("*/report.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def save_report(rep):
    p = report_path(rep["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


# ---------------------------------------------------------------- 解析投递单

def parse_slip(text, subject=""):
    """从投递单正文里读出编号、文献、许可、文件名与指纹。读不出编号的一律不认。"""
    text = text or ""
    m = RID.search(text)
    rid = m.group(1) if m else ""
    pm = PAPER.search(text)
    pid = pm.group(1) if pm else ""
    if not rid or not pid:
        # 正文被邮件客户端改写坏了也不该丢件：主题里带编号就按主题认
        sm = SUBJ.search(subject or "")
        if not sm:
            return None
        pid, rid = sm.group(1), sm.group(2)
    lic = LIC.search(text)
    fn = FILE.search(text)
    sh = SHA.search(text)
    return {
        "rid": rid,
        "pid": pid,
        "kind": KIND,
        "license": (lic.group(1).lower() if lic else ""),
        "declared_file": (fn.group(1) if fn else ""),
        "declared_sha": (sh.group(1) if sh and sh.group(1) != "n/a" else ""),
        "subject": subject or "",
    }


def _walk_parts(msg):
    """邮件可能是 multipart（正文 + 附件），也可能整封只有一个文件。返回 (正文, [(名, 字节)])。"""
    texts, files = [], []
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        fn = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if fn:
            files.append((safe_name(fn), data))
        elif part.get_content_type() == "text/plain":
            try:
                texts.append(data.decode(part.get_content_charset() or "utf-8", "ignore"))
            except Exception:
                texts.append(data.decode("utf-8", "ignore"))
    return "\n".join(texts), files


def read_eml(path):
    raw = path.read_bytes()
    msg = email.message_from_bytes(raw, policy=policy.default)
    subj = str(msg.get("Subject") or "")
    body, files = _walk_parts(msg)
    return body, files, subj


# ---------------------------------------------------------------- 取件

def fetch_one(rid, body, files, subject, src=""):
    """把一封邮件解到 inbox/<rid>/raw/。落盘前逐字节 scan 注释定界符。"""
    rep = {
        "id": rid, "state": "fetched", "kind": KIND,
        "created": now().strftime("%Y-%m-%d %H:%M"),
        "paper_id": "", "src": src, "steps": [], "reason": "",
    }
    man = parse_slip(body, subject)
    if not man:
        rep.update(state="failed", reason="邮件里没有投递单（缺 rid / paper 行）")
        return rep
    rep["paper_id"] = man["pid"]
    rep["meta"] = man

    usable = []
    for name, data in files:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in BODY_EXT:
            rep.setdefault("skipped", []).append(name)
            continue
        if len(data) > MAX_BYTES:
            rep.setdefault("skipped", []).append(name + "（超过 40MB）")
            continue
        if b"<!--" in data or b"-->" in data:
            rep.update(state="blocked", reason=f"{name} 含 HTML 注释定界符，拒绝解码（防注入）")
            return rep
        usable.append((name, data, ext))

    if not usable:
        rep.update(state="blocked", reason="邮件里没有可解析的附件",
                   msg="没收到文件——请把全文作为附件重发，主题里的编号不要改")
        return rep

    # 指纹对不上时不拒收，只记一笔：读者可能只是换了个版本重发
    if man["declared_sha"]:
        for name, data, _ in usable:
            got = hashlib.sha256(data).hexdigest()
            if got != man["declared_sha"]:
                rep["steps"].append(
                    f"指纹与投递单不符：{name}（投递单 {man['declared_sha'][:12]}… / 实际 {got[:12]}…），可能换了文件")

    raw_dir = ROOT / "inbox" / rid / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    got = []
    for name, data, ext in usable:
        dest = raw_dir / ("body." + ext)
        dest.write_bytes(data)
        got.append({"name": name, "bytes": len(data), "sha256": sha256(dest)})

    rep["files"] = got
    rep["state"] = "quarantined"
    return rep


def fetch_all(folder=None):
    """扫 drops/ 下的 .eml 与 .txt，把没登记过的批次取到隔离区。"""
    folder = Path(folder) if folder else DROPS
    done = {x["id"] for x in load_reports()}
    made = []
    if not folder.exists():
        return made
    for f in sorted(folder.glob("*.eml")) + sorted(folder.glob("*.txt")):
        try:
            if f.suffix.lower() == ".eml":
                body, files, subj = read_eml(f)
            else:
                body = f.read_text(encoding="utf-8", errors="ignore")
                subj, files = "", []
                side = folder / f.stem            # 同名目录里的文件当作附件
                if side.is_dir():
                    files = [(safe_name(x.name), x.read_bytes()) for x in sorted(side.iterdir()) if x.is_file()]
        except Exception as e:
            print(f"读不了 {f.name}：{type(e).__name__}: {e}", file=sys.stderr)
            continue
        man = parse_slip(body, subj)
        if not man or man["rid"] in done:
            continue
        rep = fetch_one(man["rid"], body, files, subj, src=f.name)
        save_report(rep)
        made.append(rep)
    return made


def fetch_imap():
    """可选：直连邮箱把标题带 [全文投稿] 的信拉成 .eml 存进 drops/。"""
    host = os.environ.get("KBINBOX_IMAP_HOST", "")
    if not host:
        return 0
    import imaplib
    user = os.environ.get("KBINBOX_IMAP_USER", "")
    pwd = os.environ.get("KBINBOX_IMAP_PASS", "")
    port = int(os.environ.get("KBINBOX_IMAP_PORT", "993"))
    DROPS.mkdir(parents=True, exist_ok=True)
    n = 0
    with imaplib.IMAP4_SSL(host, port) as M:
        M.login(user, pwd)
        M.select("INBOX")
        typ, data = M.search(None, "SUBJECT", '"[全文投稿]"')
        for num in (data[0].split() if data and data[0] else []):
            typ, raw = M.fetch(num, "(RFC822)")
            if typ != "OK" or not raw or not isinstance(raw[0], tuple):
                continue
            blob = raw[0][1]
            msg = email.message_from_bytes(blob, policy=policy.default)
            subj = str(msg.get("Subject") or "")
            man = parse_slip(subj, subj)
            name = (man["rid"] if man else "mail-" + num.decode()) + ".eml"
            dest = DROPS / name
            if not dest.exists():
                dest.write_bytes(blob)
                n += 1
    return n


if __name__ == "__main__":
    print(__doc__)
