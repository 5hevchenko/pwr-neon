"""Гарантированный доход: подарки приносят звёзды, сейф (стейкинг подарков), бизнесы."""
from settings import conf
import hashlib
import json

from fastapi import Depends, Request

from app import R, app, auth, bal, db, err, event, now, q, q1, tx, gift_out, unpin, cancel_trades_with, add_xp, INCOME_TAX

# ---------- схема ----------
for _c in ("inc_ts INTEGER DEFAULT 0",):
    try:
        db.execute("ALTER TABLE users ADD COLUMN " + _c)
    except Exception:
        pass
try:
    db.execute("ALTER TABLE gifts ADD COLUMN acq INTEGER DEFAULT 0")
    db.execute("UPDATE gifts SET acq=created")
except Exception:
    pass
db.executescript("""
-- когда подарок сменил владельца — с этого момента он начинает приносить доход новому владельцу
CREATE TRIGGER IF NOT EXISTS gift_acq AFTER UPDATE OF owner ON gifts WHEN NEW.owner > 0 AND NEW.owner != OLD.owner
BEGIN UPDATE gifts SET acq = CAST(strftime('%s','now') AS INTEGER) WHERE id = NEW.id; END;
CREATE TRIGGER IF NOT EXISTS gift_acq_new AFTER INSERT ON gifts
BEGIN UPDATE gifts SET acq = COALESCE(NEW.created, CAST(strftime('%s','now') AS INTEGER)) WHERE id = NEW.id; END;
CREATE TABLE IF NOT EXISTS vault(gift INTEGER PRIMARY KEY, user INTEGER, start INTEGER, until INTEGER, pct REAL);
CREATE TABLE IF NOT EXISTS biz(user INTEGER, bid TEXT, level INTEGER, ts INTEGER, PRIMARY KEY(user, bid));
""")

# ---------- 1. доход с коллекции ----------
GIFT_RATE = conf("economy.gift_income", 0.02)          # 2% ценности в сутки
GIFT_CAP = 12 * 3600      # копится максимум 12 часов
LAUNCH = 1791234400       # запуск дохода (2026-10-05 ~23:26 CEST) — с этого момента копят все


def _rate_mult(mp):
    return 2.0 if mp <= 5 else 1.5 if mp <= 10 else 1.0


def _gift_accrual(uid, t, inc_ts):
    """Сколько накапали подарки с прошлого сбора (каждый — с момента, как стал твоим)."""
    from app import LOOK
    import app as _a
    fk = _a.FAUCET_K()
    total, per_day = 0.0, 0.0
    for g in q("SELECT col, model, value, acq FROM gifts WHERE owner=? AND price IS NULL", uid):
        mp = LOOK[g["col"]][0].get(g["model"], 99) if g["col"] in LOOK else 99
        day = g["value"] * GIFT_RATE * _rate_mult(mp) * fk
        per_day += day
        since = max(inc_ts, g["acq"] or 0)
        total += day * max(0, min(t - since, t - inc_ts, GIFT_CAP)) / 86400
    return int(total), per_day, total


# ---------- 2. сейф ----------
VAULT = {1: conf("economy.vault_1d", 0.02), 3: conf("economy.vault_3d", 0.07), 7: conf("economy.vault_7d", 0.18)}
VAULT_OWNER = 2 * 10 ** 9   # подарок в сейфе: owner = -(VAULT_OWNER + uid)

# ---------- 3. бизнесы ----------
BIZ_SCALE = conf("economy.biz_scale", 0.55)   # множитель дохода всех бизнесов
BIZ = [  # id, название, картинка (коллекция), цена, доход/час на 1 уровне
    ("stall", "Ларёк с леденцами", "Lol Pop", 2_000, 17),
    ("coffee", "Кофейня", "Spiced Wine", 5_000, 42),
    ("bakery", "Кондитерская", "Homemade Cake", 8_000, 67),
    ("flowers", "Цветочный бутик", "Sakura Flower", 25_000, 210),
    ("jewelry", "Ювелирный салон", "Signet Ring", 80_000, 670),
    ("club", "Ночной клуб", "Party Sparkler", 250_000, 2_100),
    ("cinema", "Кинотеатр", "Record Player", 500_000, 2_100),
    ("durov", "Студия Дурова", "Durov's Cap", 1_000_000, 4_200),
    ("casino", "Аркада", "Money Pot", 2_500_000, 10_500),
    ("space", "Космодром", "Stellar Rocket", 6_000_000, 25_000),
    ("pepe", "Империя Пепе", "Plush Pepe", 15_000_000, 62_500),
]   # 2026-10-10: доходность урезана вдвое — до 500k ~20% цены в сутки, дороже ~10% (бизнесы печатали по 450k/сутки)
SHIFT_EVERY = 2 * 3600   # «Смена»: тапать 10 секунд, до часа дохода бизнеса, раз в 2 часа
SHIFT_TAPS = 40          # столько тапов — полный час дохода
try:
    db.execute("ALTER TABLE biz ADD COLUMN shift_ts INTEGER DEFAULT 0")
