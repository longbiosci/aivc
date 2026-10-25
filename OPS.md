# AIVC Insight 仓库写入规范（OPS）

> 本文件是本站内容生产的唯一权威操作规程。所有写入方（编辑部、AIVC Insight Bot、协作者）必须遵守。
> 制定日期：2026-10-25。背景：10-24 夜间编辑部与 Bot 在 main 上分叉，合并后立此规范。

## 一、分支模型

| 分支 | 所有者 | 用途 | 规则 |
|---|---|---|---|
| `main` | 编辑部（editor@aivc.news） | 唯一对外部署分支，Cloudflare Pages 自动部署 | **禁止直接 push**（已启用分支保护）。只接受 PR 合并 |
| `bot/daily` | AIVC Insight Bot（bot@aivc.news） | Bot 全部产出（情报更新、数据维护、技术运维） | Bot 只许推此分支；推送前必须 `git pull --rebase origin bot/daily` |
| `feature/*` | 任何人 | 编辑部的大改动（改版、重构） | 完成后开 PR 进 main |

## 二、每日合并流程（编辑部执行）

1. Bot 在 `bot/daily` 完成当日推送后，编辑部（人工或代理）执行审查：
   - `git fetch origin && git log origin/main..origin/bot/daily --oneline`
   - 抽查数据改动（papers-data.js 条数、feed.xml 条目数、页面临时改动）
   - 若 Bot 改动了 `insight.html` / `index.html` / `assets/style.css`：**必须人工阅读全文后**方可合并
2. 合并方式（二选一）：
   - `git checkout main && git merge origin/bot/daily --no-ff -m "合并 Bot 每日维护 $(date +%F)"`，然后 `git push`
   - 或通过 GitHub PR 界面合并（保留可追溯的审查记录）
3. 合并后本地验证：`python3 -m http.server` + Playwright 双视口巡检（见仓库验证惯例）
4. 若 Bot 改动有问题：在 `bot/daily` 上直接修复或回退对应提交，再合并；**不在 main 上修**

## 三、Bot 改造清单（运行环境待确认，改造前 Bot 一律只读）

在 Bot 运行环境中落实以下四点，未落实前建议暂停 Bot 定时任务：

1. **推送目标**：`origin bot/daily`（不再有 `origin main`）
2. **推送前置**：`git fetch origin && git rebase origin/bot/daily`，失败即中止本次运行并告警，**禁止 force push**
3. **写入边界**（建议）：Bot 只写数据与内容文件——
   `papers-data.js`、`papers.html`、`news.html`、`benchmarks.html`、`assets/feed.xml`、`assets/search-index.js`
   **禁写**：`index.html`、`insight.html`、`about.html`、`assets/style.css`、`OPS.md`
   （Bot 若对上述禁区文件有改动建议，写入 `bot/daily` 分支上的 `SUGGESTIONS.md`，由编辑部决定是否采纳）
4. **提交身份**：保持 `AIVC Insight Bot <bot@aivc.news>`，提交信息以 `[bot]` 开头

## 四、编辑部（人工）操作规程

1. 大改动走 `feature/*` 分支 + PR；社论、栏目改版等重大内容改完后本地验证再推
2. 推 main 前：`git pull --rebase origin main`（main 有保护时通过 PR 流程）
3. 任何改动不得绕过本地验证（Playwright 桌面 1280 / 移动 390 双视口、JS 错误、横向溢出）

## 五、应急

- **Bot 失控/重复推送**：暂停 Bot 定时任务 → `git push origin --delete bot/daily` 或回退提交 → 通知编辑部
- **main 被污染**：`git revert` 污染提交后推 PR；Cloudflare Pages 保留历史部署可随时回滚
- **写入方争议**：以本文件为准；本文件修改须经编辑部（editor@aivc.news）确认

---

*本规范随仓库版本化管理。变更记录见 git log。*
