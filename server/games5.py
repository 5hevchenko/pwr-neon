"""Сейф, ставка на банк, аукцион банка, бизнесы клана.

Сейф: код из 3 цифр, 5 попыток, после каждой видно, какие позиции угаданы. Лучшая стратегия — на каждой неугаданной
позиции пробовать новую цифру, тогда P(открыть за k попыток) = (k/10)^3. Лучше сыграть нельзя, поэтому таблица выплат
считается точно и не зависит от умения игрока. 2% ставки копится в общем фонде, его забирает открывший за 1–2 попытки.

Ставка на банк: тотализатор. Вырастет банк за следующий час или упадёт. Банк не рискует: победители делят ставки
проигравших, банк берёт комиссию. Изменение считается без операций самих участников раунда, иначе итог можно подкрутить.

Аукцион: подарки из хранилища банка. Деньги победителя идут в банк.
"""
import asyncio
import json
import time

from fastapi import Depends, Request

import fair
from app import R, add_xp, app, auth, bal, check_bet, db, err, event, gift_out, notify, now, q, q1, tx
from settings import conf, tuned

db.executescript("""
CREATE TABLE IF NOT EXISTS safe_game(user INTEGER PRIMARY KEY, bet INTEGER, code TEXT, tries TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS bb_bet(id INTEGER PRIMARY KEY AUTOINCREMENT, hour INTEGER, user INTEGER, side TEXT, amount INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS bb_bet_hour ON bb_bet(hour);
CREATE TABLE IF NOT EXISTS bb_round(hour INTEGER PRIMARY KEY, net INTEGER, side TEXT, up INTEGER, down INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS auction(id INTEGER PRIMARY KEY AUTOINCREMENT, gift TEXT, value INTEGER, ends INTEGER, top_user INTEGER, top_bid INTEGER DEFAULT 0, done INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS clan_biz(clan INTEGER, bid TEXT, level INTEGER, ts INTEGER, PRIMARY KEY(clan, bid));
""")
fair.HOLD_TABLES = (*fair.HOLD_TABLES, "safe_game")

# ---------------- сейф ----------------
SAFE_TRIES = 5
SAFE_SHAPE = [200, 60, 20, 8, 4]
SAFE_POT = 0.02


def safe_chance(k):
    return (k / 10) ** 3 - ((k - 1) / 10) ** 3


def safe_mults():
    """Выплаты под заявленный возврат. 2% ставки отдельно копятся в фонде и тоже возвращаются игрокам."""
    rtp = tuned("games.safe_rtp", 0.94) - SAFE_POT
    c = rtp / sum(safe_chance(k) * SAFE_SHAPE[k - 1] for k in range(1, SAFE_TRIES + 1))
    return [round(x * c, 2) for x in SAFE_SHAPE]


def _pot():
    r = q1("SELECT v FROM kv WHERE k='safe_pot'")
    return int(r["v"]) if r else 0


