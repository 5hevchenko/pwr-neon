"""Вывод скинов CS в Steam через market.csgo.com — перенос из cs-bot-backend (modules/skin).

Как в оригинале:
  · игрок сохраняет трейд-ссылку Steam (…/tradeoffer/new/?partner=…&token=…);
  · заявка: ищем предмет на площадке по торговому имени (search-item-by-hash-name), берём самую низкую цену. Площадка отдаёт её
    в валюте своего аккаунта: в долларах $1 = 1000, в рублях 1 ₽ = 100. Игра считает в долларах, рубли пересчитываются
    по курсу ЦБ (_rub_rate; без свежего курса рублёвый вывод встаёт на паузу). Другая валюта аккаунта — вывод остановлен;
    если она выше ценности скина больше чем в PRICE_CAP раз (1,15) — отказ, скин остаётся у игрока: его можно продать игре
    за полную ценность или вывести позже. Так дефицит скина на площадке не превращается в убыток;
  · покупаем предмет сразу на трейд-ссылку игрока (buy-for, chance_to_transfer=40, custom_id — номер заявки);
  · раз в минуту спрашиваем этап (get-buy-info-by-custom-id): 1 — куплен, обмен отправляется игроку (как только площадка
    отдаёт номер обмена, бот просит игрока принять его в Steam), 2 — игрок получил предмет, 5 — сорвалось:
    скин возвращается игроку, бот пишет ему об этом;
  · после этапа 2 обмен ещё можно откатить в Steam, пока не пройдёт время settlement из ответа площадки. Всё это время
    заявка перепроверяется раз в RECHECK_H часов: если площадка вернула этап 5 (buyer_rollback / seller_rollback),
    скин возвращается в сумку, админам уходит сообщение с суммами удержаний.
Добавлено под единую валюту (в оригинале коины были отдельным кошельком и раздавались скупо):
  · вывод открыт только тем, кто покупал за Telegram Stars; сумма выводов в долларах не больше
    оплаченные XTR × xtr_usd × limit_k — бесплатные ⭐ в скины сверх оплаченного не превращаются.
Площадка удаляет ключ за 5 и больше запросов в секунду, поэтому все запросы идут по одному с паузой GAP.
Ключ площадки — переменная окружения MARKET_KEY (в коде и в базе его нет), в запросах он идёт в заголовке X-API-KEY,
а не в адресе. Без ключа вывод выключен."""
import asyncio
import json
import os
import re
import secrets
import time

from fastapi import Depends, Request

import economy as E
import app as A
from app import R, app, auth, db, err, gift_out, notify, now, q, q1, tx
from settings import conf

MARKET = os.environ.get("MARKET_URL", "https://market.csgo.com/api/v2/")   # MARKET_URL — только для тестов
KEY = os.environ.get("MARKET_KEY", "").strip()
ON = conf("withdraw.on", True)
XTR_USD = conf("withdraw.xtr_usd", 0.011)        # сколько долларов приносит 1 Telegram Star (осторожная оценка; по факту ≈ 0,013)
LIMIT_K = conf("withdraw.limit_k", 0.7)          # лимит выводов = оплачено × этот множитель
HOLD_H = conf("withdraw.hold_hours", 24)         # свежая оплата идёт в лимит только через столько часов (защита от возвратов платежей)
EXTRA_USED = []                                  # другие виды вывода в том же лимите: функции uid → $ (настоящие подарки — realgifts.py)
PRICE_CAP = conf("withdraw.price_cap", 1.15)     # цена на площадке не выше ценности скина × это число, иначе вывод не покупается (в оригинале было ×3)
RECHECK_H = conf("withdraw.recheck_hours", 6)     # как часто перепроверять уже переданные скины, пока обмен можно откатить
LOW_USD = conf("withdraw.low_usd", 10.0)         # баланс площадки ниже этого (в пересчёте на $) — сообщение админам
RUB_FIX = conf("withdraw.rub_per_usd", 0)        # курс ₽ за $ вручную; 0 — брать сам (ЦБ, запасные источники)
FX_AGE = 48 * 3600                               # курс старше этого не годится: рублёвый вывод на паузе
# источники курса ₽ за $ и где в ответе лежит число. FX_URL — только для тестов
FX = [(os.environ["FX_URL"], ("Valute", "USD", "Value"))] if os.environ.get("FX_URL") else [
    ("https://www.cbr-xml-daily.ru/daily_json.js", ("Valute", "USD", "Value")),
    ("https://open.er-api.com/v6/latest/USD", ("rates", "RUB")),
    ("https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub", ("tether", "rub"))]
