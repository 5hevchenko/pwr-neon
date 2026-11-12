"""Привилегии топа богачей (звёзды + ценность подарков):
корона в профиле и топе, скидка на комиссию маркета и ежедневный ключ от кейса (раз в сутки в полночь по серверу)."""
import asyncio
import json
import time

from app import ADMINS, BANNED, RICH_RANK, db, esc, notify, now, q, q1, tx

db.executescript("""
CREATE TABLE IF NOT EXISTS rich_days(day INTEGER PRIMARY KEY, result TEXT, ts INTEGER);
""")
TOP = 10
# место → кейс, ключ от которого выдаём каждый день
DAILY_KEY = {1: "cups", 2: "lux", 3: "lux", **{i: "luck" for i in range(4, TOP + 1)}}
PERKS = [   # для экрана «Привилегии богачей»
    {"place": "1", "key": "Кубки", "fee": 1},
    {"place": "2–3", "key": "Роскошь", "fee": 2},
    {"place": "4–10", "key": "Удача", "fee": 3},
]


def market_fee(uid, base):
    """Комиссия маркета для продавца: топ-1 — 1%, топ-2–3 — 2%, топ-4–10 — 3% (вместо 5%)."""
    r = RICH_RANK.get(uid)
    f = base if not r else min(base, 0.01 if r == 1 else 0.02 if r <= 3 else 0.03)   # скидка не выше общей ставки
    u = q1("SELECT vip_until FROM users WHERE id=?", uid)
    return f / 2 if u and (u["vip_until"] or 0) > now() else f   # VIP — комиссия вдвое ниже


def ranking():
    """Текущий топ богачей без админов и забаненных."""
    rows = q("""SELECT u.id, u.stars + COALESCE((SELECT SUM(value) FROM gifts g WHERE g.owner=u.id),0) score
                FROM users u ORDER BY score DESC LIMIT ?""", TOP + len(ADMINS) + len(BANNED))
    out = [r["id"] for r in rows if r["id"] not in ADMINS and r["id"] not in BANNED][:TOP]
    RICH_RANK.clear()
    RICH_RANK.update({uid: i + 1 for i, uid in enumerate(out)})
    return out


def _day():
    lt = time.localtime()
    return int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)))


def _award():
    """Раз в сутки (идемпотентно): ключи топу богачей."""
    import economy as E
    day = _day()
    top = ranking()
    if q1("SELECT 1 FROM rich_days WHERE day=?", day) or not top:
        return
    msgs = []
    with tx():
        if q1("SELECT 1 FROM rich_days WHERE day=?", day):
            return
        res = []
        for place, uid in enumerate(top, 1):
            cid = DAILY_KEY[place]
            db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,1) ON CONFLICT(user,cid) DO UPDATE SET n=n+1", (uid, cid))
            res.append({"place": place, "user": uid, "cid": cid})
            msgs.append((uid, f"👑 Ты {place} в топе богачей! Ежедневная награда: ключ от кейса «{esc(E.CASES[cid]['title'])}». "
                              f"Комиссия маркета для тебя — {round(market_fee(uid, 0.05) * 100)}%."))
        db.execute("INSERT INTO rich_days(day,result,ts) VALUES(?,?,?)", (day, json.dumps(res), now()))
    for uid, text in msgs:
        notify(uid, text)


async def rich_loop():
    await asyncio.sleep(15)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _award)
        except Exception as e:
            print("rich:", e, flush=True)
        await asyncio.sleep(300)   # заодно обновляем короны раз в 5 минут