except Exception:
    pass
BIZ_CAP = 8 * 3600
BIZ_MAX = 10
BIZ_MAP = {b[0]: b for b in BIZ}


# Цепочки поставок: следующему звену нужен предыдущий бизнес. Без поставщика — 60% дохода, полная цепочка — ещё +15%.
CHAINS = [["stall", "coffee", "bakery"], ["flowers", "jewelry"], ["club", "cinema", "durov"], ["casino", "space", "pepe"]]
CHAIN_OF = {b: (i, c.index(b)) for i, c in enumerate(CHAINS) for b in c}
CHAIN_NO_SUPPLY, CHAIN_FULL = 0.6, 0.15
db.execute("CREATE TABLE IF NOT EXISTS biz_mgr(user INTEGER, bid TEXT, col TEXT, model TEXT, value INTEGER, bonus REAL, until INTEGER, PRIMARY KEY(user,bid))")
MGR_DAYS, MGR_MAX = 7, 0.25


def biz_mult(uid, bid):
    """Множитель цепочки и управляющего для бизнеса игрока."""
    own = {r["bid"]: r["level"] for r in q("SELECT bid, level FROM biz WHERE user=?", uid)}
    ci, pos = CHAIN_OF.get(bid, (None, 0))
    k = 1.0
    if ci is not None:
        ch = CHAINS[ci]
        if pos > 0 and ch[pos - 1] not in own:
            k = CHAIN_NO_SUPPLY
        if all(x in own for x in ch):
            k += CHAIN_FULL
    m = q1("SELECT bonus FROM biz_mgr WHERE user=? AND bid=? AND until>?", uid, bid, now())
    return k + (m["bonus"] if m else 0)


def biz_income(bid, level, uid=None):
    """Доход в час: база × уровень × biz_scale. С игроком ещё цепочка, управляющий и курс банка. Партии идут сверху."""
    v = BIZ_MAP[bid][4] * (1 + 0.35 * (level - 1)) * BIZ_SCALE
    if uid is not None:
        v *= biz_mult(uid, bid) * biz_bank_rate()
    return max(1, int(v))


# Партия: игрок закупает товар за звёзды (они уходят в банк), через BATCH_TIME забирает с наценкой.
# Наценка = база × спрос × цепочка/управляющий × курс банка и фиксируется в момент закупки.
# Не забрал за BATCH_FRESH — товар портится: за следующие сутки теряется до половины, остаток остаётся у банка.
BATCH_TIME, BATCH_FRESH, BATCH_ROT = 4 * 3600, 8 * 3600, 24 * 3600
# Партия на 1 уровне — доля цены бизнеса: дешёвые окупаются быстрее дорогих, иначе они приносят копейки
BATCH_SHARES = (conf("economy.biz_batch_small", 0.25), conf("economy.biz_batch_mid", 0.15), conf("economy.biz_batch_big", 0.10), conf("economy.biz_batch_huge", 0.07))
DEMAND_EVERY = 6 * 3600
MARGIN = conf("economy.biz_margin", 0.12)
for _col in ("batch_cost", "batch_pay", "batch_ready"):
    try:
        db.execute(f"ALTER TABLE biz ADD COLUMN {_col} INTEGER DEFAULT 0")
    except Exception:
        pass


def biz_demand(bid, t=None):
    """Спрос меняется каждые 6 часов и считается открытой формулой от названия и времени: подкрутить под игрока нельзя. От 0,4 до 1,6."""
    w = (t if t is not None else now()) // DEMAND_EVERY
    x = int(hashlib.sha256(f"{bid}:{w}".encode()).hexdigest()[:8], 16) / 0xffffffff
    return round(0.4 + 1.2 * x, 2)


