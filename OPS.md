# AIVC Insight 仓库写入规范（OPS）

> 本文件是本站内容生产的唯一权威操作规程。所有写入方（编辑部、AIVC Insight Bot、协作者）必须遵守。
> 制定日期：2026-10-25。修订：2026-10-27（第二轮）。
> 修订背景：10-25 编号撞车事故（两个分支各自新增 p86–p89/p86–p92）与 10-26 PR #8 自合事故（Bot 建 PR 后 13 分钟内自行合并，无任何审查）。核心变化：分支模型改为「当日分支 + PR + CI 硬门槛 + 每日晨审」；禁区文件由「禁写」改为「可经 PR 修改」。

## 一、分支模型

| 分支 | 所有者 | 用途 | 规则 |
|---|---|---|---|
| `main` | 编辑部（editor@aivc.news） | 唯一对外部署分支，Cloudflare Pages 自动部署 | **禁止直接 push**（分支保护：必须经 PR 且 CI 校验通过） |
| `bot/<type>-YYYY-MM-DD` | AIVC Insight Bot（bot@aivc.news） | Bot 当日产出，type ∈ content / ops / deep | 从 `origin/main` 建立；推分支 + 开 PR；**禁止合并 PR**（由编辑部晨审后人工合并） |
| `feature/*` | 任何人 | 编辑部的大改动（改版、重构、规范修订） | 完成后开 PR 进 main |

## 二、发布纪律（所有写入方；机器可校验部分以 CI 为准）

1. **基线**：动工前 `git fetch origin`，从 `origin/main` 建立当日分支（`git checkout -B <branch> origin/main`）。禁止基于本地旧状态、未合并的前序分支或过期提交开工
2. **编号追加制**：新文献编号从 `assets/papers-data.js` 当前最大编号 +1 起递增。改编号/重映射时，以下八处必须同步：`papers-data.js`、`papers.html`、`search.html`、`index.html`、`news.html`、`feed.xml`、`sitemap.xml`、`further[]` 交叉引用
3. **校验关卡（硬门槛）**：提交前运行 `python3 tools/validate.py`，必须全绿（0 error）。main 分支保护已启用 required status check（上下文 `check`），**校验红 = PR 无法合并**
4. **提交身份**：Bot 保持 `AIVC Insight Bot <bot@aivc.news>`，提交信息以 `[bot]` 开头，注明日期与一句话摘要
5. **禁止事项**：直推 main；Bot 自合 PR；force push；带 error 提交；绕过 CI 合并

## 三、写入边界（2026-10-27 修订：禁区文件可经 PR 修改）

1. **内容与数据文件**（Bot 可直接写）：`papers-data.js`、`papers.html`、`news.html`、`benchmarks.html`、`companies.html`、`assets/feed.xml`、`search.html`、`sitemap.xml`、`robots.txt`
2. **原禁区文件**（`index.html`、`insight.html`、`about.html`、`assets/style.css`、`OPS.md`、`AGENTS.md`）：**不再是绝对禁写**。Bot 可在当日分支修改并随 PR 提交，但必须经编辑部审查方可合并；重大改动（首页改版、样式体系变更、本文件修改）由编辑部人工确认后执行
3. **跨任务建议**：不适合放入当日 PR 的改动建议（纯样式方案、长期 backlog），Bot 写入 `SUGGESTIONS.md`，由编辑部批复后落地

## 四、每日合并流程（编辑部执行）

1. 每日 08:30「编辑部晨审」自动化任务汇总全部 open `[bot]` PR：CI 状态、本地 `tools/validate.py` 复核、diff 摘要与内容质量审查结论
2. 编辑部（总管）根据晨审报告逐 PR 决断：合并 / 打回修改 / 保持开放
3. 合并方式：GitHub PR 合并（保留可追溯的审查记录）；合并后抽验（Playwright 桌面 1280 / 移动 390 双视口、JS 错误、横向溢出）
4. Bot PR 有问题：在对应当日分支上修复或新开修复 PR，**不在 main 上直接修**

## 五、编辑部（人工）操作规程

1. 大改动走 `feature/*` 分支 + PR；社论、栏目改版等重大内容改完后本地验证再推
2. 推 main 前：`git pull --rebase origin main`（main 有保护时通过 PR 流程）
3. 任何改动不得绕过本地验证（Playwright 桌面 1280 / 移动 390 双视口、JS 错误、横向溢出）

## 六、应急

- **Bot 失控/重复推送**：暂停 Bot 定时任务 → 删除对应当日分支（`git push origin --delete <branch>`）→ 通知编辑部
- **main 被污染**：`git revert` 污染提交后推 PR；Cloudflare Pages 保留历史部署可随时回滚
- **CI 误拦合理改动**：修正 `tools/validate.py` 判定规则（走编辑部 `feature/*` 分支 PR），**不得绕过 CI 合并**
- **写入方争议**：以本文件为准；本文件修改须经编辑部（editor@aivc.news）确认

---

*本规范随仓库版本化管理。变更记录见 git log。*
