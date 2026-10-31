# 投稿口（kb-inbox）——读者把全文投进来，我们核验后入库

> 上线日期：2026-10-31。相关规范：OPS.md §3.2.6。
> 这套东西解决的是「110 篇里 79 篇站内读不到正文」这个产品缺陷的最短闭环。

## 一句话

读者在文献详情页生成一张**投递单**（带编号），连同全文作为附件发到编辑部邮箱 →
后台按编号取件 → 机器判许可与归属 → 通过的转成站内可读全文进 `kb/`；
不通过的回执写明原因，读者凭编号在页面上看到结果。

## 为什么通道是邮件（两次否决的结论）

站点是纯静态的（Cloudflare Pages，没有服务端）。「上传」必须有落点，先后试过两条路，都不成立：

| 方案 | 结论 |
|---|---|
| **前端拿令牌直传仓库分支** | 静态站把令牌写进 `assets/*.js`，等于把写权限公开在网页源码里；GitHub 密钥扫描还会直接拒收提交。**本功能第一版正因此在推送时被拒**：`GH013 —— GitHub Personal Access Token` |
| **前端无凭据开 GitHub issue** | issue 的写接口一律要求认证：`POST /repos/{o}/{r}/issues` 与 `POST /issues/{n}/comments` 匿名均返回 **401 Requires authentication**。要匿名提交就只能把令牌塞回前端，等于换个方式犯同一个错 |
| **邮件（现行）** | 读者天然有邮箱，我们天然能收，不需要任何凭据、不依赖第三方服务、不受 CORS 约束 |

邮件的唯一代价：浏览器无权把文件挂到邮件上，读者需要自己拖一次附件。这个取舍是明确的——
宁可多一步人工，不把写权限公开在网页上。

## 数据流

```
文献页 #kv
  ├─ 浏览器内筛格式/大小
  ├─ 生成投递单（纯文本，机读头）
  │    AIVC-INSIGHT-UPLOAD v1
  │    rid: u2026103109264743bl
  │    paper: p98
  │    license: cc-by
  │    file: t98.txt (5 KB)
  │    sha256: 47db65d8…
  └─ mailto:editor@aivc.news?subject=[全文投稿] p98 <rid>&body=<投递单>
        ↓ 读者补附件、发送
  编辑部邮箱 ──「另存为 .eml」──> drops/<rid>.eml
        ↓
  tools/inbox.py fetch     解 multipart → inbox/<rid>/raw/body.<ext>（隔离区）
        ↓                 落盘前逐字节扫 <!-- / -->，命中即拒收
  tools/inbox.py process   许可判定 → 归属校验 → 解析 → kb/<id>.src.json → build_kb 渲染
        ↓
  tools/publish_inbox.py   → assets/kb-inbox-data.js（页面状态回执 + 文献库角标）
```

投递**编号**由浏览器生成：`u` + 14 位时间戳 + 4 位随机（`u2026103109264743bl`）。
编号是回执唯一键，页面用 `localStorage` 记住，下次打开同一篇会显示处理状态。

## 每日怎么跑

```bash
# 1. 把读者邮件另存为 .eml，放进 drops/（或设 KBINBOX_IMAP_HOST 让脚本直连邮箱拉）
python3 tools/inbox.py fetch      # 解邮件 → 隔离区
python3 tools/inbox.py process    # 许可/归属/解析/入库
python3 tools/publish_inbox.py    # 回执写进 assets/kb-inbox-data.js
python3 tools/build_kb.py --no-fetch
python3 tools/validate.py
```

`python3 tools/inbox.py status` 随时看每个批次卡在哪一步。

### 三种取件源

| 来源 | 用法 | 适用 |
|---|---|---|
| `drops/*.eml` | 邮件客户端「另存为 .eml」丢进 `drops/` | **默认**，最省事 |
| `drops/*.txt` | 只贴正文；同名目录 `drops/<同名>/` 里的文件当附件 | 邮件客户端不支持导出时 |
| IMAP | `KBINBOX_IMAP_HOST/USER/PASS`，脚本直连邮箱拉标题带 `[全文投稿]` 的信 | 投稿量大时 |

三种来源的解析规则完全相同：都先归一成「正文 + 附件」，再交给同一个 `fetch_one()`。

### 可选环境变量

