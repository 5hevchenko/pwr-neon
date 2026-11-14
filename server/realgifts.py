"""Все кейсы подарков — с настоящими подарками Telegram: приз можно продать игре за полную цену или вывести на свой аккаунт.

Кейсы — те же, что были в игре (названия, обложки, цены, состав коллекций), но внутри теперь настоящие призы:
  · обычные подарки Telegram (15–100 Stars): бот покупает их у Telegram и дарит игроку (Bot API sendGift) со своего баланса Stars,
    поэтому цена подарка в Stars равна его цене в игре один к одному (15 Stars = 15 000 ⭐);
  · коллекционные подарки из состава кейса (Lol Pop, Love Candle…): цена — рыночная (Portals или Tonnel) + комиссия 10%, в TON по курсу;
    в ⭐ она переводится через withdraw.xtr_usd — сколько долларов приносит нам 1 Telegram Star;
  · звёзды ⭐: в кейсах, которые стоят дешевле самого дешёвого подарка, частый приз — часть цены кейса звёздами, а подарок — редкий.
Склада нет: подарок покупается только в момент вывода и только когда игрок сам об этом попросил.

Как считаются шансы. Цена кейса твёрдая, от живых цен подарков меняются шансы: кейс всегда возвращает призами rtp (0,60) своей цены.
  · если 60% цены кейса не меньше самого дешёвого подарка — в кейсе только подарки, вес приза = (1 / цена)^k, а k подбирается так,
    чтобы средний приз был ровно 60% цены: дешёвые подарки выпадают часто, дорогие — редко;
  · если кейс дешевле — звёздами возвращается в среднем fill_ev (37%) цены, а подарки (между собой с весом (1/цена)^k_fill) получают
    ровно такой общий шанс, чтобы вместе вышло 60%. Подарок дороже кейса в десятки и тысячи раз — с крошечным шансом;
  · призы, которых мало для дорогого кейса, отбрасываются снизу; не набралось — кейс на паузе, пока нет цен дорогих подарков.
Защита
  · вывод — в общем со скинами лимите (withdraw.py): только после покупок и не больше оплаченного × limit_k, свежие пополнения
    в лимит не идут hold_hours часов. Это жёсткий потолок реальных выплат при любых бонусах и бесплатных ⭐;
  · на выводе цена проверяется ещё раз: подорожал больше чем в slip раз — отказ, приз остаётся в сумке (продать его можно всегда);
  · не получилось купить или подарить — приз возвращается в сумку; ответа нет и исход неизвестен — заявку разбирает админ.
Ключи: TONNEL_AUTH (и TONNEL_PROXY) — переменные окружения, см. tonnel.py. Без них коллекционные подарки выдаёт админ вручную."""
from settings import S
import asyncio
import hashlib
import os
import sys
import random
import statistics
import time
import urllib.parse

from fastapi import Depends, Request
from fastapi.responses import FileResponse, Response

import app as A
import economy as E
import fair
import shop
import tonnel as T
import withdraw as W
from admin import admin
from app import DEV, R, TOKEN, app, auth, bal, db, err, esc, event, notify, now, q, q1, tx
from settings import conf

ON = conf("realgifts.on", True)
RTP = conf("realgifts.rtp", 0.87)                       # доля цены кейса, которая в среднем возвращается призами
REFRESH = int(conf("realgifts.refresh_min", 10) * 60)   # как часто обновлять цены
MAX_AGE = int(conf("realgifts.max_age_min", 40) * 60)   # цена старше — приз убирается из кейса
SLIP = conf("realgifts.slip", 1.15)                     # на выводе приз может стоить не больше цены выигрыша × slip
NFT_MODE = conf("realgifts.nft_mode", "auto")           # коллекционные: auto — покупает сервер (нет сессии площадки — заявка админу), manual — всегда админ, off — выключены
RTP_FREE = conf("realgifts.rtp_free", 0.70)             # тот же возврат для игроков без единого пополнения. Правило открытое: оно написано
                                                        # в окне кейса и в справке («у игроков с пополнением шансы на дорогие призы выше»)
PRICE_K = conf("realgifts.price_k", 1000)                # цены кейсов в описаниях — в целых ⭐ (1 ⭐ = 1 Telegram Star); в игре звёзды хранятся в тысячных
MARKUP = conf("realgifts.markup", 1.45)                 # приз оценивается в ⭐ дороже, чем стоит нам в Telegram Stars: подарок за 15 Stars — 22 ⭐
STARS = conf("realgifts.stars", [15, 100])              # какие обычные подарки кладём в кейсы: цена в Telegram Stars, от и до
MAX_USD = conf("realgifts.max_usd", 600.0)              # коллекционные дороже в кейсы не кладём: такой приз нечем обеспечить
K_FILL = conf("realgifts.k_fill", 1.5)                  # вес подарков между собой в дешёвых кейсах: (1 / цена)^k
FILL = conf("realgifts.fill", [[0.1, 47.0], [0.3, 29.0], [0.6, 14.0], [1.2, 8.0], [3.0, 2.0]])   # призы звёздами: [доля цены кейса, вес]
FREE_EV = conf("realgifts.free_ev", 300)                # средний приз бесплатного кейса, ⭐
HIDE = set(conf("realgifts.hide", ["csgo", "csgo2", "brawl", "mc"]))   # игровые кейсы без настоящих призов — убраны с витрины
FEE = T.FEE                                             # комиссия площадки, закладывается в цену коллекционного подарка
FREE_GIFTS = conf("realgifts.free_gifts", True)         # в бесплатном кейсе только подарки, без звёзд: средний приз = самый дешёвый подарок × free_over
FREE_OVER = conf("realgifts.free_over", 1.08)
MIN_REAL = 3                                            # меньше настоящих призов — кейс на паузе
TG_API = os.environ.get("TG_API_URL", "https://api.telegram.org")   # TG_API_URL, TON_RATE_URL, PORTALS_URL — только для тестов
TON_URLS = [u for u in [os.environ.get("TON_RATE_URL", "")] if u] or [
    "https://tonapi.io/v2/rates?tokens=ton&currencies=usd",
    "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"]
PORTALS = os.environ.get("PORTALS_URL", "https://portal-market.com/api/")
FILL_EV = sum(m * w for m, w in FILL) / sum(w for _, w in FILL)   # сколько цены кейса в среднем возвращают призы звёздами


def _defs():
    """Кейсы подарков из игры: всё, кроме кейсов скинов (у них свой вывод) и убранных."""
    out = []
    for cid, c in E.CASES.items():
        if c.get("src") == "cs" or cid in HIDE:
            continue
        out.append({"id": cid, "title": c["title"], "price": int(c["price"]) * PRICE_K, "level": c.get("level", 1), "gifts": list(c["cols"])})
        E.FIXED_PRICE[cid] = int(c["price"])   # цена твёрдая: курс банка и акции на неё не действуют, иначе съедут шансы
    return out


CASES = _defs()
IDS = {c["id"] for c in CASES}
PRICES = {c["id"]: c["price"] for c in CASES}   # цена кейса в единицах игры (для витрины кейсов); _build может её снизить


db.execute("CREATE TABLE IF NOT EXISTS real_case_price(cid TEXT PRIMARY KEY, price INTEGER, ts INTEGER)")
for _r in q("SELECT cid, price FROM real_case_price"):
    if _r["cid"] in PRICES and 0 < _r["price"] < PRICES[_r["cid"]]:
        PRICES[_r["cid"]] = _r["price"]


def _keep_price(cid, price):
    with tx():
        db.execute("INSERT OR REPLACE INTO real_case_price(cid,price,ts) VALUES(?,?,?)", (cid, price, now()))


# ---- ключи. Ключ открывает кейс бесплатно, а призы в кейсах подарков настоящие, поэтому ключ действует только на дешёвые кейсы:
# ключ от кейса дороже KEY_MAX превращается в ключ от самого дешёвого платного кейса (иначе награда «за серию входов»
# стоила бы тысячи звёзд).
KEY_MAX = conf("realgifts.key_max", 100) * shop.RATE


KEY_CASE = conf("realgifts.key_case", "tier_01")   # кейс, который открывают все ключи-награды


def key_case():
    if KEY_CASE in PRICES and 0 < PRICES[KEY_CASE] <= KEY_MAX:
        return KEY_CASE
    work = [b for b in _BUILT.values() if not b["paused"] and b["price"] > 0]
    return min(work, key=lambda b: b["price"])["id"] if work else KEY_CASE


def key_cid(cid):
    """Какой кейс на самом деле откроет ключ от кейса cid."""
    return key_case() if cid in IDS and PRICES.get(cid, 0) > KEY_MAX else cid


