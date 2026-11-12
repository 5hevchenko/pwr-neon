"""Пополнение криптой через Crypto Pay (@CryptoBot): игрок платит USDT или TON, получает игровые звёзды.

Зачем: с покупки за Telegram Stars до нас доходит около 68% денег игрока (комиссии магазинов приложений и Telegram),
с крипты — около 97% (комиссия Crypto Pay 3%). Поэтому за доллар криптой даём больше звёзд (crypto.stars_per_usd) —
наша выручка на одну игровую звезду при этом такая же, как с Telegram Stars.
  · счёт создаёт сервер (createInvoice, сумма в долларах, платить можно любой из crypto.assets);
  · оплату подтверждает только Crypto Pay: раз в 20 секунд сервер спрашивает статусы своих открытых счетов (getInvoices);
    настраивать вебхук не нужно. Каждый счёт начисляется один раз;
  · платёж пишется в общую таблицу payments (kind='crypto') в пересчёте на Telegram Stars — лимиты вывода, бонусы пакетов,
    «×2 первая покупка» и доля пригласившему работают так же, как при оплате Stars.
Ключ — переменная окружения CRYPTOPAY_TOKEN (выдаёт @CryptoBot → Crypto Pay → Create App). Без ключа раздел скрыт.
Продажа включается тем же переключателем, что и пакеты звёзд (админка → «Продажи»)."""
import asyncio
import os

from fastapi import Depends, Request

import app as A
import shop
from app import R, app, auth, bal, db, err, event, notify, now, q, q1, tx
from settings import conf

TOKEN = os.environ.get("CRYPTOPAY_TOKEN", "").strip()
API = os.environ.get("CRYPTOPAY_URL", "https://pay.crypt.bot/api/")     # CRYPTOPAY_URL — только для тестов
ON = conf("crypto.on", True)
PER_USD = conf("crypto.stars_per_usd", 74000)      # базовых игровых звёзд за $1 (до бонуса пакета)
PACKS = conf("crypto.packs", [1.0, 5.0, 10.0, 25.0, 50.0, 100.0])
MIN_USD, MAX_USD = conf("crypto.min_usd", 1.0), conf("crypto.max_usd", 500.0)
ASSETS = conf("crypto.assets", "USDT,TON")
TTL = 3600                                          # счёт живёт час

db.execute("CREATE TABLE IF NOT EXISTS crypto_invoices(id INTEGER PRIMARY KEY, user INTEGER, usd REAL, status TEXT, url TEXT, ts INTEGER)")


def enabled():
    return bool(ON and TOKEN)


def xtr_eq(usd):
    """Сумма в долларах в пересчёте на Telegram Stars по курсу магазина: так крипта попадает в общие лимиты и бонусы."""
    return max(1, round(usd * PER_USD / shop.RATE))


async def _call(method, **params):
    r = await A.http.post(API + method, json=params, headers={"Crypto-Pay-API-Token": TOKEN}, timeout=30)
    d = r.json()
    if not d.get("ok"):
        raise RuntimeError(str(d.get("error"))[:200])
    return d["result"]


def _state(uid):
    first = shop.is_first(uid)
    return {"on": enabled() and shop.shop_on(), "first": first, "perUsd": PER_USD, "min": MIN_USD, "max": MAX_USD, "rate": shop.RATE,
            "bonus": {str(k): int(v * 100) for k, v in shop.BONUS.items()}, "firstCap": shop.FIRST_CAP,
            "packs": [{"usd": u, "stars": shop.pack_stars(xtr_eq(u), first), "base": shop.pack_stars(xtr_eq(u)), "bonus": int(shop.pack_bonus(xtr_eq(u)) * 100)}
                      for u in PACKS], "stars": bal(uid)}


@app.get(R + "/cpay")
def crypto_state(uid=Depends(auth)):
    return _state(uid)


