"""Вывод скинов CS в Steam через market.csgo.com — перенос из cs-bot-backend (modules/skin).

Как в оригинале:
  · игрок сохраняет трейд-ссылку Steam (…/tradeoffer/new/?partner=…&token=…);
  · заявка: ищем предмет на площадке по торговому имени (search-item-by-hash-name), берём самую низкую цену (в тысячных доллара:
    аккаунт площадки должен быть в USD, иначе вывод останавливается);
    если она выше нашей цены скина в PRICE_CAP раз (в оригинале ×3) — отказ, скин остаётся у игрока;
  · покупаем предмет сразу на трейд-ссылку игрока (buy-for, chance_to_transfer=40, custom_id — номер заявки);
  · раз в минуту спрашиваем этап (get-buy-info-by-custom-id): 1 — в работе, 2 — передан, 5 и 6 — сорвалось:
    скин возвращается игроку, бот пишет ему об этом.
Добавлено под единую валюту (в оригинале коины были отдельным кошельком и раздавались скупо):
  · вывод открыт только тем, кто покупал за Telegram Stars; сумма выводов в долларах не больше
    оплаченные XTR × xtr_usd × limit_k — бесплатные ⭐ в скины сверх оплаченного не превращаются.
Площадка удаляет ключ за 5 и больше запросов в секунду, поэтому все запросы идут по одному с паузой GAP.
Ключ площадки — переменная окружения MARKET_KEY (в коде и в базе его нет). Без ключа вывод выключен."""
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
PRICE_CAP = conf("withdraw.price_cap", 3.0)      # цена на площадке не выше нашей × это число (как в оригинале)
CHECK_EVERY = int(os.environ.get("MARKET_CHECK", "60"))
LINK_RE = re.compile(r"^https://steamcommunity\.com/tradeoffer/new/?\?partner=(\d+)&token=([A-Za-z0-9_-]+)$")
# коды ошибок buy-for (комментарий в оригинальном market.ts) → что сказать игроку
CODES = {3: "Не удалось проверить трейд-ссылку", 5: "У тебя скрыт инвентарь Steam — открой его в настройках приватности",
         6: "Аккаунт Steam заблокирован", 7: "К аккаунту Steam не привязан мобильный аутентификатор",
         8: "Ссылка не прошла проверку — включи офлайн-обмены в Steam", 12: "Неверная трейд-ссылка",
         21: "Инвентарь Steam переполнен"}
STAGE = {"1": "Покупаем и передаём", "2": "Передан в Steam", "5": "Не удалось — скин возвращён", "6": "Не удалось — скин возвращён"}

db.execute("CREATE TABLE IF NOT EXISTS withdraws(id TEXT PRIMARY KEY, user INTEGER, gift TEXT, col TEXT, hash TEXT, usd REAL, "
           "market_usd REAL, stage TEXT, error TEXT, causer TEXT, ts INTEGER, upd INTEGER)")
db.execute("CREATE INDEX IF NOT EXISTS withdraws_user ON withdraws(user)")
try:
    db.execute("ALTER TABLE users ADD COLUMN trade_link TEXT")
except Exception:
    pass


def enabled():
    return bool(ON and KEY)


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
            r = await A.http.get(MARKET + method, params={"key": KEY, **params}, timeout=30)
        finally:
            _LAST[0] = time.monotonic()
    if r.status_code != 200:
        return None
    return r.json()


def _restore(w):
    """Вернуть скин игроку (заявка сорвалась). Внутри tx()."""
    g = json.loads(w["gift"])
    g.pop("id", None)
    cols = ",".join(g)
    db.execute(f"INSERT INTO gifts({cols}) VALUES({','.join('?' * len(g))})", tuple(g.values()))


