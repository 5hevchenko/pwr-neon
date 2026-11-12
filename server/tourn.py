"""Турниры: два турнира по разным играм, каждые PERIOD дней (с 2026-10-12 — раз в 3 дня, до этого были недельные).
Счёт — чистый выигрыш в игре за турнир. Призовой фонд от банка казино, топ-5 делят по долям; итоги — автоматически
в начале следующего. Ключ турнира (колонка week) — время его начала."""
from settings import conf
import asyncio
import json

from fastapi import Depends

import app as A
from app import R, app, auth, db, esc, event, notify, now, q, q1, tx, user_brief

ROTATION = [("dogs", "crash"), ("chicken", "avia"), ("slots", "mines"), ("dice", "tower"), ("battle", "scratch")]
NAMES = {"dogs": "Пёсики", "crash": "Краш", "chicken": "Курица", "avia": "Самолётик", "slots": "Слоты", "mines": "Мины",
         "dice": "Кубик", "tower": "Башня", "battle": "Битва кейсов", "scratch": "Скретч-карты"}
POOL = conf("tourn.pool", 100_000)
SHARES = [.40, .25, .15, .12, .08]
WEEK = 7 * 86400
PERIOD = int(conf("tourn.days", 3)) * 86400
ANCHOR = 1791763200   # пн 12.10.2026 00:00 UTC — начало последнего недельного турнира, от него идут 3-дневные
ROT0 = (ANCHOR // WEEK) % len(ROTATION)   # первый 3-дневный турнир — с теми же играми, что шли на этой неделе


def period_start(t=None):
    t = now() if t is None else t
    return ANCHOR + (t - ANCHOR) // PERIOD * PERIOD

db.executescript("CREATE TABLE IF NOT EXISTS tourn_results(week INTEGER, game TEXT, result TEXT, ts INTEGER, PRIMARY KEY(week, game));")


def games_of(ps):
    if ps < ANCHOR:   # старые недельные — для архива
        return ROTATION[(ps // WEEK) % len(ROTATION)]
    return ROTATION[(ROT0 + (ps - ANCHOR) // PERIOD) % len(ROTATION)]


def standings(game, ws, limit=10):
    return q("SELECT user, SUM(delta) s FROM events WHERE kind=? AND ts>=? AND ts<? GROUP BY user HAVING s>0 ORDER BY s DESC LIMIT ?",
             game, max(ws, A.season_from()), ws + PERIOD, limit)


@app.get(R + "/tournaments")
def tournaments(uid=Depends(auth)):
    ws = period_start()
    items = []
    for g in games_of(ws):
        rows = standings(g, ws)
        top = []
        for i, r in enumerate(rows):
            u = q1("SELECT * FROM users WHERE id=?", r["user"])
            if u:
                top.append({**user_brief(u), "score": r["s"], "prize": A.prize_k(POOL * SHARES[i]) if i < len(SHARES) else 0})
        me = q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind=? AND user=? AND ts>=?", g, uid, max(ws, A.season_from()))["s"]
        place = next((i + 1 for i, r in enumerate(standings(g, ws, 1000)) if r["user"] == uid), None)
        items.append({"game": g, "title": NAMES[g], "pool": A.prize_k(POOL), "top": top, "me": {"score": me, "place": place}})
    last = [dict(r) | {"result": json.loads(r["result"])} for r in q("SELECT * FROM tourn_results ORDER BY week DESC, game LIMIT 2")]
    nxt = games_of(ws + PERIOD)
    return {"items": items, "weekEnds": ws + PERIOD, "days": PERIOD // 86400, "shares": SHARES, "last": last, "next": [NAMES[g] for g in nxt]}


def _settle():
    prev = period_start() - PERIOD
    if prev < ANCHOR:   # последняя неделя до перехода уже подведена старым кодом
        return
    msgs = []
    with tx():
        for g in games_of(prev):
            if q1("SELECT 1 FROM tourn_results WHERE week=? AND game=?", prev, g):
                continue
            res = []
            for i, r in enumerate(standings(g, prev, len(SHARES))):
                prize = A.prize_k(POOL * SHARES[i])
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (prize, r["user"]))
                event(r["user"], "tourn", prize)
                u = q1("SELECT name FROM users WHERE id=?", r["user"])
                res.append({"place": i + 1, "user": r["user"], "name": u["name"] if u else "?", "score": r["s"], "prize": prize})
                msgs.append((r["user"], f"🏆 Турнир «{esc(NAMES[g])}»: ты на {i + 1} месте! Приз ⭐ {prize:,}".replace(",", " ")))
            db.execute("INSERT INTO tourn_results(week,game,result,ts) VALUES(?,?,?,?)", (prev, g, json.dumps(res, ensure_ascii=False), now()))
    for u, t in msgs:
        notify(u, t)


async def tourn_loop():
    await asyncio.sleep(40)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _settle)
        except Exception as e:
            print("tourn:", e, flush=True)
        await asyncio.sleep(900)


@app.on_event("startup")
async def _tourn_start():
    asyncio.create_task(tourn_loop())
