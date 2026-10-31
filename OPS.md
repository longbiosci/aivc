# AIVC Insight 仓库写入规范（OPS）

> 本文件是本站内容生产的唯一权威操作规程。所有写入方（编辑部、AIVC Insight Bot、协作者）必须遵守。
> 制定日期：2026-10-25。修订：2026-10-27（第二轮）。
> 修订背景：10-25 编号撞车事故（两个分支各自新增 p86–p89/p86–p92）与 10-26 PR #8 自合事故（Bot 建 PR 后 13 分钟内自行合并，无任何审查）。核心变化：分支模型改为「当日分支 + PR + CI 硬门槛 + 每日晨审」；禁区文件由「禁写」改为「可经 PR 修改」。

## 一、分支模型

| 分支 | 所有者 | 用途 | 规则 |
|---|---|---|---|
| `main` | 编辑部（editor@aivc.news） | 唯一对外部署分支，Cloudflare Pages 自动部署 | **禁止直接 push**（分支保护：必须经 PR 且 CI 校验通过） |
| `bot/<type>-YYYY-MM-DD` | AIVC Insight Bot（bot@aivc.news） | Bot 当日产出，type ∈ content / ops / deep | 从 `origin/main` 建立；推分支 + 开 PR；**Bot 自身禁止合并**；达标 PR 由独立自动化任务按 §4.2 自动合并 |
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

## 三之二、岗位与写入边界（2026-10-31 修订：消除三岗位职责重叠）

> 修订背景：10-31 两个 PR 各自在 `search.html` 与 `benchmarks.html` 上重复写入，导致同一处缺逗号故障被制造两遍、Cascade 卡片被收录两张。复盘发现根因不在执行，而在**三份任务书的职责表里，同一批文件出现在三张名下**：
>
> | 文件 | content 任务书写了 | ops 任务书写了 | deep 任务书写了 |
> |---|---|---|---|
> | `search.html` IDX 索引 | 「同步更新」 | 「检查是否覆盖全部文献」 | — |
> | `benchmarks.html` | 「更新」 | — | 「检查并更新」 |
> | `assets/feed.xml` | 「同步更新」 | 「同步检查」 | — |
>
> 三张表都认为自己在管，谁也认为对方会管。本章把职责改成**互斥**。

### 3.2.1 唯一归属（每个文件只有一个写者）

| 文件 | 唯一写者 | 其他岗位只能做 |
|---|---|---|
| `assets/papers-data.js`、`papers.html` | content | 只读 |
| `assets/fulltext-data.js`（全文可达性） | content，且**只能用 `python3 tools/fulltext.py` 生成，禁止手改** | ops/deep 只跑 `--check` 巡检并报告失效项，不改文件 |
| `assets/feed.xml`、`search.html`（IDX 索引）、`sitemap.xml`、`index.html` 最新情报、`news.html` | content | 只读 |
| `companies.html` | content | 只读 |
| `insight.html`（每日观察） | deep | 只读 |
| `benchmarks.html` | deep | 只读 |
| `assets/style.css`、`paper.html`、`glossary.html` 等页面壳 | ops | 只读 |
| `tools/*.py`、`.github/workflows/*` | ops | 只读 |
| `OPS.md`、`AGENTS.md`、`SUGGESTIONS.md` | 编辑部（Bot 只可提建议） | — |

**跨岗位发现问题时的唯一动作**：写进 PR 描述的「发现但未修」清单 + 报告末尾，**不自己动手**。归属方次日处理。

### 3.2.2 顺序即隔离

content 00:30 → ops 02:00 → deep 03:30，三者**串行**。后一岗从 `origin/main` 建分支时，前一岗若已合并，天然继承其成果；若前一岗**未合并**（CI 红或待审核），后一岗照常开工，但**必须在报告中明示「上游 PR #x 未合并，本次基于旧基线」**。

### 3.2.3 并行写入门禁（机器强制）

`tools/preflight_conflicts.py` 在 CI 中比对「本 PR 改动文件」与「其余 open PR 改动文件」，重叠即红。归位后正常情况不应再红；**红了说明归位规则被违反或有新文件加入，按 3.2.1 认领后再动手**。

### 3.2.4 新增文献的连带动作（漏一步 CI 就红）

`assets/papers-data.js` 加一篇文献后，**必须同一次提交里**跑一遍：

```bash
python3 tools/fulltext.py     # 重新生成 assets/fulltext-data.js
```

`validate.py` 第 18 项会校验两侧 id 集合完全一致——漏生成会直接报「fulltext-data.js 漏掉文献」，PR 过不了门禁。这是有意的硬约束：宁可提交时被拦，不要让新文献在站点上「点进去发现没有全文入口」。

### 3.2.5 全文策略：二手不托管，一手做转录（2026-10-31 定，同日修订）

**不托管、不镜像论文 PDF。** 理由不变：6 篇订阅闭源托管即侵权；110 篇 PDF 累计数百 MB，
仓库与 Pages 带宽都不划算；原文权威地址是 DOI，由出版方永久解析。

**但「站内读不到全文」是产品缺陷，不是版权约束。** 所以另建 `kb/` 全文库：
把**许可明确的开放获取**论文从 JATS XML 转录成站内可读 HTML，读者不必跳出站点。

| 层级 | 位置 | 写者 | 说明 |
|---|---|---|---|
| 全文库正文 | `kb/*.html` | content（只能由 `tools/build_kb.py` 生成，禁止手改） | 只收 CC BY / CC0 / CC BY-NC / CC BY-NC-ND |
| 检索索引 | `assets/kb-index.js` | 同上 | 由生成器产出 |
| 可达性分级 | `assets/fulltext-data.js` | content（`tools/fulltext.py` 生成） | 三态 pdf/page/closed |

