"""NePridymal — игровой кейс-симулятор подарков Telegram. Подарки и звёзды ненастоящие.

FastAPI + SQLite. Внутри же: игровой цикл краша и long polling бота.
"""
from settings import conf, tuned
import asyncio
import hashlib
import hmac
import html as html_lib
import json
import math
import os
import random
import re
import sqlite3
import threading
import time
import urllib.parse
from collections import deque
from contextvars import ContextVar

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

import economy as E

TOKEN = os.environ["BOT_TOKEN"]
APP_URL = os.environ.get("APP_URL", "https://2.27.44.210/np/")
BOT_NAME = os.environ.get("BOT_USERNAME", "NePridymalhzbot")
VIA_BOT = ContextVar("via_bot", default=0)        # франшиза: id дочернего бота, через которого пришёл запрос (0 — главный)
CUR_TOKEN = ContextVar("cur_token", default=None)  # франшиза: ответы на апдейт дочернего бота — его токеном
DEV = os.environ.get("DEV") == "1"
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "game.db"))
WEB_DIR = os.environ.get("WEB_DIR", os.path.join(os.path.dirname(__file__), "..", "web"))
_BUILD = {"mtime": 0, "v": ""}


def build_v():
    """Номер текущей сборки фронта (хэш bundle.js из index.html). Клиент сравнивает со своим и перезагружается, если устарел."""
    try:
        # на проде фронт лежит в /var/www/nepridymal (nginx), а WEB_DIR указывает на ../web — берём первый существующий index.html
        p = next((x for x in (os.path.join(WEB_DIR, "index.html"), "/var/www/nepridymal/index.html") if os.path.exists(x)), "")
        mt = os.stat(p).st_mtime
        if mt != _BUILD["mtime"]:
            m = re.search(r"bundle\.js\?v=([0-9a-f]+)", open(p, encoding="utf-8").read())
            _BUILD.update(mtime=mt, v=m.group(1) if m else "")
    except OSError:
        pass
    return _BUILD["v"]


def app_url_v():
    """Адрес игры с номером сборки: Telegram кэширует страницу, а новый адрес всегда открывается свежим."""
    v = build_v()
    return APP_URL + ("&" if "?" in APP_URL else "?") + "v=" + v if v else APP_URL


SERVE_WEB = os.environ.get("SERVE_WEB") == "1"   # отдавать фронт самим (запуск без nginx — run.py)

START_STARS = conf("start.start_stars", 5000)
REF_BONUS = conf("start.ref_bonus", 2500)
FREE_CASE_EVERY = int(conf("start.free_case_hours", 3.0) * 3600)
DAILY_EVERY = int(conf("start.daily_hours", 20.0) * 3600)
DAILY_SCALE = conf("start.daily_scale", 1.0)
SELL_RATE = conf("economy.sell_rate", 0.85)
MARKET_FEE = conf("economy.market_fee", 0.05)
TRADE_FEE = conf("economy.trade_fee", 0.05)   # со звёзд, переданных в обмене, — в банк
INCOME_TAX = conf("economy.income_tax", 0.03)  # с собранного дохода и наград сейфа — в банк
DISCLAIMER = ("Это игра. Подарки и звёзды здесь игровые: звёзды можно купить за Telegram Stars, но вывести их или "
              "обменять на настоящие подарки Telegram нельзя. Картинки подарков — @GiftChanges (api.changes.tg).")
DISCLAIMER_NOSHOP = ("Это игра. Подарки и звёзды здесь игровые: вывести их или обменять на настоящие подарки Telegram нельзя. "
                     "Картинки подарков — @GiftChanges (api.changes.tg).")


def disclaimer():
    """Про покупку за Telegram Stars говорим, только пока владелец держит продажу включённой (админка → «Продажи»)."""
    import shop
    return DISCLAIMER if shop.shop_on() else DISCLAIMER_NOSHOP

# ============================== БД ==============================
LOCK = threading.RLock()
db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
db.row_factory = sqlite3.Row
db.executescript("""
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-16384;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=67108864;
PRAGMA busy_timeout=5000;
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT, username TEXT, photo TEXT,
  stars INTEGER, xp INTEGER DEFAULT 0, ref_by INTEGER, refs INTEGER DEFAULT 0,
  created INTEGER, last_free INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0, streak INTEGER DEFAULT 0,
  best_crash REAL DEFAULT 0, opened INTEGER DEFAULT 0,
  bio TEXT DEFAULT '', banner TEXT DEFAULT '', pinned TEXT DEFAULT '[]', seen INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS gifts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER, col TEXT, model TEXT, backdrop TEXT, symbol TEXT,
  num INTEGER, value INTEGER, created INTEGER, price INTEGER, listed INTEGER);
CREATE INDEX IF NOT EXISTS gifts_owner ON gifts(owner);
CREATE INDEX IF NOT EXISTS gifts_price ON gifts(price);
CREATE TABLE IF NOT EXISTS events(user INTEGER, kind TEXT, delta INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_user ON events(user, ts);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind, ts, delta);
CREATE INDEX IF NOT EXISTS events_kind_user ON events(kind, ts, user, delta);
CREATE TABLE IF NOT EXISTS feed(id INTEGER PRIMARY KEY AUTOINCREMENT, user INTEGER, gift INTEGER, cs TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS friends(a INTEGER, b INTEGER, status TEXT, ts INTEGER, PRIMARY KEY(a,b));
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, src INTEGER, dst INTEGER,
  give TEXT, give_stars INTEGER, want TEXT, want_stars INTEGER, status TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS pending_refs(user INTEGER PRIMARY KEY, ref INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY AUTOINCREMENT, gift INTEGER, col TEXT, model TEXT, backdrop TEXT, symbol TEXT,
  num INTEGER, value INTEGER, price INTEGER, seller INTEGER, buyer INTEGER, ts INTEGER);
""")


def _exec(sql, a, c=None):
    c = c or db
    try:
        return c.execute(sql, a)
    except sqlite3.OperationalError as e:
        if "integer overflow" not in str(e) or "SUM(" not in sql.upper():
            raise
        print(f"[db] integer overflow, retry with TOTAL(): {sql[:160]}", flush=True)
        return c.execute(sql.replace("SUM(", "TOTAL("), a)


def q(sql, *a):
    with LOCK:
        return _exec(sql, a).fetchall()


def q1(sql, *a):
    with LOCK:
        return _exec(sql, a).fetchone()


# Тяжёлые подсчёты (топы за сезон, полная сверка банка, редкость достижений) читаем отдельным соединением только для чтения,
# без общего лока: WAL позволяет читать параллельно с записью, и ставки остальных игроков их не ждут. Видны только
# закоммиченные данные — для таблиц лидеров это то же самое. Обычные запросы идут через общее соединение: у него тёплый кэш.
_RD = threading.local()


def _rd():
    c = getattr(_RD, "c", None)
    if c is None:
        if DB_PATH == ":memory:":
            return None
        c = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None, timeout=5)
        c.row_factory = sqlite3.Row
        c.executescript("PRAGMA query_only=1; PRAGMA cache_size=-8192; PRAGMA temp_store=MEMORY; PRAGMA mmap_size=67108864; PRAGMA busy_timeout=5000;")
        _RD.c = c
    return c


def qr(sql, *a):
    """Как q(), но без общего лока — для долгих агрегатов. Внутри tx() читает общим соединением (видит свои записи)."""
    c = None if LOCK._is_owned() else _rd()
    if c is None:
        return q(sql, *a)
    cur = _exec(sql, a, c)
    try:
        return cur.fetchall()
    finally:
        cur.close()


def qr_snap(*queries):
    """Несколько чтений одним согласованным снимком базы, без общего лока: [(sql, args), ...] -> [rows, ...]."""
    c = None if LOCK._is_owned() else _rd()
    if c is None:
        with LOCK:
            return [_exec(sq, a).fetchall() for sq, a in queries]
    c.execute("BEGIN")
    try:
        return [_exec(sq, a, c).fetchall() for sq, a in queries]
    finally:
        c.execute("COMMIT")


class tx:
    """Транзакция под общим локом: with tx(): ..."""
    def __enter__(self):
        LOCK.acquire()
        db.execute("BEGIN IMMEDIATE")

    def __exit__(self, et, ev, tb):
        try:
            db.execute("ROLLBACK" if et else "COMMIT")
        finally:
            LOCK.release()


def err(msg, code=400):
    raise HTTPException(code, msg)


now = lambda: int(time.time())

# ============================== щедрые выходные ==============================
# сб–вс (время сервера) казино щедрее; админ может включить/выключить вручную (kv.promo = auto|on|off)
db.executescript("""
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS case_keys(user INTEGER, cid TEXT, n INTEGER DEFAULT 0, PRIMARY KEY(user, cid));
""")
PROMO_PERKS = ["Кейсы −10%", "Шансы в апгрейде выше", "Мини-игры и краш отдают 98%",
               "Бесплатный кейс раз в 1,5 часа", "Бонус дня x2"]
_PROMO = {"ts": 0, "v": None}


def kv_get(k, default=None):
    r = q1("SELECT v FROM kv WHERE k=?", k)
    return r["v"] if r else default


def season_from():
    """Начало текущего сезона: рейтинги, призы и кэшбэк не считают то, что было до вайпа."""
    return int(kv_get("bank_from", 0) or 0)


def promo():
    """Активная акция или None. Кэш на 5 с — функция зовётся в каждой ставке."""
    t = time.time()
    if t - _PROMO["ts"] < 5:
        return _PROMO["v"]
    mode, lt = kv_get("promo", "off"), time.localtime(t)
    v = None
    if mode == "on" or (mode == "auto" and lt.tm_wday >= 5):
        midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + 1, 0, 0, 0, 0, 0, -1))
        until = midnight + (86400 if lt.tm_wday == 5 and mode == "auto" else 0)
        v = {"title": "Щедрые выходные" if mode == "auto" else "Щедрый день", "until": int(until) if mode == "auto" else None,
             "perks": PROMO_PERKS}
    _PROMO.update(ts=t, v=v)
    return v


def edge(base, promo_edge=0.98):
    """Возврат игроку: в акцию — не ниже promo_edge."""
    return max(base, promo_edge) if promo() else base


# ============================== сезонные ивенты: включаются сами по датам (UTC), каждый год ==============================
EVENTS = [
    {"id": "halloween", "title": "Хэллоуин", "from": (10, 24), "to": (11, 1), "case": "spooky", "sale": 0.15,   # больше нельзя: кейс отдаёт 90% цены, продажа подарка — 85% → при −30% был бы «станок» +9%
     "perks": ["Кейс «Хэллоуин» −15%", "Ивент-задания с повышенными наградами", "Тыквенное оформление игры"],
     "quests": [("hw_cases", "gift", "Открой 5 кейсов", "case", 5, 3000),
                ("hw_dogs", "paw", "Сыграй 15 раз в Пёсиков", "dogs", 15, 4000),
                ("hw_chicken", "flame", "Сыграй 5 раз в Курицу", "chicken", 5, 3000)]},
]


_EV = {"ts": 0, "v": None}


def event_active():
    """Текущий ивент или None (кэш 5 с). Админ может включить заранее для проверки: kv.event = <id> | off | auto."""
    if time.time() - _EV["ts"] < 5:
        return _EV["v"]
    _EV.update(ts=time.time(), v=_event_now())
    return _EV["v"]


def _event_now():
    force = kv_get("event", "auto")
    if force == "off":
        return None
    if force != "auto":
        return next((e for e in EVENTS if e["id"] == force), None)
    g = time.gmtime()
    md = (g.tm_mon, g.tm_mday)
    return next((e for e in EVENTS if e["from"] <= md <= e["to"]), None)


def event_public():
    e = event_active()
    if not e:
        return None
    g = time.gmtime()
    import calendar
    until = calendar.timegm((g.tm_year, e["to"][0], e["to"][1], 23, 59, 59)) + 1   # конец последнего дня (UTC)
    return {"id": e["id"], "title": e["title"], "case": e["case"], "sale": e["sale"], "perks": e["perks"], "until": until}


# курс банка (bank.py): множители призов, цены кейсов и скупки — банк богатый → щедрее, бедный → скупее
BANK_K = None


def bank_k():
    return BANK_K() if BANK_K else {"r": 1.0, "prize": 1.0, "case": 1.0, "sell": 0.0}


def prize_k(v):
    """Приз с учётом курса банка, круглыми суммами."""
    v = v * bank_k()["prize"]
    return int(round(v / 100) * 100) if v >= 1000 else int(round(v / 10) * 10)


def sell_rate():
    """Мгновенная продажа банку: базовая ставка (админка → «Комиссии») ± поправка курса банка, не выше 95%."""
    return round(min(0.95, max(0.05, SELL_RATE + bank_k()["sell"])), 4)


def case_price(c):
    if not c["price"]:
        return 0
    if c["id"] in E.FIXED_PRICE:   # кейс CS:GO — всегда ровно своя цена, без курса банка и акций
        return c["price"]
    # скидка/наценка от банка; вместе с акцией выходных — не дешевле −10%, чтобы кейсы не ушли в плюс игроку
    f = max(0.9, (0.9 if promo() else 1.0) * bank_k()["case"])
    price = int(round(c["price"] * f / 5) * 5)
    e = event_active()
    if e and e["case"] == c["id"]:
        price = min(price, int(round(c["price"] * (1 - e["sale"]) / 5) * 5))
    return price


def is_vip(u):
    return bool(u is not None and "vip_until" in u.keys() and (u["vip_until"] or 0) > now())


def free_every(u=None):
    """Перезарядка бесплатного кейса: в акцию и у VIP — вдвое быстрее (не суммируется)."""
    return FREE_CASE_EVERY // 2 if promo() or is_vip(u) else FREE_CASE_EVERY


# ============================== каталог / рендер-инфо ==============================
LOOK = {}
for _c, _d in E.CATALOG.items():
    LOOK[_c] = ({m[0]: m[1] for m in _d["models"]},
                {b[0]: b for b in _d["backdrops"]},
                {s[0]: s[1] for s in _d["symbols"]})
BACKDROPS = {}
for _d in E.CATALOG.values():
    for _b in _d["backdrops"]:
        BACKDROPS.setdefault(_b[0], _b)


def gift_out(r, owner=False):
    ml, bl, sl = LOOK[r["col"]]
    b = bl.get(r["backdrop"]) or BACKDROPS.get(r["backdrop"])
    g = {"id": r["id"], "col": r["col"], "model": r["model"], "backdrop": r["backdrop"], "symbol": r["symbol"],
         "num": r["num"], "value": r["value"], "price": r["price"],
         "mp": ml.get(r["model"], 0), "bp": b[1], "sp": sl.get(r["symbol"], 0), "c": b[2:6]}
    if owner:
        g["owner"] = r["owner"]
    return g


def preview_out(col, d):
    ml, bl, sl = LOOK[col]
    b = bl[d["backdrop"]]
    return {"col": col, "model": d["model"], "backdrop": d["backdrop"], "symbol": d["symbol"], "value": d["value"],
            "num": d["num"], "mp": ml[d["model"]], "bp": b[1], "sp": sl[d["symbol"]], "c": b[2:6]}


# ============================== уровни ==============================
def level(xp):
    return int(math.sqrt(xp / 100)) + 1


def level_info(xp):
    L = level(xp)
    lo, hi = 100 * (L - 1) ** 2, 100 * L ** 2
    return {"level": L, "xp": xp, "from": lo, "to": hi}


def level_bonus(L):
    return int((100 + 15 * (L - 1)) * conf("economy.reward_scale", 1.0))


try:
    db.execute("ALTER TABLE users ADD COLUMN lvl_paid INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass


def add_xp(uid, amount):
    """Начислить опыт; при повышении уровня — бонус звёздами. Возвращает новый уровень или None."""
    u = q1("SELECT xp, lvl_paid FROM users WHERE id=?", uid)
    old, new = max(level(u["xp"]), u["lvl_paid"] or 0), level(u["xp"] + amount)   # lvl_paid: за эти уровни бонус уже выдан (после срезки уровня — не платим повторно)
    db.execute("UPDATE users SET xp=xp+? WHERE id=?", (amount, uid))
    if new > old:
        # бонус за уровень не должен расти вместе с оборотом ставок: раньше 250×L возвращал ~6% от поставленного —
        # больше преимущества казино в любой игре («станок» через Плинко). Сейчас ≈0,4% от оборота.
        bonus = sum(level_bonus(L) for L in range(old + 1, new + 1))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (bonus, uid))
        event(uid, "level", bonus)
        return {"level": new, "bonus": bonus}
    return None


try:
    db.execute("ALTER TABLE users ADD COLUMN surprise INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
CLAN_TAX = {}   # uid → (id клана, ставка налога) — заполняет clans.py
TAXABLE = {"crash", "mines", "wheel", "duel", "dice", "limbo", "plinko", "tower", "slots", "blackjack", "dogs", "roulette", "hilo",
           "chicken", "avia", "scratch", "claw", "pump", "drill", "darts", "fish", "keno", "penalty", "safe", "ladder", "carousel"}   # игры на звёзды; кейсы, апгрейды, битвы и т. п. дают подарки — их не облагаем


BIGWIN_MIN = conf("economy.bigwin_min", 3000)   # выигрыш от этой суммы попадает в живую ленту крупных выигрышей (live.py)
BIG_KINDS = {"carousel", "safe", "ladder", "bankbet", "forecast", "crash", "mines", "wheel", "duel", "dice", "limbo", "plinko", "tower", "slots", "blackjack", "dogs", "roulette", "hilo",
             "chicken", "avia", "scratch", "battle", "starfall", "upgrade", "jroul", "cards", "craft", "claw", "pump", "drill", "darts", "fish", "keno", "penalty"}
db.executescript("""
CREATE TABLE IF NOT EXISTS bigwins(id INTEGER PRIMARY KEY, user INTEGER, kind TEXT, amount INTEGER, ts INTEGER);
""")
LUCKY_P = conf("economy.lucky_chance", 0.006)   # «удачный момент»: шанс сюрприза после раунда в игре (~раз в 170 раундов)
LUCKY = ([200, 300, 500, 1000, 2500], [40, 30, 20, 8, 2])
FLASH_LUCK = lambda: None   # flash.py: во время ивента «Удача ×N» → (N, начало ивента)


VAULT_TAKE = None   # bank.py: подарок из хранилища банка для выигрыша в апгрейде
FAUCET_K = lambda: 1.0   # bank.py: стабилизатор бонусов и пассивного дохода
BIGWIN_FEE, BIGWIN_FEE_MIN = conf("economy.bigwin_fee", 0.01), conf("economy.bigwin_fee_min", 10_000)
RECENT_WINS = {}   # share.py: последние выигрыши со ставкой, чтобы показать честный множитель на карточке
FAIR_DONE = None   # fair.py: учёт оборота и фактического возврата по играм


REC_WIN = None   # records.on_win, ставится при импорте records.py
AWAY_HOOK = None   # away.on_return, ставится при импорте away.py
ACH_PCT = {}   # achrare.py: доля игроков с каждым достижением, %
SELF_GUARD = None   # limits.guard: лимиты, которые игрок поставил себе сам


def event(uid, kind, delta, stake=None, pf=None, res=None):
    """Движение звёзд в журнал. stake — размер ставки: нужен, чтобы считать фактический возврат игры.
    pf/res — итог для проверки ставки в панели «Честность»."""
    db.execute("INSERT INTO events VALUES(?,?,?,?)", (uid, kind, delta, now()))
    if stake is not None and FAIR_DONE:
        FAIR_DONE(uid, kind, stake, delta + stake, pf, res)
    if stake and delta > 0 and REC_WIN:   # личные рекорды (records.py)
        REC_WIN(uid, kind, delta, stake)
    if stake and delta > 0:
        RECENT_WINS.setdefault(uid, []).append((kind, stake, delta, now()))
        del RECENT_WINS[uid][:-5]
        if len(RECENT_WINS) > 5000:
            RECENT_WINS.clear()
    if stake is not None and delta >= BIGWIN_FEE_MIN and BIGWIN_FEE > 0:   # сбор банка с крупного выигрыша, виден в журнале и в правилах
        fee = int(delta * BIGWIN_FEE)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (fee, uid))
        db.execute("INSERT INTO events VALUES(?,?,?,?)", (uid, "fee", -fee, now()))
    if delta >= BIGWIN_MIN and kind in BIG_KINDS:   # в живую ленту крупных выигрышей
        db.execute("INSERT INTO bigwins(user,kind,amount,ts) VALUES(?,?,?,?)", (uid, kind, delta, now()))
        db.execute("DELETE FROM bigwins WHERE id < (SELECT MAX(id) FROM bigwins) - 200")
        if CLAN_WIN and uid in CLAN_TAG:
            CLAN_WIN(uid, kind, delta)
    fl = FLASH_LUCK() if kind in TAXABLE else None
    if kind in TAXABLE and random.random() < LUCKY_P * (fl[0] if fl else 1):   # маленький сюрприз — не чаще раза в сутки, иначе его фармят ставками по 10 ⭐
        # во время «Удачи ×N» (flash.py) — ещё раз за ивент, даже если сегодня уже был; всё равно не больше одного за ивент
        if not q1("SELECT 1 FROM events WHERE user=? AND kind='lucky' AND ts>=?", uid, fl[1] if fl else now() - 86400):
            amt = random.choices(*LUCKY)[0]
            db.execute("UPDATE users SET stars=stars+?, surprise=surprise+? WHERE id=?", (amt, amt, uid))
            db.execute("INSERT INTO events VALUES(?,?,?,?)", (uid, "lucky", amt, now()))
    ct = CLAN_TAX.get(uid)
    if ct and ct[1] and delta > 0 and kind in TAXABLE:   # налог клана с чистого выигрыша → в казну клана
        tax = int(delta * ct[1])
        if tax > 0:
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (tax, uid))
            db.execute("UPDATE clans SET bank=bank+?, treasury=treasury+? WHERE id=?", (tax, tax, ct[0]))
            db.execute("UPDATE clan_members SET taxed=taxed+? WHERE user=?", (tax, uid))