@app.post(R + "/cpay/invoice")
async def crypto_invoice(req: Request, uid=Depends(auth)):
    if not (enabled() and shop.shop_on()):
        err("Пополнение криптой сейчас недоступно")
    try:
        usd = round(float((await req.json()).get("usd") or 0), 2)
    except (TypeError, ValueError):
        usd = 0
    if not MIN_USD <= usd <= MAX_USD:
        err(f"Сумма от ${MIN_USD:g} до ${MAX_USD:g}")
    if q1("SELECT COUNT(*) n FROM crypto_invoices WHERE user=? AND status='active' AND ts>?", uid, now() - 600)["n"] >= 5:
        err("Слишком много неоплаченных счетов — оплати один из них или подожди 10 минут")
    stars = shop.pack_stars(xtr_eq(usd), shop.is_first(uid))
    try:
        inv = await _call("createInvoice", currency_type="fiat", fiat="USD", amount=f"{usd:.2f}", accepted_assets=ASSETS,
                          description=f"{stars:,} игровых звёзд".replace(",", " "), payload=str(uid), expires_in=TTL, allow_comments=False)
    except Exception as e:
        print("cryptopay createInvoice:", type(e).__name__, e, flush=True)
        err("Не удалось создать счёт — попробуй позже")
    url = inv.get("mini_app_invoice_url") or inv.get("bot_invoice_url") or inv.get("pay_url") or ""
    with tx():
        db.execute("INSERT OR REPLACE INTO crypto_invoices(id,user,usd,status,url,ts) VALUES(?,?,?,'active',?,?)", (int(inv["invoice_id"]), uid, usd, url, now()))
    return {"id": int(inv["invoice_id"]), "url": url, "stars": stars}


def _credit(row, inv):
    """Начислить звёзды по оплаченному счёту — ровно один раз."""
    charge = f"cp{row['id']}"
    uid = row["user"]
    try:   # сумму берём из ответа Crypto Pay и не больше той, на которую выставляли счёт
        usd = min(row["usd"], float(inv.get("amount") or 0)) if inv.get("fiat") == "USD" else 0
    except (TypeError, ValueError):
        usd = 0
    with tx():
        if q1("SELECT 1 FROM payments WHERE charge=?", charge):
            db.execute("UPDATE crypto_invoices SET status='paid' WHERE id=?", (row["id"],))
            return
        if usd < MIN_USD:
            db.execute("UPDATE crypto_invoices SET status='bad' WHERE id=?", (row["id"],))
            print("cryptopay: счёт", row["id"], "оплачен, но сумма не сошлась:", inv.get("amount"), inv.get("fiat"), flush=True)
            return
        first = shop.is_first(uid)
        x = xtr_eq(usd)
        stars = shop.pack_stars(x, first)
        db.execute("INSERT INTO payments(charge,user,xtr,stars,ts,kind) VALUES(?,?,?,?,?,'crypto')", (charge, uid, x, stars, now()))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (stars, uid))
        db.execute("UPDATE crypto_invoices SET status='paid' WHERE id=?", (row["id"],))
        event(uid, "buy", stars)
        __import__("bank").back(stars)
    notify(uid, (f"✅ Оплата криптой прошла: +{stars:,} ⭐ на баланс" + (" — первая покупка, звёзд вдвое больше!" if first else "") + " Спасибо!").replace(",", " "))
    try:
        __import__("refs").on_buy(uid, stars)
    except Exception as e:
        print("refs on_buy", e, flush=True)


async def check(rows):
    """Спросить у Crypto Pay статусы счетов и начислить оплаченные."""
    if not rows:
        return
    res = await _call("getInvoices", invoice_ids=",".join(str(r["id"]) for r in rows), count=len(rows))
    got = {int(i["invoice_id"]): i for i in (res.get("items") if isinstance(res, dict) else res) or []}
    for r in rows:
        inv = got.get(r["id"])
        if inv and inv.get("status") == "paid":
            _credit(r, inv)
        elif (inv and inv.get("status") == "expired") or now() - r["ts"] > TTL + 600:
            with tx():
                db.execute("UPDATE crypto_invoices SET status='expired' WHERE id=? AND status='active'", (r["id"],))


@app.post(R + "/cpay/check")
async def crypto_check(req: Request, uid=Depends(auth)):
    """Клиент ждёт оплату: проверяем его счёт сразу, не дожидаясь общего обхода."""
    iid = int((await req.json()).get("id") or 0)
    row = q1("SELECT * FROM crypto_invoices WHERE id=? AND user=?", iid, uid) or err("Счёт не найден")
    if row["status"] == "active" and enabled():
        try:
            await check([row])
        except Exception as e:
            print("cryptopay check:", type(e).__name__, e, flush=True)
        row = q1("SELECT * FROM crypto_invoices WHERE id=?", iid)
    return {"status": row["status"], **_state(uid)}


async def loop():
    while True:
        await asyncio.sleep(20)
        if not enabled():
            continue
        try:
            rows = q("SELECT * FROM crypto_invoices WHERE status='active' ORDER BY ts DESC LIMIT 100")
            await check(rows)
        except Exception as e:
            print("cryptopay loop:", type(e).__name__, e, flush=True)


@app.on_event("startup")
async def _start():
    asyncio.create_task(loop())
