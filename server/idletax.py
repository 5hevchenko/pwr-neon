"""Сбор за простой: раз в неделю с брошенных больших балансов. Кто не заходил 14 дней и держит больше порога,
отдаёт банку долю с суммы сверх порога (по умолчанию 1% с того, что выше 5 млн). Звёзды возвращаются в банк, экономика не
раздувается от мёртвых аккаунтов. Активных игроков сбор не касается вовсе: достаточно зайти раз в две недели.
Первый раз игроку приходит сообщение с объяснением. Всё видно в журнале и на публичной странице банка."""
import asyncio

import app as A
from app import db, esc, event, notify, now, q, q1, tx, week_start
from settings import conf

ON = conf("idletax.on", True)
FLOOR = conf("idletax.floor", 5_000_000)
RATE = conf("idletax.rate", 0.01)
IDLE = conf("idletax.idle_days", 14) * 86400

db.executescript("""CREATE TABLE IF NOT EXISTS idletax(week INTEGER, user INTEGER, amount INTEGER, ts INTEGER, PRIMARY KEY(week, user));
CREATE TABLE IF NOT EXISTS idletax_warn(user INTEGER PRIMARY KEY, ts INTEGER);""")
WARN_AHEAD = 6 * 86400   # сначала предупреждение, списание — не раньше чем через 6 дней после него


def nf(n):
    return f"{int(n):,}".replace(",", " ")


def _run():
    import wipe
    if not ON or wipe.frozen():
        return
    week = week_start()
    if q1("SELECT 1 FROM idletax WHERE week=? AND user=0", week):
        return
    t = now()
    msgs = []
    with tx():
        if q1("SELECT 1 FROM idletax WHERE week=? AND user=0", week):
            return
        db.execute("DELETE FROM idletax_warn WHERE EXISTS (SELECT 1 FROM users u WHERE u.id=idletax_warn.user AND u.seen>idletax_warn.ts)")   # зашёл — предупреждение сгорает
        for u in q("SELECT id, name, stars, seen FROM users WHERE stars>? AND seen<? AND banned=0 AND id>0", FLOOR, t - IDLE):
            amount = int((u["stars"] - FLOOR) * RATE)
            if amount <= 0:
                continue
            w = q1("SELECT ts FROM idletax_warn WHERE user=?", u["id"])
            if not w:
                db.execute("INSERT INTO idletax_warn(user,ts) VALUES(?,?)", (u["id"], t))
                msgs.append((u["id"], f"{esc(u['name'])}, тебя не было в игре больше {IDLE // 86400} дней, а на балансе больше {nf(FLOOR)} ⭐. "
                                      f"С брошенных больших балансов банк раз в неделю берёт {RATE * 100:g}% с суммы сверх {nf(FLOOR)}, у тебя это около {nf(amount)} ⭐. "
                                      f"Первый сбор через неделю. Зайди в игру, и его не будет."))
                continue
            if t - w["ts"] < WARN_AHEAD:
                continue
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, u["id"]))
            event(u["id"], "idletax", -amount)
            db.execute("INSERT INTO idletax(week,user,amount,ts) VALUES(?,?,?,?)", (week, u["id"], amount, t))
        db.execute("INSERT INTO idletax(week,user,amount,ts) VALUES(?,0,0,?)", (week, t))
    for u, text in msgs:
        notify(u, text)
    if msgs:
        print(f"idletax: week {week}, first-time {len(msgs)}", flush=True)


def public():
    last = q1("SELECT MAX(week) w FROM idletax WHERE user=0")["w"] or 0
    r = q1("SELECT COALESCE(SUM(amount),0) s, COUNT(*) n FROM idletax WHERE week=? AND user>0", last)
    tot = q1("SELECT COALESCE(SUM(amount),0) s FROM idletax WHERE user>0")["s"]
    return {"on": ON, "floor": FLOOR, "rate": RATE, "idleDays": IDLE // 86400, "lastWeek": r["s"], "lastWeekN": r["n"], "total": tot}


async def _loop():
    await asyncio.sleep(70)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _run)
        except Exception as e:
            print("idletax:", e, flush=True)
        await asyncio.sleep(1800)


@A.app.on_event("startup")
async def _start():
    if not A.DEV:
        asyncio.create_task(_loop())
