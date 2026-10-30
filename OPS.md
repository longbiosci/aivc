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

## 四、合并流程（2026-10-30 修订：新增自动合并通道，消除上线卡点）

> 修订背景：10-29 至 10-30 的 4 个 PR 全部积压两天无人合并，站点两天未更新（与 10-25 事故同型）。根因是「合并」这一步没有任何自动化提示，完全依赖总管记得手动点击。经总管 2026-10-30 授权，改为「机器审查全过 = 自动合并，例外才找人工」。

### 4.1 三关审查（不变，由自动化任务执行）

对全部 open `[bot]` PR 执行：① CI `check` 状态；② 本地 `python3 tools/validate.py` 复核（0 error）；③ 内容 diff 审查（事实/观点分离、来源标注、编号八处同步、禁区文件改动合理性、有无越界写入）。

### 4.2 自动合并通道（新增）

满足以下**全部**条件的 PR，由晨审/巡检自动化任务直接合并（merge commit），无需人工点击：

1. CI `check` 绿；
2. 本地 validate 0 error；
3. 类型为 `bot/content-*`（纯数据追加）或 `bot/ops-*`（技术修复，不含版式体系变更）；`bot/deep-*` 因常涉及观点内容与规范表述，默认仍由人工决断，但自动化任务必须先出齐审查结论与建议；
4. 与 main 无冲突。有冲突时，自动化任务可在对应当日分支上 `merge origin/main` 解冲突后重推（解决原则：内容类按时间序融合、两说并留；规范/事实表述类冲突不得择一执行，按 SUGGESTIONS 机制报请裁定），重跑 validate 与 CI 全绿后方可合并；
5. 内容审查无「需修改」结论（如跨 PR 的事实性矛盾、待核实项未标注等）。

不满足任一条件 → 保持 open，晨审报告列出具体问题清单，由总管决断。

### 4.3 职责分离（不变的红线）

- **Bot 产出任务自身仍禁止合并自己的 PR**。合并动作只能由独立的晨审/巡检自动化任务或总管执行——产出与合并必须是两个主体。
- 自动化合并须在 PR 评论中留痕：三关结论与合并依据，保证可追溯。
- 合并后抽验（Playwright 桌面 1280 / 移动 390 双视口、JS 错误、横向溢出）由自动化任务执行。

### 4.4 频率

- 晨审任务每日 07:00 固定跑一轮（汇总报告 + 对达标 PR 执行自动合并）。
- `bot/content-*` 类 PR 开出后，巡检可即时审查即时合并，**不必等次日晨审**——目标是「Bot 提交 → 当小时内上线」。
- Bot PR 有问题：在对应当日分支上修复或新开修复 PR，**不在 main 上直接修**。

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
