"""Кейсы с настоящими подарками Telegram: приз лежит в сумке, его можно продать игре за полную цену или вывести на свой аккаунт.

Откуда призы и что они нам стоят
  · обычные подарки (сердце, мишка, торт…) бот покупает у самого Telegram и дарит игроку (Bot API sendGift). Платит бот со своего
    баланса Telegram Stars — туда же приходят покупки игроков, поэтому цена подарка в Stars равна его цене в игре один к одному;
  · коллекционные подарки (Lol Pop, Love Candle…) покупаются на площадке Tonnel сразу на аккаунт игрока, в TON. Цена приза =
    цена на площадке + её комиссия 10%, в долларах по курсу TON. В ⭐ она переводится через withdraw.xtr_usd — сколько долларов
    приносит нам 1 Telegram Star после всех комиссий.
Склада нет: покупка происходит только в момент вывода и только когда игрок сам об этом попросил.

Как считается кейс (та же формула, что у кейсов скинов)
  · вес приза = (1000 / цена в $)^k — дешёвые выпадают часто, дорогие редко; k у каждого кейса свой;
  · цена кейса = средняя цена приза / rtp (0,60): в среднем игрок получает призов на 60% цены, 40% остаётся игре;
  · цены обновляются раз в refresh_min минут; цена кейса пересчитывается от живых цен. Нет свежей цены — приз исчезает из кейса,
    призов меньше трёх — кейс на паузе.
Защита
  · вывод — в общем со скинами лимите (withdraw.py): только после покупок и не больше оплаченного × limit_k, свежие пополнения
    в лимит не идут hold_hours часов. Это жёсткий потолок реальных выплат при любых бонусах и бесплатных ⭐;
  · на выводе цена проверяется ещё раз: подорожал больше чем в slip раз — отказ, приз остаётся в сумке (продать его можно всегда);
  · не получилось купить или подарить — приз возвращается в сумку; ответа нет и исход неизвестен — заявку разбирает админ.
Ключи: TONNEL_AUTH — переменная окружения (см. tonnel.py). Без неё работают только обычные подарки."""
import asyncio
import math
import os
import random
import statistics
import time

from fastapi import Depends, Request
from fastapi.responses import FileResponse, Response

import app as A
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
NFT_MODE = conf("realgifts.nft_mode", "auto")           # коллекционные: auto — покупает сервер, manual — админ руками, off — выключены
MAX_XTR = conf("realgifts.max_xtr", 2500)               # обычные подарки дороже в кейсы не берём
MIN_ITEMS = 3
TG_API = os.environ.get("TG_API_URL", "https://api.telegram.org")   # TG_API_URL, TON_RATE_URL — только для тестов
TON_URLS = [u for u in [os.environ.get("TON_RATE_URL", "")] if u] or [
    "https://tonapi.io/v2/rates?tokens=ton&currencies=usd",
    "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"]
DEFAULT_CASES = [
    {"id": "start", "title": "Стартовый", "k": 1.5, "stars": [15, 100],
     "gifts": ["Lol Pop", "B-Day Candle", "Desk Calendar", "Love Candle", "Electric Skull"]},
    {"id": "collect", "title": "Коллекционный", "k": 2.0, "stars": [0, 0],
     "gifts": ["Lol Pop", "Easter Egg", "B-Day Candle", "Desk Calendar", "Light Sword", "Joyful Bundle", "Love Candle", "Crystal Ball",
               "Cupid Charm", "Electric Skull", "Diamond Ring", "Kissed Frog", "Artisan Brick", "Astral Shard"]},
    {"id": "legend", "title": "Легенда", "k": 1.6, "stars": [0, 0],
     "gifts": ["Love Candle", "Crystal Ball", "Cupid Charm", "Electric Skull", "Diamond Ring", "Kissed Frog", "Artisan Brick", "Astral Shard",
               "Loot Bag", "Durov's Cap"]},
]
CASES = conf("realgifts.cases", []) or DEFAULT_CASES
NAMES = sorted({n for c in CASES for n in c.get("gifts", [])})

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
for _r in q("SELECT * FROM real_prices"):     # цены переживают перезапуск вместе со своим возрастом
    if _r["k"] == "ton":
        _TON.update(usd=_r["v"], ts=_r["ts"])
    elif _r["k"].startswith("nft:"):
        _NFT[_r["k"][4:]] = {"ton": _r["v"], "lo": _r["lo"] or _r["v"], "ts": _r["ts"], "cand": 0}


def enabled():
    return bool(ON and (not DEV or "TG_API_URL" in os.environ))


