"""Джекпот на подарки: общий банк из подарков и звёзд, колесо с секторами по вкладу, победитель забирает всё."""
import asyncio
import json
import random

from fastapi import Depends, Request

from app import R, app, auth, bal, db, err, esc, event, notify, now, q, q1, tx, user_brief, gift_out
from app import unpin, cancel_trades_with

db.executescript("""
CREATE TABLE IF NOT EXISTS jr_rounds(id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT, deadline REAL, spin_at REAL,
  winner INTEGER, ticket REAL, total INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS jr_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, round INTEGER, user INTEGER, gifts TEXT, stars INTEGER, value INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS jr_bets_round ON jr_bets(round);
""")
COUNTDOWN = 45      # после второго игрока — столько секунд на ставки
SPIN = 7            # длительность анимации колеса
MIN_BET = 100       # минимальный вклад (ценность)
FEE = 0.05          # комиссия только со звёзд банка
ESC = 10 ** 9       # подарки в банке: owner = -(ESC + id раунда)


def _cur():
    r = q1("SELECT * FROM jr_rounds WHERE status IN ('open','spinning') ORDER BY id DESC LIMIT 1")
    if r:
        return r
    with tx():
        r = q1("SELECT * FROM jr_rounds WHERE status IN ('open','spinning') ORDER BY id DESC LIMIT 1")
        if not r:
            db.execute("INSERT INTO jr_rounds(status, ts) VALUES('open', ?)", (now(),))
            r = q1("SELECT * FROM jr_rounds WHERE status='open' ORDER BY id DESC LIMIT 1")
    return r


def _bets(rid):
    """Вклады раунда, сгруппированные по игрокам, в порядке первого входа (так рисуются сектора)."""
    out = {}
    for b in q("SELECT * FROM jr_bets WHERE round=? ORDER BY id", rid):
        u = out.setdefault(b["user"], {"user": b["user"], "value": 0, "stars": 0, "gifts": []})
        u["value"] += b["value"]
        u["stars"] += b["stars"]
        u["gifts"] += json.loads(b["gifts"])
    return list(out.values())


def _settle(r):
    """Розыгрыш: выбираем билет 0..1, отдаём победителю все подарки и звёзды банка."""
    bets = _bets(r["id"])
    total = sum(b["value"] for b in bets)
    import fair
    rng = fair.pub("jroul", f"round:{r['id']}")
    ticket = rng.random()
    fair.close_pub(rng, {"ticket": round(ticket, 8), "total": total})
    acc, winner = 0.0, bets[-1]["user"]
    for b in bets:
        acc += b["value"] / total
        if ticket < acc:
            winner = b["user"]
            break
    stars = sum(b["stars"] for b in bets)
    pay_stars = int(stars * (1 - FEE))
    db.execute("UPDATE gifts SET owner=? WHERE owner=?", (winner, -(ESC + r["id"])))
    if pay_stars:
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay_stars, winner))
    for b in bets:
        won = (total - (stars - pay_stars)) if b["user"] == winner else 0
        event(b["user"], "jroul", won - b["value"], stake=b["value"])
    db.execute("UPDATE jr_rounds SET status='spinning', winner=?, ticket=?, total=?, spin_at=? WHERE id=?",
               (winner, ticket, total, now() + 0.0, r["id"]))
    return winner, total, bets


async def jr_loop():
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _tick)
        except Exception as e:
            print("jackpot-roulette:", e, flush=True)
        await asyncio.sleep(1)