def remap_keys():
    """Награды-ключи (серия входов, топ богачей, альбом, цели клана, возврат, подарок от друга, наборы) объявлены от дорогих кейсов.
    Сводим их к кейсу, который ключ реально открывает, чтобы в текстах и в сумке был один и тот же кейс."""
    m = sys.modules
    try:
        for d, c in list(A.STREAK_KEYS.items()):
            A.STREAK_KEYS[d] = key_cid(c)
        for d, (amt, c) in list(A.STREAK_MS.items()):
            A.STREAK_MS[d] = (amt, key_cid(c))
        if "rich" in m:
            for k, c in list(m["rich"].DAILY_KEY.items()):
                m["rich"].DAILY_KEY[k] = key_cid(c)
        if "album" in m:
            m["album"].TIERS[:] = [(a, b, key_cid(c) if c else c) for a, b, c in m["album"].TIERS]
        if "clans" in m:
            m["clans"].GOALS[:] = [(a, key_cid(c)) for a, c in m["clans"].GOALS]
            m["clans"].KEY_SHOP[:] = list(dict.fromkeys(key_cid(c) for c in m["clans"].KEY_SHOP))
        if "retain" in m:
            m["retain"].TIERS[:] = [(a, b, key_cid(c), d, e) for a, b, c, d, e in m["retain"].TIERS]
        if "refs" in m:
            m["refs"].GIFT_CASE = key_cid(m["refs"].GIFT_CASE)
        if "premium" in m:
            m["premium"].OFFERS[:] = [(a, b, key_cid(c)) for a, b, c in m["premium"].OFFERS]
    except Exception as e:
        print("realgifts remap_keys:", type(e).__name__, e, flush=True)


def fix_keys(uid=None):
    """Перевести ключи от дорогих кейсов подарков в ключи от самого дешёвого. uid=None — у всех игроков."""
    big = [cid for cid in IDS if PRICES.get(cid, 0) > KEY_MAX]
    if not big:
        return
    to = key_case()
    if PRICES.get(to, 0) > KEY_MAX:
        return
    marks = ",".join("?" * len(big))
    who = "" if uid is None else " AND user=?"
    args = tuple(big) + (() if uid is None else (uid,))
    if not q1(f"SELECT 1 FROM case_keys WHERE n>0 AND cid IN ({marks}){who} LIMIT 1", *args):
        return
    with tx():
        for r in q(f"SELECT user, SUM(n) n FROM case_keys WHERE n>0 AND cid IN ({marks}){who} GROUP BY user", *args):
            db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,?) ON CONFLICT(user,cid) DO UPDATE SET n=n+?", (r["user"], to, r["n"], r["n"]))
        db.execute(f"UPDATE case_keys SET n=0 WHERE cid IN ({marks}){who}", args)


