/* 投稿口（kb-inbox.js）—— 文献页「这篇的全文我也有」的投稿与状态显示
 *
 * 纯静态站没有服务端，也不能在前端放任何凭据（见下），所以投稿走邮件：
 *   1. 浏览器里把格式、大小筛一遍，不合格当场说清楚，不让人白等；
 *   2. 生成一张结构化的「投递单」（编号、文献、许可、署名、文件指纹），
 *      填进 mailto: 的主题与正文——读者只需附上文件、点发送；
 *   3. 编号存在本地，按 assets/kb-inbox-data.js 的回执显示「处理中 / 已收录 / 需补充」。
 *
 * 为什么不是「页面直接把文件传到仓库」：
 *   静态站若在前端放一个能写仓库的令牌，等于把写权限公开在网页源码里；
 *   GitHub 的密钥扫描也会直接拦下这种提交。改用 GitHub issue 也不行——
 *   issue 的写接口（POST /issues、POST /comments）一律要求认证，匿名返回 401，
 *   想匿名提交就得把令牌放回前端，等于换个方式犯同一个错。
 *   邮件是唯一「读者天然有、我们天然能收、且不需要任何凭据」的通道。
 *   闭环因此靠编号自洽：投递有编号可查、处理有回执、入库后页面自动出现全文。
 */