CHECK_EVERY = int(os.environ.get("MARKET_CHECK", "60"))
RECHECK = int(os.environ.get("MARKET_RECHECK", str(int(RECHECK_H * 3600))))   # MARKET_RECHECK — только для тестов
LINK_RE = re.compile(r"^https://steamcommunity\.com/tradeoffer/new/?\?partner=(\d+)&token=([A-Za-z0-9_-]+)$")
# коды ошибок buy-for (комментарий в оригинальном market.ts) → что сказать игроку
CODES = {2: "Площадка вернула ошибку — попробуй ещё раз", 20: "Проверка трейд-ссылок на площадке временно недоступна — попробуй позже",
         3: "Не удалось проверить трейд-ссылку", 5: "У тебя скрыт инвентарь Steam — открой его в настройках приватности",
         6: "Аккаунт Steam заблокирован", 7: "К аккаунту Steam не привязан мобильный аутентификатор",
         8: "Ссылка не прошла проверку — включи офлайн-обмены в Steam", 12: "Неверная трейд-ссылка",
         21: "Инвентарь Steam переполнен"}
STAGE = {"1": "Покупаем и передаём", "2": "Получен в Steam", "5": "Не удалось — скин возвращён", "6": "Не удалось — скин возвращён"}

db.execute("CREATE TABLE IF NOT EXISTS withdraws(id TEXT PRIMARY KEY, user INTEGER, gift TEXT, col TEXT, hash TEXT, usd REAL, "
           "market_usd REAL, stage TEXT, error TEXT, causer TEXT, ts INTEGER, upd INTEGER)")
db.execute("CREATE INDEX IF NOT EXISTS withdraws_user ON withdraws(user)")
# offer — номер обмена Steam (игроку уже написали «прими обмен»); miss — сколько раз подряд площадка не нашла заявку;
# settle — до какого времени переданный скин перепроверяется на откат обмена
for _sql in ("ALTER TABLE users ADD COLUMN trade_link TEXT", "ALTER TABLE withdraws ADD COLUMN offer TEXT DEFAULT ''",
             "ALTER TABLE withdraws ADD COLUMN miss INTEGER DEFAULT 0", "ALTER TABLE withdraws ADD COLUMN settle INTEGER DEFAULT 0"):
    try:
        db.execute(_sql)
    except Exception:
        pass


def enabled():
    return bool(ON and KEY)


_FX = {"rate": 0.0, "ts": 0, "try": 0}
try:
    _FX["rate"], _FX["ts"] = [float(x) for x in (A.kv_get("rub_usd") or "0 0").split()]
except Exception:
    pass


def _rate():
    """Курс ₽ за $ из памяти; 0 — годного курса нет."""
    if RUB_FIX:
        return float(RUB_FIX)
    return _FX["rate"] if now() - _FX["ts"] < FX_AGE else 0.0


async def _rub_rate():
    """Курс ₽ за $: обновляется раз в час, хранится в базе (переживает перезапуск)."""
    if RUB_FIX:
        return float(RUB_FIX)
    if now() - _FX["ts"] < 3600 or now() - _FX["try"] < 60:
        return _rate()
    _FX["try"] = now()
    for url, path in FX:
        try:
            v = (await A.http.get(url, timeout=15)).json()
            for k in path:
                v = v[k]
            v = float(v)
        except Exception:
            continue
        old = _FX["rate"]
        if not 20 < v < 500 or (old and not 0.7 < v / old < 1.4 and now() - _FX["ts"] < FX_AGE):
            continue   # не похоже на курс рубля или скачок на десятки процентов за час — такому источнику не верим
        _FX["rate"], _FX["ts"] = v, now()
        with tx():
            db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('rub_usd',?)", (f"{v} {now()}",))
        break
    return _rate()


