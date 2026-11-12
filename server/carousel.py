"""Карусель: большое колесо, общий раунд на всех. Ставки на секторы: четыре множителя и три бонуса.

Честность: сиды раундов — своя цепочка хэшей, как в краше: вершина опубликована заранее, sha256(сид раунда) = сид прошлого раунда.
Вероятности заданы так, чтобы каждый сектор возвращал одинаковый заявленный процент. Бонусы устроены так, что любой выбор
игрока даёт одно и то же матожидание: выбор меняет только риск, поэтому лучшей стратегии против банка нет.
"""
import asyncio
import hashlib
import hmac as hmac_mod
import json
import secrets
import time

from fastapi import Depends, Request

import fair
from app import R, add_xp, app, auth, bal, check_bet, db, err, event, now, q, q1, tx, user_brief
from settings import conf, tuned

db.executescript("""
CREATE TABLE IF NOT EXISTS cr_chain(id INTEGER PRIMARY KEY AUTOINCREMENT, master TEXT, commit_hash TEXT, size INTEGER, pos INTEGER DEFAULT 0, marks TEXT, created INTEGER);
CREATE TABLE IF NOT EXISTS cr_round(chain INTEGER, pos INTEGER, seed TEXT, sector TEXT, bonus TEXT, rtp REAL, ts INTEGER, PRIMARY KEY(chain, pos));
CREATE TABLE IF NOT EXISTS cr_bet(id INTEGER PRIMARY KEY AUTOINCREMENT, round INTEGER, user INTEGER, sector TEXT, amount INTEGER, choice INTEGER);
CREATE INDEX IF NOT EXISTS cr_bet_round ON cr_bet(round);
""")

BET_TIME, SPIN_TIME, BONUS_TIME, SHOW_TIME = 15, 6, 12, 6
CHAIN_SIZE, CHAIN_MARK = 200_000, 1000
MULTS = {"x2": 2.5, "x4": 4, "x8": 8, "x16": 16}
BONUS_SHARE = {"safe": 0.42, "ladder": 0.33, "bomb": 0.25}
TITLES = {"x2": "×2,5", "x4": "×4", "x8": "×8", "x16": "×16", "safe": "Сейф", "ladder": "Лестница", "bomb": "Бомба"}
ORDER = ["x2", "x4", "x8", "x16", "safe", "ladder", "bomb"]
MAX_BET = conf("games.carousel_max", 200_000)
LADDER_P = 0.7
LADDER_MAX = 6
SAFE_RATIO = 5   # угаданная цифра платит в 5 раз больше неугаданной

ST = {"phase": "bet", "until": 0.0, "round": 0, "chain": 0, "seed": "", "hash": "", "sector": None, "bonus": None, "weights": None, "rtp": 0.94, "history": [], "paid": {}}
_CH = {"id": 0, "marks": [], "size": 0, "pos": 0, "commit": ""}


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _u(seed, tag):
    return int(hmac_mod.new(seed.encode(), tag.encode(), hashlib.sha256).hexdigest()[:15], 16) / 16 ** 15


def weights(rtp):
    """Вероятность сектора = возврат ÷ множитель. Остаток делят бонусы, и у них тот же возврат."""
    w = {k: rtp / m for k, m in MULTS.items()}
    left = 1 - sum(w.values())
    w.update({k: left * s for k, s in BONUS_SHARE.items()})
    return w


def bonus_value(sector, rtp):
    return rtp / weights(rtp)[sector]   # сколько бонус возвращает на единицу ставки в среднем


def spin(seed, rtp):
    w = weights(rtp)
    return ORDER[fair.pick(_u(seed, "wheel"), [w[k] for k in ORDER])]


def bonus_outcome(sector, seed):
    if sector == "safe":
        return {"digit": fair.idx(_u(seed, "bonus:0"), 10)}
    if sector == "ladder":
        top = 0
        while top < LADDER_MAX and _u(seed, f"bonus:{top}") < LADDER_P:
            top += 1
        return {"top": top}
    if sector == "bomb":
        return {"at": 1 + fair.idx(_u(seed, "bonus:0"), 10)}
    return None


