"""Краш-дуэль 1 на 1, «Больше/меньше» (Hi-Lo) и крафт подарков."""
from settings import conf, tuned
import json
import math
import random
import time

from fastapi import Depends, Request

import economy as E
from app import (R, app, auth, bal, cancel_trades_with, check_bet, db, err, event, gift_out, notify, now, own_gift, q, q1,
                 tx, unpin, user_brief, add_xp, DUEL_FEE, esc, APP_URL, edge)

# ============================================================ краш-дуэль
# Дуэль game='crash': после принятия оба жмут «Готов», ракета взлетает через 3 с.
# Кто забрал позже (но до взрыва) — забирает банк. Оба взорвались или забрали одинаково — ставки возвращаются.
for col in ("cp REAL", "start REAL", "ready TEXT"):
    try:
        db.execute(f"ALTER TABLE duels ADD COLUMN {col}")
    except Exception:
        pass
CD_K = 0.12             # скорость роста множителя: x2 за ~5,8 с, x10 за ~19 с
CD_READY = 180          # столько ждём готовности обоих, потом отмена с возвратом
CD_MAX = 100.0


def cd_mult(d, t):
    return math.exp(CD_K * max(0.0, t - d["start"]))


def cd_cash(d):
    r = json.loads(d["ready"] or "{}")
    return r.get("ca"), r.get("cb")


def cd_finish(d, t=None):
    """Подвести итог, если пора (вызывать внутри tx). Возвращает True, если дуэль закончилась."""
    t = t or time.time()
    if d["status"] != "live":
        return False
    r = json.loads(d["ready"] or "{}")
    if not d["start"]:
        if now() - d["ts"] > CD_READY:          # кто-то так и не нажал «Готов»
            for u in (d["a"], d["b"]):
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (d["stake"], u))
            db.execute("UPDATE duels SET status='expired', done=? WHERE id=?", (now(), d["id"]))
            return True
        return False
    ca, cb = r.get("ca"), r.get("cb")
    crashed = t >= d["start"] + math.log(d["cp"]) / CD_K
    if not (ca and cb) and not crashed:
        return False
    if ca and cb and ca != cb:
        win = d["a"] if ca > cb else d["b"]
    elif ca and not cb:
        win = d["a"]
    elif cb and not ca:
        win = d["b"]
    else:
        win = None
    if win is None:                             # ничья — вернуть ставки
        for u in (d["a"], d["b"]):
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (d["stake"], u))
    else:
        pay = int(d["stake"] * 2 * (1 - DUEL_FEE))
        lose = d["b"] if win == d["a"] else d["a"]
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, win))
        event(win, "duel", pay - d["stake"], stake=d["stake"])
        event(lose, "duel", -d["stake"], stake=d["stake"])
    db.execute("UPDATE duels SET status='done', winner=?, ra=?, rb=?, done=? WHERE id=?",
               (win, json.dumps([ca]), json.dumps([cb]), now(), d["id"]))
    return True


def cd_tick_all():
    with tx():
        for d in q("SELECT * FROM duels WHERE status='live'"):
            cd_finish(d)


def cd_view(d, uid):
    t = time.time()
    ca, cb = cd_cash(d) if d["status"] == "live" else (json.loads(d["ra"] or "[null]")[0], json.loads(d["rb"] or "[null]")[0])
    r = json.loads(d["ready"] or "{}")
    a, b = q1("SELECT * FROM users WHERE id=?", d["a"]), q1("SELECT * FROM users WHERE id=?", d["b"])
    over = d["status"] != "live"
    return {"id": d["id"], "status": d["status"], "stake": d["stake"], "pay": int(d["stake"] * 2 * (1 - DUEL_FEE)),
            "a": user_brief(a), "b": user_brief(b), "ca": ca, "cb": cb, "readyA": bool(r.get("ra")), "readyB": bool(r.get("rb")),
            "start": d["start"], "now": t, "k": CD_K, "cp": d["cp"] if over else None, "winner": d["winner"],
            "me": "a" if uid == d["a"] else "b", "readyLeft": max(0, d["ts"] + CD_READY - now()) if not d["start"] else 0}


@app.get(R + "/cduel/{did}")
def cduel(did: int, uid=Depends(auth)):
    with tx():
        d = q1("SELECT * FROM duels WHERE id=? AND game='crash'", did)
        if not d or uid not in (d["a"], d["b"]):
            err("дуэль не найдена")
        if cd_finish(d):
            d = q1("SELECT * FROM duels WHERE id=?", did)
    out = cd_view(d, uid)
    out["stars"] = bal(uid)
    return out