def _set_pot(v):
    db.execute("INSERT INTO kv(k,v) VALUES('safe_pot',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(int(v)),))


def _safe_view(r, reveal=False):
    tries = json.loads(r["tries"])
    out = {"active": True, "bet": r["bet"], "tries": tries, "left": SAFE_TRIES - len(tries), "mults": safe_mults(), "pot": _pot()}
    if reveal:
        out.update(active=False, code=r["code"])
    return out


@app.get(R + "/safe")
def safe_state(uid=Depends(auth)):
    r = q1("SELECT * FROM safe_game WHERE user=?", uid)
    return _safe_view(r) if r else {"active": False, "mults": safe_mults(), "pot": _pot(), "tries_max": SAFE_TRIES,
                                    "chances": [round(safe_chance(k) * 100, 2) for k in range(1, SAFE_TRIES + 1)]}


@app.post(R + "/safe/start")
async def safe_start(req: Request, uid=Depends(auth)):
    bet = int((await req.json()).get("bet", 0))
    with tx():
        if q1("SELECT 1 FROM safe_game WHERE user=?", uid):
            err("сначала доиграй текущий сейф")
        check_bet(uid, bet)
        rr, pf = fair.rolls(uid, "safe", "code", 3)
        code = "".join(str(fair.idx(x, 10)) for x in rr)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        _set_pot(_pot() + bet * SAFE_POT)
        db.execute("INSERT INTO safe_game VALUES(?,?,?,?,?)", (uid, bet, code, "[]", now()))
        lvl = add_xp(uid, max(1, bet // 20))
        r = q1("SELECT * FROM safe_game WHERE user=?", uid)
    return {**_safe_view(r), "stars": bal(uid), "levelup": lvl, "pf": pf}


@app.post(R + "/safe/try")
async def safe_try(req: Request, uid=Depends(auth)):
    code = str((await req.json()).get("code", ""))
    if len(code) != 3 or not code.isdigit():
        err("код — 3 цифры")
    with tx():
        r = q1("SELECT * FROM safe_game WHERE user=?", uid) or err("сейф не начат")
        tries = json.loads(r["tries"])
        marks = [int(a == b) for a, b in zip(code, r["code"])]
        tries.append({"code": code, "marks": marks})
        k = len(tries)
        won = code == r["code"]
        if not won and k < SAFE_TRIES:
            db.execute("UPDATE safe_game SET tries=? WHERE user=?", (json.dumps(tries), uid))
            return {**_safe_view(q1("SELECT * FROM safe_game WHERE user=?", uid)), "last": marks}
        pay, pot = 0, 0
        if won:
            pay = int(r["bet"] * safe_mults()[k - 1])
            if k <= 2:
                pot = _pot()
                _set_pot(0)
        db.execute("DELETE FROM safe_game WHERE user=?", (uid,))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay + pot, uid))
        event(uid, "safe", pay + pot - r["bet"], stake=r["bet"], res={"code": r["code"], "tries": k, "won": won})
        view = {**_safe_view(r, True), "tries": tries, "left": SAFE_TRIES - k}
    return {**view, "won": won, "pay": pay + pot, "potWon": pot, "last": marks, "stars": bal(uid)}


# ---------------- лестница ----------------
# 10 ступеней, на каждой две двери: за одной шаг вверх, за другой обрыв. Икс = возврат × 2^ступень.
# Подсказка показывает верную дверь и стоит 105% от суммы на кону: дешевле нельзя, иначе ей выгодно злоупотреблять.
LD_STEPS = 10
LD_HINT = 1.05
db.execute("CREATE TABLE IF NOT EXISTS ladder_game(user INTEGER PRIMARY KEY, bet INTEGER, doors TEXT, step INTEGER DEFAULT 0, hints INTEGER DEFAULT 0, ts INTEGER)")
fair.HOLD_TABLES = (*fair.HOLD_TABLES, "ladder_game")


def _ld_mult(k):
    return round(tuned("games.ladder_rtp", 0.94) * 2 ** k, 2) if k else 0


def _ld_stake(r):
    """Сколько сейчас на кону: на первой ступени — ставка, дальше — текущий выигрыш."""
    return int(r["bet"] * _ld_mult(r["step"])) if r["step"] else r["bet"]


def _ld_view(r, reveal=False):
    out = {"active": True, "bet": r["bet"], "step": r["step"], "steps": LD_STEPS, "mult": _ld_mult(r["step"]), "next": _ld_mult(r["step"] + 1),
           "hintCost": int(_ld_stake(r) * LD_HINT) + 1, "win": int(r["bet"] * _ld_mult(r["step"])),
           "mults": [_ld_mult(i) for i in range(1, LD_STEPS + 1)]}
    if reveal:
        out.update(active=False, doors=json.loads(r["doors"]))
    return out


@app.get(R + "/ladder")
def ladder_state(uid=Depends(auth)):
    r = q1("SELECT * FROM ladder_game WHERE user=?", uid)
    return _ld_view(r) if r else {"active": False, "step": 0, "steps": LD_STEPS, "mults": [_ld_mult(i) for i in range(1, LD_STEPS + 1)]}


@app.post(R + "/ladder/start")
async def ladder_start(req: Request, uid=Depends(auth)):
    bet = int((await req.json()).get("bet", 0))
    with tx():
        if q1("SELECT 1 FROM ladder_game WHERE user=?", uid):
            err("сначала доиграй текущую партию")
        check_bet(uid, bet)
        rr, pf = fair.rolls(uid, "ladder", "doors", LD_STEPS)
        doors = [fair.idx(x, 2) for x in rr]
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        db.execute("INSERT INTO ladder_game(user,bet,doors,step,hints,ts) VALUES(?,?,?,0,0,?)", (uid, bet, json.dumps(doors), now()))
        lvl = add_xp(uid, max(1, bet // 20))
        r = q1("SELECT * FROM ladder_game WHERE user=?", uid)
    return {**_ld_view(r), "stars": bal(uid), "levelup": lvl, "pf": pf}


def _ld_end(uid, r, pay):
    db.execute("DELETE FROM ladder_game WHERE user=?", (uid,))
    if pay:
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
    event(uid, "ladder", pay - r["bet"], stake=r["bet"], res={"doors": json.loads(r["doors"]), "step": r["step"]})


@app.post(R + "/ladder/pick")
async def ladder_pick(req: Request, uid=Depends(auth)):
    door = int((await req.json()).get("door", -1))
    if door not in (0, 1):
        err("выбери дверь")
    with tx():
        r = q1("SELECT * FROM ladder_game WHERE user=?", uid) or err("игра не начата")
        doors = json.loads(r["doors"])
        if doors[r["step"]] != door:
            _ld_end(uid, r, 0)
            return {**_ld_view(r, True), "lost": True, "door": door, "stars": bal(uid)}
        db.execute("UPDATE ladder_game SET step=step+1 WHERE user=?", (uid,))
        r = q1("SELECT * FROM ladder_game WHERE user=?", uid)
        if r["step"] >= LD_STEPS:
            pay = int(r["bet"] * _ld_mult(LD_STEPS))
            _ld_end(uid, r, pay)
            return {**_ld_view(r, True), "won": True, "pay": pay, "door": door, "stars": bal(uid)}
    return {**_ld_view(r), "door": door, "ok": True}


@app.post(R + "/ladder/hint")
def ladder_hint(uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM ladder_game WHERE user=?", uid) or err("игра не начата")
        cost = int(_ld_stake(r) * LD_HINT) + 1
        if bal(uid) < cost:
            err(f"Подсказка стоит ⭐ {cost:,}".replace(",", " "))
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (cost, uid))
        db.execute("UPDATE ladder_game SET hints=hints+1 WHERE user=?", (uid,))
        event(uid, "fee", -cost)
        d = json.loads(r["doors"])[r["step"]]
    return {"door": d, "cost": cost, "stars": bal(uid)}


@app.post(R + "/ladder/cashout")
def ladder_cashout(uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM ladder_game WHERE user=?", uid) or err("игра не начата")
        if not r["step"]:
            err("пройди хотя бы одну ступень")
        pay = int(r["bet"] * _ld_mult(r["step"]))
        _ld_end(uid, r, pay)
    return {**_ld_view(r, True), "won": True, "pay": pay, "stars": bal(uid)}


# ---------------- ставка на банк ----------------
BB_RAKE = conf("games.bankbet_rake", 0.08)
BB_MIN, BB_MAX = 100, conf("games.bankbet_max", 100_000)
HOUR = 3600


def _hour(t=None):
    return (t if t is not None else now()) // HOUR


def _bb_net(hour, skip):
    """Как изменился банк за этот час без операций участников раунда."""
    import bank
    ph = ",".join("?" * len(skip)) or "NULL"
    r = q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE ({bank.BANK_KINDS}) AND kind<>'bankbet' AND ts>=? AND ts<? AND user NOT IN ({ph})",
           hour * HOUR, (hour + 1) * HOUR, *skip)
    return -int(r["s"])


def _bb_settle(hour):
    bets = q("SELECT * FROM bb_bet WHERE hour=?", hour)
    users = sorted({b["user"] for b in bets})
    net = _bb_net(hour, users)
    up = sum(b["amount"] for b in bets if b["side"] == "up")
    down = sum(b["amount"] for b in bets if b["side"] == "down")
    side = "up" if net > 0 else "down" if net < 0 else None
    with tx():
        if q1("SELECT 1 FROM bb_round WHERE hour=?", hour):
            return
        db.execute("INSERT INTO bb_round(hour,net,side,up,down,ts) VALUES(?,?,?,?,?,?)", (hour, net, side, up, down, now()))
        win_pool = up if side == "up" else down if side == "down" else 0
        lose_pool = (down if side == "up" else up) if side else 0
        for b in bets:
            if not side or not win_pool or not lose_pool:   # ничья или нет соперников: ставка возвращается
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (b["amount"], b["user"]))
            elif b["side"] == side:
                pay = b["amount"] + int(b["amount"] / win_pool * lose_pool * (1 - BB_RAKE))
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, b["user"]))
                event(b["user"], "bankbet", pay - b["amount"], stake=b["amount"])
            else:
                event(b["user"], "bankbet", -b["amount"], stake=b["amount"])


