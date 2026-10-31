#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIVC Insight 并行写入冲突门禁（preflight）
==========================================
问题背景（2026-10-31）：
    当日 content / ops / deep 三个 Bot 任务并行，均从同一个 origin/main 建立分支。
    content 与 deep 各自在 search.html 与 benchmarks.html 上做了修改，双方都不知道
    对方在改同一个文件，结果：
      - search.html 的 4 处缺逗号故障被两个分支各继承一遍、各修复一遍；
      - benchmarks.html 的 Cascade 卡片被两个 PR 各加一张，自动合并后页面上出现重复卡片。
    并行本身不是错，错在「改之前不知道别人正在改同一个文件」。

本脚本的职责（只做一件事）：
    在 PR 打开时，比较「当前 PR 改动的文件」与「其他 open PR 改动的文件」，
    重叠即判红（exit 1），把撞车从「合并时人工解冲突」提前到「建 PR 时机器拦截」。

设计原则：
    1. 只读：不写仓库、不改任何内容、不合并。
    2. 无网可降级：拿不到 open PR 列表时输出 warning 并 exit 0，
       绝不因为网络问题误拦正常 PR（宁漏勿误伤）。
    3. 有豁免名单：确实需要同时改的公共文件（如 search.html 的索引追加）
       走显式豁免并在输出中留痕，避免门禁变成「人人骂的橡皮筋」。

用法：
    # 本地预检（对比当前分支与 origin/main）
    python3 tools/preflight_conflicts.py --base origin/main

    # CI 内（GitHub Actions 自动提供环境变量）
    GITHUB_TOKEN=xxx GITHUB_REPOSITORY=owner/repo GITHUB_HEAD_REF=bot/content-x \
        python3 tools/preflight_conflicts.py

退出码：0 = 无冲突（或无法判定，降级放行）；1 = 存在文件重叠冲突。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

# ---------- 豁免名单 ----------
# 语义：这些文件允许被多个 open PR 同时改动，但必须在这里显式登记并写明理由。
# 加条目 = 承认「该文件存在真实的多写竞争」，须同时在 SUGGESTIONS.md 报备。
ALLOW = {}
# 例：ALLOW = {"search.html": "索引按编号顺序追加，冲突可机械解（见 SUGGESTIONS 建议 X）"}


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {r.stderr.strip()[:200]}")
    return r.stdout


def changed_files(base: str, head: str = "HEAD") -> set[str]:
    """三点 diff：只算本分支相对 merge-base 真正新增的改动。"""
    out = git("diff", "--name-only", f"{base}...{head}")
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def api(path: str, token: str | None) -> object | None:
    url = f"https://api.github.com/repos/{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"⚠ 无法访问 GitHub API（{e.__class__.__name__}），门禁降级放行。")
        return None


def open_pr_files(repo: str, token: str | None, skip_branch: str) -> dict[str, list[int]]:
    """返回 {文件路径: [pr编号...]}，覆盖除自身外的全部 open PR。"""
    prs = api(f"{repo}/pulls?state=open&per_page=100", token)
    if prs is None:
        return {}
    result: dict[str, list[int]] = {}
    for pr in prs:
        if pr["head"]["ref"] == skip_branch:
            continue
        files = api(f"{repo}/pulls/{pr['number']}/files?per_page=300", token)
        if files is None:
            continue
        for f in files:
            result.setdefault(f["filename"], []).append(pr["number"])
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="open PR 之间改动文件重叠检测")
    ap.add_argument("--base", default="origin/main", help="比较基线，默认 origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    ap.add_argument(
        "--self-branch",
        default=os.environ.get("GITHUB_HEAD_REF", ""),
        help="自身分支名，用于从重叠集合里排除自己",
    )
    args = ap.parse_args()

    try:
        mine = changed_files(args.base, args.head)
    except RuntimeError as e:
        print(f"⚠ {e}")
        print("门禁降级放行（无法取得 diff）。")
        return 0

    print(f"本分支改动文件 {len(mine)} 个（vs {args.base}）")
    if not args.repo:
        print("未提供 --repo / GITHUB_REPOSITORY，跳过跨 PR 比对。")
        return 0

    others = open_pr_files(args.repo, args.token or None, args.self_branch)
    if not others:
        print("无其他 open PR，或 API 不可用，门禁通过。")
        return 0

    clash = {f: prs for f, prs in others.items() if f in mine and f not in ALLOW}
    if not clash:
        print("✅ 与其他 open PR 无文件重叠。")
        return 0

    print("\n❌ 与其他 open PR 存在文件重叠（并行写入冲突）：")
    for f, prs in sorted(clash.items()):
        print(f"   {f}  ← 同时被 PR {', '.join('#'+str(p) for p in prs)} 改动")
    print(
        "\n处置建议：\n"
        "  1) 若两侧改动互不依赖：后开的 PR 等前一个合并后 rebase，再开；\n"
        "  2) 若必须同时改：按 OPS §4.2 第 4 条「内容类按时间序融合、两说并留」解冲突，\n"
        "     并在 PR 描述中写明如何避免重复收录；\n"
        "  3) 若该文件确属多写竞争且可机械解：在 tools/preflight_conflicts.py 的 ALLOW\n"
        "     登记理由，并在 SUGGESTIONS.md 报备。"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
