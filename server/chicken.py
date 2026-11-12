"""«Курица» (Chicken Road): курица перебегает дорогу полоса за полосой. Каждая полоса — шанс попасть под машину
по сложности; множитель растёт с каждым шагом, забрать можно в любой момент. Возврат игроку — EDGE (в акцию 99%)."""
from settings import conf, tuned
import json

from fastapi import Depends, Request

from app import R, app, auth, bal, check_bet, db, edge, err, event, add_xp, now, q1, tx

db.executescript("""
CREATE TABLE IF NOT EXISTS chicken(user INTEGER PRIMARY KEY, bet INTEGER, mode TEXT, step INTEGER DEFAULT 0, ts INTEGER);
""")
LANES = 20
EDGE = conf("games.chicken_edge", 0.96)
MODES = {"easy": 1 / 25, "mid": 3 / 25, "hard": 5 / 25, "hell": 10 / 25}   # шанс попасть под машину на каждой полосе
MAX_MULT = 10000
# риск нарастает по полосам: первые безопаснее (×0,4 от базового), к 7-й — как базовый, дальше до ×1,5
RAMP = [min(1.5, 0.4 + 0.1 * i) for i in range(LANES)]


def risk(mode, i):
    """Шанс, что собьют на полосе i (с нуля)."""
    return MODES[mode] * RAMP[i]


def mult(mode, k):
    """Множитель после k пройденных полос: каждая полоса честно оплачивает свой риск, преимущество казино — EDGE."""
    if not k:
        return 1.0
    m = edge(tuned("games.chicken_edge", EDGE))
    for i in range(k):
        m /= 1 - risk(mode, i)
    # на первых полосах «Лёгкого» честный множитель < 1 — выглядит как минус; минимум +1% за полосу (возврат всё равно < 100%)
    return min(MAX_MULT, max(m, 1 + 0.01 * k))


def table(mode):
    return [round(mult(mode, k), 2) for k in range(1, LANES + 1)]


def state(r):
    k = r["step"]
    return {"active": True, "bet": r["bet"], "mode": r["mode"], "step": k, "mult": round(mult(r["mode"], k), 2),
            "next": round(mult(r["mode"], k + 1), 2) if k < LANES else None, "table": table(r["mode"])}


@app.get(R + "/chicken")
def chicken(uid=Depends(auth)):
    r = q1("SELECT * FROM chicken WHERE user=?", uid)
    return {**(state(r) if r else {"active": False}), "lanes": LANES, "modes": {m: table(m) for m in MODES},
            "risk": {m: round(p * 100) for m, p in MODES.items()},
            "riskFrom": {m: round(risk(m, 0) * 100, 1) for m in MODES}, "riskTo": {m: round(risk(m, LANES - 1) * 100) for m in MODES}}


@app.post(R + "/chicken/start")
async def chicken_start(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, mode = int(b.get("bet", 0)), str(b.get("mode", "mid"))
    if mode not in MODES:
        err("нет такой сложности")
    with tx():
        if q1("SELECT 1 FROM chicken WHERE user=?", uid):
            err("курица уже на дороге")
        check_bet(uid, bet)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        db.execute("INSERT INTO chicken(user,bet,mode,step,ts) VALUES(?,?,?,0,?)", (uid, bet, mode, now()))
        lvl = add_xp(uid, max(1, bet // 20))
        r = q1("SELECT * FROM chicken WHERE user=?", uid)
    return {**state(r), "stars": bal(uid), "levelup": lvl}


def _cash(uid, r):
    pay = int(r["bet"] * mult(r["mode"], r["step"]))
    db.execute("DELETE FROM chicken WHERE user=?", (uid,))
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
    event(uid, "chicken", pay - r["bet"], stake=r["bet"])
    return {**state(r), "active": False, "pay": pay, "stars": bal(uid)}


@app.post(R + "/chicken/step")
def chicken_step(uid=Depends(auth)):
    import fair
    with tx():
        r = q1("SELECT * FROM chicken WHERE user=?", uid) or err("игра не начата")
        rr, pf = fair.rolls(uid, "chicken", ref=f"{r['mode']}:{r['step']}")
        fair.record(uid, "chicken", 0, 0, {"p": round(risk(r["mode"], r["step"]), 6), "hit": rr[0] < risk(r["mode"], r["step"])}, pf)
        if rr[0] < risk(r["mode"], r["step"]):   # сбили
            db.execute("DELETE FROM chicken WHERE user=?", (uid,))
            event(uid, "chicken", -r["bet"], stake=r["bet"])
            return {**state(r), "active": False, "dead": r["step"] + 1, "stars": bal(uid), "pf": pf}
        db.execute("UPDATE chicken SET step=step+1 WHERE user=?", (uid,))
        r = q1("SELECT * FROM chicken WHERE user=?", uid)
        if r["step"] >= LANES:   # перешла всю дорогу — выплата автоматически
            return {**_cash(uid, r), "pf": pf}
        return {**state(r), "pf": pf}


@app.post(R + "/chicken/cashout")
def chicken_cashout(uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM chicken WHERE user=?", uid) or err("игра не начата")
        if not r["step"]:
            err("сделай хотя бы один шаг")
        return _cash(uid, r)