def nft_ready():
    """Можно ли сейчас выдавать коллекционные подарки."""
    if NFT_MODE == "manual":
        return True
    return NFT_MODE == "auto" and T.has_session() and _TN["ts"] > 0 and _TN["fails"] < 3


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
        if not xtr or xtr > MAX_XTR or (left is not None and left <= 0):
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
    if NFT_MODE != "off" and NAMES and T.available():
        await _load_ton()
        bad = 0
        for name in NAMES:
            try:
                _take_price(name, await T.listings(name))
            except T.TonnelError as e:
                bad += 1
                if bad == 1:
                    print("realgifts tonnel:", name, e, flush=True)
                if bad >= 3:   # площадка недоступна — не долбим её оставшимися запросами
                    break
            await asyncio.sleep(1.2)
        if T.has_session():
            try:
                _TN.update(bal=await T.balance(), ts=time.time(), fails=0, err="")
            except T.TonnelError as e:
                _TN.update(fails=_TN["fails"] + 1, err=str(e))
                if _TN["fails"] == 3:
                    alert("tn-session", f"Площадка Tonnel не принимает сессию ({esc(str(e))}). Коллекционные подарки убраны из кейсов до обновления TONNEL_AUTH.")
    _rebuild()


def _nice(v):
    """Цена кейса: вверх до трёх значащих цифр (округление всегда в пользу игры)."""
    if v <= 0:
        return 0
    step = max(100, 10 ** (len(str(int(v))) - 3))
    return int(math.ceil(v / step) * step)


def _pool(c):
    out = []
    lo, hi = (c.get("stars") or [0, 0])[:2]
    if hi and _fresh(_CAT["ts"]):
        for g in _CAT["items"]:
            if lo <= g["xtr"] <= hi:
                out.append({"key": "tg:" + g["id"], "kind": "tg", "ref": g["id"], "title": f"Подарок за {g['xtr']} Stars", "xtr": g["xtr"],
                            "usd": round(g["xtr"] * W.XTR_USD, 4), "value": g["xtr"] * shop.RATE, "emoji": g["emoji"], "img": bool(g["thumb"])})
    if nft_ready() and _fresh(_TON["ts"], 3):
        for name in c.get("gifts", []):
            p = _NFT.get(name)
            if p and _fresh(p["ts"]):
                usd = p["ton"] * (1 + T.FEE) * _TON["usd"]
                out.append({"key": "nft:" + name, "kind": "nft", "ref": name, "title": name, "xtr": 0, "usd": round(usd, 4),
                            "value": int(round(usd / W.XTR_USD * shop.RATE, -2)), "emoji": "", "img": True})
    return out


def _rebuild():
    for c in CASES:
        items = _pool(c)
        if len(items) < MIN_ITEMS:
            _BUILT[c["id"]] = {"id": c["id"], "title": c["title"], "paused": True, "items": [], "price": 0}
            continue
        w = [(1000 / x["usd"]) ** c.get("k", 1.5) for x in items]
        tw = sum(w)
        ev = sum(x["value"] * wi for x, wi in zip(items, w)) / tw
        price = _nice(ev / RTP)
        for x, wi in zip(items, w):
            x["p"] = wi / tw
        _BUILT[c["id"]] = {"id": c["id"], "title": c["title"], "paused": False, "items": items, "w": w, "price": price, "ev": ev,
                           "win": sum(x["p"] for x in items if x["value"] > price), "nft": any(x["kind"] == "nft" for x in items)}


def _now_usd(it):
    """Сколько приз стоит нам сейчас по ленте цен (для подсказки игроку); на выводе цена проверяется живым запросом."""
    if it["kind"] == "tg":
        return round(it["xtr"] * W.XTR_USD, 4)
    p = _NFT.get(it["ref"])
    return round(p["lo"] * (1 + T.FEE) * _TON["usd"], 4) if p and _TON["usd"] else it["usd"]


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