async def _bb_loop():
    loop = asyncio.get_running_loop()
    while True:
        try:
            cur = _hour()
            for r in q("SELECT DISTINCT hour FROM bb_bet WHERE hour<? AND hour NOT IN (SELECT hour FROM bb_round)", cur):
                await loop.run_in_executor(None, _bb_settle, r["hour"])
            await loop.run_in_executor(None, _auction_tick)
        except Exception as e:
            print("games5 loop:", e, flush=True)
        await asyncio.sleep(30)


@app.on_event("startup")
async def _g5_start():
    asyncio.create_task(_bb_loop())


@app.get(R + "/bankbet")
def bb_state(uid=Depends(auth)):
    h = _hour() + 1   # ставки принимаются на следующий час: текущее движение банка уже известно
    pool = {r["side"]: r["s"] for r in q("SELECT side, SUM(amount) s FROM bb_bet WHERE hour=? GROUP BY side", h)}
    import bank
    return {"bank": bank.bank_value(), "netNow": _bb_net(_hour(), []), "hour": h, "startsIn": h * HOUR - now(), "up": pool.get("up", 0), "down": pool.get("down", 0), "rake": BB_RAKE, "min": BB_MIN, "max": BB_MAX,
            "mine": [dict(r) for r in q("SELECT hour, side, amount FROM bb_bet WHERE user=? AND hour>=? ORDER BY id DESC", uid, _hour())],
            "history": [dict(r) for r in q("SELECT hour, net, side, up, down FROM bb_round ORDER BY hour DESC LIMIT 12")]}


