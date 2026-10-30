# SUGGESTIONS.md — Bot 对「禁区文件」的改动建议

> 依据 [OPS.md](./OPS.md) 第三节：Bot 禁写 `index.html`、`insight.html`、`about.html`、`assets/style.css`、`OPS.md`、`AGENTS.md`。
> 本文件记录 2026-10-25 每日技术运维中，**需要编辑部确认采纳后手工落地**的改动。
> 提交身份：AIVC Insight Bot <bot@aivc.news>；分支：`bot/daily`。

---

## 建议 1（高优先级）：为文献库长列表补折叠样式，缓解内容增长带来的阅读负担

### 背景（实测数据）

`papers.html` 已收录 **85 篇**文献，正文约 1.9 万字。Playwright 实测页面高度：

| 视口 | 折叠前页高 | 折叠后页高 | 变化 |
|---|---|---|---|
| 390×844（移动） | 19496 px（≈23.1 屏） | 12952 px | −34% |
| 1440×900（桌面） | 12280 px | 8580 px | −30% |

页面已有「分组锚点目录 + 分组筛选 + 关键词检索 + 回到顶部」，唯一缺的是**按组折叠**。建议补上。

### 需要编辑部加到 `assets/style.css` 的样式

按本仓规范「所有页面样式统一写在 style.css、媒体查询置于样式表末尾」，建议插入位置为
`.pgroup{scroll-margin-top:64px}` 之后、`/* 回到顶部 */` 之前（即现有两条 `@media` 之前）：

```css
/* 长列表分组折叠：文献量增长后，每组默认展示前若干条，其余按需展开 */
.paper.folded{display:none}
.pgroup.expanded .paper.folded{display:block}
.morebtn{display:inline-block;margin:12px 0 2px;padding:5px 13px;font-family:var(--sans);
  font-size:12.5px;line-height:1.6;color:var(--accent);background:var(--paper);
  border:1px solid var(--line);border-radius:2px;cursor:pointer;letter-spacing:.3px}
.morebtn:hover{border-color:var(--accent);background:var(--accent-soft);text-decoration:none}
.morebtn::after{content:" ▾";font-size:10px}
.pgroup.expanded .morebtn::after{content:" ▴";font-size:10px}
.morebtn.hide{display:none}
```

并在 `@media(max-width:860px)` 段落内追加（保证窄屏触控友好）：

```css
  /* 分组展开按钮：窄屏整行铺满，便于点按 */
  .morebtn{width:100%;text-align:left;padding:9px 14px;font-size:13.5px}
```

### 配套说明

`papers.html` 的折叠脚本**已经上线**（本次 Bot 提交），并做了能力检测：

- 检测到上述 `.paper.folded{display:none}` 规则存在 → 启用折叠，每组默认 8 条，其余出现「展开剩余 N 篇」按钮；
- 检测不到 → **自动跳过折叠**，页面保持原样，**不会出现点了没反应的无效按钮**。

因此**样式可以先不落地，不会有破版风险**；落地后折叠自动生效，无需再改 HTML/JS。
检索或分组筛选时脚本会自动展开各组，避免命中项被折叠隐藏。

---

## 建议 2（中优先级）：修正 sitemap.xml 中 85 条文献详情页 URL

`sitemap.xml` 现有 95 条 URL，其中 85 条写为：

```
https://aivc.news/paper?id=p01
```

而仓库中的实际页面是 `paper.html`。提交信息注明「采用 308 归一化 URL」，
但仓库内**未见 `_redirects` 文件**（Cloudflare Pages 的重定向需由 `_redirects` 或面板规则提供，
现有 `_headers` 只管响应头、不做跳转）。

**请编辑部确认二选一：**

1. 若确实已在 Cloudflare 面板配置了 `/paper?id=*` → `/paper.html?id=*` 的 308 规则 → **本条可忽略**；
2. 若无该规则 → 这批 URL 会 404，建议改为 `https://aivc.news/paper.html?id=p01`，或新增 `_redirects`：

```
/paper?id=:id  /paper.html?id=:id  308
```

批量修正命令（编辑部执行）：

```bash
sed -i 's|https://aivc.news/paper?id=|https://aivc.news/paper.html?id=|g' sitemap.xml
```

---

## 建议 3（低优先级）：搜索索引从「节选」扩到「全量」

`search.html` 的 `IDX` 目前 114 条，其中文献库部分为**节选**（85 篇中索引约 41 条），
其余依赖 `papers.html` 页内检索兜底。本次已补入 4 条此前遗漏的高价值条目
（p70 Geroscience、p72 扰动模型系统比较、p22 LangCell、p40 VCC 指标复盘）。

若希望全站搜索可直达任意一篇，建议改为由 `assets/papers-data.js` 自动生成索引
（新增 `assets/search-index.js`，OPS.md 第三节已将其列入 Bot 可写清单），
届时 Bot 可在每次文献入库时同步重建索引，不再有遗漏。

---

*本文件由 AIVC Insight Bot 每日技术运维生成，仅供编辑部参考，不自动生效。*

---

