"""Кредиты банка. Условия зависят от кредитного рейтинга (0–1000, старт 300): лимит, ставка и доступные сроки.
- без залога: с 5 уровня, один за раз; не вернул — долг и штраф списываются с баланса, даже в минус;
- под залог подарка: не вернул — подарок переходит банку и выставляется на маркет;
- под залог бизнеса: часть дохода при сборе сама идёт в погашение; не вернул — бизнес забирает банк.
Рейтинг растёт за возврат в срок (кредит не меньше заметной суммы и дольше 6 часов, иначе рейтинг легко накрутить),
просрочка его снижает, на 48 часов закрывает новые кредиты и ограничивает ставки."""
from settings import conf
import asyncio
import math

from fastapi import Depends

from fastapi import Request

import app as A
from app import (R, app, auth, bal, cancel_trades_with, db, err, esc, event, gift_out, in_open_trade, level, notify, now, own_gift,
                 q, q1, tx, unpin)

LOAN_OWNER = 2 * 10 ** 10  # подарок в залоге: owner = -(LOAN_OWNER + uid); выше диапазона сейфа (-(2e9 + uid), uid до ~1e10)
LTV = conf("loans.ltv", 0.5)                  # даём 50% ценности
MAX_LOANS = 3
MIN_VALUE = 100
WARN = 12 * 3600           # напомнить за 12 часов до срока
CASH_LEVEL = 5
# рейтинг от, название, ставка на 3 дня, лимит без залога, доступные сроки
TIERS = [(0, "Низкий", 0.15, 5_000, (1,)), (300, "Начальный", 0.15, 10_000, (1, 3)), (400, "Средний", 0.12, 50_000, (1, 3)),
         (550, "Хороший", 0.10, 200_000, (1, 3, 7)), (700, "Отличный", 0.07, 500_000, (1, 3, 7)), (850, "Высший", 0.05, 1_000_000, (1, 3, 7))]
TERM_K = {1: 0.7, 3: 1.0, 7: 1.5}             # короткий кредит дешевле, длинный дороже
FEE_MIN = 0.03
FEE = conf("loans.fee", 0.15)                  # базовая ставка (начальный рейтинг, 3 дня), меняется в админке; остальные считаются от неё
FEE_BASE = 0.15                                # ставка начального рейтинга в таблице TIERS
SCORE_START = 300
SCORE_OK = conf("loans.score_ok", 40)          # за возврат в срок
SCORE_LOST = conf("loans.score_lost", 150)     # за просрочку
OK_HOLD = 6 * 3600                             # быстрый возврат рейтинг не поднимает
BANK_SHARE = conf("loans.bank_share", 0.05)    # без залога одному игроку — не больше этой доли банка
BIZ_LTV = conf("loans.biz_ltv", 0.8)           # под бизнес: доля цены продажи, чтобы взять и не вернуть было хуже, чем продать
AUTO_SHARE = conf("loans.auto_share", 0.3)     # часть собранного дохода, которая сама гасит кредит под бизнес
LOST_FEE = conf("loans.lost_fee", 0.05)        # штраф за просрочку кредита без залога
PENALTY = conf("loans.penalty_hours", 48) * 3600
PENALTY_BET = conf("loans.penalty_bet", 10_000)


def stars_locked(uid):
    """Пока есть кредит без залога или баланс в минусе — звёзды другим игрокам отдавать нельзя (против фарма с твинков)."""
    return bal(uid) < 0 or bool(q1("SELECT 1 FROM loans WHERE user=? AND status='open' AND gift IS NULL AND biz IS NULL", uid))

db.executescript("""
CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY, user INTEGER, gift INTEGER, principal INTEGER, debt INTEGER, ts INTEGER,
  until INTEGER, status TEXT DEFAULT 'open', closed INTEGER, warned INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS loans_user ON loans(user, status);
""")
try:   # paid — сколько уже внесено частями; осталось вернуть debt - paid
    db.execute("ALTER TABLE loans ADD COLUMN paid INTEGER DEFAULT 0")
except Exception:
    pass
try:   # залог-бизнес: id бизнеса
    db.execute("ALTER TABLE loans ADD COLUMN biz TEXT")
except Exception:
    pass
db.execute("CREATE TABLE IF NOT EXISTS credit(user INTEGER PRIMARY KEY, score INTEGER DEFAULT 300, ok INTEGER DEFAULT 0, lost INTEGER DEFAULT 0, penalty INTEGER DEFAULT 0)")
PART_MIN = 100   # частичный взнос — не меньше (или весь остаток)