def _nice(x):
    """Круглая цена кейса в единицах игры: до 100 ⭐ — шаг 5, до 1000 — 25, до 10 000 — 250, дальше — 2500."""
    v = x / shop.RATE
    step = 5 if v < 100 else 25 if v < 1000 else 250 if v < 10000 else 2500
    return int(v // step * step) * shop.RATE


def _value(stars_cost):
    """Ценность приза в игре: себестоимость в Telegram Stars × MARKUP, в целых ⭐."""
    return int(stars_cost * MARKUP + 0.5) * shop.RATE
NAMES = sorted({n for c in CASES for n in c["gifts"] if n in E.NATIVE})

db.execute("CREATE TABLE IF NOT EXISTS real_items(id INTEGER PRIMARY KEY AUTOINCREMENT, user INTEGER, kind TEXT, ref TEXT, title TEXT, xtr INTEGER, "
           "value INTEGER, usd REAL, cid TEXT, paid INTEGER, status TEXT, cost REAL DEFAULT 0, note TEXT DEFAULT '', ts INTEGER, upd INTEGER)")
db.execute("CREATE INDEX IF NOT EXISTS real_items_user ON real_items(user, status)")
db.execute("CREATE TABLE IF NOT EXISTS real_prices(k TEXT PRIMARY KEY, v REAL, lo REAL, ts INTEGER)")

_CAT = {"ts": 0, "items": []}                 # обычные подарки, которые Telegram продаёт сейчас
_THUMBS = set()                               # у каких из них есть картинка
_NFT = {}                                     # название → {"ton": цена для расчёта, "lo": самое дешёвое предложение, "ts", "cand"}
_TON = {"usd": 0.0, "ts": 0}                  # курс TON
_BOT = {"stars": None, "ts": 0}               # баланс бота в Telegram Stars
_TN = {"bal": None, "ts": 0, "fails": 0, "err": ""}   # сессия и баланс площадки
_BUILT = {}                                   # собранные кейсы
_ALERT = {}                                   # когда о чём писали админам
_FEED = {}                                    # состояние источников цен
for _r in q("SELECT * FROM real_prices"):     # цены переживают перезапуск вместе со своим возрастом
    if _r["k"] == "ton":
        _TON.update(usd=_r["v"], ts=_r["ts"])
    elif _r["k"].startswith("nft:"):
        _NFT[_r["k"][4:]] = {"ton": _r["v"], "lo": _r["lo"] or _r["v"], "ts": _r["ts"], "cand": 0}


def enabled():
    return bool(ON and (not DEV or "TG_API_URL" in os.environ))


def nft_auto():
    """Сервер сам покупает коллекционные подарки на площадке."""
    return NFT_MODE == "auto" and T.has_session() and _TN["ts"] > 0 and _TN["fails"] < 3


def nft_ready():
    """Коллекционные подарки можно класть в кейсы: их купит сервер или выдаст админ по заявке."""
    return NFT_MODE in ("auto", "manual")


def _fresh(ts, k=1):
    return time.time() - ts <= MAX_AGE * k


async def _tg(method, **params):
    r = await A.http.post(f"{TG_API}/bot{TOKEN}/{method}", json=params, timeout=40)
    return r.json()


def alert(key, text, every=3600):
    """Сообщение админам, не чаще раза в every секунд на один повод."""
    if time.time() - _ALERT.get(key, 0) < every:
        return
    _ALERT[key] = time.time()
    for aid in A.ADMINS:
        notify(aid, "🛠 " + text)


# ---------------- цены ----------------
async def _load_catalog():
    r = await _tg("getAvailableGifts")
    if not r.get("ok"):
        raise RuntimeError(str(r.get("description")))
    items = []
    for g in r["result"]["gifts"]:
        xtr, left = int(g.get("star_count") or 0), g.get("remaining_count")
        if not xtr or (left is not None and left <= 0):
            continue
        st = g.get("sticker") or {}
        items.append({"id": str(g["id"]), "xtr": xtr, "emoji": st.get("emoji") or "🎁", "thumb": (st.get("thumbnail") or {}).get("file_id"), "left": left})
    _CAT.update(ts=time.time(), items=sorted(items, key=lambda x: (x["xtr"], x["id"])))
    _THUMBS.clear()
    _THUMBS.update(g["id"] for g in items if g["thumb"])


async def _load_ton():
    for url in TON_URLS:
        try:
            d = (await A.http.get(url, timeout=15)).json()
            v = float((d.get("rates") or {}).get("TON", {}).get("prices", {}).get("USD") or (d.get("the-open-network") or {}).get("usd") or 0)
            if 0.05 < v < 500:
                _TON.update(usd=v, ts=time.time())
                with tx():
                    db.execute("INSERT OR REPLACE INTO real_prices(k,v,lo,ts) VALUES('ton',?,?,?)", (v, v, int(time.time())))
                return
        except Exception:
            continue


def _take_price(name, offers):
    """Цена подарка для расчётов — медиана трёх самых дешёвых предложений: одно случайное или подставное предложение её не сдвигает.
    Скачок больше чем в полтора раза принимается только со второго обновления подряд."""
    if not offers:
        return
    top = [o["price"] for o in offers[:3]]
    new, lo = (statistics.median(top) if len(top) >= 3 else max(top)), top[0]
    old = _NFT.get(name)
    if old and _fresh(old["ts"]) and not 1 / 1.5 <= new / old["ton"] <= 1.5:
        if not old.get("cand") or abs(new / old["cand"] - 1) > 0.15:
            old["cand"] = new
            return
    _NFT[name] = {"ton": new, "lo": lo, "ts": time.time(), "cand": 0}
    with tx():
        db.execute("INSERT OR REPLACE INTO real_prices(k,v,lo,ts) VALUES(?,?,?,?)", ("nft:" + name, new, lo, int(time.time())))


async def _load_portals():
    """Цены всех коллекций одним запросом (открытый адрес площадки Portals, ключ не нужен). → сколько цен принято."""
    if not T.available():
        return 0
    try:
        async with T.AsyncSession(impersonate="chrome", **({"proxies": {"https": T.PROXY, "http": T.PROXY}} if T.PROXY else {})) as s:
            r = await s.get(PORTALS + "collections?limit=500", timeout=20, headers={
                "Accept": "application/json, text/plain, */*", "Origin": "https://portal-market.com", "Referer": "https://portal-market.com/"})
        if r.status_code != 200:
            raise RuntimeError(f"ответ {r.status_code}")
        rows = r.json().get("collections") or []
    except Exception as e:
        if not _FEED.get("portals_err"):
            print("realgifts portals:", type(e).__name__, e, flush=True)
        _FEED["portals_err"] = str(e)[:120] or type(e).__name__
        return 0
    want = {n.lower(): n for n in NAMES}
    n = 0
    for c in rows:
        name = want.get(str(c.get("name") or "").strip().lower())
        try:
            f = float(c.get("floor_price") or 0)
        except (TypeError, ValueError):
            f = 0
        if name and f > 0:
            _take_price(name, [{"price": f}])
            n += 1
    _FEED.update(portals_err="", portals=n, portals_ts=time.time())
    return n


async def _load_tonnel():
    bad = 0
    for name in NAMES:
        try:
            _take_price(name, await T.listings(name))
        except T.TonnelError as e:
            bad += 1
            if bad == 1 and not _FEED.get("tonnel_err"):
                print("realgifts tonnel:", name, e, flush=True)
            _FEED["tonnel_err"] = str(e)[:120]
            if bad >= 3:   # площадка недоступна — не долбим её оставшимися запросами
                return
        await asyncio.sleep(1.2)
    _FEED["tonnel_err"] = ""


async def refresh():
    if not enabled():
        return
    try:
        await _load_catalog()
    except Exception as e:
        print("realgifts catalog:", type(e).__name__, e, flush=True)
    try:
        r = await _tg("getMyStarBalance")
        if r.get("ok"):
            _BOT.update(stars=int(r["result"].get("amount") or 0), ts=time.time())
    except Exception:
        pass
    if NFT_MODE != "off" and NAMES:
        await _load_ton()
        if not await _load_portals() and T.available():
            await _load_tonnel()
        if T.has_session():
            try:
                _TN.update(bal=await T.balance(), ts=time.time(), fails=0, err="")
            except T.TonnelError as e:
                _TN.update(fails=_TN["fails"] + 1, err=str(e))
                if _TN["fails"] == 3:
                    alert("tn-session", f"Площадка Tonnel не принимает сессию ({esc(str(e))}). Заявки на коллекционные подарки теперь приходят тебе на ручную выдачу.")
    _rebuild()


# обычные подарки Telegram называются по своему эмодзи; незнакомый — «Подарок за N Stars»
TG_NAMES = {"💝": "Сердце", "🧸": "Мишка", "🎁": "Подарок", "🌹": "Роза", "🎂": "Торт", "💐": "Букет", "🚀": "Ракета", "🍾": "Шампанское",
            "🏆": "Кубок", "💍": "Кольцо", "💎": "Алмаз"}


def _real(c):
    """Настоящие призы кейса со свежей ценой: обычные подарки и коллекционные из его состава."""
    out = []
    lo, hi = STARS[:2]
    if _fresh(_CAT["ts"]):
        for g in _CAT["items"]:
            if lo <= g["xtr"] <= hi:
                out.append({"key": "tg:" + g["id"], "kind": "tg", "ref": g["id"], "title": TG_NAMES.get(g["emoji"], f"Подарок за {g['xtr']} Stars"), "xtr": g["xtr"],
                            "usd": round(g["xtr"] * W.XTR_USD, 4), "value": _value(g["xtr"]), "emoji": g["emoji"], "img": bool(g["thumb"])})
    if nft_ready() and _fresh(_TON["ts"], 3):
        for name in c["gifts"]:
            p = _NFT.get(name)
            if p and _fresh(p["ts"]):
                usd = p["ton"] * (1 + FEE) * _TON["usd"]
                if usd <= MAX_USD:
                    out.append({"key": "nft:" + name, "kind": "nft", "ref": name, "title": name, "xtr": 0, "usd": round(usd, 4),
                                "value": _value(usd / W.XTR_USD), "emoji": "", "img": True})
    return sorted(out, key=lambda x: x["value"])


def _weights(items, k):
    lo = items[0]["value"]
    return [(lo / x["value"]) ** k for x in items]


def _ev(items, k):
    w = _weights(items, k)
    return sum(x["value"] * wi for x, wi in zip(items, w)) / sum(w)


def _solve(items, target):
    """k, при котором средний приз равен target: чем больше k, тем чаще дешёвые призы (средний приз падает)."""
    lo, hi = 0.0, 60.0
    for _ in range(70):
        mid = (lo + hi) / 2
        if _ev(items, mid) > target:
            lo = mid
        else:
            hi = mid
    return hi


def _build(c):
    """Кейс с твёрдой ценой: шансы призов подобраны так, чтобы средний приз был RTP × цена (у бесплатного — FREE_EV).
    Если призы кейса дешевле, чем нужно для его цены, цена снижается до той, которую они обеспечивают, и дальше держится."""
    price = PRICES.get(c["id"], c["price"])
    base = {"id": c["id"], "title": c["title"], "price": price, "level": c["level"], "paused": True, "items": [], "w": []}
    items = _real(c)
    if len(items) < MIN_REAL:
        return dict(base, why="нет цен подарков")
    nominal = price or FREE_EV / RTP               # от чего считаются призы звёздами
    target = RTP * nominal
    if not price and FREE_GIFTS:                    # бесплатный кейс без звёзд: почти всегда самый дешёвый подарок, изредка дороже
        target = items[0]["value"] * FREE_OVER
        nominal = target / RTP
    if target >= items[0]["value"]:                 # только подарки
        full = items                                # дешёвые призы убираем, но самый дешёвый из оставшихся всегда дешевле среднего приза —
                                                    # иначе кейс возвращал бы больше своей цены
        while len(items) > MIN_REAL and _ev(items, 0.5) < target and items[1]["value"] < target:   # дорогому кейсу дешёвые призы не нужны
            items = items[1:]
        if _ev(items, 0.0) < target:                # призы не тянут такую цену — снижаем её
            known = sum(1 for n in c["gifts"] if n in _NFT and _fresh(_NFT[n]["ts"]))
            if not nft_ready():                     # цен пока нет совсем (старт, сбой площадки): цену не трогаем, ждём
                return dict(base, why="нет цен подарков")
            if known < 0.8 * len(c["gifts"]):       # у части состава цен нет на рынке вовсе — кейс не собрать, с витрины он убран
                return dict(base, why="нет цен у части подарков", hide=True)
            if sum(1 for x in full if x["kind"] == "nft") < 3:      # почти весь состав дороже max_usd — такой кейс нечем обеспечить
                return dict(base, why="не хватает дорогих призов", hide=True)
            keep = min(5, len(full))                    # сколько призов оставляем самое меньшее: самые дорогие из состава
            price = _nice(max(_ev(full[i:], 0.5) for i in range(len(full) - keep + 1)) / RTP)
            target = RTP * price
            if price >= base["price"] or target < full[0]["value"]:
                return dict(base, why="не хватает дорогих призов")
            base["price"] = nominal = PRICES[c["id"]] = price
            _keep_price(c["id"], price)
            items = full
            while len(items) > MIN_REAL and _ev(items, 0.5) < target and items[1]["value"] < target:
                items = items[1:]
            if _ev(items, 0.0) < target:
                return dict(base, why="не хватает дорогих призов")
        k = _solve(items, target)
        w = _weights(items, k)
        tw = sum(w)
        w = [x / tw for x in w]
        if price and RTP_FREE < RTP:   # шансы для игроков без пополнений: тот же состав, дорогие призы реже
            wf = _weights(items, _solve(items, max(RTP_FREE * price, items[0]["value"] * 1.03)))
            base["wf"] = [x / sum(wf) for x in wf]
    else:                                           # частый приз — звёзды, подарки — редкие
        fw = sum(x[1] for x in FILL)
        stars = [{"key": f"star:{i}", "kind": "star", "ref": "", "title": "Звёзды", "xtr": 0, "usd": 0.0, "value": max(1, int(m * nominal)), "emoji": "⭐", "img": False}
                 for i, (m, _) in enumerate(FILL)]
        fill_ev = sum(x["value"] * f[1] for x, f in zip(stars, FILL)) / fw
        rw = _weights(items, K_FILL)
        real_ev = sum(x["value"] * wi for x, wi in zip(items, rw)) / sum(rw)
        p_real = (target - fill_ev) / (real_ev - fill_ev)
        if not 0 < p_real < 1:
            return dict(base, why="призы не сходятся с ценой")
        w = [(1 - p_real) * f[1] / fw for f in FILL] + [p_real * x / sum(rw) for x in rw]
        items = stars + items
    for x, wi in zip(items, w):
        x["p"] = wi
    ev = sum(x["value"] * x["p"] for x in items)
    return dict(base, paused=False, items=items, w=w, ev=ev, nominal=nominal,
                gift=sum(x["p"] for x in items if x["kind"] != "star"), nft=any(x["kind"] == "nft" for x in items),
                top=max(items, key=lambda x: x["value"]))


def payer(uid):
    """Пополнял ли игрок баланс хоть раз (Telegram Stars или крипта). От этого зависят шансы в кейсах подарков — правило открытое."""
    return bool(q1("SELECT 1 FROM payments WHERE user=? AND xtr>0 LIMIT 1", uid))


def hidden(cid):
    """Кейс убран с витрины: его призы дороже того, что игра может выдать (max_usd)."""
    return bool(_BUILT.get(cid, {}).get("hide"))


def _rebuild():
    for c in CASES:
        _BUILT[c["id"]] = _build(c)
    paused = [f"{b['title']} ({b.get('why')})" for b in _BUILT.values() if b["paused"]]
    line = (f"realgifts: обычных подарков {len(_CAT['items'])}, цен коллекционных {sum(1 for n in NAMES if n in _NFT and _fresh(_NFT[n]['ts']))} из {len(NAMES)} "
            f"(Portals: {_FEED.get('portals', 0)}), TON ${_TON['usd']:.3f}, кейсов работает {len(_BUILT) - len(paused)} из {len(_BUILT)}"
            + (f", на паузе: {', '.join(paused[:8])}" if paused else ""))
    over = [f"{b['title']} {b['ev'] / b['nominal'] * 100:.0f}%" for b in _BUILT.values() if not b["paused"] and b["ev"] > RTP * b["nominal"] * 1.01]
    if over:                        # такого быть не должно: кейс возвращает больше задуманного
        line += f", возврат выше нормы: {', '.join(over[:8])}"
    if _FEED.get("log") != line:   # в журнал — только когда картина изменилась
        _FEED["log"] = line
        print(line, flush=True)


def _now_usd(it):
    """Сколько приз стоит нам сейчас по ленте цен (для подсказки игроку); на выводе цена проверяется живым запросом."""
    if it["kind"] == "tg":
        return round(it["xtr"] * W.XTR_USD, 4)
    p = _NFT.get(it["ref"])
    return round(p["lo"] * (1 + FEE) * _TON["usd"], 4) if p and _TON["usd"] else it["usd"]


# ---------------- общий лимит вывода ----------------
def _used(uid):
    return q1("SELECT COALESCE(SUM(MAX(usd, cost)),0) s FROM real_items WHERE user=? AND status IN ('sending','pending','sent')", uid)["s"]


W.EXTRA_USED.append(_used)

STATUS = {"sending": "Отправляем", "pending": "Проверяем вручную — обычно до суток", "sent": "Отправлен в Telegram", "sold": "Продан"}


# ---------------- подарок из кейса = обычный подарок игры ----------------
# У каждого подарка из кейса, который лежит в сумке, есть запись-«зеркало» в общей таблице gifts (gifts.real = номер в real_items,
# src='real' — продаётся за полную цену и не приносит дохода, как скины). Поэтому он работает везде, где работают остальные
# подарки: маркет игроков, джекпот, столы, сейф, обмены, залог, витрина. Две таблицы держат в согласии триггеры:
#   зеркало сменило хозяина (маркет, выигрыш, обмен) → у настоящего подарка тот же хозяин;
#   зеркало удалено (сожгли в игре, продали банку)    → настоящий подарок сгорел;
#   настоящий подарок ушёл из сумки (вывод, продажа)  → зеркало удалено.
# Подарок из бесплатного кейса заблокирован, пока игрок не пригласит друга (need_refs): зеркала у него нет, вывести и продать нельзя.
for _sql in ("ALTER TABLE real_items ADD COLUMN need_refs INTEGER DEFAULT 0",):
    try:
        db.execute(_sql)
    except Exception:
        pass
db.executescript("""
CREATE TABLE IF NOT EXISTS rg_cols(title TEXT, ref TEXT PRIMARY KEY);
CREATE INDEX IF NOT EXISTS gifts_real ON gifts(real);
CREATE TRIGGER IF NOT EXISTS gifts_real_owner AFTER UPDATE OF owner ON gifts WHEN NEW.real IS NOT NULL AND NEW.owner >= 0
BEGIN UPDATE real_items SET user = NEW.owner WHERE id = NEW.real AND status = 'bag'; END;
CREATE TRIGGER IF NOT EXISTS gifts_real_del AFTER DELETE ON gifts WHEN OLD.real IS NOT NULL
BEGIN UPDATE real_items SET status = 'burned', upd = CAST(strftime('%s','now') AS INTEGER) WHERE id = OLD.real AND status = 'bag'; END;
CREATE TRIGGER IF NOT EXISTS real_items_gone AFTER UPDATE OF status ON real_items WHEN NEW.status != 'bag'
BEGIN DELETE FROM gifts WHERE real = NEW.id; END;
""")


def _reg(title, ref):
    """Обычный подарок Telegram → «коллекция» каталога (как скины). Возвращает (коллекция, модель)."""
    ref = str(ref)
    row = q1("SELECT title FROM rg_cols WHERE ref=?", ref)
    col = row["title"] if row else title
    m = E.reg_tg(col, ref)
    if m is None:   # название совпало с коллекцией игры
        col = title + " 🎁"
        m = E.reg_tg(col, ref)
    if not row:
        db.execute("INSERT OR IGNORE INTO rg_cols(title, ref) VALUES(?,?)", (col, ref))
    d = E.CATALOG[col]
    A.LOOK[col] = ({x[0]: x[1] for x in d["models"]}, {b[0]: b for b in d["backdrops"]}, {x[0]: x[1] for x in d["symbols"]})
    return col, m


for _r in q("SELECT title, ref FROM rg_cols ORDER BY rowid"):   # тот же порядок, что при первом появлении: имена моделей не съезжают
    _reg(_r["title"], _r["ref"])


def _look(kind, ref, title, seed):
    """Вид подарка из кейса в общей таблице: (коллекция, модель, фон, узор)."""
    rng = random.Random(f"rg:{seed}")
    if kind == "nft" and ref in E.NATIVE:   # коллекционный: на вывод покупается самый дешёвый — показываем самую частую модель
        d = E.CATALOG[ref]
        return ref, max(d["models"], key=lambda x: x[1])[0], rng.choice(d["backdrops"])[0], rng.choice(d["symbols"])[0]
    col, m = _reg(title, ref)
    d = E.CATALOG[col]
    rng = random.Random(f"rg:{ref}")   # одинаковые подарки выглядят одинаково
    return col, m, rng.choice(d["backdrops"])[0], rng.choice(d["symbols"])[0]


def friend_level():
    """До какого уровня должен дойти приглашённый, чтобы пойти в зачёт для замка бесплатного кейса (0 — достаточно зайти в игру).
    Уровень тот же, что в программе приглашений (refs: l1_level) — «активный друг». Защита от накрутки пустыми аккаунтами."""
    r = __import__("sys").modules.get("refs")
    return int(r.cfg("l1_level")) if FREE_ACTIVE and r else 0


def _refs(uid):
    """Сколько друзей игрока идут в зачёт: активные (дошли до уровня) или все зашедшие по ссылке."""
    if friend_level():
        return __import__("sys").modules["refs"]._active_count(uid)
    r = q1("SELECT refs FROM users WHERE id=?", uid)
    return (r["refs"] or 0) if r else 0


def lock_text(left):
    """Что нужно, чтобы замок снялся — одной фразой (для ошибок и уведомлений)."""
    who = "друг" if left == 1 else f"{left} друзей"
    L = friend_level()
    return (f"когда {who} по твоей ссылке {'дойдёт' if left == 1 else 'дойдут'} до {L} уровня" if L
            else f"когда {who} {'зайдёт' if left == 1 else 'зайдут'} в игру по твоей ссылке")


def _mirror(it):
    """Зеркало подарка в gifts (создаёт, если нет). Вызывать внутри транзакции."""
    g = q1("SELECT * FROM gifts WHERE real=?", it["id"])
    if g:
        return g
    col, model, bd, sym = _look(it["kind"], it["ref"], it["title"], it["id"])
    cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created,src,real) VALUES(?,?,?,?,?,?,?,?,'real',?)",
                     (it["user"], col, model, bd, sym, it["id"], it["value"], it["ts"] or now(), it["id"]))
    return q1("SELECT * FROM gifts WHERE id=?", cur.lastrowid)


