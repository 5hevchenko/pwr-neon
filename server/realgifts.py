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
import asyncio
import os
import random
import statistics
import time

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
RTP = conf("realgifts.rtp", 0.60)                       # доля цены кейса, которая в среднем возвращается призами
REFRESH = int(conf("realgifts.refresh_min", 10) * 60)   # как часто обновлять цены
MAX_AGE = int(conf("realgifts.max_age_min", 40) * 60)   # цена старше — приз убирается из кейса
SLIP = conf("realgifts.slip", 1.15)                     # на выводе приз может стоить не больше цены выигрыша × slip
NFT_MODE = conf("realgifts.nft_mode", "auto")           # коллекционные: auto — покупает сервер (нет сессии площадки — заявка админу), manual — всегда админ, off — выключены
STARS = conf("realgifts.stars", [15, 100])              # какие обычные подарки кладём в кейсы: цена в Telegram Stars, от и до
MAX_USD = conf("realgifts.max_usd", 600.0)              # коллекционные дороже в кейсы не кладём: такой приз нечем обеспечить
K_FILL = conf("realgifts.k_fill", 1.5)                  # вес подарков между собой в дешёвых кейсах: (1 / цена)^k
FILL = conf("realgifts.fill", [[0.1, 47.0], [0.3, 29.0], [0.6, 14.0], [1.2, 8.0], [3.0, 2.0]])   # призы звёздами: [доля цены кейса, вес]
FREE_EV = conf("realgifts.free_ev", 300)                # средний приз бесплатного кейса, ⭐
HIDE = set(conf("realgifts.hide", ["csgo", "csgo2", "brawl", "mc"]))   # игровые кейсы без настоящих призов — убраны с витрины
FEE = T.FEE                                             # комиссия площадки, закладывается в цену коллекционного подарка
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
        out.append({"id": cid, "title": c["title"], "price": int(c["price"]), "level": c.get("level", 1), "gifts": list(c["cols"])})
        E.FIXED_PRICE[cid] = int(c["price"])   # цена твёрдая: курс банка и акции на неё не действуют, иначе съедут шансы
    return out


CASES = _defs()
IDS = {c["id"] for c in CASES}
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


def _real(c):
    """Настоящие призы кейса со свежей ценой: обычные подарки и коллекционные из его состава."""
    out = []
    lo, hi = STARS[:2]
    if _fresh(_CAT["ts"]):
        for g in _CAT["items"]:
            if lo <= g["xtr"] <= hi:
                out.append({"key": "tg:" + g["id"], "kind": "tg", "ref": g["id"], "title": f"Подарок за {g['xtr']} Stars", "xtr": g["xtr"],
                            "usd": round(g["xtr"] * W.XTR_USD, 4), "value": g["xtr"] * shop.RATE, "emoji": g["emoji"], "img": bool(g["thumb"])})
    if nft_ready() and _fresh(_TON["ts"], 3):
        for name in c["gifts"]:
            p = _NFT.get(name)
            if p and _fresh(p["ts"]):
                usd = p["ton"] * (1 + FEE) * _TON["usd"]
                if usd <= MAX_USD:
                    out.append({"key": "nft:" + name, "kind": "nft", "ref": name, "title": name, "xtr": 0, "usd": round(usd, 4),
                                "value": int(round(usd / W.XTR_USD * shop.RATE, -2)), "emoji": "", "img": True})
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
    """Кейс с твёрдой ценой: шансы призов подобраны так, чтобы средний приз был RTP × цена (у бесплатного — FREE_EV)."""
    base = {"id": c["id"], "title": c["title"], "price": c["price"], "level": c["level"], "paused": True, "items": [], "w": []}
    items = _real(c)
    if len(items) < MIN_REAL:
        return dict(base, why="нет цен подарков")
    nominal = c["price"] or FREE_EV / RTP          # от чего считаются призы звёздами
    target = RTP * nominal
    if target >= items[0]["value"]:                 # только подарки
        while len(items) > MIN_REAL and _ev(items, 0.5) < target:   # дорогому кейсу дешёвые призы не нужны
            items = items[1:]
        if _ev(items, 0.0) < target:
            return dict(base, why="не хватает дорогих призов")
        k = _solve(items, target)
        w = _weights(items, k)
        tw = sum(w)
        w = [x / tw for x in w]
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