def credit_of(uid):
    r = q1("SELECT * FROM credit WHERE user=?", uid)
    return {"score": r["score"], "ok": r["ok"], "lost": r["lost"], "penalty": r["penalty"]} if r else {"score": SCORE_START, "ok": 0, "lost": 0, "penalty": 0}


def tier_of(score):
    return next(t for t in reversed(TIERS) if score >= t[0])


def tier_fee(tier_rate, days=3):
    return max(FEE_MIN, round(tier_rate * FEE / FEE_BASE * TERM_K[days], 4))


def fee_for(uid, days):
    return tier_fee(tier_of(credit_of(uid)["score"])[2], days)


def _days(uid, days):
    allowed = tier_of(credit_of(uid)["score"])[4]
    try:
        days = int(days)
    except (TypeError, ValueError):
        err("выбери срок")
    if days not in allowed:
        err("с твоим рейтингом доступны сроки: " + ", ".join(map(str, allowed)) + " дн.")
    return days


def _no_penalty(uid):
    p = credit_of(uid)["penalty"] - now()
    if p > 0:
        err(f"после просрочки новый кредит можно взять через {p // 3600 + 1} ч")


def _score(uid, delta, ok=0, lost=0, penalty=0):
    db.execute("""INSERT INTO credit(user,score,ok,lost,penalty) VALUES(?,?,?,?,?) ON CONFLICT(user) DO UPDATE SET
                  score=MAX(0,MIN(1000,score+?)), ok=ok+excluded.ok, lost=lost+excluded.lost, penalty=MAX(penalty,excluded.penalty)""",
               (uid, max(0, min(1000, SCORE_START + delta)), ok, lost, penalty, delta))


def ok_min(uid):
    """От какой суммы возврат поднимает рейтинг."""
    return max(1000, int(cash_limit(uid) * 0.1))


def _on_repaid(r):
    """Закрыт в срок: рейтинг растёт, если кредит был настоящим, а не взят на минуту ради рейтинга."""
    big = r["principal"] >= ok_min(r["user"])
    up = SCORE_OK if big and now() - r["ts"] >= OK_HOLD else 0
    _score(r["user"], up, ok=1)
    return up


def biz_pledged(uid, bid):
    return bool(q1("SELECT 1 FROM loans WHERE user=? AND biz=? AND status='open'", uid, bid))


def auto_pay(uid, income):
    """Внутри tx сбора дохода: часть дохода гасит кредиты под бизнес, сначала с ближайшим сроком. Возвращает внесённое."""
    budget, total = int(income * AUTO_SHARE), 0
    for r in q("SELECT * FROM loans WHERE user=? AND status='open' AND biz IS NOT NULL ORDER BY until", uid):
        left = r["debt"] - (r["paid"] or 0)
        amount = min(budget, left)
        if amount <= 0:
            break
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        _pay_events(uid, r, amount)
        if amount == left:
            db.execute("UPDATE loans SET status='repaid', closed=?, paid=debt WHERE id=?", (now(), r["id"]))
            _on_repaid(r)
        else:
            db.execute("UPDATE loans SET paid=COALESCE(paid,0)+? WHERE id=?", (amount, r["id"]))
        budget -= amount
        total += amount
    return total


def _pay_events(uid, r, amount):
    """Взнос в счёт кредита: сначала гасится тело, потом комиссия (так журнал/прибыль банка сходятся при любом дроблении)."""
    paid = r["paid"] or 0
    body = max(0, min(amount, r["principal"] - paid))
    if body:
        event(uid, "loan", -body)
    if amount - body:
        event(uid, "fee", -(amount - body))
# переезд со старого кодирования -(3e9 + uid), которое могло совпасть с сейфом другого игрока
db.execute(f"UPDATE gifts SET owner=-({LOAN_OWNER}+(SELECT user FROM loans l WHERE l.gift=gifts.id AND l.status='open')) "
           "WHERE id IN (SELECT gift FROM loans WHERE status='open' AND gift IS NOT NULL)")


def cash_limit(uid):
    """Лимит кредита без залога: по рейтингу, но не больше доли банка."""
    import bank
    return min(tier_of(credit_of(uid)["score"])[3], max(0, int(bank.bank_value() * BANK_SHARE)))


def terms(value, fee):
    principal = int(value * LTV)
    return principal, math.ceil(principal * (1 + fee))


