"""Крипто-биржа: реальные курсы (OKX), торговля только за игровые звёзды."""
import asyncio
import math
import time

import httpx
from fastapi import Depends, Request

from app import R, app, auth, bal, db, err, event, notify, now, q, q1, tx, user_brief
from settings import conf

db.executescript("""
CREATE TABLE IF NOT EXISTS crypto(user INTEGER, asset TEXT, qty REAL DEFAULT 0, cost REAL DEFAULT 0, PRIMARY KEY(user, asset));
CREATE TABLE IF NOT EXISTS crypto_tx(id INTEGER PRIMARY KEY, user INTEGER, asset TEXT, side TEXT, qty REAL, price REAL, stars INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS crypto_tx_user ON crypto_tx(user, ts);
CREATE TABLE IF NOT EXISTS crypto_stake(user INTEGER, asset TEXT, qty REAL DEFAULT 0, cost REAL DEFAULT 0, earned REAL DEFAULT 0,
  total REAL DEFAULT 0, ts INTEGER, PRIMARY KEY(user, asset));
CREATE TABLE IF NOT EXISTS crypto_pos(id INTEGER PRIMARY KEY, user INTEGER, asset TEXT, side TEXT, lev INTEGER, margin INTEGER,
  entry REAL, qty REAL, ts INTEGER, status TEXT DEFAULT 'open', close REAL, pnl INTEGER, closed INTEGER);
CREATE INDEX IF NOT EXISTS crypto_pos_open ON crypto_pos(status, user);
""")
STAR_USD = 0.015        # курс игровой звезды к доллару (примерно как Telegram Stars)
FEE = conf("economy.crypto_fee", 0.004)        # комиссия биржи с каждой сделки (настройка [economy] crypto_fee)
MIN_TRADE = 10
STALE = 90              # старше — торговать нельзя, курс не обновился
# id, название, пара на OKX, цвет, знак
ASSETS = [
    ("BTC", "Bitcoin", "BTC-USDT", "#f7931a", "₿"),
    ("GRAM", "Gram", "GRAM-USDT", "#0098ea", "G"),
    ("ETH", "Ethereum", "ETH-USDT", "#627eea", "Ξ"),
    ("SOL", "Solana", "SOL-USDT", "#9945ff", "S"),
    ("NOT", "Notcoin", "NOT-USDT", "#4a4a5a", "N"),
    ("DOGE", "Dogecoin", "DOGE-USDT", "#c2a633", "Ð"),
    ("USDT", "Tether", "USDC-USDT", "#26a17b", "₮"),   # USDT = 1 / (USDC в USDT)
]
BY_ID = {a[0]: a for a in ASSETS}
PX = {}                 # asset -> {"usd", "open", "ts"}
CHART = {}              # (asset, range) -> (ts, points)
RANGES = {"1d": ("15m", 96), "7d": ("1H", 168), "30d": ("4H", 180)}
_http = None


def _client():
    global _http
    if _http is None:
        _http = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0"), timeout=10,
                                  headers={"User-Agent": "NePridymal/1.0"})
    return _http


async def _fetch_prices():
    r = await _client().get("https://www.okx.com/api/v5/market/tickers", params={"instType": "SPOT"})
    rows = {x["instId"]: x for x in r.json()["data"]}
    t = time.time()
    for aid, _, inst, _, _ in ASSETS:
        x = rows.get(inst)
        if not x:
            continue
        last, op = float(x["last"]), float(x["open24h"])
        if aid == "USDT":
            last, op = 1 / last, 1 / op
        PX[aid] = {"usd": last, "open": op, "ts": t}


async def crypto_loop():
    n = 0
    while True:
        try:
            await _fetch_prices()
            if n % 30 == 0:   # раз в ~5 минут прогреваем мини-графики всех монет, чтобы экран открывался мгновенно
                await asyncio.gather(*[_fetch_candles(a[0], "1H", 24) for a in ASSETS], return_exceptions=True)
            n += 1
            await asyncio.get_running_loop().run_in_executor(None, liquidate_all)
        except Exception as e:
            print("crypto:", e, flush=True)
        await asyncio.sleep(10)


@app.on_event("startup")
async def _crypto_start():
    asyncio.create_task(crypto_loop())


