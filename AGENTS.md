# AGENTS.md — 所有 AI 会话必读

> 你是本仓库的写入方之一。本仓库由多个会话/主体并行维护，**不读此文件就动手 = 制造事故**。
> 完整规范：[OPS.md](./OPS.md)（写入前必读）。**本文件与 OPS.md 冲突时，以 OPS.md 为准。**

**修订：2026-10-28（与 OPS.md 第二版对齐）。** 上一版仍写着 `bot/daily` 分支模型与「Bot 禁写禁区文件」，与 OPS.md 第二版（2026-10-27）自相矛盾，已由编辑部统一——单一事实源是 OPS.md，本文件只做摘要，不再另立规则。

## 四条铁律（违反 = CI 拦截或人工回滚）

1. **绝不直推 `main`。** main 已启用分支保护（`enforce_admins=true`，required status check = `check`），直推会被 GitHub 拒绝（GH006）。
2. **从最新 `origin/main` 建当日分支。** 命名 `bot/<type>-YYYY-MM-DD`（Bot）或 `feature/<topic>`（编辑部），禁止使用已废弃的长期分支 `bot/daily`。推送前 `git fetch origin`，禁止 `--force`。
3. **提交前本地必须跑 `python3 tools/validate.py` 且 0 error。** 带错提交会在 CI 被拦下，等于白跑。
4. **只写你的地盘，但「地盘」不等于「禁写」。** 见下方写入边界。

## 写入边界（依据 OPS.md §三）

| 身份 | 可写范围 | 说明 |
|---|---|---|
| **编辑部** | 全部文件 | 走 PR；重大改版可直推需谨慎 |
| **Bot** | 数据与内容层直写；页面与规范层（`index.html`、`insight.html`、`about.html`、`assets/style.css`、`OPS.md`、`AGENTS.md`）**可经 PR 修改，但必须经编辑部审查方可合并** | 重大改动（首页改版、样式体系变更、规范文件修改）须先在 `SUGGESTIONS.md` 提出并经批复 |

> 曾经的「禁区绝对禁写」规则已于 2026-10-27 废止。它导致 Bot 无法修复自己造成的问题、只能绕道 `SUGGESTIONS.md`，是 10-25 积压事故的直接成因。改为「可改但必过审」后，审查责任由 PR + CI + 每日晨审承担。

## 你是谁

- 提交信息以 `[editorial]` 或 `[bot]` 前缀标明身份
- 作者身份：编辑部 `AIVC Insight <editor@aivc.news>` / Bot `AIVC Insight Bot <bot@aivc.news>`

## 每日链路

```
Bot 定时任务 → 当日分支 bot/<type>-DATE → validate 全绿 → 开 PR
                                                    ↓
                              07:00 编辑部晨审（CI + 校验 + diff 审查报告）
                                                    ↓
                              总管人工决断合并 → Cloudflare 自动部署 aivc.news
```

**Bot 不得自行合并 PR。** 合并权属编辑部，由晨审报告支撑人工决断。

## 环境须知（2026-10-28 新增）

定时任务可能运行在**全新沙箱实例**：`/workspace/aivc-insight` 未必存在，前序任务写的文件（如 `.intel/` 简报）也**不会跨实例共享**。因此：

- 任何任务开始前必须自行确保仓库存在（缺失则 `git clone`），不要假定 `cd` 一定成功
- 不要设计「A 任务写文件、B 任务读文件」的交接——唯一可靠的共享介质是 **GitHub 仓库本身**
- 需要跨任务传递信息时，走分支/PR/Issue，不要走本地文件

## 事故备忘

- **2026-10-24**：两个会话并行裸写 main 导致分叉。自此立规：main 是唯一出口，其余走分支 + PR。
- **2026-10-25**：Bot 日更积压在 `bot/daily` 无人合并，站点「看起来没更新」。教训：产出必须开 PR 并被审查。
- **2026-10-26**：Bot 23:15 建 PR、23:28 自行合并，全程无审查。教训：Bot 禁自合，改为晨审 + 人工决断。
- **2026-10-28**：晨审任务因 `/workspace/aivc-insight` 不存在而 cd 失败，三个任务环境阻断。教训：任务必须环境自愈，且失败必须显式报告，不得沉默。