@app.post(R + "/cduel/{did}/{action}")
def cduel_act(did: int, action: str, uid=Depends(auth)):
    t = time.time()
    other = None
    with tx():
        d = q1("SELECT * FROM duels WHERE id=? AND game='crash'", did)
        if not d or uid not in (d["a"], d["b"]):
            err("дуэль не найдена")
        if cd_finish(d, t) or d["status"] != "live":
            d = q1("SELECT * FROM duels WHERE id=?", did)
            out = cd_view(d, uid)
            out["stars"] = bal(uid)
            return out
        r = json.loads(d["ready"] or "{}")
        me = "a" if uid == d["a"] else "b"
        if action == "ready":
            r["r" + me] = 1
            if r.get("ra") and r.get("rb") and not d["start"]:
                db.execute("UPDATE duels SET start=? WHERE id=?", (t + 3, did))
            else:
                other = d["b"] if me == "a" else d["a"]
            db.execute("UPDATE duels SET ready=? WHERE id=?", (json.dumps(r), did))
        elif action == "cash":
            if not d["start"] or t < d["start"]:
                err("ракета ещё не взлетела")
            if r.get("c" + me):
                err("ты уже забрал")
            m = cd_mult(d, t)
            if m < d["cp"]:
                r["c" + me] = math.floor(m * 100) / 100
                db.execute("UPDATE duels SET ready=? WHERE id=?", (json.dumps(r), did))
        else:
            err("Действие устарело — обнови экран")
        d = q1("SELECT * FROM duels WHERE id=?", did)
        cd_finish(d, t)
        d = q1("SELECT * FROM duels WHERE id=?", did)
        out = cd_view(d, uid)
        out["stars"] = bal(uid)
        nm = q1("SELECT name FROM users WHERE id=?", uid)["name"]
    if other:
        notify(other, f"🚀 <b>{esc(nm)}</b> готов к краш-дуэли на {d['stake']} ⭐ — заходи, ракета ждёт тебя", url=APP_URL + f"?cduel={did}")
    return out


# ============================================================ больше / меньше
db.executescript("CREATE TABLE IF NOT EXISTS hilo(user INTEGER PRIMARY KEY, bet INTEGER, mult REAL, card INTEGER, suit INTEGER, hist TEXT, ts INTEGER);")
HL_EDGE = conf("games.hilo_edge", 0.96)
HL_MAX = 1000.0


def hl_odds(card):
    """card 1..13 (двойка..туз). «Выше или так же» и «ниже или так же»: вероятность и множитель."""
    ph, pl = (14 - card) / 13, card / 13
    return {"hi": {"p": ph, "m": round(edge(tuned("games.hilo_edge", HL_EDGE)) / ph, 2) if ph < 1 else None},
            "lo": {"p": pl, "m": round(edge(tuned("games.hilo_edge", HL_EDGE)) / pl, 2) if pl < 1 else None}}


def hl_out(h):
    if not h:
        return {"active": False}
    return {"active": True, "bet": h["bet"], "mult": h["mult"], "card": h["card"], "suit": h["suit"],
            "hist": json.loads(h["hist"]), "odds": hl_odds(h["card"]), "win": int(h["bet"] * h["mult"])}


@app.get(R + "/hilo")
def hilo(uid=Depends(auth)):
    return hl_out(q1("SELECT * FROM hilo WHERE user=?", uid))