async def fresh(aid):
    """Цена монеты в звёздах прямо с биржи; при сбое — из кэша, если он свежий."""
    inst = BY_ID[aid][2]
    try:
        r = await _client().get("https://www.okx.com/api/v5/market/ticker", params={"instId": inst})
        x = r.json()["data"][0]
        last, op = float(x["last"]), float(x["open24h"])
        if aid == "USDT":
            last, op = 1 / last, 1 / op
        PX[aid] = {"usd": last, "open": op, "ts": time.time()}
    except Exception as e:
        print("crypto fresh:", e, flush=True)
    return stars_price(aid)


def stars_price(aid):
    p = PX.get(aid)
    if not p or time.time() - p["ts"] > STALE:
        err("Курс обновляется, попробуй через пару секунд")
    return p["usd"] / STAR_USD


def _asset(aid):
    a = BY_ID.get(aid.upper())
    if not a:
        err("Нет такой монеты")
    return a


def _brief(aid):
    a, p = BY_ID[aid], PX.get(aid)
    return {"id": aid, "name": a[1], "color": a[3], "glyph": a[4],
            "usd": p["usd"] if p else None, "price": p["usd"] / STAR_USD if p else None,
            "change": (p["usd"] / p["open"] - 1) * 100 if p and p["open"] else 0}


async def _candles(aid, bar, limit, ttl):
    """Цены закрытия свечей OKX [[ts, usd], …] с кэшем. Устаревший кэш отдаём сразу и обновляем в фоне —
    иначе экран крипты ждал биржу до 4 секунд."""
    key = (aid, bar, limit)
    c = CHART.get(key)
    if c and time.time() - c[0] < ttl:
        return c[1]
    if c:
        if key not in _REFRESHING:
            _REFRESHING.add(key)
            asyncio.get_running_loop().create_task(_refresh(aid, bar, limit))
        return c[1]
    return await _fetch_candles(aid, bar, limit)


_REFRESHING = set()


async def _refresh(aid, bar, limit):
    try:
        await _fetch_candles(aid, bar, limit)
    finally:
        _REFRESHING.discard((aid, bar, limit))


