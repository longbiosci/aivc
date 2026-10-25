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

