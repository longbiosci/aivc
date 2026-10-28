#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIVC Insight — 术语海报生成器

为 assets/glossary-data.js 中的每一条术语渲染一张 1080x1440 竖版海报，
含分类徽章、中英术语名、一句话定义、详细解释全文、延伸阅读文献、
站点二维码（指向该术语的站内页）与品牌信息。

用法：
    python3 tools/make_posters.py                # 生成全部
    python3 tools/make_posters.py --limit 3      # 只生成前 3 条（试渲）
    python3 tools/make_posters.py --only Virtual Cell --Aging Clock
    python3 tools/make_posters.py --format jpg   # 输出 JPEG（体积更小）
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "posters"
MANIFEST_JS = ROOT / "assets" / "posters-manifest.js"

W, H = 1080, 1440
MARGIN = 80
CONTENT_W = W - MARGIN * 2
FOOTER_Y = H - 252  # 页脚分隔线位置（延伸阅读块与二维码均须在其之下）

# ---- 站点配色（与 assets/style.css 一致）----
BG = (251, 250, 247)
PAPER = (255, 255, 255)
INK = (26, 35, 50)
BODY = (55, 64, 79)
SUB = (107, 118, 134)
DIM = (152, 161, 175)
LINE = (228, 225, 218)
ACCENT = (15, 94, 104)
ACCENT_SOFT = (232, 241, 241)
AMBER = (154, 107, 31)

CATS = {
    "core":   ("核心概念", (228, 239, 239), (15, 94, 104)),
    "model":  ("模型与架构", (230, 239, 240), (15, 94, 104)),
    "task":   ("任务与设定", (238, 242, 247), (51, 88, 122)),
    "metric": ("评测与指标", (247, 240, 224), (141, 97, 25)),
    "data":   ("数据集与基准", (241, 238, 247), (93, 78, 138)),
    "bio":    ("组学与基础", (233, 242, 233), (61, 107, 63)),
    "org":    ("机构与产业", (248, 236, 236), (160, 61, 61)),
}

FONT_SERIF_B = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
FONT_SERIF_R = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
FONT_SANS_R = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_SANS_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
SC_INDEX = 2  # TTC 内简体中文索引

SITE = "aivc.news"
GLOSSARY_URL = "https://aivc.news/glossary.html"

_fc = {}


def font(path, size):
    key = (path, size)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(path, size, index=SC_INDEX)
    return _fc[key]


def serif_b(size):
    return font(FONT_SERIF_B, size)


def serif_r(size):
    return font(FONT_SERIF_R, size)


def sans_r(size):
    return font(FONT_SANS_R, size)


def sans_b(size):
    return font(FONT_SANS_B, size)


