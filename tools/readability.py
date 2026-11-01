#!/usr/bin/env python3
"""可读性巡检：找出正文里最该改写的中文句子。

只做体检、不改文件。改不改、怎么改由编辑判断——这类问题是语义判断，
脚本能做的是把「最值得看的那 100 句」排到前面，而不是替你决定。

用法：
    python3 tools/readability.py                # 巡检 papers-data.js，输出前 30 条
    python3 tools/readability.py --top 80       # 多看一些
    python3 tools/readability.py --page news    # 巡检 news.html
    python3 tools/readability.py --score        # 只输出各篇的可读性得分排名
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 中文虚词化的「书面语框架」——生硬感的主要来源，出现即加分
STIFF_PATTERNS = [
    (r'以[^，。]{1,12}为', '以…为'),
    (r'对[^，。]{1,10}进行[^，。]{1,10}', '对…进行…'),
    (r'基于[^，。]{1,12}的', '基于…的'),
    (r'通过[^，。]{1,12}的方式', '通过…的方式'),
    (r'在[^，。]{1,10}的基础上', '在…的基础上'),
    (r'具有[^，。]{1,8}的特点', '具有…的特点'),
]


def cn_len(s):
    return len(re.findall(r'[\u4e00-\u9fff]', s))


def split_sentences(text):
    """按中文句末标点切句，保留较长的片段。"""
    parts = re.split(r'(?<=[。！？])', text)
    return [p.strip() for p in parts if cn_len(p) >= 15]


def score_sentence(s):
    """返回 (得分, 问题标签列表)。得分越高越该改写。"""
    n = cn_len(s)
    tags = []
    score = 0

    # 1) 长度：超过 50 字开始扣分，这是最硬的指标
    if n > 50:
        score += (n - 50) * 2
        tags.append('%d字' % n)

    # 2) 破折号当连接符：一句话两个以上
    if s.count('——') >= 2:
        score += 25
        tags.append('破折号×%d' % s.count('——'))

    # 3) 分号并列：一句里三个以上分号，通常是硬塞了三个独立意思
    if s.count('；') >= 2:
        score += 15
        tags.append('并列×%d' % (s.count('；') + 1))

    # 4) 「的」字过密
    de = s.count('的')
    if de >= 5:
        score += (de - 4) * 6
        tags.append('的×%d' % de)

    # 5) 书面语框架
    for pat, name in STIFF_PATTERNS:
        if re.search(pat, s):
            score += 8
            tags.append(name)

    # 6) 英文缩写过密（未解释的英文堆叠，读者要频繁跳回）
    abbr = len(re.findall(r'\b[A-Z][A-Za-z]{1,6}\b', s))
    if abbr >= 4:
        score += (abbr - 3) * 5
        tags.append('缩写×%d' % abbr)

    return score, tags


def load_papers():
    path = os.path.join(ROOT, 'assets', 'papers-data.js')
    src = open(path, encoding='utf-8').read()
    # 用 node 求值，比手写解析可靠（数据里有嵌套引号与转义）
    import subprocess
    js = ("const fs=require('fs');"
          "const code=fs.readFileSync('%s','utf8');"
          "const P=new Function(code+'; return PAPERS;')();"
          "console.log(JSON.stringify(P));" % path)
    out = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit('解析 papers-data.js 失败：' + out.stderr[:300])
    return json.loads(out.stdout)


def text_of(p):
    seg = []
    if p.get('summary'):
        seg.append(('摘要', p['summary']))
    for key, label in [('background', '背景'), ('method', '方法'), ('results', '结果'),
                       ('limits', '局限'), ('debate', '争议'), ('takeaway', '点评')]:
        for i, x in enumerate(p.get(key) or []):
            seg.append(('%s%d' % (label, i + 1), x))
    return seg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=30, help='输出条数')
    ap.add_argument('--score', action='store_true', help='只输出各篇总分排名')
    ap.add_argument('--id', help='只看某篇')
    args = ap.parse_args()

    papers = load_papers()
    if args.id:
        papers = [p for p in papers if p['id'] == args.id]

    rows = []
    per_paper = []
    for p in papers:
        segs = text_of(p)
        total = 0
        n_sent = 0
        worst = 0
        for label, txt in segs:
            for s in split_sentences(txt):
                sc, tags = score_sentence(s)
                n_sent += 1
                total += sc
                worst = max(worst, sc)
                if sc > 0:
                    rows.append((sc, p['id'], label, tags, s))
        avg = total / n_sent if n_sent else 0
        per_paper.append((avg, worst, total, n_sent, p['id'], p.get('t', '')[:50]))

    if args.score:
        per_paper.sort(reverse=True)
        print('%-6s %6s %6s %6s  %s' % ('编号', '均分', '最差', '句数', '标题'))
        for avg, worst, total, n, pid, t in per_paper:
            print('%-6s %6.1f %6d %6d  %s' % (pid, avg, worst, n, t))
        return

    rows.sort(reverse=True)
    print('=' * 78)
    print('共 %d 句需要关注（占 %d 句的 %.0f%%）' % (
        len(rows), sum(r[3] for r in per_paper),
        100.0 * len(rows) / max(1, sum(r[3] for r in per_paper))))
    print('=' * 78)
    for sc, pid, label, tags, s in rows[:args.top]:
        print('\n[%s·%s] 得分 %d  (%s)' % (pid, label, sc, ' / '.join(tags)))
        print('  ' + s[:200] + ('…' if len(s) > 200 else ''))


if __name__ == '__main__':
    main()
