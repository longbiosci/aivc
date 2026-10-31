#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把投递单回执写回 assets/kb-inbox-data.js（文献页状态条 + 文献库「读者投稿」角标）。

只写聚合结果，不写任何原文内容、不写投稿人身份——页面上要回答的只有两个问题：
「我投的那篇到哪一步了」和「这篇的全文是谁补上的」。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import uploader as UP  # noqa: E402

OUT = ROOT / "assets" / "kb-inbox-data.js"

STATE_CN = {
    "fetched": "wait", "quarantined": "wait", "parsed": "wait",
    "done": "done", "blocked": "blocked", "failed": "blocked",
}


def build():
    rows = []
    for r in UP.load_reports():
        rid = r.get("id", "")
        if not rid:
            continue          # 后台内部批次（t 开头）在发布前由 publish_inbox 的调用方筛掉
        s = STATE_CN.get(r.get("state"), "wait")
        row = {"r": rid, "p": r.get("paper_id", ""), "s": s,
               "at": (r.get("created") or "")[:10],
               "m": (r.get("msg") if s != "done" else "") or ""}
        if s == "done" and r.get("chars"):
            row["n"] = r["chars"]
        rows.append(row)
    return rows


def write(rows):
    js = ("/* 投稿口数据 —— 由 tools/publish_inbox.py 生成，禁止手改。\n"
          " * 线上投稿口提交后落到 GitHub 收件箱，由后台取件入库，处理结果写回本文件，\n"
          " * 文献页据此显示「已收录 / 处理中 / 需补充」。s ∈ done | wait | blocked。 */\n"
          "var KBINBOX_STATUS = "
          + json.dumps(rows, ensure_ascii=False, indent=0) + ";\n")
    OUT.write_text(js, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    rows = build()
    p = write(rows)
    print(f"✓ {p.relative_to(ROOT)}：{len(rows)} 条回执")