## 本轮每日内容更新的交接说明（2026-10-25）
> 由本轮「每日内容更新」提交附带，供编辑部合并前复核。
> 产出分支：`bot/daily`（基于 `a8bdc7c`），提交：`[bot] 每日内容更新`。

## 一、本轮实质改动

| 文件 | 改动 |
|---|---|
| `assets/papers-data.js` | 85 → **92** 条（新增 p89–p92，并补回 p86–p88） |
| `papers.html` | 补回 p86–p88，插入 p89–p92；页首计数 85 → 92，日期更新至 2026-10-25 |
| `search.html` | IDX 110 → **112** 条（新增 10 条 + 清除基线自带重复 8 条） |
| `index.html` | 最新情报置入 7 条头条，LATEST 标注更新至 2026-10-25 |
| `news.html` | lede 改写 + 新增 8 张卡片 |
| `companies.html` | 新增核查窗口横幅；insitro、百图生科实质更新；Xaira 补赛道对照；其余 4 家标注"本轮窗口无新披露" |
| `benchmarks.html` | VCC 卡片补投稿截止与报名口径分歧；新增空间转录组分割基准卡 |
| `assets/feed.xml` | 新增 5 条 item（XML 已校验） |

## 二、需编辑部人工复核（禁区文件）

1. **`index.html`（Bot 禁区）**：本次因"每日更新首页统计与最近更新"的指令而改动，共 2 处——`<h2>最新情报` 的 `LATEST` 后缀加日期、`<ul class="hl">` 顶部插入 7 条 `<li>`。**请合并前通读全文确认措辞与排序。**
2. **`sitemap.xml` 未改动（有意的）**：`bot/daily` 上的站点地图仍是 10 条的旧版；main 上是 95 条版（含 85 个文献详情页）。文献库增至 92 篇后，**main 的 sitemap 需补 p86–p92 共 7 条 URL**，本分支不便代改（会覆盖 main 的新版）。
3. **`assets/style.css` 未改动**：本轮新增内容全部复用既有类（`.paper` / `.card` / `.submitbox` / `.src` / `.verdict`），学术期刊排版风格未受影响。

## 三、两处待核实的口径分歧（已在页面内标注）

1. **insitro CTRO-1013 进临床时间**：站内原记"预计 2027 年初"，2026-10-25 新浪财经报道为"计划 2026 年内推进至首次人体试验"。**未覆盖旧值**，两说并存并标注"口径分歧 / 待核实"。
2. **VCC 2026 报名规模**：赛事方自述 1,800+，另有"1,082 支队伍"的说法。两者同页并列并标注待核实。

## 四、事故提示：p86–p88 曾被误删，本轮已补回

提交 `5918bba`（"每日技术运维"，2026-10-24 23:16）在做站内 URL 规范化（`/paper?id=` → `paper.html?id=`、canonical 加 `.html`）时，**同时删除了 `papers-data.js` 中的 p86（SIMCO）、p87（scButterfly-B 自编码器基准）、p88（虚拟空间转录组不确定性）三条文献**，并使文献库计数从 88 回落到 85；`news.html` 中对应的 SIMCO 与虚拟空间转录组卡片也在同一次改动中消失。

本轮基于现有 85 条底稿，将三条**按原内容补回**（URL 已转换为新的 `paper.html?id=` 规范），并追加今日 4 篇，故总数为 92。

**请编辑部确认**：若该删除是刻意为之（例如 SIMCO 的"FDA 批准进临床"表述需重新核实），请回退本轮对 p86–p88 的补回——备份分支 `backup-my-work` 保留原始改动可供比对。

## 五、来源分级说明

本轮新增内容按四级标注：**同行评审**（Nature Methods ×2、Cancer Cell）、**预印本**（bioRxiv SPInfer，页面已明确标注未经同行评议）、**机构自述**（Warp Sciences、OpenAI 公告）、**二手报道**（新浪财经、经济观察报、TechCrunch）。所有数字均附来源与日期，未见原始出处的已标"待核实"。


---

## 编辑部批复（2026-10-26，总管签发）

**建议 1（折叠样式）——已采纳。** CSS 已落地 `assets/style.css`（`.paper.folded` / `.morebtn` 规则 + `@media(max-width:860px)` 窄屏整行按钮），折叠随脚本自动生效，无需再改 HTML/JS。

**建议 2（sitemap URL）——已核实，无需修改。** 编辑部实测线上三种归一化形式（`/paper?id=p01`、`/news`、`/companies`）均返回 200，Cloudflare 侧的 308 归一化规则存在。sitemap 继续使用归一化 URL。另：本轮合并后 sitemap 已补 p90–p96 共 7 条（99 → 106 条）。

**建议 3（搜索全量索引）——列入 backlog。** 下轮技术运维评估由 `assets/papers-data.js` 自动生成 `assets/search-index.js` 的方案（OPS.md 可写清单已覆盖该文件）；落地前维持「节选 + papers.html 页内检索」兜底。本轮编辑部已将机器人日更的 11 条索引人工补入（IDX 127 条）。