def biz_bank_rate():
    """Курс банка: чем больше банк и лучше его неделя, тем выше наценка."""
    import app as _a
    return _a.FAUCET_K()


def biz_margin(uid, bid, t=None):
    return round(MARGIN * biz_demand(bid, t) * biz_mult(uid, bid) * biz_bank_rate(), 4)


def biz_batch_cap(bid, level):
    price = BIZ_MAP[bid][3]
    share = BATCH_SHARES[0] if price < 100_000 else BATCH_SHARES[1] if price < 1_000_000 else BATCH_SHARES[2] if price < 5_000_000 else BATCH_SHARES[3]
    return int(price * share * (1 + 0.5 * (level - 1)))


def batch_value(r, t):
    """Сколько можно забрать сейчас с учётом порчи."""
    over = t - r["batch_ready"] - BATCH_FRESH
    return int(r["batch_pay"] * (1 - min(0.5, max(0, over) / BATCH_ROT * 0.5)))


def biz_upgrade(bid, level):
    return int(BIZ_MAP[bid][3] * 0.5 * 1.6 ** (level - 1))


BIZ_SELL = conf("economy.biz_sell", 0.5)   # продажа: 50% вложенного — купить и сразу продать всегда в убыток (не «станок»)


def biz_invested(bid, level):
    """Сколько игрок заплатил за бизнес этого уровня: цена + все улучшения."""
    return BIZ_MAP[bid][3] + sum(biz_upgrade(bid, lv) for lv in range(1, level))


def biz_sell_price(bid, level):
    return int(biz_invested(bid, level) * BIZ_SELL)


def biz_down_price(bid, level):
    """Продать последнее улучшение (уровень level → level-1)."""
    return int(biz_upgrade(bid, level - 1) * BIZ_SELL) if level > 1 else None


def _biz_rows(uid, t):
    own = {r["bid"]: r for r in q("SELECT * FROM biz WHERE user=?", uid)}
    out, ready = [], 0
    for bid, name, col, price, _ in BIZ:
        r = own.get(bid)
        item = {"id": bid, "name": name, "col": col, "price": price, "level": r["level"] if r else 0}
        ci, pos = CHAIN_OF.get(bid, (None, 0))
        if ci is not None:
            ch = CHAINS[ci]
            item["supplier"] = BIZ_MAP[ch[pos - 1]][1] if pos else None
            item["noSupply"] = bool(pos and ch[pos - 1] not in own)
            item["chainFull"] = all(x in own for x in ch)
        mg = q1("SELECT col, model, bonus, until FROM biz_mgr WHERE user=? AND bid=? AND until>?", uid, bid, t) if r else None
        if mg:
            item["mgr"] = {"col": mg["col"], "bonus": round(mg["bonus"] * 100), "left": mg["until"] - t}
        if True:
            item.update(demand=biz_demand(bid, t), demandIn=DEMAND_EVERY - t % DEMAND_EVERY)
            lvl = r["level"] if r else 1
            k = biz_margin(uid, bid, t)
            item.update(margin=round(k * 100, 1), batchCap=biz_batch_cap(bid, lvl), batchProfit=int(biz_batch_cap(bid, lvl) * k * (1 - INCOME_TAX)))
            if r and lvl < BIZ_MAX:
                item.update(nextCap=biz_batch_cap(bid, lvl + 1), nextProfit=int(biz_batch_cap(bid, lvl + 1) * k * (1 - INCOME_TAX)))
        if r:
            item.update(batch={"cost": r["batch_cost"], "pay": r["batch_pay"], "readyIn": max(0, r["batch_ready"] - t), "now": batch_value(r, t),
                               "spoilIn": max(0, r["batch_ready"] + BATCH_FRESH - t)} if r["batch_cost"] else None)
            inc = biz_income(bid, r["level"], uid)
            acc = int(inc * min(t - r["ts"], BIZ_CAP) / 3600)
            ready += acc
            item.update(pledged=__import__("loans").biz_pledged(uid, bid))
            item.update(income=inc, accrued=acc, cap=inc * BIZ_CAP // 3600, full=t - r["ts"] >= BIZ_CAP,
                        shiftIn=max(0, (r["shift_ts"] or 0) + SHIFT_EVERY - t),
                        upgrade=biz_upgrade(bid, r["level"]) if r["level"] < BIZ_MAX else None,
                        next=biz_income(bid, r["level"] + 1, uid) if r["level"] < BIZ_MAX else None,
                        sell=biz_sell_price(bid, r["level"]), sellPct=round(BIZ_SELL * 100), down=biz_down_price(bid, r["level"]),
                        prev=biz_income(bid, r["level"] - 1, uid) if r["level"] > 1 else None)
        else:
            item.update(income=biz_income(bid, 1, uid))
        out.append(item)
    return out, ready


