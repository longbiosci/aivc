/* AIVC Insight — 术语悬停释义
 * 正文里出现术语表收录的词（英文原词、中文名、缩写），自动包成可悬停的标记，
 * 悬停或聚焦时弹出「一句话定义」并给出跳转到术语表的入口。
 *
 * 设计取舍：
 * 1) 只包第一次出现——每篇文章对同一术语只提示一次，避免满屏虚线下划线，反而更难读。
 * 2) 跳过标题、链接、代码、已有的标记——不破坏原文语义与交互。
 * 3) 首句自动附一句「中文对照」，因为多数读者卡住的正是英文缩写与中文译名对不上号。
 * 4) 纯前端、零依赖：数据来自 assets/glossary-data.js，新增术语自动生效，无需改正文。
 */
(function () {
  'use strict';

  if (typeof GLOSSARY === 'undefined' || !GLOSSARY.length) return;

  /* 样式表随脚本一起加载，页面只需引一个文件；样式单独成表是为了不碰公共 style.css */
  (function injectCSS() {
    if (document.getElementById('gterm-css')) return;
    var l = document.createElement('link');
    l.id = 'gterm-css';
    l.rel = 'stylesheet';
    l.href = 'assets/glossary-hover.css';
    document.head.appendChild(l);
  })();

  /* ---------- 1. 建词条索引 ---------- */

  // 中文里这些字太常见，作为术语别名会把正常文本误标，直接排除
  var BAD_ALIAS = ['模型', '数据', '预测', '生成', '表示', '任务', '细胞', '基因', '图', '网络'];

  /* 一缩写多义的词：不同文献语境下含义可能完全不同，不做自动标注，交由读者查术语表。
   * 例：MAE 在本站术语表是「平均绝对误差」，但在 Cell Painting 文献里指 Masked Autoencoder（掩码自编码器）。
   * 宁可漏标，不可错标——悬停提示给错解释，比不给更糟。 */
  var AMBIGUOUS = ['MAE', 'MSE', 'PIE', 'STATE', 'EVA', 'UCE', 'MMD'];

  // 术语名（英文 / 中文 / 别名）→ 词条
  var index = Object.create(null);
  GLOSSARY.forEach(function (g) {
    var keys = [g.t, g.z];
    if (g.a) {
      String(g.a).split(/[\/,，]/).forEach(function (x) {
        x = x.trim();
        if (x) keys.push(x);
      });
    }
    keys.forEach(function (k) {
      if (!k || k.length < 2) return;
      if (BAD_ALIAS.indexOf(k) >= 0) return;
      if (AMBIGUOUS.indexOf(k.toUpperCase()) >= 0 || AMBIGUOUS.indexOf(k) >= 0) return;
      var key = k.toLowerCase();
      // 同名冲突时保留先出现的，术语表本身按分类排，核心概念在前
      if (!index[key]) index[key] = g;
    });
  });

  /* ---------- 2. 编译匹配正则 ---------- */

  // 英文/缩写要求前后不粘连字母数字，避免 "MAE" 命中 "MAEstro" 这类
  // 中文可自由参与匹配，但排除已包在标签内的情形（在遍历时处理）
  var words = Object.keys(index).sort(function (a, b) { return b.length - a.length; });

  function escapeRe(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /* ---------- 3. 遍历文本节点 ---------- */

  var SKIP_TAGS = {
    A: 1, CODE: 1, PRE: 1, H1: 1, H2: 1, H3: 1, H4: 1,
    SCRIPT: 1, STYLE: 1, BUTTON: 1, TEXTAREA: 1, NAV: 1, FOOTER: 1
  };

  // 页面结构类元素不标：徽章行、按钮组、面包屑、导读导航——这些是「界面」不是「正文」
  var SKIP_CLASSES = ['dbadge', 'dtoc', 'dlinks', 'crumb', 'topbar', 'fnav', 'dpn', 'dauth', 'dft'];

  /**
   * @param {HTMLElement} root 限定范围
   * @param {number} limit 最多标注多少个术语（详情页正文长，给个上限防止刷屏）
   */
  function decorate(root, limit) {
    if (!root) return 0;
    limit = limit || 40;

    var seen = Object.create(null);   // 本篇已标注过的术语
    var count = 0;

    // 先收集文本节点，再统一替换——边遍历边改 DOM 会漏节点
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var p = node.parentNode;
        if (!p || SKIP_TAGS[p.nodeName]) return NodeFilter.FILTER_REJECT;
        // 逐级向上检查是否处于界面结构元素内
        for (var anc = p; anc && anc.classList; anc = anc.parentNode) {
          for (var k = 0; k < SKIP_CLASSES.length; k++) {
            if (anc.classList.contains(SKIP_CLASSES[k])) return NodeFilter.FILTER_REJECT;
          }
        }
        if (p.classList && (p.classList.contains('gterm') || p.classList.contains('gterm-w'))) {
          return NodeFilter.FILTER_REJECT;
        }
        if (!node.nodeValue || node.nodeValue.trim().length < 4) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });

    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach(function (node) {
      if (count >= limit) return;
      var text = node.nodeValue;
      var lower = text.toLowerCase();

      // 一个节点里可能有多个术语（甚至同一术语多次出现）。
      // 做法：按位置排序后一次性重建该节点，避免「长词先命中就把短词挤掉」。
      var hits = [];
      var taken = [];  // 已占用的字符区间，防止嵌套标注

      for (var i = 0; i < words.length; i++) {
        var w = words[i];
        var term = index[w];
        if (seen[term.t]) continue;

        var at = lower.indexOf(w);
        while (at >= 0) {
          var before = lower.charAt(at - 1);
          var after = lower.charAt(at + w.length);
          var isAscii = /^[a-z0-9]/.test(w);

          // 英文术语：前后不能紧贴字母数字（允许紧跟中文字符），否则 MAE 会命中 MAEstro
          var okBefore = !(isAscii && /[a-z0-9]/.test(before));
          var okAfter = !(isAscii && /[a-z0-9]/.test(after));

          var overlap = taken.some(function (r) {
            return at < r[1] && at + w.length > r[0];
          });

          if (okBefore && okAfter && !overlap) break;
          at = lower.indexOf(w, at + 1);
        }
        if (at < 0) continue;

        // 同一节点内同一术语只标一次；跨节点由 seen 控制
        hits.push({ at: at, len: w.length, term: term });
        taken.push([at, at + w.length]);
        seen[term.t] = 1;
        count++;
        if (count >= limit) break;
      }

      if (!hits.length) return;

      // 按出现位置升序重建节点
      hits.sort(function (a, b) { return a.at - b.at; });
      var frag = document.createDocumentFragment();
      var cursor = 0;
      hits.forEach(function (h) {
        if (h.at > cursor) frag.appendChild(document.createTextNode(text.slice(cursor, h.at)));
        frag.appendChild(makeMark(text.substr(h.at, h.len), h.term));
        cursor = h.at + h.len;
      });
      if (cursor < text.length) frag.appendChild(document.createTextNode(text.slice(cursor)));
      node.parentNode.replaceChild(frag, node);
    });

    return count;
  }

  /* ---------- 4. 生成标记与气泡 ---------- */

  var tip = null;
  var tipTimer = null;

  function ensureTip() {
    if (tip) return tip;
    tip = document.createElement('div');
    tip.className = 'gterm-tip';
    tip.setAttribute('role', 'tooltip');
    document.body.appendChild(tip);
    return tip;
  }

  function makeMark(matched, term) {
    var el = document.createElement('span');
    el.className = 'gterm';
    el.setAttribute('tabindex', '0');
    el.setAttribute('data-gt', term.t);

    var inner = document.createElement('span');
    inner.className = 'gterm-w';
    inner.textContent = matched;
    el.appendChild(inner);

    var up = document.createElement('sup');
    up.className = 'gterm-i';
    up.textContent = '?';
    el.appendChild(up);

    el.addEventListener('mouseenter', function () { showTip(el, term); });
    el.addEventListener('focus', function () { showTip(el, term); });
    el.addEventListener('mouseleave', hideTipLater);
    el.addEventListener('blur', hideTipLater);
    // 移动端点一下也能看，不跳转
    el.addEventListener('click', function (e) {
      e.preventDefault();
      showTip(el, term);
    });
    return el;
  }

  function showTip(el, term) {
    clearTimeout(tipTimer);
    var t = ensureTip();

    var zh = term.z && term.z !== term.t ? '<span class="gt-zh">' + esc(term.z) + '</span>' : '';
    var en = term.t !== term.z ? '<span class="gt-en">' + esc(term.t) + '</span>' : '';
    t.innerHTML =
      '<div class="gt-head">' + zh + en + '</div>' +
      '<div class="gt-body">' + esc(term.s || '') + '</div>' +
      '<a class="gt-more" href="glossary.html#t-' + encodeURIComponent(term.t) + '">术语表详解 →</a>';

    t.style.visibility = 'hidden';
    t.style.display = 'block';

    var r = el.getBoundingClientRect();
    var tw = t.offsetWidth, th = t.offsetHeight;
    var left = r.left + r.width / 2 - tw / 2 + window.scrollX;
    left = Math.max(10 + window.scrollX, Math.min(left, window.scrollX + document.documentElement.clientWidth - tw - 10));
    var top = r.top + window.scrollY - th - 10;
    if (r.top - th - 10 < 4) top = r.top + window.scrollY + r.height + 10; // 顶部放不下就翻到下面

    t.style.left = left + 'px';
    t.style.top = top + 'px';
    t.style.visibility = 'visible';
    el.classList.add('on');
  }

  function hideTipLater() {
    tipTimer = setTimeout(function () {
      if (!tip) return;
      tip.style.display = 'none';
      document.querySelectorAll('.gterm.on').forEach(function (x) { x.classList.remove('on'); });
    }, 120);
  }

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* ---------- 5. 对外暴露 ---------- */

  window.GlossaryHover = {
    decorate: decorate,
    // 供详情页等动态渲染的页面在插入 HTML 之后调用
    scan: function (sel, limit) {
      return decorate(document.querySelector(sel), limit);
    }
  };

  /* ---------- 6. 自动挂载 ---------- */

  // 各页面只需在自身脚本之前引本文件，不用改页面结构里的其他位置
  function boot() {
    var page = (location.pathname.split('/').pop() || 'index.html');

    // 文献详情页：正文由 paper.html 内联脚本渲染到 #app，等它跑完再扫
    if (document.getElementById('app')) {
      setTimeout(function () { decorate(document.querySelector('.detail'), 40); }, 80);
      return;
    }
    // 列表页与新闻页：只扫正文区，避开导航与页脚
    var scope = document.querySelector('.pagehead, section .wrap, main') || null;
    if (page === 'glossary.html') return; // 术语表自己不需要悬停
    decorate(scope || document.body, 25);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