(function () {
  var CFG = window.KBINBOX || null;      // 只有收件邮箱与开关，没有任何凭据
  var STATUS = window.KBINBOX_STATUS || [];
  var MAXMB = (CFG && CFG.maxMB) || 25;
  var MAIL = (CFG && CFG.reviewer) || 'editor@aivc.news';
  /* 邮件正文上限：mailto 链接太长会被邮件客户端截断，超了就只带要点、让读者自己附言 */
  var MAXBODY = 1600;

  var LIC = [
    ['cc-by', 'CC BY（署名）'],
    ['cc-by-nc', 'CC BY-NC（署名-非商业）'],
    ['cc-by-nc-nd', 'CC BY-NC-ND（署名-非商业-禁改）'],
    ['cc0', 'CC0 / 公有领域'],
    ['other', '其他（编辑部人工核实）'],
    ['unknown', '不确定，请编辑部核']
  ];

  function $(s, r) { return (r || document).querySelector(s); }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function kb(n) { return n >= 1000 ? (n / 1000).toFixed(1) + 'K 字' : n + ' 字'; }
  function licName(v) {
    for (var i = 0; i < LIC.length; i++) if (LIC[i][0] === v) return LIC[i][1].split('（')[0];
    return v || '';
  }

  /* ---------- 本地记录：文献 → 投递信息 ---------- */
  function recKey(pid) { return 'aivc_upl_' + pid; }
  function loadRec(pid) {
    try { return JSON.parse(localStorage.getItem(recKey(pid)) || 'null'); } catch (e) { return null; }
  }
  function saveRec(pid, rec) {
    try { localStorage.setItem(recKey(pid), JSON.stringify(rec)); } catch (e) { /* 隐私模式下静默 */ }
  }
  function statusOf(rid) {
    for (var i = 0; i < STATUS.length; i++) if (STATUS[i].r === rid) return STATUS[i];
    return null;
  }

  /* ---------- 指纹 ---------- */
  function sha256(buf) {
    if (!window.crypto || !crypto.subtle) return Promise.resolve('');
    return crypto.subtle.digest('SHA-256', buf).then(function (d) {
      return Array.prototype.map.call(new Uint8Array(d), function (x) {
        return ('0' + x.toString(16)).slice(-2);
      }).join('');
    });
  }
  function safe(name) {
    var dot = name.lastIndexOf('.');
    var stem = dot > 0 ? name.slice(0, dot) : name;
    var ext = dot > 0 ? name.slice(dot + 1).toLowerCase().replace(/[^a-z0-9]/g, '') : '';
    stem = stem.replace(/[^0-9A-Za-z\u4e00-\u9fff\-_]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 72) || 'paper';
    return ext ? stem + '.' + ext : stem;
  }

  /* ---------- 投递单 ----------
     纯文本，带机读头。后台 tools/uploader.py 从邮件正文里解出 rid / paper / license，
     所以格式不能随手改——改这里必须同步改那边的正则。 */
  function slip(o) {
    var head = [
      'AIVC-INSIGHT-UPLOAD v1',
      'rid: ' + o.rid,
      'paper: ' + o.pid,
      'license: ' + (o.lic || ''),
      'file: ' + o.file + ' (' + Math.round(o.size / 1024) + ' KB)',
      'sha256: ' + (o.sha || 'n/a'),
      ''
    ];
    var tail = [
      '',
      '---',
      '文献：' + o.title,
      '署名：' + (o.credit || '（未填）'),
      '原文：' + (o.url || '（未填）'),
      '说明：' + (o.note || '（未填）'),
      '',
      '请把全文文件作为附件一起发出。编辑部核验许可与归属后转成站内全文，',
      '处理结果会写回该篇详情页（凭编号 ' + o.rid + ' 查询）。'
    ];
    var body = head.concat(tail).join('\n');
    if (body.length > MAXBODY) {
      // 太长就只发机读头 + 最小信息，别让邮件客户端截断在关键字段中间
      body = head.slice(0, 6).concat(['---', '文献：' + o.title]).join('\n');
    }
    return {
      subject: '[全文投稿] ' + o.pid + ' ' + o.rid,
      body: body
    };
  }

  /* ---------- 界面 ---------- */
  function panel(host, pid, paper) {
    var box = el('div', 'kvupl');
    box.id = 'kv-upload';
    box.innerHTML =
      '<button class="kvbtn" type="button" aria-expanded="false">' +
        '<b>这篇的全文我也有</b><span>投给编辑部，核验后收录为站内全文</span></button>' +
      '<div class="kvbody" hidden>' +
        '<p class="kvint">投吧。只要你手上这份是合法拿到的（开放获取、机构订阅下载、作者自存稿），' +
        '并且许可允许转载，我们核完就把它做成站内可读全文——你可以检索、引用，别人也能。</p>' +
        '<div class="kvrow">' +
          '<label class="kvf"><span>全文文件</span><input type="file" accept=".pdf,.xml,.docx,.html,.htm,.md,.txt"></label>' +
        '</div>' +
        '<div class="kvrow two">' +
          '<label class="kvf"><span>许可类型 <i>必选</i></span><select>' +
            '<option value="">请选择…</option>' +
            LIC.map(function (x) { return '<option value="' + x[0] + '">' + x[1] + '</option>'; }).join('') +
          '</select></label>' +
          '<label class="kvf"><span>署名 <i>选填</i></span><input type="text" maxlength="120" placeholder="例：张伟（北京大学）"></label>' +
        '</div>' +
        '<label class="kvf"><span>原文链接 <i>选填</i></span><input type="url" maxlength="300" placeholder="https://doi.org/… 或出版社页面"></label>' +
        '<label class="kvf"><span>补充说明 <i>选填</i></span><textarea rows="2" maxlength="500" placeholder="例：机构订阅下载的版本；或指出我们哪一段读错了"></textarea></label>' +
        '<label class="kvck"><input type="checkbox"> 我确认这份全文是我合法获得的，且许可允许在 AIVC Insight 转载</label>' +
        '<div class="kvact"><button class="kvgo" type="button" disabled>生成投递单并写邮件</button>' +
          '<a class="kvmail" href="mailto:' + MAIL + '">直接发邮件</a></div>' +
        '<div class="kvmsg" role="status"></div>' +
      '</div>';
    host.appendChild(box);

    var btn = $('.kvbtn', box), body = $('.kvbody', box);
    var fileIn = $('input[type=file]', box), sel = $('select', box), ck = $('.kvck input', box);
    var go = $('.kvgo', box), msg = $('.kvmsg', box);
    var picked = null;

    function say(t, cls) {
      msg.className = 'kvmsg' + (cls ? ' ' + cls : '');
      msg.innerHTML = t;
    }
    function gate() {
      go.disabled = !(picked && sel.value && ck.checked);
    }

    btn.addEventListener('click', function () {
      var open = body.hidden;
      body.hidden = !open;
      btn.setAttribute('aria-expanded', String(open));
      if (open) { body.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
    });
    sel.addEventListener('change', gate);
    ck.addEventListener('change', gate);

    fileIn.addEventListener('change', function () {
      var f = fileIn.files && fileIn.files[0];
      if (!f) { picked = null; gate(); return; }
      var ext = (f.name.split('.').pop() || '').toLowerCase();
      var ok = ['pdf', 'xml', 'docx', 'html', 'htm', 'md', 'txt'].indexOf(ext) >= 0;
      if (!ok) { say('这个格式暂不支持。请给 PDF、JATS XML、Word、HTML 或纯文本。', 'bad'); picked = null; gate(); return; }
      if (f.size > MAXMB * 1024 * 1024) {
        say('文件 ' + (f.size / 1048576).toFixed(1) + 'MB，超过 ' + MAXMB + 'MB。' +
            '可以只给正文（去掉封面大图）。', 'bad');
        picked = null; gate(); return;
      }
      if (f.size < 12 * 1024) { say('文件只有 ' + Math.round(f.size / 1024) + 'KB，可能不是全文。确认后仍可提交。', 'warn'); }
      picked = { name: f.name, safe: safe(f.name), size: f.size, blob: f, sha: '' };
      say('已选 <b>' + esc(f.name) + '</b>（' + (f.size / 1024 / 1024).toFixed(2) + 'MB，' + ext.toUpperCase() + '）。填好许可并勾选确认即可生成投递单。');
      gate();
    });

    go.addEventListener('click', function () {
      if (!picked) return;
      go.disabled = true; go.textContent = '正在生成…';

      // 编号 = u + 秒级时间戳 + 4 位随机，同一秒内两次提交也不会撞号
      var rid = 'u' + new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14) +
        Math.random().toString(36).slice(2, 6);
      var readBuf = picked.blob.arrayBuffer ? picked.blob.arrayBuffer() : Promise.resolve(null);

      readBuf.then(function (buf) {
        return buf ? sha256(buf) : '';
      }).then(function (sha) {
        var s = slip({
          rid: rid, pid: pid, lic: sel.value, file: picked.safe, size: picked.size,
          sha: sha, title: paper.t,
          credit: ($('input[type=text]', box) || {}).value || '',
          url: ($('input[type=url]', box) || {}).value || '',
          note: ($('textarea', box) || {}).value || ''
        });
        var href = 'mailto:' + MAIL +
          '?subject=' + encodeURIComponent(s.subject) +
          '&body=' + encodeURIComponent(s.body);
        var rec = {
          rid: rid, at: new Date().toISOString(), name: picked.name,
          size: picked.size, lic: sel.value, mail: href
        };
        saveRec(pid, rec);
        go.textContent = '重新生成';

        msg.className = 'kvmsg ok';
        msg.innerHTML =
          '投递单已生成，编号 <b>' + esc(rid) + '</b>（存在本机，下次打开这页会显示处理状态）。' +
          '<br><b>还差两步：</b>' +
          '<br>1. <a href="' + esc(href) + '" class="kvopen"><b>点这里打开发给编辑部的邮件</b></a>（主题与正文已填好）' +
          '<br>2. 把那封邮件里的<b>附件</b>补成 <b>' + esc(picked.name) + '</b>，然后发送。' +
          '<br><span class="kvhint">你刚选的文件不会离开这台电脑——浏览器无权替你把它挂到邮件上，' +
          '所以第 2 步需要你自己拖一次。核验通过后，这页会出现「读站内全文」。</span>';
        renderStatus(host, pid);
      }).catch(function (e) {
        go.disabled = false; go.textContent = '重新生成';
        say('生成失败：' + esc(e.message || e) + '。可以刷新重试。', 'bad');
      });
    });

    return box;
  }

  /* ---------- 状态条 ---------- */
  function renderStatus(host, pid) {
    var rec = loadRec(pid);
    var old = $('.kvstat', host);
    if (old) old.parentNode.removeChild(old);
    if (!rec) return;
    var st = statusOf(rec.rid);
    var line = el('div', 'kvstat');
    var label, cls;
    if (!st) { label = '处理中：已发出，等编辑部核验'; cls = 'wait'; }
    else if (st.s === 'done') { label = '已收录：站内全文已上线'; cls = 'ok'; }
    else if (st.s === 'blocked') { label = '需补充：' + st.m; cls = 'bad'; }
    else { label = '处理中：' + (st.m || '正在解析'); cls = 'wait'; }
    line.className = 'kvstat ' + cls;
    line.innerHTML = '<b>' + esc(label) + '</b><span>投稿 ' + esc(rec.rid) + ' · ' +
      esc(rec.name) + ' · ' + new Date(rec.at).toLocaleDateString('zh-CN') +
      (st && st.s === 'done' ? ' · <a href="kb/' + pid + '.html">去看全文 →</a>' : '') + '</span>';
    host.appendChild(line);
  }

  /* ---------- 挂载 ---------- */
  function mount() {
    var host = $('#kv');
    if (!host) return;
    var pid = new URLSearchParams(location.search).get('id');
    if (!pid) return;
    /* papers-data.js 用 const 声明 PAPERS，它不在 window 上但作用域里能直接读到；
       这里不判断 typeof window.PAPERS，否则投稿口会静默不渲染。 */
    var list = (typeof PAPERS !== 'undefined') ? PAPERS : null;
    var paper = null;
    for (var i = 0; list && i < list.length; i++) if (list[i].id === pid) paper = list[i];
    if (!paper) return;
    if (!CFG || !CFG.enabled) {
      // 收件通道关掉时不让按钮出现，直接给邮件，避免读者点了没反应
      host.innerHTML = '<div class="kvstat"><b>投稿口暂停</b><span>请发邮件至 ' +
        '<a href="mailto:' + MAIL + '">' + MAIL + '</a>，注明文献编号 ' + esc(pid) + '</span></div>';
      return;
    }
    panel(host, pid, paper);
    renderStatus(host, pid);
    if (/[?&]upl=1/.test(location.search)) {
      var b = $('.kvbtn', host);
      if (b) { b.click(); setTimeout(function () { host.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 60); }
    }
  }

  try {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
    else mount();
  } catch (e) {
    // 投稿口挂了不能连累文献页：把原因留在控制台，页面上退回邮件
    try {
      console.error('[投稿口]', e);
      var h = document.getElementById('kv');
      if (h) h.innerHTML = '<div class="kvstat bad"><b>投稿口暂时用不了</b><span>请发邮件至 ' + MAIL + '</span></div>';
    } catch (e2) { /* 连兜底都失败就什么都别做了 */ }
  }
})();