def _uinc(uid, t):
    u = q1("SELECT inc_ts, created FROM users WHERE id=?", uid)
    if not u["inc_ts"]:
        first = q1("SELECT MIN(acq) a FROM gifts WHERE owner=? AND price IS NULL", uid)["a"] or t
        start = min(t, max(LAUNCH, t - GIFT_CAP, first))   # копилка — с первого подарка, не раньше запуска
        with tx():
            db.execute("UPDATE users SET inc_ts=? WHERE id=?", (start, uid))
        return start
    return u["inc_ts"]


@app.get(R + "/income")
def income(uid=Depends(auth)):
    t = now()
    inc_ts = _uinc(uid, t)
    gacc, per_day, exact = _gift_accrual(uid, t, inc_ts)
    biz, bready = _biz_rows(uid, t)
    vault = []
    for v in q("SELECT * FROM vault WHERE user=? ORDER BY until", uid):
        g = q1("SELECT * FROM gifts WHERE id=?", v["gift"])
        if g:
            vault.append({"gift": gift_out(g), "until": v["until"], "start": v["start"], "pct": v["pct"],
                          "reward": int(g["value"] * v["pct"]), "ready": t >= v["until"]})
    return {"now": t, "gifts": {"perDay": int(per_day), "accrued": gacc, "exact": round(exact, 3), "since": inc_ts, "cap": GIFT_CAP,
                                "full": t - inc_ts >= GIFT_CAP},
            "biz": biz, "bizReady": bready, "vault": vault, "vaultPlans": [{"days": d, "pct": p} for d, p in VAULT.items()],
            "ready": gacc + bready}


@app.post(R + "/income/collect")
def income_collect(uid=Depends(auth)):
    t = now()
    with tx():
        inc_ts = q1("SELECT inc_ts FROM users WHERE id=?", uid)["inc_ts"] or t
        gacc, _, _ = _gift_accrual(uid, t, inc_ts)
        _, bready = _biz_rows(uid, t)
        from clans import income_bonus
        gross = int((gacc + bready) * income_bonus(uid))   # бонус уровня клана
        if gross <= 0:
            err("пока нечего забирать")
        tax = int(gross * INCOME_TAX)
        total = gross - tax
        db.execute("UPDATE users SET stars=stars+?, inc_ts=? WHERE id=?", (total, t, uid))
        db.execute("UPDATE biz SET ts=? WHERE user=?", (t, uid))
        event(uid, "income", gross)
        if tax:
            event(uid, "fee", -tax)
        loan_paid = __import__("loans").auto_pay(uid, total)
    return {"got": total - loan_paid, "gifts": gacc, "biz": bready, "tax": tax, "loanPaid": loan_paid, "stars": bal(uid)}


@app.post(R + "/vault/put")
async def vault_put(req: Request, uid=Depends(auth)):
    b = await req.json()
    gids, days = [int(x) for x in b.get("gifts", [])][:10], int(b.get("days", 1))
    if days not in VAULT:
        err("срок: 1, 3 или 7 дней")
    if not gids:
        err("выбери подарки")
    t = now()
    with tx():
        for g in gids:
            x = q1("SELECT owner, price FROM gifts WHERE id=?", g)
            if not x or x["owner"] != uid:
                err("это не твой подарок")
            if x["price"] is not None:
                err("сначала сними подарок с маркета")
        for g in gids:
            db.execute("UPDATE gifts SET owner=? WHERE id=?", (-(VAULT_OWNER + uid), g))
            unpin(uid, g)
            cancel_trades_with(g)
            db.execute("INSERT OR REPLACE INTO vault VALUES(?,?,?,?,?)", (g, uid, t, t + days * 86400, VAULT[days]))
    return {"ok": True, "count": len(gids)}


