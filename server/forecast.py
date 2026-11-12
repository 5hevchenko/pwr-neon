"""Прогноз дня: тотализатор на итоги следующих суток (по Москве). Банк не рискует: победители делят ставки проигравших, банк берёт комиссию.

Три рынка:
- crash: самый большой икс краша за сутки. Иксы заданы цепочкой хэшей, раунды идут и без ставок, повлиять нельзя;
- carousel: сколько бонусов выпадет на Карусели за сутки, тоже цепочка хэшей;
- bank: вырастет ли банк за сутки. Считается без операций участников рынка, иначе итог можно подкрутить своей игрой.

Линия фиксируется до приёма ставок: медиана прошлых полных суток, поэтому шансы сторон близки. Ставки закрываются до начала суток.
Совпало с линией, нет соперника или сутки неполные из-за простоя: ставка возвращается без комиссии.
"""
import asyncio
import statistics
import time

from fastapi import Depends, Request

import app as A
from app import R, app, auth, bal, check_bet, db, err, event, notify, now, q, q1, tx
from settings import conf

db.executescript("""
CREATE TABLE IF NOT EXISTS fc_market(day INTEGER, key TEXT, line REAL, value REAL, side TEXT, up INTEGER DEFAULT 0, down INTEGER DEFAULT 0, done INTEGER DEFAULT 0, PRIMARY KEY(day, key));
CREATE TABLE IF NOT EXISTS fc_bet(id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER, key TEXT, user INTEGER, side TEXT, amount INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS fc_bet_day ON fc_bet(day, key);
CREATE INDEX IF NOT EXISTS fc_bet_user ON fc_bet(user, day);
CREATE TABLE IF NOT EXISTS fc_stat(user INTEGER PRIMARY KEY, won INTEGER DEFAULT 0, total INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, best INTEGER DEFAULT 0);
""")

RAKE = conf("games.forecast_rake", 0.08)
MIN_BET, MAX_BET = 100, conf("games.forecast_max", 100_000)   # максимум на один рынок
KEYS = ("crash", "carousel", "bank")
SHIFT = 3 * 3600        # сутки считаем по Москве
DAY = 86400
MIN_ROUNDS = 1000       # меньше раундов за сутки: был простой, рынок возвращает ставки (обычно их около 3000)
SETTLE_DELAY = 120      # ждём раунды, которые закончились в конце суток
HISTORY = 14


def _day(t=None):
    return ((t if t is not None else now()) + SHIFT) // DAY


def _start(day):
    return day * DAY - SHIFT


def _metric(key, day, skip=()):
    """Итог рынка за сутки (или за прошедшую часть текущих), None — данных мало."""
    a, b = _start(day), _start(day + 1)
    if key == "crash":
        r = q1("SELECT MAX(crash) v, COUNT(*) n FROM pf_crash WHERE ts>=? AND ts<?", a, b)
        return r["v"], r["n"]
    if key == "carousel":
        r = q1("SELECT COALESCE(SUM(sector IN ('safe','ladder','bomb')),0) v, COUNT(*) n FROM cr_round WHERE ts>=? AND ts<?", a, b)
        return r["v"], r["n"]
    import bank
    ph = ",".join("?" * len(skip)) or "NULL"
    r = q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE ({bank.BANK_KINDS}) AND kind NOT IN ('bankbet','forecast') AND ts>=? AND ts<? AND user NOT IN ({ph})",
           max(a, bank.bank_from()), b, *skip)
    return -int(r["s"]), None


def _past(key, day):
    """Итоги полных суток до кануна рынка: линия не меняется, пока идёт приём ставок."""
    a, b = _start(day - 1 - HISTORY), _start(day - 1)
    if key == "crash":
        sql = "SELECT MAX(crash) v FROM pf_crash WHERE ts>=? AND ts<? GROUP BY (ts+?)/? HAVING COUNT(*)>=?"
    else:
        sql = "SELECT SUM(sector IN ('safe','ladder','bomb')) v FROM cr_round WHERE ts>=? AND ts<? GROUP BY (ts+?)/? HAVING COUNT(*)>=?"
    return [r["v"] for r in q(sql, a, b, SHIFT, DAY, MIN_ROUNDS)]