async def _fetch_candles(aid, bar, limit):
    key = (aid, bar, limit)
    c = CHART.get(key)
    try:
        res = await _client().get("https://www.okx.com/api/v5/market/candles", params={"instId": BY_ID[aid][2], "bar": bar, "limit": limit})
        pts = [[int(x[0]) // 1000, float(x[4])] for x in reversed(res.json()["data"])]
        if aid == "USDT":
            pts = [[t, 1 / v] for t, v in pts]
        CHART[key] = (time.time(), pts)
        return pts
    except Exception as e:
        print("crypto chart:", e, flush=True)
        return c[1] if c else []


@app.get(R + "/crypto")
async def crypto(uid=Depends(auth)):
    sparks = await asyncio.gather(*[_candles(a[0], "1H", 24, 300) for a in ASSETS])
    spark = {a[0]: [round(v / STAR_USD, 6) for _, v in pts] for a, pts in zip(ASSETS, sparks)}
    mine = {r["asset"]: r for r in q("SELECT * FROM crypto WHERE user=? AND qty>0", uid)}
    st = {r["asset"]: r for r in q("SELECT * FROM crypto_stake WHERE user=? AND (qty>0 OR earned>0)", uid)}
    out, total, cost, t = [], 0, 0, now()
    for aid, *_ in ASSETS:
        b = _brief(aid)
        b["spark"] = spark.get(aid, [])
        b["apy"] = APY[aid]
        h, sk = mine.get(aid), st.get(aid)
        if h and b["price"]:
            b["qty"], b["value"], b["cost"] = h["qty"], h["qty"] * b["price"], h["cost"]
            total += b["value"]
            cost += h["cost"]
        if sk and b["price"]:
            earned = _earned(sk, t)
            b["staked"], b["earned"], b["stakeCost"], b["stakeTotal"] = sk["qty"], earned, sk["cost"], sk["total"] + earned
            b["stakeValue"] = (sk["qty"] + earned) * b["price"]
            b["stakeLeft"] = max(0, STAKE_CAP - (t - sk["ts"]))   # через сколько секунд копилка заполнится
            total += b["stakeValue"]
            cost += sk["cost"]
        out.append(b)
    # топ трейдеров по стоимости портфеля
    vals = {}
    for r in q("SELECT user, asset, qty FROM crypto WHERE qty>0 UNION ALL SELECT user, asset, qty FROM crypto_stake WHERE qty>0"):
        p = PX.get(r["asset"])
        if p:
            vals[r["user"]] = vals.get(r["user"], 0) + r["qty"] * p["usd"] / STAR_USD
    top = []
    for u, v in sorted(vals.items(), key=lambda x: -x[1])[:5]:
        ur = q1("SELECT * FROM users WHERE id=?", u)
        if ur:
            top.append({**user_brief(ur), "value": int(v)})
    return {"assets": out, "total": total, "cost": cost, "fee": FEE, "min": MIN_TRADE, "starUsd": STAR_USD, "top": top}


@app.get(R + "/crypto/{aid}")
async def crypto_asset(aid: str, r: str = "1d", uid=Depends(auth)):
    a = _asset(aid)
    aid = a[0]
    rng = r if r in RANGES else "1d"
    bar, limit = RANGES[rng]
    raw = await _candles(aid, bar, limit, 60)
    pts = [[t, v / STAR_USD] for t, v in raw]
    h = q1("SELECT * FROM crypto WHERE user=? AND asset=?", uid, aid)
    txs = [dict(x) for x in q("SELECT side, qty, price, stars, ts FROM crypto_tx WHERE user=? AND asset=? ORDER BY id DESC LIMIT 15", uid, aid)]
    sk = q1("SELECT * FROM crypto_stake WHERE user=? AND asset=?", uid, aid)
    return {**_brief(aid), "range": rng, "chart": pts, "qty": h["qty"] if h else 0, "cost": h["cost"] if h else 0,
            "tx": txs, "fee": FEE, "min": MIN_TRADE, "stars": bal(uid), "apy": APY[aid], "swapFee": SWAP_FEE,
            "staked": sk["qty"] if sk else 0, "earned": _earned(sk, now()) if sk else 0, "stakeTotal": sk["total"] if sk else 0,
            "stakeLeft": max(0, STAKE_CAP - (now() - sk["ts"])) if sk else STAKE_CAP}


@app.post(R + "/crypto/{aid}/buy")
async def crypto_buy(aid: str, req: Request, uid=Depends(auth)):
    aid = _asset(aid)[0]
    s = int((await req.json()).get("stars", 0))
    if s < MIN_TRADE:
        err(f"Минимум ⭐ {MIN_TRADE}")
    price = await fresh(aid)
    with tx():
        if bal(uid) < s:
            err("Не хватает звёзд")
        qty = s * (1 - FEE) / price
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (s, uid))
        db.execute("INSERT INTO crypto(user,asset,qty,cost) VALUES(?,?,?,?) ON CONFLICT(user,asset) DO UPDATE SET qty=qty+?, cost=cost+?",
                   (uid, aid, qty, s, qty, s))
        db.execute("INSERT INTO crypto_tx(user,asset,side,qty,price,stars,ts) VALUES(?,?,?,?,?,?,?)", (uid, aid, "buy", qty, price, s, now()))
        event(uid, "crypto", -s)
    return {"ok": True, "qty": qty, "stars": bal(uid)}


@app.post(R + "/crypto/{aid}/sell")
async def crypto_sell(aid: str, req: Request, uid=Depends(auth)):
    aid = _asset(aid)[0]
    pct = float((await req.json()).get("pct", 100))
    if not 0 < pct <= 100:
        err("Неверная доля")
    price = await fresh(aid)
    with tx():
        h = q1("SELECT * FROM crypto WHERE user=? AND asset=?", uid, aid)
        if not h or h["qty"] <= 0:
            err("У тебя нет этой монеты")
        qty = h["qty"] if pct >= 100 else h["qty"] * pct / 100
        got = int(qty * price * (1 - FEE))
        if got < 1:
            err("Слишком маленькая сумма")
        left = h["qty"] - qty
        cost_left = 0 if pct >= 100 else h["cost"] * (1 - pct / 100)
        db.execute("UPDATE crypto SET qty=?, cost=? WHERE user=? AND asset=?", (left if left > 1e-12 else 0, cost_left, uid, aid))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got, uid))
        db.execute("INSERT INTO crypto_tx(user,asset,side,qty,price,stars,ts) VALUES(?,?,?,?,?,?,?)", (uid, aid, "sell", qty, price, got, now()))
        event(uid, "crypto", got)
    return {"ok": True, "got": got, "stars": bal(uid)}