def _sync(uid):
    refs = None
    for it in q("SELECT r.* FROM real_items r LEFT JOIN gifts g ON g.real=r.id WHERE r.user=? AND r.status='bag' AND g.id IS NULL", uid):
        if it["need_refs"]:
            refs = _refs(uid) if refs is None else refs
            if it["need_refs"] > refs:
                continue
        _mirror(it)


def ensure(uid):
    """У каждого открытого (не заблокированного) подарка игрока в сумке есть зеркало в gifts."""
    with A.LOCK:
        if not q1("SELECT 1 FROM real_items r LEFT JOIN gifts g ON g.real=r.id WHERE r.user=? AND r.status='bag' AND g.id IS NULL LIMIT 1", uid):
            return
        if db.in_transaction:
            _sync(uid)
        else:
            with tx():
                _sync(uid)


def unlocked_note(uid, on="join"):
    """Друг пошёл в зачёт (on: join — зашёл в игру, level — дорос до уровня): какие подарки из бесплатного кейса это открыло —
    строка для уведомления (и сразу зеркала). Событие не то, по которому считаются друзья, — пустая строка."""
    if (on == "level") != bool(friend_level()):
        return ""
    refs = _refs(uid)
    rows = q("SELECT r.title FROM real_items r LEFT JOIN gifts g ON g.real=r.id "   # замок снят, а зеркала ещё нет — значит, открылся только что
             "WHERE r.user=? AND r.status='bag' AND r.need_refs>0 AND r.need_refs<=? AND g.id IS NULL", uid, refs)
    if not rows:
        return ""
    try:
        ensure(uid)
    except Exception as e:
        print("realgifts unlock:", type(e).__name__, e, flush=True)
    names = ", ".join(esc(r["title"]) for r in rows[:3])
    return f"\n\n🔓 Подарок из бесплатного кейса открыт: <b>{names}</b>. Его можно вывести в Telegram, продать или поставить в игре."


def give(uid, x, cid, paid, need=0):
    """Выдать игроку настоящий приз x (из _real): запись в real_items и её зеркало. Возвращает (real_items, gifts или None, если заблокирован)."""
    t = now()
    cur = db.execute("INSERT INTO real_items(user,kind,ref,title,xtr,value,usd,cid,paid,status,ts,upd,need_refs) VALUES(?,?,?,?,?,?,?,?,?,'bag',?,?,?)",
                     (uid, x["kind"], x["ref"], x["title"], x["xtr"], x["value"], x["usd"], cid, paid, t, t, need))
    it = q1("SELECT * FROM real_items WHERE id=?", cur.lastrowid)
    return it, (None if need and need > _refs(uid) else _mirror(it))


