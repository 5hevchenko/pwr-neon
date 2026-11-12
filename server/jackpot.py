"""Розыгрыш банка: раз в сутки часть прибыли казино + купленные билеты разыгрываются между игроками."""
from settings import conf
import asyncio
import json
import random

from fastapi import Depends, Request

import app as A
from app import R, app, auth, bal, db, err, esc, event, notify, now, q, q1, tx, user_brief, day_start, GAME_KINDS, BANK_START

db.executescript("""
CREATE TABLE IF NOT EXISTS jp_tickets(day INTEGER, user INTEGER, bought INTEGER DEFAULT 0, PRIMARY KEY(day, user));
CREATE TABLE IF NOT EXISTS jp_draws(day INTEGER PRIMARY KEY, pool INTEGER, winners TEXT, ts INTEGER);
""")
TICKET = conf("jackpot.ticket", 100)            # цена билета
ROUNDS_PER_FREE = 10    # бесплатный билет за каждые N сыгранных раундов
FREE_CAP = conf("jackpot.free_cap", 50)
HOUSE_SHARE = conf("jackpot.house_share", 0.10)      # доля дневной прибыли казино, уходящая в фонд
MIN_POOL = 10_000
SPLIT = conf("jackpot.split", [0.60, 0.25, 0.15])


def _tickets(day):
    """{user: билетов} за день: бесплатные за раунды + купленные."""
    t = {}
    for r in q(f"SELECT user, COUNT(*) n FROM events WHERE kind IN {GAME_KINDS} AND ts>=? AND ts<? GROUP BY user", day, day + 86400):
        t[r["user"]] = min(FREE_CAP, r["n"] // ROUNDS_PER_FREE)
    for r in q("SELECT user, bought FROM jp_tickets WHERE day=?", day):
        t[r["user"]] = t.get(r["user"], 0) + r["bought"]
    return {u: n for u, n in t.items() if n > 0}


def _pool(day):
    house = -q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind IN {GAME_KINDS} AND ts>=? AND ts<?", day, day + 86400)["s"]
    bought = q1("SELECT COALESCE(SUM(bought),0) s FROM jp_tickets WHERE day=?", day)["s"]
    return max(MIN_POOL, int(house * HOUSE_SHARE)) + bought * TICKET


def _draw(day):
    """Разыграть фонд за день (идемпотентно)."""
    with tx():
        if q1("SELECT 1 FROM jp_draws WHERE day=?", day):
            return None
        t, pool = _tickets(day), _pool(day)
        import fair
        _rng = fair.pub("jackpot", str(now() // 86400))
        winners, left = [], dict(t)
        for share in SPLIT:
            if not left:
                break
            users = list(left)
            u = _rng.choices(users, weights=[left[x] for x in users])[0]
            left.pop(u)
            amount = int(pool * share)
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, u))
            event(u, "jackpot", amount)
            winners.append({"user": u, "amount": amount, "tickets": t[u]})
        db.execute("INSERT INTO jp_draws VALUES(?,?,?,?)", (day, pool, json.dumps(winners), now()))
    for i, w in enumerate(winners):
        notify(w["user"], f"🎉 Ты выиграл <b>{i + 1} место</b> в розыгрыше банка — +{w['amount']} ⭐ (игровых)!")
    return winners


async def jackpot_loop():
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _draw, day_start() - 86400)
        except Exception as e:
            print("jackpot:", e, flush=True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _jp_start():
    asyncio.create_task(jackpot_loop())


@app.get(R + "/jackpot")
def jackpot(uid=Depends(auth)):
    d = day_start()
    t = _tickets(d)
    rounds = q1(f"SELECT COUNT(*) n FROM events WHERE kind IN {GAME_KINDS} AND ts>=? AND user=?", d, uid)["n"]
    last = q1("SELECT * FROM jp_draws ORDER BY day DESC LIMIT 1")
    lw = []
    if last:
        for w in json.loads(last["winners"]):
            u = q1("SELECT * FROM users WHERE id=?", w["user"])
            if u:
                lw.append({**user_brief(u), "amount": w["amount"], "tickets": w["tickets"]})
    mine, total = t.get(uid, 0), sum(t.values())
    return {"pool": _pool(d), "mine": mine, "total": total, "players": len(t), "endsIn": d + 86400 - now(),
            "chance": round(mine / total * 100, 2) if total else 0, "ticket": TICKET, "split": SPLIT,
            "nextFree": ROUNDS_PER_FREE - rounds % ROUNDS_PER_FREE if rounds // ROUNDS_PER_FREE < FREE_CAP else None,
            "freeCap": FREE_CAP, "last": {"pool": last["pool"], "winners": lw} if last else None}


@app.post(R + "/jackpot/buy")
async def jackpot_buy(req: Request, uid=Depends(auth)):
    n = max(1, min(100, int((await req.json()).get("n", 1))))
    if A.SELF_GUARD:
        A.SELF_GUARD(uid, n * TICKET)
    d = day_start()
    with tx():
        if bal(uid) < n * TICKET:
            err("Не хватает звёзд")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (n * TICKET, uid))
        db.execute("INSERT INTO jp_tickets(day,user,bought) VALUES(?,?,?) ON CONFLICT(day,user) DO UPDATE SET bought=bought+?", (d, uid, n, n))
        event(uid, "ticket", -n * TICKET)
    return {"ok": True, "stars": bal(uid)}