def _rebuild():
    for c in CASES:
        _BUILT[c["id"]] = _build(c)
    paused = [f"{b['title']} ({b.get('why')})" for b in _BUILT.values() if b["paused"]]
    line = (f"realgifts: обычных подарков {len(_CAT['items'])}, цен коллекционных {sum(1 for n in NAMES if n in _NFT and _fresh(_NFT[n]['ts']))} из {len(NAMES)} "
            f"(Portals: {_FEED.get('portals', 0)}), TON ${_TON['usd']:.3f}, кейсов работает {len(_BUILT) - len(paused)} из {len(_BUILT)}"
            + (f", на паузе: {', '.join(paused[:8])}" if paused else ""))
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


def _item(r):
    d = {"id": r["id"], "kind": r["kind"], "ref": r["ref"], "title": r["title"], "value": r["value"], "status": r["status"], "ts": r["ts"],
         "text": r["note"] if r["status"] == "bag" else STATUS.get(r["status"], ""), "emoji": "🎁",
         "img": r["kind"] == "nft" or r["ref"] in _THUMBS or os.path.exists(os.path.join(A.ASSET_CACHE, f"tggift_{r['ref']}.webp"))}
    if r["status"] == "bag":
        d["usd"] = _now_usd(r)
    return d


def _pub(x):
    return {"key": x["key"], "kind": x["kind"], "ref": x["ref"], "title": x["title"], "value": x["value"], "emoji": x["emoji"], "img": x["img"]}


def _free_in(c, u):
    """Сколько секунд до следующего бесплатного открытия (у платных кейсов — 0)."""
    if c["price"]:
        return 0
    if c["id"] in E.RU_CASES:
        return max(0, (u["ru_free_at"] or 0) + E.RU_FREE_EVERY - now())
    return max(0, (u["last_free"] or 0) + A.free_every(u) - now())


def state(uid):
    limit, used = W.budget(uid)
    cases = {}
    for c in CASES:
        b = _BUILT.get(c["id"])
        if b and not b["paused"]:
            cases[b["id"]] = {"price": b["price"], "gift": round(b["gift"] * 100, 4), "top": _pub(b["top"])}
    bag = [_item(r) for r in q("SELECT * FROM real_items WHERE user=? AND status IN ('bag','sending','pending') ORDER BY id DESC LIMIT 200", uid)]
    hist = [_item(r) for r in q("SELECT * FROM real_items WHERE user=? AND status IN ('sent','sold') ORDER BY upd DESC LIMIT 15", uid)]
    return {"on": enabled(), "cases": cases, "ids": sorted(IDS), "bag": bag, "history": hist, "stars": bal(uid), "limit": limit, "used": used,
            "left": round(max(0, limit - used), 2), "held": W.held(uid), "holdHours": W.HOLD_H,
            "rtp": int(RTP * 100), "limitK": int(W.LIMIT_K * 100), "usdK": W.XTR_USD / shop.RATE}


@app.get(R + "/realgifts")
def realgifts_state(uid=Depends(auth)):
    return state(uid)


@app.get(R + "/realgifts/img/{gid}")
async def realgifts_img(gid: str):
    """Картинка обычного подарка: один раз скачиваем у Telegram и кладём в свой кэш."""
    if not gid.isdigit():
        return Response(status_code=404)
    os.makedirs(A.ASSET_CACHE, exist_ok=True)
    f = os.path.join(A.ASSET_CACHE, f"tggift_{gid}.webp")
    if not os.path.exists(f):
        g = next((x for x in _CAT["items"] if x["id"] == gid and x["thumb"]), None)
        if not g:
            return Response(status_code=404)
        try:
            r = await _tg("getFile", file_id=g["thumb"])
            d = await A.http.get(f"{TG_API}/file/bot{TOKEN}/{r['result']['file_path']}", timeout=30)
            if d.status_code != 200:
                return Response(status_code=502)
            with open(f, "wb") as fh:
                fh.write(d.content)
        except Exception:
            return Response(status_code=502)
    return FileResponse(f, media_type="image/webp", headers={"Cache-Control": "public, max-age=604800"})


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
            "keys": kr["n"] if kr else 0, "freeIn": _free_in(b, u), "gift": round(b["gift"] * 100, 4), "nft": b["nft"],
            "items": [dict(_pub(x), p=round(x["p"] * 100, 6)) for x in sorted(b["items"], key=lambda x: -x["value"])]}


