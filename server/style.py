"""Оформление профиля: акцентный цвет, статус, значки, узор обложки (бесплатно)
и магазин за игровые звёзды — рамки аватара и эффекты ника на 30 дней (повторная покупка продлевает срок).
Надетая рамка/ник копируются в users (p_frame/p_frame_until, p_nick/p_nick_until), чтобы user_brief не делал лишних запросов."""
import json
import re

from fastapi import Depends, Request

import app as A
from app import R, app, auth, db, err, event, now, q, q1, tx

DAYS = 30
# id → (вид, название, цена в игровых ⭐ за 30 дней)
ITEMS = {
    "neon":    ("frame", "Неон", 40_000),
    "ice":     ("frame", "Лёд", 75_000),
    "fire":    ("frame", "Пламя", 75_000),
    "toxic":   ("frame", "Токсик", 120_000),
    "rainbow": ("frame", "Радуга", 150_000),
    "diamond": ("frame", "Бриллиант", 300_000),
    "n-gold":    ("nick", "Золотой ник", 50_000),
    "n-neon":    ("nick", "Неоновый ник", 80_000),
    "n-fire":    ("nick", "Огненный ник", 120_000),
    "n-rainbow": ("nick", "Радужный ник", 200_000),
}
ACCENTS = ["", "#ff5a6e", "#ff8a3d", "#ffc93d", "#4fd67a", "#2bd4c4", "#3fa8ff", "#7d6cff", "#c86bff", "#ff6fb5", "#e6e9f0"]
STATUS_MAX = 40

db.executescript("""
CREATE TABLE IF NOT EXISTS cosm(user INTEGER, item TEXT, until INTEGER, PRIMARY KEY(user, item));
""")
for _c in ("p_accent TEXT DEFAULT ''", "p_status TEXT DEFAULT ''", "p_badges TEXT DEFAULT '[]'", "p_cover INTEGER DEFAULT 0",
           "p_frame TEXT DEFAULT ''", "p_frame_until INTEGER DEFAULT 0", "p_nick TEXT DEFAULT ''", "p_nick_until INTEGER DEFAULT 0"):
    try:
        db.execute(f"ALTER TABLE users ADD COLUMN {_c}")
    except Exception:
        pass


def brief(r):
    """Добавка к user_brief: всё, что видно в списках и на аватаре."""
    k, t = r.keys(), now()
    out = {}
    if "p_status" in k and r["p_status"]:
        out["status"] = r["p_status"]
    if "p_accent" in k and r["p_accent"]:
        out["accent"] = r["p_accent"]
    if "p_nick" in k and r["p_nick"] and (r["p_nick_until"] or 0) > t:
        out["nick"] = r["p_nick"][2:]
    elif "vip_until" in k and (r["vip_until"] or 0) > t:
        out["nick"] = "gold"            # VIP — золотой ник бесплатно
    if "p_frame" in k and r["p_frame"] and (r["p_frame_until"] or 0) > t:
        out["pframe"] = r["p_frame"]
    return out


A.STYLE_BRIEF = brief


def price_for(uid, price):
    """Цена с клановой скидкой (уровень 7+ — 10%, 10 — 20%)."""
    import clans
    return int(round(price * (1 - clans.style_discount(uid)) / 100) * 100)


def owned(uid):
    return {r["item"]: r["until"] for r in q("SELECT item, until FROM cosm WHERE user=? AND until>?", uid, now())}


def my_badges(uid):
    u = q1("SELECT * FROM users WHERE id=?", uid)
    gifts = [A.gift_out(r) for r in q("SELECT * FROM gifts WHERE owner=?", uid)]
    fr = q1("SELECT COUNT(*) n FROM friends WHERE (a=? OR b=?) AND status='ok'", uid, uid)["n"]
    return {a["t"] for a in A.achievements(u, gifts, fr, A.net_worth(uid)) if a["got"]}


@app.get(R + "/style")
def style_get(uid=Depends(auth)):
    u = q1("SELECT * FROM users WHERE id=?", uid)
    import clans
    return {"items": [{"id": i, "kind": k, "name": n, "price": price_for(uid, p), "full": p} for i, (k, n, p) in ITEMS.items()], "days": DAYS,
            "discount": round(clans.style_discount(uid) * 100),
            "owned": owned(uid), "accents": ACCENTS, "statusMax": STATUS_MAX, "vip": A.is_vip(u),
            "cur": {"accent": u["p_accent"], "status": u["p_status"], "badges": json.loads(u["p_badges"] or "[]"), "cover": u["p_cover"],
                    "frame": u["p_frame"], "nick": u["p_nick"]}}


@app.post(R + "/style")
async def style_set(req: Request, uid=Depends(auth)):
    b = await req.json()
    accent = str(b.get("accent", ""))
    if accent not in ACCENTS:
        err("нет такого цвета")
    status = re.sub(r"\s+", " ", str(b.get("status", ""))).strip()[:STATUS_MAX]
    badges = [str(x) for x in (b.get("badges") or [])][:3]
    cover = int(b.get("cover") or 0)
    frame, nick = str(b.get("frame") or ""), str(b.get("nick") or "")
    with tx():
        got = my_badges(uid)
        badges = [x for x in dict.fromkeys(badges) if x in got]
        if cover and not q1("SELECT 1 FROM gifts WHERE id=? AND owner=?", cover, uid):
            cover = 0
        own = owned(uid)
        if frame and (ITEMS.get(frame, ("",))[0] != "frame" or frame not in own):
            err("эта рамка не куплена")
        if nick and (ITEMS.get(nick, ("",))[0] != "nick" or nick not in own):
            err("этот ник не куплен")
        db.execute("UPDATE users SET p_accent=?, p_status=?, p_badges=?, p_cover=?, p_frame=?, p_frame_until=?, p_nick=?, p_nick_until=? WHERE id=?",
                   (accent, status, json.dumps(badges, ensure_ascii=False), cover, frame, own.get(frame, 0), nick, own.get(nick, 0), uid))
    return {"ok": True}


@app.post(R + "/style/buy/{item}")
def style_buy(item: str, uid=Depends(auth)):
    if item not in ITEMS:
        err("нет такого товара")
    kind, name, price = ITEMS[item]
    with tx():
        price = price_for(uid, price)
        u = q1("SELECT stars, p_frame, p_nick FROM users WHERE id=?", uid)
        if u["stars"] < price:
            err(f"Не хватает звёзд — нужно ⭐ {price}")
        t = now()
        cur = q1("SELECT until FROM cosm WHERE user=? AND item=?", uid, item)
        until = max(t, cur["until"] if cur else 0) + DAYS * 86400
        db.execute("INSERT INTO cosm(user,item,until) VALUES(?,?,?) ON CONFLICT(user,item) DO UPDATE SET until=excluded.until", (uid, item, until))
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (price, uid))
        event(uid, "style", -price)
        col = "p_frame" if kind == "frame" else "p_nick"   # покупка сразу надевает
        db.execute(f"UPDATE users SET {col}=?, {col}_until=? WHERE id=?", (item, until, uid))
        stars = q1("SELECT stars FROM users WHERE id=?", uid)["stars"]
    return {"ok": True, "until": until, "stars": stars}
