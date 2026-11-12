"""«Звездопад»: общая шкала на 60 000 ⭐. Игроки вкладывают звёзды; когда шкала заполнена, один из участников
(шанс = доля вклада) получает дорогой подарок ценностью 50–65 тыс. ⭐. Средний приз ~57 тыс. → банку остаётся ~5%."""
import random

from fastapi import Depends, Request

import economy as E
import app as A
from app import (R, app, auth, bal, db, err, esc, event, add_xp, gift_out, notify, now, q, q1, tx, upg_all, user_brief)

db.executescript("""
CREATE TABLE IF NOT EXISTS sf_rounds(id INTEGER PRIMARY KEY, target INTEGER, filled INTEGER DEFAULT 0, status TEXT DEFAULT 'open',
  winner INTEGER, gift INTEGER, ts INTEGER, done INTEGER);
CREATE TABLE IF NOT EXISTS sf_bets(id INTEGER PRIMARY KEY, round INTEGER, user INTEGER, amount INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS sf_bets_round ON sf_bets(round, user);
""")
TARGET = 60_000
PRIZE_MIN, PRIZE_MAX = 50_000, 65_000
MIN_BET = 50
USER_CAP = 20_000          # не больше трети шкалы в одни руки


def prizes():
    return [t for t in upg_all() if PRIZE_MIN <= t[3] <= PRIZE_MAX]


def _cur():
    r = q1("SELECT * FROM sf_rounds WHERE status='open' ORDER BY id DESC LIMIT 1")
    if not r:
        db.execute("INSERT INTO sf_rounds(target,ts) VALUES(?,?)", (TARGET, now()))
        r = q1("SELECT * FROM sf_rounds WHERE status='open' ORDER BY id DESC LIMIT 1")
    return r


def _stakes(rid):
    return {r["user"]: r["s"] for r in q("SELECT user, SUM(amount) s FROM sf_bets WHERE round=? GROUP BY user", rid)}


def _draw(r):
    """Шкала полна: выбираем победителя по доле вклада и создаём подарок."""
    st = _stakes(r["id"])
    users, w = list(st), list(st.values())
    import fair
    rng = fair.pub("starfall", str(r["id"]))
    win = rng.choices(users, weights=w)[0]
    col, model, pm, value = rng.choice(prizes())
    d = E.CATALOG[col]
    bd = rng.choices(d["backdrops"], weights=[x[1] for x in d["backdrops"]])[0][0]
    sy = rng.choices(d["symbols"], weights=[max(x[1], .1) for x in d["symbols"]])[0][0]
    cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                     (win, col, model, bd, sy, rng.randint(1, E.supply(col)), value, now()))
    fair.close_pub(rng, {"col": col, "value": value})
    db.execute("UPDATE sf_rounds SET status='done', winner=?, gift=?, done=? WHERE id=?", (win, cur.lastrowid, now(), r["id"]))
    event(win, "starfall", value)
    db.execute("INSERT INTO feed(user,gift,cs,ts) VALUES(?,?,?,?)", (win, cur.lastrowid, "starfall", now()))
    return win, col, value, st


def _round_out(r, uid):
    st = _stakes(r["id"])
    top = sorted(st.items(), key=lambda x: -x[1])[:10]
    rows = []
    for u, s in top:
        ur = q1("SELECT * FROM users WHERE id=?", u)
        if ur:
            rows.append({**user_brief(ur), "amount": s, "chance": round(s / max(1, r["filled"]) * 100, 1)})
    mine = st.get(uid, 0)
    return {"id": r["id"], "target": r["target"], "filled": r["filled"], "players": len(st), "mine": mine,
            "chance": round(mine / max(1, r["filled"]) * 100, 1), "top": rows}


@app.get(R + "/starfall")
def starfall(uid=Depends(auth)):
    with tx():
        r = _cur()
    last = []
    for x in q("SELECT * FROM sf_rounds WHERE status='done' ORDER BY id DESC LIMIT 6"):
        u, g = q1("SELECT * FROM users WHERE id=?", x["winner"]), q1("SELECT * FROM gifts WHERE id=?", x["gift"])
        if u:
            last.append({"id": x["id"], "user": user_brief(u), "gift": gift_out(g) if g else None, "ts": x["done"]})
    shown = random.sample(prizes(), min(8, len(prizes())))
    return {**_round_out(r, uid), "last": last, "min": MIN_BET, "cap": USER_CAP, "prizeMin": PRIZE_MIN, "prizeMax": PRIZE_MAX,
            "prizes": [{"col": c, "model": m, "value": v} for c, m, _, v in shown], "stars": bal(uid)}


@app.post(R + "/starfall/bet")
async def starfall_bet(req: Request, uid=Depends(auth)):
    amount = int((await req.json()).get("amount", 0))
    if amount < MIN_BET:
        err(f"минимум ⭐ {MIN_BET}")
    if A.SELF_GUARD:
        A.SELF_GUARD(uid, amount)
    won = None
    with tx():
        r = _cur()
        mine = q1("SELECT COALESCE(SUM(amount),0) s FROM sf_bets WHERE round=? AND user=?", r["id"], uid)["s"]
        amount = min(amount, r["target"] - r["filled"], USER_CAP - mine)
        if amount <= 0:
            err(f"в одном раунде можно вложить не больше ⭐ {USER_CAP}")
        if bal(uid) < amount:
            err("Не хватает звёзд")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        db.execute("INSERT INTO sf_bets(round,user,amount,ts) VALUES(?,?,?,?)", (r["id"], uid, amount, now()))
        db.execute("UPDATE sf_rounds SET filled=filled+? WHERE id=?", (amount, r["id"]))
        event(uid, "starfall", -amount)
        lvl = add_xp(uid, max(1, amount // 20))
        r = q1("SELECT * FROM sf_rounds WHERE id=?", r["id"])
        if r["filled"] >= r["target"]:
            won = _draw(r)
            result = {"done": True, "winner": won[0], "round": r["id"]}
            _cur()
        else:
            result = {"done": False}
    if won:
        win, col, value, st = won
        name = q1("SELECT name FROM users WHERE id=?", win)["name"]
        for u in st:
            notify(u, f"🌠 <b>Звездопад!</b> Шкала заполнена — <b>{esc(name)}</b> забирает {esc(col)} ценностью ⭐ {value}"
                      + (" — это ты! Подарок уже в сумке." if u == win else ". Новый раунд уже начался."))
    return {**result, "added": amount, "stars": bal(uid), "levelup": lvl}
