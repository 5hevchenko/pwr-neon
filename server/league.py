"""Лиги недели (как в Duolingo): игроки одной лиги делятся на группы до 30 человек и соревнуются неделю.
Очки — как в сезоне: оборот в играх с потолком 10 000 с одной ставки / 100 (богач не забирает всё одной ставкой).
В группу игрок попадает, как только сыграл на этой неделе. В понедельник (00:00 UTC) итоги: топ-3 группы — звёзды
(больше в старших лигах), верхние поднимаются на лигу выше, нижние опускаются. Кто не играл неделю — остаётся где был."""
import asyncio

from fastapi import Depends

from app import GAME_KINDS, R, app, auth, db, esc, event, kv_get, notify, now, q, q1, qr, tx, user_brief, week_start
from settings import conf

TIERS = ["Бронза", "Серебро", "Золото", "Платина", "Алмаз", "Легенда"]
GROUP = 30
CAP = 10_000
WEEK = 7 * 86400
PRIZES = conf("league.prizes", [1_500, 3_000, 6_000, 12_000, 25_000, 50_000])   # 1 место по лигам; 2-е — 60%, 3-е — 40%
SHARE = [1, 0.6, 0.4]

db.executescript("""
CREATE TABLE IF NOT EXISTS league_user(user INTEGER PRIMARY KEY, tier INTEGER DEFAULT 0, best INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS league_grp(week INTEGER, gid INTEGER, tier INTEGER, n INTEGER DEFAULT 0, PRIMARY KEY(week, gid));
CREATE TABLE IF NOT EXISTS league_mem(week INTEGER, user INTEGER, gid INTEGER, ts INTEGER, PRIMARY KEY(week, user));
CREATE INDEX IF NOT EXISTS league_mem_g ON league_mem(week, gid);
CREATE TABLE IF NOT EXISTS league_res(week INTEGER, user INTEGER, tier INTEGER, newtier INTEGER, place INTEGER, size INTEGER,
  pts INTEGER, reward INTEGER, seen INTEGER DEFAULT 0, PRIMARY KEY(week, user));
""")