@app.post(R + "/bankbet")
async def bb_bet(req: Request, uid=Depends(auth)):
    b = await req.json()
    side, amount = str(b.get("side", "")), int(b.get("amount", 0))
    if side not in ("up", "down"):
        err("выбери: вырастет или упадёт")
    h = _hour() + 1
    with tx():
        check_bet(uid, amount, BB_MIN, BB_MAX)
        if q1("SELECT 1 FROM bb_bet WHERE hour=? AND user=? AND side<>?", h, uid, side):
            err("в этом раунде ты уже поставил на другой исход")
        mine = q1("SELECT COALESCE(SUM(amount),0) s FROM bb_bet WHERE hour=? AND user=?", h, uid)["s"]
        if mine + amount > BB_MAX:
            err(f"на раунд не больше ⭐ {BB_MAX:,}".replace(",", " "))
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        db.execute("INSERT INTO bb_bet(hour,user,side,amount,ts) VALUES(?,?,?,?,?)", (h, uid, side, amount, now()))
    return {**bb_state(uid), "stars": bal(uid)}


# ---------------- аукцион банка ----------------
AUC_LEN = 6 * HOUR
AUC_STEP = 1.05
AUC_START = 0.5


def _auction_tick():
    t = now()
    for a in q("SELECT * FROM auction WHERE done=0 AND ends<=?", t):
        with tx():
            g = json.loads(a["gift"])
            db.execute("UPDATE auction SET done=1 WHERE id=?", (a["id"],))
            if a["top_user"]:
                cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                                 (a["top_user"], g["col"], g["model"], g["backdrop"], g["symbol"], g["num"], a["value"], t))
                db.execute("INSERT OR REPLACE INTO gift_link(gift,prev) VALUES(?,?)", (cur.lastrowid, g["id"]))
                event(a["top_user"], "auction", -a["top_bid"])
            else:   # без ставок подарок возвращается в хранилище
                db.execute("INSERT INTO bank_vault(user,gift,value,ts) VALUES(0,?,?,?)", (a["gift"], a["value"], t))
        if a["top_user"]:
            notify(a["top_user"], f"🏆 Аукцион выигран: {g['col']} {g['model']} за ⭐ {a['top_bid']:,}".replace(",", " "))
    if not q1("SELECT 1 FROM auction WHERE done=0"):
        v = q1("SELECT * FROM bank_vault ORDER BY value DESC LIMIT 1")
        if v:
            with tx():
                db.execute("DELETE FROM bank_vault WHERE id=?", (v["id"],))
                db.execute("INSERT INTO auction(gift,value,ends) VALUES(?,?,?)", (v["gift"], v["value"], t + AUC_LEN))