# ============================================================ стейкинг
# доходность в сутки — на уровне дохода с подарков (2%/сут): стабильные монеты меньше, волатильные больше.
# APY (годовая, без сложного процента) отдаём фронту как раньше: в день = APY / 365
STAKE_SCALE = conf("economy.stake_scale", 0.35)   # множитель доходности стейкинга
DAILY = {"USDT": 0.007,   # USDT не меняет курс — доход без риска и без лимита суммы, поэтому ставка ниже
          "BTC": 0.03, "ETH": 0.035, "SOL": 0.04, "DOGE": 0.045, "GRAM": 0.05, "NOT": 0.06}
DAILY = {k: v * STAKE_SCALE for k, v in DAILY.items()}
STAKE_CAP = 86400   # награда копится максимум сутки с последнего сбора — потом надо забрать (как доход с подарков)
APY = {k: v * 365 for k, v in DAILY.items()}
YEAR = 365 * 86400


def _earned(sk, t):
    return sk["earned"] + sk["qty"] * APY[sk["asset"]] * min(STAKE_CAP, max(0, t - sk["ts"])) / YEAR


def _accrue(uid, aid, t):
    """Досчитать награду до текущего момента и вернуть строку стейка (или None)."""
    sk = q1("SELECT * FROM crypto_stake WHERE user=? AND asset=?", uid, aid)
    if sk:
        db.execute("UPDATE crypto_stake SET earned=?, ts=? WHERE user=? AND asset=?", (_earned(sk, t), t, uid, aid))
        sk = q1("SELECT * FROM crypto_stake WHERE user=? AND asset=?", uid, aid)
    return sk


def _to_wallet(uid, aid, qty, cost):
    db.execute("INSERT INTO crypto(user,asset,qty,cost) VALUES(?,?,?,?) ON CONFLICT(user,asset) DO UPDATE SET qty=qty+?, cost=cost+?",
               (uid, aid, qty, cost, qty, cost))


@app.post(R + "/crypto/{aid}/stake")
async def crypto_stake(aid: str, req: Request, uid=Depends(auth)):
    aid = _asset(aid)[0]
    pct = float((await req.json()).get("pct", 100))
    if not 0 < pct <= 100:
        err("Неверная доля")
    with tx():
        h = q1("SELECT * FROM crypto WHERE user=? AND asset=?", uid, aid)
        if not h or h["qty"] <= 0:
            err("Сначала купи эту монету")
        qty, cost = h["qty"] * pct / 100, h["cost"] * pct / 100
        t = now()
        _accrue(uid, aid, t)
        db.execute("UPDATE crypto SET qty=?, cost=? WHERE user=? AND asset=?", (max(0, h["qty"] - qty) if pct < 100 else 0, h["cost"] - cost if pct < 100 else 0, uid, aid))
        db.execute("INSERT INTO crypto_stake(user,asset,qty,cost,earned,total,ts) VALUES(?,?,?,?,0,0,?) ON CONFLICT(user,asset) DO UPDATE SET qty=qty+?, cost=cost+?",
                   (uid, aid, qty, cost, t, qty, cost))
    return {"ok": True, "qty": qty}


@app.post(R + "/crypto/{aid}/unstake")
def crypto_unstake(aid: str, uid=Depends(auth)):
    aid = _asset(aid)[0]
    with tx():
        sk = _accrue(uid, aid, now())
        if not sk or (sk["qty"] <= 0 and sk["earned"] <= 0):
            err("В стейкинге пусто")
        _to_wallet(uid, aid, sk["qty"] + sk["earned"], sk["cost"])
        db.execute("UPDATE crypto_stake SET qty=0, cost=0, earned=0, total=total+? WHERE user=? AND asset=?", (sk["earned"], uid, aid))
    return {"ok": True, "qty": sk["qty"] + sk["earned"]}


@app.post(R + "/crypto/stake/claim")
def crypto_claim(uid=Depends(auth)):
    """Забрать награды всех стейков в кошелёк (стейк продолжает работать)."""
    got = {}
    with tx():
        t = now()
        tax_st = 0
        for r in q("SELECT asset FROM crypto_stake WHERE user=?", uid):
            sk = _accrue(uid, r["asset"], t)
            if sk["earned"] > 0:
                net = sk["earned"] * (1 - STAKE_TAX)
                if sk["asset"] in PX:
                    tax_st += (sk["earned"] - net) * PX[sk["asset"]]["usd"] / STAR_USD
                _to_wallet(uid, sk["asset"], net, 0)
                db.execute("UPDATE crypto_stake SET earned=0, total=total+? WHERE user=? AND asset=?", (net, uid, sk["asset"]))
                got[sk["asset"]] = net
        if int(tax_st):
            event(uid, "fee", -int(tax_st))
    if not got:
        err("Награды пока нет")
    value = sum(v * (PX[a]["usd"] / STAR_USD if a in PX else 0) for a, v in got.items())
    return {"ok": True, "got": got, "value": value}


