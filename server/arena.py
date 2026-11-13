"""Арена: общий раунд на звёзды. Ставка игрока — его сектор на кольце: чем больше ставка, тем шире сектор и выше шанс.
Когда время вышло, по кольцу пускается мяч; чей сектор — тот забирает весь банк (минус комиссия игры).

Раунд ждёт второго игрока; с его ставки идёт обратный отсчёт. Пока игрок в раунде один, ставку можно забрать.
Честность: билет 0..1 берётся из общего сида дня (fair.pub), сектора идут по порядку первой ставки — проверяется во вкладке «Честность»."""
import asyncio

from fastapi import Depends, Request

from app import R, add_xp, app, auth, bal, db, err, event, now, q, q1, tx, user_brief
from settings import S, conf

db.executescript("""
CREATE TABLE IF NOT EXISTS ar_rounds(id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT, deadline REAL, spin_at REAL,
  winner INTEGER, ticket REAL, total INTEGER, paid INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS ar_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, round INTEGER, user INTEGER, amount INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS ar_bets_round ON ar_bets(round);
""")
COUNTDOWN = int(conf("arena.countdown", 30))    # секунд на ставки после входа второго игрока
SPIN = 8                                        # сколько катится мяч
SHOW = 5                                        # сколько показываем победителя до нового раунда
MIN_BET = int(conf("arena.min_bet", 100))       # 0,1 ⭐
MAX_BET = int(conf("arena.max_bet", 5_000_000)) # на игрока за раунд
MAX_PLAYERS = int(conf("arena.max_players", 30))
FEE = conf("arena.fee", 0.05)                   # комиссия игры с банка


def _cur():
    r = q1("SELECT * FROM ar_rounds WHERE status IN ('open','spinning') ORDER BY id DESC LIMIT 1")
    if r:
        return r
    with tx():
        r = q1("SELECT * FROM ar_rounds WHERE status IN ('open','spinning') ORDER BY id DESC LIMIT 1")
        if not r:
            db.execute("INSERT INTO ar_rounds(status, ts) VALUES('open', ?)", (now(),))
            r = q1("SELECT * FROM ar_rounds WHERE status='open' ORDER BY id DESC LIMIT 1")
    return r


def _bets(rid):
    """Ставки раунда по игрокам, в порядке первой ставки — в этом порядке идут сектора по кольцу."""
    return q("SELECT user, SUM(amount) amount FROM ar_bets WHERE round=? GROUP BY user ORDER BY MIN(id)", rid)