def _auc_view():
    a = q1("SELECT * FROM auction WHERE done=0 ORDER BY id LIMIT 1")
    if not a:
        return {"lot": None}
    nxt = max(int(a["value"] * AUC_START), int(a["top_bid"] * AUC_STEP) + 1)
    return {"lot": {"id": a["id"], "gift": json.loads(a["gift"]), "value": a["value"], "left": max(0, a["ends"] - now()), "top": a["top_bid"], "topUser": a["top_user"], "next": nxt}}


@app.get(R + "/auction")
def auction_state(uid=Depends(auth)):
    v = _auc_view()
    if v["lot"]:
        v["lot"]["mine"] = v["lot"]["topUser"] == uid
        v["lot"].pop("topUser", None)
    return v


@app.post(R + "/auction/bid")
async def auction_bid(req: Request, uid=Depends(auth)):
    b = await req.json()
    aid, amount = int(b.get("id", 0)), int(b.get("amount", 0))
    with tx():
        a = q1("SELECT * FROM auction WHERE id=? AND done=0", aid) or err("лот уже закрыт")
        if a["ends"] <= now():
            err("лот уже закрыт")
        if a["top_user"] == uid:
            err("твоя ставка уже первая")
        need = max(int(a["value"] * AUC_START), int(a["top_bid"] * AUC_STEP) + 1)
        if amount < need:
            err(f"минимальная ставка ⭐ {need:,}".replace(",", " "))
        if bal(uid) < amount:
            err("Не хватает звёзд")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        if a["top_user"]:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (a["top_bid"], a["top_user"]))
        ends = max(a["ends"], now() + 120)   # ставка в последние 2 минуты продлевает лот, чтобы нельзя было выхватить в последнюю секунду
        db.execute("UPDATE auction SET top_user=?, top_bid=?, ends=? WHERE id=?", (uid, amount, ends, aid))
    return {**auction_state(uid), "stars": bal(uid)}