@app.post(R + "/hilo/start")
async def hilo_start(req: Request, uid=Depends(auth)):
    bet = int((await req.json()).get("bet", 0))
    import fair
    with tx():
        if q1("SELECT 1 FROM hilo WHERE user=?", uid):
            err("сначала доиграй текущую партию")
        check_bet(uid, bet)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        rr, pf = fair.rolls(uid, "hilo", "start", 2)
        c, s = 1 + fair.idx(rr[0], 13), fair.idx(rr[1], 4)
        db.execute("INSERT INTO hilo VALUES(?,?,?,?,?,?,?)", (uid, bet, 1.0, c, s, json.dumps([[c, s, None]]), now()))
        lvl = add_xp(uid, max(1, bet // 20))
    out = hl_out(q1("SELECT * FROM hilo WHERE user=?", uid))
    return {**out, "stars": bal(uid), "levelup": lvl}


def _hl_pay(uid, h, mult):
    pay = int(h["bet"] * mult)
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
    db.execute("DELETE FROM hilo WHERE user=?", (uid,))
    event(uid, "hilo", pay - h["bet"], stake=h["bet"])
    return pay


@app.post(R + "/hilo/guess")
async def hilo_guess(req: Request, uid=Depends(auth)):
    d = str((await req.json()).get("dir", ""))
    import fair
    with tx():
        h = q1("SELECT * FROM hilo WHERE user=?", uid)
        if not h:
            err("партия не начата")
        hist = json.loads(h["hist"])
        rr, pf = fair.rolls(uid, "hilo", d[:8], 2)
        c, s = 1 + fair.idx(rr[0], 13), fair.idx(rr[1], 4)
        fair.record(uid, "hilo", 0, 0, {"card": c, "suit": s}, pf)
        if d == "skip":
            if len([x for x in hist if x[2] == "skip"]) >= 10:
                err("пропускать можно не больше 10 раз")
            hist.append([c, s, "skip"])
            db.execute("UPDATE hilo SET card=?, suit=?, hist=? WHERE user=?", (c, s, json.dumps(hist), uid))
            return {**hl_out(q1("SELECT * FROM hilo WHERE user=?", uid)), "res": "skip"}
        o = hl_odds(h["card"]).get(d)
        if not o or not o["m"]:
            err("так угадывать нельзя")
        ok = c >= h["card"] if d == "hi" else c <= h["card"]
        hist.append([c, s, d if ok else "x"])
        if not ok:
            db.execute("DELETE FROM hilo WHERE user=?", (uid,))
            event(uid, "hilo", -h["bet"], stake=h["bet"])
            return {"active": False, "res": "lose", "card": c, "suit": s, "hist": hist, "bet": h["bet"], "stars": bal(uid)}
        mult = round(h["mult"] * edge(tuned("games.hilo_edge", HL_EDGE)) / o["p"], 4)
        if mult >= HL_MAX:
            pay = _hl_pay(uid, h, HL_MAX)
            return {"active": False, "res": "max", "card": c, "suit": s, "hist": hist, "pay": pay, "mult": HL_MAX, "stars": bal(uid)}
        db.execute("UPDATE hilo SET mult=?, card=?, suit=?, hist=? WHERE user=?", (mult, c, s, json.dumps(hist), uid))
    return {**hl_out(q1("SELECT * FROM hilo WHERE user=?", uid)), "res": "win"}


@app.post(R + "/hilo/cashout")
def hilo_cashout(uid=Depends(auth)):
    with tx():
        h = q1("SELECT * FROM hilo WHERE user=?", uid)
        if not h:
            err("партия не начата")
        if h["mult"] <= 1:
            err("сначала угадай хотя бы раз")
        pay = _hl_pay(uid, h, h["mult"])
    return {"active": False, "pay": pay, "mult": h["mult"], "stars": bal(uid)}


# ============================================================ крафт
# 3–10 подарков сгорают → 1 подарок выбранной коллекции. Ценность = сумма × множитель:
# 72% — ×0,55–0,9 · 23% — ×0,95–1,5 · 5% — ×1,5–2,5 (в среднем ≈ ×0,9)
CRAFT_TIERS = [(0.72, 0.55, 0.90), (0.23, 0.95, 1.50), (0.05, 1.50, 2.50)]


def _craft_target(rr):
    x, acc = rr[0], 0
    for p, lo, hi in CRAFT_TIERS:
        acc += p
        if x <= acc:
            return lo + (hi - lo) * rr[1]
    return 1.0


def _craft_variant(col, target, rng):
    """Вариант подарка коллекции с ценностью как можно ближе к цели."""
    d = E.CATALOG[col]
    best, bd = None, None
    for _ in range(3000):
        m, b, s = rng.choice(d["models"]), rng.choice(d["backdrops"]), rng.choice(d["symbols"])
        v = max(1, round(E.base(col) * E.mult(col, m[1], b[1], s[1])))
        dist = abs(math.log(v / target))
        if bd is None or dist < bd:
            best, bd = (m[0], b[0], s[0], v), dist
    return best


@app.post(R + "/craft")
async def craft(req: Request, uid=Depends(auth)):
    b = await req.json()
    gids = [int(x) for x in b.get("gids", [])][:10]
    col = str(b.get("col", ""))
    if len(set(gids)) < 3:
        err("нужно минимум 3 подарка")
    import fair
    with tx():
        gs = [own_gift(g, uid) for g in set(gids)]
        if any(g["price"] is not None for g in gs):
            err("сначала сними подарки с маркета")
        cols = {g["col"] for g in gs}
        if col not in cols:
            err("коллекция должна быть одной из выбранных")
        total = sum(g["value"] for g in gs)
        rr, pf = fair.rolls(uid, "craft", col, 3)
        k = _craft_target(rr)
        target = total * k
        rng = random.Random(f"{rr[2]:.15f}")   # вид подарка: подбор детерминирован третьим броском ставки
        model, backdrop, symbol, value = _craft_variant(col, target, rng)
        # коллекция не дотягивает до выпавшей ценности (дешёвая) — разницу доплачиваем звёздами
        bonus = int(target - value) if value < target * 0.9 else 0
        if bonus:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (bonus, uid))
        for g in gs:
            db.execute("DELETE FROM gifts WHERE id=?", (g["id"],))
            unpin(uid, g["id"])
            cancel_trades_with(g["id"])
        cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                         (uid, col, model, backdrop, symbol, rng.randint(1, E.supply(col)), value, now()))
        new = gift_out(q1("SELECT * FROM gifts WHERE id=?", cur.lastrowid))
        event(uid, "craft", value + bonus - total, stake=total, pf=pf, res={"k": round(k, 6), "value": value, "bonus": bonus})
        db.execute("INSERT INTO feed(user,gift,cs,ts) VALUES(?,?,?,?)", (uid, cur.lastrowid, "craft", now()))
        lvl = add_xp(uid, max(1, total // 50))
    return {"gift": new, "total": total, "k": round((value + bonus) / total, 3), "bonus": bonus, "stars": bal(uid), "levelup": lvl}
