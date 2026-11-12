"""«Насос» — надувай шар-звезду. Каждый качок увеличивает множитель, но шар может лопнуть; забрать можно в любой момент.
Шанс лопнуть растёт с каждым качком (шар туже), по сложности. Множитель после k качков честно оплачивает риск,
возврат игроку — RTP (games.pump_rtp, меняется во вкладке «Шансы», в акцию — не ниже 98%)."""
from fastapi import Depends, Request

from app import R, add_xp, app, auth, bal, check_bet, db, edge, err, event, now, q1, tx
from settings import conf, tuned

db.executescript("""
CREATE TABLE IF NOT EXISTS pump(user INTEGER PRIMARY KEY, bet INTEGER, mode TEXT, step INTEGER DEFAULT 0, ts INTEGER);
""")
RTP = conf("games.pump_rtp", 0.96)
STEPS = 16
# (шанс лопнуть на первом качке, прибавка за каждый следующий)
MODES = {"easy": (0.035, 0.012), "mid": (0.08, 0.02), "hard": (0.16, 0.03)}
MAX_MULT = 10000


def risk(mode, i):
    a, g = MODES[mode]
    return min(0.9, a + g * i)


def mult(mode, k):
    if not k:
        return 1.0
    m = edge(tuned("games.pump_rtp", RTP))
    for i in range(k):
        m /= 1 - risk(mode, i)
    return min(MAX_MULT, max(m, 1 + 0.01 * k))


def table(mode):
    return [round(mult(mode, k), 2) for k in range(1, STEPS + 1)]


def state(r):
    k = r["step"]
    return {"active": True, "bet": r["bet"], "mode": r["mode"], "step": k, "mult": round(mult(r["mode"], k), 2),
            "next": round(mult(r["mode"], k + 1), 2) if k < STEPS else None, "risk": round(risk(r["mode"], k) * 100, 1),
            "table": table(r["mode"])}


@app.get(R + "/pump")
def pump(uid=Depends(auth)):
    r = q1("SELECT * FROM pump WHERE user=?", uid)
    return {**(state(r) if r else {"active": False}), "steps": STEPS, "modes": {m: table(m) for m in MODES},
            "riskFrom": {m: round(risk(m, 0) * 100, 1) for m in MODES}, "riskTo": {m: round(risk(m, STEPS - 1) * 100) for m in MODES},
            "rtp": round(edge(tuned("games.pump_rtp", RTP)) * 100, 1)}


@app.post(R + "/pump/start")
async def pump_start(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, mode = int(b.get("bet", 0)), str(b.get("mode", "mid"))
    if mode not in MODES:
        err("нет такой сложности")
    with tx():
        if q1("SELECT 1 FROM pump WHERE user=?", uid):
            err("шар уже надувается")
        check_bet(uid, bet)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        db.execute("INSERT INTO pump(user,bet,mode,step,ts) VALUES(?,?,?,0,?)", (uid, bet, mode, now()))
        lvl = add_xp(uid, max(1, bet // 20))
        r = q1("SELECT * FROM pump WHERE user=?", uid)
    return {**state(r), "stars": bal(uid), "levelup": lvl}


def _cash(uid, r):
    pay = int(r["bet"] * mult(r["mode"], r["step"]))
    db.execute("DELETE FROM pump WHERE user=?", (uid,))
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
    event(uid, "pump", pay - r["bet"], stake=r["bet"])
    return {**state(r), "active": False, "pay": pay, "stars": bal(uid)}


@app.post(R + "/pump/step")
def pump_step(uid=Depends(auth)):
    import fair
    with tx():
        r = q1("SELECT * FROM pump WHERE user=?", uid) or err("игра не начата")
        rr, pf = fair.rolls(uid, "pump", ref=f"{r['mode']}:{r['step']}")
        fair.record(uid, "pump", 0, 0, {"p": round(risk(r["mode"], r["step"]), 6), "hit": rr[0] < risk(r["mode"], r["step"])}, pf)
        if rr[0] < risk(r["mode"], r["step"]):   # лопнул
            db.execute("DELETE FROM pump WHERE user=?", (uid,))
            event(uid, "pump", -r["bet"], stake=r["bet"])
            return {**state(r), "active": False, "popped": r["step"] + 1, "stars": bal(uid), "pf": pf}
        db.execute("UPDATE pump SET step=step+1 WHERE user=?", (uid,))
        r = q1("SELECT * FROM pump WHERE user=?", uid)
        if r["step"] >= STEPS:   # надул до предела — выплата автоматически
            return {**_cash(uid, r), "pf": pf}
        return {**state(r), "pf": pf}


@app.post(R + "/pump/cashout")
def pump_cashout(uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM pump WHERE user=?", uid) or err("игра не начата")
        if not r["step"]:
            err("качни хотя бы раз")
        return _cash(uid, r)