def give_gift(uid, x, cid, paid):
    """То же для игр на подарках (обменник, крафт): возвращает строку gifts."""
    return give(uid, x, cid, paid)[1]


def _pool():
    seen, out = set(), []
    for x in _real({"gifts": list(NAMES)}):
        if x["key"] not in seen:
            seen.add(x["key"])
            out.append(x)
    return out


def pick_le(value):
    """Самый дорогой настоящий приз не дороже value (для крафта). Нет такого — None."""
    ok = [x for x in _pool() if x["value"] <= value]
    return max(ok, key=lambda x: x["value"]) if ok else None


def swap_targets(g):
    """Обменник: на что можно обменять подарок из кейса — другие настоящие подарки той же или чуть меньшей ценности."""
    it = q1("SELECT * FROM real_items WHERE id=?", g["real"])
    own = f"{it['kind']}:{it['ref']}" if it else ""
    out = []
    for x in sorted(_pool(), key=lambda x: -x["value"]):
        if x["key"] == own or not 0.6 * g["value"] <= x["value"] <= g["value"]:
            continue
        col, model, bd, sym = _look(x["kind"], x["ref"], x["title"], f"{g['id']}:{x['key']}")
        out.append({"col": col, "model": model, "backdrop": bd, "symbol": sym, "value": x["value"], "num": 1, "x": x})
        if len(out) >= 12:
            break
    return out


def _claim(uid, it):
    """Перед выводом, продажей и апгрейдом: подарок не заблокирован и не занят в игре или на маркете. Внутри транзакции."""
    left = (it["need_refs"] or 0) - _refs(uid)
    if left > 0:
        err(f"Подарок из бесплатного кейса откроется, {lock_text(left)}", 423)
    g = q1("SELECT * FROM gifts WHERE real=?", it["id"])
    if g:
        if g["owner"] != uid:
            err("Подарок сейчас занят — в игре, сейфе, залоге или обмене. Сначала забери его оттуда")
        if g["price"] is not None:
            err("Подарок выставлен на маркет — сначала сними его с продажи")
        A.unpin(uid, g["id"])
        A.cancel_trades_with(g["id"])


def _item(r, ctx=None):
    d = {"id": r["id"], "kind": r["kind"], "ref": r["ref"], "title": r["title"], "value": r["value"], "status": r["status"], "ts": r["ts"],
         "text": r["note"] if r["status"] == "bag" else STATUS.get(r["status"], ""), "emoji": "🎁",
         "img": r["kind"] == "nft" or r["ref"] in _THUMBS or os.path.exists(os.path.join(A.ASSET_CACHE, f"tggift_{r['ref']}.webp"))}
    if r["status"] == "bag":
        d["usd"] = _now_usd(r)
        left = (r["need_refs"] or 0) - (ctx["refs"] if ctx else _refs(r["user"])) if r["need_refs"] else 0
        if left > 0:   # из бесплатного кейса: ждёт приглашённого друга
            d["lock"] = left
        g = ctx["mir"].get(r["id"]) if ctx else q1("SELECT id, owner, price FROM gifts WHERE real=?", r["id"])
        if g:
            d["gid"] = g["id"]
            if g["owner"] != r["user"]:
                d["busy"] = "game"
            elif g["price"] is not None:
                d["busy"] = "market"
    return d


def _ctx(uid):
    return {"refs": _refs(uid), "mir": {g["real"]: g for g in q("SELECT g.id, g.owner, g.price, g.real FROM gifts g JOIN real_items r ON r.id=g.real WHERE r.user=?", uid)}}


def public_bag(uid, locked=False):
    """Подарки из кейсов в сумке игрока — для его профиля (дорогие первыми). locked — только заблокированные: остальные уже есть
    в общем списке подарков (зеркала)."""
    ctx = _ctx(uid)
    out = [_item(r, ctx) for r in q("SELECT * FROM real_items WHERE user=? AND status='bag' ORDER BY value DESC, id DESC LIMIT 60", uid)]
    return [x for x in out if x.get("lock")] if locked else out


def _pub(x):
    return {"key": x["key"], "kind": x["kind"], "ref": x["ref"], "title": x["title"], "value": x["value"], "emoji": x["emoji"], "img": x["img"]}


def tops(cid, n=3):
    """Лучшие подарки кейса — для обложки."""
    b = _BUILT.get(cid)
    if not b or b["paused"]:
        return []
    return [_pub(x) for x in sorted((x for x in b["items"] if x["kind"] != "star"), key=lambda x: -x["value"])[:n]]


def _free_in(c, u):
    """Сколько секунд до следующего бесплатного открытия (у платных кейсов — 0)."""
    if c["price"]:
        return 0
    if c["id"] in E.RU_CASES:
        return max(0, (u["ru_free_at"] or 0) + E.RU_FREE_EVERY - now())
    return max(0, (u["last_free"] or 0) + A.free_every(u) - now())


def state(uid):
    fix_keys(uid)
    ensure(uid)
    ctx = _ctx(uid)
    limit, used = W.budget(uid)
    cases = {}
    for c in CASES:
        b = _BUILT.get(c["id"])
        if b and not b["paused"]:
            cases[b["id"]] = {"price": b["price"], "tops": tops(b["id"])}
    bag = [_item(r, ctx) for r in q("SELECT * FROM real_items WHERE user=? AND status IN ('bag','sending','pending') ORDER BY id DESC LIMIT 200", uid)]
    hist = [_item(r) for r in q("SELECT * FROM real_items WHERE user=? AND status IN ('sent','sold') ORDER BY upd DESC LIMIT 15", uid)]
    return {"on": enabled(), "cases": cases, "ids": sorted(IDS), "bag": bag, "history": hist, "stars": bal(uid), "limit": limit, "used": used,
            "left": round(max(0, limit - used), 2), "held": W.held(uid), "holdHours": W.HOLD_H,
            "rtp": int(RTP * 100), "limitK": int(W.LIMIT_K * 100), "freeUsd": W.FREE_USER, "usdK": W.XTR_USD / shop.RATE / MARKUP,
            "payer": payer(uid), "freeFriends": FREE_FRIENDS, "freeLevel": friend_level()}


@app.get(R + "/realgifts")
def realgifts_state(uid=Depends(auth)):
    return state(uid)


IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}
ART_SIZE = 256


def _art_file(name):
    return os.path.join(A.ASSET_CACHE, "rgart_" + hashlib.md5(name.encode()).hexdigest() + ".webp")


def _art_make(data):
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    im.thumbnail((ART_SIZE, ART_SIZE))
    out = io.BytesIO()
    im.save(out, "WEBP", quality=82, method=4)
    return out.getvalue()


async def _art_fetch(name):
    """Картинка коллекционного подарка: один раз скачать у источника, ужать в WebP 256 px и положить на свой диск."""
    f = _art_file(name)
    if os.path.exists(f):
        return f
    try:
        if name in E.REMOTE:   # скин CS — картинка со Steam CDN
            r = await A._steam_get(f"{E.REMOTE[name]}/{ART_SIZE}fx{ART_SIZE}f")
        elif A.GIFT_ASSETS:
            r = await A.http.get(f"{A.GIFT_ASSETS}/original/{urllib.parse.quote(name)}.png?size={ART_SIZE}", timeout=30, follow_redirects=True,
                                 headers={"User-Agent": f"PWRNeon/1.0 (+t.me/{A.BOT_NAME})"})
        else:
            return None
        if r is None or r.status_code != 200:
            return None
        body = await asyncio.to_thread(_art_make, r.content)
        os.makedirs(A.ASSET_CACHE, exist_ok=True)
        tmp = f + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(body)
        os.replace(tmp, f)
        return f
    except Exception as e:
        print("realgifts art:", name, type(e).__name__, flush=True)
        return None


async def _thumb_fetch(gid):
    """Картинка обычного подарка — с серверов Telegram на свой диск."""
    f = os.path.join(A.ASSET_CACHE, f"tggift_{gid}.webp")
    if os.path.exists(f):
        return f
    g = next((x for x in _CAT["items"] if x["id"] == gid and x["thumb"]), None)
    if not g:
        return None
    try:
        r = await _tg("getFile", file_id=g["thumb"])
        d = await A.http.get(f"{TG_API}/file/bot{TOKEN}/{r['result']['file_path']}", timeout=30)
        if d.status_code != 200:
            return None
        os.makedirs(A.ASSET_CACHE, exist_ok=True)
        with open(f + ".tmp", "wb") as fh:
            fh.write(d.content)
        os.replace(f + ".tmp", f)
        return f
    except Exception:
        return None


async def warm_art():
    """Заранее сложить на диск картинки всех подарков из кейсов, чтобы игроки не ждали скачивания у источника."""
    names = [n for n in NAMES if n in _NFT and not os.path.exists(_art_file(n))]
    got = 0
    for n in names:
        got += bool(await _art_fetch(n))
        await asyncio.sleep(0.15)
    for g in _CAT["items"]:
        await _thumb_fetch(g["id"])
    if names:
        print(f"realgifts: картинки подарков на диске — скачано {got} из {len(names)} недостающих", flush=True)


@app.get(R + "/realgifts/art/{name:path}")
async def realgifts_art(name: str):
    if name not in E.CATALOG:
        return Response(status_code=404)
    f = await _art_fetch(name)
    return FileResponse(f, media_type="image/webp", headers=IMMUTABLE) if f else Response(status_code=404, headers={"Cache-Control": "no-store"})


