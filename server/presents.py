"""Подарить подарок с открыткой: игроку напрямую или по ссылке любому человеку в Telegram.
Подарок по ссылке «замораживается» (owner = -(LINK_OWNER + id ссылки)), забрать можно один раз за 7 дней, иначе возврат.
Новичок, пришедший по ссылке-подарку, засчитывается приглашением отправителя."""
import asyncio
import secrets

from fastapi import Depends, Request

from app import (bot_name, R, app, auth, cancel_trades_with, db, err, esc, event, gift_out, in_open_trade, notify, now, own_gift,
                 q, q1, tx, unpin, user_brief)

LINK_OWNER = 3 * 10 ** 10    # выше диапазонов сейфа (2e9+uid) и залога (2e10+uid)
LINK_TTL = 7 * 86400
TEXT_MAX = 120

db.executescript("""
CREATE TABLE IF NOT EXISTS gift_links(id INTEGER PRIMARY KEY, code TEXT UNIQUE, gift INTEGER, sender INTEGER, text TEXT, ts INTEGER,
  status TEXT DEFAULT 'open', taker INTEGER, done INTEGER);
""")


def _check(gid, uid):
    import loans
    g = own_gift(gid, uid)
    if g["price"] is not None:
        err("сначала сними подарок с маркета")
    if in_open_trade(gid):
        err("подарок участвует в обмене")
    if loans.stars_locked(uid):
        err("пока не закрыт кредит без залога, дарить нельзя")
    return g


def _feed(uid, gid):
    db.execute("INSERT INTO feed(user,gift,cs,ts) VALUES(?,?,?,?)", (uid, gid, "present", now()))


@app.post(R + "/gift/{gid}/send")
async def send_gift(gid: int, req: Request, uid=Depends(auth)):
    """Подарить игроку."""
    b = await req.json()
    to, text = int(b.get("to", 0)), " ".join(str(b.get("text", "")).split())[:TEXT_MAX]
    with tx():
        g = _check(gid, uid)
        if to == uid or not q1("SELECT 1 FROM users WHERE id=?", to):
            err("кому дарим?")
        db.execute("UPDATE gifts SET owner=? WHERE id=?", (to, gid))
        event(uid, "present", 0)   # отметка «дарил» (для «Старта новичка»)
        unpin(uid, gid)
        cancel_trades_with(gid)
        _feed(to, gid)
        name = q1("SELECT name FROM users WHERE id=?", uid)["name"]
    notify(to, f"🎁 <b>{esc(name)}</b> подарил тебе <b>{esc(g['col'])}</b> «{esc(g['model'])}»" + (f"\n\n<i>«{esc(text)}»</i>" if text else ""))
    return {"ok": True}


@app.post(R + "/gift/{gid}/link")
async def link_gift(gid: int, req: Request, uid=Depends(auth)):
    """Подарок по ссылке: заморозить и выдать ссылку на бота."""
    text = " ".join(str((await req.json()).get("text", "")).split())[:TEXT_MAX]
    with tx():
        _check(gid, uid)
        if q1("SELECT COUNT(*) n FROM gift_links WHERE sender=? AND status='open'", uid)["n"] >= 5:
            err("не больше 5 неоткрытых подарков по ссылке")
        code = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
        cur = db.execute("INSERT INTO gift_links(code,gift,sender,text,ts) VALUES(?,?,?,?,?)", (code, gid, uid, text, now()))
        db.execute("UPDATE gifts SET owner=? WHERE id=?", (-(LINK_OWNER + cur.lastrowid), gid))
        unpin(uid, gid)
        cancel_trades_with(gid)
    return {"ok": True, "code": code, "link": f"https://t.me/{bot_name()}?start=gift_{code}"}


@app.get(R + "/giftlink/{code}")
def link_info(code: str, uid=Depends(auth)):
    lk = q1("SELECT * FROM gift_links WHERE code=?", code) or err("подарок не найден")
    g = q1("SELECT * FROM gifts WHERE id=?", lk["gift"])
    s = q1("SELECT * FROM users WHERE id=?", lk["sender"])
    return {"status": lk["status"], "text": lk["text"], "sender": user_brief(s) if s else None, "gift": gift_out(g) if g else None,
            "mine": lk["sender"] == uid, "taker": lk["taker"]}


@app.post(R + "/giftlink/{code}/claim")
def link_claim(code: str, uid=Depends(auth)):
    with tx():
        lk = q1("SELECT * FROM gift_links WHERE code=?", code) or err("подарок не найден")
        if lk["status"] != "open":
            err("этот подарок уже открыли" if lk["status"] == "taken" else "срок подарка истёк")
        if lk["sender"] == uid:
            err("это твой подарок — отправь ссылку другу")
        db.execute("UPDATE gifts SET owner=? WHERE id=?", (uid, lk["gift"]))
        db.execute("UPDATE gift_links SET status='taken', taker=?, done=? WHERE id=?", (uid, now(), lk["id"]))
        _feed(uid, lk["gift"])
        g = gift_out(q1("SELECT * FROM gifts WHERE id=?", lk["gift"]))
        name = q1("SELECT name FROM users WHERE id=?", uid)["name"]
    notify(lk["sender"], f"🎁 <b>{esc(name)}</b> открыл твой подарок {esc(g['col'])}!")
    return {"ok": True, "gift": g}


@app.get(R + "/giftlinks")
def my_links(uid=Depends(auth)):
    out = []
    for lk in q("SELECT * FROM gift_links WHERE sender=? ORDER BY id DESC LIMIT 20", uid):
        g = q1("SELECT * FROM gifts WHERE id=?", lk["gift"])
        out.append({"code": lk["code"], "status": lk["status"], "ts": lk["ts"], "gift": gift_out(g) if g else None,
                    "link": f"https://t.me/{bot_name()}?start=gift_{lk['code']}"})
    return {"links": out}


@app.post(R + "/giftlink/{code}/cancel")
def link_cancel(code: str, uid=Depends(auth)):
    with tx():
        lk = q1("SELECT * FROM gift_links WHERE code=? AND sender=?", code, uid) or err("подарок не найден")
        if lk["status"] != "open":
            err("подарок уже открыли")
        db.execute("UPDATE gifts SET owner=? WHERE id=?", (uid, lk["gift"]))
        db.execute("UPDATE gift_links SET status='cancelled', done=? WHERE id=?", (now(), lk["id"]))
    return {"ok": True}


def _expire():
    msgs = []
    with tx():
        for lk in q("SELECT * FROM gift_links WHERE status='open' AND ts<?", now() - LINK_TTL):
            db.execute("UPDATE gifts SET owner=? WHERE id=?", (lk["sender"], lk["gift"]))
            db.execute("UPDATE gift_links SET status='expired', done=? WHERE id=?", (now(), lk["id"]))
            msgs.append(lk["sender"])
    for u in msgs:
        notify(u, "🎁 Подарок по ссылке никто не открыл за 7 дней — он вернулся в твою сумку")


async def presents_loop():
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _expire)
        except Exception as e:
            print("presents:", e, flush=True)
        await asyncio.sleep(600)


@app.on_event("startup")
async def _presents_start():
    asyncio.create_task(presents_loop())
