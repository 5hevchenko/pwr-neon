"""Битва кейсов: 2–4 участника открывают одинаковые кейсы (1–5 раундов), у кого сумма подарков больше — забирает ВСЕ подарки.
Свободные места создатель может отдать боту казино: бот не платит, его подарки достаются победителю-игроку;
если побеждает бот, подарки участников остаются у казино. Матожидание игрока = обычное открытие кейса."""
import asyncio
import json
import random

from fastapi import Depends, Request

import economy as E
from app import (R, add_xp, app, auth, bal, case_price, db, err, esc, event, gift_out, notify, now, q, q1, tx, user_brief)

db.executescript("""
CREATE TABLE IF NOT EXISTS battles(id INTEGER PRIMARY KEY, host INTEGER, cid TEXT, rounds INTEGER, slots INTEGER, price INTEGER,
  players TEXT, status TEXT DEFAULT 'waiting', result TEXT, ts INTEGER, done INTEGER);
CREATE INDEX IF NOT EXISTS battles_status ON battles(status);
""")
ROUNDS = (1, 2, 3, 5)
SLOTS = (2, 3, 4)
WAIT_TTL = 30 * 60       # ждём соперников 30 минут, потом возврат
BOT = 0


def _b(bid):
    b = q1("SELECT * FROM battles WHERE id=?", bid) or err("битва не найдена", 404)
    b = dict(b)
    b["players"] = json.loads(b["players"])
    b["result"] = json.loads(b["result"]) if b["result"] else None
    return b


def _save(b):
    db.execute("UPDATE battles SET players=?, status=?, result=?, done=? WHERE id=?",
               (json.dumps(b["players"]), b["status"], json.dumps(b["result"]) if b["result"] else None, b.get("done"), b["id"]))


def _pl(uid):
    if uid == BOT:
        return {"id": 0, "name": "Бот", "bot": True, "level": 0}
    u = q1("SELECT * FROM users WHERE id=?", uid)
    return user_brief(u) if u else {"id": uid, "name": "?", "level": 0}


def _out(b, uid=None):
    c = E.CASES[b["cid"]]
    o = {"id": b["id"], "host": b["host"], "cid": b["cid"], "case": {"id": c["id"], "title": E.case_title(c["id"], uid), "cover": E.case_cover(c["id"], uid)},
         "rounds": b["rounds"], "slots": b["slots"], "price": b["price"], "cost": b["price"] * b["rounds"],
         "players": [_pl(p) if p is not None else None for p in b["players"]], "status": b["status"], "ts": b["ts"],
         "mine": uid in b["players"] if uid else False}
    if b["result"]:
        o["result"] = b["result"]
    return o