def _biz_terms(bid, level):
    from income import biz_sell_price
    return int(biz_sell_price(bid, level) * BIZ_LTV)


def loan_out(r):
    g = q1("SELECT * FROM gifts WHERE id=?", r["gift"]) if r["gift"] else None
    biz = None
    if r["biz"]:
        from income import BIZ_MAP
        b = BIZ_MAP.get(r["biz"])
        biz = {"id": r["biz"], "name": b[1], "col": b[2]} if b else {"id": r["biz"], "name": r["biz"], "col": ""}
    return {"id": r["id"], "gift": gift_out(g) if g else None, "biz": biz, "principal": r["principal"], "debt": r["debt"] - (r["paid"] or 0),
            "total": r["debt"], "paid": r["paid"] or 0, "partMin": PART_MIN,
            "ts": r["ts"], "until": r["until"], "status": r["status"]}


@app.get(R + "/loans")
def loans(uid=Depends(auth)):
    from income import BIZ_MAP
    c, t = credit_of(uid), now()
    tr = tier_of(c["score"])
    nxt = next((x for x in TIERS if x[0] > c["score"]), None)
    pledged = {r["biz"] for r in q("SELECT biz FROM loans WHERE user=? AND status='open' AND biz IS NOT NULL", uid)}
    items = [{"id": r["bid"], "name": BIZ_MAP[r["bid"]][1], "col": BIZ_MAP[r["bid"]][2], "level": r["level"], "got": _biz_terms(r["bid"], r["level"])}
             for r in q("SELECT bid, level FROM biz WHERE user=?", uid) if r["bid"] in BIZ_MAP and r["bid"] not in pledged]
    items.sort(key=lambda x: -x["got"])
    return {"loans": [loan_out(r) for r in q("SELECT * FROM loans WHERE user=? AND status='open' ORDER BY until", uid)],
            "ltv": LTV, "fee": fee_for(uid, 3 if 3 in tr[4] else tr[4][0]), "max": MAX_LOANS, "now": t, "cashMax": cash_limit(uid), "cashLevel": CASH_LEVEL, "stars": bal(uid),
            "credit": {"score": c["score"], "tier": tr[1], "ok": c["ok"], "lost": c["lost"], "penalty": max(0, c["penalty"] - t), "penaltyBet": PENALTY_BET,
                       "gain": SCORE_OK, "okMin": ok_min(uid), "drop": SCORE_LOST, "lostFee": LOST_FEE,
                       "next": {"at": nxt[0], "tier": nxt[1], "fee": tier_fee(nxt[2]), "limit": nxt[3]} if nxt else None},
            "terms": [{"days": d, "fee": fee_for(uid, d)} for d in tr[4]],
            "ladder": [{"at": x[0], "tier": x[1], "limit": x[3], "fee": tier_fee(x[2]), "on": c["score"] >= x[0], "cur": x is tr} for x in TIERS],
            "bizLtv": BIZ_LTV, "autoShare": AUTO_SHARE, "bizItems": items}


def _open_count(uid):
    if q1("SELECT COUNT(*) n FROM loans WHERE user=? AND status='open'", uid)["n"] >= MAX_LOANS:
        err(f"не больше {MAX_LOANS} кредитов сразу")


@app.post(R + "/loans/cash")
async def take_cash(req: Request, uid=Depends(auth)):
    b = await req.json()
    amount = int(b.get("amount", 0))
    t = now()
    with tx():
        _no_penalty(uid)
        days = _days(uid, b.get("days", 3))
        lim = cash_limit(uid)
        if not 100 <= amount <= lim:
            err(f"сейчас можно до ⭐ {lim:,}".replace(",", " ") + " — возврат в срок поднимает рейтинг и лимит")
        u = q1("SELECT xp, stars FROM users WHERE id=?", uid)
        if level(u["xp"]) < CASH_LEVEL:
            err(f"кредит без залога — с {CASH_LEVEL} уровня")
        if u["stars"] < 0:
            err("сначала закрой минус на балансе")
        if q1("SELECT 1 FROM loans WHERE user=? AND status IN ('open') AND gift IS NULL AND biz IS NULL", uid):
            err("кредит без залога можно брать только один")
        _open_count(uid)
        debt = math.ceil(amount * (1 + fee_for(uid, days)))
        until = t + days * 86400
        cur = db.execute("INSERT INTO loans(user,gift,principal,debt,ts,until) VALUES(?,NULL,?,?,?,?)", (uid, amount, debt, t, until))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, uid))
        event(uid, "loan", amount)
    return {"ok": True, "id": cur.lastrowid, "got": amount, "debt": debt, "until": until, "stars": bal(uid)}