# ---------------- бизнесы клана ----------------
CB = {"exchange": ("Обменный пункт", 100_000, 500), "port": ("Порт", 1_000_000, 4_000), "tower": ("Башня клана", 10_000_000, 30_000)}
CB_MAX = 5
CB_CAP = 24 * HOUR
CB_MANAGE = ("owner", "treasurer")


def _cb_income(bid, lv):
    import app as _a
    return int(CB[bid][2] * (1 + .5 * (lv - 1)) * _a.FAUCET_K())   # доход клана зависит от банка, как и все остальные


def _cb_up(bid, lv):
    return CB[bid][1] * 2 ** (lv - 1)


def _my_clan(uid):
    r = q1("SELECT clan, role FROM clan_members WHERE user=?", uid)
    return (r["clan"], r["role"]) if r else (None, None)


@app.get(R + "/clans/biz")
def clan_biz(uid=Depends(auth)):
    cid, role = _my_clan(uid)
    if not cid:
        err("ты не в клане")
    t = now()
    own = {r["bid"]: r for r in q("SELECT * FROM clan_biz WHERE clan=?", cid)}
    items = []
    for bid, (name, price, _) in CB.items():
        r = own.get(bid)
        lv = r["level"] if r else 0
        items.append({"id": bid, "name": name, "level": lv, "income": _cb_income(bid, max(lv, 1)),
                      "cost": None if lv >= CB_MAX else (_cb_up(bid, lv) if lv else price),
                      "ready": int(_cb_income(bid, lv) * min(t - r["ts"], CB_CAP) / HOUR) if r else 0})
    c = q1("SELECT bank FROM clans WHERE id=?", cid)
    return {"items": items, "bank": c["bank"] or 0, "can": role in CB_MANAGE, "role": role}


@app.post(R + "/clans/biz/{bid}/buy")
def clan_biz_buy(bid: str, uid=Depends(auth)):
    if bid not in CB:
        err("нет такого бизнеса")
    cid, role = _my_clan(uid)
    if role not in CB_MANAGE:
        err("покупает глава или казначей")
    with tx():
        r = q1("SELECT * FROM clan_biz WHERE clan=? AND bid=?", cid, bid)
        lv = r["level"] if r else 0
        if lv >= CB_MAX:
            err("максимальный уровень")
        cost = _cb_up(bid, lv) if lv else CB[bid][1]
        if (q1("SELECT bank FROM clans WHERE id=?", cid)["bank"] or 0) < cost:
            err("в казне не хватает звёзд")
        db.execute("UPDATE clans SET bank=bank-? WHERE id=?", (cost, cid))
        db.execute("INSERT INTO clan_biz(clan,bid,level,ts) VALUES(?,?,1,?) ON CONFLICT(clan,bid) DO UPDATE SET level=level+1", (cid, bid, now()))
        event(0, "clanspend", -cost)   # траты казны идут в банк игры
    return clan_biz(uid)


@app.post(R + "/clans/biz/collect")
def clan_biz_collect(uid=Depends(auth)):
    cid, role = _my_clan(uid)
    if role not in (*CB_MANAGE, "officer", "captain"):
        err("забирает доход руководство клана")
    t = now()
    with tx():
        total = 0
        for r in q("SELECT * FROM clan_biz WHERE clan=?", cid):
            total += int(_cb_income(r["bid"], r["level"]) * min(t - r["ts"], CB_CAP) / HOUR)
        if total <= 0:
            err("пока нечего забирать")
        db.execute("UPDATE clan_biz SET ts=? WHERE clan=?", (t, cid))
        db.execute("UPDATE clans SET bank=bank+? WHERE id=?", (total, cid))
        event(0, "clanbiz", total)   # доход клана платит банк игры
    return {**clan_biz(uid), "got": total}