def bonus_pay_k(sector, rtp, choice, out):
    """Выплата на единицу ставки. Матожидание равно bonus_value при любом choice."""
    e = bonus_value(sector, rtp)
    if sector == "safe":
        lo = e / (0.1 * SAFE_RATIO + 0.9)
        return lo * SAFE_RATIO if choice == out["digit"] else lo
    if sector == "ladder":
        k = max(1, min(LADDER_MAX, choice or 1))
        return e / LADDER_P ** k if out["top"] >= k else 0
    if sector == "bomb":
        k = max(1, min(9, choice or 1))
        return e / (1 - k / 10) if out["at"] > k else 0
    return 0


def _chain_load():
    r = q1("SELECT * FROM cr_chain ORDER BY id DESC LIMIT 1")
    if not r or r["pos"] >= r["size"] - 1:
        master = secrets.token_hex(32)
        marks, cur = [], master
        for i in range(CHAIN_SIZE):
            if i % CHAIN_MARK == 0:
                marks.append(cur)
            cur = _sha(cur)
        with tx():
            rid = db.execute("INSERT INTO cr_chain(master,commit_hash,size,pos,marks,created) VALUES(?,?,?,0,?,?)", (master, cur, CHAIN_SIZE, json.dumps(marks), now())).lastrowid
        r = q1("SELECT * FROM cr_chain WHERE id=?", rid)
    _CH.update(id=r["id"], marks=json.loads(r["marks"]), size=r["size"], pos=r["pos"], commit=r["commit_hash"])


def _next_seed():
    if not _CH["id"] or _CH["pos"] >= _CH["size"] - 1:
        _chain_load()
    _CH["pos"] += 1
    db.execute("UPDATE cr_chain SET pos=? WHERE id=?", (_CH["pos"], _CH["id"]))
    times = _CH["size"] - _CH["pos"]
    j = times // CHAIN_MARK
    cur = _CH["marks"][j]
    for _ in range(times - j * CHAIN_MARK):
        cur = _sha(cur)
    return cur


def _refund_stale():
    """После перезапуска незакрытые ставки возвращаются: раунд, на который они сделаны, уже не состоится."""
    with tx():
        for b in q("SELECT * FROM cr_bet"):
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (b["amount"], b["user"]))
        db.execute("DELETE FROM cr_bet")


def _settle():
    rid, sector, rtp, seed = ST["round"], ST["sector"], ST["rtp"], ST["seed"]
    out = ST["bonus"]
    paid = {}
    with tx():
        users = {}
        for b in q("SELECT * FROM cr_bet WHERE round=?", rid):
            k = 0
            if b["sector"] == sector:
                k = MULTS[sector] if sector in MULTS else bonus_pay_k(sector, rtp, b["choice"], out)
            u = users.setdefault(b["user"], [0, 0])
            u[0] += b["amount"]
            u[1] += int(b["amount"] * k)
        for uid, (stake, pay) in users.items():
            if pay:
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
            event(uid, "carousel", pay - stake, stake=stake)
            paid[uid] = pay - stake
        db.execute("DELETE FROM cr_bet WHERE round=?", (rid,))
        db.execute("INSERT OR REPLACE INTO cr_round(chain,pos,seed,sector,bonus,rtp,ts) VALUES(?,?,?,?,?,?,?)",
                   (ST["chain"], rid, seed, sector, json.dumps(out) if out else None, rtp, now()))
        db.execute("DELETE FROM cr_round WHERE ts<?", (now() - 14 * 86400,))
    ST["paid"] = paid


async def _loop():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _chain_load)
    await loop.run_in_executor(None, _refund_stale)
    while True:
        try:
            seed = await loop.run_in_executor(None, _next_seed)
            rtp = tuned("games.carousel_rtp", 0.94)
            ST.update(phase="bet", until=time.time() + BET_TIME, round=_CH["pos"], chain=_CH["id"], seed=seed, hash=_sha(seed), rtp=rtp, sector=None, bonus=None, paid={},
                      weights=weights(rtp))
            await asyncio.sleep(BET_TIME)
            sector = spin(seed, rtp)
            ST.update(phase="spin", until=time.time() + SPIN_TIME, sector=sector)
            await asyncio.sleep(SPIN_TIME)
            if sector in BONUS_SHARE:
                ST.update(phase="bonus", until=time.time() + BONUS_TIME)
                await asyncio.sleep(BONUS_TIME)
                ST["bonus"] = bonus_outcome(sector, seed)
            await loop.run_in_executor(None, _settle)
            ST["history"] = ([{"round": ST["round"], "sector": sector}] + ST["history"])[:14]
            ST.update(phase="show", until=time.time() + SHOW_TIME)
            await asyncio.sleep(SHOW_TIME)
        except Exception as e:
            print("carousel:", e, flush=True)
            await asyncio.sleep(3)


