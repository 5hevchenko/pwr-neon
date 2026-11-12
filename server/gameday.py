"""Игра дня: каждые сутки по Москве одна из самых редких игр получает свой рейтинг.
Выбор автоматический: меньше всего раундов за неделю среди открытых игр, без повторов за 7 дней и без игр текущего турнира.
Очки = сумма исходов раундов с потолком на раунд, поэтому богач не забирает всё одной ставкой, а кэшаут на x1,01 очков не даёт.
Фонд растёт вместе с игрой и составляет 2,5% суммы исходов. При возврате 94% потеря игрока не меньше 3,1% исходов (на больших иксах),
поэтому даже весь фонд, собранный твинками, дешевле самой игры: накрутка убыточна, банк в плюсе."""
import asyncio
import hashlib
import json
import time

from fastapi import Depends

import app as A
from app import R, app, auth, db, esc, event, notify, now, q, q1, tx, user_brief
from settings import conf

db.executescript("""CREATE TABLE IF NOT EXISTS gd_day(day INTEGER PRIMARY KEY, gid TEXT, kind TEXT, title TEXT, done INTEGER DEFAULT 0, result TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS gd_win(user INTEGER PRIMARY KEY, n INTEGER DEFAULT 0);""")

# id карточки → (вид в журнале, название). Только игры против банка: PvP и кейсы сюда не подходят.
GAMES = {"slots": ("slots", "Слоты"), "plinko": ("plinko", "Плинко"), "chicken": ("chicken", "Курица"), "rlt": ("roulette", "Рулетка"), "dice": ("dice", "Кубик"),
         "limbo": ("limbo", "Лимбо"), "tower": ("tower", "Башня"), "scratch": ("scratch", "Скретч-карты"), "pump": ("pump", "Насос"), "drill": ("drill", "Бур"),
         "fish": ("fish", "Рыбалка"), "keno": ("keno", "Кено"), "penalty": ("penalty", "Пенальти"), "darts": ("darts", "Дартс"), "avia": ("avia", "Самолётик"),
         "hilo": ("hilo", "Больше/меньше"), "wheel": ("wheel", "Колесо"), "mines": ("mines", "Мины")}
DAY = 86400
SHIFT = 3 * 3600
CAP = 10_000                                    # потолок исхода одного раунда в очках
POOL_MAX = conf("gameday.pool", 30_000)         # потолок фонда до поправки на курс банка
POOL_PCT = conf("gameday.pool_pct", 0.025)      # фонд от суммы исходов всех игроков
MIN_PTS = conf("gameday.min_pts", 50)           # меньше очков — приза нет (5 000 звёзд исходов)
SHARES = [.5, .3, .2]
_LIVE = {"day": None, "at": 0, "rows": [], "pool": (0, 0)}


def day_no(t=None):
    return ((t if t is not None else now()) + SHIFT) // DAY


def day_start(d):
    return d * DAY - SHIFT


def _pick(d):
    import gates
    import tourn
    st = gates.states()
    t = now()
    busy = set(tourn.games_of(tourn.period_start()))
    recent = {r["gid"] for r in q("SELECT gid FROM gd_day WHERE day>=?", d - 7)}
    pool = [g for g in GAMES if st.get(g, "on") == "on" and g not in busy and g not in recent] or [g for g in GAMES if st.get(g, "on") == "on"] or list(GAMES)
    played = {r["kind"]: r["n"] for r in q("SELECT kind, COUNT(*) n FROM events WHERE ts>=? AND kind IN (" + ",".join("?" * len(GAMES)) + ") GROUP BY kind",
                                           t - 7 * DAY, *[v[0] for v in GAMES.values()])}
    tie = lambda g: hashlib.sha256(f"{d}:{g}".encode()).hexdigest()   # при равенстве выбор не зависит от порядка в коде
    return min(pool, key=lambda g: (played.get(GAMES[g][0], 0), tie(g)))


def today():
    d = day_no()
    r = q1("SELECT * FROM gd_day WHERE day=?", d)
    if r:
        return r
    g = _pick(d)
    with tx():
        db.execute("INSERT OR IGNORE INTO gd_day(day,gid,kind,title,ts) VALUES(?,?,?,?,?)", (d, g, GAMES[g][0], GAMES[g][1], now()))
    return q1("SELECT * FROM gd_day WHERE day=?", d)