@app.post(R + "/vault/{gid}/take")
def vault_take(gid: int, uid=Depends(auth)):
    t = now()
    with tx():
        v = q1("SELECT * FROM vault WHERE gift=? AND user=?", gid, uid) or err("этого подарка нет в сейфе")
        g = q1("SELECT value FROM gifts WHERE id=?", gid)
        reward = int(g["value"] * v["pct"]) if t >= v["until"] else 0
        db.execute("UPDATE gifts SET owner=? WHERE id=?", (uid, gid))
        db.execute("DELETE FROM vault WHERE gift=?", (gid,))
        if reward:
            tax = int(reward * INCOME_TAX)
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (reward - tax, uid))
            event(uid, "stake", reward)
            if tax:
                event(uid, "fee", -tax)
            reward -= tax
    return {"reward": reward, "early": reward == 0, "stars": bal(uid)}


@app.post(R + "/biz/{bid}/buy")
def biz_buy(bid: str, uid=Depends(auth)):
    if bid not in BIZ_MAP:
        err("нет такого бизнеса")
    t = now()
    with tx():
        r = q1("SELECT * FROM biz WHERE user=? AND bid=?", uid, bid)
        if r and __import__("loans").biz_pledged(uid, bid):
            err("бизнес в залоге: сначала закрой кредит")
        if r and r["level"] >= BIZ_MAX:
            err("максимальный уровень")
        cost = biz_upgrade(bid, r["level"]) if r else BIZ_MAP[bid][3]
        if bal(uid) < cost:
            err("Не хватает звёзд")
        if r:   # перед прокачкой забираем накопленное по старой ставке
            acc = int(biz_income(bid, r["level"], uid) * min(t - r["ts"], BIZ_CAP) / 3600)
            db.execute("UPDATE biz SET level=level+1, ts=? WHERE user=? AND bid=?", (t, uid, bid))
            tax = int(acc * INCOME_TAX)
            db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (cost, acc - tax, uid))
            if acc:
                event(uid, "income", acc)
            if tax:
                event(uid, "fee", -tax)
        else:
            db.execute("INSERT INTO biz(user,bid,level,ts) VALUES(?,?,?,?)", (uid, bid, 1, t))
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (cost, uid))
        event(uid, "bizbuy", -cost)
        lvl = add_xp(uid, max(10, cost // 50))
    return {"ok": True, "stars": bal(uid), "levelup": lvl}


@app.post(R + "/biz/{bid}/supply")
async def biz_supply(bid: str, req: Request, uid=Depends(auth)):
    amount = int((await req.json()).get("amount", 0))
    if bid not in BIZ_MAP:
        err("нет такого бизнеса")
    t = now()
    with tx():
        r = q1("SELECT * FROM biz WHERE user=? AND bid=?", uid, bid) or err("сначала купи этот бизнес")
        if r["batch_cost"]:
            err("сначала забери текущую партию")
        cap = biz_batch_cap(bid, r["level"])
        if not 100 <= amount <= cap:
            err(f"партия от ⭐ 100 до ⭐ {cap:,}".replace(",", " "))
        if bal(uid) < amount:
            err("Не хватает звёзд")
        pay = amount + int(amount * biz_margin(uid, bid, t))
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        db.execute("UPDATE biz SET batch_cost=?, batch_pay=?, batch_ready=? WHERE user=? AND bid=?", (amount, pay, t + BATCH_TIME, uid, bid))
        event(uid, "bizgoods", -amount)
    return {"ok": True, "pay": pay, "readyIn": BATCH_TIME, "stars": bal(uid)}


@app.post(R + "/biz/{bid}/deliver")
def biz_deliver(bid: str, uid=Depends(auth)):
    t = now()
    with tx():
        r = q1("SELECT * FROM biz WHERE user=? AND bid=?", uid, bid) or err("сначала купи этот бизнес")
        if not r["batch_cost"]:
            err("партии нет")
        if t < r["batch_ready"]:
            err("партия ещё не готова")
        got = batch_value(r, t)
        profit = max(0, got - r["batch_cost"])
        tax = int(profit * INCOME_TAX)
        db.execute("UPDATE biz SET batch_cost=0, batch_pay=0, batch_ready=0 WHERE user=? AND bid=?", (uid, bid))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got - tax, uid))
        event(uid, "bizgoods", got)
        if tax:
            event(uid, "fee", -tax)
    return {"got": got - tax, "cost": r["batch_cost"], "tax": tax, "stars": bal(uid)}