def _resolve(b):
    """Все места заняты: каждый открывает rounds кейсов, победитель забирает всё (внутри tx)."""
    cost = b["price"] * b["rounds"]
    import fair
    rng = fair.pub("battle", str(b["id"]))
    drops = []                         # drops[slot] = [подарок за каждый раунд]
    for _ in b["players"]:
        drops.append([E.open_case(b["cid"], rng) for _ in range(b["rounds"])])
    totals = [sum(d["value"] for d in ds) for ds in drops]
    top = max(totals)
    win_slot = rng.choice([i for i, t in enumerate(totals) if t == top])
    fair.close_pub(rng, {"totals": totals, "win": win_slot})
    winner = b["players"][win_slot]
    t = now()
    out_drops = []
    for i, ds in enumerate(drops):
        row = []
        for d in ds:
            gid = None
            if winner != BOT:            # все подарки битвы — победителю
                cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                                 (winner, d["col"], d["model"], d["backdrop"], d["symbol"], d["num"], d["value"], t))
                gid = cur.lastrowid
            row.append({"id": gid, **{k: d[k] for k in ("col", "model", "backdrop", "symbol", "num", "value")}})
        out_drops.append(row)
    total_all = sum(totals)
    for p in b["players"]:
        if p != BOT:
            event(p, "battle", (total_all if p == winner else 0) - cost, stake=cost)
            add_xp(p, max(20, cost // 10))
    if winner != BOT:
        best = max((g for row in out_drops for g in row), key=lambda g: g["value"])
        db.execute("INSERT INTO feed(user,gift,cs,ts) VALUES(?,?,?,?)", (winner, best["id"], "battle", t))
    b["status"], b["done"] = "done", t
    b["result"] = {"drops": out_drops, "totals": totals, "winSlot": win_slot, "winner": winner, "total": total_all}
    _save(b)
    return winner, total_all


def _gift_preview(d):
    """Данные для отрисовки подарка (как gift_out, но без строки в базе)."""
    from app import LOOK, BACKDROPS
    ml, bl, sl = LOOK[d["col"]]
    bd = bl.get(d["backdrop"]) or BACKDROPS.get(d["backdrop"])
    return {**d, "mp": ml.get(d["model"], 0), "bp": bd[1], "sp": sl.get(d["symbol"], 0), "c": bd[2:6], "price": None}


@app.get(R + "/battles")
def battles(uid=Depends(auth)):
    opn = [_out(_b(r["id"]), uid) for r in q("SELECT id FROM battles WHERE status='waiting' ORDER BY id DESC LIMIT 30")]
    mine = [_out(_b(r["id"]), uid) for r in q("SELECT id FROM battles WHERE status='done' AND players LIKE ? ORDER BY id DESC LIMIT 8", f"%{uid}%")]
    mine = [m for m in mine if m["mine"]][:5]
    cases = [{"id": c["id"], "title": E.case_title(c["id"], uid), "cover": E.case_cover(c["id"], uid), "price": case_price(c), "level": c["level"]}
             for c in E.CASES.values() if c["price"] and c["id"] not in E.LIMITED]
    cases.sort(key=lambda c: c["price"])
    return {"open": opn, "mine": mine, "cases": cases, "rounds": ROUNDS, "slots": SLOTS, "stars": bal(uid)}


@app.get(R + "/battles/{bid}")
def battle(bid: int, uid=Depends(auth)):
    b = _b(bid)
    o = _out(b, uid)
    if b["result"]:
        o["result"] = {**b["result"], "drops": [[_gift_preview(g) for g in row] for row in b["result"]["drops"]]}
    return o


@app.post(R + "/battles")
async def battle_new(req: Request, uid=Depends(auth)):
    from app import _pvp_guard
    _pvp_guard(uid)
    bd = await req.json()
    cid, rounds, slots = str(bd.get("cid", "")), int(bd.get("rounds", 1)), int(bd.get("slots", 2))
    c = E.CASES.get(cid) if cid not in E.LIMITED else None
    if not c or not c["price"]:
        err("выбери платный кейс")
    if rounds not in ROUNDS or slots not in SLOTS:
        err("неверные параметры")
    price = case_price(c)
    cost = price * rounds
    with tx():
        if q1("SELECT COUNT(*) n FROM battles WHERE host=? AND status='waiting'", uid)["n"] >= 3:
            err("не больше 3 открытых битв")
        if bal(uid) < cost:
            err(f"Нужно ⭐ {cost}")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (cost, uid))
        players = [uid] + [None] * (slots - 1)
        cur = db.execute("INSERT INTO battles(host,cid,rounds,slots,price,players,ts) VALUES(?,?,?,?,?,?,?)",
                         (uid, cid, rounds, slots, price, json.dumps(players), now()))
    return {"id": cur.lastrowid, "stars": bal(uid)}


def _fill(b, who):
    i = b["players"].index(None)
    b["players"][i] = who
    if None not in b["players"]:
        return _resolve(b)
    _save(b)
    return None


def _notify_done(b, res):
    if not res:
        return
    winner, total = res
    wname = _pl(winner)["name"]
    for p in set(b["players"]):
        if p and p != b.get("_actor"):
            notify(p, f"⚔️ Битва кейсов «{esc(E.case_title(b['cid'], p))}» завершена — "
                      + ("ты победил и забрал всё! " if p == winner else f"победил <b>{esc(wname)}</b>. ")
                      + f"Банк битвы ⭐ {total}")


@app.post(R + "/battles/{bid}/join")
def battle_join(bid: int, uid=Depends(auth)):
    from app import _pvp_guard
    _pvp_guard(uid)
    with tx():
        b = _b(bid)
        if b["status"] != "waiting":
            err("битва уже началась")
        if uid in b["players"]:
            err("ты уже в этой битве")
        cost = b["price"] * b["rounds"]
        if bal(uid) < cost:
            err(f"Нужно ⭐ {cost}")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (cost, uid))
        res = _fill(b, uid)
    b["_actor"] = uid
    _notify_done(b, res)
    return {"ok": True, "done": bool(res), "stars": bal(uid)}


@app.post(R + "/battles/{bid}/bot")
def battle_bot(bid: int, uid=Depends(auth)):
    """Создатель отдаёт свободные места ботам казино — битва начинается сразу."""
    with tx():
        b = _b(bid)
        if b["host"] != uid or b["status"] != "waiting":
            err("ботов добавляет создатель до начала")
        res = None
        while None in b["players"]:
            res = _fill(b, BOT)
    b["_actor"] = uid
    _notify_done(b, res)
    return {"ok": True, "done": bool(res), "stars": bal(uid)}


@app.post(R + "/battles/{bid}/cancel")
def battle_cancel(bid: int, uid=Depends(auth)):
    with tx():
        b = _b(bid)
        if b["host"] != uid or b["status"] != "waiting":
            err("отменить может создатель до начала")
        _refund(b)
    return {"ok": True, "stars": bal(uid)}


def _refund(b):
    for p in b["players"]:
        if p:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (b["price"] * b["rounds"], p))
    b["status"], b["done"] = "cancelled", now()
    _save(b)


def _expire():
    for r in q("SELECT id FROM battles WHERE status='waiting' AND ts<?", now() - WAIT_TTL):
        with tx():
            b = _b(r["id"])
            if b["status"] == "waiting":
                _refund(b)
                for p in b["players"]:
                    if p:
                        notify(p, "⚔️ Соперники не нашлись за 30 минут — ставка за битву кейсов возвращена")


async def battles_loop():
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _expire)
        except Exception as e:
            print("battles:", e, flush=True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _battles_start():
    asyncio.create_task(battles_loop())
