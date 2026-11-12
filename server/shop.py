"""Покупка игровых звёзд за Telegram Stars (валюта XTR): 1 ⭐ Telegram = 1000 игровых.
Счёт создаёт сервер (createInvoiceLink), клиент открывает tg.openInvoice; начисление — только по successful_payment от Telegram,
каждый платёж учитывается один раз (telegram_payment_charge_id)."""
from settings import conf
import json

from fastapi import Depends, Request

from app import R, app, auth, bal, db, err, esc, event, kv_get, notify, now, q1, tg_call, tx

RATE = conf("shop.rate", 1000)                       # игровых звёзд за 1 Telegram Star
PACKS = [1, 10, 50, 100, 250, 500, 1000]   # пакеты в Telegram Stars
CUSTOM_MAX = 10000                        # своя сумма: от 1 до 10 000 Telegram Stars
BONUS = {50: 0.05, 100: 0.10, 250: 0.15, 500: 0.20, 1000: 0.30}   # бонус за пакет (своя сумма — по ближайшему пакету снизу)
FIRST_X = conf("shop.first_bonus", 1.0)          # первая покупка: +100% звёзд…
FIRST_CAP = conf("shop.first_cap", 250_000)    # …но бонус не больше 250 000

db.executescript("""
CREATE TABLE IF NOT EXISTS payments(charge TEXT PRIMARY KEY, user INTEGER, xtr INTEGER, stars INTEGER, ts INTEGER, kind TEXT DEFAULT 'pack');
""")


SALE_KEYS = {"shop": "shop_on", "vip": "vip_on", "chest": "chest_on"}   # переключатели продаж в админке → «Продажи»


def sale_on(what):
    """Продаётся ли сейчас: shop — игровые звёзды, vip — VIP, chest — звёздный сундук. По умолчанию всё выключено."""
    return kv_get(SALE_KEYS[what], "0") == "1"


def shop_on():
    """Продажа игровых звёзд за Telegram Stars (пакеты, подарок другу, «Набор дня»). Владелец включает в админке → «Продажи».
    По умолчанию выключена. VIP и сундук продаются всегда."""
    return sale_on("shop")


def pack_bonus(xtr):
    return max([v for k, v in BONUS.items() if xtr >= k], default=0)


def is_first(uid):
    return not q1("SELECT 1 FROM payments WHERE user=? AND COALESCE(kind,'pack')='pack'", uid)


async def make_invoice(title, desc, payload, xtr):
    r = await tg_call("createInvoiceLink", _token=__import__("franchise").pay_token(), title=title, description=desc, payload=json.dumps(payload), currency="XTR",
                      prices=[{"label": title, "amount": xtr}])
    if not r.get("ok"):
        err("не удалось создать счёт, попробуй позже")
    return r["result"]


def are_friends(a, b):
    return a != b and bool(q1("SELECT 1 FROM friends WHERE ((a=? AND b=?) OR (a=? AND b=?)) AND status='ok'", a, b, b, a))


def pack_stars(xtr, first=False):
    base = int(xtr * RATE * (1 + pack_bonus(xtr)))
    return base + (min(FIRST_CAP, int(xtr * RATE * FIRST_X)) if first else 0)


@app.get(R + "/shop")
def shop(uid=Depends(auth)):
    first = is_first(uid)
    return {"on": shop_on(), "rate": RATE, "max": CUSTOM_MAX, "bonus": {str(k): int(v * 100) for k, v in BONUS.items()},
            "first": first, "firstCap": FIRST_CAP,
            "packs": [{"xtr": x, "stars": pack_stars(x, first), "base": pack_stars(x), "bonus": int(pack_bonus(x) * 100)} for x in PACKS]}


@app.post(R + "/shop/invoice")
async def invoice(req: Request, uid=Depends(auth)):
    body = await req.json()
    xtr, to = int(body.get("xtr", 0)), int(body.get("to") or 0)
    if not shop_on():
        err("Покупка звёзд сейчас недоступна")
    if not 1 <= xtr <= CUSTOM_MAX:
        err(f"от 1 до {CUSTOM_MAX} Telegram Stars")
    if to:   # подарок другу: обычный пакет с бонусом пакета, без «×2 первой покупки»
        if not are_friends(uid, to):
            err("дарить звёзды можно только друзьям")
        f = q1("SELECT name FROM users WHERE id=?", to)
        link = await make_invoice(f"Подарок: {pack_stars(xtr):,} ⭐".replace(",", " "),
                                  f"Игровые звёзды GiftBot в подарок для {f['name'][:40]}. Вывести или обменять на настоящие подарки Telegram нельзя.",
                                  {"u": uid, "x": xtr, "to": to}, xtr)
        return {"link": link}
    first = is_first(uid)
    r = await tg_call("createInvoiceLink", _token=__import__("franchise").pay_token(), title=(f"{pack_stars(xtr, first):,} игровых звёзд".replace(",", " ") + (" (×2 первая покупка)" if first else "")),
                      description="Игровая валюта GiftBot. Вывести или обменять на настоящие подарки Telegram нельзя.",
                      payload=json.dumps({"u": uid, "x": xtr}), currency="XTR", prices=[{"label": "Игровые звёзды", "amount": xtr}])
    if not r.get("ok"):
        err("не удалось создать счёт, попробуй позже")
    return {"link": r["result"]}


