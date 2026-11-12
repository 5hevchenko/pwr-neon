"""«Огоньки» как в TikTok: серия дней между двумя друзьями.
Каждый день (по Москве) оба отправляют друг другу огонёк → серия +1. Пропустили день — серия сгорает.
Отправить огонёк можно, только сыграв сегодня хотя бы раунд (иначе это ферма на твинках).
Тип огонька растёт с длиной серии; на вехах обоим — звёзды (маленькие, фиксированные)."""
import asyncio

from fastapi import Depends

from app import GAME_KINDS, R, app, auth, db, err, esc, event, notify, now, q, q1, tx, user_brief

TZ = 3 * 3600                        # день считаем по Москве
MILESTONES = {3: 300, 7: 1000, 14: 2000, 30: 5000, 50: 8000, 100: 20000, 200: 30000, 365: 50000}
TIERS = [(100, "blue", "Синее пламя"), (30, "violet", "Фиолетовое пламя"), (7, "red", "Пламя"), (3, "orange", "Огонёк"), (1, "spark", "Искра")]

db.executescript("""
CREATE TABLE IF NOT EXISTS sparks(a INTEGER, b INTEGER, count INTEGER DEFAULT 0, best INTEGER DEFAULT 0, last INTEGER DEFAULT 0,
  a_day INTEGER DEFAULT 0, b_day INTEGER DEFAULT 0, r_day INTEGER DEFAULT 0, PRIMARY KEY(a, b));
""")


def day():
    return (now() + TZ) // 86400


def day_ts(d):
    return d * 86400 - TZ


def tier(n):
    return next(((k, t) for m, k, t in TIERS if n >= m), (None, None))


def _pair(u, f):
    return (u, f) if u < f else (f, u)


def _state(r, uid, d):
    """Серия глазами игрока uid (жива, если последний общий день — сегодня или вчера)."""
    a_side = r["a"] == uid
    alive = r["last"] >= d - 1
    n = r["count"] if alive else 0
    mine, theirs = (r["a_day"], r["b_day"]) if a_side else (r["b_day"], r["a_day"])
    k, t = tier(n)
    return {"count": n, "best": r["best"], "done": r["last"] == d, "mine": mine == d, "theirs": theirs == d,
            "risk": alive and n > 0 and r["last"] == d - 1, "tier": k, "tierName": t,
            "next": next((m for m in sorted(MILESTONES) if m > n), None)}


def sparks_waiting(uid):
    """Сколько друзей уже прислали огонёк сегодня и ждут ответа."""
    d = day()
    return q1("""SELECT COUNT(*) n FROM sparks WHERE (a=? AND b_day=? AND a_day<>?) OR (b=? AND a_day=? AND b_day<>?)""",
              uid, d, d, uid, d, d)["n"]


def _friends(uid):
    return [r["b"] if r["a"] == uid else r["a"] for r in q("SELECT a, b FROM friends WHERE (a=? OR b=?) AND status='ok'", uid, uid)]


@app.get(R + "/sparks")
def sparks(uid=Depends(auth)):
    d, out = day(), []
    for f in _friends(uid):
        a, b = _pair(uid, f)
        r = q1("SELECT * FROM sparks WHERE a=? AND b=?", a, b)
        st = _state(r, uid, d) if r else {"count": 0, "best": 0, "done": False, "mine": False, "theirs": False, "risk": False, "tier": None, "tierName": None, "next": 3}
        u = q1("SELECT * FROM users WHERE id=?", f)
        if u:
            out.append({**st, "user": user_brief(u)})
    out.sort(key=lambda x: (not (x["theirs"] and not x["mine"]), not x["risk"], -x["count"]))
    played = bool(q1(f"SELECT 1 FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=? LIMIT 1", uid, day_ts(d)))
    return {"items": out, "played": played, "milestones": MILESTONES, "endsIn": day_ts(d + 1) - now()}


@app.post(R + "/sparks/{fid}")
def spark_send(fid: int, uid=Depends(auth)):
    d = day()
    if fid == uid or not q1("SELECT 1 FROM friends WHERE ((a=? AND b=?) OR (a=? AND b=?)) AND status='ok'", uid, fid, fid, uid):
        err("огоньки можно отправлять только друзьям")
    if not q1(f"SELECT 1 FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=? LIMIT 1", uid, day_ts(d)):
        err("Сначала сыграй сегодня хотя бы один раунд — потом можно отправить огонёк")
    a, b = _pair(uid, fid)
    msgs, reward = [], 0
    with tx():
        db.execute("INSERT OR IGNORE INTO sparks(a,b) VALUES(?,?)", (a, b))
        r = q1("SELECT * FROM sparks WHERE a=? AND b=?", a, b)
        col = "a_day" if uid == a else "b_day"
        if r[col] == d:
            err("Сегодня огонёк этому другу уже отправлен")
        db.execute(f"UPDATE sparks SET {col}=? WHERE a=? AND b=?", (d, a, b))
        other_day = r["b_day"] if uid == a else r["a_day"]
        me = q1("SELECT * FROM users WHERE id=?", uid)
        if other_day == d and r["last"] != d:     # оба отправили — день засчитан
            n = r["count"] + 1 if r["last"] == d - 1 else 1
            db.execute("UPDATE sparks SET count=?, best=MAX(best, ?), last=? WHERE a=? AND b=?", (n, n, d, a, b))
            reward = MILESTONES.get(n, 0)
            if reward:
                for x in (a, b):
                    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (reward, x))
                    event(x, "sparks", reward)
            k, t = tier(n)
            msgs.append((fid, f"🔥 Серия с <b>{esc(me['name'])}</b>: {n} {'день' if n % 10 == 1 and n % 100 != 11 else 'дня' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'дней'}!"
                              + (f" Награда +{reward:,} ⭐ каждому".replace(",", " ") if reward else "")))
        else:
            n = r["count"] if r["last"] >= d - 1 else 0
            msgs.append((fid, f"🔥 Огонёк от <b>{esc(me['name'])}</b>" + (f": серия {n} — ответь, чтобы не сгорела!" if n else ": ответь, и начнётся ваша серия!")))
        st = _state(q1("SELECT * FROM sparks WHERE a=? AND b=?", a, b), uid, d)
    for u, t in msgs:
        notify(u, t)
    return {**st, "reward": reward}


def _remind():
    """Вечером (19–21 по Москве) напоминаем о сериях, которые сгорят в полночь — раз в день."""
    t = now() + TZ
    if not 19 <= (t % 86400) // 3600 < 22:
        return
    d = day()
    for r in q("SELECT * FROM sparks WHERE last=? AND count>=2 AND r_day<>?", d - 1, d):
        with tx():
            db.execute("UPDATE sparks SET r_day=? WHERE a=? AND b=?", (d, r["a"], r["b"]))
        for me_, other, my_day in ((r["a"], r["b"], r["a_day"]), (r["b"], r["a"], r["b_day"])):
            if my_day == d:
                continue
            o = q1("SELECT name FROM users WHERE id=?", other)
            if o:
                notify(me_, f"⏳ Серия огоньков с <b>{esc(o['name'])}</b> ({r['count']} дн.) сгорит в полночь — отправь огонёк!")


async def sparks_loop():
    await asyncio.sleep(90)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _remind)
        except Exception as e:
            print("sparks:", e, flush=True)
        await asyncio.sleep(1200)


@app.on_event("startup")
async def _sparks_start():
    asyncio.create_task(sparks_loop())