@app.post(R + "/biz/{bid}/manager")
async def biz_manager(bid: str, req: Request, uid=Depends(auth)):
    """Управляющий: подарок работает 7 дней и сгорает. Бонус = ценность подарка к цене бизнеса, не больше +25%. Ценность уходит в банк."""
    gid = int((await req.json()).get("gid", 0))
    if bid not in BIZ_MAP:
        err("нет такого бизнеса")
    t = now()
    with tx():
        q1("SELECT 1 FROM biz WHERE user=? AND bid=?", uid, bid) or err("сначала купи этот бизнес")
        if q1("SELECT 1 FROM biz_mgr WHERE user=? AND bid=? AND until>?", uid, bid, t):
            err("управляющий уже работает")
        g = q1("SELECT * FROM gifts WHERE id=? AND owner=? AND price IS NULL", gid, uid) or err("подарок недоступен")
        bonus = round(min(MGR_MAX, g["value"] / BIZ_MAP[bid][3]), 4)
        unpin(uid, gid)
        cancel_trades_with(gid)
        db.execute("DELETE FROM gifts WHERE id=?", (gid,))
        db.execute("INSERT OR REPLACE INTO biz_mgr(user,bid,col,model,value,bonus,until) VALUES(?,?,?,?,?,?,?)", (uid, bid, g["col"], g["model"], g["value"], bonus, t + MGR_DAYS * 86400))
        event(uid, "bizmgr", -g["value"])
    return {"ok": True, "bonus": round(bonus * 100, 1)}


@app.post(R + "/biz/{bid}/sell")
async def biz_sell(bid: str, req: Request, uid=Depends(auth)):
    """Продажа: what=all — бизнес целиком за долю вложенного (BIZ_SELL); what=level — последнее улучшение за ту же долю его цены.
    Накопленный доход перед этим выплачивается (с налогом), как при прокачке."""
    what = (await req.json()).get("what")
    if bid not in BIZ_MAP or what not in ("all", "level"):
        err("нет такого бизнеса")
    t = now()
    with tx():
        r = q1("SELECT * FROM biz WHERE user=? AND bid=?", uid, bid) or err("этот бизнес уже не твой")
        if r["batch_cost"]:
            err("сначала забери партию товара")
        if __import__("loans").biz_pledged(uid, bid):
            err("бизнес в залоге: сначала закрой кредит")
        lv = r["level"]
        if what == "level" and lv <= 1:
            err("это первый уровень — можно продать только бизнес целиком")
        got = biz_sell_price(bid, lv) if what == "all" else biz_down_price(bid, lv)
        acc = int(biz_income(bid, lv, uid) * min(t - r["ts"], BIZ_CAP) / 3600)
        tax = int(acc * INCOME_TAX)
        if what == "all":
            db.execute("DELETE FROM biz WHERE user=? AND bid=?", (uid, bid))
        else:
            db.execute("UPDATE biz SET level=level-1, ts=? WHERE user=? AND bid=?", (t, uid, bid))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got + acc - tax, uid))
        if acc:
            event(uid, "income", acc)
        if tax:
            event(uid, "fee", -tax)
        event(uid, "bizsell", got)
    return {"ok": True, "got": got, "income": acc - tax, "stars": bal(uid)}


@app.post(R + "/biz/{bid}/shift")
async def biz_shift(bid: str, req: Request, uid=Depends(auth)):
    """Смены убраны из игры: кнопки нет, а с почасовым доходом запрос давал бы лишние +50%."""
    err("смен больше нет")
    taps = max(0, min(SHIFT_TAPS, int((await req.json()).get("taps", 0))))
    if bid not in BIZ_MAP:
        err("нет такого бизнеса")
    t = now()
    with tx():
        r = q1("SELECT * FROM biz WHERE user=? AND bid=?", uid, bid) or err("сначала купи этот бизнес")
        if (r["shift_ts"] or 0) + SHIFT_EVERY > t:
            err("смена ещё не началась — загляни позже")
        gross = int(biz_income(bid, r["level"], uid) * taps / SHIFT_TAPS)
        tax = int(gross * INCOME_TAX)
        db.execute("UPDATE biz SET shift_ts=? WHERE user=? AND bid=?", (t, uid, bid))
        if gross:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (gross - tax, uid))
            event(uid, "income", gross)
            if tax:
                event(uid, "fee", -tax)
    return {"got": gross - tax, "taps": taps, "full": taps >= SHIFT_TAPS, "stars": bal(uid), "next": t + SHIFT_EVERY}