def _tick():
    r = _cur()
    t = now()
    if r["status"] == "open":
        players = q1("SELECT COUNT(DISTINCT user) n FROM jr_bets WHERE round=?", r["id"])["n"]
        if players >= 2 and not r["deadline"]:
            with tx():
                db.execute("UPDATE jr_rounds SET deadline=? WHERE id=? AND deadline IS NULL", (t + COUNTDOWN, r["id"]))
        elif r["deadline"] and t >= r["deadline"]:
            with tx():
                r = q1("SELECT * FROM jr_rounds WHERE id=?", r["id"])
                if r["status"] != "open":
                    return
                winner, total, bets = _settle(r)
            name = q1("SELECT name FROM users WHERE id=?", winner)["name"]
            for b in bets:
                if b["user"] == winner:
                    notify(winner, f"🎰 Ты сорвал джекпот на <b>{total} ⭐</b> — все подарки банка твои!")
    elif r["status"] == "spinning" and t >= (r["spin_at"] or t) + SPIN + 4:
        with tx():
            db.execute("UPDATE jr_rounds SET status='done' WHERE id=?", (r["id"],))
            db.execute("INSERT INTO jr_rounds(status, ts) VALUES('open', ?)", (t,))


@app.on_event("startup")
async def _jr_start():
    asyncio.create_task(jr_loop())


def _round_view(r, uid):
    bets = _bets(r["id"])
    total = sum(b["value"] for b in bets) or 0
    users = []
    for b in bets:
        u = q1("SELECT * FROM users WHERE id=?", b["user"])
        gs = [gift_out(x) for x in (q1("SELECT * FROM gifts WHERE id=?", g) for g in b["gifts"]) if x]
        users.append({**user_brief(u), "value": b["value"], "stars": b["stars"], "gifts": gs,
                      "chance": round(b["value"] / total * 100, 2) if total else 0})
    return {"id": r["id"], "status": r["status"], "deadline": r["deadline"], "spinAt": r["spin_at"], "now": now(),
            "total": total, "players": users, "winner": r["winner"] if r["status"] != "open" else None,
            "ticket": r["ticket"] if r["status"] != "open" else None, "spin": SPIN, "min": MIN_BET}


@app.get(R + "/jroul")
def jr_get(uid=Depends(auth)):
    r = _cur()
    hist = []
    for h in q("SELECT * FROM jr_rounds WHERE status='done' AND winner IS NOT NULL ORDER BY id DESC LIMIT 8"):
        u = q1("SELECT * FROM users WHERE id=?", h["winner"])
        me_val = q1("SELECT COALESCE(SUM(value),0) v FROM jr_bets WHERE round=? AND user=?", h["id"], h["winner"])["v"]
        hist.append({**user_brief(u), "total": h["total"], "chance": round(me_val / h["total"] * 100, 1) if h["total"] else 0})
    return {**_round_view(r, uid), "history": hist}


@app.post(R + "/jroul/bet")
async def jr_bet(req: Request, uid=Depends(auth)):
    from app import _pvp_guard
    _pvp_guard(uid)
    b = await req.json()
    gids = list(dict.fromkeys(int(x) for x in b.get("gifts", [])))[:10]
    stars = max(0, int(b.get("stars", 0)))
    rid = _cur()["id"]
    with tx():
        r = q1("SELECT * FROM jr_rounds WHERE id=?", rid)
        if r["status"] != "open" or (r["deadline"] and now() > r["deadline"] - 1):
            err("ставки закрыты — дождись следующего раунда")
        value = stars
        for g in gids:
            x = q1("SELECT * FROM gifts WHERE id=?", g)
            if not x or x["owner"] != uid:
                err("это не твой подарок")
            if x["price"] is not None:
                err("сначала сними подарок с маркета")
            value += x["value"]
        if value < MIN_BET:
            err(f"минимальный вклад — {MIN_BET} ⭐")
        if stars and bal(uid) < stars:
            err("Не хватает звёзд")
        if stars:
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (stars, uid))
        for g in gids:
            db.execute("UPDATE gifts SET owner=? WHERE id=?", (-(ESC + r["id"]), g))
            unpin(uid, g)
            cancel_trades_with(g)
        db.execute("INSERT INTO jr_bets(round,user,gifts,stars,value,ts) VALUES(?,?,?,?,?,?)",
                   (r["id"], uid, json.dumps(gids), stars, value, now()))
        r = q1("SELECT * FROM jr_rounds WHERE id=?", r["id"])
    return {**_round_view(r, uid), "stars": bal(uid)}