async def on_pre_checkout(pq):
    """Telegram спрашивает, можно ли провести оплату — отвечаем за 10 секунд."""
    try:
        p = json.loads(pq.get("invoice_payload") or "{}")
        if p.get("k"):
            import premium
            ok = premium.validate(p, pq.get("total_amount", 0)) and pq.get("currency") == "XTR" and sale_on({"offer": "shop"}.get(p.get("k"), p.get("k")))
        else:
            ok = shop_on() and isinstance(p.get("x"), int) and 1 <= p["x"] <= CUSTOM_MAX and int(pq.get("total_amount", 0)) == p["x"] and pq.get("currency") == "XTR"
            if ok and p.get("to"):
                ok = are_friends(int(p.get("u", 0)), int(p["to"]))
    except Exception:
        ok = False
    await tg_call("answerPreCheckoutQuery", pre_checkout_query_id=pq["id"], ok=ok,
                  **({} if ok else {"error_message": "Пакет устарел или покупка звёзд отключена"}))


def on_paid(m):
    """successful_payment: начислить звёзды ровно один раз."""
    sp = m["successful_payment"]
    charge, xtr = sp["telegram_payment_charge_id"], int(sp["total_amount"])
    uid = m["from"]["id"]
    p = {}
    try:
        p = json.loads(sp.get("invoice_payload") or "{}")
        uid = int(p.get("u", uid))
    except Exception:
        pass
    if not q1("SELECT 1 FROM users WHERE id=?", uid):
        uid = m["from"]["id"]
    if p.get("k"):
        import premium
        return premium.fulfill(uid, p["k"], xtr, charge, p)
    if p.get("to"):
        return gift_paid(uid, int(p["to"]), xtr, charge)
    with tx():
        if q1("SELECT 1 FROM payments WHERE charge=?", charge):
            return
        if not q1("SELECT 1 FROM users WHERE id=?", uid):
            uid = m["from"]["id"]
        first = is_first(uid)
        stars = pack_stars(xtr, first)
        db.execute("INSERT INTO payments(charge,user,xtr,stars,ts,kind) VALUES(?,?,?,?,?,'pack')", (charge, uid, xtr, stars, now()))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (stars, uid))
        event(uid, "buy", stars)
        __import__("bank").back(stars)
    notify(uid, (f"✅ Оплата прошла: +{stars:,} ⭐ на баланс" + (" — первая покупка, звёзд вдвое больше!" if first else "") + " Спасибо!").replace(",", " "))
    try:
        __import__("refs").on_buy(uid, stars)   # пригласившему — % от покупки (refs.py)
    except Exception as e:
        print("refs on_buy", e, flush=True)


def gift_paid(uid, to, xtr, charge):
    """Подарок звёзд другу: платёж числится за покупателем (kind='gift'), звёзды — получателю.
    Деньги уже списаны Telegram, поэтому начисляем, даже если дружбу успели разорвать."""
    with tx():
        if q1("SELECT 1 FROM payments WHERE charge=?", charge):
            return
        if not q1("SELECT 1 FROM users WHERE id=?", to):
            to = uid
        stars = pack_stars(xtr)
        db.execute("INSERT INTO payments(charge,user,xtr,stars,ts,kind) VALUES(?,?,?,?,?,'gift')", (charge, uid, xtr, stars, now()))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (stars, to))
        event(to, "buy_gift", stars)
        __import__("bank").back(stars)
        names = {r["id"]: r["name"] for r in db.execute("SELECT id,name FROM users WHERE id IN (?,?)", (uid, to))}
    if to == uid:
        return notify(uid, f"✅ Оплата прошла: +{stars:,} ⭐ на баланс. Спасибо!".replace(",", " "))
    notify(to, f"🎁 <b>{esc(names.get(uid, 'Друг'))}</b> подарил(а) тебе <b>{stars:,} ⭐</b>!".replace(",", " "))
    notify(uid, f"✅ Подарок отправлен: {esc(names.get(to, 'другу'))} получил(а) {stars:,} ⭐. Спасибо!".replace(",", " "))
