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

实际页面是 `paper.html`，**缺少 `.html` 扩展名**，提交给搜索引擎会 404。建议批量改为：

```
https://aivc.news/paper.html?id=p01
```

可用一条命令完成（编辑部执行）：

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