def zones(n, tier):
    """Сколько поднимается и опускается в группе из n игроков."""
    up = 0 if tier >= len(TIERS) - 1 else min(5, max(1, n // 4)) if n >= 2 else 0
    down = 0 if tier == 0 else min(5, n // 4) if n >= 6 else 0
    return up, down


def prizes(tier):
    import app as A
    return [A.prize_k(PRIZES[tier] * s) for s in SHARE]


def tier_of(uid):
    r = q1("SELECT tier FROM league_user WHERE user=?", uid)
    return r["tier"] if r else 0


def _join(uid, ws):
    """Поставить игрока в группу его лиги на эту неделю (вызывать внутри tx)."""
    if q1("SELECT 1 FROM league_mem WHERE week=? AND user=?", ws, uid):
        return
    t = tier_of(uid)
    g = q1("SELECT gid FROM league_grp WHERE week=? AND tier=? AND n<? ORDER BY gid LIMIT 1", ws, t, GROUP)
    if g:
        gid = g["gid"]
    else:
        gid = (q1("SELECT MAX(gid) m FROM league_grp WHERE week=?", ws)["m"] or 0) + 1
        db.execute("INSERT INTO league_grp(week,gid,tier,n) VALUES(?,?,?,0)", (ws, gid, t))
    db.execute("UPDATE league_grp SET n=n+1 WHERE week=? AND gid=?", (ws, gid))
    db.execute("INSERT INTO league_mem(week,user,gid,ts) VALUES(?,?,?,?)", (ws, uid, gid, now()))
    db.execute("INSERT OR IGNORE INTO league_user(user,tier) VALUES(?,0)", (uid,))


def _assign():
    """Всех, кто играл на этой неделе и ещё не в группе, — по группам (в порядке первой игры)."""
    ws = week_start()
    rows = q(f"""SELECT user, MIN(ts) t FROM events WHERE kind IN {GAME_KINDS} AND ts>=?
                 AND user NOT IN (SELECT user FROM league_mem WHERE week=?) GROUP BY user ORDER BY t""", ws, ws)
    if not rows:
        return
    import app as A
    with tx():
        for r in rows:
            if r["user"] not in A.BANNED:
                _join(r["user"], ws)


def standings(ws, gid):
    """Участники группы с очками, по местам (равные очки — кто раньше вошёл)."""
    mem = q("SELECT user, ts FROM league_mem WHERE week=? AND gid=?", ws, gid)
    if not mem:
        return []
    ids = [m["user"] for m in mem]
    ph = ",".join("?" * len(ids))
    pts = {r["user"]: r["p"] for r in qr(f"""SELECT user, SUM(MIN(ABS(delta), {CAP})) / 100 p FROM events
                                           WHERE kind IN {GAME_KINDS} AND ts>=? AND ts<? AND user IN ({ph}) GROUP BY user""", max(ws, __import__("app").season_from()), ws + WEEK, *ids)}
    out = [{"user": m["user"], "pts": int(pts.get(m["user"], 0)), "ts": m["ts"]} for m in mem]
    out.sort(key=lambda x: (-x["pts"], x["ts"]))
    return out


def _settle():
    """Итоги прошлой недели (идемпотентно: kv league_done = неделя, которую уже подвели)."""
    pw = week_start() - WEEK
    if int(kv_get("league_done", "0") or 0) >= pw:
        return
    msgs = []
    with tx():
        if int(kv_get("league_done", "0") or 0) >= pw:
            return
        for g in q("SELECT * FROM league_grp WHERE week=?", pw):
            st, t = standings(pw, g["gid"]), g["tier"]
            n = len(st)
            up, down = zones(n, t)
            pr = prizes(t)
            for i, r in enumerate(st):
                place, uid = i + 1, r["user"]
                nt = t + 1 if place <= up else t - 1 if down and place > n - down else t
                reward = pr[i] if i < 3 and r["pts"] > 0 else 0
                if reward:
                    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (reward, uid))
                    event(uid, "league", reward)
                db.execute("INSERT INTO league_user(user,tier,best) VALUES(?,?,?) ON CONFLICT(user) DO UPDATE SET tier=excluded.tier, best=MAX(best, excluded.tier)",
                           (uid, nt, nt))
                db.execute("INSERT OR REPLACE INTO league_res(week,user,tier,newtier,place,size,pts,reward,seen) VALUES(?,?,?,?,?,?,?,?,0)",
                           (pw, uid, t, nt, place, n, r["pts"], reward))
                move = f"Переход в лигу «{TIERS[nt]}»!" if nt > t else f"Вылет в лигу «{TIERS[nt]}»." if nt < t else f"Остаёшься в лиге «{TIERS[t]}»."
                msgs.append((uid, f"🏅 Итоги недели в лиге «{esc(TIERS[t])}»: {place} место из {n}." + (f" Приз ⭐ {reward:,}.".replace(",", " ") if reward else "") + f"\n{move}"))
        db.execute("INSERT INTO kv(k,v) VALUES('league_done',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(pw),))
    for u, t in msgs:
        notify(u, t)


async def league_loop():
    await asyncio.sleep(40)
    while True:
        for f in (_settle, _assign):
            try:
                await asyncio.get_running_loop().run_in_executor(None, f)
            except Exception as e:
                print("league:", f.__name__, e, flush=True)
        await asyncio.sleep(120)


@app.on_event("startup")
async def _league_start():
    asyncio.create_task(league_loop())


@app.get(R + "/league")
def league(uid=Depends(auth)):
    ws = week_start()
    m = q1("SELECT gid FROM league_mem WHERE week=? AND user=?", ws, uid)
    if not m and q1(f"SELECT 1 FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=? LIMIT 1", uid, ws):
        with tx():
            _join(uid, ws)
        m = q1("SELECT gid FROM league_mem WHERE week=? AND user=?", ws, uid)
    t = tier_of(uid)
    last = q1("SELECT * FROM league_res WHERE user=? AND seen=0 ORDER BY week DESC LIMIT 1", uid)
    out = {"tier": t, "tiers": TIERS, "ends": ws + WEEK, "prizes": [prizes(i) for i in range(len(TIERS))],
           "best": (q1("SELECT best FROM league_user WHERE user=?", uid) or {"best": 0})["best"],
           "last": dict(last) if last else None, "joined": bool(m)}
    if m:
        g = q1("SELECT * FROM league_grp WHERE week=? AND gid=?", ws, m["gid"])
        st = standings(ws, m["gid"])
        users = {u["id"]: u for u in (q(f"SELECT * FROM users WHERE id IN ({','.join('?' * len(st))})", *[r["user"] for r in st]) if st else [])}
        up, down = zones(len(st), g["tier"])
        out.update(tier=g["tier"], gid=m["gid"], up=up, down=down,
                   rows=[{**user_brief(users[r["user"]]), "pts": r["pts"]} for r in st if r["user"] in users])
    return out


@app.post(R + "/league/seen")
def league_seen(uid=Depends(auth)):
    with tx():
        db.execute("UPDATE league_res SET seen=1 WHERE user=?", (uid,))
    return {"ok": True}


@app.get(R + "/league/brief")
def league_brief(uid=Depends(auth)):
    """Для плашки в «Топе»: лига и место без списка."""
    ws = week_start()
    m = q1("SELECT gid FROM league_mem WHERE week=? AND user=?", ws, uid)
    if not m:
        return {"tier": tier_of(uid), "place": None, "ends": ws + WEEK}
    st = standings(ws, m["gid"])
    return {"tier": tier_of(uid), "place": next((i + 1 for i, r in enumerate(st) if r["user"] == uid), None), "size": len(st), "ends": ws + WEEK}
