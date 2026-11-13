"""Живые цены скинов CS с market.csgo.com и пересчёт шансов кейсов под них.

Зачем: цены скинов в data.json записаны один раз, а рынок двигается. Подешевел частый приз или подорожал редкий —
кейс начинает возвращать не столько, сколько задумано, и вывод скинов может уйти в минус.

Как работает:
  · раз в pwr.prices_min минут сервер забирает общий прайс площадки (prices/USD.json — один запрос на все предметы, ключ не нужен)
    и кладёт цену каждого нашего скина в таблицу cs_prices;
  · скачок цены больше чем в JUMP раз принимается только со второго раза подряд (защита от случайного лота);
  · цена кейса в ⭐ не меняется. Меняются шансы: показатель степени в формуле веса (1000 / цена)^e подбирается так, чтобы
    средний приз остался той же долей цены кейса, что была заложена изначально (отдельно для FREE / PWR / VIP);
  · выпавший скин получает ценность по живой цене (× pwr.usd_coins), по ней же он потом продаётся игре и выводится;
  · скина нет на площадке дольше KEEP_H часов — он убирается из кейсов (его всё равно не вывести); осталось меньше половины
    состава или самый дешёвый приз стал дороже положенного возврата — кейс встаёт на паузу;
  · площадка не отвечает — кейсы работают по последним известным ценам (после перезапуска — из таблицы), админам уходит сообщение.
Пока прайс ни разу не получен, всё работает по ценам из data.json, как раньше."""
import asyncio
import os
import time

import economy as E
import app as A
from app import app, db, notify, now, q, tx
from settings import conf

URL = os.environ.get("MARKET_PRICES_URL", "https://market.csgo.com/api/v2/prices/USD.json")   # MARKET_PRICES_URL — только для тестов
ON = conf("pwr.prices_on", True)
EVERY = int(os.environ.get("CS_PRICES_EVERY") or conf("pwr.prices_min", 15) * 60)
KEEP_H = conf("pwr.prices_keep_hours", 24)       # сколько часов верим последней цене скина, которого сейчас нет на площадке
JUMP = 1.5                                       # скачок цены больше чем в столько раз — только со второго раза подряд
MAX_RTP = 0.95                                   # возврат выше этого удержать шансами нельзя — кейс на паузе

db.execute("CREATE TABLE IF NOT EXISTS cs_prices(col TEXT PRIMARY KEY, usd REAL, cand REAL DEFAULT 0, ts INTEGER)")

MH = {c: d["mh"] for c, d in E.PWR["cols"].items() if d.get("mh")}                    # скин → торговое имя на площадке
ORIG = {d["id"]: [(c, u) for c, u in d["items"] if c in E.CATALOG] for d in E.PWR["cases"]}   # состав кейсов с исходными ценами
CASE_USD = {d["id"]: d["usd"] for d in E.PWR["cases"]}
LIVE = {r["col"]: (r["usd"], r["ts"]) for r in q("SELECT col, usd, ts FROM cs_prices WHERE usd>0")}
STATE = {"ts": 0, "ok": bool(LIVE), "fails": 0, "said": 0, "log": "", "paused": {}}


def _ev(items, e):
    w = [(1000 / u) ** e for _, u in items]
    return sum(u * x for (_, u), x in zip(items, w)) / sum(w)


# возврат, заложенный в каждый кейс изначально (по ценам data.json): его и держим при любых ценах
SID = {d["id"]: d["sid"] for d in E.PWR["cases"]}
BASE_RTP = {cid: {t: _ev(items, 2.5 - k) / CASE_USD[cid] for t, k in E.CASE_COEFS[SID[cid]].items()} for cid, items in ORIG.items()}


def cur(col, default=None):
    """Живая цена скина в $; default — если живой нет (ни разу не получали или давно пропал с площадки)."""
    p = LIVE.get(col)
    return p[0] if p and now() - p[1] < KEEP_H * 3600 else default


