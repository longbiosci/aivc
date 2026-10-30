#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search.html 文献索引自动补齐器（幂等）
=====================================
背景：search.html 的 `const IDX=[...]` 是全站搜索的唯一索引。其中「文献库」分组长期是人工
节选 + 部分条目只指向 papers.html 整页，导致大量文献在站内搜索里**点不进详情页**。

本脚本把 papers-data.js 中「尚未被 IDX 精确指向」的文献自动补成 IDX 条目，写进
search.html 的自动区段（由 `// AUTO-IDX-BEGIN` / `// AUTO-IDX-END` 界定）：

    {s:"文献库",t:"<英文原标题>",d:"<期刊 · 日期｜要点>",u:"paper.html?id=pXX",k:"<关键词>"},

性质：
  * **幂等**：重复运行结果一致；已存在的精确条目不会被覆盖或重复生成。
  * **不碰人工条目**：脚本只增补缺失条目，从不改写人工撰写的 IDX 条目。
  * 新增文献后重跑即可；由 tools/validate.py 负责把关（尤其第 7 项标题/描述一致性）。

用法：python3 tools/build_search_index.py [--check]
      --check  只报告缺失数量，不写文件（退出码非 0 表示有缺失）
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "assets" / "papers-data.js"
HTML = ROOT / "search.html"
BEGIN = "// AUTO-IDX-BEGIN"
END = "// AUTO-IDX-END"

# 生成 k 字段时剔除的高频无信息词
STOP = {
    "the", "and", "for", "with", "from", "that", "this", "across", "using", "based",
    "via", "into", "over", "their", "when", "what", "how", "systems", "analysis",
    "predicting", "reveals", "learning", "model", "models", "cell", "cells", "data",
    "single", "human", "study", "deep", "large", "novel", "toward", "towards",
}


def load_papers() -> list[dict]:
    """用 node 求值 papers-data.js，避免正则解析 JS 字符串的各种坑。"""
    src = DATA.read_text(encoding="utf-8")
    body = src[src.index("["): src.rindex("]") + 1]
    js = (
        "const p=" + body + ";"
        "console.log(JSON.stringify(p.map(x=>({id:x.id,t:x.t,a:x.a,v:x.v,d:x.d,summary:x.summary}))))"
    )
    # papers-data.js 体积较大，塞进 `node -e` 会 Argv too long，改走临时文件
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tf:
        tf.write(js)
        tmp = tf.name
    try:
        r = subprocess.run(["node", tmp], capture_output=True, text=True)
    finally:
        Path(tmp).unlink(missing_ok=True)
    if r.returncode != 0:
        sys.exit(f"解析 papers-data.js 失败: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


def latin_keywords(title: str, limit: int = 8) -> list[str]:
    """从英文标题提取实词关键词（保留原始大小写，便于阅读）。"""
    out, seen = [], set()
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", title):
        low = raw.lower().replace("-", "")
        if len(low) < 4 or low in STOP or low in seen:
            continue
        seen.add(low)
        out.append(raw)
        if len(out) >= limit:
            break
    return out


def build_entry(p: dict) -> str:
    title = p["t"].replace("\n", " ").strip()
    summary = re.sub(r"\s+", " ", p["summary"]).strip().rstrip("。")
    if len(summary) > 70:
        summary = summary[:70].rstrip("，、；: ·") + "…"
    desc = f"{p['v']} · {p['d']}"
    if summary:
        desc += f"｜{summary}"
    keys = latin_keywords(title)
    if p["v"]:
        keys.append(p["v"])
    # 通讯/第一作者姓作为检索面
    for tok in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", p["a"] or ""):
        if tok not in keys:
            keys.append(tok)
        if len(keys) >= 14:
            break
    j = lambda s: json.dumps(s, ensure_ascii=False)  # 统一转义，保证 JS 字符串合法
    return (
        '{s:"文献库",t:' + j(title) + ",d:" + j(desc)
        + ',u:"paper.html?id=' + p["id"] + '",k:' + j(" ".join(keys)) + "},"
    )


def main() -> None:
    papers = load_papers()
    html = HTML.read_text(encoding="utf-8")

    if BEGIN not in html or END not in html:
        sys.exit(
            "search.html 缺少 AUTO-IDX 区段标记，请先在 IDX 中文献类条目之后插入\n"
            f"  {BEGIN}\n  {END}"
        )

    blob = html[html.index("const IDX=["): html.index("];", html.index("const IDX=["))]
    covered = set(re.findall(r'u:"paper(?:\.html)?\?id=(p\d+)"', blob))

    cur_block = html[html.index(BEGIN): html.index(END) + len(END)]

    missing = [p for p in papers if p["id"] not in covered]
    print(f"文献总数 {len(papers)} | IDX 已有精确入口 {len(covered)} | 待补齐 {len(missing)}")

    if "--check" in sys.argv:
        if missing:
            print("缺失:", [p["id"] for p in missing])
        sys.exit(1 if missing else 0)

    # 保留自动区段里已有的条目（重跑时它们已计入 covered，不必、也不应重建）
    kept = re.findall(r"^\s*\{s:\"文献库\".*?\},?\s*$", cur_block, re.M)
    lines = [l.strip() for l in kept] + [build_entry(p) for p in missing]
    print(f"保留既有自动条目 {len(kept)} 条，新增 {len(missing)} 条")
    block = "\n".join(
        [BEGIN, "// ↓ 以下条目由 tools/build_search_index.py 自动生成，重跑脚本即可刷新；请勿手工编辑 ↓"]
        + lines + [END]
    )
    new = re.sub(
        re.escape(BEGIN) + r".*?" + re.escape(END),
        lambda _: block,
        html,
        count=1,
        flags=re.S,
    )
    HTML.write_text(new, encoding="utf-8")
    print(f"已写入 {len(lines)} 条自动索引条目 → search.html（IDX 覆盖已补齐至 {len(papers)}/{len(papers)}）")


if __name__ == "__main__":
    main()
