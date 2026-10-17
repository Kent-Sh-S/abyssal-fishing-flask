"""Flask edition: username/password accounts and signed-cookie game saves."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
import re
import unicodedata
import math
from datetime import timedelta

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from itsdangerous import BadData, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException

import game
import developer


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True,
                instance_path=(config or {}).get("INSTANCE_PATH"))
    app.json.sort_keys = False
    app.config.from_mapping(
        DATABASE=os.environ.get("ABYSS_DATABASE", str(Path(app.instance_path) / "abyss.sqlite3")),
        SESSION_COOKIE_NAME="abyss_session",
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=365),
        MAX_CONTENT_LENGTH=4096,
    )
    if config:
        app.config.update(config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get("SECRET_KEY"):
        key_path = Path(app.instance_path) / ".secret"
        if "ABYSS_SECRET" in os.environ:
            app.config["SECRET_KEY"] = os.environ["ABYSS_SECRET"]
        else:
            try:
                with key_path.open("x") as handle:
                    handle.write(secrets.token_hex(32))
                key_path.chmod(0o600)
            except FileExistsError:
                pass
            app.config["SECRET_KEY"] = key_path.read_text().strip()
    with sqlite3.connect(app.config["DATABASE"]) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, created_at REAL NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
            attempt_key TEXT PRIMARY KEY, failures INTEGER NOT NULL,
            expires REAL NOT NULL
        )""")
        developer.init_schema(db)
    saves = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="abyssal-cookie-save-v1")
    dummy_hash = generate_password_hash(secrets.token_urlsafe(32))
    save_max_age = 365 * 24 * 60 * 60

    def identity():
        session.permanent = True
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        return session["csrf"]

    def account():
        uid = session.get("user_id")
        if type(uid) is not int:
            raise game.RuleError("请先登录你的潜航员账号", 401)
        with sqlite3.connect(app.config["DATABASE"]) as db:
            row = db.execute("SELECT id, username, developer_enabled FROM accounts WHERE id=?", (uid,)).fetchone()
        if row is None:
            raise game.RuleError("登录已失效，请重新登录", 401)
        return dict(id=row[0], username=row[1], developer_enabled=bool(row[2]))

    def save_name(uid):
        return f"abyss_save_{uid}"

    def read_player(uid):
        token = request.cookies.get(save_name(uid))
        if token:
            try:
                data = saves.loads(token, max_age=save_max_age)
                p = data["game"]
                if (data["user"] == uid and 0 <= p["diamonds"] <= game.INT64_MAX
                        and type(p["diamonds"]) is int and math.isfinite(p["gold"])
                        and 0 <= p["gold"] <= game.GOLD_CAP and 1 <= p["level"] <= game.MAX_LEVEL):
                    return p
            except (BadData, KeyError, TypeError, ValueError):
                pass
        return game.new_player()

    def write_player(uid, p):
        # Six recent specimens keep the signed save well below browser limits.
        payload = dict(p)
        payload["history"] = p["history"][:6]
        token = saves.dumps(dict(user=uid, game=payload))
        if len(token) > 3750:
            payload["history"] = []
            token = saves.dumps(dict(user=uid, game=payload))
        if len(token) > 3750:
            raise game.RuleError("Cookie 存档空间不足，请联系维护者", 500)
        g.save_cookie = (save_name(uid), token)

    def transaction(action=None):
        identity()
        user = account()
        p = read_player(user["id"])
        auto_count = game.settle_auto(p)
        result = action(p) if action else {}
        write_player(user["id"], p)
        return jsonify(state=game.public_state(p), result=result, auto_catches=auto_count,
                       csrf=session["csrf"], account=user, storage="signed-cookie")

    @app.before_request
    def protect_mutations():
        if request.routing_exception is not None:
            return  # Let Flask report a missing route or incorrect HTTP method.
        # Only the dedicated, key-authenticated blueprint is CSRF exempt.
        if request.method == "POST" and request.blueprint != "developer_api":
            if not session.get("csrf") or not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session["csrf"]):
                raise game.RuleError("会话已刷新，请重新载入页面", 403)

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith(("/api/", "/auth/")) or request.path in ("/", "/login"):
            response.headers["Cache-Control"] = "no-store"
        if hasattr(g, "save_cookie"):
            name, value = g.save_cookie
            response.set_cookie(name, value, max_age=save_max_age, httponly=True,
                                secure=request.is_secure or app.config["SESSION_COOKIE_SECURE"],
                                samesite="Lax", path="/")
        if getattr(g, "clear_legacy_cookie", False):
            response.delete_cookie("session", path="/")
        return response

    @app.errorhandler(game.RuleError)
    def rule_error(error):
        if request.blueprint in ("developer_api", "developers"):
            return jsonify(ok=False, error=str(error)), error.status
        return jsonify(error=str(error)), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path in developer.API_PATHS:
            response = jsonify(ok=False, error=error.description)
            response.status_code = error.code
            response.headers["Cache-Control"] = "no-store"
            return response
        return error

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise game.RuleError("请求必须是 JSON 对象")
        return value

    @app.get("/")
    def index():
        identity()
        if not session.get("user_id"):
            return redirect(url_for("login_page"))
        try:
            user = account()
        except game.RuleError:
            return redirect(url_for("login_page"))
        return render_template("index.html", fish=game.FISH, username=user["username"],
                               developer_enabled=user["developer_enabled"],
                               desktop=app.config.get("DESKTOP_MODE", False))

    @app.get("/login")
    def login_page():
        identity()
        return render_template("auth.html", csrf=session["csrf"],
                               desktop=app.config.get("DESKTOP_MODE", False))

    @app.get("/auth/csrf")
    def auth_csrf():
        return jsonify(csrf=identity())

    def credentials():
        data = body()
        username, password = data.get("username"), data.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise game.RuleError("请输入账号名和密码")
        username = unicodedata.normalize("NFKC", username.strip())
        if not re.fullmatch(r"[\w-]{3,24}", username):
            raise game.RuleError("账号名须为 3—24 位中文、字母、数字、下划线或短横线")
        if not 8 <= len(password) <= 128:
            raise game.RuleError("密码须为 8—128 个字符")
        return username, username.casefold(), password

    def sign_in(uid, username, destination="/"):
        session.clear()
        session["user_id"], session["username"] = uid, username
        identity()
        return jsonify(ok=True, redirect=destination, csrf=session["csrf"], username=username)

    @app.post("/auth/register")
    def register():
        username, key, password = credentials()
        plan = body().get("developer_plan", False)
        if type(plan) is not bool:
            raise game.RuleError("开发者计划选项必须为布尔值")
        password_hash = generate_password_hash(password, method="scrypt")
        with sqlite3.connect(app.config["DATABASE"]) as db:
            try:
                row = db.execute("INSERT INTO accounts(username,username_key,password_hash,created_at,developer_enabled) VALUES(?,?,?,?,?)",
                                 (username, key, password_hash, time.time(), int(plan)))
            except sqlite3.IntegrityError:
                raise game.RuleError("这个账号名已被使用，请直接登录或换个名字", 409)
            uid = row.lastrowid
        p = game.new_player()
        # Claim this browser's pre-login edition save once, without deleting it.
        legacy_token = request.cookies.get("session")
        if legacy_token:
            try:
                legacy = app.session_interface.get_signing_serializer(app).loads(legacy_token, max_age=save_max_age)
                with sqlite3.connect(app.config["DATABASE"]) as db:
                    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='players'").fetchone()
                    row = db.execute("SELECT gold,diamonds,data FROM players WHERE id=?", (legacy.get("player", ""),)).fetchone() if exists else None
                if row:
                    p = json.loads(row[2])
                    p["gold"], p["diamonds"] = row[0], row[1]
                    g.clear_legacy_cookie = True
            except (BadData, TypeError, ValueError):
                pass
        write_player(uid, p)
        return sign_in(uid, username, "/developer" if plan else "/")

    @app.post("/auth/login")
    def login():
        username, key, password = credentials()
        attempt_key = f"{request.remote_addr}:{key}"
        now = time.time()
        with sqlite3.connect(app.config["DATABASE"], timeout=15) as db:
            db.execute("BEGIN IMMEDIATE")
            attempt = db.execute("SELECT failures, expires FROM login_attempts WHERE attempt_key=?", (attempt_key,)).fetchone()
            if attempt and attempt[0] >= 5 and attempt[1] > now:
                raise game.RuleError("尝试过于频繁，请一分钟后重试", 429)
            row = db.execute("SELECT id,username,password_hash FROM accounts WHERE username_key=?", (key,)).fetchone()
            valid = check_password_hash(row[2] if row else dummy_hash, password)
            if not valid:
                failures = attempt[0] + 1 if attempt and attempt[1] > now else 1
                db.execute("INSERT INTO login_attempts VALUES(?,?,?) ON CONFLICT(attempt_key) DO UPDATE SET failures=excluded.failures,expires=excluded.expires",
                           (attempt_key, failures, now + 60))
            else:
                db.execute("DELETE FROM login_attempts WHERE attempt_key=?", (attempt_key,))
        if not valid:
            raise game.RuleError("账号名或密码不正确", 401)
        return sign_in(row[0], row[1])

    @app.post("/auth/logout")
    def logout():
        session.clear()
        identity()
        return jsonify(ok=True, redirect="/login", csrf=session["csrf"])

    @app.get("/api/state")
    def state():
        return transaction()

    @app.post("/api/catch")
    def catch():
        return transaction(game.manual_catch)

    @app.post("/api/upgrade")
    def upgrade():
        mode = body().get("mode", "one")
        return transaction(lambda p: game.upgrade_player(p, mode))

    @app.post("/api/gear")
    def gear():
        key = body().get("key")
        if not isinstance(key, str):
            raise game.RuleError("请选择有效装备")
        return transaction(lambda p: game.upgrade_gear(p, key))

    @app.post("/api/auto")
    def auto():
        enabled = body().get("enabled")
        if type(enabled) is not bool:
            raise game.RuleError("拖网开关必须为布尔值")
        return transaction(lambda p: game.set_net(p, enabled))

    @app.post("/api/exchange")
    def exchange():
        fraction = body().get("fraction", 100)
        return transaction(lambda p: game.exchange(p, fraction))

    @app.post("/api/reset")
    def reset():
        if body().get("confirm") != "深渊":
            raise game.RuleError("输入「深渊」以确认重新开始")
        def action(p):
            p.clear()
            p.update(game.new_player())
            return dict(message="新的航程开始了")
        return transaction(action)

    developer.install(app, identity=identity, account=account,
                      read_player=read_player, write_player=write_player)
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5050")), debug=False)