def _solve(items, target):
    """Показатель e для весов (1000 / цена)^e, при котором средний приз равен target. Больше e — чаще дешёвые призы."""
    lo, hi = 0.2, 9.0
    if _ev(items, lo) <= target:
        return lo
    if _ev(items, hi) >= target:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        if _ev(items, mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def apply():
    """Пересобрать кейсы скинов под текущие цены. Пока живых цен нет совсем — ничего не трогаем."""
    if not STATE["ok"]:
        return
    paused = {}
    for cid, orig in ORIG.items():
        items = [(c, p) for c, p in ((c, cur(c)) for c, _ in orig) if p]
        price = CASE_USD[cid]
        if len(items) < max(5, len(orig) // 2):
            paused[cid] = "мало скинов на площадке"
        elif min(u for _, u in items) > MAX_RTP * price:
            paused[cid] = "самый дешёвый скин дороже кейса"
        if cid in paused:
            E.CASES[cid]["paused"] = True
            continue
        w = {t: [(1000 / u) ** _solve(items, r * price) for _, u in items] for t, r in BASE_RTP[cid].items()}
        if _ev(items, _solve(items, BASE_RTP[cid]["VIP"] * price)) > MAX_RTP * price:
            paused[cid] = "призы подорожали сильнее, чем можно удержать шансами"
            E.CASES[cid]["paused"] = True
            continue
        E.PWR_CASES[cid] = {"items": items, "w": w}          # замена целиком: открытие кейса в соседнем потоке видит либо старое, либо новое
        odds = E.pwr_odds(cid)
        cum, acc = [], 0.0
        for x in odds.values():
            acc += x
            cum.append(acc)
        E.CASES[cid].update(cols=list(odds), cum=cum, odds=odds, evs={c: E.usd_coins(u) for c, u in items}, paused=False)
    for col in MH:
        p = cur(col)
        if p:
            E.PWR["cols"][col]["usd"] = p
            E.BASE[col] = E.usd_coins(p)
    STATE["paused"] = paused
    line = f"csprices: живых цен {sum(1 for c in MH if cur(c))} из {len(MH)}, кейсов работает {len(ORIG) - len(paused)} из {len(ORIG)}" \
           + (", на паузе: " + ", ".join(f"{E.CASES[c]['title']} ({w})" for c, w in paused.items()) if paused else "")
    if line != STATE["log"]:
        STATE["log"] = line
        print(line, flush=True)


def _parse(data):
    """Прайс площадки → {торговое имя: цена в $}. Формат терпим к вариантам: список записей или словарь."""
    items = data.get("items") or data.get("data") or []
    out = {}
    rows = items.items() if isinstance(items, dict) else ((None, x) for x in items)
    for k, x in rows:
        try:
            name = k or x.get("market_hash_name") or x.get("hash_name")
            p = float(x.get("price") if isinstance(x, dict) else x)
        except (TypeError, ValueError, AttributeError):
            continue
        if name and p > 0 and (name not in out or p < out[name]):
            out[name] = p
    return out


def _unit(prices):
    """В каких единицах цены прайса: сверяем с нашими исходными ценами по медиане (1 — доллары, 100 — центы, 1000 — тысячные)."""
    base = {MH[c]: u for items in ORIG.values() for c, u in items if c in MH}
    ratios = sorted(prices[n] / u for n, u in base.items() if n in prices and u > 0)
    if len(ratios) < 30:
        return 0
    med = ratios[len(ratios) // 2]
    for k in (1, 100, 1000):
        if 0.25 * k < med < 4 * k:
            return k
    return 0


async def refresh():
    r = await A.http.get(URL, timeout=90)
    data = r.json()
    if str(data.get("currency") or "USD").upper() != "USD":
        raise ValueError(f"прайс в валюте {data.get('currency')}")
    prices = _parse(data)
    k = _unit(prices)
    if not k:
        raise ValueError(f"прайс не похож на цены в долларах (позиций {len(prices)})")
    t, n = now(), 0
    with tx():
        old = {r["col"]: r for r in q("SELECT * FROM cs_prices")}
        for col, mh in MH.items():
            p = prices.get(mh)
            if not p:
                continue
            p = round(p / k, 4)
            o = old.get(col)
            if o and o["usd"] > 0 and not 1 / JUMP <= p / o["usd"] <= JUMP:
                c = o["cand"] or 0
                if not (c > 0 and 1 / 1.15 <= p / c <= 1.15):   # первый раз видим такой скачок: запоминаем и ждём подтверждения
                    db.execute("UPDATE cs_prices SET cand=? WHERE col=?", (p, col))
                    continue
            db.execute("INSERT OR REPLACE INTO cs_prices(col,usd,cand,ts) VALUES(?,?,0,?)", (col, p, t))
            LIVE[col] = (p, t)
            n += 1
    STATE.update(ts=t, ok=True, fails=0)
    apply()
    return n


async def loop():
    await asyncio.sleep(5)
    while True:
        try:
            await refresh()
        except Exception as e:
            STATE["fails"] += 1
            print("csprices:", type(e).__name__, str(e)[:200], flush=True)
            if STATE["fails"] >= 4 and now() - STATE["said"] > 6 * 3600:   # час без цен
                STATE["said"] = now()
                for aid in A.ADMINS:
                    notify(aid, f"🛠 Цены скинов CS не обновляются уже {STATE['fails'] * EVERY // 60} мин ({A.esc(str(e)[:120])}). "
                                "Кейсы работают по последним известным ценам.")
        await asyncio.sleep(EVERY)


@app.on_event("startup")
async def _start():
    if not ON:
        return
    try:
        apply()            # после перезапуска — сразу по ценам из таблицы
    except Exception as e:
        print("csprices apply:", type(e).__name__, e, flush=True)
    asyncio.create_task(loop())