def state(uid):
    limit, used = W.budget(uid)
    held = W.held(uid)
    cases = []
    for c in CASES:
        b = _BUILT.get(c["id"])
        if not b or b["paused"]:
            continue
        cases.append({"id": b["id"], "title": b["title"], "price": b["price"], "win": round(b["win"] * 100, 1), "nft": b["nft"],
                      "items": [{"key": x["key"], "kind": x["kind"], "ref": x["ref"], "title": x["title"], "value": x["value"], "emoji": x["emoji"],
                                 "img": x["img"], "p": round(x["p"] * 100, 4)} for x in sorted(b["items"], key=lambda x: -x["value"])]})
    bag = [_item(r) for r in q("SELECT * FROM real_items WHERE user=? AND status IN ('bag','sending','pending') ORDER BY id DESC LIMIT 200", uid)]
    hist = [_item(r) for r in q("SELECT * FROM real_items WHERE user=? AND status IN ('sent','sold') ORDER BY upd DESC LIMIT 15", uid)]
    return {"on": enabled(), "cases": cases, "bag": bag, "history": hist, "stars": bal(uid), "limit": limit, "used": used,
            "left": round(max(0, limit - used), 2), "held": held, "holdHours": W.HOLD_H, "nftSoon": NFT_MODE != "off" and not nft_ready(),
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
@app.post(R + "/realgifts/case/{cid}/open")
async def realgifts_open(cid: str, req: Request, uid=Depends(auth)):
    seen = int((await req.json()).get("price") or 0)
    if not enabled():
        err("Кейсы с настоящими подарками пока выключены")
    b = _BUILT.get(cid)
    if not b or b["paused"]:
        err("Кейс на паузе: обновляем цены подарков. Загляни чуть позже")
    price = b["price"]
    if seen != price:   # цена пересчиталась, пока игрок смотрел на кейс — списываем только ту, что он видел
        err("Цена кейса обновилась — проверь её и открой ещё раз", 409)
    with tx():
        u = q1("SELECT * FROM users WHERE id=?", uid)
        if u["stars"] < price:
            err("Не хватает звёзд")
        if A.SELF_GUARD:
            A.SELF_GUARD(uid, price)
        rng = fair.stream(uid, "case", "real:" + cid)
        it = rng.choices(b["items"], weights=b["w"])[0]
        t = now()
        cur = db.execute("INSERT INTO real_items(user,kind,ref,title,xtr,value,usd,cid,paid,status,ts,upd) VALUES(?,?,?,?,?,?,?,?,?,'bag',?,?)",
                         (uid, it["kind"], it["ref"], it["title"], it["xtr"], it["value"], it["usd"], cid, price, t, t))
        db.execute("UPDATE users SET stars=stars-?, opened=opened+1 WHERE id=?", (price, uid))
        event(uid, "case", it["value"] - price, stake=price)
        fair.record(uid, "case", price, it["value"], {"case": "real:" + cid, "drops": [it["value"]], "prize": it["title"]}, fair.close_stream(rng))
        lvl = A.add_xp(uid, max(20, price // 10))
        row = q1("SELECT * FROM real_items WHERE id=?", cur.lastrowid)
    WIN = 42
    pub = lambda x: {"kind": x["kind"], "ref": x["ref"], "title": x["title"], "value": x["value"], "emoji": x["emoji"], "img": x["img"]}   # noqa: E731
    strip = [pub(x) for x in random.choices(b["items"], weights=b["w"], k=50)]
    strip[WIN] = pub(it)
    return {"item": _item(row), "strip": strip, "win": WIN, "levelup": lvl, **state(uid)}


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
    if NFT_MODE == "manual":
        _to_admin(iid, uid, it, "ручной режим выдачи")
        return
    if not nft_ready() or not _fresh(_TON["ts"], 3):
        _back(iid, "")
        err("Вывод коллекционных подарков временно недоступен. Приз остался в сумке")
    try:
        offers = await T.listings(it["ref"], 5)
    except T.TonnelError:
        _back(iid, "")
        err("Площадка подарков не отвечает — попробуй позже. Приз остался в сумке")
    k = (1 + T.FEE) * _TON["usd"]
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
    return {"on": enabled(), "nftMode": NFT_MODE, "nftReady": nft_ready(), "tonnelLib": T.available(), "tonnelSession": T.has_session(),
            "tonnelBal": _TN["bal"], "tonnelErr": _TN["err"], "tonnelAge": age(_TN["ts"]), "botStars": _BOT["stars"], "ton": _TON["usd"], "tonAge": age(_TON["ts"]),
            "catalog": len(_CAT["items"]), "catalogAge": age(_CAT["ts"]), "xtrUsd": W.XTR_USD,
            "prices": [{"name": n, "ton": _NFT[n]["ton"], "lo": _NFT[n]["lo"], "age": age(_NFT[n]["ts"])} for n in NAMES if n in _NFT],
            "noPrice": [n for n in NAMES if n not in _NFT],
            "cases": [{"id": b["id"], "title": b["title"], "paused": b["paused"], "price": b["price"], "items": len(b["items"])} for b in _BUILT.values()],
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
