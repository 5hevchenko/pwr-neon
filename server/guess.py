"""«Угадай дроп» на тир-кейсах: три разных подарка из кейса, один из них — настоящий дроп (каждый с шансом 1/3).
Игрок платит цену кейса и выбирает подарок. Угадал — забирает все три, не угадал — ничего.
Средний выигрыш = (1/3) × сумма трёх = один обычный дроп, поэтому возврат равен возврату самого кейса при любом выборе."""
import json

from fastapi import Depends, Request

import economy as E
import app as A
import fair
from app import R, app, auth, bal, case_price, db, err, event, gift_out, now, preview_out, q1, tx

db.execute("CREATE TABLE IF NOT EXISTS guess_rounds(user INTEGER PRIMARY KEY, cid TEXT, price INTEGER, drops TEXT, correct INTEGER, pf TEXT, ts INTEGER)")


def _cases():
    return [c for c in E.CASES.values() if c.get("src") == "ru" and c["price"]]


def _view(r):
    drops = json.loads(r["drops"])
    return {"active": True, "cid": r["cid"], "price": r["price"], "choices": [preview_out(d["col"], d) for d in drops]}


@app.get(R + "/guess")
def guess_state(uid=Depends(auth)):
    r = q1("SELECT * FROM guess_rounds WHERE user=?", uid)
    return {"cases": [{"id": c["id"], "name": c["title"], "price": case_price(c)} for c in sorted(_cases(), key=lambda c: c["price"])],
            "round": _view(r) if r else None, "stars": bal(uid)}


@app.post(R + "/guess/start")
async def guess_start(req: Request, uid=Depends(auth)):
    cid = str((await req.json()).get("cid", ""))
    c = E.CASES.get(cid)
    if not c or c.get("src") != "ru" or not c["price"]:
        err("Выбери тир-кейс")
    with tx():
        r = q1("SELECT * FROM guess_rounds WHERE user=?", uid)
        if r:   # незаконченный раунд: сначала выбери подарок
            return {**_view(r), "stars": bal(uid)}
        price = case_price(c)
        if A.SELF_GUARD:
            A.SELF_GUARD(uid, price)
        if q1("SELECT stars FROM users WHERE id=?", uid)["stars"] < price:
            err("Не хватает звёзд")
        rng = fair.stream(uid, "case", "guess:" + cid)
        drops, seen = [], set()
        for _ in range(200):
            d = E.ru_open(cid, rng)
            k = (d["col"], d["model"], d["backdrop"], d["symbol"])
            if k not in seen:
                seen.add(k)
                drops.append(d)
                if len(drops) == 3:
                    break
        if len(drops) < 3:
            err("В этом кейсе слишком мало подарков")
        correct = rng.randint(0, 2)
        pf = fair.close_stream(rng)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (price, uid))
        db.execute("INSERT INTO guess_rounds(user,cid,price,drops,correct,pf,ts) VALUES(?,?,?,?,?,?,?)",
                   (uid, cid, price, json.dumps(drops, ensure_ascii=False), correct, json.dumps(pf), now()))
        r = q1("SELECT * FROM guess_rounds WHERE user=?", uid)
    return {**_view(r), "stars": bal(uid)}


@app.post(R + "/guess/pick")
async def guess_pick(req: Request, uid=Depends(auth)):
    pick = int((await req.json()).get("i", -1))
    if pick not in (0, 1, 2):
        err("Выбери один из трёх подарков")
    with tx():
        r = q1("SELECT * FROM guess_rounds WHERE user=?", uid) or err("Раунд не начат")
        drops, correct, price = json.loads(r["drops"]), r["correct"], r["price"]
        win = pick == correct
        gifts, pay = [], 0
        if win:
            for d in drops:
                cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created,src) VALUES(?,?,?,?,?,?,?,?,'ru')",
                                 (uid, d["col"], d["model"], d["backdrop"], d["symbol"], d["num"], d["value"], now()))
                gifts.append(gift_out(q1("SELECT * FROM gifts WHERE id=?", cur.lastrowid)))
                pay += d["value"]
        event(uid, "case", pay - price, stake=price)
        fair.record(uid, "case", price, pay, {"case": r["cid"], "guess": pick, "drop": correct, "drops": [d["value"] for d in drops]}, json.loads(r["pf"]))
        db.execute("DELETE FROM guess_rounds WHERE user=?", (uid,))
        lvl = A.add_xp(uid, max(20, price // 10))
    return {"active": False, "win": win, "correct": correct, "pick": pick, "pay": pay, "gifts": gifts,
            "choices": [preview_out(d["col"], d) for d in drops], "stars": bal(uid), "levelup": lvl}