# ============================================================ обмен монета → монета
SWAP_FEE = conf("economy.swap_fee", 0.005)   # обмен монета → монета


@app.post(R + "/crypto/{aid}/swap")
async def crypto_swap(aid: str, req: Request, uid=Depends(auth)):
    aid = _asset(aid)[0]
    b = await req.json()
    to, pct = _asset(str(b.get("to", "")))[0], float(b.get("pct", 100))
    if to == aid:
        err("Выбери другую монету")
    if not 0 < pct <= 100:
        err("Неверная доля")
    pa, pb = await asyncio.gather(fresh(aid), fresh(to))
    with tx():
        h = q1("SELECT * FROM crypto WHERE user=? AND asset=?", uid, aid)
        if not h or h["qty"] <= 0:
            err("У тебя нет этой монеты")
        qty = h["qty"] if pct >= 100 else h["qty"] * pct / 100
        value = qty * pa
        if value < MIN_TRADE:
            err(f"Минимум на ⭐ {MIN_TRADE}")
        cost = h["cost"] if pct >= 100 else h["cost"] * pct / 100
        got = value * (1 - SWAP_FEE) / pb
        db.execute("UPDATE crypto SET qty=?, cost=? WHERE user=? AND asset=?", (0 if pct >= 100 else h["qty"] - qty, 0 if pct >= 100 else h["cost"] - cost, uid, aid))
        _to_wallet(uid, to, got, cost)
        db.execute("INSERT INTO crypto_tx(user,asset,side,qty,price,stars,ts) VALUES(?,?,?,?,?,?,?)", (uid, aid, "swap", qty, pa, int(value), now()))
        db.execute("INSERT INTO crypto_tx(user,asset,side,qty,price,stars,ts) VALUES(?,?,?,?,?,?,?)", (uid, to, "swapin", got, pb, int(value), now()))
    return {"ok": True, "got": got, "to": to}


# ============================================================ фьючерсы: лонг/шорт с плечом
LEVS = [2, 5, 10, 25, 50]
FUT_FEE = conf("economy.fut_fee", 0.002)   # от объёма позиции при открытии и закрытии фьючерса
STAKE_TAX = 0.0         # налог с наград стейкинга (часть монет) — меняется в админке, fees.py
LIQ = 0.9               # ликвидация, когда убыток съел 90% маржи
MAX_POS = 10
MIN_MARGIN = 50
FUT_ASSETS = [a[0] for a in ASSETS if a[0] != "USDT"]


def _liq_price(side, entry, lev):
    return entry * (1 - LIQ / lev) if side == "long" else entry * (1 + LIQ / lev)


def _pnl(pos, price):
    d = 1 if pos["side"] == "long" else -1
    return pos["qty"] * (price - pos["entry"]) * d


def _pos_view(r, price=None):
    o = {k: r[k] for k in ("id", "asset", "side", "lev", "margin", "entry", "qty", "ts", "status")}
    o["liq"] = _liq_price(r["side"], r["entry"], r["lev"])
    if r["status"] == "open":
        o["mark"] = price
        o["pnl"] = _pnl(r, price) if price else 0
    else:
        o["mark"], o["pnl"], o["closed"] = r["close"], r["pnl"], r["closed"]
    o["roe"] = o["pnl"] / r["margin"] * 100
    return o


def liquidate_all():
    """Проверка всех открытых позиций по свежим курсам (из crypto_loop)."""
    hit = []
    with tx():
        for r in q("SELECT * FROM crypto_pos WHERE status='open'"):
            p = PX.get(r["asset"])
            if not p:
                continue
            price = p["usd"] / STAR_USD
            if _pnl(r, price) <= -LIQ * r["margin"]:
                db.execute("UPDATE crypto_pos SET status='liq', close=?, pnl=?, closed=? WHERE id=?", (price, -r["margin"], now(), r["id"]))
                hit.append(r)
    for r in hit:
        notify(r["user"], f"Позиция {r['asset']} x{r['lev']} {'лонг' if r['side'] == 'long' else 'шорт'} ликвидирована — маржа ⭐ {r['margin']} сгорела.")
    return hit