def _row(w):
    return {"id": w["id"], "col": w["col"], "usd": w["usd"], "stage": w["stage"], "text": w["error"] or STAGE.get(w["stage"], "В работе"), "ts": w["ts"]}


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
    if cur != "USD":   # цены считаем в тысячных доллара; у аккаунта в рублях или евро единицы другие — покупать нельзя
        for aid in A.ADMINS:
            notify(aid, f"🛠 Вывод скинов остановлен: аккаунт площадки в валюте {A.esc(cur)}, а игра считает в долларах. Переключи валюту аккаунта market.csgo.com на USD.")
        fail("Вывод скинов временно недоступен — попробуй позже", f"currency {cur}")
    items = [x for x in (found or {}).get("data") or [] if int(x.get("count", 1) or 0) > 0 and x.get("price")]
    if not items:
        fail("Этого скина сейчас нет на площадке — попробуй позже", "no item")
    price = min(int(x["price"]) for x in items)   # в тысячных доллара; список площадка не обязана отдавать по возрастанию
    if price / 1000 > usd * PRICE_CAP:
        fail("Скин сейчас слишком дорог на площадке — попробуй позже", f"market {price / 1000} > {usd}×{PRICE_CAP}")
    if price / 1000 > usd and used + price / 1000 > limit + 1e-9:
        fail(f"На площадке скин сейчас стоит ${price / 1000:.2f} — это больше остатка лимита ${max(0, limit - used):.2f}", "limit by market price")
    try:
        order = await _market("buy-for", hash_name=mh, price=price, partner=m.group(1), token=m.group(2), chance_to_transfer=40, custom_id=wid)
    except Exception as e:   # не знаем, принята ли заявка: оставляем в работе — проверка этапа разберётся
        order = {"success": True, "error": "", "_unknown": type(e).__name__}
    if not order or not order.get("success") or order.get("error"):
        code = (order or {}).get("code")
        fail(CODES.get(code, "Не удалось отправить скин — попробуй позже"), str((order or {}).get("error") or code or "no order"))
    with tx():
        db.execute("UPDATE withdraws SET stage='1', market_usd=?, upd=? WHERE id=?", (price / 1000, now(), wid))
    return state(uid)


async def check_once():
    """Этапы заявок в работе: 2 — готово, 5/6 — возврат скина."""
    for w in q("SELECT * FROM withdraws WHERE (stage='1' AND upd<?) OR (stage='0' AND ts<?)", now() - CHECK_EVERY + 5, now() - 300):
        try:
            r = await _market("get-buy-info-by-custom-id", custom_id=w["id"])
        except Exception:
            continue
        d = (r or {}).get("data") or {}
        stage = str(d.get("stage") or "")
        # заявки на площадке нет: «0» — сервер упал до покупки; «1» дольше получаса — покупка не дошла. Скин возвращаем.
        lost = r is not None and not stage and (w["stage"] == "0" or now() - w["ts"] > 1800)
        with tx():
            if lost:
                if q1("SELECT 1 FROM withdraws WHERE id=? AND stage IN ('0','1')", w["id"]):
                    _restore(w)
                    db.execute("UPDATE withdraws SET stage='x', error='Заявка не дошла до площадки — скин возвращён', upd=? WHERE id=?", (now(), w["id"]))
            elif stage == "1" and w["stage"] == "0":
                db.execute("UPDATE withdraws SET stage='1', upd=? WHERE id=?", (now(), w["id"]))
            elif stage == "2":
                db.execute("UPDATE withdraws SET stage='2', causer=?, upd=? WHERE id=? AND stage IN ('0','1')", (str(d.get("causer") or ""), now(), w["id"]))
                notify(w["user"], f"✅ Скин <b>{A.esc(w['col'])}</b> передан в Steam — прими обмен.")
            elif stage in ("5", "6"):
                if q1("SELECT 1 FROM withdraws WHERE id=? AND stage IN ('0','1')", w["id"]):
                    _restore(w)
                    db.execute("UPDATE withdraws SET stage=?, causer=?, upd=? WHERE id=?", (stage, str(d.get("causer") or ""), now(), w["id"]))
                    notify(w["user"], f"↩️ Скин <b>{A.esc(w['col'])}</b> не удалось передать в Steam — он снова в сумке. Проверь трейд-ссылку и попробуй ещё раз.")
            else:
                db.execute("UPDATE withdraws SET upd=? WHERE id=?", (now(), w["id"]))


async def loop():
    while True:
        await asyncio.sleep(CHECK_EVERY)
        if not enabled():
            continue
        try:
            await check_once()
        except Exception as e:
            print("withdraw loop:", type(e).__name__, e, flush=True)


@app.on_event("startup")
async def _start():
    asyncio.create_task(loop())
