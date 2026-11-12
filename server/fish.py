"""«Рыбалка» — заброс, поклёвка и вываживание. После поклёвки множитель растёт, пока леска не порвётся;
вытащи раньше — заберёшь ставку × множитель. Это одиночный краш: точку обрыва сервер выбирает при забросе
(P(дотянуть до x) = RTP / x, games.fish_rtp во вкладке «Шансы»), время считает сам — клиент только рисует.
Незабранный раунд закрывается при следующем запросе игрока (обрыв или автовывод)."""
import math
import random
import time

from fastapi import Depends, Request

import economy as E
from app import R, add_xp, app, auth, bal, check_bet, db, edge, err, event, preview_out, q1, tx
from settings import conf, tuned

db.executescript("""
CREATE TABLE IF NOT EXISTS fish(user INTEGER PRIMARY KEY, bet INTEGER, bust REAL, t0 REAL, auto REAL, ts INTEGER);
""")
RTP = conf("games.fish_rtp", 0.96)
K = 0.11          # скорость роста: x = e^(K·t) — x2 за ~6,3 с, x10 за ~21 с
MAX = 1000
# что попалось на крючок: море, блеск и всякое смешное
CATCH = ["Lol Pop", "Kissed Frog", "Pet Snake", "Ion Gem", "Diamond Ring", "Precious Peach", "Plush Pepe", "Sakura Flower",
         "Swiss Watch", "Loot Bag", "Bunny Muffin", "Jelly Bunny", "Star Notepad", "Eternal Rose", "Signet Ring", "Durov's Cap"]


def x_at(t):
    return math.exp(K * max(0.0, t))


def t_of(x):
    return math.log(x) / K


def _bust(uid):
    """Точка обрыва: P(bust ≥ x) = RTP / x; с шансом 1 − RTP рыба срывается сразу после поклёвки (честный бросок)."""
    import fair
    u, pf = fair.one(uid, "fish", ref="bust")
    b = edge(tuned("games.fish_rtp", RTP)) / max(1e-9, 1 - u)
    return (1.0 if b < 1.01 else min(MAX, math.floor(b * 100) / 100)), pf


def _resolve(uid, r, at=None):
    """Закрыть раунд, если он уже кончился сам (обрыв или автовывод). Возвращает итог или None."""
    t = (at or time.time()) - r["t0"]
    if t < 0:
        return None
    x = x_at(t)
    if r["auto"] and r["auto"] < r["bust"] and x >= r["auto"]:
        return _pay(uid, r, r["auto"])
    if x >= r["bust"]:
        db.execute("DELETE FROM fish WHERE user=?", (uid,))
        event(uid, "fish", -r["bet"], stake=r["bet"], res={"bust": r["bust"]})
        return {"active": False, "lost": True, "bust": r["bust"], "bet": r["bet"]}
    return None


def _pay(uid, r, x):
    x = math.floor(x * 100) / 100
    pay = int(r["bet"] * x)
    db.execute("DELETE FROM fish WHERE user=?", (uid,))
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
    event(uid, "fish", pay - r["bet"], stake=r["bet"], res={"bust": r["bust"], "mult": x})
    col = random.choice([c for c in CATCH if c in E.CATALOG] or list(E.CATALOG))
    return {"active": False, "won": True, "mult": x, "pay": pay, "bet": r["bet"], "bust": r["bust"], "gift": preview_out(col, E.roll(col))}


def _state(r):
    now_ = time.time()
    return {"active": True, "bet": r["bet"], "auto": r["auto"], "bite": round(r["t0"] - now_, 3), "elapsed": round(now_ - r["t0"], 3)}


@app.get(R + "/fish")
def fish(uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM fish WHERE user=?", uid)
        res = _resolve(uid, r) if r else None
    base = {"k": K, "rtp": round(edge(tuned("games.fish_rtp", RTP)) * 100, 1), "stars": bal(uid)}
    if res:
        return {**base, **res}
    return {**base, **(_state(r) if r else {"active": False})}


@app.post(R + "/fish/cast")
async def fish_cast(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet = int(b.get("bet", 0))
    auto = b.get("auto")
    auto = round(float(auto), 2) if auto else None
    if auto is not None and not 1.01 <= auto <= MAX:
        err(f"автовывод — от x1,01 до x{MAX}")
    with tx():
        r = q1("SELECT * FROM fish WHERE user=?", uid)
        if r and not _resolve(uid, r):
            err("удочка уже заброшена")
        check_bet(uid, bet)
        bite = time.time() + random.uniform(1.4, 3.6)   # поклёвка — пауза для атмосферы, на шанс не влияет
        bust, pf = _bust(uid)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        db.execute("INSERT INTO fish(user,bet,bust,t0,auto,ts) VALUES(?,?,?,?,?,?) ON CONFLICT(user) DO UPDATE SET bet=excluded.bet, "
                   "bust=excluded.bust, t0=excluded.t0, auto=excluded.auto, ts=excluded.ts", (uid, bet, bust, bite, auto, int(time.time())))
        lvl = add_xp(uid, max(1, bet // 20))
        r = q1("SELECT * FROM fish WHERE user=?", uid)
    return {**_state(r), "stars": bal(uid), "levelup": lvl, "pf": pf}


@app.post(R + "/fish/reel")
def fish_reel(uid=Depends(auth)):
    """Вытащить: множитель по серверному времени. Опоздал — леска уже порвалась."""
    at = time.time()
    with tx():
        r = q1("SELECT * FROM fish WHERE user=?", uid) or err("удочка не заброшена")
        res = _resolve(uid, r, at)
        if not res:
            if at < r["t0"]:
                err("ещё не клюнуло")
            res = _pay(uid, r, x_at(at - r["t0"]))
    return {**res, "stars": bal(uid)}