async def _units(cur):
    """Сколько единиц цены площадки в одном долларе для валюты аккаунта; 0 — в этой валюте работать нельзя."""
    if cur == "USD":
        return 1000.0
    if cur == "RUB":
        return 100.0 * await _rub_rate()
    return 0.0


def gift_usd(g):
    """Цена скина в долларах: его ценность в ⭐ по курсу единой валюты."""
    return round(g["value"] / E.USD_COINS, 3)


def budget(uid):
    """(лимит в $, уже выведено или в работе в $) — лимит считается от оплаченного (Telegram Stars и крипта в пересчёте на Stars).
    Оплаты моложе HOLD_H часов в лимит пока не идут. В «выведено» входят и скины, и настоящие подарки."""
    paid = q1("SELECT COALESCE(SUM(xtr),0) s FROM payments WHERE user=? AND ts<=?", uid, now() - int(HOLD_H * 3600))["s"]
    # в лимит идёт то, что реально уплачено площадке (если она дороже нашей цены скина)
    used = q1("SELECT COALESCE(SUM(MAX(usd, market_usd)),0) s FROM withdraws WHERE user=? AND stage IN ('0','1','2')", uid)["s"]
    used += sum(f(uid) for f in EXTRA_USED)
    return round(paid * XTR_USD * LIMIT_K, 2), round(used, 2)


def held(uid):
    """Сколько $ лимита ещё «на выдержке» после свежих оплат."""
    fresh = q1("SELECT COALESCE(SUM(xtr),0) s FROM payments WHERE user=? AND ts>?", uid, now() - int(HOLD_H * 3600))["s"]
    return round(fresh * XTR_USD * LIMIT_K, 2)


GAP = 0.35            # пауза между запросами к площадке: за 5 и больше запросов в секунду она удаляет ключ
_LOCK = asyncio.Lock()
_LAST = [0.0]


async def _market(method, **params):
    """Запрос к площадке. Все запросы идут строго по одному и не чаще раза в GAP секунд — и от игроков, и от проверки этапов."""
    async with _LOCK:
        wait = _LAST[0] + GAP - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            r = await A.http.get(MARKET + method, params=params, headers={"X-API-KEY": KEY}, timeout=30)
        finally:
            _LAST[0] = time.monotonic()
    try:   # отказ площадка тоже отдаёт как JSON; если пришло что-то другое (страница шлюза) — ответа нет
        out = r.json()
    except Exception:
        return None
    return out if isinstance(out, dict) else None


_SAID = {}


def _alert(key, text, every=1800):
    """Сообщение админам, не чаще раза в every секунд на одну тему."""
    if now() - _SAID.get(key, 0) < every:
        return
    _SAID[key] = now()
    for aid in A.ADMINS:
        notify(aid, "🛠 " + text)


def _restore(w):
    """Вернуть скин игроку (заявка сорвалась). Внутри tx()."""
    g = json.loads(w["gift"])
    g.pop("id", None)
    cols = ",".join(g)
    db.execute(f"INSERT INTO gifts({cols}) VALUES({','.join('?' * len(g))})", tuple(g.values()))


def _row(w):
    text = w["error"] or ("Обмен отправлен — прими его в Steam" if w["stage"] == "1" and w["offer"] else STAGE.get(w["stage"], "В работе"))
    return {"id": w["id"], "col": w["col"], "usd": w["usd"], "stage": w["stage"], "text": text, "ts": w["ts"]}


