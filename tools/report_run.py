#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIVC Insight 任务运行落账（run ledger）
======================================
问题背景（2026-10-31）：
    五个定时任务各自在独立沙箱里跑，报告直接输出给「可能没人看」的地方。
    失败、半途而废、推送没成功，都没有任何留存——07:00 晨审只能靠翻 PR 猜昨晚
    发生了什么。今日实测：`git push` 因网络抖动失败两次，其中一次重试循环的
    `&&` 把错误吞掉了，任务"跑完了"、分支根本没推上去。

本脚本的职责（只做一件事）：
    把一次运行的结论写成结构化 JSON，并在**失败时**给出显式的失败标记，
    供晨审任务读取。CRLF/LF、时区、脚本路径都不该影响结论。

用法（每条任务结束时调用，无论成败）：
    python3 tools/report_run.py \
        --task content --status ok --sha $(git rev-parse --short HEAD) \
        --branch bot/content-$(date +%F) --pr 25 \
        --summary "新增 p104-p110 七篇" \
        --note "validate 0 error；DOI 7/7 Crossref 命中"

    python3 tools/report_run.py --task ops --status blocked \
        --summary "环境阻断：无法获取仓库" --out /workspace/.intel

status 取值：ok / noop（无内容不提交）/ blocked（环境或依赖阻断）/ failed（执行失败）
exit code：ok / noop → 0；blocked / failed → 1（让上层调度能感知到失败）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
VALID = ("ok", "noop", "blocked", "failed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, help="content / ops / deep / scan / review")
    ap.add_argument("--status", required=True, choices=VALID)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--sha", default="")
    ap.add_argument("--branch", default="")
    ap.add_argument("--pr", default="")
    ap.add_argument("--out", default="/workspace/.intel", help="落账目录")
    args = ap.parse_args()

    now = datetime.now(CST)
    rec = {
        "task": args.task,
        "status": args.status,
        "summary": args.summary,
        "note": args.note,
        "sha": args.sha,
        "branch": args.branch,
        "pr": args.pr,
        "at": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False)
    with (out / "runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")

    # 失败/阻断单独留一份显眼标记，方便晨审一眼看到
    if args.status in ("blocked", "failed"):
        with (out / f"ALERT-{args.task}-{now.strftime('%Y%m%d-%H%M')}.txt").open(
            "w", encoding="utf-8"
        ) as fh:
            fh.write(f"[{args.status.upper()}] {args.task} @ {rec['at']}\n{args.summary}\n{args.note}\n")

    print(line)
    return 0 if args.status in ("ok", "noop") else 1


if __name__ == "__main__":
    sys.exit(main())