# ============================== авторизация ==============================
SECRET = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()


def check_init_data(init):
    data = dict(urllib.parse.parse_qsl(init, keep_blank_values=True))
    h = data.pop("hash", None)
    if not h:
        return None
    dcs = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    if not hmac.compare_digest(hmac.new(SECRET, dcs.encode(), hashlib.sha256).hexdigest(), h):
        return None
    if now() - int(data.get("auth_date", 0)) > 7 * 86400:
        return None
    return data


def register(tg_user, start_param="", bid=0):
    uid = int(tg_user["id"])
    name = (tg_user.get("first_name", "") + " " + tg_user.get("last_name", "")).strip() or "Игрок"
    with tx():
        u = q1("SELECT id, seen FROM users WHERE id=?", uid)
        if u and now() - (u["seen"] or 0) < 60:
            return uid, None
        if u:
            if AWAY_HOOK:   # away.py: вернулся после перерыва — запомнить, с какого момента не было
                AWAY_HOOK(uid, u["seen"])
            db.execute("UPDATE users SET name=?, username=?, photo=COALESCE(?,photo), seen=? WHERE id=?",
                       (name, tg_user.get("username"), tg_user.get("photo_url"), now(), uid))
            return uid, None
        ref = None
        if start_param.startswith("ref_") and start_param[4:].isdigit():
            ref = int(start_param[4:])
        else:
            p = q1("SELECT ref FROM pending_refs WHERE user=?", uid)
            ref = p["ref"] if p else None
        if ref == uid or not (ref and q1("SELECT 1 FROM users WHERE id=?", ref)):
            ref = None
        nb, jb = refs.bonuses(bool(ref))   # суммы — в админке «Рефералы» (refs.py)
        db.execute("INSERT INTO users(id,name,username,photo,stars,created,seen,ref_by,bot,came_bot) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (uid, name, tg_user.get("username"), tg_user.get("photo_url"),
                    START_STARS + nb, now(), now(), ref, bid, bid))
        if ref:
            db.execute("UPDATE users SET stars=stars+?, refs=refs+1 WHERE id=?", (jb, ref))
            event(ref, "ref", jb)
            refs.on_register(uid, ref)   # ключ от кейса «от друга» и цель на двоих
    if ref:
        L1, B1 = refs.cfg("l1_level"), refs.cfg("l1_bonus")
        notify(ref, f"🎉 По твоей ссылке пришёл <b>{esc(name)}</b>." + (f" Тебе +{jb:,} ⭐".replace(",", " ") if jb else "")
               + (f"\n\nКогда он дойдёт до {L1} уровня — ещё +{B1:,} ⭐".replace(",", " ") if refs.cfg("on") and B1 else ""))
    return uid, ref


# админы — Telegram id через запятую в .env (ADMIN_IDS); заблокированным игрокам API отвечает 403
ADMINS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}
STEALTH = set()   # админы с включённым «режимом секретности» (admin.py): им не шлём служебные уведомления, пока режим включён
try:
    db.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
BANNED = {r[0] for r in db.execute("SELECT id FROM users WHERE banned=1")}


def auth(request: Request, x_init_data: str = Header(""), x_dev_user: str = Header("")):
    if DEV and x_dev_user:
        uid = int(x_dev_user)
        register({"id": uid, "first_name": f"Тест {uid}", "username": f"test{uid}"})
        if uid in BANNED:
            err("Аккаунт заблокирован", 403)
        request.state.uid = uid   # для журнала действий (actlog.py)
        return uid
    v = franchise.verify(x_init_data)   # главный бот — HMAC токеном, дочерние — подпись Telegram (franchise.py)
    if not v or "user" not in v[1]:
        err("unauthorized", 401)
    bid, data = v[0], v[1]
    if bid and not franchise.active(bid):
        err(f"Этот бот отключён — играй в @{franchise.face_name()}", 403)
    uid, _ = register(json.loads(data["user"]), data.get("start_param", ""), bid)
    franchise.seen_via(uid, bid)
    request.state.uid = uid   # для журнала действий (actlog.py)
    if uid in BANNED:
        err("Аккаунт заблокирован", 403)
    return uid


# ============================== бот ==============================
API = f"https://api.telegram.org/bot{TOKEN}/"
http: httpx.AsyncClient = None
LOOP: asyncio.AbstractEventLoop = None


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def tg_call(method, _token=None, **params):
    """_token — чужой бот франшизы; без него — бот текущего апдейта (вебхук франшизы) или главный."""
    tok = _token or CUR_TOKEN.get()
    r = await http.post(f"https://api.telegram.org/bot{tok}/{method}" if tok else API + method, json=params, timeout=70)
    return r.json()


def bot_name():
    """Бот, через которого игрок сейчас играет: на него — реф-ссылки, приглашения в клан, подарки, столы."""
    b = VIA_BOT.get()
    return franchise.username(b) if b else franchise.face_name()   # «лицо» игры назначается в админке


def notif_card(text):
    """JPEG-карточка к уведомлению или None. Выключается в kv: notif_cards = off. Подпись к фото — до 1024 символов."""
    if kv_get("notif_cards", "on") == "off" or len(text) > 1000:
        return None
    import notifimg
    return notifimg.card(text)


async def tg_photo(tok, chat_id, img, caption, kb):
    """sendPhoto с картинкой из памяти (multipart)."""
    try:
        r = await http.post(f"https://api.telegram.org/bot{tok or TOKEN}/sendPhoto", timeout=70,
                            data={"chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML", "reply_markup": json.dumps(kb)},
                            files={"photo": ("card.jpg", img, "image/jpeg")})
        return r.json()
    except Exception as e:
        print("photo error", chat_id, e, flush=True)
        return {}


def notify(uid, text, url=None):
    """Сообщение игроку от бота (из любого потока, без ожидания) + копия во «входящие» (колокольчик в игре)."""
    try:
        with LOCK:   # внутри tx() вставка станет частью транзакции, снаружи — отдельной записью
            db.execute("INSERT INTO inbox(user,text,ts) VALUES(?,?,?)", (uid, html_lib.unescape(re.sub(r"<[^>]+>", "", text)), int(time.time())))
    except Exception as e:
        print("inbox", e, flush=True)
    if LOOP is None:
        return
    kb = {"inline_keyboard": [[{"text": "Открыть", "web_app": {"url": url or APP_URL}}]]}

    async def send():
        try:
            tok = franchise.token_for(uid)
            # красивая карточка к сообщению (notifimg.py); не распознали тип / выключено / длинный текст — обычное сообщение
            img = await asyncio.get_running_loop().run_in_executor(None, notif_card, text)
            r = await tg_photo(tok, uid, img, text, kb) if img else {}
            if img and not r.get("ok") and tok != TOKEN:
                r = await tg_photo(TOKEN, uid, img, text, kb)
            if not r.get("ok"):
                r = await tg_call("sendMessage", _token=tok, chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb)
            if not r.get("ok") and tok != TOKEN:   # бот-франшиза не смог (игрок его заблокировал и т. п.) — пробуем главным
                r = await tg_call("sendMessage", _token=TOKEN, chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb)
            if not r.get("ok"):
                print("notify fail", uid, r.get("description"), flush=True)
        except Exception as e:
            print("notify error", uid, e, flush=True)
    asyncio.run_coroutine_threadsafe(send(), LOOP)


async def bot_description(token=None):
    await tg_call("setMyDescription", _token=token, description=(
        "🎁 Кейс-симулятор подарков Telegram: 29 кейсов и 20+ игр — краш, Самолётик, Курица, Пёсики, слоты, плинко, мины, "
        "битва кейсов, скретч-карты, дуэли с друзьями. Маркет, крипта, кланы, турниры каждые 3 дня и альбом коллекций.\n\n⚠️ " + disclaimer()))


async def bot_setup(token=None):
    """token — бот франшизы (настраивается так же, без /franchise)."""
    for i in range(3):   # у только что созданного бота-франшизы Telegram иногда не принимает с первого раза
        r = await tg_call("setChatMenuButton", _token=token, menu_button={"type": "web_app", "text": "Играть", "web_app": {"url": app_url_v()}})
        if r.get("ok"):
            break
        print("setChatMenuButton", "франшиза" if token else "главный", r.get("description"), flush=True)
        await asyncio.sleep(2 + 3 * i)
    await tg_call("setMyCommands", _token=token, commands=[{"command": "start", "description": "Играть"},
                                                           {"command": "ref", "description": "Моя реф-ссылка"}]
                  + ([] if token else [{"command": "franchise", "description": "Свой бот с этой игрой"}]))
    await bot_description(token)
    await tg_call("setMyShortDescription", _token=token, short_description="Игра-симулятор подарков: кейсы, краш, слоты, маркет. Подарки и звёзды игровые 🎁")


async def bot_loop():
    while True:
        try:
            await bot_setup()
            break
        except Exception as e:
            print("bot setup:", e, flush=True)
            await asyncio.sleep(10)
    offset = 0
    while True:
        try:
            res = await tg_call("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "pre_checkout_query", "managed_bot", "callback_query", "inline_query", "chosen_inline_result"])
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                m = upd.get("message")
                if upd.get("managed_bot"):   # игрок создал бота-франшизу / сменил токен (franchise.py)
                    await franchise.on_managed(upd["managed_bot"])
                elif upd.get("callback_query"):   # кнопки под опросом (polls.py)
                    await polls.on_callback(upd["callback_query"])
                elif upd.get("pre_checkout_query"):   # оплата Telegram Stars (shop.py)
                    await shop.on_pre_checkout(upd["pre_checkout_query"])
                elif m and m.get("successful_payment"):
                    await asyncio.get_running_loop().run_in_executor(None, shop.on_paid, m)
                elif upd.get("inline_query"):   # @бот <сумма> в чате — инлайн-чек (pay.py)
                    await pay.on_inline(upd["inline_query"])
                elif upd.get("chosen_inline_result"):   # чек отправлен в чат — резервируем средства
                    cir = upd["chosen_inline_result"]
                    await asyncio.get_running_loop().run_in_executor(None, pay.reserve_cheque, cir["from"]["id"], cir["result_id"])
                elif m and m.get("text", "").startswith("/"):
                    await on_command(m)
        except Exception as e:
            print("poll:", e, flush=True)
            await asyncio.sleep(5)


async def on_command(m):
    uid, text = m["from"]["id"], m["text"]
    cmd, _, arg = text.partition(" ")
    kb = {"inline_keyboard": [[{"text": "🎁 Играть", "web_app": {"url": app_url_v()}}]]}
    if CUR_TOKEN.get() is None and (cmd.startswith("/franchise") or (cmd.startswith("/start") and arg == "franchise")):
        await franchise.cmd(m)   # только в главном боте
        return
    if cmd.startswith("/start") and arg.startswith("room_") and arg[5:].isdigit():
        await tg_call("sendMessage", chat_id=uid, parse_mode="HTML", text="🃏 Тебя зовут за игровой стол — жми кнопку, чтобы сесть",
                      reply_markup={"inline_keyboard": [[{"text": "🃏 Сесть за стол", "web_app": {"url": APP_URL + "?room=" + arg[5:]}}]]})
        return
    if cmd.startswith("/start") and arg.startswith("gift_"):   # подарок по ссылке (presents.py)
        lk = q1("SELECT * FROM gift_links WHERE code=?", arg[5:])
        if lk:
            with tx():   # новичок по подарку — приглашение отправителя
                if not q1("SELECT 1 FROM users WHERE id=?", uid) and lk["sender"] != uid:
                    db.execute("INSERT OR REPLACE INTO pending_refs VALUES(?,?,?)", (uid, lk["sender"], now()))
            s = q1("SELECT name FROM users WHERE id=?", lk["sender"])
            await tg_call("sendMessage", chat_id=uid, parse_mode="HTML",
                          text=f"🎁 <b>{esc(s['name'] if s else 'Друг')}</b> прислал тебе подарок! Жми, чтобы распаковать" + (f"\n\n<i>«{esc(lk['text'])}»</i>" if lk["text"] else ""),
                          reply_markup={"inline_keyboard": [[{"text": "🎁 Открыть подарок", "web_app": {"url": APP_URL + "?gift=" + arg[5:]}}]]})
            return
    if cmd.startswith("/start") and arg.startswith("pay_"):   # QR / ссылка «Получить» (pay.py): pay_<id>[_<сумма>]
        part = arg[4:].split("_")
        if part[0].isdigit() and (len(part) == 1 or part[1].isdigit()):
            s = q1("SELECT name FROM users WHERE id=?", int(part[0]))
            if s:
                amt = int(part[1]) if len(part) > 1 else 0
                await tg_call("sendMessage", chat_id=uid, parse_mode="HTML",
                              text=f"💸 Перевод игроку <b>{esc(s['name'])}</b>" + (f": <b>{amt} ⭐</b>" if amt else "") + "\nЖми кнопку, чтобы отправить",
                              reply_markup={"inline_keyboard": [[{"text": "💸 Перевести", "web_app": {"url": APP_URL + f"?pay={part[0]}&amt={amt}"}}]]})
                return
    if cmd.startswith("/start") and arg.startswith("claim_"):   # инлайн-чек: забрать (pay.py)
        register(m["from"])   # чек может забрать и новичок — заводим аккаунт из данных Telegram
        r = await asyncio.get_running_loop().run_in_executor(None, pay.claim_cheque, uid, arg[6:])
        if r.get("ok"):
            amt_s = f"{r['amount']:,}".replace(",", " ")
            await tg_call("sendMessage", chat_id=uid, parse_mode="HTML",
                          text=f"🎁 Ты получил чек на <b>{amt_s} ⭐</b> от <b>{esc(r['from'])}</b>! Звёзды уже на балансе.", reply_markup=kb)
        else:
            await tg_call("sendMessage", chat_id=uid, parse_mode="HTML", text="🧾 " + esc(r["err"]), reply_markup=kb)
        return
    if cmd.startswith("/start") and arg.startswith("gw_") and arg[3:].isdigit():   # розыгрыш из канала (giveaway.py)
        g = q1("SELECT title FROM gw WHERE id=?", int(arg[3:]))
        if g:
            await tg_call("sendMessage", chat_id=uid, parse_mode="HTML", text=f"Розыгрыш «{esc(g['title'])}». Жми кнопку, чтобы участвовать",
                          reply_markup={"inline_keyboard": [[{"text": "Участвовать", "web_app": {"url": APP_URL + "?gw=" + arg[3:]}}]]})
            return
    if cmd.startswith("/start") and arg == "wallet":   # из инлайн-подсказки «открой кошелёк»
        await tg_call("sendMessage", chat_id=uid, parse_mode="HTML",
                      text="💸 Открой кошелёк в игре — звёзды можно слать по адресу, QR или через @бот прямо в чате.", reply_markup=kb)
        return
    if cmd.startswith("/start") and arg.startswith("clan_") and arg[5:].isdigit():
        c = q1("SELECT name, tag FROM clans WHERE id=?", int(arg[5:]))
        if c:
            await tg_call("sendMessage", chat_id=uid, parse_mode="HTML", text=f"🛡 Тебя зовут в клан <b>[{esc(c['tag'])}] {esc(c['name'])}</b> — жми кнопку",
                          reply_markup={"inline_keyboard": [[{"text": "🛡 Открыть клан", "web_app": {"url": APP_URL + "?clan=" + arg[5:]}}]]})
            return
    if cmd.startswith("/start"):
        if arg.startswith("ref_") and arg[4:].isdigit() and int(arg[4:]) != uid:
            with tx():
                if not q1("SELECT 1 FROM users WHERE id=?", uid):
                    db.execute("INSERT OR REPLACE INTO pending_refs VALUES(?,?,?)", (uid, int(arg[4:]), now()))
        txt = ("🎁 <b>Кейс-симулятор подарков</b>\n\nОткрывай кейсы, лови редкие модели и фоны, играй в краш, плинко, башню и слоты, "
               "вызывай друзей на дуэли, торгуй на маркете и выполняй задания.\n\n"
               f"Старт: <b>{START_STARS} ⭐</b>" + (f" + <b>{refs.cfg('new_bonus')} ⭐</b> за приглашение" if arg.startswith("ref_") and refs.cfg("on") and refs.cfg("new_bonus") else "")
               + ("\nИ ключ от кейса в подарок от друга, он уже ждёт в игре." if arg.startswith("ref_") and refs.cfg("on") and refs.cfg("gift_on") else "")
               + f"\n\n<i>⚠️ {esc(disclaimer())}</i>")
        await tg_call("sendMessage", chat_id=uid, text=txt, parse_mode="HTML", reply_markup=kb)
    elif cmd.startswith("/ref"):
        link = f"https://t.me/{bot_name()}?start=ref_{uid}"
        c = refs.cfg
        await tg_call("sendMessage", chat_id=uid, parse_mode="HTML", disable_web_page_preview=True,
                      text=(f"👥 <b>Приглашай друзей</b>\n\nТвоя ссылка:\n{link}\n\n"
                            + (f"• другу сразу +{c('new_bonus'):,} ⭐\n" if c("new_bonus") else "")
                            + (f"• тебе сразу +{c('join_bonus'):,} ⭐\n" if c("join_bonus") else "")
                            + (f"• друг дошёл до {c('l1_level')} ур. — тебе +{c('l1_bonus'):,} ⭐\n" if c("l1_bonus") else "")
                            + (f"• до {c('l2_level')} ур. — ещё +{c('l2_bonus'):,} ⭐\n" if c("l2_bonus") else "")
                            + (f"• {c('buy_pct')}% от звёзд, которые друг купит\n" if c("buy_pct") else "")
                            + ("• призы за рубежи и недельный топ — в игре: «Пригласи друга»" if c("milestones") or c("top_on") else "")
                            ).replace(",", " ") if c("on") else f"Твоя ссылка:\n{link}",
                      reply_markup={"inline_keyboard": [[{"text": "📤 Отправить другу", "url": "https://t.me/share/url?url=" + urllib.parse.quote(link)}]]})


# ============================== краш ==============================
CR = {"round": 0, "phase": "bet", "until": 0.0, "start": 0.0, "crash": 1.0, "bets": {}, "history": deque(maxlen=20),
      "seed": "", "seed_hash": "", "chain": 0, "pos": 0, "edge": 0.97}
CRASH_EDGE = conf("games.crash_edge", 0.97)   # возврат игроку в краше
CRASH_K = 0.065  # множитель = e^(k·t): 2x ≈ 10.7 c
BET_TIME, END_TIME = 8.0, 4.0
# Защита от пинга: о взрыве сервер объявляет с задержкой CASHOUT_GRACE. Пока идёт задержка, никто не знает, что ракета
# уже взорвалась, поэтому кэшаут с показанным ДО взрыва множителем можно честно оплатить. Объявлять сразу и платить
# задним числом нельзя: бот, увидев взрыв, забирал бы ставку в каждом раунде.
CASHOUT_GRACE = 0.8


def crash_mult(t):
    return math.exp(CRASH_K * max(0.0, t))


def gen_crash(r, e):
    return max(1.0, min(10000.0, math.floor(e * 100 / (1 - r)) / 100))


def _crash_uniform(seed):
    """Точка краша раунда — из HMAC сида раунда (provably fair: хэш сида публикуем ДО раунда)."""
    return int(hmac.new(seed.encode(), b"crash", hashlib.sha256).hexdigest()[:15], 16) / 16 ** 15


def _cashout(uid, b, m):
    with LOCK:  # автовывод и ручной вывод могут прийти одновременно
        if b["cashed"] is not None:
            return 0
        b["cashed"] = round(m, 2)
    pay = int(b["amount"] * m)
    with tx():
        db.execute("UPDATE users SET stars=stars+?, best_crash=MAX(best_crash,?) WHERE id=?", (pay, round(m, 2), uid))
        event(uid, "crash", pay - b["amount"], stake=b["amount"])
    return pay


async def crash_loop():
    while True:
        link = await asyncio.to_thread(fair.crash_next)   # сид раунда — следующее звено опубликованной цепочки хэшей
        seed = link["seed"]
        e = edge(tuned("games.crash_edge", CRASH_EDGE), 0.98)   # возврат фиксируем СЕЙЧАС — верификатору он нужен будет после взрыва
        CR.update(round=CR["round"] + 1, phase="bet", until=time.time() + BET_TIME, bets={}, seed=seed, edge=e, chain=link["chain"], pos=link["pos"],
                  seed_hash=hashlib.sha256(seed.encode()).hexdigest(), crash=gen_crash(_crash_uniform(seed), e))
        await asyncio.sleep(BET_TIME)
        CR.update(phase="run", start=time.time())
        while True:
            m = crash_mult(time.time() - CR["start"])
            for uid, b in list(CR["bets"].items()):
                if b["cashed"] is None and b["auto"] and b["auto"] <= m and b["auto"] < CR["crash"]:
                    _cashout(uid, b, b["auto"])
            if m >= CR["crash"]:
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(CASHOUT_GRACE)   # окно для запросов, ушедших до взрыва; для всех раунд ещё в полёте
        CR.update(phase="end", until=time.time() + END_TIME)
        CR["history"].appendleft(CR["crash"])
        with tx():
            fair.crash_log(CR["chain"], CR["pos"], CR["round"], CR["crash"], seed, CR["edge"])
            for uid, b in CR["bets"].items():
                if b["cashed"] is None:
                    event(uid, "crash", -b["amount"], stake=b["amount"])
        await asyncio.sleep(END_TIME)


# ============================== приложение ==============================
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)   # бандл 1,4 МБ → 0,4 МБ: через туннель это секунды загрузки