def state(uid):
    limit, used = budget(uid)
    u = q1("SELECT trade_link FROM users WHERE id=?", uid)
    return {"on": enabled(), "rate": E.USD_COINS, "link": (u["trade_link"] or "") if u else "", "limit": limit, "used": used, "left": round(max(0, limit - used), 2),
            "held": held(uid), "holdHours": HOLD_H,
            "items": [_row(w) for w in q("SELECT * FROM withdraws WHERE user=? ORDER BY ts DESC LIMIT 30", uid)]}


@app.get(R + "/withdraw")
def withdraw_state(uid=Depends(auth)):
    return state(uid)


@app.post(R + "/withdraw/link")
async def withdraw_link(req: Request, uid=Depends(auth)):
    link = str((await req.json()).get("link", "")).strip()
    if not LINK_RE.match(link):
        err("Это не трейд-ссылка Steam. Она выглядит так: https://steamcommunity.com/tradeoffer/new/?partner=…&token=…")
    with tx():
        db.execute("UPDATE users SET trade_link=? WHERE id=?", (link, uid))
    return state(uid)


@app.post(R + "/withdraw/{gid}")
async def withdraw(gid: int, uid=Depends(auth)):
    if not enabled():
        err("Вывод скинов пока не включён")
    with tx():   # забираем скин из сумки сразу: пока идёт покупка, его нельзя продать или вывести второй раз
        g = A.own_gift(gid, uid)
        if g["src"] != "cs" or g["col"] not in E.PWR["cols"]:
            err("Вывести можно только скины CS")
        if g["price"] is not None or A.in_open_trade(gid):
            err("Сначала сними скин с продажи или обмена")
        m = LINK_RE.match(q1("SELECT trade_link FROM users WHERE id=?", uid)["trade_link"] or "")
        if not m:
            err("Сначала сохрани трейд-ссылку Steam")
        usd = gift_usd(g)
        limit, used = budget(uid)
        if not limit:
            err(f"Свежее пополнение станет доступно для вывода через {HOLD_H} ч после оплаты" if held(uid) else "Вывод открывается после первой покупки звёзд")
        if used + usd > limit + 1e-9:
            err(f"Лимит вывода: осталось ${max(0, limit - used):.2f}, а скин стоит ${usd:.2f}. Лимит растёт с покупками")
        wid = secrets.token_hex(16)
        mh = E.PWR["cols"][g["col"]]["mh"]
        db.execute("DELETE FROM gifts WHERE id=?", (gid,))
        A.unpin(uid, gid)
        A.cancel_trades_with(gid)
        db.execute("INSERT INTO withdraws(id,user,gift,col,hash,usd,market_usd,stage,error,causer,ts,upd) VALUES(?,?,?,?,?,?,0,'0','','',?,?)",
                   (wid, uid, json.dumps(dict(g), ensure_ascii=False), g["col"], mh, usd, now(), now()))

    def fail(text, log=""):
        with tx():
            w = q1("SELECT * FROM withdraws WHERE id=? AND stage='0'", wid)
            if w:
                _restore(w)
                db.execute("UPDATE withdraws SET stage='x', error=?, causer=?, upd=? WHERE id=?", (text, log[:200], now(), wid))
        err(text)

    try:
        found = await _market("search-item-by-hash-name", hash_name=mh)
    except Exception as e:
        fail("Площадка не отвечает — попробуй позже", type(e).__name__)
    cur = str((found or {}).get("currency") or "USD").upper()
    try:
        unit = await _units(cur)   # единиц цены площадки в одном долларе
    except Exception:
        unit = 0.0
    if not unit:
        _alert("cur", "Вывод скинов остановлен: не удалось получить курс рубля." if cur == "RUB" else
               f"Вывод скинов остановлен: аккаунт площадки в валюте {A.esc(cur)}, игра умеет работать с USD и RUB.")
        fail("Вывод скинов временно недоступен — попробуй позже", f"currency {cur}")
    items = [x for x in (found or {}).get("data") or [] if int(x.get("count", 1) or 0) > 0 and x.get("price")]
    if not items:
        fail("Этого скина сейчас нет на площадке — попробуй позже", "no item")
    price = min(int(x["price"]) for x in items)   # в единицах площадки; список она не обязана отдавать по возрастанию
    cost = round(price / unit, 3)                 # то же в долларах
    if cost > usd * PRICE_CAP:
        fail("Скин подорожал на площадке — вывести его сейчас нельзя. Продай его игре за полную цену или попробуй позже", f"market {cost} > {usd}×{PRICE_CAP}")
    if cost > usd and used + cost > limit + 1e-9:
        fail(f"На площадке скин сейчас стоит ${cost:.2f} — это больше остатка лимита ${max(0, limit - used):.2f}", "limit by market price")
    try:
        order = await _market("buy-for", hash_name=mh, price=price, partner=m.group(1), token=m.group(2), chance_to_transfer=40, custom_id=wid)
    except Exception:
        order = None
    if order is None:   # ответа нет — не знаем, прошла ли покупка: скин не возвращаем, заявка ждёт проверки этапа
        with tx():
            db.execute("UPDATE withdraws SET market_usd=?, upd=? WHERE id=?", (cost, now(), wid))
        return state(uid)
    if not order.get("success") or order.get("error"):
        code = order.get("code")
        why = str(order.get("error") or code or "no order")
        if code not in CODES or code == 20:   # не про аккаунт игрока: баланс площадки, ключ, сбой — это видит только админ
            _alert("buy", f"Площадка отказала в покупке скина {A.esc(mh)}: {A.esc(why[:200])}")
        fail(CODES.get(code, "Не удалось отправить скин — попробуй позже"), why)
    with tx():
        db.execute("UPDATE withdraws SET stage='1', market_usd=?, upd=? WHERE id=?", (cost, now(), wid))
    return state(uid)