**转录的三条硬规矩**（违反即下架该篇）：

1. **只转许可明确的**。`tools/build_kb.py` 里的 `ALLOW_LIC` 是白名单；许可字段缺失的一律不转录正文，
   只给摘要与章节大纲，并明确写「许可不明，不转录」。
2. **只做格式转换，不改文字**。XML→HTML 只做标签替换与章节标号，不删句、不改写、不重排段落。
   标题全大写转 Title Case 属排版规范化，且用缩写表保护 AIVC / UR / scRNA 这类专有写法。
3. **每篇页首必须标注**许可类型、来源站点、原文 DOI，并提供「回到本站解读」与「原文地址」两个出口。

一旦收到权利人异议：先撤下该篇正文（保留摘要与链接），再核许可，不要先争论。

全文可达性三态（pdf / page / closed）的定义见 `assets/fulltext-data.js` 头部注释；
全文库的许可白名单见 `tools/build_kb.py` 的 `ALLOW_LIC`。

### 3.2.6 投稿口：读者把全文投进来（2026-10-31 定）

**问题**：110 篇里 79 篇站内读不到正文。境外抓取只能覆盖 PMC OA 子集（bioRxiv 全站 403），
剩下的只能靠人——而「欢迎发邮件」这条路没有任何反馈，投了不知道有没有用。

**做法**：文献详情页生成带编号的**投递单**，读者把全文作为附件发到编辑部邮箱 →
后台按编号取件 → 机器判许可与归属 → 通过的转成站内全文进 `kb/`，结果写回页面。

| 环节 | 位置 | 写者 |
|---|---|---|
| 前端投稿口 | `assets/kb-inbox.js`、`assets/kb-inbox-cfg.js`（**无凭据**） | ops |
| 取件与入库 | `tools/uploader.py`、`tools/inbox.py` | ops |
| 邮件落地区 | `drops/*.eml`（**不入库**，在 `.gitignore` 里） | ops |
| 隔离区 | `inbox/<批次>/`（**不入库**） | 只有 `tools/inbox.py` 能写 |
| 回执 | `assets/kb-inbox-data.js` | 只由 `tools/publish_inbox.py` 生成 |

**四条硬规矩**：

1. **前端不得携带任何凭据**。静态站把写权限放进网页源码等于公开给人用，GitHub 密钥扫描也会
   拒收这种提交；GitHub 的 issue 写接口匿名一律 401，想匿名提交就得把令牌放回前端。这两条路
   都试过且都被否决，**通道固定为邮件（mailto）**。`validate.py` 第 20 项会扫 `ghp_` / `github_pat_`，
   并要求 CSP 里不得再出现 `api.github.com`（残留即说明旧通道没清干净）。
2. **三道判定，没有第四种结局**：允许 / 拒绝 / 待确认。许可不明的一律「待确认」，不进正文。
3. **归属不符即退回**。正文里找不到该篇 DOI 或标题前 40 字符的，按投错处理，写明原因，
   不猜、不并、不静默覆盖已有全文（新稿字数低于现有 95% 不覆盖）。
4. **原文不进仓库**。`drops/` 与 `inbox/` 都在 `.gitignore` 里；`inbox/**` 带 `filter=kbscrub`，
   落盘前逐字节扫 `<!--` / `-->`，命中即拒收，不假定清道过滤一定生效。

投稿口入库的篇章，`kb/<id>.html` 页首必须写明「由读者投稿并经本刊核验许可」——
与外链转录区分开，读者有权知道这份开放获取是谁说的。


## 四、合并流程（2026-10-30 修订：新增自动合并通道，消除上线卡点）

> 修订背景：10-29 至 10-30 的 4 个 PR 全部积压两天无人合并，站点两天未更新（与 10-25 事故同型）。根因是「合并」这一步没有任何自动化提示，完全依赖总管记得手动点击。经总管 2026-10-30 授权，改为「机器审查全过 = 自动合并，例外才找人工」。

### 4.1 三关审查（不变，由自动化任务执行）

对全部 open `[bot]` PR 执行：① CI `check` 状态；② 本地 `python3 tools/validate.py` 复核（0 error）；③ 内容 diff 审查（事实/观点分离、来源标注、编号八处同步、禁区文件改动合理性、有无越界写入）。

> **2026-10-31 补充：①② 的结论只认「独立复跑」，不认产出方自述。** 每个 Bot 任务书里的「运行 validate 必须 0 error」只是**产出方自检**，不构成通关凭证——10-31 #25 自检通过、CI 也绿，却带着 4 处内联脚本语法错误，因为当时的校验器漏检内联脚本、且产出方用的就是同一把有缺陷的尺子。**自查不算数，复跑才算数。**

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

### 4.5 失败可见（2026-10-31 新增）

每次运行结束**必须**调用 `python3 tools/report_run.py`（见 `.intel/README.md`）落账，状态四选一：

| status | 含义 | 要求 |
|---|---|---|
| `ok` | 有产出并已推送 / 已开 PR | — |
| `noop` | 确无值得发布的内容，主动不提交 | 须写明「确无内容」的判断依据 |
| `blocked` | 环境或依赖阻断 | **exit 1，必须点名报警** |
| `failed` | 执行出错 | **exit 1，必须点名报警** |

**红线**：`blocked` 不得写成 `noop`。把阻断报成「今日无内容」等于虚假绿灯——2026-10-28 已发生过一次（当日晨审因此沉默），不得复发。
晨审读不到落账时（沙箱不跨实例），以 GitHub PR / Issue 为准，并在报告中说明「无法读取落账」。


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