```bash
export KBINBOX_IMAP_HOST=imap.example.com   # 直连收信
export KBINBOX_IMAP_USER=editor@aivc.news
export KBINBOX_IMAP_PASS=...
export KBINBOX_DROPS=/path/to/drops         # 换落地区
```

这些凭据**只在运维机器上**，与前端无关，永远不会进仓库。

## 三道判定，没有第四种结局

| 判定 | 触发 | 结果 |
|---|---|---|
| **允许** | 许可在白名单（CC BY / CC0 / CC BY-NC / CC BY-NC-ND），且与正文版权行不冲突 | 入 `kb/`，详情页出现「读站内全文」，页首标「由读者投稿并经本刊核验许可」 |
| **拒绝** | 正文出现 `All Rights Reserved`、DC 版权扩展项，或标注 CC BY-ND | 不入库，回执写明原因 |
| **待确认** | 投稿人选了「其他 / 不确定」，或声明与正文版权行矛盾 | 人工核，正文不进站 |

**归属校验**是防投错的关键：正文里必须找得到这篇的 DOI 或标题前 40 字符；
若正文里出现的 DOI 与目标文献不符，当场退回。投错比不投更麻烦——读者会以为那是这篇论文的内容。

**质量比较**：若该篇已有站内全文，投来的版本短于现状 95% 就不覆盖，回执写「该文献已有质量更高的全文」。

**指纹**只做记录不做拦截：投递单里的 `sha256` 与附件实际值不符时，在报告里记一笔
（读者可能换了版本重发），仍按附件内容判定。

## 防护：为什么原文不会自己变成线上页面

四条独立锁：

1. **原文不在仓库里**：附件只在读者邮箱与运维机器的 `drops/`、`inbox/` 之间流动；
2. **`drops/` 与 `inbox/` 都在 `.gitignore` 里**：`git status` 看不见，没有被误提交的机会；
3. **Git 清道**：`.gitattributes` 把 `inbox/**` 标为 `-text filter=kbscrub`，checkout 时
   `<!--` / `-->` 被替换成 `‹!‹‹` / `‹!‹‹-`，注释闭合序列进不了工作区；
4. **解析器不信它**：`tools/inbox.py` 读字节时再查一遍定界符，命中即拒收——不假定清道一定生效。

投递单本身的约束：

- **必须能解出编号与文献号**（机读头或主题前缀），解不出的一律不认——空邮件、广告邮件直接忽略；
- **附件白名单**：PDF / JATS XML / DOCX / HTML / MD / TXT / JSON，单文件上限 40MB，其余记入 `skipped`。

`validate.py` 第 20 项把这些钉成机器检查：前端无凭据（正则扫 `ghp_` / `github_pat_`）、
CSP 不得再放行 `api.github.com`（残留即说明旧通道没清干净）、清道规则存在、
`inbox/` 在 `.gitignore` 里、脚本引入顺序、`id="kv"` 挂载点、回执编号格式。

## 回执与页面

| 文件 | 内容 | 谁写 |
|---|---|---|
| `assets/kb-inbox-cfg.js` | 收件邮箱、大小上限、开关——**无任何凭据** | 人 |
| `assets/kb-inbox.js` | 表单、编号生成、投递单、mailto、状态条 | 人 |
| `assets/kb-inbox-data.js` | `[{r,p,s,at,m,n}]`，`s ∈ done\|wait\|blocked` | `publish_inbox.py` |

`localStorage['aivc_upl_<pid>']` 存本机投递记录。投稿量少时回执表很小，随站发布即可。

## 已知限制

- **需要读者手动补附件**：浏览器不能替用户挂附件，页面已把这一步写成显式两步引导；
- **扫描版 PDF 读不出字**：没有 OCR 依赖，`pdftotext` 抽不到文本会判「文件读不出来」并退回，
  这时请投稿人给 JATS XML 或文字版；
- **上限 25MB（页面）/ 40MB（后台）**：超过的判断在页面侧就拦下并提示只给正文；
- **只接受单文件**：一篇一次，正文 + 补充材料的打包请走邮件正文说明；
- **解析质量**：PDF 分节靠行首规则，识别不出的会整篇当一节——不假装成功，但不阻断入库；
- **回执靠本地记录**：换设备、清缓存后读者看不到自己的投递状态，需凭编号来信查询。