def _settle(r):
    bets = _bets(r["id"])
    total = sum(b["amount"] for b in bets)
    import fair
    rng = fair.pub("arena", f"round:{r['id']}")
    ticket = rng.random()
    fair.close_pub(rng, {"ticket": round(ticket, 8), "total": total})
    acc, winner = 0.0, bets[-1]["user"]
    for b in bets:
        acc += b["amount"] / total
        if ticket < acc:
            winner = b["user"]
            break
    paid = int(total * (1 - FEE))
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (paid, winner))
    for b in bets:
        event(b["user"], "arena", (paid if b["user"] == winner else 0) - b["amount"], stake=b["amount"])
        add_xp(b["user"], max(5, b["amount"] // 100))
    db.execute("UPDATE ar_rounds SET status='spinning', winner=?, ticket=?, total=?, paid=?, spin_at=? WHERE id=?", (winner, ticket, total, paid, now(), r["id"]))


def _tick():
    r = _cur()
    t = now()
    if r["status"] == "open":
        players = q1("SELECT COUNT(DISTINCT user) n FROM ar_bets WHERE round=?", r["id"])["n"]
        if players >= 2 and not r["deadline"]:
            with tx():
                db.execute("UPDATE ar_rounds SET deadline=? WHERE id=? AND deadline IS NULL", (t + COUNTDOWN, r["id"]))
        elif players < 2 and r["deadline"]:      # второй игрок забрал ставку — отсчёт снимаем
            with tx():
                db.execute("UPDATE ar_rounds SET deadline=NULL WHERE id=? AND status='open'", (r["id"],))
        elif r["deadline"] and t >= r["deadline"]:
            with tx():
                r = q1("SELECT * FROM ar_rounds WHERE id=?", r["id"])
                if r["status"] == "open":
                    _settle(r)
    elif r["status"] == "spinning" and t >= (r["spin_at"] or t) + SPIN + SHOW:
        with tx():
            db.execute("UPDATE ar_rounds SET status='done' WHERE id=?", (r["id"],))
            db.execute("INSERT INTO ar_rounds(status, ts) VALUES('open', ?)", (t,))


async def _loop():
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _tick)
        except Exception as e:
            print("arena:", type(e).__name__, e, flush=True)
        await asyncio.sleep(1)


@app.on_event("startup")
async def _start():
    asyncio.create_task(_loop())


def _view(r, uid):
    bets = _bets(r["id"])
    total = sum(b["amount"] for b in bets)
    players = []
    for b in bets:
        u = q1("SELECT * FROM users WHERE id=?", b["user"])
        players.append({**user_brief(u), "amount": b["amount"], "chance": round(b["amount"] / total * 100, 2) if total else 0})
    done = r["status"] != "open"
    return {"id": r["id"], "status": r["status"], "deadline": r["deadline"], "spinAt": r["spin_at"], "now": now(), "total": total,
            "players": players, "mine": next((b["amount"] for b in bets if b["user"] == uid), 0),
            "winner": r["winner"] if done else None, "ticket": r["ticket"] if done else None, "paid": r["paid"] if done else None,
            "spin": SPIN, "min": MIN_BET, "max": MAX_BET, "fee": round(FEE * 100, 1), "countdown": COUNTDOWN}


@app.get(R + "/arena")
def arena_get(uid=Depends(auth)):
    r = _cur()
    hist = []
    for h in q("SELECT * FROM ar_rounds WHERE status='done' AND winner IS NOT NULL ORDER BY id DESC LIMIT 8"):
        u = q1("SELECT * FROM users WHERE id=?", h["winner"])
        if not u:
            continue
        mine = q1("SELECT COALESCE(SUM(amount),0) v FROM ar_bets WHERE round=? AND user=?", h["id"], h["winner"])["v"]
        hist.append({**user_brief(u), "paid": h["paid"] or 0, "chance": round(mine / h["total"] * 100, 1) if h["total"] else 0})
    return {**_view(r, uid), "history": hist}


@app.post(R + "/arena/bet")
async def arena_bet(req: Request, uid=Depends(auth)):
    from app import _pvp_guard
    _pvp_guard(uid)
    amount = int((await req.json()).get("amount", 0))
    rid = _cur()["id"]
    with tx():
        r = q1("SELECT * FROM ar_rounds WHERE id=?", rid)
        if r["status"] != "open" or (r["deadline"] and now() > r["deadline"] - 1):
            err("Ставки закрыты — дождись следующего раунда")
        if amount < MIN_BET:
            err(f"Минимальная ставка — {S(MIN_BET)} ⭐")
        mine = q1("SELECT COALESCE(SUM(amount),0) s FROM ar_bets WHERE round=? AND user=?", rid, uid)["s"]
        if mine + amount > MAX_BET:
            err(f"Не больше {S(MAX_BET)} ⭐ на игрока за раунд")
        if not mine and q1("SELECT COUNT(DISTINCT user) n FROM ar_bets WHERE round=?", rid)["n"] >= MAX_PLAYERS:
            err("В этом раунде уже нет мест — дождись следующего")
        if bal(uid) < amount:
            err("Не хватает звёзд")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        db.execute("INSERT INTO ar_bets(round,user,amount,ts) VALUES(?,?,?,?)", (rid, uid, amount, now()))
        r = q1("SELECT * FROM ar_rounds WHERE id=?", rid)
    return {**_view(r, uid), "stars": bal(uid)}


@app.post(R + "/arena/cancel")
def arena_cancel(uid=Depends(auth)):
    """Забрать ставку, пока отсчёт не пошёл (игрок в раунде один)."""
    rid = _cur()["id"]
    with tx():
        r = q1("SELECT * FROM ar_rounds WHERE id=?", rid)
        if r["status"] != "open" or r["deadline"]:
            err("Отсчёт уже идёт — ставку забрать нельзя")
        mine = q1("SELECT COALESCE(SUM(amount),0) s FROM ar_bets WHERE round=? AND user=?", rid, uid)["s"]
        if not mine:
            err("У тебя нет ставки в этом раунде")
        db.execute("DELETE FROM ar_bets WHERE round=? AND user=?", (rid, uid))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (mine, uid))
    return {**_view(q1("SELECT * FROM ar_rounds WHERE id=?", rid), uid), "stars": bal(uid)}