@app.exception_handler(ValueError)
@app.exception_handler(TypeError)
@app.exception_handler(AttributeError)
@app.exception_handler(KeyError)
async def _bad_input(request: Request, e: Exception):
    """Кривые данные в запросе (строка вместо числа, число вместо списка) — понятный 400 вместо 500. Трассировка — в лог."""
    import traceback
    print("BADINPUT", request.method, request.url.path, "".join(traceback.format_exception(e))[-600:], flush=True)
    return JSONResponse({"detail": "Неверные данные — обнови экран"}, status_code=400)


@app.on_event("startup")
async def startup():
    global http, LOOP
    LOOP = asyncio.get_running_loop()
    http = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0"))  # только IPv4
    asyncio.create_task(crash_loop())
    asyncio.create_task(rich.rich_loop())
    asyncio.create_task(pay.cheque_loop())   # возврат невостребованных инлайн-чеков
    if not DEV:  # локально бот не поллит, чтобы не драться с продом за getUpdates
        asyncio.create_task(bot_loop())
        asyncio.create_task(reminder_loop())
        asyncio.create_task(franchise.startup())


@app.on_event("shutdown")
def crash_refund():
    """Перезапуск посреди раунда краша: ставки живут в памяти — возвращаем всем, кто ещё не забрал и не проиграл."""
    if CR["phase"] == "end":
        return
    with tx():
        for uid, b in CR["bets"].items():
            if b["cashed"] is None:
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (b["amount"], uid))
    CR["bets"] = {}


R = "/np/api"


CLAN_TAG = {}   # uid → тег клана (заполняет clans.py)
RICH_RANK = {}  # uid → место в топе богачей 1–10 (обновляет rich.py)


TITLE_NAMES = {}   # id титула → название (заполняет seasons.py)


STYLE_BRIEF = None   # style.py: статус, акцент, эффект ника, купленная рамка
CLAN_LOOK = None     # clans.py: цвет и уровень клана (цветной тег, клановая рамка)
CLAN_WIN = None      # clans.py: крупный выигрыш участника → системное сообщение в чат клана
CLAN_UNREAD = None   # clans.py: непрочитанные в чате клана


def user_brief(r):
    keys = r.keys()
    title = TITLE_NAMES.get(r["title"]) if "title" in keys and r["title"] else None
    frame = r["frame"] if "frame" in keys and r["frame"] and (r["frame_until"] or 0) > now() else None
    name = (r["nick"] if "nick" in keys and r["nick"] else r["name"]) or "Игрок"
    photo = (r["avatar"] if "avatar" in keys and r["avatar"] else r["photo"])
    return {"id": r["id"], "name": name, "username": r["username"], "photo": photo, "level": level(r["xp"]),
            "clan": CLAN_TAG.get(r["id"]), "crown": RICH_RANK.get(r["id"]), "title": title, "frame": frame, "vip": is_vip(r),
            **(STYLE_BRIEF(r) if STYLE_BRIEF else {}), **(CLAN_LOOK(r["id"]) if CLAN_LOOK else {})}


def net_worth(uid):
    v = q1("SELECT COALESCE(SUM(value),0) v FROM gifts WHERE owner=?", uid)["v"]
    return v + q1("SELECT stars FROM users WHERE id=?", uid)["stars"]


def counters(uid):
    return {
        "friendReq": q1("SELECT COUNT(*) n FROM friends WHERE b=? AND status='pending'", uid)["n"],
        "trades": q1("SELECT COUNT(*) n FROM trades WHERE dst=? AND status='open'", uid)["n"],
        "duels": q1("SELECT COUNT(*) n FROM duels WHERE b=? AND status='open'", uid)["n"],
        "rooms": sum(1 for r in q("SELECT players, invited FROM rooms WHERE status='waiting'")
                     if uid in json.loads(r["invited"] or "[]") and uid not in json.loads(r["players"])),
        "quests": sum(1 for x in quests_state(uid) if x["have"] >= x["need"] and not x["claimed"]),
    }


@app.get(R + "/me")
def me(uid=Depends(auth)):
    u = q1("SELECT * FROM users WHERE id=?", uid)
    t = now()
    return {**user_brief(u), "stars": u["stars"], "lv": level_info(u["xp"]), "refs": u["refs"],
            "freeIn": max(0, u["last_free"] + free_every(u) - t), "vip": u["vip_until"] if is_vip(u) else 0, "dailyIn": max(0, u["last_daily"] + DAILY_EVERY - t),
            "streakNext": u["streak"] + 1 if t - u["last_daily"] < 48 * 3600 else 1,   # какой день серии будет при следующем заборе
            "streak": u["streak"], "streakBest": u["best_streak"] if "best_streak" in u.keys() else 0, "streakMs": _next_ms(uid),
            "refLink": f"https://t.me/{bot_name()}?start=ref_{uid}", "refBonus": refs.cfg("new_bonus") if refs.cfg("on") else 0, "ref": refs.summary(uid),
            "disclaimer": disclaimer(), "build": build_v(), "shopOn": shop.shop_on(), "notif": bool(u["notif"]) if "notif" in u.keys() else True, "admin": uid in ADMINS, "stealth": uid in STEALTH, "promo": promo(), "event": event_public(), "surprise": u["surprise"] if "surprise" in u.keys() else 0,
            "keys": q1("SELECT COALESCE(SUM(n),0) n FROM case_keys WHERE user=?", uid)["n"],
            "sparks": __import__("sparks").sparks_waiting(uid),
            "gamesOff": __import__("gates").games_state(),
            "franchise": franchise.offer(uid),
            "flash": flash.public(uid),
            "fees": fees.public(),
            "wipe": wipe.public(uid), "polls": polls.public(uid),
            "tickets": tickets.me_info(uid),
            # фронт считает иксы по этим же коэффициентам и показывает возврат каждой игры в её шапке
            "edges": {**fair.declared(), "x": edge(tuned("games.edge", EDGE)), "mines": edge(tuned("games.mines_edge", MINES_EDGE)), "upg": edge(tuned("games.upgrade_edge", UPG_EDGE), 0.93)},
            "inbox": q1("SELECT COUNT(*) n FROM inbox WHERE user=? AND id>?", uid, u["inbox_read"] if "inbox_read" in u.keys() else 0)["n"], **counters(uid), "clanChat": CLAN_UNREAD(uid) if CLAN_UNREAD else 0, "cashback": __import__("retain").cashback_preview(uid)}


def look_of(col, seed):
    """Стабильный «образ» коллекции для витрины: фон + узор (как у улучшенного подарка)."""
    rng = random.Random(f"{col}:{seed}")
    d = E.CATALOG.get(col) or E.CATALOG[E.CUSTOM_DONOR]   # обложка кейса CS:GO — не коллекция, образ берём у донора
    b = rng.choice(d["backdrops"])
    s = rng.choice(d["symbols"])
    return {"c": b[2:6], "symbol": s[0]}


db.execute("CREATE TABLE IF NOT EXISTS case_limit(cid TEXT PRIMARY KEY, n INTEGER)")
for _cid, _n in E.LIMITED.items():
    db.execute("INSERT OR IGNORE INTO case_limit VALUES(?,?)", (_cid, _n))


def _case_limit(cid):
    if cid not in E.LIMITED:
        return {}
    return {"limit": E.LIMITED[cid], "left": q1("SELECT n FROM case_limit WHERE cid=?", cid)["n"]}


@app.get(R + "/cases")
def cases(uid=Depends(auth)):
    keys = {r["cid"]: r["n"] for r in q("SELECT cid, n FROM case_keys WHERE user=? AND n>0", uid)}
    out = []
    for c in E.CASES.values():
        top = max(c["odds"], key=lambda x: E.base(x))
        items = []
        for k, v in c["odds"].items():
            items.append({"col": k, "p": round(v * 100, 3), "base": E.base(k), "ev": round(c["evs"][k]), **look_of(k, "shop")})
        items.sort(key=lambda x: -x["ev"])
        out.append({"id": c["id"], "title": E.case_title(c["id"], uid), "price": case_price(c), "full": c["price"], "keys": keys.get(c["id"], 0),
                    "level": c["level"], "cover": E.case_cover(c["id"], uid), **_case_limit(c["id"]),
                    "top": top, "pat": look_of(E.case_cover(c["id"], uid), c["id"])["symbol"],
                    "previews": [x["col"] for x in items[:3]], "items": items})
    return out


