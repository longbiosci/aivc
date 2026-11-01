/* AIVC Insight — 文献评论区（原型版）
 * 挂在 paper.html 的 #comments 容器上，按文献编号 pid 归档。
 * 接口契约见 tools/proto_comments.py；生产版换 Workers + D1 时前端不用改。
 * 纪律：前端不携带任何凭据（OPS §3.2.6 同款红线）。
 */
(function () {
  'use strict';

  var API = (window.AIVC_COMMENTS_API || '');
  var root = document.getElementById('comments');
  if (!root) return;
  var pid = new URLSearchParams(location.search).get('id');
  if (!pid) return;

  var state = { me: { kind: 'guest', name: '游客（新）', admin: false }, items: [], replyTo: null };

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function api(path, opts) {
    return fetch(API + path, Object.assign({ credentials: 'same-origin' }, opts || {}))
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, data: j }; }); })
      .catch(function () { return { ok: false, data: { error: '网络不通：原型服务没启动？' } }; });
  }

  /* ---------- 渲染骨架 ---------- */
  function skeleton() {
    root.innerHTML =
      '<div class="cmhead">' +
        '<div class="cmtitle">讨论<small id="cm-count"></small></div>' +
        '<div class="cmwho" id="cm-who"></div>' +
      '</div>' +
      '<div class="cmbox" id="cm-box">' +
        '<div class="cmbox-hint" id="cm-hint"></div>' +
        '<textarea id="cm-input" rows="3" maxlength="2000" placeholder="说点什么：对这条文献的判断、你读到的疑点、或者你认为本站漏掉的东西。"></textarea>' +
        '<div class="cmbox-foot">' +
          '<span class="cm-replying" id="cm-replying" hidden></span>' +
          '<span class="cm-grow"></span>' +
          '<span class="cm-context" id="cm-namebox"></span>' +
          '<button class="cmbtn" id="cm-send" type="button">发表</button>' +
        '</div>' +
      '</div>' +
      '<div class="cmlist" id="cm-list"></div>' +
      '<div class="cmlogin" id="cm-login" hidden>' +
        '<div class="cmlogin-h">用账号登录（原型内置两个测试账号）</div>' +
        '<div class="cmlogin-row">' +
          '<input id="cm-email" type="email" placeholder="邮箱" autocomplete="username">' +
          '<input id="cm-pw" type="password" placeholder="密码" autocomplete="current-password">' +
          '<button class="cmbtn ghost" id="cm-do-login" type="button">登录</button>' +
        '</div>' +
        '<div class="cmlogin-tip">editor@aivc.news（管理员）· reader@example.com（读者）· 密码均为 proto123。' +
        '<b>游客无需登录，直接发言即可</b>，系统会自动分配一个代号。</div>' +
      '</div>';
  }

  function paintWho() {
    var me = state.me;
    var who = document.getElementById('cm-who');
    var namebox = document.getElementById('cm-namebox');
    if (me.kind === 'user') {
      who.innerHTML = '<span class="cm-chip user">' + esc(me.name) + (me.admin ? ' · 管理员' : '') + '</span>' +
        '<button class="cmlink" id="cm-logout" type="button">退出</button>' +
        (me.admin ? ' <a class="cmlink" href="#admin">后台</a>' : '');
      namebox.textContent = '以 ' + me.name + ' 的身份发言';
      var lo = document.getElementById('cm-logout');
      if (lo) lo.onclick = function () { api('/api/logout', { method: 'POST' }).then(boot); };
    } else {
      who.innerHTML = '<span class="cm-chip guest">' + esc(me.name) + '</span>' +
        '<button class="cmlink" id="cm-showlogin" type="button">我有账号</button>';
      namebox.textContent = '以 ' + me.name + ' 的身份发言（游客）';
      var sl = document.getElementById('cm-showlogin');
      var box = document.getElementById('cm-login');
      if (sl) sl.onclick = function () { box.hidden = !box.hidden; };
    }
  }

  /* ---------- 评论列表 ---------- */
  function renderList() {
    var list = document.getElementById('cm-list');
    var tops = state.items.filter(function (c) { return !c.parent_id; });
    var kids = {};
    state.items.forEach(function (c) {
      if (c.parent_id) (kids[c.parent_id] = kids[c.parent_id] || []).push(c);
    });
    document.getElementById('cm-count').textContent = state.items.length
      ? ' · ' + state.items.length + ' 条' : '';

    if (!tops.length) {
      list.innerHTML = '<div class="cmempty">还没有人说话。第一条往往最难，也最有用。</div>';
      return;
    }
    list.innerHTML = tops.map(function (c) {
      var thread = (kids[c.id] || []).map(function (k) { return itemHTML(k, true); }).join('');
      return itemHTML(c, false) + (thread ? '<div class="cmthread">' + thread + '</div>' : '');
    }).join('');

    list.querySelectorAll('[data-reply]').forEach(function (b) {
      b.onclick = function () {
        var id = parseInt(b.getAttribute('data-reply'), 10);
        var t = state.items.filter(function (x) { return x.id === id; })[0];
        state.replyTo = id;
        var bar = document.getElementById('cm-replying');
        bar.hidden = false;
        bar.innerHTML = '回复 ' + esc(t.author) + ' <button class="cmlink" type="button" id="cm-cancel">取消</button>';
        document.getElementById('cm-input').focus();
        document.getElementById('cm-cancel').onclick = function () {
          state.replyTo = null; bar.hidden = true; bar.innerHTML = '';
        };
      };
    });
    list.querySelectorAll('[data-del]').forEach(function (b) {
      b.onclick = function () {
        if (!confirm('确认删除这条评论？可以在后台恢复。')) return;
        api('/api/admin/moderate', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: parseInt(b.getAttribute('data-del'), 10), action: 'delete' })
        }).then(load);
      };
    });
  }

  function itemHTML(c, isChild) {
    var badge = c.is_editor ? '<span class="cm-tag ed">编辑部</span>'
      : (c.kind === 'user' ? '<span class="cm-tag usr">注册用户</span>' : '');
    var del = state.me.admin ? ' <button class="cmlink danger" type="button" data-del="' + c.id + '">删除</button>' : '';
    return '<div class="cmitem' + (isChild ? ' child' : '') + '" data-id="' + c.id + '">' +
      '<div class="cmm">' +
        '<b class="cmname ' + (c.kind === 'guest' ? 'g' : '') + '">' + esc(c.author) + '</b>' + badge +
        '<span class="cmtime">' + esc(c.at) + '</span>' +
      '</div>' +
      '<div class="cmbody">' + esc(c.content).replace(/\n/g, '<br>') + '</div>' +
      '<div class="cmact">' +
        '<button class="cmlink" type="button" data-reply="' + c.id + '">回复</button>' +
        (c.mine ? ' <span class="cm-mine">你</span>' : '') + del +
      '</div>' +
    '</div>';
  }

  /* ---------- 发送 ---------- */
  function send() {
    var ta = document.getElementById('cm-input');
    var txt = ta.value.trim();
    var btn = document.getElementById('cm-send');
    if (!txt) { ta.focus(); return; }
    btn.disabled = true;
    api('/api/comments', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid: pid, content: txt, parent_id: state.replyTo })
    }).then(function (r) {
      btn.disabled = false;
      if (!r.ok) { alert(r.data.error || '发送失败'); return; }
      ta.value = '';
      state.replyTo = null;
      var bar = document.getElementById('cm-replying');
      bar.hidden = true; bar.innerHTML = '';
      if (r.data.status === 'pending') {
        flash('已提交，等待编辑部审核（这条只有审核通过后才会公开）');
      } else {
        flash('已发表。');
      }
      load();
      api('/api/me').then(function (m) { if (m.ok) { state.me = m.data; paintWho(); } });
    });
  }

  function flash(msg) {
    var h = document.getElementById('cm-hint');
    h.textContent = msg;
    h.classList.add('show');
    setTimeout(function () { h.classList.remove('show'); }, 4200);
  }

  function load() {
    return api('/api/comments?pid=' + encodeURIComponent(pid)).then(function (r) {
      state.items = r.ok ? r.data.items : [];
      renderList();
    });
  }

  function bindLogin() {
    var go = document.getElementById('cm-do-login');
    if (!go) return;
    go.onclick = function () {
      api('/api/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: document.getElementById('cm-email').value,
          password: document.getElementById('cm-pw').value
        })
      }).then(function (r) {
        if (!r.ok) { alert(r.data.error || '登录失败'); return; }
        boot();
      });
    };
  }

  function boot() {
    skeleton();
    api('/api/me').then(function (m) {
      if (m.ok) state.me = m.data;
      paintWho();
      bindLogin();
      document.getElementById('cm-send').onclick = send;
      document.getElementById('cm-input').addEventListener('keydown', function (e) {
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') send();
      });
      load();
    });
  }

  boot();
})();
