# AIVC Insight Bot 改造指南（已作废）

> ⚠️ **本文件于 2026-10-28 作废，仅作历史档案保留，不要按本文操作。**
>
> 它描述的 `bot/daily` 单一长期分支模型、`git rebase origin/bot/daily` 同步方式、「禁区文件绝对禁写」规则，均已被 [OPS.md](./OPS.md) 第二版（2026-10-27）取代。当前规范为：**当日分支 `bot/<type>-YYYY-MM-DD` + PR + CI 硬门槛 + 每日 07:00 晨审 + 人工决断合并**；禁区文件改为「可经 PR 修改、必过审」。
>
> 本文保留的唯一价值是记录 2026-10-24 分叉事故的原始处置思路。**新会话请直接读 OPS.md 与 AGENTS.md。**

> 制定：2026-10-25 · 适用范围：AIVC Insight Bot（bot@aivc.news）的全部运行环境
> 背景：2026-10-24 夜，Bot 与编辑部在 main 分支上分叉。main 已启用分支保护（禁直推），**Bot 未完成本改造前，推送将全部失败**。

## 一、必须落实的四条铁律

| # | 项目 | 旧行为 | 新行为 |
|---|---|---|---|
| 1 | 推送目标 | `git push origin main` | **`git push origin bot/daily`**（唯一目标） |
| 2 | 推送前置 | 无 | `git fetch origin && git rebase origin/bot/daily`，rebase 失败即中止本次运行 |
| 3 | 写入边界 | 全仓库 | 只写数据文件（见下表），禁区文件只读 |
| 4 | 提交信息 | 自由 | 以 `[bot]` 开头，身份保持 `AIVC Insight Bot <bot@aivc.news>` |

**绝对禁止**：`git push --force`、`git push origin HEAD:main`、删除 `bot/daily` 或 `main` 分支。

## 二、写入边界

**可写（数据与内容层）**：
- `papers-data.js`、`papers.html`
- `news.html`、`benchmarks.html`
- `assets/feed.xml`
- `assets/search-index.js`
- `bot/daily` 分支上的 `SUGGESTIONS.md`（对禁区文件的改动建议）

**禁写（页面与规范层，归编辑部）**：
- `index.html`、`insight.html`、`about.html`
- `assets/style.css`
- `OPS.md`、`BOT-MIGRATION.md`

## 三、参考实现（bash 骨架）

把 Bot 任务脚本的「推送段」替换为等价逻辑：

```bash
#!/usr/bin/env bash
set -euo pipefail
REPO=/path/to/aivc-insight   # Bot 环境中的仓库路径
BR=bot/daily

cd "$REPO"

# 1. 同步（失败即中止）
git fetch origin
git checkout "$BR"
git rebase "origin/$BR"   # 与远端对齐；冲突即中止并告警

# 2. 生成当日内容（原有逻辑不变）
#    ... 此处为 Bot 的情报抓取/写入/构建逻辑 ...
#    注意：只允许触碰第二节「可写」清单内的文件
#    可用 git status --porcelain 检查误触禁区：
if git status --porcelain | grep -qE 'index\.html|insight\.html|about\.html|style\.css|OPS\.md'; then
  echo "[bot] 错误：触碰到禁区文件，已中止" >&2
  git checkout -- .
  exit 1
fi

# 3. 提交并推送
git add -A
git commit -m "[bot] 每日维护 $(date +%F)" || { echo "[bot] 无变更"; exit 0; }
git push origin "$BR"      # 绝不加 --force，绝不推 main
```

## 四、改完后的验证清单

1. `git log origin/bot/daily --oneline -3` —— 新提交出现在 bot/daily，而非 main
2. `git ls-remote --heads origin` —— main 的 SHA 只有编辑部合并后才变
3. 手动跑一次任务，确认推送成功且 GitHub 上 `bot/daily` 分支时间戳更新
4. （可选）尝试推一次 main 确认被拒：应看到 `GH006: Protected branch update failed`

## 五、每日链路（改造后）

```
Bot 定时任务 → 写内容 → 推 bot/daily
                            ↓
              编辑部（人工/代理）审查 → PR 合并进 main
                            ↓
              Cloudflare Pages 自动部署 → aivc.news
```

编辑部合并窗口：每日上午。若 Bot 推送失败，不影响站点运行，只记录告警。

## 六、临时措施（改造完成前）

- 方案 1（推荐）：暂停 Bot 定时任务，完成改造后恢复
- 方案 2：不暂停。Bot 推 main 会被 GitHub 拒绝并报错，不会造成分叉，但错误日志会积累

---

*本文件与仓库 OPS.md 配套：OPS.md 是规则，本文件是 Bot 侧的落地手册。*