@app.post(R + "/case/{cid}/open")
def open_case(cid: str, n: int = 1, uid=Depends(auth)):
    c = E.CASES.get(cid) or err("нет такого кейса")
    n = 1 if cid == "free" else max(1, min(10, n))
    t = now()
    with tx():
        if cid in E.LIMITED:   # лимитный тираж: остаток уменьшается в той же транзакции
            left = q1("SELECT n FROM case_limit WHERE cid=?", cid)["n"]
            if left < n:
                err("Тираж закончился" if not left else f"Осталось только {left}")
            db.execute("UPDATE case_limit SET n=n-? WHERE cid=?", (n, cid))
        u = q1("SELECT * FROM users WHERE id=?", uid)
        price = case_price(c)
        kr = q1("SELECT n FROM case_keys WHERE user=? AND cid=?", uid, cid)
        keys = min(n, kr["n"] if kr else 0)   # сначала тратим ключи (выданные админом), остальное — за звёзды
        if keys < n and level(u["xp"]) < c["level"]:   # ключом можно открыть и без нужного уровня
            err(f"Нужен {c['level']} уровень")
        if SELF_GUARD and cid != "free" and n > keys:   # за звёзды — под лимиты игрока; бесплатный кейс и ключи нет
            SELF_GUARD(uid, price * (n - keys))
        if keys:
            db.execute("UPDATE case_keys SET n=n-? WHERE user=? AND cid=?", (keys, uid, cid))
        elif cid == "free":
            if u["last_free"] + free_every(u) > t:
                err("Бесплатный кейс ещё перезаряжается")
            db.execute("UPDATE users SET last_free=? WHERE id=?", (t, uid))
        if u["stars"] < price * (n - keys):
            err("Не хватает звёзд")
        ids = []
        rng = fair.stream(uid, "case", cid)
        drops = []
        for i in range(n):
            d = E.open_case(cid, rng)
            drops.append(d["value"])
            cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                             (uid, d["col"], d["model"], d["backdrop"], d["symbol"], d["num"], d["value"], t))
            ids.append(cur.lastrowid)
            if i < keys:
                event(uid, "gift", d["value"])
            else:
                event(uid, "case", d["value"] - price, stake=price)
        fair.record(uid, "case", price * (n - keys), sum(drops), {"case": cid, "drops": drops}, fair.close_stream(rng))
        if keys:
            refs.on_key_open(uid, cid, q1("SELECT col FROM gifts WHERE id=?", ids[0])["col"])
        best = max(ids, key=lambda i: q1("SELECT value FROM gifts WHERE id=?", i)["value"])
        __import__("records").on_gift(uid, best, q1("SELECT value FROM gifts WHERE id=?", best)["value"])
        db.execute("INSERT INTO feed(user,gift,cs,ts) VALUES(?,?,?,?)", (uid, best, cid, t))
        db.execute("UPDATE users SET stars=stars-?, opened=opened+? WHERE id=?", (price * (n - keys), n, uid))
        lvl = add_xp(uid, max(20, c["price"] // 10) * n)
        stars = q1("SELECT stars FROM users WHERE id=?", uid)["stars"]
    # ленты рулеток: случайные предметы из кейса, выигрыш на позиции WIN
    WIN = 42
    gifts, strips = [], []
    for gid in ids:
        g = gift_out(q1("SELECT * FROM gifts WHERE id=?", gid))
        strip = [preview_out(x["col"], x) for x in (E.open_case(cid) for _ in range(50))]
        strip[WIN] = g
        gifts.append(g)
        strips.append(strip)
    return {"gifts": gifts, "strips": strips, "gift": gifts[0], "strip": strips[0], "win": WIN, "stars": stars, "levelup": lvl,
            "keysUsed": keys, "keys": (kr["n"] - keys) if kr else 0}


@app.post(R + "/daily")
def daily(uid=Depends(auth)):
    t = now()
    with tx():
        u = q1("SELECT * FROM users WHERE id=?", uid)
        if u["last_daily"] + DAILY_EVERY > t:
            err("Ещё рано")
        streak = u["streak"] + 1 if t - u["last_daily"] < 48 * 3600 else 1
        bonus = int((300 + 100 * min(streak, 7)) * DAILY_SCALE * FAUCET_K()) * (2 if promo() else 1) * (2 if is_vip(u) else 1)
        db.execute("UPDATE users SET stars=stars+?, last_daily=?, streak=?, best_streak=MAX(best_streak,?) WHERE id=?", (bonus, t, streak, streak, uid))
        event(uid, "daily", bonus)
        key = STREAK_KEYS.get(streak) or (STREAK_KEYS[7] if streak > 7 and streak % 7 == 0 else None)
        if key:   # за серию дней — ключ от кейса
            db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,1) ON CONFLICT(user,cid) DO UPDATE SET n=n+1", (uid, key))
        ms = None   # веха серии — разовый крупный приз (звёзды + ключ), выдаётся один раз за достигнутый день
        if streak in STREAK_MS and not q1("SELECT 1 FROM streak_ms WHERE user=? AND day=?", uid, streak):
            amt, mcid = STREAK_MS[streak]
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amt, uid))
            db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,1) ON CONFLICT(user,cid) DO UPDATE SET n=n+1", (uid, mcid))
            db.execute("INSERT INTO streak_ms(user,day,ts) VALUES(?,?,?)", (uid, streak, t))
            event(uid, "daily", amt)
            ms = {"day": streak, "stars": amt, "key": E.case_title(mcid, uid)}
    return {"bonus": bonus, "streak": streak, "key": E.case_title(key, uid) if key else None, "milestone": ms, "nextMs": _next_ms(uid),
            "nextKey": next(({"day": d, "title": E.case_title(c, uid)} for d, c in sorted(STREAK_KEYS.items()) if d > streak),
                            {"day": (streak // 7 + 1) * 7, "title": E.case_title(STREAK_KEYS[7], uid)})}


STREAK_KEYS = {2: "pepehunt", 3: "luck", 5: "hearthunt", 7: "lux"}   # день серии → ключ от кейса (далее каждые 7 дней — «Роскошь»)
# разовые вехи серии: день → (звёзды, ключ от кейса). Дают долгую цель заходить каждый день неделями.
STREAK_MS = {14: (10_000, "elite"), 30: (30_000, "mega"), 60: (75_000, "mega"), 100: (200_000, "mega")}
try:
    db.execute("ALTER TABLE users ADD COLUMN best_streak INTEGER DEFAULT 0")   # рекорд серии — для показа и мотивации
except sqlite3.OperationalError:
    pass
db.execute("CREATE TABLE IF NOT EXISTS streak_ms(user INTEGER, day INTEGER, ts INTEGER, PRIMARY KEY(user, day))")


def _next_ms(uid):
    """Ближайшая невзятая веха серии (для показа цели)."""
    done = {r["day"] for r in q("SELECT day FROM streak_ms WHERE user=?", uid)}
    for d in sorted(STREAK_MS):
        if d not in done:
            amt, cid = STREAK_MS[d]
            return {"day": d, "stars": amt, "key": E.case_title(cid, uid)}
    return None


@app.get(R + "/feed")
def feed(uid=Depends(auth)):
    rows = q("""SELECT f.cs, g.*, COALESCE(NULLIF(u.nick,''),u.name) uname, COALESCE(NULLIF(u.avatar,''),u.photo) uphoto FROM feed f JOIN gifts g ON g.id=f.gift
                JOIN users u ON u.id=f.user ORDER BY f.id DESC LIMIT 24""")
    return [{"user": {"id": r["owner"], "name": r["uname"], "photo": r["uphoto"]}, "gift": gift_out(r), "case": r["cs"]} for r in rows]


# ---------------- профиль ----------------
def friend_status(a, b):
    if a == b:
        return "me"
    r = q1("SELECT * FROM friends WHERE (a=? AND b=?) OR (a=? AND b=?)", a, b, b, a)
    if not r:
        return "none"
    if r["status"] == "ok":
        return "friend"
    return "outgoing" if r["a"] == a else "incoming"


@app.get(R + "/user/{tid}")
def profile(tid: int, uid=Depends(auth)):
    u = q1("SELECT * FROM users WHERE id=?", tid) or err("игрок не найден", 404)
    gifts = [gift_out(r) for r in q("SELECT * FROM gifts WHERE owner=? ORDER BY id DESC", tid)]
    pinned = [g for pid in json.loads(u["pinned"] or "[]") for g in gifts if g["id"] == pid]
    fr = q1("SELECT COUNT(*) n FROM friends WHERE (a=? OR b=?) AND status='ok'", tid, tid)["n"]
    worth = net_worth(tid)
    games = {r["kind"]: r["n"] for r in q(f"SELECT kind, COUNT(*) n FROM events WHERE user=? AND kind IN {GAME_KINDS} GROUP BY kind", tid)}
    won, lost = pnl([tid]).get(tid, (0, 0))
    best = q1(f"SELECT MAX(delta) m FROM events WHERE user=? AND kind IN {GAME_KINDS}", tid)["m"] or 0
    return {"ach": achievements(u, gifts, fr, worth), "cols": len({g["col"] for g in gifts}),
            "bannerImg": u["banner_img"] if "banner_img" in u.keys() else "",
            "nick": u["nick"] if "nick" in u.keys() else "", "tgName": u["name"] or "",
            "avatarImg": u["avatar"] if "avatar" in u.keys() else "", "tgPhoto": u["photo"] or "",
            "stats": {"games": games, "won": won, "lost": lost, "best": best, "rounds": sum(games.values())}, **user_brief(u), "lv": level_info(u["xp"]), "bio": u["bio"], "banner": u["banner"],
            "pinned": pinned, "gifts": gifts, "worth": worth, "opened": u["opened"],
            "badges": json.loads(u["p_badges"] or "[]") if "p_badges" in u.keys() else [], "cover": u["p_cover"] if "p_cover" in u.keys() else 0,
            "bestCrash": u["best_crash"], "friends": fr, "refs": u["refs"], "since": u["created"],
            "seen": u["seen"] or 0, "now": now(),   # последний онлайн (seen обновляется при входе, не чаще раза в минуту)
            "rel": friend_status(uid, tid)}


def achievements(u, gifts, friends, worth):
    best = min((g["mp"] for g in gifts), default=999)
    cols = len({g["col"] for g in gifts})
    lvl = level(u["xp"])
    A = [("🎁", "Первый кейс", "Открой первый кейс", u["opened"] >= 1),
         ("📦", "Кейсоман", "Открой 100 кейсов", u["opened"] >= 100),
         ("💎", "Легенда", "Подарок с моделью ≤ 0,5%", best <= 5),
         ("🚀", "Космонавт", "Забери x10 в краше", u["best_crash"] >= 10),
         ("🌕", "На Луну", "Забери x100 в краше", u["best_crash"] >= 100),
         ("💰", "Магнат", "Состояние 100 000 ⭐", worth >= 100000),
         ("🗂", "Коллекционер", "20 разных коллекций", cols >= 20),
         ("🤝", "Душа компании", "5 друзей", friends >= 5),
         ("📣", "Вербовщик", "Пригласи 3 друзей", u["refs"] >= 3),
         ("🎖", "Ветеран", "Достигни 10 уровня", lvl >= 10)]
    import eggs
    n = eggs.egg_count(u["id"])
    A.append(("🥚", "Охотник за пасхалками", f"Найди {eggs.EGG_NEED} секретов в игре · найдено {min(n, eggs.EGG_NEED)} из {eggs.EGG_NEED}", n >= eggs.EGG_NEED))
    return [{"e": e, "t": t, "d": d, "got": bool(g), "pct": ACH_PCT.get(t)} for e, t, d, g in A]


@app.get(R + "/collections")
def collections(uid=Depends(auth)):
    return {c: [len(d["models"]), E.base(c)] for c, d in E.CATALOG.items()}


@app.post(R + "/gifts/sell")
async def sell_many(req: Request, uid=Depends(auth)):
    ids = list(dict.fromkeys(int(x) for x in (await req.json()).get("ids", [])))[:200]   # повторы — один раз
    if not ids:
        err("ничего не выбрано")
    total = 0
    with tx():
        for gid in ids:
            g = own_gift(gid, uid)
            if g["price"] is not None:
                err("сначала сними выбранные подарки с маркета")
            total += int(g["value"] * sell_rate())
            db.execute("DELETE FROM gifts WHERE id=?", (gid,))
            unpin(uid, gid)
            cancel_trades_with(gid)
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (total, uid))
        stars = q1("SELECT stars FROM users WHERE id=?", uid)["stars"]
    return {"paid": total, "count": len(ids), "stars": stars}


# --- своя картинка на баннер профиля ---
import base64  # noqa: E402
import secrets  # noqa: E402

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(WEB_DIR, "u"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
for _c in ("banner_img TEXT DEFAULT ''", "nick TEXT DEFAULT ''", "avatar TEXT DEFAULT ''"):
    try:   # nick/avatar — свои имя и аватарка в игре поверх присланных Telegram (пусто — берём из Telegram)
        db.execute(f"ALTER TABLE users ADD COLUMN {_c}")
    except Exception:
        pass
BANNER_MAX = 700 * 1024
AVA_MAX = 400 * 1024


@app.post(R + "/profile/banner")
async def banner_upload(req: Request, uid=Depends(auth)):
    """Картинка приходит уже обрезанной и сжатой на клиенте (JPEG data URL). Пустая строка — убрать."""
    img = str((await req.json()).get("img", ""))
    old = q1("SELECT banner_img FROM users WHERE id=?", uid)["banner_img"] or ""
    name = ""
    if img:
        if not img.startswith("data:image/jpeg;base64,"):
            err("нужна картинка JPEG")
        try:
            raw = base64.b64decode(img.split(",", 1)[1], validate=True)
        except Exception:
            err("картинка повреждена")
        if len(raw) > BANNER_MAX or raw[:3] != b"\xff\xd8\xff":
            err("картинка слишком большая или не JPEG")
        name = f"u/{uid}_{secrets.token_hex(6)}.jpg"
        with open(os.path.join(UPLOAD_DIR, os.path.basename(name)), "wb") as f:
            f.write(raw)
    with tx():
        db.execute("UPDATE users SET banner_img=? WHERE id=?", (name, uid))
    if old:
        try:
            os.remove(os.path.join(UPLOAD_DIR, os.path.basename(old)))
        except OSError:
            pass
    return {"bannerImg": name}


@app.post(R + "/profile/avatar")
async def avatar_upload(req: Request, uid=Depends(auth)):
    """Своя аватарка: приходит обрезанной в квадрат и сжатой на клиенте (JPEG data URL). Пустая строка — вернуть аватар из Telegram."""
    img = str((await req.json()).get("img", ""))
    old = q1("SELECT avatar FROM users WHERE id=?", uid)["avatar"] or ""
    name = ""
    if img:
        if not img.startswith("data:image/jpeg;base64,"):
            err("нужна картинка JPEG")
        try:
            raw = base64.b64decode(img.split(",", 1)[1], validate=True)
        except Exception:
            err("картинка повреждена")
        if len(raw) > AVA_MAX or raw[:3] != b"\xff\xd8\xff":
            err("картинка слишком большая или не JPEG")
        name = f"u/a{uid}_{secrets.token_hex(6)}.jpg"
        with open(os.path.join(UPLOAD_DIR, os.path.basename(name)), "wb") as f:
            f.write(raw)
    with tx():
        db.execute("UPDATE users SET avatar=? WHERE id=?", (name, uid))
    if old:
        try:
            os.remove(os.path.join(UPLOAD_DIR, os.path.basename(old)))
        except OSError:
            pass
    return {"avatar": name}


@app.post(R + "/profile")
async def edit_profile(req: Request, uid=Depends(auth)):
    body = await req.json()
    bio = str(body.get("bio", ""))[:140]
    banner = str(body.get("banner", ""))
    if banner and banner not in BACKDROPS:
        err("нет такого баннера")
    pinned = [int(x) for x in body.get("pinned", [])][:6]
    set_nick = "nick" in body   # ник меняем, только если его прислали (пустая строка = сброс на имя из Telegram)
    nick = ""
    if set_nick:
        nick = " ".join(str(body["nick"]).split())[:24]   # схлопываем пробелы и переводы строк, режем до 24
        if nick and len(nick) < 2:
            err("Ник — минимум 2 символа")
    with tx():
        own = {r["id"] for r in q("SELECT id FROM gifts WHERE owner=?", uid)}
        pinned = [p for p in pinned if p in own]
        db.execute("UPDATE users SET bio=?, banner=?, pinned=? WHERE id=?", (bio, banner, json.dumps(pinned), uid))
        if set_nick:
            db.execute("UPDATE users SET nick=? WHERE id=?", (nick, uid))
    return {"ok": True}


@app.get(R + "/banners")
def banners(uid=Depends(auth)):
    return [{"name": b[0], "c": b[2:6]} for b in BACKDROPS.values()]


# ---------------- подарки / маркет ----------------
def own_gift(gid, uid):
    g = q1("SELECT * FROM gifts WHERE id=?", gid)
    if not g or g["owner"] != uid:
        err("это не твой подарок")
    return g


def in_open_trade(gid):
    for r in q("SELECT give, want FROM trades WHERE status='open'"):
        if gid in json.loads(r["give"]) or gid in json.loads(r["want"]):
            return True
    return False


def unpin(uid, gid):
    u = q1("SELECT pinned FROM users WHERE id=?", uid)
    p = [x for x in json.loads(u["pinned"] or "[]") if x != gid]
    db.execute("UPDATE users SET pinned=? WHERE id=?", (json.dumps(p), uid))


def cancel_trades_with(gid):
    for r in q("SELECT id, give, want FROM trades WHERE status='open'"):
        if gid in json.loads(r["give"]) or gid in json.loads(r["want"]):
            db.execute("UPDATE trades SET status='void' WHERE id=?", (r["id"],))


@app.post(R + "/gift/{gid}/sell")
def sell(gid: int, uid=Depends(auth)):
    with tx():
        g = own_gift(gid, uid)
        pay = int(g["value"] * sell_rate())
        db.execute("DELETE FROM gifts WHERE id=?", (gid,))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
        unpin(uid, gid)
        cancel_trades_with(gid)
        stars = q1("SELECT stars FROM users WHERE id=?", uid)["stars"]
    return {"paid": pay, "stars": stars}


@app.post(R + "/gift/{gid}/list")
async def list_gift(gid: int, req: Request, uid=Depends(auth)):
    price = int((await req.json()).get("price", 0))
    if not 10 <= price <= 100_000_000:
        err("цена от 10 ⭐")
    with tx():
        own_gift(gid, uid)
        if in_open_trade(gid):
            err("подарок участвует в обмене")
        db.execute("UPDATE gifts SET price=?, listed=? WHERE id=?", (price, now(), gid))
    return {"ok": True}


@app.post(R + "/gift/{gid}/unlist")
def unlist(gid: int, uid=Depends(auth)):
    with tx():
        own_gift(gid, uid)
        db.execute("UPDATE gifts SET price=NULL, listed=NULL WHERE id=?", (gid,))
    return {"ok": True}


@app.get(R + "/market")
def market(sort: str = "new", col: str = "", qs: str = "", mine: int = 0, rare: str = "", uid=Depends(auth)):
    order = {"new": "g.listed DESC", "cheap": "g.price ASC", "expensive": "g.price DESC",
             "deal": "CAST(g.price AS REAL)/g.value ASC"}.get(sort, "g.listed DESC")
    where, args = "g.price IS NOT NULL", []
    if col:
        where += " AND g.col=?"
        args.append(col)
    if qs.strip():
        where += " AND (g.col LIKE ? OR g.model LIKE ?)"
        args += [f"%{qs.strip()}%"] * 2
    if mine:
        where += " AND g.owner=?"
        args.append(uid)
    rows = q(f"""SELECT g.*, COALESCE(NULLIF(u.nick,''),u.name, 'Банк игры') uname, COALESCE(NULLIF(u.avatar,''),u.photo) uphoto FROM gifts g LEFT JOIN users u ON u.id=g.owner
                 WHERE {where} AND (u.id IS NOT NULL OR g.owner=0) ORDER BY {order} LIMIT 400""", *args)
    items = [{**gift_out(r, True), "seller": {"id": r["owner"], "name": r["uname"], "photo": r["uphoto"]}} for r in rows]
    lim = {"legend": 5, "epic": 10, "rare": 15}.get(rare)
    if lim:
        items = [x for x in items if x["mp"] <= lim]
    cols = [r["col"] for r in q("SELECT DISTINCT col FROM gifts WHERE price IS NOT NULL ORDER BY col")]
    st = q1("SELECT COUNT(*) n, MIN(price) floor FROM gifts WHERE price IS NOT NULL" + (" AND col=?" if col else ""), *([col] if col else []))
    vol = q1("SELECT COUNT(*) n, COALESCE(SUM(price),0) v FROM sales WHERE ts>?", now() - 86400)
    sales = [{**gift_out({**dict(r), "id": r["gift"], "price": r["price"]}), "ts": r["ts"]}
             for r in q("SELECT * FROM sales ORDER BY id DESC LIMIT 12")]
    return {"items": items[:150], "cols": cols, "count": st["n"], "floor": st["floor"], "vol24": vol["v"], "sales24": vol["n"], "sales": sales,
            "myCount": q1("SELECT COUNT(*) n FROM gifts WHERE owner=? AND price IS NOT NULL", uid)["n"]}


@app.post(R + "/market/{gid}/buy")
def buy(gid: int, uid=Depends(auth)):
    with tx():
        g = q1("SELECT * FROM gifts WHERE id=?", gid)
        if not g or g["price"] is None:
            err("уже продано")
        if g["owner"] == uid:
            err("это твой лот")
        import loans
        if g["owner"] != 0 and loans.stars_locked(uid):   # иначе твинк в кредит «покупает» подарок у своего основного аккаунта
            err("пока не закрыт кредит без залога, покупать у игроков нельзя (подарки банка — можно)")
        u = q1("SELECT stars FROM users WHERE id=?", uid)
        if u["stars"] < g["price"]:
            err("Не хватает звёзд")
        seller, price = g["owner"], g["price"]
        got = int(price * (1 - rich.market_fee(seller, MARKET_FEE)))
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (price, uid))
        if seller == 0:   # подарок банка (просроченный залог) — деньги возвращаются в банк
            event(0, "loan", -price)
        else:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got, seller))
            event(seller, "fee", -(price - got))
        db.execute("UPDATE gifts SET owner=?, price=NULL, listed=NULL WHERE id=?", (uid, gid))
        db.execute("INSERT INTO sales(gift,col,model,backdrop,symbol,num,value,price,seller,buyer,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (gid, g["col"], g["model"], g["backdrop"], g["symbol"], g["num"], g["value"], price, seller, uid, now()))
        unpin(seller, gid)
        cancel_trades_with(gid)
        stars = q1("SELECT stars FROM users WHERE id=?", uid)["stars"]
        buyer = q1("SELECT name FROM users WHERE id=?", uid)["name"]
    if seller:
        notify(seller, f"💰 <b>{esc(buyer)}</b> купил твой {esc(g['col'])} #{g['num']} — тебе +{got} ⭐")
    return {"ok": True, "stars": stars}


# ---------------- краш ----------------
@app.get(R + "/crash")
def crash_state(uid=Depends(auth)):
    t = time.time()
    bets = []
    for bid, b in CR["bets"].items():
        bets.append({"id": bid, "name": b["name"], "photo": b["photo"], "amount": b["amount"], "cashed": b["cashed"]})
    bets.sort(key=lambda b: -b["amount"])
    my = CR["bets"].get(uid)
    return {"round": CR["round"], "phase": CR["phase"], "now": t, "until": CR["until"], "start": CR["start"], "k": CRASH_K,
            "crash": CR["crash"] if CR["phase"] == "end" else None, "history": list(CR["history"]),
            "hash": CR["seed_hash"] if CR["phase"] in ("bet", "run") else None,
            "seed": CR["seed"] if CR["phase"] == "end" else None,
            "chain": {"id": CR["chain"], "pos": CR["pos"]},
            "bets": bets, "my": my and {"amount": my["amount"], "auto": my["auto"], "cashed": my["cashed"]},
            "stars": q1("SELECT stars FROM users WHERE id=?", uid)["stars"]}


@app.post(R + "/crash/bet")
async def crash_bet(req: Request, uid=Depends(auth)):
    body = await req.json()
    amount = int(body.get("amount", 0))
    auto = body.get("auto")
    auto = round(float(auto), 2) if auto else None
    if auto is not None and not 1.01 <= auto <= 10000:   # «not …» — чтобы NaN/Infinity из JSON тоже отсекались
        err("автовывод от 1.01x до 10000x")
    check_bet(uid, amount)   # потолок в кризис банка, после просрочки кредита, лимиты игрока
    if CR["phase"] != "bet" or time.time() > CR["until"] - 0.2:
        err("приём ставок закрыт, жди раунд")
    with tx():   # проверка и запись ставки атомарно — двойной тап не спишет дважды
        if uid in CR["bets"]:
            err("ставка уже сделана")
        u = q1("SELECT * FROM users WHERE id=?", uid)
        if u["stars"] < amount:
            err("Не хватает звёзд")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        lvl = add_xp(uid, max(1, amount // 20))
        CR["bets"][uid] = {"amount": amount, "auto": auto, "cashed": None, "round": CR["round"],
                           "name": (u["nick"] if "nick" in u.keys() and u["nick"] else u["name"]),
                           "photo": (u["avatar"] if "avatar" in u.keys() and u["avatar"] else u["photo"])}
    return {"ok": True, "levelup": lvl}


@app.post(R + "/crash/cashout")
async def crash_cashout(req: Request, uid=Depends(auth)):
    """Кэшаут по множителю, который игрок видел при нажатии (m): платим min(показанный, текущий).
    Выигрыш, только если этот множитель меньше точки взрыва. Запрос, доехавший в окне CASHOUT_GRACE, засчитывается так же:
    в это окно игрок ещё не может знать о взрыве, а поздний запрос с множителем выше взрыва всё равно проигрывает."""
    b = CR["bets"].get(uid)
    if not b or b["cashed"] is not None:
        err("нечего забирать")
    try:
        claimed = float((await req.json()).get("m") or 0)
    except Exception:
        claimed = 0
    if CR["phase"] != "run":
        err("не успел 💥")
    cur = crash_mult(time.time() - CR["start"])
    m = min(claimed, cur) if claimed >= 1.01 else cur
    if m >= CR["crash"]:
        err("не успел 💥")
    pay = _cashout(uid, b, m)
    if not pay:
        err("уже выведено")
    return {"mult": round(m, 2), "pay": pay}


# ---------------- мини-игры: апгрейд, мины, колесо ----------------
db.executescript("""
CREATE TABLE IF NOT EXISTS mines(user INTEGER PRIMARY KEY, bet INTEGER, n INTEGER, bombs TEXT, opened TEXT, ts INTEGER);
""")

UPG_EDGE = conf("games.upgrade_edge", 0.92)    # шанс = ценность / цель × 0.92 (в акцию 0.93); было 0.88 — подняли 11.10.2026
UPG_MAX = conf("games.upgrade_max", 0.8)


def bal(uid):
    return q1("SELECT stars FROM users WHERE id=?", uid)["stars"]


MAX_BET = conf("games.max_bet", 1_000_000)


BET_CAP = None   # bank.py: в кризис банка — потолок ставки
LOAN_BET_CAP = None   # loans.py: после просрочки кредита — потолок ставки
VAULT_PUT = None  # bank.py: проигранные в апгрейде подарки → хранилище банка


def check_bet(uid, amount, lo=10, hi=None):
    hi = hi or MAX_BET
    if SELF_GUARD:
        SELF_GUARD(uid, amount)
    cap = BET_CAP() if BET_CAP else None
    if cap and amount > cap:
        err(f"Банк в кризисе — ставка не больше {cap:,} ⭐".replace(",", " "))
    lc = LOAN_BET_CAP(uid) if LOAN_BET_CAP else None
    if lc and amount > lc:
        err(f"После просрочки кредита ставка не больше {lc:,} ⭐".replace(",", " "))
    if not lo <= amount <= hi:
        err(f"ставка от {lo} до {hi:,} ⭐".replace(",", " "))
    if bal(uid) < amount:
        err("Не хватает звёзд")


UPG_TARGETS = None  # все пары (коллекция, модель) с ценностью — для выбора цели апгрейда


def upg_all():
    global UPG_TARGETS
    if UPG_TARGETS is None:
        out = []
        for col, d in E.CATALOG.items():
            mm, mb, ms = E._MED[col]
            for m in d["models"]:
                out.append((col, m[0], m[1], max(1, round(E.base(col) * E.mult(col, m[1], mb, ms)))))
        out.sort(key=lambda x: x[3])
        UPG_TARGETS = out
    return UPG_TARGETS


def upg_card(col, model, pm, value):
    lk = look_of(col, model)
    return {"col": col, "model": model, "mp": pm, "value": value, "c": lk["c"], "symbol": lk["symbol"], "num": 0}


def _gids(raw):
    ids = [int(x) for x in str(raw).replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()]
    return list(dict.fromkeys(ids))[:10]


@app.get(R + "/upgrade/targets")
def upgrade_targets(gid: str = "", col: str = "", qs: str = "", kmin: float = 1.2, kmax: float = 1000, uid=Depends(auth)):
    ids = _gids(gid) or err("выбери подарок")
    v = sum(own_gift(i, uid)["value"] for i in ids)
    qs = qs.strip().lower()
    res = [t for t in upg_all() if kmin * v <= t[3] <= kmax * v and (not col or t[0] == col)
           and (not qs or qs in t[0].lower() or qs in t[1].lower())]
    cols = sorted({t[0] for t in upg_all() if t[3] >= 0.2 * v})
    items = [{**upg_card(*t), "chance": round(min(UPG_MAX, v / t[3] * edge(tuned("games.upgrade_edge", UPG_EDGE), 0.93)) * 100, 2)} for t in res[:300]]
    # edge — чтобы клиент показывал РЕАЛЬНЫЙ шанс (а не свой расчёт: админка/акция меняют возврат на лету)
    return {"items": items, "total": len(res), "cols": cols, "stake": v,
            "edge": round(edge(tuned("games.upgrade_edge", UPG_EDGE), 0.93) * 100, 2)}


UPG_MAX_TARGETS = 10   # целей в одном апгрейде: можно одну и ту же несколько раз (2 Пепе за 1 Пепе)


@app.post(R + "/upgrade")
async def upgrade(req: Request, uid=Depends(auth)):
    """Апгрейд: пачка подарков (до 10) → одна или несколько целей (до 5). Шанс от суммарных ценностей."""
    if SELF_GUARD:
        SELF_GUARD(uid, 0)
    b = await req.json()
    gids = [int(x) for x in (b.get("gids") or [b.get("gid", 0)])][:10]
    tgs = b.get("targets") or [{"col": b.get("col", ""), "model": b.get("model", "")}]
    targets = []
    for t in tgs[:UPG_MAX_TARGETS]:
        x = next((y for y in upg_all() if y[0] == str(t.get("col")) and y[1] == str(t.get("model"))), None)
        if not x:
            err("нет такой цели")
        targets.append(x)
    gids = list(dict.fromkeys(gids))
    if not gids or not targets:
        err("выбери подарки и цель")
    with tx():
        gifts = [own_gift(g, uid) for g in gids]
        if any(g["price"] is not None for g in gifts):
            err("сначала сними подарки с маркета")
        sv, tv = sum(g["value"] for g in gifts), sum(t[3] for t in targets)
        if tv < 1.2 * sv:
            err("цель должна быть дороже ставки хотя бы в 1.2 раза")
        chance = min(UPG_MAX, sv / tv * edge(tuned("games.upgrade_edge", UPG_EDGE), 0.93))
        rr, pf = fair.rolls(uid, "upgrade", ref=",".join(map(str, gids)), n=4)   # честный бросок: выигрыш + вид выигрышного подарка
        win = rr[0] < chance
        if not win and VAULT_PUT:   # проигранные подарки — в хранилище банка (bank.py), через 48 ч перерабатываются
            VAULT_PUT(uid, gifts)
        for g in gids:
            db.execute("DELETE FROM gifts WHERE id=?", (g,))
            unpin(uid, g)
            cancel_trades_with(g)
        new = []
        if win:
            for col, model, pm, value in targets:
                d = E.CATALOG[col]
                old = VAULT_TAKE(col, model, value) if VAULT_TAKE else None   # есть такой подарок в хранилище банка — выдаём его, а не печатаем новый
                bd = old["backdrop"] if old else d["backdrops"][fair.pick(rr[1], [x[1] for x in d["backdrops"]])][0]
                sy = old["symbol"] if old else d["symbols"][fair.pick(rr[2], [max(x[1], .1) for x in d["symbols"]])][0]
                num = old["num"] if old else 1 + fair.idx(rr[3], E.supply(col))
                cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                                 (uid, col, model, bd, sy, num, value, now()))
                if old:
                    db.execute("INSERT OR REPLACE INTO gift_link(gift,prev) VALUES(?,?)", (cur.lastrowid, old["id"]))
                new.append(gift_out(q1("SELECT * FROM gifts WHERE id=?", cur.lastrowid)))
            best = max(new, key=lambda g: g["value"])
            db.execute("INSERT INTO feed(user,gift,cs,ts) VALUES(?,?,?,?)", (uid, best["id"], "upgrade", now()))
        event(uid, "upgrade", (tv if win else 0) - sv, stake=sv, pf=pf, res={"p": round(chance, 6), "win": win})
        lvl = add_xp(uid, max(5, sv // 20))
    return {"win": win, "chance": round(chance * 100, 2), "gifts": new, "gift": new[0] if new else None, "levelup": lvl, "pf": pf}


# --- мины 5×5 ---
MINES_EDGE = conf("games.mines_edge", 0.96)


def mines_mult(n, k):
    m = edge(tuned("games.mines_edge", MINES_EDGE))
    for i in range(k):
        m *= (25 - i) / (25 - n - i)
    return m if k else 1.0


def mines_state(r, reveal=False):
    opened = json.loads(r["opened"])
    k = len(opened)
    mult = mines_mult(r["n"], k)
    nxt = mines_mult(r["n"], k + 1) if k < 25 - r["n"] else mult  # все безопасные открыты — следующего хода нет
    st = {"active": True, "bet": r["bet"], "n": r["n"], "opened": opened,
          "mult": round(mult, 2), "next": round(nxt, 2)}
    if reveal:
        st["bombs"] = json.loads(r["bombs"])
    return st


@app.get(R + "/mines")
def mines_get(uid=Depends(auth)):
    r = q1("SELECT * FROM mines WHERE user=?", uid)
    return mines_state(r) if r else {"active": False}


@app.post(R + "/mines/start")
async def mines_start(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, n = int(b.get("bet", 0)), int(b.get("n", 3))
    if not 1 <= n <= 24:
        err("мин от 1 до 24")
    with tx():
        if q1("SELECT 1 FROM mines WHERE user=?", uid):
            err("игра уже идёт")
        check_bet(uid, bet)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        rr, pf = fair.rolls(uid, "mines", ref=str(n), n=n)
        bombs = fair.sample(rr, range(25), n)
        db.execute("INSERT INTO mines VALUES(?,?,?,?,?,?)", (uid, bet, n, json.dumps(bombs), "[]", now()))
        lvl = add_xp(uid, max(1, bet // 20))
        r = q1("SELECT * FROM mines WHERE user=?", uid)
    return {**mines_state(r), "stars": bal(uid), "levelup": lvl, "pf": pf}


@app.post(R + "/mines/reveal")
async def mines_reveal(req: Request, uid=Depends(auth)):
    cell = int((await req.json()).get("cell", -1))
    if not 0 <= cell < 25:
        err("Действие устарело — обнови экран")
    with tx():
        r = q1("SELECT * FROM mines WHERE user=?", uid) or err("игра не начата")
        opened, bombs = json.loads(r["opened"]), json.loads(r["bombs"])
        if cell in opened:
            return mines_state(r)
        if cell in bombs:
            db.execute("DELETE FROM mines WHERE user=?", (uid,))
            event(uid, "mines", -r["bet"], stake=r["bet"], res={"n": r["n"], "bombs": bombs, "open": opened})
            return {**mines_state(r, True), "active": False, "boom": cell}
        opened.append(cell)
        db.execute("UPDATE mines SET opened=? WHERE user=?", (json.dumps(opened), uid))
        r = q1("SELECT * FROM mines WHERE user=?", uid)
        if len(opened) == 25 - r["n"]:  # открыл всё — автоматически забираем
            return _mines_cash(uid, r)
        return mines_state(r)


def _mines_cash(uid, r):
    m = mines_mult(r["n"], len(json.loads(r["opened"])))
    pay = int(r["bet"] * m)
    db.execute("DELETE FROM mines WHERE user=?", (uid,))
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
    event(uid, "mines", pay - r["bet"], stake=r["bet"], res={"n": r["n"], "bombs": json.loads(r["bombs"]), "open": json.loads(r["opened"])})
    return {**mines_state(r, True), "active": False, "pay": pay, "stars": bal(uid)}


@app.post(R + "/mines/cashout")
def mines_cashout(uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM mines WHERE user=?", uid) or err("игра не начата")
        if not json.loads(r["opened"]):
            err("открой хотя бы одну клетку")
        return _mines_cash(uid, r)


# --- колесо фортуны: 20 секторов, RTP ≈ 93.5% ---
WHEEL = [0, 1.5, 0, 2, 0, 1.2, 0, 3, 0, 1.5, 0, 0.5, 0, 5, 0, 1.5, 0, 2, 0, 0.5]


WHEEL_RTP = 0.935


def wheel_segs():
    """Секторы с учётом возврата из админки: множители масштабируются пропорционально."""
    k = tuned("games.wheel_rtp", WHEEL_RTP) / WHEEL_RTP
    return WHEEL if k == 1 else [round(x * k, 2) for x in WHEEL]


@app.get(R + "/wheel")
def wheel_info(uid=Depends(auth)):
    return {"segments": wheel_segs()}


@app.post(R + "/wheel")
async def wheel_spin(req: Request, uid=Depends(auth)):
    bet = int((await req.json()).get("bet", 0))
    with tx():
        check_bet(uid, bet)
        segs = wheel_segs()
        rr, pf = fair.rolls(uid, "wheel", n=1)
        idx = fair.idx(rr[0], len(segs))
        pay = int(bet * segs[idx])
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
        event(uid, "wheel", pay - bet, stake=bet, pf=pf, res={"idx": idx, "segs": len(segs), "mult": segs[idx]})
        lvl = add_xp(uid, max(1, bet // 20))
    return {"idx": idx, "mult": segs[idx], "pay": pay, "stars": bal(uid), "levelup": lvl, "pf": pf}


# --- обменник: подарок → другой подарок той же ценности (комиссия до 15%) ---
SWAP = {}


@app.get(R + "/swap/options")
def swap_options(gid: int, uid=Depends(auth)):
    g = own_gift(gid, uid)
    if g["price"] is not None:
        err("сначала сними подарок с маркета")
    v = g["value"]
    found, seen = [], {(g["col"], g["model"])}
    cols = list(E.CATALOG)
    for _ in range(1500):
        if len(found) >= 12:
            break
        d = E.roll(random.choice(cols))
        if not 0.85 * v <= d["value"] <= v or (d["col"], d["model"]) in seen:
            continue
        seen.add((d["col"], d["model"]))
        found.append(d)
    found.sort(key=lambda d: -d["value"])
    SWAP[uid] = {"gid": gid, "targets": found, "ts": time.time()}
    return [preview_out(d["col"], d) for d in found]


@app.post(R + "/swap")
async def swap(req: Request, uid=Depends(auth)):
    b = await req.json()
    st = SWAP.get(uid)
    gid, idx = int(b.get("gid", 0)), int(b.get("idx", -1))
    if not st or st["gid"] != gid or time.time() - st["ts"] > 900 or not 0 <= idx < len(st["targets"]):
        err("обнови варианты обмена")
    t = st["targets"][idx]
    with tx():
        g = own_gift(gid, uid)
        if g["price"] is not None:
            err("сначала сними подарок с маркета")
        db.execute("DELETE FROM gifts WHERE id=?", (gid,))
        unpin(uid, gid)
        cancel_trades_with(gid)
        cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                         (uid, t["col"], t["model"], t["backdrop"], t["symbol"], t["num"], t["value"], now()))
        new = gift_out(q1("SELECT * FROM gifts WHERE id=?", cur.lastrowid))
    SWAP.pop(uid, None)
    return {"gift": new}


# --- дуэли 1 на 1: монетка / кости, банк забирает победитель (комиссия 5%) ---
db.executescript("""
CREATE TABLE IF NOT EXISTS duels(id INTEGER PRIMARY KEY AUTOINCREMENT, a INTEGER, b INTEGER, game TEXT, stake INTEGER,
  status TEXT, winner INTEGER, ra TEXT, rb TEXT, ts INTEGER, done INTEGER);
CREATE INDEX IF NOT EXISTS duels_status ON duels(status);
""")
DUEL_FEE = conf("economy.duel_fee", 0.05)
DUEL_TTL = 24 * 3600


def duel_expire():
    """Просроченные вызовы — вернуть ставку создателю."""
    for d in q("SELECT * FROM duels WHERE status='open' AND ts<?", now() - DUEL_TTL):
        with tx():
            if q1("SELECT status FROM duels WHERE id=?", d["id"])["status"] == "open":
                db.execute("UPDATE duels SET status='expired' WHERE id=?", (d["id"],))
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (d["stake"], d["a"]))


def duel_out(d):
    a = q1("SELECT * FROM users WHERE id=?", d["a"])
    b = q1("SELECT * FROM users WHERE id=?", d["b"]) if d["b"] else None
    return {"id": d["id"], "game": d["game"], "stake": d["stake"], "status": d["status"], "winner": d["winner"],
            "ra": json.loads(d["ra"]) if d["ra"] else None, "rb": json.loads(d["rb"]) if d["rb"] else None,
            "a": user_brief(a), "b": user_brief(b) if b else None, "ts": d["ts"], "pay": int(d["stake"] * 2 * (1 - DUEL_FEE))}


@app.get(R + "/duels")
def duels(uid=Depends(auth)):
    duel_expire()
    import games4
    games4.cd_tick_all()
    return {
        "live": [games4.cd_view(d, uid) for d in q("SELECT * FROM duels WHERE status='live' AND (a=? OR b=?) ORDER BY id DESC", uid, uid)],
        "incoming": [duel_out(d) for d in q("SELECT * FROM duels WHERE status='open' AND b=? ORDER BY id DESC", uid)],
        "lobby": [duel_out(d) for d in q("SELECT * FROM duels WHERE status='open' AND b IS NULL AND a!=? ORDER BY stake DESC LIMIT 30", uid)],
        "mine": [duel_out(d) for d in q("SELECT * FROM duels WHERE status='open' AND a=? ORDER BY id DESC", uid)],
        "history": [duel_out(d) for d in q("SELECT * FROM duels WHERE status='done' AND (a=? OR b=?) ORDER BY done DESC LIMIT 15", uid, uid)],
    }


def _pvp_guard(uid):
    """Должникам (кредит без залога / минус) — без PvP: иначе твинк берёт 5000 в кредит и «сливает» их основному аккаунту."""
    import loans
    if loans.stars_locked(uid):
        err("пока не закрыт кредит без залога или баланс в минусе, играть против других игроков нельзя")
    if SELF_GUARD:   # перерыв или исчерпанный дневной лимит (limits.py)
        SELF_GUARD(uid, 0)


@app.post(R + "/duels")
async def duel_new(req: Request, uid=Depends(auth)):
    _pvp_guard(uid)
    b = await req.json()
    game, stake, to = str(b.get("game", "coin")), int(b.get("stake", 0)), b.get("to")
    if game not in ("coin", "dice", "crash"):
        err("нет такой игры")
    if to is not None:
        to = int(to)
        if to == uid or not q1("SELECT 1 FROM users WHERE id=?", to):
            err("кого вызываем?")
    with tx():
        if q1("SELECT COUNT(*) n FROM duels WHERE status='open' AND a=?", uid)["n"] >= 10:
            err("не больше 10 открытых вызовов")
        check_bet(uid, stake, 10, 1_000_000)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (stake, uid))
        cur = db.execute("INSERT INTO duels(a,b,game,stake,status,ts) VALUES(?,?,?,?,?,?)", (uid, to, game, stake, "open", now()))
        name = q1("SELECT name FROM users WHERE id=?", uid)["name"]
    if to:
        notify(to, f"⚔️ <b>{esc(name)}</b> вызывает тебя на дуэль ({ {'coin': 'монетка', 'dice': 'кости', 'crash': 'краш'}[game] }) на {stake} ⭐")
    return {"id": cur.lastrowid, "stars": bal(uid)}


@app.post(R + "/duels/{did}/{action}")
def duel_action(did: int, action: str, uid=Depends(auth)):
    if action == "accept":
        _pvp_guard(uid)
    with tx():
        d = q1("SELECT * FROM duels WHERE id=?", did)
        if not d or d["status"] != "open":
            err("вызов уже неактуален")
        if action in ("cancel", "decline"):
            if not (action == "cancel" and d["a"] == uid or action == "decline" and d["b"] == uid):
                err("не твой вызов")
            db.execute("UPDATE duels SET status=? WHERE id=?", ("cancelled" if action == "cancel" else "declined", did))
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (d["stake"], d["a"]))
            res = {"ok": True}
            msg = None if action == "cancel" else (d["a"], "Твой вызов на дуэль отклонили — ставка вернулась")
        elif action == "accept":
            if d["a"] == uid or (d["b"] and d["b"] != uid):
                err("этот вызов не для тебя")
            check_bet(uid, d["stake"], 1, 10**9)
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (d["stake"], uid))
            if d["game"] == "crash":
                # краш-дуэль идёт вживую: точка взрыва известна только серверу, старт — когда оба нажмут «Готов»
                rng = fair.pub("duel", f"crash:{did}")
                cp = min(100.0, max(1.01, 1 / (1 - rng.random())))
                fair.close_pub(rng, {"cp": round(cp, 4)})
                db.execute("UPDATE duels SET b=?, status='live', cp=?, ts=?, ready='{}' WHERE id=?", (uid, cp, now(), did))
                nm = q1("SELECT name FROM users WHERE id=?", uid)["name"]
                res = {"live": did, "stars": bal(uid)}
                msg = (d["a"], f"🚀 <b>{esc(nm)}</b> принял краш-дуэль на {d['stake']} ⭐ — заходи и жми «Готов»!", APP_URL + f"?cduel={did}")
            elif d["game"] == "coin":
                rng = fair.pub("duel", f"coin:{did}")
                side = rng.randint(0, 1)             # 0 — создатель, 1 — принявший
                fair.close_pub(rng, {"side": side})
                ra, rb, win = [side], [side], (d["a"] if side == 0 else uid)
            else:
                rng = fair.pub("duel", f"dice:{did}")
                while True:
                    ra, rb = [rng.randint(1, 6), rng.randint(1, 6)], [rng.randint(1, 6), rng.randint(1, 6)]
                    if sum(ra) != sum(rb):
                        break
                fair.close_pub(rng, {"a": ra, "b": rb})
                win = d["a"] if sum(ra) > sum(rb) else uid
            if d["game"] != "crash":
                pay = int(d["stake"] * 2 * (1 - DUEL_FEE))
                lose = uid if win == d["a"] else d["a"]
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, win))
                db.execute("UPDATE duels SET b=?, status='done', winner=?, ra=?, rb=?, done=? WHERE id=?",
                           (uid, win, json.dumps(ra), json.dumps(rb), now(), did))
                event(win, "duel", pay - d["stake"], stake=d["stake"])
                event(lose, "duel", -d["stake"], stake=d["stake"])
                res = duel_out(q1("SELECT * FROM duels WHERE id=?", did))
                res["stars"] = bal(uid)
                nm = q1("SELECT name FROM users WHERE id=?", uid)["name"]
                msg = (d["a"], f"⚔️ <b>{esc(nm)}</b> принял дуэль на {d['stake']} ⭐ — " + ("ты победил! +" + str(pay) + " ⭐" if win == d["a"] else "ты проиграл"))
        else:
            err("Действие устарело — обнови экран")
    if msg:
        notify(*msg)
    return res


# --- ежедневные задания ---
db.executescript("CREATE TABLE IF NOT EXISTS quest_claims(user INTEGER, qid TEXT, day INTEGER, PRIMARY KEY(user,qid,day));")
# Пул заданий: каждый день сервер берёт из него набор (одинаковый для всех — есть что обсудить в чате):
# 2 лёгких, 2 средних, 1 сложное и 1 «новинка» из свежих игр + сундук за выполнение всех.
# Задания в закрытые/скрытые/админские игры не попадают (gates). Режимы: n — сыграй N раз,
# w — выиграй N раз (итог раунда в плюс), x — один выигрыш не меньше arg ⭐, g — сыграй в N разных игр.
# (id, иконка, текст, игра в gates или None, виды событий, режим, сколько, arg, награда, уровень)
_ALLG = ("crash", "mines", "wheel", "duel", "dice", "limbo", "plinko", "tower", "slots", "blackjack", "dogs", "roulette", "hilo",
         "chicken", "starfall", "avia", "battle", "scratch", "claw", "pump", "drill", "darts", "fish", "jroul", "upgrade", "keno", "penalty")
QPOOL = [
    ("cases", "box", "Открой 3 кейса", None, ("case",), "n", 3, 0, 250, 1),
    ("crash", "rocket", "Сыграй 5 раундов в краш", "crash", ("crash",), "n", 5, 0, 250, 1),
    ("mines", "bomb", "Сыграй 3 раза в мины", "mines", ("mines",), "n", 3, 0, 200, 1),
    ("wheel", "refresh", "Крутани колесо 3 раза", "wheel", ("wheel",), "n", 3, 0, 200, 1),
    ("upgrade", "trend", "Сделай апгрейд", "upgrade", ("upgrade",), "n", 1, 0, 250, 1),
    ("dice", "target", "Брось кубик 10 раз", "dice", ("dice",), "n", 10, 0, 200, 1),
    ("slots", "grid", "Крутани слоты 10 раз", "slots", ("slots",), "n", 10, 0, 200, 1),
    ("scratch", "sparkles", "Сотри 3 скретч-карты", "scratch", ("scratch",), "n", 3, 0, 250, 1),
    ("tower", "layers", "Залезь на башню 3 раза", "tower", ("tower",), "n", 3, 0, 200, 1),
    ("chicken", "flame", "Проведи курицу 3 раза", "chicken", ("chicken",), "n", 3, 0, 200, 1),
    ("claw", "gift", "Сыграй в «Кран» 3 раза", "claw", ("claw",), "n", 3, 0, 250, 1),
    ("hilo", "chev", "Угадай карту в «Больше/меньше» 3 раза", "hilo", ("hilo",), "n", 3, 0, 200, 1),
    ("games3", "games", "Сыграй в 3 разные игры", None, _ALLG, "g", 3, 0, 300, 1),
    ("cases10", "gift", "Открой 10 кейсов", None, ("case",), "n", 10, 0, 700, 2),
    ("crashw", "rocket", "Выиграй 3 раунда в краш", "crash", ("crash",), "w", 3, 0, 500, 2),
    ("minesw", "bomb", "Забери выигрыш в минах 3 раза", "mines", ("mines",), "w", 3, 0, 500, 2),
    ("dogs", "activity", "Крутани «Пёсиков» 10 раз", "dogs", ("dogs",), "n", 10, 0, 450, 2),
    ("bj", "award", "Сыграй 5 раздач в блэкджек", "blackjack", ("blackjack",), "n", 5, 0, 450, 2),
    ("towerw", "layers", "Забери выигрыш в башне 3 раза", "tower", ("tower",), "w", 3, 0, 500, 2),
    ("chickenw", "flame", "Выиграй с курицей 3 раза", "chicken", ("chicken",), "w", 3, 0, 500, 2),
    ("upg3", "trend", "Сделай 3 апгрейда", "upgrade", ("upgrade",), "n", 3, 0, 600, 2),
    ("duel", "target", "Сыграй дуэль", "duels", ("duel",), "n", 1, 0, 500, 2),
    ("avia", "send", "Запусти самолётик 3 раза", "avia", ("avia",), "n", 3, 0, 450, 2),
    ("rlt", "refresh", "Сыграй 3 раунда рулетки", "rlt", ("roulette",), "n", 3, 0, 450, 2),
    ("games5", "games", "Сыграй в 5 разных игр", None, _ALLG, "g", 5, 0, 600, 2),
    ("win1k", "coins", "Выиграй разом от ⭐ 1 000", None, _ALLG, "x", 1, 1000, 600, 2),
    ("cases25", "box", "Открой 25 кейсов", None, ("case",), "n", 25, 0, 1500, 3),
    ("casew", "crown", "Окупи 3 кейса", None, ("case",), "w", 3, 0, 1200, 3),
    ("upgw", "trend", "Сделай удачный апгрейд", "upgrade", ("upgrade",), "w", 1, 0, 1200, 3),
    ("crash15", "rocket", "Сыграй 15 раундов в краш", "crash", ("crash",), "n", 15, 0, 1000, 3),
    ("games8", "games", "Сыграй в 8 разных игр", None, _ALLG, "g", 8, 0, 1300, 3),
    ("win10k", "crown", "Выиграй разом от ⭐ 10 000", None, _ALLG, "x", 1, 10000, 1500, 3),
    ("battle", "users", "Сыграй в «Битву кейсов»", "battle", ("battle",), "n", 1, 0, 1000, 3),
    ("slotsw", "grid", "Выиграй в слотах 5 раз", "slots", ("slots",), "w", 5, 0, 1000, 3),
]
QNEW = [   # «новинка дня» — из свежих игр
    ("n_pump", "wind", "Надуй шар в «Насосе» 5 раз", "pump", ("pump",), "n", 5, 0, 500, 0),
    ("n_pumpw", "wind", "Забери выигрыш в «Насосе» 3 раза", "pump", ("pump",), "w", 3, 0, 600, 0),
    ("n_drill", "drill", "Пробури землю в «Буре» 5 раз", "drill", ("drill",), "n", 5, 0, 500, 0),
    ("n_drillw", "drill", "Выиграй в «Буре» 2 раза", "drill", ("drill",), "w", 2, 0, 600, 0),
    ("n_darts", "crosshair", "Брось 10 дротиков в «Дартсе»", "darts", ("darts",), "n", 10, 0, 500, 0),
    ("n_dartsw", "crosshair", "Выиграй в «Дартсе» 3 раза", "darts", ("darts",), "w", 3, 0, 600, 0),
    ("n_fish", "fish", "Закинь удочку 5 раз", "fish", ("fish",), "n", 5, 0, 500, 0),
    ("n_fishw", "fish", "Вытащи 3 рыбы на «Рыбалке»", "fish", ("fish",), "w", 3, 0, 600, 0),
    ("n_plinko", "target", "Брось 20 шариков в «Плинко»", "plinko", ("plinko",), "n", 20, 0, 500, 0),
    ("n_plinkow", "target", "Поймай 5 выигрышей в «Плинко»", "plinko", ("plinko",), "w", 5, 0, 600, 0),
    ("n_keno", "grid", "Сыграй 10 тиражей в «Кено»", "keno", ("keno",), "n", 10, 0, 500, 0),
    ("n_kenow", "grid", "Выиграй в «Кено» 3 раза", "keno", ("keno",), "w", 3, 0, 600, 0),
    ("n_pen", "target", "Пробей 5 серий пенальти", "penalty", ("penalty",), "n", 5, 0, 500, 0),
    ("n_penw", "trophy", "Забери выигрыш в «Пенальти» 3 раза", "penalty", ("penalty",), "w", 3, 0, 600, 0),
]
QCHEST = 1000   # сундук: забрал все задания дня
QWEEK = 7000    # сундук 7 дней подряд


def day_start():
    """Полночь UTC. Время берём один раз: раньше два разных вызова давали сдвиг на секунду → двойные дивиденды/задания."""
    t = int(time.time())
    return t - t % 86400


def _qopen(gate):
    if not gate:
        return True
    try:
        from gates import states
        return states().get(gate, "on") == "on"
    except Exception:
        return True


def quests_today():
    """Набор дня: детерминирован по дате (сид — номер дня), один и тот же для всех игроков."""
    rnd = random.Random(day_start() // 86400 * 7919 + 17)
    out = []
    for tier, k in ((1, 2), (2, 2), (3, 1)):
        pool = [x for x in QPOOL if x[9] == tier and _qopen(x[3])]
        rnd.shuffle(pool)
        seen = set()
        for x in pool:   # не два задания на одну игру в одном уровне
            if len([y for y in out if y[9] == tier]) >= k:
                break
            if x[3] in seen and x[3]:
                continue
            seen.add(x[3]); out.append(x)
    nw = [x for x in QNEW if _qopen(x[3])]
    if nw:
        out.append(nw[rnd.randrange(len(nw))])
    return out


def quests_state(uid):
    d0 = day_start()
    st = {r["kind"]: r for r in q("SELECT kind, COUNT(*) n, SUM(delta>0) w, MAX(delta) mx FROM events WHERE user=? AND ts>=? GROUP BY kind", uid, d0)}
    got = {r["qid"] for r in q("SELECT qid FROM quest_claims WHERE user=? AND day=?", uid, d0)}
    items = []
    for i, ic, t, _, kinds, mode, n, arg, rw, tier in quests_today():
        rs = [st[k] for k in kinds if k in st]
        have = (len(rs) if mode == "g" else sum(r["n"] for r in rs) if mode == "n" else sum(r["w"] or 0 for r in rs) if mode == "w"
                else int(any((r["mx"] or 0) >= arg for r in rs)))
        items.append({"id": i, "icon": ic, "t": t, "need": n, "have": min(n, have), "reward": prize_k(rw), "claimed": i in got,
                      "tier": "new" if not tier else tier})
    e = event_active()
    for i, ic, t, k, n, rw in (e["quests"] if e else []):
        items.append({"id": i, "icon": ic, "t": t, "need": n, "have": min(n, st[k]["n"] if k in st else 0), "reward": rw,
                      "claimed": i in got, "tier": "event"})
    done = sum(1 for x in items if x["claimed"])
    items.append({"id": "chest", "icon": "trophy", "t": "Сундук: выполни все задания", "need": len(items),
                  "have": done, "reward": prize_k(QCHEST), "claimed": "chest" in got, "tier": "chest"})
    st7 = chest_streak(uid)
    items.append({"id": "week", "icon": "crown", "t": "Неделя без пропусков: сундук 7 дней подряд", "need": 7,
                  "have": min(7, st7), "reward": prize_k(QWEEK), "claimed": "week" in got, "tier": "week"})
    return items


def chest_streak(uid):
    """Сколько дней подряд (по сегодня или по вчера) открыт сундук, считая после последней недельной награды."""
    d0 = day_start()
    last = q1("SELECT MAX(day) d FROM quest_claims WHERE user=? AND qid='week'", uid)["d"] or 0
    days = {r["day"] for r in q("SELECT day FROM quest_claims WHERE user=? AND qid='chest' AND day>? AND day>=?", uid, last, d0 - 8 * 86400)}
    d, s = (d0 if d0 in days else d0 - 86400), 0
    while d in days:
        s += 1
        d -= 86400
    return s


@app.get(R + "/quests")
def quests(uid=Depends(auth)):
    return {"items": quests_state(uid), "resetIn": day_start() + 86400 - now()}


@app.post(R + "/quests/{qid}/claim")
def quest_claim(qid: str, uid=Depends(auth)):
    with tx():
        st = next((x for x in quests_state(uid) if x["id"] == qid), None) or err("нет такого задания")
        if st["claimed"]:
            err("награда уже получена")
        if st["have"] < st["need"]:
            err("задание ещё не выполнено")
        db.execute("INSERT INTO quest_claims VALUES(?,?,?)", (uid, qid, day_start()))
        got = max(1, int(st["reward"] * conf("economy.reward_scale", 1.0)))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got, uid))
        event(uid, "quest", got)
    return {"reward": got, "stars": bal(uid)}


# ---------------- ещё мини-игры: кубик, лимбо, плинко, башня, слоты ----------------
EDGE = conf("games.edge", 0.96)  # возврат игроку в «быстрых» играх


def _bet_tx(uid, bet, kind, pay):
    """Списать ставку, начислить выигрыш, записать событие и опыт — одной транзакцией."""
    with tx():
        check_bet(uid, bet)
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
        event(uid, kind, pay - bet)
        lvl = add_xp(uid, max(1, bet // 20))
    return {"pay": pay, "stars": bal(uid), "levelup": lvl}


# --- кубик: выпадает 0.00–99.99, ставишь больше/меньше порога ---
@app.post(R + "/dice")
async def dice(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, target, over = int(b.get("bet", 0)), round(float(b.get("target", 50)), 2), bool(b.get("over", True))
    if not 2 <= target <= 98:
        err("порог от 2 до 98")
    chance = (100 - target) if over else target
    if chance > 95:   # при шансе выше 95% выигрыш был бы ≤ ставки
        err("шанс не больше 95%")
    mult = round(edge(tuned("games.edge", EDGE)) * 100 / chance, 4)
    if mult < 1.01:   # при низком возврате высокий шанс давал бы выплату меньше ставки
        err(f"шанс не больше {int(edge(tuned('games.edge', EDGE)) * 100 / 1.01)}%")
    with tx():
        check_bet(uid, bet)
        rr, pf = fair.rolls(uid, "dice", ref=f"{target}:{'o' if over else 'u'}")
        roll = fair.idx(rr[0], 10000) / 100
        win = roll > target if over else roll < target
        pay = int(bet * mult) if win else 0
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
        event(uid, "dice", pay - bet, stake=bet, pf=pf, res={"roll": roll, "target": target, "over": over, "mult": mult})
        lvl = add_xp(uid, max(1, bet // 20))
    return {"roll": roll, "win": win, "mult": round(mult, 2), "pay": pay, "stars": bal(uid), "levelup": lvl, "pf": pf}


# --- лимбо: случайный множитель, выигрыш если не меньше цели ---
@app.post(R + "/limbo")
async def limbo(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, target = int(b.get("bet", 0)), round(float(b.get("target", 2)), 2)
    if not 1.01 <= target <= 1000:
        err("цель от 1.01x до 1000x")
    with tx():
        check_bet(uid, bet)
        rr, pf = fair.rolls(uid, "limbo", ref=str(target))
        r = max(1.0, min(10000.0, math.floor(edge(tuned("games.edge", EDGE)) * 100 / (1 - rr[0])) / 100))
        win = r >= target
        pay = int(bet * target) if win else 0
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
        event(uid, "limbo", pay - bet, stake=bet, pf=pf, res={"result": r, "target": target, "edge": edge(tuned("games.edge", EDGE))})
        lvl = add_xp(uid, max(1, bet // 20))
    return {"result": r, "win": win, "pay": pay, "stars": bal(uid), "levelup": lvl, "pf": pf}


# --- плинко: 12 рядов, 13 лунок, три уровня риска ---
# 2026-10: игру абузили («станок»): бонус за уровень возвращал ~6% оборота + низкий риск ≈99% + по 10 шариков.
# Теперь: бонус за уровень ≈0,4% оборота (add_xp), возврат — из админки (games.plinko_rtp, по умолчанию 96%),
# лимиты и кризисный потолок — на СУММУ всех шариков, не чаще PLINKO_GAP секунды на игрока.
PLINKO_ROWS = 12
PLINKO_RTP = conf("games.plinko_rtp", 0.96)
PLINKO_GAP = 0.25
_PSHAPE = {   # форма таблиц; итоговые множители — масштаб под возврат, округление вниз
    "low": [9, 3, 1.5, 1.3, 1.1, 1, .45, 1, 1.1, 1.3, 1.5, 3, 9],
    "mid": [30, 10, 4, 2, 1.1, .55, .3, .55, 1.1, 2, 4, 10, 30],
    "high": [150, 22, 8, 2, .7, .2, .2, .2, .7, 2, 8, 22, 150],
}
_PPROB = [math.comb(PLINKO_ROWS, i) / 2 ** PLINKO_ROWS for i in range(PLINKO_ROWS + 1)]
_PLAST = {}


def plinko_tables():
    rtp = edge(tuned("games.plinko_rtp", PLINKO_RTP))
    out = {}
    for risk, shape in _PSHAPE.items():
        k = rtp / sum(p * m for p, m in zip(_PPROB, shape))
        out[risk] = [math.floor(m * k * 100) / 100 for m in shape]
    return out


@app.get(R + "/plinko")
def plinko_info(uid=Depends(auth)):
    return {"rows": PLINKO_ROWS, "tables": plinko_tables(), "rtp": round(edge(tuned("games.plinko_rtp", PLINKO_RTP)) * 100, 1),
            "chances": [round(p * 100, 3) for p in _PPROB]}


@app.post(R + "/plinko")
async def plinko(req: Request, uid=Depends(auth)):
    b = await req.json()
    try:
        bet, risk, n = int(b.get("bet", 0)), str(b.get("risk", "mid")), int(b.get("n", 1))
    except (TypeError, ValueError):
        err("Неверные данные — обнови экран")
    tables = plinko_tables()
    if risk not in tables:
        err("Действие устарело — обнови экран")
    if n not in (1, 5, 10):
        err("шариков — 1, 5 или 10")
    t = time.time()
    if t - _PLAST.get(uid, 0) < PLINKO_GAP:
        err("Не так быстро")
    _PLAST[uid] = t
    balls = []
    with tx():
        if not 10 <= bet:
            err("ставка от 10 ⭐ за шарик")
        if bet * n > MAX_BET:
            err(f"за один бросок не больше ⭐ {MAX_BET:,} — уменьши ставку или число шариков".replace(",", " "))
        check_bet(uid, bet * n, 10 * n)   # лимит, баланс и кризисный потолок — на всю сумму
        rr, pf = fair.rolls(uid, "plinko", ref=risk, n=n * PLINKO_ROWS)
        for bi in range(n):
            path = [fair.idx(rr[bi * PLINKO_ROWS + j], 2) for j in range(PLINKO_ROWS)]
            slot = sum(path)
            mult = tables[risk][slot]
            balls.append({"path": path, "slot": slot, "mult": mult, "pay": int(bet * mult)})
        pay = sum(x["pay"] for x in balls)
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet * n, pay, uid))
        for x in balls:
            event(uid, "plinko", x["pay"] - bet, stake=bet)
        fair.record(uid, "plinko", bet * n, pay, {"rows": PLINKO_ROWS, "slots": [x["slot"] for x in balls]}, pf)
        lvl = add_xp(uid, max(1, bet * n // 20))
    return {"balls": balls, "bet": bet, "pay": pay, "stars": bal(uid), "levelup": lvl, "pf": pf}


# --- башня: 8 этажей, на каждом одна мина среди плиток ---
db.executescript("CREATE TABLE IF NOT EXISTS tower(user INTEGER PRIMARY KEY, bet INTEGER, mode TEXT, bombs TEXT, picks TEXT, ts INTEGER);")
TOWER_FLOORS = 8
TOWER_MODES = {"easy": 4, "mid": 3, "hard": 2}   # плиток на этаже, мина одна


def tower_mult(mode, k):
    w = TOWER_MODES[mode]
    return (edge(tuned("games.edge", EDGE)) * (w / (w - 1)) ** k) if k else 1.0


def tower_state(r, reveal=False):
    picks = json.loads(r["picks"])
    st = {"active": True, "bet": r["bet"], "mode": r["mode"], "picks": picks, "floor": len(picks),
          "mult": round(tower_mult(r["mode"], len(picks)), 2), "next": round(tower_mult(r["mode"], len(picks) + 1), 2)}
    if reveal:
        st["bombs"] = json.loads(r["bombs"])
    return st


@app.get(R + "/tower")
def tower_get(uid=Depends(auth)):
    r = q1("SELECT * FROM tower WHERE user=?", uid)
    return {**(tower_state(r) if r else {"active": False}),
            "modes": {m: [round(tower_mult(m, k), 2) for k in range(1, TOWER_FLOORS + 1)] for m in TOWER_MODES}}


@app.post(R + "/tower/start")
async def tower_start(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, mode = int(b.get("bet", 0)), str(b.get("mode", "mid"))
    if mode not in TOWER_MODES:
        err("Действие устарело — обнови экран")
    with tx():
        if q1("SELECT 1 FROM tower WHERE user=?", uid):
            err("игра уже идёт")
        check_bet(uid, bet)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        rr, pf = fair.rolls(uid, "tower", ref=mode, n=TOWER_FLOORS)
        bombs = [fair.idx(r, TOWER_MODES[mode]) for r in rr]
        db.execute("INSERT INTO tower VALUES(?,?,?,?,?,?)", (uid, bet, mode, json.dumps(bombs), "[]", now()))
        lvl = add_xp(uid, max(1, bet // 20))
        r = q1("SELECT * FROM tower WHERE user=?", uid)
    return {**tower_state(r), "stars": bal(uid), "levelup": lvl, "pf": pf}


def _tower_cash(uid, r):
    pay = int(r["bet"] * tower_mult(r["mode"], len(json.loads(r["picks"]))))
    db.execute("DELETE FROM tower WHERE user=?", (uid,))
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
    event(uid, "tower", pay - r["bet"], stake=r["bet"], res={"tiles": TOWER_MODES[r["mode"]], "bombs": json.loads(r["bombs"])})
    return {**tower_state(r, True), "active": False, "pay": pay, "stars": bal(uid)}


@app.post(R + "/tower/step")
async def tower_step(req: Request, uid=Depends(auth)):
    tile = int((await req.json()).get("tile", -1))
    with tx():
        r = q1("SELECT * FROM tower WHERE user=?", uid) or err("игра не начата")
        if not 0 <= tile < TOWER_MODES[r["mode"]]:
            err("Действие устарело — обнови экран")
        picks, bombs = json.loads(r["picks"]), json.loads(r["bombs"])
        if bombs[len(picks)] == tile:
            db.execute("DELETE FROM tower WHERE user=?", (uid,))
            event(uid, "tower", -r["bet"], stake=r["bet"], res={"tiles": TOWER_MODES[r["mode"]], "bombs": json.loads(r["bombs"])})
            return {**tower_state(r, True), "active": False, "boom": [len(picks), tile]}
        picks.append(tile)
        db.execute("UPDATE tower SET picks=? WHERE user=?", (json.dumps(picks), uid))
        r = q1("SELECT * FROM tower WHERE user=?", uid)
        if len(picks) == TOWER_FLOORS:
            return _tower_cash(uid, r)
        return tower_state(r)


@app.post(R + "/tower/cashout")
def tower_cashout(uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM tower WHERE user=?", uid) or err("игра не начата")
        if not json.loads(r["picks"]):
            err("пройди хотя бы один этаж")
        return _tower_cash(uid, r)


# --- слоты: 3 барабана с подарками ---
SLOT_SYMS = ["Lol Pop", "Desk Calendar", "Jelly Bunny", "Signet Ring", "Durov's Cap", "Plush Pepe"]
SLOT_W = [30, 25, 18, 12, 8, 4]
_S3 = [4, 8, 15, 30, 80, 500]      # три одинаковых
_S2 = [.5, .7, 1, 1.5, 3, 10]      # ровно два одинаковых


def _slot_tables(target=0.94):
    tw = sum(SLOT_W)
    p = [w / tw for w in SLOT_W]
    rtp = sum(pi ** 3 * a + 3 * pi ** 2 * (1 - pi) * c for pi, a, c in zip(p, _S3, _S2))
    s = target / rtp
    return [round(a * s, 1) if a * s < 10 else round(a * s) for a in _S3], [round(c * s, 2) for c in _S2]


_SLOT_C = {}


def slot_tables():
    """(три, два) под текущий возврат: settings.toml [games] slots_rtp или правка из админки."""
    rtp = tuned("games.slots_rtp", 0.94)
    if rtp not in _SLOT_C:
        _SLOT_C[rtp] = _slot_tables(rtp)
    return _SLOT_C[rtp]


@app.get(R + "/slots")
def slots_info(uid=Depends(auth)):
    s3, s2 = slot_tables()
    return {"syms": SLOT_SYMS, "three": s3, "two": s2}


@app.post(R + "/slots")
async def slots(req: Request, uid=Depends(auth)):
    body = await req.json()
    bet, n = int(body.get("bet", 0)), max(1, min(5, int(body.get("n", 1))))
    spins, total = [], 0
    SLOT3, SLOT2 = slot_tables()
    with tx():
        check_bet(uid, bet)
        if bal(uid) < bet * n:
            err("Не хватает звёзд")
        rr, pf = fair.rolls(uid, "slots", n=n * 3)
        for si in range(n):   # n автоматов крутятся одновременно, ставка на каждый
            reels = [fair.pick(rr[si * 3 + j], SLOT_W) for j in range(3)]
            cnt = {x: reels.count(x) for x in reels}
            sym, k = max(cnt.items(), key=lambda kv: (kv[1], kv[0]))
            mult = SLOT3[sym] if k == 3 else SLOT2[sym] if k == 2 else 0
            pay = int(bet * mult)
            total += pay
            spins.append({"reels": reels, "mult": mult, "pay": pay})
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet * n, total, uid))
        for sp in spins:
            event(uid, "slots", sp["pay"] - bet, stake=bet)
        fair.record(uid, "slots", bet * n, total, {"reels": [sp["reels"] for sp in spins], "w": SLOT_W}, pf)
        lvl = add_xp(uid, max(1, bet * n // 20))
    first = spins[0]
    return {"spins": spins, "reels": first["reels"], "mult": first["mult"], "win": total > 0, "pay": total,
            "stars": bal(uid), "levelup": lvl, "pf": pf}


# --- банк казино: стартовый резерв + всё, что проиграли игроки, − всё, что они выиграли ---
BANK_START = 50_000_000


@app.get(R + "/bank")
def bank(uid=Depends(auth)):
    import bank as _bank   # тот же расчёт, что в bank.py (с учётом сброса банка на вайпе)
    total = BANK_START - _bank.bank_value()
    today = q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind IN {GAME_KINDS} AND ts>=?", day_start())["s"]
    return {"bank": BANK_START - total, "today": -today, **_bank.ticker()}


# --- «Пёсики»: слот 5×3, вайлд-будка, фриспины с липкими вайлдами ---
import dogs as DOGS  # noqa: E402


@app.get(R + "/dogs")
def dogs_info(uid=Depends(auth)):
    return {"dogs": DOGS.DOGS, "low": DOGS.LOW, "lines": DOGS.LINES, "free": DOGS.FREE_SPINS, "freeBy": DOGS.FREE_BY_SCAT, "buy": DOGS.BUY_PRICE,
            "pay": [[round(p * DOGS.scale() / DOGS.NL, 2) for p in row] for row in DOGS.PAY]}


@app.post(R + "/dogs")
async def dogs_spin(req: Request, uid=Depends(auth)):
    """n автоматов (1, 2 или 4) крутятся одновременно, ставка на каждый. Первый — в корне ответа (старый формат)."""
    b = await req.json()
    bet, n = int(b.get("bet", 0)), int(b.get("n", 1))
    if n not in (1, 2, 4):
        err("автоматов: 1, 2 или 4")
    with tx():
        check_bet(uid, bet)
        if bal(uid) < bet * n:
            err("Не хватает звёзд")
        rng = fair.stream(uid, "dogs", f"spin:{n}")
        rounds = [DOGS.spin(bet, rng) for _ in range(n)]
        total = sum(r["pay"] for r in rounds)
        fair.record(uid, "dogs", bet * n, total, {"pays": [r["pay"] for r in rounds]}, fair.close_stream(rng))
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet * n, total, uid))
        for r in rounds:
            event(uid, "dogs", r["pay"] - bet, stake=bet)
        lvl = add_xp(uid, max(1, bet * n // 20))
    return {**rounds[0], "rounds": rounds, "total": total, "stars": bal(uid), "levelup": lvl}


@app.post(R + "/dogs/buy")
async def dogs_buy(req: Request, uid=Depends(auth)):
    """Покупка бонуса: цена = ставка × BUY_PRICE[лапок], сразу фриспины (6 или 10)."""
    b = await req.json()
    bet, scat = int(b.get("bet", 0)), int(b.get("scat", 3))
    if scat not in DOGS.BUY_PRICE:
        err("нет такого бонуса")
    cost = bet * DOGS.BUY_PRICE[scat]
    with tx():
        check_bet(uid, bet, 10, 100_000)
        if bal(uid) < cost:
            err(f"Нужно ⭐ {cost}")
        rng = fair.stream(uid, "dogs", f"buy:{scat}")
        r = DOGS.bonus_round(bet, scat, rng)
        fair.record(uid, "dogs", cost, r["pay"], {"pays": [r["pay"]]}, fair.close_stream(rng))
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (cost, r["pay"], uid))
        event(uid, "dogs", r["pay"] - cost, stake=cost)
        lvl = add_xp(uid, max(1, cost // 20))
    return {**r, "rounds": [r], "total": r["pay"], "cost": cost, "stars": bal(uid), "levelup": lvl}


# --- рулетка (европейская, 37 секторов) ---
RL_RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


def _rl_win(t, v, n):
    """Множитель выплаты (с возвратом ставки) для ставки типа t со значением v при выпавшем n."""
    if t == "num":
        return 36 if n == int(v) else 0
    if n == 0:
        return 0
    if t == "red":
        return 2 if n in RL_RED else 0
    if t == "black":
        return 2 if n not in RL_RED else 0
    if t == "even":
        return 2 if n % 2 == 0 else 0
    if t == "odd":
        return 2 if n % 2 else 0
    if t == "low":
        return 2 if n <= 18 else 0
    if t == "high":
        return 2 if n >= 19 else 0
    if t == "dozen":
        return 3 if (n - 1) // 12 == int(v) else 0
    if t == "col":
        return 3 if (n - 1) % 3 == int(v) else 0
    return 0


@app.post(R + "/rlt")
async def roulette(req: Request, uid=Depends(auth)):
    bets = (await req.json()).get("bets", [])[:40]
    clean, total = [], 0
    for b in bets:
        t, v, a = str(b.get("t")), b.get("v"), int(b.get("a", 0))
        if t not in ("num", "red", "black", "even", "odd", "low", "high", "dozen", "col") or a < 1:
            err("неверная ставка")
        if t == "num" and not (0 <= int(v) <= 36) or t in ("dozen", "col") and not (0 <= int(v) <= 2):
            err("неверная ставка")
        clean.append((t, v, a))
        total += a
    if not clean or total < 10:
        err("ставка от 10 ⭐")
    with tx():
        check_bet(uid, total)
        rr, pf = fair.rolls(uid, "rlt", ref=str(len(clean)), n=1)
        n = fair.idx(rr[0], 37)
        pay = sum(a * _rl_win(t, v, n) for t, v, a in clean)
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (total, pay, uid))
        event(uid, "roulette", pay - total, stake=total, pf=pf, res={"n": n})
        lvl = add_xp(uid, max(1, total // 20))
    return {"n": n, "red": n in RL_RED, "win": [i for i, (t, v, a) in enumerate(clean) if _rl_win(t, v, n)],
            "pay": pay, "stars": bal(uid), "levelup": lvl, "pf": pf}


# --- сеты: собери N разных моделей коллекции — получи награду ---
db.executescript("CREATE TABLE IF NOT EXISTS set_claims(user INTEGER, col TEXT, tier INTEGER, ts INTEGER, PRIMARY KEY(user,col,tier));")
SET_TIERS = {5: 0.5, 10: 1.5, 25: 5.0}   # ступень → награда в базовых ценах коллекции


def set_reward(col, tier):
    return int(min(250_000, E.base(col) * SET_TIERS[tier]))


@app.get(R + "/sets")
def sets(uid=Depends(auth)):
    own = {}
    for r in q("SELECT col, COUNT(DISTINCT model) n FROM gifts WHERE owner=? GROUP BY col", uid):
        own[r["col"]] = r["n"]
    claimed = {(r["col"], r["tier"]) for r in q("SELECT col, tier FROM set_claims WHERE user=?", uid)}
    out = {}
    for col, d in E.CATALOG.items():
        tiers = [{"tier": t, "reward": set_reward(col, t), "claimed": (col, t) in claimed} for t in SET_TIERS if t <= len(d["models"])]
        out[col] = {"have": own.get(col, 0), "n": len(d["models"]), "base": E.base(col), "tiers": tiers}
    return {"sets": out, "claimed": len(claimed)}


@app.post(R + "/sets/claim")
async def set_claim(req: Request, uid=Depends(auth)):
    b = await req.json()
    col, tier = str(b.get("col")), int(b.get("tier", 0))
    if col not in E.CATALOG or tier not in SET_TIERS:
        err("Действие устарело — обнови экран")
    with tx():
        # в зачёт — подарки, которые у игрока хотя бы сутки: иначе один набор гоняют по твинкам и каждый забирает награду
        have = q1("SELECT COUNT(DISTINCT model) n FROM gifts WHERE owner=? AND col=? AND COALESCE(acq,0)<=?", uid, col, now() - 86400)["n"]
        if have < tier:
            fresh = q1("SELECT COUNT(DISTINCT model) n FROM gifts WHERE owner=? AND col=?", uid, col)["n"]
            err(f"нужно {tier} разных моделей, у тебя {have}" + (" (новые подарки засчитываются через сутки)" if fresh > have else ""))
        if q1("SELECT 1 FROM set_claims WHERE user=? AND col=? AND tier=?", uid, col, tier):
            err("награда уже получена")
        reward = set_reward(col, tier)
        db.execute("INSERT INTO set_claims VALUES(?,?,?,?)", (uid, col, tier, now()))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (reward, uid))
        event(uid, "set", reward)
    return {"reward": reward, "stars": bal(uid)}


# --- история цен на маркете ---
@app.get(R + "/market/history")
def market_history(col: str, uid=Depends(auth)):
    d0 = day_start() - 13 * 86400
    days = []
    for i in range(14):
        a, b = d0 + i * 86400, d0 + (i + 1) * 86400
        r = q1("SELECT COUNT(*) n, AVG(price) avg, MIN(price) mn FROM sales WHERE col=? AND ts>=? AND ts<?", col, a, b)
        days.append({"day": a, "n": r["n"], "avg": round(r["avg"]) if r["avg"] else None, "min": r["mn"]})
    floor = q1("SELECT MIN(price) f, COUNT(*) n FROM gifts WHERE col=? AND price IS NOT NULL", col)
    last = q("SELECT price, model, ts FROM sales WHERE col=? ORDER BY id DESC LIMIT 5", col)
    return {"col": col, "days": days, "floor": floor["f"], "listed": floor["n"], "base": E.base(col),
            "last": [dict(x) for x in last]}


# --- напоминания от бота: бесплатный кейс готов, серия бонусов сгорает ---
for _c in ("notif INTEGER DEFAULT 1", "rem_free INTEGER DEFAULT 0", "rem_daily INTEGER DEFAULT 0", "rem_last INTEGER DEFAULT 0"):
    try:
        db.execute("ALTER TABLE users ADD COLUMN " + _c)
    except Exception:
        pass
REMIND_GAP = 3 * 3600   # не чаще раза в 3 часа на игрока


def _reminders():
    t = now()
    for u in q("SELECT id, last_free, last_daily, streak, rem_free, rem_daily, rem_last, seen FROM users "
               "WHERE notif=1 AND seen>? AND rem_last<?", t - 7 * 86400, t - REMIND_GAP):
        msg, col = None, None
        if u["streak"] >= 2 and 42 * 3600 <= t - u["last_daily"] < 48 * 3600 and u["rem_daily"] != u["last_daily"]:
            left = int((u["last_daily"] + 48 * 3600 - t) / 3600) or 1
            msg, col = f"🔥 Серия бонусов ({u['streak']} дн.) сгорит через {left} ч — забери бонус дня!", ("rem_daily", u["last_daily"])
        elif u["last_free"] and t >= u["last_free"] + free_every(u) and u["rem_free"] != u["last_free"] and t - u["seen"] > 1800:
            msg, col = "🎁 Бесплатный кейс снова готов — открой его!", ("rem_free", u["last_free"])
        if msg:
            with tx():
                db.execute(f"UPDATE users SET {col[0]}=?, rem_last=? WHERE id=?", (col[1], t, u["id"]))
            notify(u["id"], msg)


async def reminder_loop():
    await asyncio.sleep(30)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _reminders)
        except Exception as e:
            print("reminders:", e, flush=True)
        await asyncio.sleep(300)


@app.post(R + "/settings")
async def settings(req: Request, uid=Depends(auth)):
    b = await req.json()
    with tx():
        db.execute("UPDATE users SET notif=? WHERE id=?", (1 if b.get("notif") else 0, uid))
    return {"ok": True}


@app.post(R + "/surprise/ack")
def surprise_ack(uid=Depends(auth)):
    with tx():
        db.execute("UPDATE users SET surprise=0 WHERE id=?", (uid,))
    return {"ok": True}


# ---------------- топы ----------------
def week_start():
    """Понедельник 00:00 UTC (время берём один раз — см. day_start)."""
    t = int(time.time())
    return t - t % 86400 - time.gmtime(t).tm_wday * 86400


GAME_KINDS = "('carousel','safe','ladder','bankbet','forecast','case','crash','upgrade','mines','wheel','duel','dice','limbo','plinko','tower','slots','blackjack','cards','dogs','roulette','jroul','hilo','craft','chicken','starfall','avia','battle','scratch','claw','pump','drill','darts','fish','keno','penalty')"


def pnl(uids, since=0):
    """Выиграно / проиграно по играм и кейсам для списка игроков."""
    if not uids:
        return {}
    ph = ",".join("?" * len(uids))
    rows = q(f"""SELECT user, SUM(CASE WHEN delta>0 THEN delta ELSE 0 END) won, SUM(CASE WHEN delta<0 THEN -delta ELSE 0 END) lost
                 FROM events WHERE kind IN {GAME_KINDS} AND ts>=? AND user IN ({ph}) GROUP BY user""", since, *uids)
    return {r["user"]: (r["won"] or 0, r["lost"] or 0) for r in rows}


@app.get(R + "/leaders")
def leaders(kind: str = "rich", uid=Depends(auth)):
    since = max(week_start(), season_from()) if kind == "week" else season_from()
    if kind == "level":
        rows = q("SELECT *, xp score FROM users ORDER BY xp DESC LIMIT 50")
        fmt = lambda r: {"score": level(r["xp"])}
    elif kind == "crash":
        rows = q("SELECT *, best_crash score FROM users WHERE best_crash>0 ORDER BY best_crash DESC LIMIT 50")
        fmt = lambda r: {"score": r["best_crash"]}
    elif kind in ("week", "profit"):
        rows = q(f"""SELECT u.*, SUM(e.delta) score FROM events e JOIN users u ON u.id=e.user
                    WHERE e.ts>=? AND e.kind IN {GAME_KINDS} GROUP BY e.user ORDER BY score DESC LIMIT 50""", since)
        fmt = lambda r: {"score": r["score"]}
    else:
        rows = q("""SELECT u.*, u.stars + COALESCE((SELECT SUM(value) FROM gifts g WHERE g.owner=u.id),0) score
                    FROM users u ORDER BY score DESC LIMIT 50""")
        fmt = lambda r: {"score": r["score"]}
    ids = [r["id"] for r in rows]
    pl = pnl(ids + [uid], since)
    out = []
    for r in rows:
        w, l = pl.get(r["id"], (0, 0))
        out.append({**user_brief(r), **fmt(r), "won": w, "lost": l})
    mw, ml = pl.get(uid, (0, 0))
    pos = next((i + 1 for i, r in enumerate(rows) if r["id"] == uid), None)
    return {"kind": kind, "weekEnds": week_start() + 7 * 86400, "rows": out, "richPerks": rich.PERKS, "myCrown": RICH_RANK.get(uid),
            "me": {"won": mw, "lost": ml, "net": mw - ml, "pos": pos, "worth": net_worth(uid)}}


# ---------------- друзья ----------------
@app.get(R + "/friends")
def friends(uid=Depends(auth)):
    rows = q("SELECT * FROM friends WHERE a=? OR b=?", uid, uid)
    out = {"friends": [], "incoming": [], "outgoing": []}
    for r in rows:
        other = r["b"] if r["a"] == uid else r["a"]
        u = q1("SELECT * FROM users WHERE id=?", other)
        if not u:
            continue
        key = "friends" if r["status"] == "ok" else ("outgoing" if r["a"] == uid else "incoming")
        out[key].append(user_brief(u))
    return out


@app.get(R + "/users/search")
def search(qs: str = "", uid=Depends(auth)):
    s = qs.strip().lstrip("@")
    if len(s) < 2:
        return []
    rows = q("SELECT * FROM users WHERE (username LIKE ? OR name LIKE ?) AND id!=? ORDER BY xp DESC LIMIT 20",
             f"%{s}%", f"%{s}%", uid)
    return [user_brief(r) for r in rows]


@app.post(R + "/friends/{tid}/{action}")
def friend_action(tid: int, action: str, uid=Depends(auth)):
    if tid == uid:
        err("это ты")
    with tx():
        if not q1("SELECT 1 FROM users WHERE id=?", tid):
            err("игрок не найден", 404)
        st = friend_status(uid, tid)
        me_name = q1("SELECT name FROM users WHERE id=?", uid)["name"]
        msg = None
        if action == "add":
            if st == "incoming":
                db.execute("UPDATE friends SET status='ok' WHERE a=? AND b=?", (tid, uid))
                msg = f"🤝 <b>{esc(me_name)}</b> принял заявку в друзья"
            elif st == "none":
                db.execute("INSERT INTO friends VALUES(?,?,?,?)", (uid, tid, "pending", now()))
                msg = f"👋 <b>{esc(me_name)}</b> хочет добавить тебя в друзья"
        elif action == "remove":
            db.execute("DELETE FROM friends WHERE (a=? AND b=?) OR (a=? AND b=?)", (uid, tid, tid, uid))
        else:
            err("Действие устарело — обнови экран")
    if msg:
        notify(tid, msg)
    return {"rel": friend_status(uid, tid)}


# ---------------- обмены ----------------
def trade_out(r):
    def gl(ids):
        rows = [q1("SELECT * FROM gifts WHERE id=?", i) for i in json.loads(ids)]
        return [gift_out(x) for x in rows if x]
    s, d = q1("SELECT * FROM users WHERE id=?", r["src"]), q1("SELECT * FROM users WHERE id=?", r["dst"])
    return {"id": r["id"], "src": user_brief(s), "dst": user_brief(d), "give": gl(r["give"]), "giveStars": r["give_stars"],
            "want": gl(r["want"]), "wantStars": r["want_stars"], "status": r["status"], "ts": r["ts"]}


@app.get(R + "/trades")
def trades(uid=Depends(auth)):
    rows = q("SELECT * FROM trades WHERE src=? OR dst=? ORDER BY id DESC LIMIT 60", uid, uid)
    return [trade_out(r) for r in rows]


@app.post(R + "/trades")
async def new_trade(req: Request, uid=Depends(auth)):
    b = await req.json()
    to = int(b.get("to", 0))
    give = sorted({int(x) for x in b.get("give", [])})[:10]
    want = sorted({int(x) for x in b.get("want", [])})[:10]
    gs, ws = max(0, int(b.get("giveStars", 0))), max(0, int(b.get("wantStars", 0)))
    if to == uid or not q1("SELECT 1 FROM users WHERE id=?", to):
        err("кому?")
    if not (give or want or gs or ws):
        err("пустой обмен")
    with tx():
        for g in give:
            x = own_gift(g, uid)
            if x["price"] is not None:
                err("сначала сними подарок с маркета")
        for g in want:
            x = q1("SELECT owner, price FROM gifts WHERE id=?", g)
            if not x or x["owner"] != to:
                err("у него уже нет этого подарка")
        if q1("SELECT stars FROM users WHERE id=?", uid)["stars"] < gs:
            err("Не хватает звёзд")
        if gs and loans.stars_locked(uid):
            err("пока не закрыт кредит без залога, отдавать звёзды нельзя")
        cur = db.execute("INSERT INTO trades(src,dst,give,give_stars,want,want_stars,status,ts) VALUES(?,?,?,?,?,?,?,?)",
                         (uid, to, json.dumps(give), gs, json.dumps(want), ws, "open", now()))
        name = q1("SELECT name FROM users WHERE id=?", uid)["name"]
    notify(to, f"🔄 <b>{esc(name)}</b> предлагает обмен — загляни в «Обмены»")
    return {"id": cur.lastrowid}


@app.post(R + "/trades/{tid}/{action}")
def trade_action(tid: int, action: str, uid=Depends(auth)):
    with tx():
        t = q1("SELECT * FROM trades WHERE id=?", tid)
        if not t or t["status"] != "open":
            err("обмен уже закрыт")
        if action == "cancel" and t["src"] == uid:
            db.execute("UPDATE trades SET status='cancelled' WHERE id=?", (tid,))
            return {"ok": True}
        if t["dst"] != uid:
            err("не твой обмен")
        if action == "decline":
            db.execute("UPDATE trades SET status='declined' WHERE id=?", (tid,))
            notify_after = (t["src"], "❌ Твой обмен отклонили")
        elif action == "accept":
            give, want = json.loads(t["give"]), json.loads(t["want"])
            for g in give:
                x = q1("SELECT owner FROM gifts WHERE id=?", g)
                if not x or x["owner"] != t["src"]:
                    db.execute("UPDATE trades SET status='void' WHERE id=?", (tid,))
                    err("подарков уже нет — обмен отменён")
            for g in want:
                x = q1("SELECT owner FROM gifts WHERE id=?", g)
                if not x or x["owner"] != uid:
                    db.execute("UPDATE trades SET status='void' WHERE id=?", (tid,))
                    err("подарков уже нет — обмен отменён")
            if q1("SELECT stars FROM users WHERE id=?", t["src"])["stars"] < t["give_stars"]:
                err("у него не хватает звёзд")
            if q1("SELECT stars FROM users WHERE id=?", uid)["stars"] < t["want_stars"]:
                err("Не хватает звёзд")
            for g in give:
                db.execute("UPDATE gifts SET owner=?, price=NULL, listed=NULL WHERE id=?", (uid, g))
                unpin(t["src"], g)
            for g in want:
                db.execute("UPDATE gifts SET owner=?, price=NULL, listed=NULL WHERE id=?", (t["src"], g))
                unpin(uid, g)
            delta = t["give_stars"] - t["want_stars"]
            payer, getter = (t["src"], uid) if delta > 0 else (uid, t["src"])
            if delta and loans.stars_locked(payer):
                err("у одного из вас не закрыт кредит без залога — звёзды передавать нельзя")
            fee = math.ceil(abs(delta) * TRADE_FEE)
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (abs(delta), payer))
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (abs(delta) - fee, getter))
            if fee:
                event(getter, "fee", -fee)
            db.execute("UPDATE trades SET status='done' WHERE id=?", (tid,))
            for g in give + want:
                cancel_trades_with(g)
            notify_after = (t["src"], "✅ Обмен принят!")
        else:
            err("Действие устарело — обнови экран")
    notify(*notify_after)
    return {"ok": True}


import cards  # noqa: E402,F401 — блэкджек, «21» и «101» (регистрирует свои маршруты)
import jackpot  # noqa: E402,F401 — ежедневный розыгрыш банка
import pvp  # noqa: E402,F401 — джекпот на подарки
import income  # noqa: E402,F401 — доход: подарки, сейф, бизнесы
import onboard  # noqa: E402,F401 — «Старт новичка»
import games4  # noqa: E402,F401 — краш-дуэль, больше/меньше, крафт
import bank as BANKMOD  # noqa: E402,F401 — экран банка: история, акции казино, дивиденды
import crypto  # noqa: E402,F401 — крипто-биржа: реальные курсы, торговля за игровые звёзды
import chicken  # noqa: E402,F401 — «Курица»: перебежать дорогу
import avia  # noqa: E402,F401 — «Самолётик»: самолёт, облака с иксами, посадка на корабль
import battles  # noqa: E402,F401 — битва кейсов
import scratch  # noqa: E402,F401 — скретч-карты
import seasons  # noqa: E402,F401 — сезоны и титулы
import live  # noqa: E402,F401 — живая лента крупных выигрышей, онлайн, реакции
import hub  # noqa: E402,F401 — входящие (колокольчик) и история операций
import sparks  # noqa: E402,F401 — огоньки с друзьями (серии как в TikTok)
import premium  # noqa: E402,F401 — VIP, набор дня, звёздный сундук (за Telegram Stars)
import style  # noqa: E402,F401 — оформление профиля: цвет, статус, значки, рамки и ники за звёзды
import tourn  # noqa: E402,F401 — турниры каждые 3 дня
import album  # noqa: E402,F401 — альбом коллекций
import presents  # noqa: E402,F401 — подарить подарок с открыткой
import mkshop  # noqa: E402,F401 — витрина и скупка казино на маркете
import shop  # noqa: E402 — покупка игровых звёзд за Telegram Stars
import starfall  # noqa: E402,F401 — «Звездопад»: общая шкала, приз — дорогой подарок
import rich  # noqa: E402 — привилегии топа богачей
import loans  # noqa: E402,F401 — кредит под залог подарка
import clans  # noqa: E402,F401 — кланы, недельная битва кланов
import admin  # noqa: E402,F401 — админ-панель (только ADMIN_IDS)
import gates  # noqa: E402,F401 — админ закрывает/скрывает игры
import actlog  # noqa: E402,F401 — подробный журнал действий игроков (logs.db)
import retain  # noqa: E402,F401 — кэшбэк недели и «возвращайся»
import odds  # noqa: E402,F401 — админка «Шансы»: возврат по играм на лету
import claw  # noqa: E402,F401 — «Кран»: автомат с клешнёй (после admin — у него вкладка в админке)
import pump, drill, darts, fish, keno, penalty  # noqa: E402,F401 — «Насос», «Бур», «Дартс», «Рыбалка», «Кено», «Пенальти»
import ops  # noqa: E402,F401 — пульт, тревоги, разбор игрока, отмена действий админа
import sanctions  # noqa: E402,F401 — заморозка кошелька, компенсации
import league  # noqa: E402,F401 — лиги недели (группы по 30, повышение/вылет)
import pay  # noqa: E402,F401 — переводы звёзд между игроками по QR («Кошелёк»)
import dbtools  # noqa: E402,F401 — админка: экспорт/импорт базы (только владелец)
import eggs  # noqa: E402,F401 — пасхалки (без звёзд, только достижение)
import stack  # noqa: E402,F401 — «Стопка»: игра на ловкость, недельный турнир
import franchise  # noqa: E402 — франшиза: свои боты игроков с этой же игрой (Managed Bots)
import refs  # noqa: E402 — реферальная программа: уровни друзей, рубежи, доля с покупок, недельный топ
import flash  # noqa: E402 — ивенты раз в ~2 часа: «Удача ×3/×5», «Раздача ⭐»
import tickets  # noqa: E402 — тикеты поддержки: игрок ↔ админы
import polls  # noqa: E402 — опросы в боте с кнопками «Да»/«Нет», итоги админам
import fees  # noqa: E402 — все комиссии и налоги из админки (переписывает ставки модулей)
import wipe  # noqa: E402 — вайпы: сброс звёзд, подарков, бизнесов (уровень остаётся), настройки в админке
import fair  # noqa: E402,F401 — provably fair: сид-хэш ДО ставки, раскрытие после; панель «Честность»
import games5  # noqa: E402,F401 — сейф, ставка на банк, аукцион, бизнесы клана
import carousel  # noqa: E402,F401 — общее колесо с бонусами
import forecast  # noqa: E402,F401 — прогноз дня: тотализатор на итоги суток
import gameday  # noqa: E402,F401 — игра дня: рейтинг редкой игры на сутки
import nudge  # noqa: E402,F401 — письма новичкам и про Игру дня
import giveaway  # noqa: E402,F401 — розыгрыши в канале игры
import records  # noqa: E402,F401 — личные рекорды
import recruit  # noqa: E402,F401 — набор недели у кланов
import limits  # noqa: E402,F401 — лимиты игрока и итоги недели
import away  # noqa: E402,F401 — сводка «пока тебя не было»
import achrare  # noqa: E402,F401 — редкость достижений
import idletax  # noqa: E402,F401 — сбор с брошенных больших балансов
import legacy  # noqa: E402,F401 — наследие: итоги прошлых сезонов в профиле
import share  # noqa: E402,F401 — карточка большого выигрыша


# ---------------- картинки подарков (api.changes.tg); на проде перед этим стоит кэш nginx ----------------
ASSET_CACHE = os.path.join(os.path.dirname(__file__), ".asset_cache")
_WEBP_SEM = asyncio.Semaphore(2)   # одновременно не больше 2 конверсий — одно ядро, игра важнее


def _to_webp(data):
    """PNG → WebP (в 4–5 раз легче). Конвертируем один раз: дальше отдаёт кэш nginx (ключ с учётом X-Webp)."""
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    out = io.BytesIO()
    im.save(out, "WEBP", quality=85, method=4)
    return out.getvalue()


def _cache_write(path, data):
    """Запись в кэш ассетов: если папка недоступна (нет прав) — просто отдаём файл без кэша."""
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as e:
        print("asset cache:", path, e, flush=True)


def _custom_asset(raw, request):
    """Картинка своего подарка → Response; узор своего подарка → путь у донора; обычный подарок → None."""
    parts = [urllib.parse.unquote(x) for x in raw.split("/")]
    kind, col = parts[0], parts[1].removesuffix(".png").removesuffix(".json") if len(parts) > 1 else ""
    if col not in E.CUSTOM and col not in E.CUSTOM_COVERS and not col.startswith("~"):
        return None
    if kind == "pattern":
        return "pattern/" + urllib.parse.quote(E.CUSTOM_DONOR) + "/" + "/".join(raw.split("/")[2:])
    if raw.endswith(".json"):   # lottie-анимаций у своих подарков нет — фронт покажет картинку
        return Response(status_code=404)
    f = E.custom_file(col, parts[2].removesuffix(".png") if kind == "model" and len(parts) > 2 else None)
    size = request.query_params.get("size", "256")
    size = size if size in ("64", "128", "256", "512") else "256"
    webp = "image/webp" in request.headers.get("accept", "").lower() or request.headers.get("x-webp") == "1"
    path = f and f"{f}_{size}.{'webp' if webp else 'png'}"
    if not path or not os.path.exists(path):
        return Response(status_code=404)
    return FileResponse(path, media_type="image/webp" if webp else "image/png", headers={"Cache-Control": "public, max-age=2592000"})


@app.get("/np/a/{path:path}")
async def asset(path: str, request: Request):
    raw = request.scope["raw_path"].decode()[
        len("/np/a/") :
    ]  # без раскодирования: в именах бывает %2F (AC/DC)
    if not raw.startswith(("model/", "pattern/", "symbol/", "original/")):
        return Response(status_code=404)
    custom = _custom_asset(raw, request)   # свои подарки (кейс CS:GO) — с диска; их узоры — у коллекции-донора
    if isinstance(custom, Response):
        return custom
    raw = custom or raw
    url = (
        "https://api.changes.tg/"
        + raw
        + ("?" + request.url.query if request.url.query else "")
    )
    ct = "application/json" if raw.endswith(".json") else "image/png"
    # Браузер шлёт Accept: image/webp — отдаём webp (в 3–5 раз легче). Заголовок x-webp ставил nginx,
    # которого тут нет (фронт отдаёт сам uvicorn), поэтому смотрим и на Accept: иначе телефон
    # тянет десятки мегабайт PNG через медленный туннель.
    want_webp = ct == "image/png" and (
        request.headers.get("x-webp") == "1"
        or "image/webp" in request.headers.get("accept", "").lower()
    )
    hdrs = {"Cache-Control": "public, max-age=2592000"}
    if DEV or SERVE_WEB:  # без nginx кэшируем на диск, на проде кэширует nginx
        try:
            os.makedirs(ASSET_CACHE, exist_ok=True)
        except OSError as e:
            print("asset cache dir:", e, flush=True)
        f = os.path.join(ASSET_CACHE, hashlib.md5(url.encode()).hexdigest())
        fw = f + ".webp"
        if want_webp and os.path.exists(fw):
            return FileResponse(fw, media_type="image/webp", headers=hdrs)
        if not want_webp and os.path.exists(f):
            return FileResponse(f, media_type=ct, headers=hdrs)
    r = await http.get(
        url, headers={"User-Agent": f"NePridymal/1.0 (+t.me/{BOT_NAME})"}, timeout=30
    )
    if r.status_code != 200:
        return Response(status_code=r.status_code)
    if DEV or SERVE_WEB:
        _cache_write(f, r.content)
    if want_webp:
        try:
            async with _WEBP_SEM:
                body = await asyncio.to_thread(_to_webp, r.content)
            if DEV or SERVE_WEB:
                _cache_write(f + ".webp", body)
            return Response(body, media_type="image/webp", headers=hdrs)
        except Exception as e:  # не вышло — отдаём PNG как раньше
            print("webp:", raw[:80], e, flush=True)
    return Response(r.content, media_type=ct, headers=hdrs)


class CachedStatic(StaticFiles):
    """Статика с Cache-Control: без него Cloudflare не держит бандл на краю и каждый заход тянет его через туннель."""

    async def get_response(self, path: str, scope):
        resp = await super().get_response(path, scope)
        if "text/html" in resp.headers.get("content-type", ""):
            resp.headers["Cache-Control"] = "no-cache"   # страница всегда свежая: внутри неё версия бандла
        elif resp.status_code == 200:
            resp.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable" if "bundle." in path else "public, max-age=604800")
        return resp


if (DEV or SERVE_WEB) and os.path.isdir(WEB_DIR):
    app.mount("/np", CachedStatic(directory=WEB_DIR, html=True), name="web")