@app.on_event("startup")
async def _start():
    asyncio.create_task(_loop())


@app.get(R + "/carousel")
def state(uid=Depends(auth)):
    p = ST["phase"]
    mine = q("SELECT sector, SUM(amount) a, MAX(choice) c FROM cr_bet WHERE round=? AND user=? GROUP BY sector", ST["round"], uid)
    pools = {r["sector"]: r["a"] for r in q("SELECT sector, SUM(amount) a FROM cr_bet WHERE round=? GROUP BY sector", ST["round"])}
    w = ST["weights"] or weights(tuned("games.carousel_rtp", 0.94))
    return {"phase": p, "now": time.time(), "until": ST["until"], "round": ST["round"], "hash": ST["hash"], "seed": ST["seed"] if p == "show" else None,
            "sector": ST["sector"] if p != "bet" else None, "bonus": ST["bonus"], "history": ST["history"], "players": q1("SELECT COUNT(DISTINCT user) n FROM cr_bet WHERE round=?", ST["round"])["n"],
            "mine": {r["sector"]: r["a"] for r in mine}, "choice": next((r["c"] for r in mine if r["c"] is not None), None), "pools": pools, "delta": ST["paid"].get(uid) if p == "show" else None,
            "sectors": [{"id": k, "title": TITLES[k], "p": round(w[k] * 100, 2), "mult": MULTS.get(k)} for k in ORDER],
            "bonusK": {k: round(bonus_value(k, ST["rtp"]), 2) for k in BONUS_SHARE}, "ladderP": LADDER_P, "ladderMax": LADDER_MAX, "max": MAX_BET,
            "bonusTable": {"safe": round(bonus_value("safe", ST["rtp"]) / (0.1 * SAFE_RATIO + 0.9), 2), "ratio": SAFE_RATIO}}


@app.post(R + "/carousel/bet")
async def bet(req: Request, uid=Depends(auth)):
    b = await req.json()
    sector, amount = str(b.get("sector", "")), int(b.get("amount", 0))
    if sector not in ORDER:
        err("нет такого сектора")
    if ST["phase"] != "bet" or time.time() > ST["until"] - 0.3:
        err("ставки закрыты — дождись следующего раунда")
    with tx():
        check_bet(uid, amount, 10, MAX_BET)
        total = q1("SELECT COALESCE(SUM(amount),0) s FROM cr_bet WHERE round=? AND user=?", ST["round"], uid)["s"]
        if total + amount > MAX_BET:
            err(f"на раунд не больше ⭐ {MAX_BET:,}".replace(",", " "))
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        db.execute("INSERT INTO cr_bet(round,user,sector,amount) VALUES(?,?,?,?)", (ST["round"], uid, sector, amount))
        lvl = add_xp(uid, max(1, amount // 20))
    return {**state(uid), "stars": bal(uid), "levelup": lvl}


@app.post(R + "/carousel/choice")
async def choice(req: Request, uid=Depends(auth)):
    v = int((await req.json()).get("value", -1))
    s = ST["sector"]
    if ST["phase"] != "bonus" or s not in BONUS_SHARE:
        err("сейчас выбирать нечего")
    if not ((s == "safe" and 0 <= v <= 9) or (s == "ladder" and 1 <= v <= LADDER_MAX) or (s == "bomb" and 1 <= v <= 9)):
        err("Неверные данные — обнови экран")
    with tx():
        if not q1("SELECT 1 FROM cr_bet WHERE round=? AND user=? AND sector=?", ST["round"], uid, s):
            err("ты не ставил на этот бонус")
        db.execute("UPDATE cr_bet SET choice=? WHERE round=? AND user=? AND sector=?", (v, ST["round"], uid, s))
    return state(uid)


@app.get(R + "/fair/carousel")
def rounds(limit: int = 30):
    rows = q("SELECT * FROM cr_round WHERE chain=? ORDER BY pos DESC LIMIT ?", _CH["id"], max(1, min(100, limit)))
    return {"commit": _CH["commit"], "pos": _CH["pos"], "size": _CH["size"], "items": [{**dict(r), "weights": [weights(r["rtp"])[k] for k in ORDER], "order": ORDER} for r in rows]}