@app.post(R + "/realgifts/case/{cid}/open")
async def realgifts_open(cid: str, req: Request, uid=Depends(auth)):
    seen = int((await req.json()).get("price") or 0)
    if not enabled():
        err("Кейсы пока выключены")
    b = _BUILT.get(cid)
    if not b or b["paused"]:
        err("Кейс на паузе: обновляем цены подарков. Загляни чуть позже")
    price = b["price"]
    if seen != price:
        err("Цена кейса обновилась — проверь её и открой ещё раз", 409)
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
        it = rng.choices(b["items"], weights=b["w"])[0]
        row = None
        if it["kind"] == "star":   # звёзды сразу на баланс
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (it["value"], uid))
        else:
            cur = db.execute("INSERT INTO real_items(user,kind,ref,title,xtr,value,usd,cid,paid,status,ts,upd) VALUES(?,?,?,?,?,?,?,?,?,'bag',?,?)",
                             (uid, it["kind"], it["ref"], it["title"], it["xtr"], it["value"], it["usd"], cid, paid, t, t))
            row = q1("SELECT * FROM real_items WHERE id=?", cur.lastrowid)
        db.execute("UPDATE users SET stars=stars-?, opened=opened+1 WHERE id=?", (paid, uid))
        if key:
            event(uid, "gift", it["value"])
            __import__("refs").on_key_open(uid, cid, it["title"] if it["kind"] != "star" else f"{it['value']} ⭐")
        else:
            event(uid, "case", it["value"] - paid, stake=paid)
        fair.record(uid, "case", paid, it["value"], {"case": cid, "drops": [it["value"]], "prize": it["title"]}, fair.close_stream(rng))
        lvl = A.add_xp(uid, max(20, price // 10))
    WIN = 42
    strip = [_pub(x) for x in random.choices(b["items"], weights=b["w"], k=50)]
    strip[WIN] = _pub(it)
    return {"prize": _pub(it), "item": _item(row) if row else None, "strip": strip, "win": WIN, "levelup": lvl,
            "case": realgifts_case(cid, uid), **state(uid)}


@app.post(R + "/realgifts/item/{iid}/sell")
def realgifts_sell(iid: int, uid=Depends(auth)):
    with tx():
        it = q1("SELECT * FROM real_items WHERE id=? AND user=?", iid, uid) or err("Это не твой подарок")
        if it["status"] != "bag":
            err("Этот подарок уже продан или отправляется")
        db.execute("UPDATE real_items SET status='sold', upd=? WHERE id=?", (now(), iid))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (it["value"], uid))
    return {"paid": it["value"], **state(uid)}


# ---------------- вывод ----------------
def _back(iid, note):
    with tx():
        db.execute("UPDATE real_items SET status='bag', note=?, upd=? WHERE id=? AND status='sending'", (note[:200], now(), iid))


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
        limit, used = W.budget(uid)
        if not limit:
            held = W.held(uid)
            err(f"Свежее пополнение станет доступно для вывода через {W.HOLD_H} ч после оплаты" if held else "Вывод открывается после первой покупки звёзд")
        need = max(it["usd"], _now_usd(it)) if it["kind"] == "tg" else it["usd"]
        if used + need > limit + 1e-9:
            err(f"Лимит вывода: осталось ${max(0, limit - used):.2f}, а подарок стоит ${need:.2f}. Лимит растёт с покупками")
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
        await asyncio.sleep(REFRESH)


@app.on_event("startup")
async def _start():
    with tx():   # сервер перезапустился посреди отправки: исход неизвестен — на ручную проверку
        db.execute("UPDATE real_items SET status='pending', note='сервер перезапустился во время отправки' WHERE status='sending'")
    asyncio.create_task(loop())