@app.post(R + "/loans/biz")
async def take_biz(req: Request, uid=Depends(auth)):
    from income import BIZ_MAP
    b = await req.json()
    bid = str(b.get("bid", ""))
    t = now()
    with tx():
        _no_penalty(uid)
        days = _days(uid, b.get("days", 3))
        r = q1("SELECT * FROM biz WHERE user=? AND bid=?", uid, bid)
        if not r or bid not in BIZ_MAP:
            err("этот бизнес уже не твой")
        if biz_pledged(uid, bid):
            err("этот бизнес уже в залоге")
        _open_count(uid)
        principal = _biz_terms(bid, r["level"])
        if principal < MIN_VALUE:
            err(f"под этот бизнес банк даст меньше ⭐ {MIN_VALUE}")
        debt = math.ceil(principal * (1 + fee_for(uid, days)))
        until = t + days * 86400
        cur = db.execute("INSERT INTO loans(user,gift,biz,principal,debt,ts,until) VALUES(?,NULL,?,?,?,?,?)", (uid, bid, principal, debt, t, until))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (principal, uid))
        event(uid, "loan", principal)
    return {"ok": True, "id": cur.lastrowid, "got": principal, "debt": debt, "until": until, "stars": bal(uid)}


@app.post(R + "/gift/{gid}/loan")
async def take_loan(gid: int, req: Request, uid=Depends(auth)):
    try:
        b = await req.json()
    except Exception:
        b = {}
    t = now()
    with tx():
        _no_penalty(uid)
        days = _days(uid, (b or {}).get("days", 3))
        g = own_gift(gid, uid)
        if g["price"] is not None:
            err("сначала сними подарок с маркета")
        if in_open_trade(gid):
            err("подарок участвует в обмене")
        if g["value"] < MIN_VALUE:
            err(f"в залог берём подарки от ⭐ {MIN_VALUE}")
        _open_count(uid)
        principal, debt = terms(g["value"], fee_for(uid, days))
        until = t + days * 86400
        db.execute("UPDATE gifts SET owner=? WHERE id=?", (-(LOAN_OWNER + uid), gid))
        unpin(uid, gid)
        cancel_trades_with(gid)
        cur = db.execute("INSERT INTO loans(user,gift,principal,debt,ts,until) VALUES(?,?,?,?,?,?)", (uid, gid, principal, debt, t, until))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (principal, uid))
        event(uid, "loan", principal)
    return {"ok": True, "id": cur.lastrowid, "got": principal, "debt": debt, "until": until, "stars": bal(uid)}


@app.post(R + "/loans/{lid}/repay")
async def repay(lid: int, req: Request, uid=Depends(auth)):
    """Вернуть кредит целиком или частью: {amount} — взнос; без amount или ≥ остатка — закрыть полностью."""
    try:
        b = await req.json()
    except Exception:
        b = {}
    amount = (b or {}).get("amount") if isinstance(b, dict) else None
    with tx():
        r = q1("SELECT * FROM loans WHERE id=? AND user=? AND status='open'", lid, uid) or err("кредит уже закрыт")
        left = r["debt"] - (r["paid"] or 0)
        if amount is None:
            amount = left
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            err("введи сумму")
        amount = min(amount, left)
        if amount < min(PART_MIN, left):
            err(f"взнос — от ⭐ {PART_MIN}")
        if bal(uid) < amount:
            err(f"Нужно ⭐ {amount}")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        _pay_events(uid, r, amount)
        closed = amount == left
        rating = 0
        if closed:
            if r["gift"]:
                db.execute("UPDATE gifts SET owner=? WHERE id=?", (uid, r["gift"]))
            db.execute("UPDATE loans SET status='repaid', closed=?, paid=debt WHERE id=?", (now(), lid))
            rating = _on_repaid(r)
        else:
            db.execute("UPDATE loans SET paid=COALESCE(paid,0)+? WHERE id=?", (amount, lid))
    return {"ok": True, "stars": bal(uid), "closed": closed, "paid": amount, "left": left - amount, "gift": bool(r["gift"]), "biz": bool(r["biz"]), "rating": rating}


