# AGENTS.md — 所有 AI 会话必读

> 你是本仓库的写入方之一。本仓库由多个会话/主体并行维护，**不读此文件就动手 = 制造事故**。
> 完整规范：[OPS.md](./OPS.md)（写入前必读）。

## 三条铁律（违反=服务端拒绝或人工回滚）

1. **绝不直推 `main`。** main 已启用分支保护（`enforce_admins=true`），任何直推会被 GitHub 拒绝（GH006）。你的产出推到 `bot/daily` 分支或开 `feature/*` 分支。
2. **推送前必须 `git fetch origin && git rebase origin/<你的分支>`。** 禁止 `--force`。
3. **只写你的地盘。** 本会话默认身份是「编辑部」，可写全部文件但走 PR；若你是「Bot 身份」，禁写 `index.html`、`insight.html`、`about.html`、`assets/style.css`、`OPS.md`、`AGENTS.md`——对这些文件的建议写入 `bot/daily` 分支的 `SUGGESTIONS.md`。

## 你是谁

- 提交信息以 `[editorial]` 或 `[bot]` 前缀标明身份
- 作者身份：编辑部 `AIVC Insight <editor@aivc.news>` / Bot `AIVC Insight Bot <bot@aivc.news>`

## 每日链路

```
你的会话产出 → 推 bot/daily 或 feature/* → PR → 合并进 main → Cloudflare 自动部署
```

合并由「主编会话」统一执行（每日上午审查）。你若在 `bot/daily` 上完成推送，即视为当日产出已交付，**不要自行合并、不要直推 main**。

## 事故备忘（2026-10-24）

两个会话并行裸写 main 导致分叉。自此立规：main 是编辑部唯一出口，其余一切产出走分支 + PR。