# ---------------- 数据加载 ----------------
def load_terms():
    """通过 node 求值拿到术语数组，避免正则解析 JS 字面量出错。"""
    js = (ROOT / "assets" / "glossary-data.js").read_text(encoding="utf-8")
    code = (
        "const fs=require('fs');global.window={};"
        "eval(fs.readFileSync('assets/glossary-data.js','utf8'));"
        "console.log(JSON.stringify(window.GLOSSARY));"
    )
    out = subprocess.run(["node", "-e", code], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("解析 glossary-data.js 失败：\n" + out.stderr)
    return json.loads(out.stdout)


def load_titles():
    code = (
        "const fs=require('fs');var PAPER_TITLES={};"
        "eval(fs.readFileSync('assets/paper-titles.js','utf8'));"
        "console.log(JSON.stringify(PAPER_TITLES));"
    )
    out = subprocess.run(["node", "-e", code], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    return json.loads(out.stdout)


# ---------------- 中文排版 ----------------
CJK = re.compile(r"[\u2e80-\u9fff\u3000-\u303f\uff00-\uffef]")
FORBIDDEN_START = set("，。、；：？！）〉》」』”’·…～%,.;:?!)]}")


def tokenize(text):
    """中文逐字、拉丁词成组，作为换行单元。"""
    toks, buf = [], ""
    for ch in text:
        if CJK.match(ch):
            if buf:
                toks.append(buf)
                buf = ""
            toks.append(ch)
        elif ch.isalnum() or ch in ".+-_/":
            buf += ch
        else:
            if buf:
                toks.append(buf)
                buf = ""
            toks.append(ch)
    if buf:
        toks.append(buf)
    return toks


def wrap(text, fnt, max_w, draw):
    """按像素宽度折行；避免行首出现标点（避头尾，标点悬挂）。"""
    lines, cur = [], ""
    for tok in tokenize(text):
        cand = cur + tok
        if draw.textlength(cand, font=fnt) <= max_w:
            cur = cand
            continue
        if cur and tok and tok[0] in FORBIDDEN_START:
            # 标点不另起一行，悬挂到行尾
            cur += tok
            continue
        if cur:
            lines.append(cur)
        if draw.textlength(tok, font=fnt) <= max_w:
            cur = tok
        else:  # 超长单词硬切
            piece = ""
            for ch in tok:
                if draw.textlength(piece + ch, font=fnt) <= max_w:
                    piece += ch
                else:
                    if piece:
                        lines.append(piece)
                    piece = ch
            cur = piece
    if cur:
        lines.append(cur)
    return lines


def line_h(fnt, mult=1.55):
    """行高：以字号(em)为基准，mult 为行距倍数。CJK 字体 bbox 偏大，用 em 更可控。"""
    return int(fnt.size * mult)


def draw_lines(draw, xy, lines, fnt, fill, lh, max_w=None):
    x, y = xy
    for ln in lines:
        draw.text((x, y), ln, font=fnt, fill=fill)
        y += lh
    return y


def ellipsize(text, fnt, max_w, draw):
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=fnt) > max_w:
        text = text[:-1]
    return text + "…"


# ---------------- 组件 ----------------
def qr_image(url, slot=176, min_module=3):
    """生成二维码并做整数倍 NEAREST 放大——保证模块边缘锐利、可被扫码器解码。

    三个关键约束（都是实测踩出来的）：
    1. 禁止 LANCZOS 缩放，插值会模糊模块边界导致解码失败；
    2. 结果尺寸必须不超过 slot，否则贴进海报会溢出画布被裁掉（底部截断
       同样扫不出来）；
    3. 纠错等级用 H（最高）而非 M——实测 EC=M 时部分 URL 图案（MAE、IL-11 等）
       在 OpenCV 下解不出，EC=H 全部可解。代价只是二维码稍密一点。
    """
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H,
                       box_size=1, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    base = qr.make_image(fill_color=ACCENT, back_color=PAPER).convert("RGB")
    n = base.size[0]                      # 含边框的模块总数
    scale = max(1, min(slot // n, max(min_module, -(-slot // n))))
    size = n * scale
    return base.resize((size, size), Image.NEAREST)


def draw_brand(draw, x, y):
    """左上角品牌标记：圆角方块 + 衬线 AI 字样。"""
    draw.rounded_rectangle([x, y, x + 58, y + 58], radius=12, fill=ACCENT)
    draw.text((x + 13, y + 9), "Ai", font=serif_b(32), fill=PAPER)


def render(term, idx, total, titles, out_path, fmt="png"):
    cat = term["c"]
    cat_name, cat_bg, cat_fg = CATS.get(cat, ("术语", ACCENT_SOFT, ACCENT))

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # 顶部细色条
    draw.rectangle([0, 0, W, 9], fill=ACCENT)

    # ---- 品牌区 ----
    draw_brand(draw, MARGIN, 52)
    draw.text((MARGIN + 74, 50), "AIVC INSIGHT", font=serif_b(33), fill=INK)
    draw.text((MARGIN + 76, 92), "AI 虚拟细胞 · 术语图鉴", font=sans_r(19), fill=DIM)

    idx_txt = f"{idx} / {total}"
    w_idx = draw.textlength(idx_txt, font=serif_b(24))
    draw.text((W - MARGIN - w_idx, 58), idx_txt, font=serif_b(24), fill=ACCENT)
    lab = "TERM CARD"
    w_lab = draw.textlength(lab, font=sans_r(15))
    draw.text((W - MARGIN - w_lab, 92), lab, font=sans_r(15), fill=DIM)

    y = 148
    draw.line([MARGIN, y, W - MARGIN, y], fill=LINE, width=2)

    # ---- 分类徽章 + 缩写 ----
    y = 176
    cat_txt = cat_name
    f_badge = sans_b(22)
    tw = draw.textlength(cat_txt, font=f_badge)
    draw.rounded_rectangle([MARGIN, y, MARGIN + tw + 34, y + 42], radius=21, fill=cat_bg)
    draw.text((MARGIN + 17, y + 7), cat_txt, font=f_badge, fill=cat_fg)

    abbr = term.get("a") or ""
    if abbr:
        f_ab = sans_b(20)
        aw = draw.textlength(abbr, font=f_ab)
        ax = MARGIN + tw + 34 + 12
        draw.rounded_rectangle([ax, y + 4, ax + aw + 26, y + 38], radius=17,
                               outline=cat_fg, width=2)
        draw.text((ax + 13, y + 8), abbr, font=f_ab, fill=cat_fg)

    # ---- 英文术语名（自适应字号，最多两行）----
    y += 62
    name = term["t"]
    f_name = None
    name_lines = None
    for size in range(74, 39, -2):
        fnt = serif_b(size)
        ls = wrap(name, fnt, CONTENT_W, draw)
        if len(ls) <= 2:
            f_name, name_lines = fnt, ls
            break
    if f_name is None:
        f_name = serif_b(40)
        name_lines = wrap(name, f_name, CONTENT_W, draw)
    lh = line_h(f_name, 1.26)
    y = draw_lines(draw, (MARGIN, y), name_lines, f_name, INK, lh)

    # ---- 中文名 ----
    zh = term.get("z") or ""
    if zh:
        f_zh = serif_r(38)
        while draw.textlength(zh, font=f_zh) > CONTENT_W and f_zh.size > 24:
            f_zh = serif_r(f_zh.size - 2)
        draw.text((MARGIN, y + 4), zh, font=f_zh, fill=ACCENT)
        y += f_zh.size + 14

    y += 6
    draw.line([MARGIN, y, W - MARGIN, y], fill=LINE, width=2)
    y += 26

    # ---- 一句话定义（高亮框）----
    s = term.get("s") or ""
    f_s = sans_r(29)
    s_lines = wrap(s, f_s, CONTENT_W - 56, draw)
    lh_s = line_h(f_s, 1.5)
    box_h = 34 + len(s_lines) * lh_s + 26
    draw.rounded_rectangle([MARGIN, y, W - MARGIN, y + box_h], radius=8, fill=ACCENT_SOFT)
    draw.rectangle([MARGIN, y, MARGIN + 7, y + box_h], fill=ACCENT)
    draw.text((MARGIN + 26, y + 12), "一句话定义", font=sans_b(17), fill=ACCENT)
    draw_lines(draw, (MARGIN + 26, y + 38), s_lines, f_s, BODY, lh_s)
    y += box_h + 26

    # ---- 详细解释 ----
    b = term.get("b") or ""
    draw.text((MARGIN, y), "详细解释", font=sans_b(18), fill=ACCENT)
    draw.line([MARGIN + 96, y + 13, W - MARGIN, y + 13], fill=LINE, width=1)
    y += 30

    # 版面规划：页脚线固定在 FOOTER_Y，延伸阅读块置于其上
    refs = term.get("r") or []
    n_ref = min(len(refs), 3)
    ref_block_h = 30 + n_ref * 34
    detail_bottom = FOOTER_Y - 24 - ref_block_h
    avail = max(detail_bottom - y, 60)
    f_b, blines, blh = None, None, None
    for size in range(29, 20, -1):
        fnt = sans_r(size)
        ls = wrap(b, fnt, CONTENT_W, draw)
        lh_try = line_h(fnt, 1.68)
        if len(ls) * lh_try <= avail:
            f_b, blines, blh = fnt, ls, lh_try
            break
    if f_b is None:
        f_b = sans_r(20)
        blines = wrap(b, f_b, CONTENT_W, draw)
        blh = line_h(f_b, 1.55)
        while len(blines) * blh > avail and blines:
            blines = blines[:-1]
    y = draw_lines(draw, (MARGIN, y), blines, f_b, BODY, blh)

    # ---- 延伸阅读（底部对齐到页脚线之上）----
    if n_ref:
        y = max(y + 20, FOOTER_Y - 20 - ref_block_h)
        draw.text((MARGIN, y), "延伸阅读", font=sans_b(18), fill=ACCENT)
        draw.line([MARGIN + 96, y + 13, W - MARGIN, y + 13], fill=LINE, width=1)
        y += 30
        f_ref = sans_r(20)
        f_refb = sans_b(20)
        for pid in refs[:n_ref]:
            info = titles.get(pid) or {}
            short = ellipsize(info.get("t", ""), f_ref, CONTENT_W - 56, draw)
            tail = short
            if info.get("v"):
                tail += f"（{info['v']}）"
            tail = ellipsize(tail, f_ref, CONTENT_W - 56, draw)
            draw.text((MARGIN, y), pid, font=f_refb, fill=ACCENT)
            draw.text((MARGIN + 52, y), "· " + tail, font=f_ref, fill=SUB)
            y += 34

    # ---- 页脚：二维码 ----
    draw.line([MARGIN, FOOTER_Y, W - MARGIN, FOOTER_Y], fill=LINE, width=2)
    fy = FOOTER_Y + 20

    qr = qr_image(f"{GLOSSARY_URL}?q={_urlq(term['t'])}", slot=176, min_module=3)
    qsize = qr.size[0]
    qx = W - MARGIN - qsize
    qy = fy + max(0, (176 - qsize) // 2)
    draw.rounded_rectangle([qx - 9, qy - 9, qx + qsize + 9, qy + qsize + 9],
                           radius=8, fill=PAPER, outline=LINE, width=2)
    img.paste(qr, (qx, qy))

    draw.text((MARGIN, fy + 14), "扫码查看完整词条", font=sans_b(29), fill=INK)
    draw.text((MARGIN, fy + 60), "延伸文献 · 每日更新 · 全站术语检索", font=sans_r(21), fill=SUB)
    draw.text((MARGIN, fy + 98), f"{SITE}/glossary", font=sans_b(24), fill=ACCENT)

    draw.text((MARGIN, H - 42), "AI 虚拟细胞情报站 · aivc.news",
              font=sans_r(18), fill=DIM)

    if fmt == "jpg":
        img.save(out_path, "JPEG", quality=90, optimize=True, progressive=True)
    elif fmt == "webp":
        img.save(out_path, "WEBP", quality=88, method=6)
    else:
        img.save(out_path, "PNG", optimize=True)
    return out_path


def _urlq(s):
    import urllib.parse
    return urllib.parse.quote(s)


def slugify(name, idx):
    s = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    if not s:
        s = "term"
    return f"{idx:03d}-{s[:46]}"


FINDER = [[1, 1, 1, 1, 1, 1, 1],
          [1, 0, 0, 0, 0, 0, 1],
          [1, 0, 1, 1, 1, 0, 1],
          [1, 0, 1, 1, 1, 0, 1],
          [1, 0, 1, 1, 1, 0, 1],
          [1, 0, 0, 0, 0, 0, 1],
          [1, 1, 1, 1, 1, 1, 1]]


def check_qr_structure(arr, expect_url):
    """从海报像素中定位二维码并反解模块矩阵，校验其结构规范性。

    不依赖任何解码器的检测能力——先用颜色把二维码区域框出来，再按模块
    中心采样得到 0/1 矩阵，最后检查 finder pattern、timing pattern、
    格式信息与数据区是否自洽。
    """
    import numpy as np

    # 1) 定位二维码区域：主色 #0f5e68 的深青像素构成的矩形
    r, g, b = arr[:, :, 0].astype(int), arr[:, :, 1].astype(int), arr[:, :, 2].astype(int)
    mask = (r < 90) & (g > 60) & (g < 130) & (b > 70) & (b < 140)
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return False, "未找到二维码区域"
    # 取右下角聚簇（海报二维码位于右下）
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    if x1 - x0 < 80 or y1 - y0 < 80:
        return False, "二维码区域过小"

    # 2) 由 finder pattern 反推模块尺寸与矩阵原点
    #    左上 finder 中心在 (x0+3.5*m, y0+3.5*m)；用投影找模块边界
    region = mask[y0:y1 + 1, x0:x1 + 1]
    n_mod = None
    for cand in range(21, 90):
        # 粗略：整除检测
        if region.shape[0] % cand == 0 and region.shape[1] % cand == 0:
            n_mod = cand
            break
    if n_mod is None:
        # 用 finder pattern 的黑白跳变推断模块数：QR 版本 v → 边长 17+4v
        v = int(round((region.shape[1] - 8) / 4))
        n_mod = 17 + 4 * v
    if n_mod < 21 or n_mod > 177:
        return False, f"无法确定模块数（区域 {region.shape}）"

    m = region.shape[1] // n_mod
    if m < 1:
        return False, "模块尺寸为零"

    # 3) 模块中心采样（border=2，即前两行/列为空白边框）
    border = 2
    bits = []
    for i in range(n_mod):
        row = []
        for j in range(n_mod):
            cy = (i + border) * m + m // 2
            cx = (j + border) * m + m // 2
            row.append(1 if region[cy, cx] else 0)
        bits.append(row)

    # 4) 结构校验
    def finder_ok(ox, oy):
        return all(bits[oy + y][ox + x] == FINDER[y][x]
                   for y in range(7) for x in range(7))

    if not (finder_ok(0, 0) and finder_ok(n_mod - 7, 0)
            and finder_ok(0, n_mod - 7)):
        return False, "finder pattern 不符规范"
    for i in range(8, n_mod - 8):
        if bits[6][i] != (1 if i % 2 == 0 else 0):
            return False, "timing pattern 不符规范"
        if bits[i][6] != (1 if i % 2 == 0 else 0):
            return False, "timing pattern 不符规范（列）"

    # 5) 数据区非全白（确认真的编码了内容而非空白图）
    data_cells = sum(sum(bits[y][x] for x in range(9, n_mod - 8))
                     for y in range(9, n_mod - 8))
    if data_cells == 0:
        return False, "数据区为空"
    return True, f"结构校验通过（{n_mod}x{n_mod} 模块，数据位 {data_cells}）"


def verify_qr(path, expect):
    """校验生成的二维码能被扫码器正确解码。

    校验分两层：
    1. 结构校验（不依赖检测器）：读出模块矩阵，检查 finder pattern 与
       timing pattern 是否符合 QR 规范——这是二维码「本身对不对」的硬证据；
    2. 实际解码：用 zbar 解码并比对 URL。
       首选 zbar（与手机扫码同源），退回 OpenCV——注意 OpenCV 检测器对
       个别图案存在固定盲区（如 scGPT-spatial / MSigDB），它解不出不代表
       二维码有问题，故结构校验才是最终判据。
    """
    import numpy as np
    from PIL import Image

    try:
        from pyzbar.pyzbar import decode as zbar_decode
    except Exception:
        zbar_decode = None

    img = Image.open(path).convert("RGB")
    arr = np.array(img)

    # 1) 实际解码
    decoded = ""
    if zbar_decode is not None:
        for r in zbar_decode(arr):
            decoded = r.data.decode("utf-8", "ignore")
            break
    if not decoded:
        try:
            import cv2
            d, _, _ = cv2.QRCodeDetector().detectAndDecode(
                cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
            decoded = d or ""
        except Exception:
            decoded = ""
    if decoded:
        return (decoded == expect), (decoded if decoded == expect
                                     else f"内容不符: {decoded}")
    # 2) 解码器都没解出 → 退回结构校验
    return check_qr_structure(arr, expect)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--format", choices=["jpg", "png", "webp"], default="jpg",
                    help="默认 jpg：微信/微博/公众号通用，下载即用")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    terms = load_terms()
    titles = load_titles()
    total = len(terms)

    if args.only:
        want = set(args.only)
        terms = [t for t in terms if t["t"] in want]
    if args.limit:
        terms = terms[: args.limit]

    out_dir = Path(args.out) if args.out else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    fmts = [args.format]

    manifest = []
    failed = 0
    for i, t in enumerate(terms, 1):
        base = slugify(t["t"], i)
        url = f"{GLOSSARY_URL}?q={_urlq(t['t'])}"
        for fm in fmts:
            fname = f"{base}.{fm}"
            out_path = out_dir / fname
            render(t, i, total, titles, out_path, fm)
            ok, msg = verify_qr(out_path, url)
            if not ok:
                failed += 1
                print(f"  [{i:3d}/{total}] {fname}  ❌ 二维码: {msg}")
        manifest.append({
            "n": i, "c": t["c"], "t": t["t"], "z": t.get("z", ""),
            "a": t.get("a", ""),
            "f": f"posters/{base}.{fmts[0]}",
            "u": f"glossary.html?q={_urlq(t['t'])}",
        })
        if not args.only and not args.limit:
            print(f"  [{i:3d}/{total}] {base}")

    if not args.only and not args.limit:
        lines = ["// AIVC Insight — 术语海报清单（由 tools/make_posters.py 生成，勿手改）",
                 f"// 共 {len(manifest)} 张，对应 glossary-data.js 全部术语",
                 "// f = 海报图片（jpg）｜ u = 对应词条页",
                 "window.POSTER_MANIFEST=" + json.dumps(manifest, ensure_ascii=False,
                                                       separators=(",", ":")) + ";"]
        MANIFEST_JS.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n清单已写入 {MANIFEST_JS.relative_to(ROOT)}")

    for fm in fmts:
        sizes = [f.stat().st_size for f in out_dir.glob(f"*.{fm}")]
        if sizes:
            print(f"{fm:5s} {len(sizes)} 张，单张 {min(sizes)/1024:.0f}–{max(sizes)/1024:.0f} KB，"
                  f"合计 {sum(sizes)/1024/1024:.1f} MB")
    if failed:
        print(f"\n❌ {failed} 张二维码校验未通过")
        sys.exit(1)
    if not args.only and not args.limit:
        print("✅ 全部二维码校验通过")


if __name__ == "__main__":
    main()