@app.get(R + "/futures")
def futures(uid=Depends(auth)):
    t = now()
    assets = []
    for aid in FUT_ASSETS:
        b = _brief(aid)
        c = CHART.get((aid, "1H", 24))
        b["spark"] = [round(v / STAR_USD, 6) for _, v in c[1]] if c else []
        assets.append(b)
    pos = [_pos_view(r, PX[r["asset"]]["usd"] / STAR_USD if r["asset"] in PX else None)
           for r in q("SELECT * FROM crypto_pos WHERE user=? AND status='open' ORDER BY id DESC", uid)]
    hist = [_pos_view(r) for r in q("SELECT * FROM crypto_pos WHERE user=? AND status!='open' ORDER BY closed DESC LIMIT 15", uid)]
    real = q1("SELECT COALESCE(SUM(pnl),0) s, COUNT(*) n, SUM(pnl>0) w FROM crypto_pos WHERE user=? AND status!='open'", uid)
    top = []
    for r in q("SELECT user, SUM(pnl) s FROM crypto_pos WHERE status!='open' GROUP BY user HAVING s>0 ORDER BY s DESC LIMIT 5"):
        u = q1("SELECT * FROM users WHERE id=?", r["user"])
        if u:
            top.append({**user_brief(u), "pnl": r["s"]})
    return {"assets": assets, "positions": pos, "history": hist, "levs": LEVS, "fee": FUT_FEE, "liq": LIQ, "min": MIN_MARGIN,
            "maxPos": MAX_POS, "stats": {"pnl": real["s"], "trades": real["n"], "wins": real["w"] or 0}, "top": top, "stars": bal(uid), "now": t}


@app.post(R + "/futures/open")
async def futures_open(req: Request, uid=Depends(auth)):
    b = await req.json()
    aid = _asset(str(b.get("asset", "")))[0]
    side, lev, margin = b.get("side"), int(b.get("lev", 0)), int(b.get("margin", 0))
    if aid not in FUT_ASSETS or side not in ("long", "short") or lev not in LEVS:
        err("Неверные параметры")
    if margin < MIN_MARGIN:
        err(f"Минимальная маржа ⭐ {MIN_MARGIN}")
    price = await fresh(aid)
    notional = margin * lev
    fee = math.ceil(notional * FUT_FEE)
    with tx():
        if q1("SELECT COUNT(*) n FROM crypto_pos WHERE user=? AND status='open'", uid)["n"] >= MAX_POS:
            err(f"Не больше {MAX_POS} открытых позиций")
        if bal(uid) < margin + fee:
            err("Не хватает звёзд")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (margin + fee, uid))
        cur = db.execute("INSERT INTO crypto_pos(user,asset,side,lev,margin,entry,qty,ts) VALUES(?,?,?,?,?,?,?,?)",
                         (uid, aid, side, lev, margin, price, notional / price, now()))
        event(uid, "futures", -(margin + fee))
    return {"ok": True, "id": cur.lastrowid, "entry": price, "fee": fee, "liq": _liq_price(side, price, lev), "stars": bal(uid)}


@app.post(R + "/futures/{pid}/close")
async def futures_close(pid: int, uid=Depends(auth)):
    r = q1("SELECT * FROM crypto_pos WHERE id=? AND user=?", pid, uid)
    if not r or r["status"] != "open":
        err("Позиция уже закрыта")
    price = await fresh(r["asset"])
    with tx():
        r = q1("SELECT * FROM crypto_pos WHERE id=? AND user=? AND status='open'", pid, uid)
        if not r:
            err("Позиция уже закрыта")
        pnl = _pnl(r, price)
        if pnl <= -LIQ * r["margin"]:
            payout, status, pnl = 0, "liq", -r["margin"]
        else:
            payout, status = max(0, int(r["margin"] + pnl - r["qty"] * price * FUT_FEE)), "closed"
        db.execute("UPDATE crypto_pos SET status=?, close=?, pnl=?, closed=? WHERE id=?", (status, price, int(payout - r["margin"]) if status == "closed" else pnl, now(), pid))
        if payout:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (payout, uid))
            event(uid, "futures", payout)
    return {"ok": True, "payout": payout, "pnl": int(payout - r["margin"]), "status": status, "stars": bal(uid)}