def _paid(d, w):
    """Сколько реально списала площадка (она покупает самый дешёвый лот не дороже нашей цены). В долларах."""
    try:
        paid = float(d.get("paid") or 0)
    except (TypeError, ValueError):
        return w["market_usd"]
    k = {"USD": 1.0, "RUB": _rate()}.get(str(d.get("currency") or "USD").upper(), 0)   # paid — в валюте аккаунта, не в единицах цены
    return round(paid / k, 3) if paid > 0 and k else w["market_usd"]


async def check_once():
    """Этапы заявок. В работе — раз в минуту: 2 — получен, 5 — возврат скина. Переданные — раз в RECHECK, пока обмен можно откатить."""
    rows = q("SELECT * FROM withdraws WHERE (stage='1' AND upd<?) OR (stage='0' AND ts<?) OR (stage='2' AND settle>? AND upd<?)",
             now() - CHECK_EVERY + 5, now() - 300, now(), now() - RECHECK)
    for w in rows:
        try:
            r = await _market("get-buy-info-by-custom-id", custom_id=w["id"])
        except Exception:
            continue
        if r is None:
            continue
        d = r.get("data") or {}
        stage = str(d.get("stage") or "")
        col = A.esc(w["col"])
        with tx():
            live = q1("SELECT * FROM withdraws WHERE id=?", w["id"])
            if not live or live["stage"] != w["stage"]:
                continue
            if not stage:   # площадка заявку не знает
                miss = (w["miss"] or 0) + 1
                if w["stage"] == "0" and miss >= 3:   # покупка не подтверждалась и за три проверки не нашлась — её не было
                    _restore(w)
                    db.execute("UPDATE withdraws SET stage='x', error='Заявка не дошла до площадки — скин возвращён', upd=? WHERE id=?", (now(), w["id"]))
                else:   # покупку площадка подтверждала (этап 1 и 2): сами скин не возвращаем, иначе игрок получит его дважды
                    db.execute("UPDATE withdraws SET miss=?, upd=? WHERE id=?", (miss, now(), w["id"]))
                    if w["stage"] == "1" and miss == 30:
                        _alert("lost" + w["id"], f"Заявка на вывод {w['id'][:8]} ({col}): площадка приняла покупку, но полчаса не отдаёт её статус. Проверь в кабинете площадки.")
            elif stage == "1" and w["stage"] != "2":
                offer = str(d.get("trade_id") or "")
                db.execute("UPDATE withdraws SET stage='1', miss=0, market_usd=?, offer=?, upd=? WHERE id=?", (_paid(d, w), offer or w["offer"], now(), w["id"]))
                if offer and not w["offer"]:
                    notify(w["user"], f"📦 Обмен со скином <b>{col}</b> отправлен тебе в Steam. Прими его в Steam: «Предложения обмена». Если не принять, скин вернётся в сумку.")
            elif stage == "2":
                if w["stage"] != "2":
                    try:
                        settle = int(float(d.get("settlement") or 0))
                    except (TypeError, ValueError):
                        settle = 0
                    settle = (settle if settle > now() else now() + 8 * 86400) + 86400
                    db.execute("UPDATE withdraws SET stage='2', miss=0, market_usd=?, settle=?, upd=? WHERE id=?", (_paid(d, w), settle, now(), w["id"]))
                    notify(w["user"], f"✅ Скин <b>{col}</b> у тебя в инвентаре Steam.")
                else:
                    db.execute("UPDATE withdraws SET miss=0, upd=? WHERE id=?", (now(), w["id"]))
            elif stage in ("5", "6"):
                why = str(d.get("cancellation_reason") or d.get("causer") or "")
                _restore(w)
                if w["stage"] == "2":   # обмен откатили в Steam уже после передачи
                    db.execute("UPDATE withdraws SET stage='5', error='Обмен отменён в Steam — скин возвращён', causer=?, upd=? WHERE id=?", (why, now(), w["id"]))
                    notify(w["user"], f"↩️ Обмен со скином <b>{col}</b> отменён в Steam — скин снова в сумке.")
                    _alert("rb" + w["id"], f"Откат обмена после передачи: {col}, заявка {w['id'][:8]}, причина {A.esc(why or '—')}, уплачено ${w['market_usd']:.2f}, "
                                           f"удержания площадки: {A.esc(json.dumps(d.get('refund') or {}, ensure_ascii=False)[:300])}")
                else:
                    db.execute("UPDATE withdraws SET stage=?, causer=?, upd=? WHERE id=?", (stage, why, now(), w["id"]))
                    notify(w["user"], f"↩️ Скин <b>{col}</b> не удалось передать в Steam — он снова в сумке. Проверь трейд-ссылку и попробуй ещё раз.")
            else:
                db.execute("UPDATE withdraws SET upd=? WHERE id=?", (now(), w["id"]))


