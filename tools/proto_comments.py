#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIVC Insight 评论区 · 本地原型服务（仅用于原型验证，不是生产实现）
=====================================================================
目的：让你在浏览器里真的点一遍——游客发评论、拿代号、登录发言、后台删除。

刻意用 Python 标准库 + JSON 文件，不引入依赖：
    python3 tools/proto_comments.py            # 默认 8787 端口
    python3 tools/proto_comments.py --port 9000

生产版会换成 Cloudflare Workers + D1，但**接口形状保持一致**，
这样前端代码可以平移，不用重写。这是原型能省时间的唯一理由。

数据落在 /tmp/aivc-proto/（不入库），删掉即复位。

接口：
    GET  /api/comments?pid=p116      列出评论（含游客代号）
    POST /api/comments               发评论 {pid, content, parent_id}
    POST /api/login                  登录 {email, password}（原型用固定账号）
    POST /api/logout
    GET  /api/me                     当前身份
    GET  /api/admin/comments         后台列表（需 admin）
    POST /api/admin/moderate         删除/恢复 {id, action}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import secrets
import sys
import time
import uuid
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = Path("/tmp/aivc-proto")
DATA.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA / "comments.json"
SESS_FILE = DATA / "sessions.json"

# 原型固定账号：生产版走邮箱验证码 / GitHub OAuth
PROTO_USERS = {
    "editor@aivc.news": {"pw": "proto123", "name": "编辑部", "admin": True},
    "reader@example.com": {"pw": "proto123", "name": "读者小周", "admin": False},
}

MAX_LEN = 2000


def load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path: Path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def guest_code(uid: str) -> str:
    """由匿名 uid 稳定派生代号：同一浏览器永远同一代号，不留原始 uid。"""
    h = hashlib.sha256(uid.encode("utf-8")).hexdigest()
    return "游客 %03d" % (int(h[:6], 16) % 1000)


def now_ts() -> int:
    return int(time.time())