**p86–p88 补回——确认正确，并已完成编号收敛。** 核查结论：误删发生在 bot 分支的运维提交 `5918bba`（URL 规范化副作用），该提交从未合入 main，main 文献库不含这三篇，故「刻意删除」的假设不成立，补回正确。因本分支 p86–p92 与 main 已上线的 p86–p89（PIE / UniPert-G2CP / VCWM / Speciesformer）编号撞车，编辑部已将本分支 7 篇统一改编号为 **p90–p96**（SIMCO / scButterfly-B 基准 / 虚拟空间不确定性 / CauTrigger / 分割基准 / SPInfer / iPhenMap），papers-data.js、papers.html、search.html、index.html、news.html、feed.xml、sitemap.xml 内的链接与 `further` 交叉引用已同步更新；文献库总数 **96 篇，编号连续无断档**。

**两处口径分歧——维持「并存 + 待核实」处理。** insitro CTRO-1013 进临床时间（2027 年初 vs 2026 年内）与 VCC 2026 报名规模（1,800+ vs 1,082）均保持页面内双口径并列并标注，待赛事方/公司正式公告后更新。

**禁区文件 index.html——编辑部已通读整合。** 本分支 7 条头条已按日期排序插入「最新情报」（LATEST 更新至 2026-10-26），措辞经编辑部复核。

**后续协作约定。** 请 Bot 下次日更前先 `git fetch origin && git rebase origin/main`，并在提交说明中注明所改文件的基准 commit；文献编号沿用追加制（新篇从当前最大编号续），避免与 main 撞号。

---

## 编辑部第二轮批复（2026-10-26 深夜，总管签发）：协作机制升级——CI 强制校验已上线

**背景。** 本轮合并后复查发现：机器人日更的 7 篇文献在 `search.html` 检索索引中有 **3 条链接指错文献**（SIMCO→p94、scButterfly-B→p95、虚拟空间转录组→p96，均为重映射错位），用户搜索后点击会进入错误论文；另发现 p40 缺 `doi` 字段。此类错误靠人眼审查难以稳定拦截，故本轮将协作机制升级。

**已落地（本提交）。**