@app.get(R + "/realgifts/img/{gid}")
async def realgifts_img(gid: str):
    if not gid.isdigit():
        return Response(status_code=404)
    f = await _thumb_fetch(gid)
    return FileResponse(f, media_type="image/webp", headers=IMMUTABLE) if f else Response(status_code=404, headers={"Cache-Control": "no-store"})


# ---------------- условия бесплатного кейса ----------------
# Открыть бесплатный кейс можно без друга: нужна только подписка на каналы (FREE_CHANNELS), если они заданы. Друг нужен, чтобы
# забрать выпавший подарок: до него подарок лежит в сумке под замком (need_refs) — не выводится, не продаётся, в играх не участвует.
# FREE_CHANNELS — через запятую: «@канал» или «id|ссылка|название» (для закрытых чатов). Бот должен быть админом в каждом,
# иначе Telegram не отвечает, подписан ли игрок. Список пуст — прокрут без условий.
db.execute("CREATE TABLE IF NOT EXISTS free_gate(user INTEGER, cid TEXT, opens INTEGER DEFAULT 0, refs_at INTEGER DEFAULT 0, "
           "PRIMARY KEY(user, cid))")
FREE_ACTIVE = conf("realgifts.free_friend_active", False)   # False — друг идёт в зачёт, как только зашёл по ссылке (второй аккаунт с того же устройства другом не считается — guard.py); True — только когда дорос до уровня программы приглашений
FREE_EACH = conf("realgifts.free_lock_each", True)       # True — каждому подарку из бесплатного кейса нужен свой новый друг; False — один друг открывает все накопленные
FREE_FRIENDS = conf("realgifts.free_friends", 1)        # сколько новых друзей нужно на каждый следующий бесплатный прокрут; 0 — условие снято
_SUB_OK = {}                                            # (игрок, канал) → время последней удачной проверки подписки


def _channels():
    out = []
    raw = os.environ.get("FREE_CHANNELS", "").strip() or os.environ.get("PWR_CHANNEL", "").strip()
    for part in [x.strip() for x in raw.split(",") if x.strip()]:
        bits = [x.strip() for x in part.split("|")]
        cid = bits[0]
        url = bits[1] if len(bits) > 1 else ("https://t.me/" + cid.lstrip("@") if cid.startswith("@") else "")
        out.append({"id": cid, "url": url, "title": bits[2] if len(bits) > 2 else cid})
    return out


async def _subscribed(uid, ch):
    """Подписан ли игрок на канал. Удачный ответ помним 10 минут, чтобы не дёргать Telegram на каждый прокрут."""
    if time.time() - _SUB_OK.get((uid, ch["id"]), 0) < 600:
        return True
    try:
        r = await A.tg_call("getChatMember", chat_id=ch["id"], user_id=uid)
    except Exception:
        return False
    res = r.get("result")
    ok = bool(r.get("ok")) and isinstance(res, dict) and res.get("status") in ("creator", "administrator", "member", "restricted")
    if not r.get("ok"):
        alert("free-ch" + ch["id"], f"Бесплатный кейс: бот не может проверить подписку на {esc(ch['id'])} "
                                    f"({esc(str(r.get('description') or 'нет ответа'))}). Сделай бота админом этого канала.")
    if ok:
        _SUB_OK[(uid, ch["id"])] = time.time()
    return ok


async def free_gate(uid, cid):
    """Что нужно сделать перед бесплатным прокрутом: подписка на каналы. Друг для открытия не нужен — он нужен, чтобы забрать
    выпавший подарок (need_refs): {ok, kind: subs, steps, friends — сколько друзей откроет подарок}."""
    chans = [] if DEV and "TG_API_URL" not in os.environ else _channels()
    steps = [{"title": ch["title"], "url": ch["url"], "done": await _subscribed(uid, ch)} for ch in chans]
    return {"ok": all(x["done"] for x in steps), "kind": "subs", "steps": steps, "friends": max(0, FREE_FRIENDS)}


def _free_need(uid, cid, refs):
    """Порог друзей для подарка из бесплатного кейса: каждому подарку — свой новый друг."""
    if FREE_FRIENDS <= 0:
        return 0
    row = q1("SELECT refs_at FROM free_gate WHERE user=? AND cid=?", uid, cid)
    return (max(refs, row["refs_at"] if row else 0) if FREE_EACH else refs) + FREE_FRIENDS


@app.on_event("startup")
async def _keys_start():
    remap_keys()
    try:
        fix_keys()
    except Exception as e:
        print("realgifts fix_keys:", type(e).__name__, e, flush=True)


@app.get(R + "/realgifts/free/{cid}")
async def realgifts_free(cid: str, uid=Depends(auth)):
    b = _BUILT.get(cid)
    if not b or b["price"]:
        err("нет такого кейса")
    return await free_gate(uid, cid)


# ---------------- открыть / продать ----------------
@app.get(R + "/realgifts/case/{cid}")
def realgifts_case(cid: str, uid=Depends(auth)):
    """Кейс целиком: призы и шансы."""
    b = _BUILT.get(cid)
    if not b or b["paused"]:
        err("Кейс на паузе: обновляем цены подарков. Загляни чуть позже")
    u = q1("SELECT * FROM users WHERE id=?", uid)
    kr = q1("SELECT n FROM case_keys WHERE user=? AND cid=?", uid, cid)
    return {"id": cid, "title": E.case_title(cid, uid), "price": b["price"], "level": b["level"], "locked": A.level(u["xp"]) < b["level"],
            "keys": kr["n"] if kr else 0, "freeIn": _free_in(b, u), "nft": b["nft"],
            "items": [_pub(x) for x in sorted(b["items"], key=lambda x: (x["kind"] == "star", -x["value"]))]}   # шансы наружу не отдаём


def _strip(b, n):
    """Лента рулетки — витрина кейса, а не его шансы: по настоящим шансам в дешёвом кейсе на ней были бы одни звёзды.
    Больше половины ячеек — подарки (редкие тоже мелькают), остальное — звёзды. Приз в ячейку выигрыша ставит open()."""
    gifts = [(x, w) for x, w in zip(b["items"], b["w"]) if x["kind"] != "star"]
    stars = [(x, w) for x, w in zip(b["items"], b["w"]) if x["kind"] == "star"]
    if not gifts or not stars:
        pool = gifts or stars
        return [_pub(x) for x in random.choices([x for x, _ in pool], weights=[w ** 0.5 for _, w in pool], k=n)]
    gw = [w ** 0.3 for _, w in gifts]   # сглаженные веса: дешёвые чаще, но дорогие тоже видны
    out = []
    for _ in range(n):
        pool, w = (gifts, gw) if random.random() < 0.6 else (stars, [w for _, w in stars])
        out.append(_pub(random.choices([x for x, _ in pool], weights=w)[0]))
    return out


