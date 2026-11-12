"""«Пенальти» — серия ударов по воротам. В воротах 5 зон; перед каждым ударом вратарь (сервер) закрывает случайные
1, 2 или 3 зоны — по сложности. Попал в открытую — гол, множитель растёт; в закрытую — сейв, ставка сгорает.
Куда бьёт игрок, на шанс не влияет: P(гол) = (5 − закрыто) / 5 всегда. Множитель после n голов = RTP / P^n
(games.penalty_rtp, вкладка «Шансы»). Забрать можно после любого гола, после 10-го — выплата автоматически."""
import math
import secrets

from fastapi import Depends, Request

from app import R, add_xp, app, auth, bal, check_bet, db, edge, err, event, now, q1, tx
from settings import conf, tuned

db.executescript("""
CREATE TABLE IF NOT EXISTS penalty(user INTEGER PRIMARY KEY, bet INTEGER, mode TEXT, step INTEGER DEFAULT 0, ts INTEGER);
""")
RTP = conf("games.penalty_rtp", 0.96)
ZONES = 5          # 0 — верх-лево, 1 — верх-право, 2 — центр, 3 — низ-лево, 4 — низ-право
KICKS = 10
MODES = {"easy": 1, "mid": 2, "hard": 3}   # сколько зон закрывает вратарь
MAX_MULT = 5000
RND = secrets.SystemRandom()


def p_goal(mode):
    return (ZONES - MODES[mode]) / ZONES


def mult(mode, n):
    if not n:
        return 1.0
    return math.floor(min(MAX_MULT, edge(tuned("games.penalty_rtp", RTP)) / p_goal(mode) ** n) * 100) / 100


def table(mode):
    return [mult(mode, n) for n in range(1, KICKS + 1)]


def state(r):
    n = r["step"]
    return {"active": True, "bet": r["bet"], "mode": r["mode"], "step": n, "mult": mult(r["mode"], n),
            "next": mult(r["mode"], n + 1) if n < KICKS else None, "table": table(r["mode"])}


@app.get(R + "/penalty")
def penalty(uid=Depends(auth)):
    r = q1("SELECT * FROM penalty WHERE user=?", uid)
    return {**(state(r) if r else {"active": False}), "kicks": KICKS, "modes": {m: table(m) for m in MODES},
            "chance": {m: round(p_goal(m) * 100) for m in MODES}, "rtp": round(edge(tuned("games.penalty_rtp", RTP)) * 100, 1)}


@app.post(R + "/penalty/start")
async def penalty_start(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, mode = int(b.get("bet", 0)), str(b.get("mode", "mid"))
    if mode not in MODES:
        err("нет такой сложности")
    with tx():
        if q1("SELECT 1 FROM penalty WHERE user=?", uid):
            err("серия уже идёт")
        check_bet(uid, bet)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        db.execute("INSERT INTO penalty(user,bet,mode,step,ts) VALUES(?,?,?,0,?)", (uid, bet, mode, now()))
        lvl = add_xp(uid, max(1, bet // 20))
        r = q1("SELECT * FROM penalty WHERE user=?", uid)
    return {**state(r), "stars": bal(uid), "levelup": lvl}


def _cash(uid, r):
    pay = int(r["bet"] * mult(r["mode"], r["step"]))
    db.execute("DELETE FROM penalty WHERE user=?", (uid,))
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
    event(uid, "penalty", pay - r["bet"], stake=r["bet"])
    return {**state(r), "active": False, "pay": pay, "stars": bal(uid)}


@app.post(R + "/penalty/kick")
async def penalty_kick(req: Request, uid=Depends(auth)):
    b = await req.json()
    try:
        zone = int(b.get("zone", -1))
    except (TypeError, ValueError):
        zone = -1
    if not 0 <= zone < ZONES:
        err("выбери, куда бить")
    import fair
    with tx():
        r = q1("SELECT * FROM penalty WHERE user=?", uid) or err("серия не начата")
        mc = MODES[r["mode"]]
        rr, pf = fair.rolls(uid, "penalty", ref=f"{r['mode']}:{r['step']}", n=mc + 1)
        cover = sorted(fair.sample(rr[:mc], range(ZONES), mc))
        # куда прыгнул вратарь (для анимации): в зону удара, если угадал, иначе в одну из своих
        dive = zone if zone in cover else cover[fair.idx(rr[mc], len(cover))]
        fair.record(uid, "penalty", 0, 0, {"cover": cover, "zone": zone, "goal": zone not in cover}, pf)
        if zone in cover:   # сейв
            db.execute("DELETE FROM penalty WHERE user=?", (uid,))
            event(uid, "penalty", -r["bet"], stake=r["bet"])
            return {**state(r), "active": False, "goal": False, "zone": zone, "cover": cover, "dive": dive, "stars": bal(uid), "pf": pf}
        db.execute("UPDATE penalty SET step=step+1 WHERE user=?", (uid,))
        r = q1("SELECT * FROM penalty WHERE user=?", uid)
        if r["step"] >= KICKS:   # забил все 10 — выплата сама
            return {**_cash(uid, r), "goal": True, "zone": zone, "cover": cover, "dive": dive, "auto": True, "pf": pf}
        return {**state(r), "goal": True, "zone": zone, "cover": cover, "dive": dive, "pf": pf}


@app.post(R + "/penalty/cashout")
def penalty_cashout(uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM penalty WHERE user=?", uid) or err("серия не начата")
        if not r["step"]:
            err("забей хотя бы один")
        return _cash(uid, r)
