"""Набор недели: кланы соревнуются, кто приведёт больше новых игроков.
Очко клану — за участника, который вступил в клан на этой неделе, завёл аккаунт не раньше чем за 3 дня до вступления
(старых игроков перетаскивать бессмысленно) и дорос до 5 уровня (против твинков). Считаются только те, кто остался в клане.
Призы топ-3 идут в казну клана (и тратимую часть, и счёт уровня), минимум 2 новичка."""
import asyncio
import json

from fastapi import Depends

import app as A
from app import R, app, auth, db, esc, event, notify, now, q, q1, tx, week_start
from settings import conf

LEVEL = 5
FRESH = 3 * 86400
MIN_NEW = 2
BASE = conf("clans.recruit_prizes", [30_000, 15_000, 7_500])

db.executescript("CREATE TABLE IF NOT EXISTS clan_recruit(week INTEGER PRIMARY KEY, result TEXT, ts INTEGER);")


def prizes():
    return [A.prize_k(p) for p in BASE]


def _xp(level):
    return 100 * (level - 1) ** 2


def scores(ws):
    """[(clan, n)] за неделю, начиная с ws, по убыванию."""
    rows = q("""SELECT m.clan, COUNT(*) n FROM clan_members m JOIN users u ON u.id=m.user
                WHERE m.joined>=? AND m.joined<? AND u.created>=m.joined-? AND u.xp>=? AND u.banned=0
                GROUP BY m.clan ORDER BY n DESC, MIN(m.joined)""", ws, ws + 7 * 86400, FRESH, _xp(LEVEL))
    return [(r["clan"], r["n"]) for r in rows]


def _settle():
    week = week_start() - 7 * 86400
    if q1("SELECT 1 FROM clan_recruit WHERE week=?", week):
        return
    msgs, out, pz = [], [], prizes()
    with tx():
        if q1("SELECT 1 FROM clan_recruit WHERE week=?", week):
            return
        place = 0
        for cid, n in scores(week):
            if place >= len(pz) or n < MIN_NEW:
                break
            c = q1("SELECT * FROM clans WHERE id=?", cid)
            if not c:
                continue
            prize = pz[place]
            place += 1
            db.execute("UPDATE clans SET bank=bank+?, treasury=treasury+? WHERE id=?", (prize, prize, cid))
            event(0, "clanrecruit", prize)
            out.append({"place": place, "id": cid, "tag": c["tag"], "name": c["name"], "n": n, "prize": prize})
            for m in q("SELECT user FROM clan_members WHERE clan=?", cid):
                msgs.append((m["user"], f"Клан [{esc(c['tag'])}] занял {place} место в наборе недели: {n} новых игроков. В казну +{prize:,} ⭐".replace(",", " ")))
        db.execute("INSERT INTO clan_recruit(week,result,ts) VALUES(?,?,?)", (week, json.dumps(out, ensure_ascii=False), now()))
    for u, t in msgs:
        notify(u, t)


@app.get(R + "/clans-recruit")
def recruit(uid=Depends(auth)):
    ws = week_start()
    top, sc = [], scores(ws)
    for cid, n in sc[:5]:
        c = q1("SELECT id, tag, name, color, treasury FROM clans WHERE id=?", cid)
        if c:
            top.append({"id": c["id"], "tag": c["tag"], "name": c["name"], "color": c["color"], "level": __import__("clans").clan_level(c["treasury"]), "n": n})
    mine = q1("SELECT clan FROM clan_members WHERE user=?", uid)
    my = next((n for cid, n in sc if mine and cid == mine["clan"]), 0)
    last = q1("SELECT result FROM clan_recruit ORDER BY week DESC LIMIT 1")
    return {"top": top, "mine": my, "inClan": bool(mine), "prizes": prizes(), "min": MIN_NEW, "level": LEVEL, "left": ws + 7 * 86400 - now(),
            "last": json.loads(last["result"]) if last else []}


async def _loop():
    await asyncio.sleep(55)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _settle)
        except Exception as e:
            print("recruit:", e, flush=True)
        await asyncio.sleep(600)


@app.on_event("startup")
async def _start():
    if not A.DEV:
        asyncio.create_task(_loop())