@app.post(R + "/realgifts/case/{cid}/open")
async def realgifts_open(cid: str, req: Request, uid=Depends(auth)):
    seen = int((await req.json()).get("price") or 0)
    if not enabled():
        err("Кейсы пока выключены")
    fix_keys(uid)
    b = _BUILT.get(cid)
    if not b or b["paused"]:
        err("Кейс на паузе: обновляем цены подарков. Загляни чуть позже")
    price = b["price"]
    if seen != price:
        err("Цена кейса обновилась — проверь её и открой ещё раз", 409)
    gated = not price and not q1("SELECT 1 FROM case_keys WHERE user=? AND cid=? AND n>0", uid, cid)
    if gated and not (await free_gate(uid, cid))["ok"]:
        err("Сначала выполни условия бесплатного кейса", 428)
    t = now()
    with tx():
        u = q1("SELECT * FROM users WHERE id=?", uid)
        kr = q1("SELECT n FROM case_keys WHERE user=? AND cid=?", uid, cid)
        key = bool(kr and kr["n"] > 0)                 # ключ от админа или друга: открытие без оплаты, уровня и ожидания
        if key:
            db.execute("UPDATE case_keys SET n=n-1 WHERE user=? AND cid=?", (uid, cid))
            paid = 0
        else:
            if A.level(u["xp"]) < b["level"]:
                err(f"Нужен {b['level']} уровень")
            left = _free_in(b, u)
            if left:
                err(f"Следующий бесплатный кейс — через {left // 3600} ч {left % 3600 // 60} мин" if left >= 3600 else f"Следующий бесплатный кейс — через {max(1, left // 60)} мин")
            if not price:
                db.execute("UPDATE users SET ru_free_at=? WHERE id=?" if cid in E.RU_CASES else "UPDATE users SET last_free=? WHERE id=?", (t, uid))
                db.execute("INSERT INTO free_gate(user,cid,opens,refs_at) VALUES(?,?,1,?) ON CONFLICT(user,cid) DO UPDATE SET opens=opens+1",
                           (uid, cid, _refs(uid)))
            paid = price
            if u["stars"] < paid:
                err("Не хватает звёзд")
            if A.SELF_GUARD and paid:
                A.SELF_GUARD(uid, paid)
        if cid in E.LIMITED:   # лимитный тираж
            left = q1("SELECT n FROM case_limit WHERE cid=?", cid)["n"]
            if left < 1:
                err("Тираж закончился")
            db.execute("UPDATE case_limit SET n=n-1 WHERE cid=?", (cid,))
        rng = fair.stream(uid, "case", cid)
        it = rng.choices(b["items"], weights=b["w"] if not b.get("wf") or payer(uid) else b["wf"])[0]
        row = None
        if it["kind"] == "star":   # звёзды сразу на баланс
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (it["value"], uid))
        else:
            need = 0
            if not price and not key:   # бесплатный кейс: подарок ждёт нового друга
                need = _free_need(uid, cid, _refs(uid))
                if need:
                    db.execute("UPDATE free_gate SET refs_at=? WHERE user=? AND cid=?", (need, uid, cid))
            row = give(uid, it, cid, paid, need)[0]
        db.execute("UPDATE users SET stars=stars-?, opened=opened+1 WHERE id=?", (paid, uid))
        if key:
            event(uid, "gift", it["value"])
            __import__("refs").on_key_open(uid, cid, it["title"] if it["kind"] != "star" else f"{S(it['value'])} ⭐")
        else:
            event(uid, "case", it["value"] - paid, stake=paid)
        fair.record(uid, "case", paid, it["value"], {"case": cid, "drops": [it["value"]], "prize": it["title"]}, fair.close_stream(rng))
        lvl = A.add_xp(uid, max(20, paid // 10))   # как у остальных кейсов: опыт от потраченного (ключом — минимум)
    WIN = 42
    strip = _strip(b, 50)
    strip[WIN] = _pub(it)
    return {"prize": _pub(it), "item": _item(row) if row else None, "strip": strip, "win": WIN, "levelup": lvl,
            "case": realgifts_case(cid, uid), **state(uid)}


@app.post(R + "/realgifts/item/{iid}/sell")
def realgifts_sell(iid: int, uid=Depends(auth)):
    with tx():
        it = q1("SELECT * FROM real_items WHERE id=? AND user=?", iid, uid) or err("Это не твой подарок")
        if it["status"] != "bag":
            err("Этот подарок уже продан или отправляется")
        _claim(uid, it)
        db.execute("UPDATE real_items SET status='sold', upd=? WHERE id=?", (now(), iid))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (it["value"], uid))
    return {"paid": it["value"], **state(uid)}


# ---------------- апгрейд подарка из кейса ----------------
UPG_EDGE = conf("realgifts.upg_edge", 0.90)             # возврат апгрейда: шанс = цена ставки / цена цели × upg_edge
UPG_MAX = conf("realgifts.upg_max", 0.80)               # шанс не выше
UPG_MIN_K = 1.2                                         # цель дороже ставки хотя бы во столько раз


def _upg_edge(uid):
    """Возврат апгрейда для игрока: у игроков без пополнений он ниже в той же пропорции, что и в кейсах."""
    return UPG_EDGE if payer(uid) else UPG_EDGE * min(1.0, RTP_FREE / RTP)


def _upg_targets(uid, sv):
    edge = _upg_edge(uid)
    seen, out = set(), []
    for x in _real({"gifts": list(NAMES)}):
        if x["key"] in seen or x["value"] < UPG_MIN_K * sv:
            continue
        seen.add(x["key"])
        out.append((x, min(UPG_MAX, sv / x["value"] * edge)))
    return sorted(out, key=lambda p: p[0]["value"])


@app.get(R + "/realgifts/item/{iid}/upgrade")
def realgifts_upgrade_targets(iid: int, uid=Depends(auth)):
    it = q1("SELECT * FROM real_items WHERE id=? AND user=?", iid, uid) or err("Это не твой подарок")
    if it["status"] != "bag":
        err("Этот подарок уже продан или отправляется")
    return {"item": _item(it), "targets": [{**_pub(x), "chance": round(p * 100, 2)} for x, p in _upg_targets(uid, it["value"])[:120]]}


@app.post(R + "/realgifts/item/{iid}/upgrade")
async def realgifts_upgrade(iid: int, req: Request, uid=Depends(auth)):
    """Апгрейд: подарок из сумки — ставка, цель — подарок дороже. Не повезло — ставка сгорает."""
    if not enabled():
        err("Кейсы подарков пока выключены")
    key = str((await req.json()).get("key", ""))
    t = now()
    with tx():
        it = q1("SELECT * FROM real_items WHERE id=? AND user=?", iid, uid) or err("Это не твой подарок")
        if it["status"] != "bag":
            err("Этот подарок уже продан или отправляется")
        hit = next(((x, p) for x, p in _upg_targets(uid, it["value"]) if x["key"] == key), None) or err("Эта цель сейчас недоступна — выбери другую")
        tg, chance = hit
        _claim(uid, it)
        if A.SELF_GUARD:
            A.SELF_GUARD(uid, 0)
        rr, pf = fair.rolls(uid, "upgrade", ref=f"rg{iid}", n=1)
        win = rr[0] < chance
        db.execute("UPDATE real_items SET status='burned', upd=? WHERE id=?", (t, iid))
        new = None
        if win:
            new = _item(give(uid, tg, "upgrade", it["value"])[0])
        event(uid, "upgrade", (tg["value"] if win else 0) - it["value"], stake=it["value"], pf=pf, res={"p": round(chance, 6), "win": win})
        lvl = A.add_xp(uid, max(5, it["value"] // 20))
    return {"win": win, "chance": round(chance * 100, 2), "item": new, "target": _pub(tg), "levelup": lvl, "pf": pf, **state(uid)}


# ---------------- вывод ----------------
def _back(iid, note):
    with tx():
        db.execute("UPDATE real_items SET status='bag', note=?, upd=? WHERE id=? AND status='sending'", (note[:200], now(), iid))
        it = q1("SELECT * FROM real_items WHERE id=? AND status='bag'", iid)
        if it:
            _mirror(it)


def _to_admin(iid, uid, it, why):
    with tx():
        db.execute("UPDATE real_items SET status='pending', note=?, upd=? WHERE id=? AND status='sending'", (why[:200], now(), iid))
    alert(f"pend{iid}", f"Заявка №{iid} на вывод подарка <b>{esc(it['title'])}</b> игроку <code>{uid}</code> ждёт ручной проверки: {esc(why)}. "
                        "Открой «Настоящие подарки» в игре — внизу список заявок.", every=0)


async def _send_tg(iid, uid, it):
    if not any(g["id"] == it["ref"] for g in _CAT["items"]):
        return _back(iid, "") or err("Telegram больше не продаёт этот подарок. Его можно продать игре за полную цену")
    try:
        r = await _tg("sendGift", user_id=uid, gift_id=it["ref"], text="Приз из кейса")
    except Exception as e:   # ответа нет — подарок мог уйти; второй раз сами не шлём
        _to_admin(iid, uid, it, f"Telegram не ответил на отправку ({type(e).__name__})")
        return
    if r.get("ok"):
        with tx():
            db.execute("UPDATE real_items SET status='sent', cost=?, note='', upd=? WHERE id=?", (round(it["xtr"] * W.XTR_USD, 4), now(), iid))
        if _BOT["stars"] is not None:
            _BOT["stars"] -= it["xtr"]
        notify(uid, f"🎁 Подарок за <b>{it['xtr']} Stars</b> отправлен — он уже в твоём профиле Telegram.")
        return
    desc = str(r.get("description") or "")
    print("realgifts sendGift:", desc, flush=True)
    if "BALANCE" in desc.upper():
        alert("bot-stars", "У бота не хватает Telegram Stars на подарки игрокам. Пополни баланс бота или дождись новых покупок.")
        _back(iid, "")
        err("Подарки временно закончились — попробуй позже. Приз остался в сумке")
    _back(iid, "")
    err("Telegram не принял подарок. Проверь в настройках приватности Telegram, что тебе можно дарить подарки, и попробуй ещё раз")


async def _send_nft(iid, uid, it, limit, used):
    if NFT_MODE == "off":
        _back(iid, "")
        err("Вывод коллекционных подарков временно недоступен. Приз остался в сумке")
    if not nft_auto() or not _fresh(_TON["ts"], 3):   # сервер купить не может — подарок выдаёт админ
        _to_admin(iid, uid, it, "выдать вручную" if NFT_MODE == "manual" or not T.has_session() else "площадка недоступна, выдать вручную")
        return
    try:
        offers = await T.listings(it["ref"], 5)
    except T.TonnelError:
        _back(iid, "")
        err("Площадка подарков не отвечает — попробуй позже. Приз остался в сумке")
    k = (1 + FEE) * _TON["usd"]
    tried = 0
    for o in offers[:3]:
        cost = o["price"] * k
        if cost > it["usd"] * SLIP:   # дальше только дороже
            break
        if used + max(cost, it["usd"]) > limit + 1e-9:
            _back(iid, "")
            err(f"Сейчас подарок стоит ${cost:.2f} — это больше остатка лимита вывода ${max(0, limit - used):.2f}")
        tried += 1
        try:
            ok, why = await T.buy(o["id"], o["price"], uid)
        except T.TonnelError as e:   # исход неизвестен — повторять нельзя, иначе можно купить дважды
            _to_admin(iid, uid, it, f"площадка не ответила на покупку предложения {o['id']} за {o['price']} TON ({e})")
            return
        if ok:
            with tx():
                db.execute("UPDATE real_items SET status='sent', cost=?, note=?, upd=? WHERE id=?",
                           (round(cost, 4), f"{o['model']} · {o['backdrop']}"[:200], now(), iid))
            if _TN["bal"] is not None:
                _TN["bal"] -= o["price"] * (1 + T.FEE)
            notify(uid, f"🎁 Подарок <b>{esc(it['title'])}</b> отправлен на твой аккаунт Telegram.")
            return
        print("realgifts tonnel buy:", o["id"], why, flush=True)
        if "balance" in why.lower() or "fund" in why.lower():
            alert("tn-bal", "На балансе площадки Tonnel не хватает TON на подарок игроку. Пополни баланс площадки.")
            _back(iid, "")
            err("Подарки временно закончились — попробуй позже. Приз остался в сумке")
    _back(iid, "")
    if not tried:
        err("Подарок сейчас подорожал на рынке — попробуй позже или продай его игре за полную цену" if offers else
            "Этого подарка сейчас нет на площадке — попробуй позже или продай его игре за полную цену")
    err("Не получилось купить подарок на площадке — попробуй ещё раз. Приз остался в сумке")


@app.post(R + "/realgifts/item/{iid}/withdraw")
async def realgifts_withdraw(iid: int, uid=Depends(auth)):
    if not enabled():
        err("Вывод подарков пока выключен")
    with tx():   # приз сразу помечается «отправляется»: второй вывод или продажа в это время невозможны, а его цена уже занимает лимит
        it = q1("SELECT * FROM real_items WHERE id=? AND user=?", iid, uid) or err("Это не твой подарок")
        if it["status"] != "bag":
            err("Этот подарок уже продан или отправляется")
        _claim(uid, it)
        limit, used = W.budget(uid)
        if not limit:
            held = W.held(uid)
            err(f"Свежее пополнение станет доступно для вывода через {W.HOLD_H} ч после оплаты" if held else "Вывод открывается после первой покупки звёзд")
        need = max(it["usd"], _now_usd(it)) if it["kind"] == "tg" else it["usd"]
        if used + need > limit + 1e-9:
            err(f"Лимит вывода: осталось ${max(0, limit - used):.2f}, а подарок стоит ${need:.2f}. Лимит растёт с покупками")
        free = W.free_take(uid, used, need)
        db.execute("UPDATE real_items SET status='sending', upd=? WHERE id=?", (now(), iid))
    try:
        if it["kind"] == "tg":
            await _send_tg(iid, uid, it)
        else:
            await _send_nft(iid, uid, it, limit, used)
    finally:   # что бы ни случилось, приз не должен зависнуть в «отправляется» без хозяина
        r = q1("SELECT status FROM real_items WHERE id=?", iid)
        if r and r["status"] == "sending":
            _back(iid, "")
            r = {"status": "bag"}
        if r and r["status"] == "bag":   # не отправили — бесплатный бюджет дня возвращаем
            W.free_return(free)
    return state(uid)


# ---------------- админ ----------------
@app.get(R + "/admin/realgifts")
def admin_state(aid=Depends(admin)):
    age = lambda ts: int(time.time() - ts) if ts else None   # noqa: E731
    out = q1("SELECT COUNT(*) n, COALESCE(SUM(MAX(usd,cost)),0) usd FROM real_items WHERE status='sent'")
    opened = q1("SELECT COUNT(*) n, COALESCE(SUM(paid),0) paid, COALESCE(SUM(value),0) value FROM real_items")
    return {"on": enabled(), "nftMode": NFT_MODE, "nftReady": nft_ready(), "nftAuto": nft_auto(), "tonnelLib": T.available(), "tonnelSession": T.has_session(),
            "feed": {k: v for k, v in _FEED.items() if k != "log"}, "paused": [{"title": b["title"], "why": b.get("why", "")} for b in _BUILT.values() if b["paused"]],
            "tonnelBal": _TN["bal"], "tonnelErr": _TN["err"], "tonnelAge": age(_TN["ts"]), "botStars": _BOT["stars"], "ton": _TON["usd"], "tonAge": age(_TON["ts"]),
            "catalog": len(_CAT["items"]), "catalogAge": age(_CAT["ts"]), "xtrUsd": W.XTR_USD,
            "prices": [{"name": n, "ton": _NFT[n]["ton"], "lo": _NFT[n]["lo"], "age": age(_NFT[n]["ts"])} for n in NAMES if n in _NFT],
            "noPrice": [n for n in NAMES if n not in _NFT],
            "cases": len([b for b in _BUILT.values() if not b["paused"]]),
            "sent": {"n": out["n"], "usd": round(out["usd"], 2)}, "opened": dict(opened),
            "pending": [{"id": r["id"], "user": r["user"], "kind": r["kind"], "title": r["title"], "usd": r["usd"], "note": r["note"], "ts": r["upd"]}
                        for r in q("SELECT * FROM real_items WHERE status='pending' ORDER BY upd")]}


@app.post(R + "/admin/realgifts/refresh")
async def admin_refresh(aid=Depends(admin)):
    await refresh()
    return admin_state(aid)


@app.post(R + "/admin/realgifts/{iid}/{what}")
async def admin_resolve(iid: int, what: str, req: Request, aid=Depends(admin)):
    """Заявка на ручной проверке: done — подарок у игрока (cost — сколько он стоил в $), back — не выдан, приз вернуть в сумку."""
    if what not in ("done", "back"):
        err("нет такого действия")
    try:
        body = await req.json()
    except Exception:
        body = {}
    with tx():
        it = q1("SELECT * FROM real_items WHERE id=? AND status='pending'", iid) or err("Заявка уже разобрана")
        if what == "done":
            cost = float(body.get("cost") or 0) or it["usd"]
            db.execute("UPDATE real_items SET status='sent', cost=?, note='', upd=? WHERE id=?", (round(cost, 4), now(), iid))
        else:
            db.execute("UPDATE real_items SET status='bag', note='', upd=? WHERE id=?", (now(), iid))
            _mirror(q1("SELECT * FROM real_items WHERE id=?", iid))
    notify(it["user"], f"🎁 Подарок <b>{esc(it['title'])}</b> отправлен на твой аккаунт Telegram." if what == "done" else
           f"↩️ Подарок <b>{esc(it['title'])}</b> не получилось отправить — он снова в сумке. Попробуй вывести ещё раз или продай его.")
    return admin_state(aid)


async def loop():
    await asyncio.sleep(3)
    while True:
        try:
            await refresh()
        except Exception as e:
            print("realgifts loop:", type(e).__name__, e, flush=True)
        try:
            await warm_art()
        except Exception as e:
            print("realgifts warm:", type(e).__name__, e, flush=True)
        await asyncio.sleep(REFRESH)


@app.on_event("startup")
async def _start():
    with tx():   # сервер перезапустился посреди отправки: исход неизвестен — на ручную проверку
        db.execute("UPDATE real_items SET status='pending', note='сервер перезапустился во время отправки' WHERE status='sending'")
    asyncio.create_task(loop())
    try:
        _migrate()
    except Exception as e:
        print("realgifts migrate:", type(e).__name__, e, flush=True)


def _migrate():
    """Подарки из кейсов, выигранные до появления зеркал, заводим в общую таблицу; подарки из бесплатного кейса — под замок до друга."""
    free = [c["id"] for c in CASES if not c["price"]]
    with tx():
        if not A.kv_get("rg_free_lock") and FREE_FRIENDS > 0 and free:
            marks = ",".join("?" * len(free))
            db.execute(f"UPDATE real_items SET need_refs=(SELECT COALESCE(refs,0) FROM users WHERE id=real_items.user)+? "
                       f"WHERE status='bag' AND paid=0 AND COALESCE(need_refs,0)=0 AND cid IN ({marks}) "
                       f"AND NOT EXISTS(SELECT 1 FROM gifts g WHERE g.real=real_items.id)", (FREE_FRIENDS, *free))
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('rg_free_lock','1')")
        base = "active" if friend_level() else "refs"   # как считаются друзья: активные (дошли до уровня) или все зашедшие
        if (A.kv_get("rg_lock_base") or ("active" if A.kv_get("rg_lock_active") else "refs")) != base:
            # способ подсчёта друзей сменился — пересчитываем пороги замков от нового счёта. Что уже открыто, остаётся открытым
            for r in q("SELECT DISTINCT user FROM real_items WHERE status='bag' AND need_refs>0 AND user>0"):
                uid = r["user"]
                cnt, k = _refs(uid), 0
                for it in q("SELECT r.id, g.id gid FROM real_items r LEFT JOIN gifts g ON g.real=r.id "
                            "WHERE r.user=? AND r.status='bag' AND r.need_refs>0 ORDER BY r.need_refs, r.id", uid):
                    if it["gid"]:
                        db.execute("UPDATE real_items SET need_refs=0 WHERE id=?", (it["id"],))
                    else:
                        k += 1
                        db.execute("UPDATE real_items SET need_refs=? WHERE id=?", (cnt + (k if FREE_EACH else 1) * FREE_FRIENDS, it["id"]))
                db.execute("UPDATE free_gate SET refs_at=? WHERE user=?", (cnt + k * FREE_FRIENDS, uid))
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('rg_lock_base',?)", (base,))
        # зеркало в игре или на маркете, а подарок уже не в сумке — такого быть не должно, но висеть оно не будет
        db.execute("DELETE FROM gifts WHERE real IS NOT NULL AND NOT EXISTS(SELECT 1 FROM real_items r WHERE r.id=gifts.real AND r.status='bag')")
        for r in q("SELECT DISTINCT user FROM real_items WHERE status='bag' AND user>0"):
            _sync(r["user"])