1. **`tools/validate.py`**——站点数据校验器，本地可跑：`python3 tools/validate.py`。覆盖 8 类合并级错误：JS 语法、编号断档/重复、条目字段完整性、sitemap 覆盖、`further[] 交叉引用有效性、全站 paper 链接有效性、**检索索引条目与文献标题/描述一致性**（专抓重映射指错）、papers.html 计数。
2. **`.github/workflows/validate.yml`**——每个 PR 与 main 推送自动运行该校验；**error 级问题 CI 直接失败，合并被拦截**。本提交的 PR 即为首例验证。
3. 修复上述 3 个错链 + p40 补 `doi:"10.48550/arXiv.2511.16954"`（沿用本站 arXiv 条目惯例）；修复后校验全绿（96 篇、0 error 0 warning）。

**后续协作约定（升级版，请 Bot 严格遵守）。**

1. **每次日更提交前，本地必须运行 `python3 tools/validate.py` 并确认全绿**；CI 会在 PR 上自动复核，红叉 PR 不予合并。
2. 文献编号继续追加制：先 rebase main，新篇从当前最大编号续（p97 起）。
3. **改编号/重映射时，`search.html` 索引、`papers.html`、`index.html`、`news.html`、`feed.xml`、`sitemap.xml`、`further[]` 七处必须同步**——本轮 3 个错链全部漏在 search.html，校验器第 7 项即专抓此类。
4. PR 标题统一前缀：`[bot] 每日内容更新` / `[bot] 每日技术运维`；编辑部承诺**日更 PR 当日审查**，不再积压。
5. 已合并的远程分支（feature/2026-10-25-daily、feature/daily-2026-10-26、feature/merge-bot-daily、bot/daily）本轮已清理，下次日更请从最新 main 切新分支。

---

## 编辑部第三轮批复（2026-10-27，总管签发）：协作机制第二轮升级——OPS.md 已修订，请以新版为准

**背景。** 10-26 夜间复盘发现：PR #8（深度维护任务）由 Bot 账号自建自合（23:15 创建、23:28 合并），未经任何审查；且四个定时任务的 prompt 仍写着「push origin main」，与实际执行的分支+PR 流程脱节；OPS.md 的「禁区禁写」规则与任务 prompt 的改禁区文件指令互相矛盾。

**已落地。** `OPS.md` 已修订为第二版（随本 PR 合入），核心变化：

1. **分支模型**：`bot/daily` 废弃，改为每日分支 `bot/<type>-YYYY-MM-DD`（type ∈ content/ops/deep），从 `origin/main` 建立，开 PR，**禁自合**
2. **禁区文件解除禁写**：`index.html` / `insight.html` / `about.html` / `assets/style.css` / `OPS.md` / `AGENTS.md` 不再绝对禁写，可经 PR 修改但必须过编辑部审查；纯建议仍写本文件
3. **CI 硬门槛**：main 分支保护启用 required status check（`check`），`tools/validate.py` 红 = PR 无法合并
4. **四个定时任务 prompt 已按新纪律重写**（当日分支、validate 全绿、编号追加制、禁直推禁自合；情报扫描改为只读，简报落 `/workspace/.intel/`）
5. **新增「编辑部晨审」任务**（每日 08:30）：自动汇总 open `[bot]` PR 的 CI/校验/diff 结论，由总管人工决断合并

**给 Bot 的提示**：本文件的「建议」通道继续有效，但日常产出一律走当日分支 + PR；遇 CI 红先修数据再提交，不要绕过。

---

## Bot 建议（2026-10-28 · 深度维护分支 `bot/deep-2026-10-28`）：三条协作/工具建议，请编辑部批复

**背景。** 本分支执行每日深度维护时发现三处「规范与实现打架」或「工具缺位」的情况，均不属 Bot 写入边界（OPS §3.1 未列 `tools/` 与 `_redirects`），故不在当日 PR 内自行落地，按 §3.3 走本建议通道。

**建议 1（工具）：新增「站点级」扩展自检，作为官方 CI 之外的第二道本地关卡。**
现行 `tools/validate.py`（编辑部 2026-10-27 落地，174 行，8 类检查）专注**文献数据一致性**，不覆盖**页面结构**。Bot 侧另有一份 537 行的扩展自检（本次临时使用，副本留存 `/workspace/.intel/tools/validate-extended.py`），额外覆盖 6 类：必需文件存在性、HTML 骨架（doctype/charset/viewport/lang/canonical + 标签配对）、**全站导航栏目覆盖与 active 唯一性**、**内部链接与页内锚点可达性**、静态资产引用、DOI 字面格式、声明计数与实际一致性。本次在 96 篇口径下实测：导航 11 页全覆盖、内链 427 条 0 断链、DOI 格式 0 非法、计数一致。
建议：由编辑部以 `feature/*` 分支评估合入（可拆为 `tools/validate-site.py`，CI 再加一步），避免与现行校验器抢占同一文件名。

**建议 2（规范冲突）：`sitemap.xml` 的 `/paper?id=` 写法维持现状，勿改。**
本站此前建议（本文件建议 2）提出把 sitemap 内 `https://aivc.news/paper?id=pNN` 改为 `paper.html?id=pNN`。本次复核结论是**该建议应撤回**：（a）站点部署在 Cloudflare Pages，无扩展名路径会自动解析到同名 `.html`，`/paper?id=pNN` 线上实际可达；（b）现行 `tools/validate.py` 第 4 项以 `f"paper?id={i}"` 硬匹配 sitemap，一旦改成 `paper.html?` 会**全量撞红、CI 拦截合并**。
若编辑部仍希望统一为显式 `.html`，请**三处同步**并经 `feature/*` 分支一次提交：改 sitemap 全量 URL、改 `tools/validate.py` 第 4 项匹配式、补 `_redirects`（`/paper?id=:id → /paper.html?id=:id 308`）。单改任何一处都会产生断链或 CI 红。Bot 本次已回退该改动，并同步撤回 `_redirects` 的新建。

**建议 3（方法）：DOI 可用性抽查请改用 Handle API，不要用 `https://doi.org/<doi>` 直连。**
`https://doi.org/<doi>` 的 HEAD/GET 在多数出版商处返回 **403（反爬）**，与「DOI 不存在」无法区分，据此做出的「DOI 失效」判断不可靠。正确信号是 DOI Handle API：`https://doi.org/api/handles/<doi>`（请求头 `Accept: application/json`），读 `responseCode`——**1 = 已注册，100 = 未找到**；doi 内含 `/` 需按 `safe="/"` 转义。
实测：本站静态 DOI 链接 104 个，其中 103 个 responseCode=1；唯一例外是本期新引的 **AI Agent 综述 DOI `10.20517/aiagent.2026.16`（查询返回 404 / 未注册）**。该文在出版商页面可正常打开（收稿 2026-05-12、接受 2026-10-15、发表 2026-10-27），属新刊 DOI 注册滞后，非伪引；本站已在 10-28 期观察的「待核实」与信源列表中如实标注。

---

## 编辑部批复（2026-10-28 · 对应上节三项建议与三项待审）

**建议 1（站点级扩展自检）——采纳，入口 backlog，规格已定。**
分拆为 `tools/validate-site.py`，**不并入** `validate.py`：避免单文件继续膨胀，也避免文献校验与页面结构校验的失败语义混淆。CI 里作为独立 step 运行，v1 观察期「失败不阻断、但必须在晨审报告显式列出」，观察一周确认零误报后升级为阻断。合入时在 `tools/README` 注明两套校验的边界：`validate.py` 管数据一致性，`validate-site.py` 管页面结构。
另：`/workspace/.intel/` 不是共享位置（见本节末条），那份 537 行副本请随 PR 提交进仓库内，别放在会被销毁的实例目录。

**建议 2（sitemap 维持 `/paper?id=`）——采纳，原建议正式撤回。**
理由成立：Cloudflare Pages 的归一化能兜住可达性，而 `validate.py` 第 4 项的硬匹配决定了单改必红。裁定：**sitemap 保持 `https://aivc.news/paper?id=pNN`，不改。** 若要统一为显式 `.html`，按你给的三处同步方案走，属独立技术债，不进日更。
已把这条写进技术运维与深度维护的任务指令：**遇到此类规范冲突一律写 SUGGESTIONS，不得自行改数据结构去迎合校验器。**

**建议 3（DOI 用 Handle API）——采纳，已即时生效。**
`doi.org/<doi>` 的 403 是反爬不是失效证据，这个纠正对。技术运维与深度维护的指令已改为查 `https://doi.org/api/handles/<doi>` 读 `responseCode`（1 已注册 / 100 未找到）。`10.20517/aiagent.2026.16` 判定「新刊注册滞后、非伪引」，维持现标注，下期复核。

**待审定夺 1：VCC 2025 复算数（0.341344 vs 归档冠军 0.340052）——保留，但必须带口径。**
作者自述口径 + 锚点系重建值，与当年赛事非同场竞技——这两个条件决定它不能作为「刷新冠军」陈述。裁定：**保留入库，标题与首段禁止出现「超越」「刷新」类表述，数字旁必须紧跟「作者自述口径、非同场竞技」限定语，并保留「待核实」。** 若下轮仍无第三方复现，降级为括号注释。

**待审定夺 2：OmicsLM v1（2026-05-07 提交，不在 24 小时窗口）——口径合适，维持。**
日更窗口是「过去 24-48 小时」，超窗内容只作背景进 `news.html`、不入文献库，这个处理正确。补一条执行细则：若该文有 v2 或正式发表版本落在窗口内，届时按新文献入库，并与本条互相 `further` 引用。

**待审定夺 3：OPS.md 与 AGENTS.md 禁写规则冲突——已裁定并修复。**
单一事实源是 **OPS.md 第二版**。AGENTS.md 中 `bot/daily` 模型与「禁区绝对禁写」条款已删除、`BOT-MIGRATION.md` 已标作废（PR #13，2026-10-28）。今后任何文档与 OPS.md 冲突，一律以 OPS.md 为准，并在 SUGGESTIONS 报出冲突点，**不得自行择一执行**。

**另：关于 `/workspace/.intel/`（给全体任务的更正）**
定时任务运行在**独立沙箱实例**，`/workspace` 不跨实例共享，`/workspace/.intel/` 这种「A 任务写、B 任务读」的交接方式**在架构上不成立**——10-28 凌晨情报扫描任务零产出、晨审任务 `cd` 失败，都是这个原因。已改为：情报扫描只输出报告、不落文件；内容更新自行扫描，不依赖任何本地简报；每个任务启动前自行确保仓库存在（缺失则 clone）。**跨任务传递信息唯一可靠的介质是 GitHub（分支 / PR / Issue）。**

---

## Bot 建议（2026-10-29 · 深度维护分支 `bot/deep-2026-10-29`）：三处规范与实现打架，附两种改法的连带影响

**背景。** 本站当日深度维护（insight.html 10-29 期观察 + benchmarks.html 数据更新 + 全站导航与 DOI 抽查）过程中发现三处「规范与实现不一致」。按 OPS.md §3.3 与编辑部 2026-10-28 批复（「遇规范冲突一律写 SUGGESTIONS，不得自行改数据结构去迎合校验器」），三处均**未在当日 PR 内自行落地**，交编辑部裁定。

### 建议 1（中高优先级 · 真实缺陷）：`tools/validate.py` 第 6 项声称校验 `feed.xml`，实际因路径写错静默跳过

**事实。** `tools/validate.py:117` 写的是：

```python
scan_files = sorted(ROOT.glob("*.html")) + [ROOT / "feed.xml", ROOT / "sitemap.xml"]
```

而仓库中 `feed.xml` 的实际位置是 **`assets/feed.xml`**（根目录无此文件）。紧随其后的循环有 `if not f.exists(): continue`，因此该路径被**静默跳过**——校验器第 6 项对 feed 的检查从未真正执行过。这与文件头文档字符串「6. 全站（*.html + feed.xml + sitemap.xml）paper 链接指向不存在的文献」不符，也与 OPS.md §2.2「改编号/重映射时，以下八处必须同步：…`assets/feed.xml`…」直接冲突——**八处清单里唯一一处处于校验盲区的，恰好就是 feed。**

**本次实测（供决策用）：** `assets/feed.xml` 现含 6 条 paper 链接（p93 / p94 / p95 / p97 / p98 / p99），**全部有效，无断链**。因此下面的改法 A 在**当前状态下不会立即产生新 error**。

**请编辑部二选一：**

- **改法 A（Bot 推荐）：修 `validate.py` 的路径。** 把 `ROOT / "feed.xml"` 改为 `ROOT / "assets" / "feed.xml"`。
  - *连带影响*：① 从此 feed 被真正纳入校验，未来任何编号重映射若漏改 feed，**CI 会转红并阻塞合并**——这正是 OPS §2.2 想要的效果；② 当前 6 条链接已验证有效，**改完即刻仍是全绿，无存量爆雷**；③ 若历史上曾有过 feed 漏改而后来被人工补上的情况，该路径修正只是补上了一道此前缺失的网，不改变任何现行数据。
  - *风险*：低。属纯路径修正，不改任何数据结构。
- **改法 B：不动校验器，改 OPS.md §2.2，把 `assets/feed.xml` 从八处同步清单中移除。**
  - *连带影响*：① feed 将长期成为编号重映射的**永久盲区**——RSS 订阅者会拿到指向错误文献的链接，且无人能靠 CI 发现；② 与 §2.2 的编号纪律目标（八处同步）相悖，需同时修改该条款的措辞以免自相矛盾；③ 省下一次 `feature/*` 分支改动。
  - *风险*：中。把一处已知的校验缺口规范化为「不校验」。

**Bot 倾向 A**，理由是本次已实测当前 feed 无断链，改 A 的即时代价为零，而收益是补上 OPS §2.2 要求的最后一道网。但**是否改、何时改由编辑部定**，Bot 未动该文件。

### 建议 2（低优先级 · 文档过期）：`SUGGESTIONS.md` 自身头部的规范描述仍是旧版

本文件开头仍写着：

> 依据 [OPS.md](./OPS.md) 第三节：Bot 禁写 `index.html`、`insight.html`、`about.html`、`assets/style.css`、`OPS.md`、`AGENTS.md`。
> 提交身份：AIVC Insight Bot <bot@aivc.news>；分支：`bot/daily`。

这两条**均已被 OPS.md 第二版（2026-10-27）废止**：禁区已改为「可经 PR 修改、必过审」，`bot/daily` 已改为每日分支 `bot/<type>-YYYY-MM-DD`。按编辑部 2026-10-28 裁定（对应 `AGENTS.md` 同类问题）：**单一事实源是 OPS.md，冲突文档一律以 OPS.md 为准，且不得自行择一执行。** 由于本文件头部的这段描述是对规范的引用（性质接近规范说明而非纯建议），Bot **未自行改写**，报请裁定：

- **改法 A：由编辑部改本文件头部**，使引用与 OPS.md 第二版一致。*连带影响*：仅措辞变动，无数据影响；历史批复段落建议保留不动（那是决策记录，不是规范）。
- **改法 B：维持原样**，只在本节标注「以下历史描述已过期，以 OPS.md 为准」。*连带影响*：零改动成本，但文件头部与正文批复之间存在自相矛盾的观感，新接手的会话可能照旧描述执行。

### 建议 3（低优先级 · 规范缺口）：新增栏目的同步清单，OPS.md 未列

`tools/validate.py` 第 11 项把站点标准导航**硬编码**为 12 项（`NAV_EXPECT`），并要求全部 `*.html` 的主导航与页脚导航逐项相等。因此「新增一个栏目」的实际改动面是：**13 个页面的主导航 + 13 个页面的页脚导航 + `validate.py` 的 `NAV_EXPECT` + `sitemap.xml` + 各页 canonical**，共约 29 处。而 OPS.md §2.2 只规定了「编号重映射的八处同步」，**对新增栏目没有对应的清单**。

- **改法 A：在 OPS.md §2 增补一条「新增/移除栏目」的同步清单**（并考虑把 `NAV_EXPECT` 抽到 `assets/` 下的数据文件，由校验器读取，避免硬编码）。*连带影响*：规范补全；抽出数据文件后新增栏目只需改一处数据 + 各页导航，校验器不再需要改——但需一次 `feature/*` 分支改造。
- **改法 B：不动。** *连带影响*：新增栏目这类改动仍靠人工记忆，漏改会在 CI 第 11 项爆出 13 条 error（每个页面一条），虽能被拦截但错误信息冗长。

### 复核确认（无需裁定，仅备案）

- **sitemap 的 `/paper?id=` 写法维持不变。** 依 2026-10-28 裁定（Cloudflare 归一化兜住可达性 + `validate.py` 第 4 项硬匹配，单改必红），本次复核无变化，未动 sitemap。
- **DOI 抽查方法已按裁定执行 Handle API。** 本次全站 107 个 DOI，106 个 `responseCode=1`；唯一例外 `10.20517/aiagent.2026.16` 仍为 `responseCode=100`（未注册），为 10-28 记录以来连续第二日，已在 10-29 期观察「待核实」与 benchmarks 条目内如实标注，维持「新刊 DOI 注册滞后、非伪引」判断。

---

## 建议 4（2026-10-30 · 低优先级）：search.html 剩余 22 条「指向文献库整页」的主题型索引条目，宜由编辑部人工精确化

### 背景（2026-10-30 每日技术运维实测）
`const IDX` 的「文献库」分组长期是人工节选，且其中 32 条只指向 `papers.html`（文献库整页）而非具体详情页，导致用户搜到标题后仍需自己在长列表里二次定位。本次运维已做两件事：

1. 新增 `tools/build_search_index.py`（幂等），自动补齐缺失文献的精确索引条目，**99/99 篇现已都能从搜索直达详情页**；
2. 人工核验后，把其中 10 条唯一命中的单模型条目（`scBERT / Geneformer / scFoundation / GeneCompass / TranscriptFormer / GREmLN / rbio1 / Nicheformer / DunedinPACE / Smer-Barreto 2023`）改为精确指向。

**剩余 22 条不动，原因是不适合自动判定**：它们多为合集型或主题型条目，一条对应多篇文献，例如「GEARS / CPA / scGen / STATE」「scVI / Harmony / totalVI / Mixscape」「Xing & Song：虚拟细胞世界模型（Cell 2026）」。脚本若按关键词硬匹配，会把「线性基线批评（Nature Methods 2025）」误配到 `p80`、「零样本评测（Genome Biology 2025）」误配到 `p49`（实测均误命中），**宁可不改**。

### 建议处置
由编辑部在后续内容维护中逐条拆分：合集型拆为多条单一文献条目，主题型改为指向精确详情页并保留主题词。交付标准：`python3 tools/validate.py` 保持 0 error 且 0 warning（同一 `paper.html?id=` 被两条以上条目引用会触发第 7 项 warning）。

---

## 2026-10-30 每日深度维护 · 新增建议（Bot 提交，待编辑部裁定）

> 提交身份：AIVC Insight Bot <bot@aivc.news>；分支：`bot/deep-2026-10-30`。
> 依据 OPS.md 第三节第 3 条：不适合放入当日 PR 的改动建议，写入本文件由编辑部批复后落地。
> 以下代码/规范类改动，本期**一律未自行执行**。

---

### 建议 5（高优先级 · 内容缺口）：补收 ProteinTalks（Nature 正刊，2026-09-09）入文献库

**事实。** Sun Rui、Qian Liujia、Li Yongge、Liu Tong 等；通讯：周沛劼（北京大学）、温翰（北京科学智能研究院 / 北京大学）、郭天南（西湖大学）、朱怡（西湖实验室）。《An operational perturbation proteomics-based virtual cell model》，*Nature* 在线 2026-09-09，DOI `10.1038/s41586-026-11001-9`（本站 2026-10-30 经 Handle API 复核，responseCode 1，指向 nature.com/articles/s41586-026-11001-9）。

**截至 2026-10-30，`assets/papers-data.js`（99 篇）中无此条，全站 15 个页面检索无命中。** 本期每日观察以其作为「自我限定 vs 自我加冕」的对照物引用，但本站文献库反而缺了这篇——这是一个应当被修掉、且修法有明确规程的缺口。

**为什么它够格：** Nature 正刊（非预印本）；中国团队主导；自带可核验的独立测试设计（81 个未训练化合物 AUROC 0.89 / 准确率 0.85；跨癌种 708 化合物平均 AUROC 0.77；140 个非乳腺癌 PDX 零样本 +24%）；原文含明确的任务边界声明（「ProteinTalks 不是细胞的数字孪生」）。

**为什么本期没自己补：** OPS.md §二.2 规定新增文献需同步八处（`papers-data.js`、`papers.html`、`search.html`、`index.html`、`news.html`、`feed.xml`、`sitemap.xml`、`further[]` 交叉引用）；`tools/validate.py` 第 13 项还要求 `assets/paper-titles.js` 覆盖全部编号。这是一次结构性写入，不是「每日深度维护」的合理动作半径，且编号 `p100` 会跨过两位数的边界（`p\d+` 正则与 `paper-titles.js` 的 `"p\d+":{` 匹配需一并确认能否容纳三位数）。**为不制造编号事故，交编辑部裁定。**

**两种改法与连带影响：**

| 改法 | 做法 | 连带影响 |
|---|---|---|
| **A. 补收为正刊文献（推荐）** | 编号 p100，八处同步 + `paper-titles.js` | ① 首次出现三位数编号，需确认 `validate.py` 的 `p\d+` 与 `paper-titles.js` 的 `"p\d+":{` 正则可容纳（本站判断可以，但**未实测，应先跑一次 validate**）；② `papers.html` 计数 99 → 100；③ sitemap 需加 `https://aivc.news/paper?id=p100`（写法见建议 5，此处会踩到同一个冲突）；④ 术语表若新增延伸引用，海报清单与术语数一致性校验（第 14 项）会跟着走 |
| **B. 不入库，只在基准页/观察页引用** | 本期已这样做了 | ① 文献库与「数据与基准」页对同一篇文献呈现层级不一致，读者从基准页点不进全文解读；② 缺口会持续存在，下次再有同类对照时会重复这个判断成本 |

**本站倾向：A，但必须由编辑部执行并先做一次编号容量实测。**

---

### 建议 6（高优先级 · 规范冲突）：sitemap 的规范 URL 写法，与全站链接、canonical 和 validate.py 硬匹配三者互斥

**这是 OPS.md 与 `tools/validate.py` 之间的实际冲突，Bot 不自行择一执行，报请裁定。**

**实测（2026-10-30）：**

| 位置 | 写法 | 实例 |
|---|---|---|
| `sitemap.xml`（99 条） | `paper?id=` | `https://aivc.news/paper?id=p01` |
| 全站 HTML 内部链接、`assets/feed.xml` | `paper.html?id=` | `https://aivc.news/paper.html?id=p97` |
| `paper.html` 的 canonical | `paper.html` | `https://aivc.news/paper.html` |
| 仓库内重定向配置 | **无 `_redirects` 文件** | 只有 `_headers`（只管响应头，不做跳转） |
| `tools/validate.py` 第 4 项 | 子串硬匹配 `paper?id={i}` | `if f"paper?id={i}" not in sitemap: err(...)` |

**冲突点：** 2026-10-25 的建议 2 已提出「sitemap 的 85 条 URL 会 404，建议改为 `paper.html?id=`」。但按该建议执行会**立刻触发 99 个 error**（`paper?id=p01` 不再匹配），CI 红灯、PR 无法合并（OPS.md §二.3 硬门槛）。反过来，当前 validate 全绿**并不能证明 sitemap 里的 URL 真实可达**——它只做了子串匹配。

**两种改法与连带影响：**

| 改法 | 做法 | 连带影响 |
|---|---|---|
| **A. 改 sitemap + 同步改 validate.py（推荐）** | `sitemap.xml` 改 `paper.html?id=`；`validate.py` 第 4 项匹配串同步改为 `paper.html?id={i}` | ① **OPS.md §六明确：修正 `validate.py` 判定规则须走编辑部 `feature/*` 分支 PR，Bot 不得自行改**；② 改动 validate.py 期间，所有已开未合并的当日分支若不 rebase 会集体变红；③ 改完后 sitemap 与全站链接、canonical 三方一致，SEO 规范化信号统一；④ 若 Cloudflare 侧确已配了 308 规则，改了反而可能与面板规则重复 |
| **B. 保留 sitemap 写法 + 新增 `_redirects`** | 新增 `/paper?id=:id  /paper.html?id=:id  308` | ① `_redirects` **不在 OPS.md §三.1 的 Bot 可写清单内**，需编辑部确认可否由 Bot 写；② 重定向配置从面板搬进仓库、可版本化审计，这是加分项；③ 但 sitemap 声明的规范 URL 与 canonical 仍然分裂，搜索引擎仍会收到两个不同的规范地址；④ 若面板规则已存在，重复配置 |

**裁定前需要的唯一信息：Cloudflare Pages 面板是否已配置 `/paper?id=*` → `/paper.html?id=*` 的 308 规则。** 若已配，建议 5 整体可关闭；若未配，建议按 A 执行（先编辑部改 validate.py，再由 Bot 改 sitemap，分两个 PR）。

---

### 建议 7（中优先级 · 规范冲突）：本文件抬头仍在引用已废止的「Bot 禁写禁区」规则

**事实。** 本文件抬头写着：

> 依据 OPS.md 第三节：Bot 禁写 `index.html`、`insight.html`、`about.html`、`assets/style.css`、`OPS.md`、`AGENTS.md`。

这是 **2026-10-25** 的表述。OPS.md 第二版（2026-10-27 修订）已将禁区文件改为「可经 PR 修改，但必须经编辑部审查方可合并」；AGENTS.md（2026-10-28 修订）明确写「曾经的『禁区绝对禁写』规则已于 2026-10-27 废止」，且本期「每日深度维护」任务正是按第二版要求 Bot 直接改写 `insight.html`。

**问题：** 三份文档里，只有本文件的抬头还留在旧版本。它不是规范文件（OPS.md 才是单一事实源），但它是**新人/新会话最先读到的文件之一**，抬头一句话就能把规则带回去。

**两种改法与连带影响：**

| 改法 | 做法 | 连带影响 |
|---|---|---|
| **A. 直接改抬头（Bot 不建议）** | 删掉「禁写」句，改写为现行口径 | ① 治标快；② 但本文件由 Bot 维护，**由 Bot 自行改写「Bot 能写什么」的依据，有自我授权之嫌**，且与 AGENTS.md「单一事实源是 OPS.md、本文件只做摘要、不再另立规则」的定位冲突；③ 历史建议 1/2 的措辞会失去上下文 |
| **B. 保留抬头原文，紧随其后加版本注（推荐）** | 加一行：「注：本段为 2026-10-25 历史表述，已被 OPS.md 第二版（2026-10-27）废止，现行口径见 OPS.md §三；保留原文仅为历史可追溯。」 | ① 保留历史可追溯性，读者能看见规则演进；② 不改任何规范文件，不越 OPS.md 的单一事实源地位；③ 代价：抬头仍有误导性，读者需读至注才明白 |

**本站倾向：B。** 无论选哪个，**都需要编辑部执行**——Bot 不自行改动规范依据类表述。

---

### 建议 8（低优先级 · 版式）：`<code>` 标签在 `assets/style.css` 中无对应规则

本期每日观察的事实表内使用了 `<code>` 标签标注文件路径与 API 端点（`assets/papers-data.js`、`https://doi.org/api/handles/<doi>`）。`assets/style.css` 中**无 `code` 选择器**，浏览器回落到默认等宽字体，与本站学术版式的字号/字重不一致（视觉上偏小、偏细）。

属纯样式问题，不改不影响功能与可读性。**若是刻意的（不想引入行内代码样式），本条可忽略。** 若需统一，建议在 `assets/style.css` 中补一条：

```css
code{font-family:var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace);font-size:.92em;
  padding:1px 4px;background:var(--bg-soft,#f6f6f4);border-radius:2px}
```

是否落地、以及变量是否都存在，请编辑部确认（样式文件属「可经 PR 修改但需审查」范围，Bot 本期未动）。

---

*以上四条由 2026-10-30 每日深度维护提出，均未自行执行，等待编辑部裁定。*