def _per_day(table):
    """Раундов в сутки по последним данным, пока истории нет."""
    t = now()
    r = q1(f"SELECT COUNT(*) n, MIN(ts) a FROM {table} WHERE ts>=?", t - DAY)
    return r["n"] * DAY / max(1, t - r["a"]) if r["n"] >= 50 else None


def _line(key, day):
    if key == "bank":
        return 0
    past = _past(key, day)
    if key == "crash":
        # медиана максимума из N раундов: P(икс >= x) = возврат / x, отсюда x = возврат * N / ln 2; потолок икса 10 000
        v = statistics.median(past) if len(past) >= 3 else min(9000, 0.94 * (_per_day("pf_crash") or 3200) / 0.693)
        return float(f"{v:.2g}")
    if len(past) >= 3:
        return int(statistics.median(past))
    import carousel
    w = carousel.weights(0.94)
    return int((_per_day("cr_round") or 2400) * sum(w[k] for k in carousel.BONUS_SHARE))


def _ensure(day):
    if q1("SELECT COUNT(*) n FROM fc_market WHERE day=?", day)["n"] == len(KEYS):
        return
    lines = {k: _line(k, day) for k in KEYS}
    with tx():
        for k, v in lines.items():
            db.execute("INSERT OR IGNORE INTO fc_market(day,key,line) VALUES(?,?,?)", (day, k, v))


def _label(day):
    return time.strftime("%d.%m", time.gmtime(day * DAY))


def _settle(day):
    per_user = {}
    for m in q("SELECT * FROM fc_market WHERE day=? AND done=0", day):
        key = m["key"]
        bets = q("SELECT * FROM fc_bet WHERE day=? AND key=?", day, key)
        value, rounds = _metric(key, day, sorted({b["user"] for b in bets}))
        if rounds is not None and rounds < MIN_ROUNDS:
            value = None
        side = None if value is None or value == m["line"] else "up" if value > m["line"] else "down"
        up = sum(b["amount"] for b in bets if b["side"] == "up")
        down = sum(b["amount"] for b in bets if b["side"] == "down")
        win_pool, lose_pool = (up, down) if side == "up" else (down, up) if side == "down" else (0, 0)
        with tx():
            if q1("SELECT done FROM fc_market WHERE day=? AND key=?", day, key)["done"]:
                continue
            db.execute("UPDATE fc_market SET value=?, side=?, up=?, down=?, done=1 WHERE day=? AND key=?", (value, side, up, down, day, key))
            played = bool(win_pool and lose_pool)
            for u in {b["user"] for b in bets}:
                mine = [b for b in bets if b["user"] == u]
                stake = sum(b["amount"] for b in mine)
                res = per_user.setdefault(u, {"won": 0, "n": 0, "delta": 0, "back": 0})
                if not played:   # совпало с линией, нет соперника или простой
                    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (stake, u))
                    res["back"] += stake
                    continue
                ok = mine[0]["side"] == side
                pay = stake + int(stake / win_pool * lose_pool * (1 - RAKE)) if ok else 0
                if pay:
                    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, u))
                event(u, "forecast", pay - stake, stake=stake)
                db.execute("""INSERT INTO fc_stat(user,won,total,streak,best) VALUES(?,?,1,?,?) ON CONFLICT(user) DO UPDATE SET
                              won=won+excluded.won, total=total+1, streak=CASE WHEN excluded.won=1 THEN streak+1 ELSE 0 END,
                              best=MAX(best, CASE WHEN excluded.won=1 THEN streak+1 ELSE 0 END)""", (u, int(ok), int(ok), int(ok)))
                res["won"] += ok
                res["n"] += 1
                gain = pay - stake
                res["delta"] += gain - (int(gain * A.BIGWIN_FEE) if gain >= A.BIGWIN_FEE_MIN else 0)   # event уже снял сбор с крупного выигрыша
    for u, r in per_user.items():
        parts = [f"Прогноз дня за {_label(day)}:"]
        if r["n"]:
            total = f"{abs(r['delta']):,}".replace(",", " ")
            parts.append(f"угадано {r['won']} из {r['n']}, итог {'+' if r['delta'] >= 0 else '−'}⭐ {total}.")
        if r["back"]:
            back = f"{r['back']:,}".replace(",", " ")
            parts.append(f"Возврат ⭐ {back}: не нашлось соперника или итог совпал с линией.")
        parts.append("Прогноз на новые сутки уже открыт.")
        notify(u, " ".join(parts))