def fmt_time(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


# ---------------- 极简「脏评论」拦截（原型级，生产用 Turnstile + 人工） ----------------
LINK_RE = re.compile(r"https?://", re.I)
SPAM_WORDS = ("加微信", "加V", "代购", "办证", "博彩", "棋牌", "贷", "裸聊", "约炮")


def screen(content: str) -> tuple[str, str]:
    """返回 (状态, 原因)。状态 ∈ ok / pending。"""
    if not content.strip():
        return "reject", "内容为空"
    if len(content) > MAX_LEN:
        return "reject", "超过 %d 字" % MAX_LEN
    if len(LINK_RE.findall(content)) >= 2:
        return "pending", "含多个外链，待人工审核"
    low = content.lower()
    if any(w.lower() in low for w in SPAM_WORDS):
        return "pending", "命中敏感词，待人工审核"
    return "ok", ""


class Handler(BaseHTTPRequestHandler):
    server_version = "AIVCProto/0.1"

    # ---------- 工具 ----------
    def log_message(self, fmt, *args):
        sys.stderr.write("[proto] %s\n" % (fmt % args))

    def _json(self, obj, code=200, extra_headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # 允许传 dict 或 [(k, v), ...]——多条 Set-Cookie 必须用列表，否则会被合并掉
        pairs = extra_headers.items() if isinstance(extra_headers, dict) else (extra_headers or [])
        for k, v in pairs:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def _cookies(self):
        c = SimpleCookie()
        c.load(self.headers.get("Cookie") or "")
        return c

    def _identity(self):
        """返回 (kind, name, admin, uid)；kind ∈ user / guest"""
        sessions = load(SESS_FILE, {})
        tok = self._cookies().get("aivc_sid")
        if tok:
            s = sessions.get(tok.value)
            if s and s.get("exp", 0) > now_ts():
                return "user", s["name"], bool(s.get("admin")), s["email"]
        uid = None
        g = self._cookies().get("aivc_gid")
        if g and re.fullmatch(r"[0-9a-f]{32}", g.value or ""):
            uid = g.value
        return "guest", None, False, uid

    def _set_cookie(self, key, val, max_age):
        return "Set-Cookie", "%s=%s; Path=/; Max-Age=%d; SameSite=Lax" % (key, val, max_age)

    # ---------- 路由 ----------
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p == "/api/me":
            kind, name, admin, uid = self._identity()
            return self._json({
                "kind": kind,
                "name": name or (guest_code(uid) if uid else "游客（新）"),
                "admin": admin,
            })
        if p == "/api/comments":
            pid = (parse_qs(u.query).get("pid") or [""])[0]
            return self._list_comments(pid)
        if p == "/api/admin/comments":
            kind, _, admin, _ = self._identity()
            if not admin:
                return self._json({"error": "需要管理员身份"}, 403)
            return self._list_comments(None, admin=True)
        return self._static(p)

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/comments":
            return self._add_comment()
        if p == "/api/login":
            return self._login()
        if p == "/api/logout":
            return self._json({"ok": True}, extra_headers=[self._set_cookie("aivc_sid", "", 0)])
        if p == "/api/admin/moderate":
            return self._moderate()
        return self._json({"error": "not found"}, 404)

    # ---------- 业务 ----------
    def _list_comments(self, pid, admin=False):
        db = load(DB_FILE, {"seq": 0, "items": []})
        items = [c for c in db["items"] if pid is None or c["pid"] == pid]
        if not admin:
            items = [c for c in items if c["status"] == "ok"]
        out = []
        for c in sorted(items, key=lambda x: x["id"]):
            out.append({
                "id": c["id"],
                "pid": c["pid"],
                "parent_id": c["parent_id"],
                "author": c["author"],
                "kind": c["kind"],
                "is_editor": c.get("is_editor", False),
                "content": c["content"],
                "at": fmt_time(c["at"]),
                "status": c["status"],
                "reason": c.get("reason", ""),
                "mine": c.get("uid") == self._identity()[3],
            })
        return self._json({"total": len(out), "items": out})

    def _add_comment(self):
        kind, name, admin, uid = self._identity()
        data = self._body()
        pid = str(data.get("pid") or "").strip()
        content = str(data.get("content") or "").strip()
        parent = data.get("parent_id")
        if not re.fullmatch(r"p\d{2,4}", pid):
            return self._json({"error": "文献编号不合法"}, 400)
        status, reason = screen(content)
        if status == "reject":
            return self._json({"error": reason}, 400)

        # 游客首次发言分配匿名 uid，写进 Cookie（生产版同样逻辑）
        headers = []
        if kind == "guest" and not uid:
            uid = uuid.uuid4().hex
            headers.append(self._set_cookie("aivc_gid", uid, 60 * 60 * 24 * 365))

        db = load(DB_FILE, {"seq": 0, "items": []})
        db["seq"] = int(db.get("seq", 0)) + 1
        rec = {
            "id": db["seq"],
            "pid": pid,
            "parent_id": parent,
            "author": name if kind == "user" else guest_code(uid),
            "kind": kind,
            "is_editor": bool(admin),
            "content": content,
            "at": now_ts(),
            "status": status,
            "reason": reason,
            "uid": uid,
        }
        db["items"].append(rec)
        save(DB_FILE, db)
        msg = "已发布" if status == "ok" else "已提交，等待编辑部审核（%s）" % reason
        return self._json({"ok": True, "id": rec["id"], "status": status, "message": msg},
                          extra_headers=headers)

    def _login(self):
        data = self._body()
        email = str(data.get("email") or "").strip().lower()
        pw = str(data.get("password") or "")
        u = PROTO_USERS.get(email)
        if not u or u["pw"] != pw:
            return self._json({"error": "邮箱或密码不正确"}, 401)
        tok = secrets.token_urlsafe(24)
        sessions = load(SESS_FILE, {})
        sessions[tok] = {"email": email, "name": u["name"], "admin": u["admin"],
                         "exp": now_ts() + 3600 * 24 * 7}
        save(SESS_FILE, sessions)
        return self._json({"ok": True, "name": u["name"], "admin": u["admin"]},
                          extra_headers=[self._set_cookie("aivc_sid", tok, 3600 * 24 * 7)])

    def _moderate(self):
        _, _, admin, _ = self._identity()
        if not admin:
            return self._json({"error": "需要管理员身份"}, 403)
        data = self._body()
        cid = data.get("id")
        action = data.get("action")
        if action not in ("delete", "restore"):
            return self._json({"error": "action 只能 delete / restore"}, 400)
        db = load(DB_FILE, {"seq": 0, "items": []})
        for c in db["items"]:
            if c["id"] == cid:
                c["status"] = "deleted" if action == "delete" else "ok"
                save(DB_FILE, db)
                return self._json({"ok": True})
        return self._json({"error": "未找到该评论"}, 404)

    # ---------- 静态文件 ----------
    def _static(self, p):
        if p in ("/", ""):
            p = "/paper.html"
        if p.startswith("/__proto__"):
            return self._json({"error": "not found"}, 404)
        fp = (ROOT / p.lstrip("/")).resolve()
        try:
            fp.relative_to(ROOT)
        except ValueError:
            return self._bad(HTTPStatus.FORBIDDEN)
        if not fp.is_file():
            return self._bad(HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/xml"):
            ctype += "; charset=utf-8"
        body = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _bad(self, code):
        body = b"<!doctype html><meta charset=utf-8><h1>404</h1>"
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--reset", action="store_true", help="清空原型数据后启动")
    a = ap.parse_args()
    if a.reset:
        for f in (DB_FILE, SESS_FILE):
            f.unlink(missing_ok=True)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print("原型服务已启动 http://%s:%d/paper.html?id=p116" % (a.host, a.port), file=sys.stderr)
    print("账号：editor@aivc.news / reader@example.com，密码均为 proto123", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
