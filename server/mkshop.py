"""Маркет-мейкер казино: «Витрина» (12 конкретных подарков на продаже, обновляется каждые 6 ч, цена = ценность +10%)
и «Скупка» (4 заказа казино на коллекции по 100–110% ценности — выгоднее мгновенной продажи за 85%).
Деньги с витрины идут в банк казино, скупку оплачивает банк (вид события mkbank входит в BANK_KINDS)."""
import random
import time

from fastapi import Depends, Request

import economy as E
from app import (R, app, auth, bal, cancel_trades_with, db, err, event, gift_out, in_open_trade, now, q, q1, tx, unpin)

EPOCH = 6 * 3600
SHOP_MARKUP = 1.10
TIERS = [(4, 0, 2_000), (4, 2_000, 20_000), (3, 20_000, 150_000), (1, 150_000, 10 ** 9)]   # сколько лотов, диапазон базы коллекции

db.executescript("""
CREATE TABLE IF NOT EXISTS mk_shop(id INTEGER PRIMARY KEY, epoch INTEGER, col TEXT, model TEXT, backdrop TEXT, symbol TEXT,
  num INTEGER, value INTEGER, price INTEGER, buyer INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS mk_shop_epoch ON mk_shop(epoch);
CREATE TABLE IF NOT EXISTS mk_orders(id INTEGER PRIMARY KEY, epoch INTEGER, col TEXT, pct REAL, qty INTEGER, filled INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS mk_orders_epoch ON mk_orders(epoch);
""")


def epoch():
    t = int(time.time())
    return t - t % EPOCH


def _gen(ep):
    """Витрина и заказы на новую эпоху (внутри tx, один раз)."""
    if q1("SELECT 1 FROM mk_shop WHERE epoch=?", ep):
        return
    cols = list(E.CATALOG)
    for n, lo, hi in TIERS:
        pool = [c for c in cols if lo <= E.base(c) < hi] or cols
        for c in random.sample(pool, min(n, len(pool))):
            g = max((E.roll(c) for _ in range(3)), key=lambda d: d["value"])   # из трёх бросков — лучший: на витрине поредкие
            db.execute("INSERT INTO mk_shop(epoch,col,model,backdrop,symbol,num,value,price,ts) VALUES(?,?,?,?,?,?,?,?,?)",
                       (ep, g["col"], g["model"], g["backdrop"], g["symbol"], g["num"], g["value"], int(g["value"] * SHOP_MARKUP), now()))
    # скупка: половина — из того, что реально есть у игроков (чтобы было кому продать), половина — случайные
    owned = [r["col"] for r in q("SELECT col, COUNT(*) n FROM gifts WHERE owner>0 AND price IS NULL GROUP BY col ORDER BY n DESC LIMIT 20")]
    picks = random.sample(owned, min(2, len(owned))) + random.sample(cols, 4)
    seen = []
    for c in picks:
        if c not in seen and len(seen) < 4:
            seen.append(c)
            db.execute("INSERT INTO mk_orders(epoch,col,pct,qty) VALUES(?,?,?,?)", (ep, c, random.choice((1.0, 1.05, 1.1)), random.choice((2, 3, 5))))


def _look(r):
    from app import LOOK, BACKDROPS
    ml, bl, sl = LOOK[r["col"]]
    bd = bl.get(r["backdrop"]) or BACKDROPS.get(r["backdrop"])
    return {"id": r["id"], "col": r["col"], "model": r["model"], "backdrop": r["backdrop"], "symbol": r["symbol"], "num": r["num"],
            "value": r["value"], "price": r["price"], "mp": ml.get(r["model"], 0), "bp": bd[1], "sp": sl.get(r["symbol"], 0), "c": bd[2:6],
            "sold": bool(r["buyer"])}


@app.get(R + "/mkshop")
def mkshop(uid=Depends(auth)):
    ep = epoch()
    with tx():
        _gen(ep)
    shop = [_look(r) for r in q("SELECT * FROM mk_shop WHERE epoch=? ORDER BY value DESC", ep)]
    orders = []
    for o in q("SELECT * FROM mk_orders WHERE epoch=?", ep):
        mine = q("SELECT * FROM gifts WHERE owner=? AND col=? AND price IS NULL ORDER BY value DESC", uid, o["col"])
        orders.append({"id": o["id"], "col": o["col"], "pct": o["pct"], "qty": o["qty"], "filled": o["filled"], "base": E.base(o["col"]),
                       "mine": [gift_out(g) for g in mine[:12]]})
    return {"shop": shop, "orders": orders, "refresh": ep + EPOCH, "now": now(), "markup": SHOP_MARKUP}


@app.post(R + "/mkshop/{lid}/buy")
def mkshop_buy(lid: int, uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM mk_shop WHERE id=?", lid) or err("лот не найден")
        if r["epoch"] != epoch():
            err("витрина обновилась — посмотри новые лоты")
        if r["buyer"]:
            err("уже купили — загляни в другие лоты")
        if bal(uid) < r["price"]:
            err("Не хватает звёзд")
        db.execute("UPDATE mk_shop SET buyer=? WHERE id=?", (uid, lid))
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (r["price"], uid))
        cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                         (uid, r["col"], r["model"], r["backdrop"], r["symbol"], r["num"], r["value"], now()))
        event(uid, "mkbank", -r["price"])
        g = gift_out(q1("SELECT * FROM gifts WHERE id=?", cur.lastrowid))
    return {"ok": True, "gift": g, "stars": bal(uid)}


@app.post(R + "/mkorders/{oid}/sell")
async def mkorder_sell(oid: int, req: Request, uid=Depends(auth)):
    gid = int((await req.json()).get("gid", 0))
    with tx():
        o = q1("SELECT * FROM mk_orders WHERE id=?", oid) or err("заказ не найден")
        if o["epoch"] != epoch():
            err("заказы обновились — посмотри новые")
        if o["filled"] >= o["qty"]:
            err("банк уже набрал нужное количество")
        g = q1("SELECT * FROM gifts WHERE id=?", gid)
        if not g or g["owner"] != uid:
            err("это не твой подарок")
        if g["col"] != o["col"]:
            err("банк покупает только эту коллекцию")
        if g["price"] is not None:
            err("сначала сними подарок с маркета")
        if in_open_trade(gid):
            err("подарок участвует в обмене")
        pay = int(g["value"] * o["pct"])
        db.execute("DELETE FROM gifts WHERE id=?", (gid,))
        unpin(uid, gid)
        cancel_trades_with(gid)
        db.execute("UPDATE mk_orders SET filled=filled+1 WHERE id=?", (oid,))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
        event(uid, "mkbank", pay)
    return {"ok": True, "pay": pay, "stars": bal(uid)}
