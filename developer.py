"""Flask-only developer plan, scoped User Keys and the documented game API."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time

from flask import Blueprint, g, jsonify, render_template, request, session

import game


API_ROUTES = (
    ("POST", "/fish/enablenet", "开启自动渔网", "必须已拥有自动拖网，否则 400。重复开启不重置作业进度。"),
    ("POST", "/fish/disablenet", "关闭自动渔网", "必须已拥有自动拖网，否则 400。"),
    ("POST", "/fish", "手动钓一次鱼", "每次间隔至少 0.65 秒，冷却中返回 429。"),
    ("POST", "/diamond25", "投入 25% 金币兑换钻石", "Lv.30 解锁，否则 400；常规兑换按整兆取整。"),
    ("POST", "/diamond50", "投入 50% 金币兑换钻石", "Lv.30 解锁，否则 400；常规兑换按整兆取整。"),
    ("POST", "/diamonds", "投入全部金币兑换钻石", "Lv.30 解锁，否则 400；未满一兆返回 400。"),
    ("POST", "/uphufu", "升级深渊护符", "消耗钻石，Lv.30 解锁；余额不足、未解锁或已满级均返回 400。"),
    ("POST", "/upshengna", "升级异变声呐", "消耗金币；余额不足或已满级返回 400。"),
    ("POST", "/uptuowang", "购买或升级自动拖网", "消耗金币，Lv.5 解锁；购买第一级会自动开启拖网。"),
    ("POST", "/upgrademain", "升级潜航员一次", "消耗金币，与网页升级一次相同；金币不足或已达 Lv.870 返回 400。"),
    ("GET", "/getpays", "获取金币、钻石和渔获数", "data 返回 gold、diamonds、catches。"),
    ("GET", "/tujian", "获取已解锁与未解锁图鉴", "unlocked 为已捕获档案，locked 为未捕获档案；available 表示等级是否允许捕获。"),
)
API_PATHS = frozenset(row[1] for row in API_ROUTES)


def init_schema(db):
    columns = {row[1] for row in db.execute("PRAGMA table_info(accounts)")}
    if "developer_enabled" not in columns:
        db.execute("ALTER TABLE accounts ADD COLUMN developer_enabled INTEGER NOT NULL DEFAULT 0")
    db.execute("""CREATE TABLE IF NOT EXISTS user_keys (
        id TEXT PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
        name TEXT NOT NULL, key_hash TEXT NOT NULL UNIQUE, prefix TEXT NOT NULL,
        created_at REAL NOT NULL, last_used_at REAL, revoked_at REAL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS user_keys_account ON user_keys(account_id)")


def install(app, *, identity, account, read_player, write_player):
    portal = Blueprint("developers", __name__)
    api = Blueprint("developer_api", __name__)

    def database():
        return sqlite3.connect(app.config["DATABASE"], timeout=15)

    def developer_account():
        user = account()
        if not user["developer_enabled"]:
            raise game.RuleError("请先加入开发者计划【beta】", 403)
        return user

    def json_body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise game.RuleError("请求必须是 JSON 对象")
        return data

    @portal.get("/developer")
    def dashboard():
        user = account()
        identity()
        return render_template("developer.html", user=user, csrf=session["csrf"])

    @portal.get("/developer/docs")
    def handbook():
        user = developer_account()
        return render_template("developer_docs.html", user=user, routes=API_ROUTES,
                               base_url=request.url_root.rstrip("/"))

    @portal.post("/developer/join")
    def join():
        user = account()
        with database() as db:
            db.execute("UPDATE accounts SET developer_enabled=1 WHERE id=?", (user["id"],))
        return jsonify(ok=True, message="已加入开发者计划【beta】", redirect="/developer")

    @portal.get("/developer/keys")
    def list_keys():
        user = developer_account()
        with database() as db:
            rows = db.execute("SELECT id,name,prefix,created_at,last_used_at,revoked_at FROM user_keys WHERE account_id=? ORDER BY created_at DESC,id", (user["id"],)).fetchall()
        return jsonify(ok=True, keys=[dict(zip(("id", "name", "prefix", "created_at", "last_used_at", "revoked_at"), row)) for row in rows])

    @portal.post("/developer/keys")
    def create_key():
        user = developer_account()
        name = json_body().get("name", "默认 Key")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
            raise game.RuleError("Key 名称须为 1—40 个字符")
        name = name.strip()
        token = "ak_" + secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        key_id, now = secrets.token_hex(12), time.time()
        prefix = token[:11] + "…"
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM user_keys WHERE account_id=? AND revoked_at IS NULL", (user["id"],)).fetchone()[0]
            if count >= 5:
                raise game.RuleError("最多保留 5 个有效 User Key，请先吊销旧 Key")
            db.execute("INSERT INTO user_keys(id,account_id,name,key_hash,prefix,created_at) VALUES(?,?,?,?,?,?)",
                       (key_id, user["id"], name, digest, prefix, now))
        return jsonify(ok=True, key=dict(id=key_id, name=name, prefix=prefix, created_at=now, value=token),
                       message="完整 User Key 仅显示这一次，请复制保存"), 201

    @portal.post("/developer/keys/<key_id>/revoke")
    def revoke_key(key_id):
        user = developer_account()
        with database() as db:
            found = db.execute("SELECT id FROM user_keys WHERE id=? AND account_id=?", (key_id, user["id"])).fetchone()
            if not found:
                raise game.RuleError("未找到这个 User Key", 404)
            db.execute("UPDATE user_keys SET revoked_at=COALESCE(revoked_at,?) WHERE id=? AND account_id=?", (time.time(), key_id, user["id"]))
        return jsonify(ok=True, message="User Key 已吊销")

    @api.before_request
    def authenticate_key():
        direct = request.headers.get("X-User-Key", "").strip()
        authorization = request.headers.get("Authorization", "").strip()
        bearer = ""
        if authorization:
            parts = authorization.split()
            if len(parts) != 2 or parts[0].lower() != "bearer":
                raise game.RuleError("请使用 Authorization: Bearer <User Key>", 401)
            bearer = parts[1]
        if direct and bearer and not secrets.compare_digest(direct.encode("utf-8"), bearer.encode("utf-8")):
            raise game.RuleError("两个鉴权请求头中的 Key 不一致", 401)
        token = direct or bearer
        if not token or not token.startswith("ak_") or len(token) > 256:
            raise game.RuleError("缺少有效的 User Key，请在请求头中携带 X-User-Key", 401)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with database() as db:
            row = db.execute("""SELECT k.id,a.id,a.username,a.developer_enabled FROM user_keys k
                JOIN accounts a ON a.id=k.account_id WHERE k.key_hash=? AND k.revoked_at IS NULL""", (digest,)).fetchone()
            if row is None:
                raise game.RuleError("User Key 无效或已吊销", 401)
            if not row[3]:
                raise game.RuleError("该账号未加入开发者计划【beta】", 403)
            db.execute("UPDATE user_keys SET last_used_at=? WHERE id=?", (time.time(), row[0]))
        g.developer_user = dict(id=row[1], username=row[2])

    def run(action):
        user = g.developer_user
        p = read_player(user["id"])
        auto_count = game.settle_auto(p)
        result = action(p)
        write_player(user["id"], p)
        return jsonify(ok=True, data=result, state=game.public_state(p),
                       storage="signed-cookie", auto_catches=auto_count)

    @api.post("/fish/enablenet")
    def enable_net():
        return run(lambda p: game.set_net(p, True))

    @api.post("/fish/disablenet")
    def disable_net():
        return run(lambda p: game.set_net(p, False))

    @api.post("/fish")
    def fish():
        return run(game.manual_catch)

    @api.post("/diamond25")
    def diamond25():
        return run(lambda p: game.exchange(p, 25))

    @api.post("/diamond50")
    def diamond50():
        return run(lambda p: game.exchange(p, 50))

    @api.post("/diamonds")
    def diamonds():
        return run(lambda p: game.exchange(p, 100))

    @api.post("/uphufu")
    def uphufu():
        return run(lambda p: game.upgrade_gear(p, "charm"))

    @api.post("/upshengna")
    def upshengna():
        return run(lambda p: game.upgrade_gear(p, "sonar"))

    @api.post("/uptuowang")
    def uptuowang():
        return run(lambda p: game.upgrade_gear(p, "net"))

    @api.post("/upgrademain")
    def upgrademain():
        return run(lambda p: game.upgrade_player(p, "one"))

    @api.get("/getpays")
    def getpays():
        return run(lambda p: dict(gold=p["gold"], diamonds=str(p["diamonds"]), catches=p["catches"]))

    @api.get("/tujian")
    def tujian():
        def contents(p):
            entries = []
            for f in game.FISH:
                count = p["collection"].get(f["id"], 0)
                entries.append(dict(id=f["id"], name=f["name"], latin=f["latin"], rarity=f["rarity"],
                                    required_level=f["unlock"], available=p["level"] >= f["unlock"],
                                    unlocked=count > 0, caught=count,
                                    description=f["description"] if count else "尚未捕获，完整档案未解锁",
                                    length=f["length"] if count else "未知"))
            return dict(total=len(entries), unlocked=[f for f in entries if f["unlocked"]],
                        locked=[f for f in entries if not f["unlocked"]])
        return run(contents)

    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    portal.after_request(no_cache)
    api.after_request(no_cache)
    app.register_blueprint(portal)
    app.register_blueprint(api)