def _sweep():
    """Просрочка → подарок банку на маркет; напоминание за 12 ч."""
    t, msgs = now(), []
    with tx():
        for r in q("SELECT * FROM loans WHERE status='open' AND until<=?", t):
            db.execute("UPDATE loans SET status='lost', closed=? WHERE id=?", (t, r["id"]))
            left = r["debt"] - (r["paid"] or 0)
            _score(r["user"], -SCORE_LOST, lost=1, penalty=t + PENALTY)
            tail = f" Рейтинг −{SCORE_LOST}. {PENALTY // 3600} ч без новых кредитов, ставки до ⭐ {PENALTY_BET:,}.".replace(",", " ")
            if r["biz"]:   # банк забирает бизнес; товар в пути и внесённое возвращаем, чтобы платить частями не было хуже, чем не платить
                from income import BIZ_MAP
                row = q1("SELECT batch_cost FROM biz WHERE user=? AND bid=?", r["user"], r["biz"])
                back = (r["paid"] or 0) + (row["batch_cost"] or 0 if row else 0)
                if r["paid"]:
                    back_fee = max(0, r["paid"] - r["principal"])
                    event(r["user"], "loan", r["paid"] - back_fee)
                    if back_fee:
                        event(r["user"], "fee", back_fee)
                if row and row["batch_cost"]:
                    event(r["user"], "bizgoods", row["batch_cost"])
                if back:
                    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (back, r["user"]))
                db.execute("DELETE FROM biz WHERE user=? AND bid=?", (r["user"], r["biz"]))
                db.execute("DELETE FROM biz_mgr WHERE user=? AND bid=?", (r["user"], r["biz"]))
                name = BIZ_MAP[r["biz"]][1] if r["biz"] in BIZ_MAP else r["biz"]
                msgs.append((r["user"], f"Срок кредита истёк — банк забрал бизнес <b>{esc(name)}</b>." + (f" ⭐ {back} вернули на баланс." if back else "") + tail))
                continue
            if not r["gift"]:   # без залога — списываем остаток долга и штраф с баланса, хоть в минус
                fine = math.ceil(left * LOST_FEE)
                db.execute("UPDATE users SET stars=stars-? WHERE id=?", (left + fine, r["user"]))
                _pay_events(r["user"], r, left)
                event(r["user"], "fee", -fine)
                msgs.append((r["user"], f"Срок кредита истёк — ⭐ {left} и штраф ⭐ {fine} списаны с баланса. Если звёзд не хватило, баланс ушёл в минус: "
                                        "доход и выигрыши сначала закроют долг." + tail))
                continue
            g = q1("SELECT * FROM gifts WHERE id=?", r["gift"])
            if r["paid"]:   # подарок забирает банк — внесённое частями возвращаем, иначе платить частями было бы хуже, чем не платить
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (r["paid"], r["user"]))
                back_fee = max(0, r["paid"] - r["principal"])
                event(r["user"], "loan", r["paid"] - back_fee)
                if back_fee:
                    event(r["user"], "fee", back_fee)
            if g:
                db.execute("UPDATE gifts SET owner=0, price=?, listed=? WHERE id=?", (max(10, g["value"]), t, g["id"]))
                msgs.append((r["user"], f"Срок кредита истёк — <b>{esc(g['col'])} #{g['num']}</b> перешёл банку игры и выставлен на маркет."
                                        + (f" Внесённые частями ⭐ {r['paid']} вернули на баланс." if r["paid"] else "") + tail))
        for r in q("SELECT * FROM loans WHERE status='open' AND warned=0 AND until-?<=?", t, WARN):
            db.execute("UPDATE loans SET warned=1 WHERE id=?", (r["id"],))
            msgs.append((r["user"], f"Через {max(1, (r['until'] - t) // 3600)} ч истекает кредит: верни ⭐ {r['debt'] - (r['paid'] or 0)}, иначе "
                                    + ("подарок заберёт банк." if r["gift"] else "банк заберёт бизнес." if r["biz"] else "долг и штраф спишутся с баланса, даже в минус.")))
    for uid, text in msgs:
        notify(uid, text)


def bet_cap(uid):
    """После просрочки ставки ограничены."""
    return PENALTY_BET if credit_of(uid)["penalty"] > now() else None


A.LOAN_BET_CAP = bet_cap


async def loans_loop():
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _sweep)
        except Exception as e:
            print("loans:", e, flush=True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _loans_start():
    asyncio.create_task(loans_loop())