async def balance_check():
    """Раз в час: хватает ли денег на площадке и не сменилась ли валюта аккаунта."""
    r = await _market("get-money")
    if not r or not r.get("success"):
        return
    cur = str(r.get("currency") or "").upper()
    money = float(r.get("money") or 0)
    k = 1.0 if cur == "USD" else await _rub_rate() if cur == "RUB" else 0
    if cur not in ("USD", "RUB"):
        _alert("cur", f"Вывод скинов остановлен: аккаунт площадки в валюте {A.esc(cur)}, игра умеет работать с USD и RUB.", 12 * 3600)
    elif not k:
        _alert("cur", "Вывод скинов остановлен: не удалось получить курс рубля.", 3 * 3600)
    elif money / k < LOW_USD:
        have = f"{money:.0f} ₽ (≈ ${money / k:.2f})" if cur == "RUB" else f"${money:.2f}"
        _alert("low", f"На площадке скинов осталось {have}. Пополни баланс market.csgo.com, иначе выводы скинов начнут срываться.", 12 * 3600)


async def loop():
    while True:
        await asyncio.sleep(CHECK_EVERY)
        if not enabled():
            continue
        try:
            await check_once()
            if now() - _SAID.get("bal_ts", 0) >= 3600:
                _SAID["bal_ts"] = now()
                await balance_check()
        except Exception as e:
            print("withdraw loop:", type(e).__name__, e, flush=True)


@app.on_event("startup")
async def _start():
    asyncio.create_task(loop())