async def _loop():
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.run_in_executor(None, _ensure, _day() + 1)
            ready = _day(now() - SETTLE_DELAY)
            for r in q("SELECT DISTINCT day FROM fc_market WHERE done=0 AND day<?", ready):
                await loop.run_in_executor(None, _settle, r["day"])
        except Exception as e:
            print("forecast:", e, flush=True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _fc_start():
    asyncio.create_task(_loop())


def _out(m, uid):
    mine = q("SELECT side, amount FROM fc_bet WHERE day=? AND key=? AND user=?", m["day"], m["key"], uid)
    return {"day": m["day"], "key": m["key"], "line": m["line"], "value": m["value"], "side": m["side"], "done": m["done"],
            "mine": {"side": mine[0]["side"], "amount": sum(b["amount"] for b in mine)} if mine else None}


def _pools(m):
    if m["done"]:
        return {"up": m["up"], "down": m["down"]}
    p = {r["side"]: r["s"] for r in q("SELECT side, SUM(amount) s FROM fc_bet WHERE day=? AND key=? GROUP BY side", m["day"], m["key"])}
    return {"up": p.get("up", 0), "down": p.get("down", 0)}


@app.get(R + "/forecast")
def fc_state(uid=Depends(auth)):
    today = _day()
    _ensure(today + 1)
    s = q1("SELECT won, total, streak, best FROM fc_stat WHERE user=?", uid)
    live = []
    for m in q("SELECT * FROM fc_market WHERE day=?", today):
        users = sorted({r["user"] for r in q("SELECT DISTINCT user FROM fc_bet WHERE day=? AND key=?", today, m["key"])})
        live.append({**_out(m, uid), **_pools(m), "now": _metric(m["key"], today, users)[0]})
    return {"day": today + 1, "dayTs": _start(today + 1), "closesIn": _start(today + 1) - now(), "rake": RAKE, "min": MIN_BET, "max": MAX_BET,
            "open": sorted(({**_out(m, uid), **_pools(m)} for m in q("SELECT * FROM fc_market WHERE day=?", today + 1)), key=lambda x: KEYS.index(x["key"])),
            "live": live,
            "past": [{**_out(m, uid), **_pools(m), "dayTs": _start(m["day"])} for m in q("SELECT * FROM fc_market WHERE done=1 ORDER BY day DESC, key LIMIT 9")],
            "stats": dict(s) if s else {"won": 0, "total": 0, "streak": 0, "best": 0}}


@app.post(R + "/forecast/bet")
async def fc_bet(req: Request, uid=Depends(auth)):
    b = await req.json()
    key, side, amount = str(b.get("key", "")), str(b.get("side", "")), int(b.get("amount", 0))
    if key not in KEYS or side not in ("up", "down"):
        err("выбери рынок и исход")
    day = _day() + 1
    _ensure(day)
    with tx():
        check_bet(uid, amount, MIN_BET, MAX_BET)
        if q1("SELECT 1 FROM fc_bet WHERE day=? AND key=? AND user=? AND side<>?", day, key, uid, side):
            err("на этот рынок ты уже поставил другой исход")
        mine = q1("SELECT COALESCE(SUM(amount),0) s FROM fc_bet WHERE day=? AND key=? AND user=?", day, key, uid)["s"]
        if mine + amount > MAX_BET:
            err(f"на один рынок не больше ⭐ {MAX_BET:,}".replace(",", " "))
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        db.execute("INSERT INTO fc_bet(day,key,user,side,amount,ts) VALUES(?,?,?,?,?,?)", (day, key, uid, side, amount, now()))
    return {**fc_state(uid), "stars": bal(uid)}