def _scores(kind, d, limit=None):
    a = max(day_start(d), A.season_from())
    sql = f"""SELECT user, SUM(MIN(ABS(delta), {CAP})) s, SUM(ABS(delta)) raw FROM events WHERE kind=? AND ts>=? AND ts<? AND user>0
              AND user NOT IN (SELECT id FROM users WHERE banned=1) GROUP BY user ORDER BY s DESC, user"""
    return q(sql + (f" LIMIT {int(limit)}" if limit else ""), kind, a, day_start(d) + DAY)


def _pool(kind, d):
    a = max(day_start(d), A.season_from())
    total = q1("SELECT COALESCE(SUM(ABS(delta)),0) t FROM events WHERE kind=? AND ts>=? AND ts<? AND user>0", kind, a, day_start(d) + DAY)["t"]
    cap = A.prize_k(POOL_MAX)
    raw = min(cap, int(total * POOL_PCT))
    return (raw // 10 * 10), cap


def _prizes(pool):
    return [int(pool * s) // 10 * 10 for s in SHARES]


def _settle():
    import wipe
    if wipe.frozen():
        return
    msgs = []
    for r in q("SELECT * FROM gd_day WHERE done=0 AND day<? ORDER BY day", day_no()):
        with tx():
            if q1("SELECT done FROM gd_day WHERE day=?", r["day"])["done"]:
                continue
            pool, _ = _pool(r["kind"], r["day"])
            prizes = _prizes(pool)
            res = []
            for i, s in enumerate(_scores(r["kind"], r["day"], len(SHARES))):
                pts = s["s"] // 100
                if pts < MIN_PTS or prizes[i] <= 0:
                    continue
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (prizes[i], s["user"]))
                event(s["user"], "gameday", prizes[i])
                res.append({"place": i + 1, "user": s["user"], "pts": pts, "prize": prizes[i]})
                msgs.append((s["user"], f"Игра дня «{esc(r['title'])}»: ты на {i + 1} месте! Приз +{prizes[i]:,} ⭐".replace(",", " ")))
                if i == 0:
                    db.execute("INSERT INTO gd_win(user,n) VALUES(?,1) ON CONFLICT(user) DO UPDATE SET n=n+1", (s["user"],))
                    u = q1("SELECT frame, frame_until FROM users WHERE id=?", s["user"])
                    t = now()
                    if (u["frame_until"] or 0) <= t or u["frame"] == "gold":   # сезонную рамку лучше не перебиваем
                        db.execute("UPDATE users SET frame='gold', frame_until=? WHERE id=?", (max(u["frame_until"] or 0, t + DAY), s["user"]))
            db.execute("UPDATE gd_day SET done=1, result=? WHERE day=?", (json.dumps(res), r["day"]))
    for u, t in msgs:
        notify(u, t)


@app.get(R + "/gameday")
def gameday(uid=Depends(auth)):
    r = today()
    d = r["day"]
    if _LIVE["day"] != d or time.time() - _LIVE["at"] > 8:   # вкладка «Игры» спрашивает часто, таблица журнала большая
        _LIVE.update(day=d, at=time.time(), rows=_scores(r["kind"], d), pool=_pool(r["kind"], d))
    rows = _LIVE["rows"]
    pool, cap = _LIVE["pool"]
    prizes = _prizes(pool)
    top = []
    for i, s in enumerate(rows[:10]):
        u = q1("SELECT * FROM users WHERE id=?", s["user"])
        pts = s["s"] // 100
        top.append({"place": i + 1, "pts": pts, "prize": prizes[i] if i < len(prizes) and pts >= MIN_PTS else 0, **user_brief(u)})
    me = next(({"place": i + 1, "pts": s["s"] // 100} for i, s in enumerate(rows) if s["user"] == uid), {"place": 0, "pts": 0})
    prev = q1("SELECT * FROM gd_day WHERE done=1 ORDER BY day DESC LIMIT 1")
    last = None
    if prev:
        res = []
        for x in json.loads(prev["result"] or "[]"):
            u = q1("SELECT * FROM users WHERE id=?", x["user"])
            if u:
                res.append({"place": x["place"], "prize": x["prize"], "pts": x["pts"], **user_brief(u)})
        last = {"title": prev["title"], "gid": prev["gid"], "top": res}
    return {"gid": r["gid"], "title": r["title"], "left": day_start(d) + DAY - now(), "pool": pool, "cap": cap, "prizes": prizes, "shares": SHARES, "players": len(rows),
            "minPts": MIN_PTS, "top": top, "me": me, "last": last}


async def _loop():
    await asyncio.sleep(25)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _settle)
        except Exception as e:
            print("gameday:", e, flush=True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _start():
    asyncio.create_task(_loop())
