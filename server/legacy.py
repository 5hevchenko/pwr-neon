"""Наследие: итоги каждого прошедшего сезона остаются в профиле навсегда, вайп их не трогает. На балансы не влияет.
Место считается по обороту в играх (выиграно + проиграно) среди тех, кто играл. Прошлые сезоны заполняются один раз из wipe_thanks."""
import json
import sqlite3
import threading
import time

from fastapi import Depends

import app as A
from app import R, app, auth, db, err, now, q, q1, tx

db.executescript("""CREATE TABLE IF NOT EXISTS legacy(wipe INTEGER, user INTEGER, season INTEGER, ts_from INTEGER, ts_to INTEGER, place INTEGER, players INTEGER,
    rounds INTEGER, won INTEGER, lost INTEGER, best INTEGER, best_game TEXT, hours REAL, gift TEXT, PRIMARY KEY(wipe, user));
CREATE INDEX IF NOT EXISTS legacy_user ON legacy(user, wipe);
CREATE INDEX IF NOT EXISTS legacy_place ON legacy(wipe, place);""")

_RDB = sqlite3.connect(f"file:{A.DB_PATH}?mode=ro", uri=True, check_same_thread=False, timeout=5)   # тяжёлый подсчёт места не держит общий лок игры
_RL = threading.Lock()
_CUR = {"ts": 0, "rows": {}, "players": 0}
_BG = {"case": "Кейсы"}


def _ranked(stats, skip=()):
    """{игрок: статистика} → список (игрок, место, статистика) по обороту, без не игравших и исключённых."""
    rows = [(u, s) for u, s in stats.items() if (s.get("rounds") or 0) > 0 and u not in skip and u > 0]
    rows.sort(key=lambda x: -((x[1].get("won") or 0) + (x[1].get("lost") or 0)))
    return [(u, i + 1, s) for i, (u, s) in enumerate(rows)], len(rows)


def _store(wid, season, since, until, stats, skip=(), gifts=None):
    rows, n = _ranked(stats, skip)
    for u, place, s in rows:
        db.execute("INSERT OR REPLACE INTO legacy(wipe,user,season,ts_from,ts_to,place,players,rounds,won,lost,best,best_game,hours,gift) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (wid, u, season, since, until, place, n, s.get("rounds") or 0, s.get("won") or 0, s.get("lost") or 0, s.get("best") or 0,
                    _BG.get(s.get("bestGame"), s.get("bestGame") or ""), s.get("hours") or 0, json.dumps((gifts or {}).get(u)) if (gifts or {}).get(u) else None))


def capture(wid, season, since, until, stats, skip):
    """Вызывается внутри транзакции вайпа, пока подарки ещё на месте: в карточку сезона попадает самый дорогой подарок игрока."""
    gifts = {}
    for r in q("SELECT g.* FROM gifts g JOIN (SELECT owner, MAX(value) v FROM gifts GROUP BY owner) m ON g.owner=m.owner AND g.value=m.v ORDER BY g.id"):
        if r["owner"] not in gifts:
            try:
                gifts[r["owner"]] = A.gift_out(r)
            except Exception as e:
                print("legacy gift:", r["id"], e, flush=True)   # итоги сезона важнее картинки, вайп из-за этого не падает
    banned = {r["id"] for r in q("SELECT id FROM users WHERE banned=1")}
    _store(wid, season, since, until, stats, set(skip) | banned, gifts)


def _backfill():
    """Сезоны, завершившиеся до появления Наследия: данные уже лежат в письмах вайпа, подарков там нет."""
    wipes = q("SELECT id, ts FROM wipe_log ORDER BY id")
    prev = 0
    banned = {r["id"] for r in q("SELECT id FROM users WHERE banned=1")}
    with tx():
        for i, w in enumerate(wipes):
            if not q1("SELECT 1 FROM legacy WHERE wipe=? LIMIT 1", w["id"]):
                rows = q("SELECT user, stats, bad FROM wipe_thanks WHERE wipe=?", w["id"])
                stats, skip = {}, set()
                for r in rows:
                    try:
                        stats[r["user"]] = json.loads(r["stats"] or "{}")
                    except Exception:
                        pass
                    if r["bad"]:
                        skip.add(r["user"])
                _store(w["id"], i + 1, prev, w["ts"], stats, skip | banned)
            prev = w["ts"]


_backfill()


def _current():
    """Текущий сезон: раз в минуту, в отдельном соединении, таблица журнала большая."""
    t = time.time()
    if t - _CUR["ts"] < 60:
        return _CUR
    since = A.season_from() or (q1("SELECT COALESCE(MAX(ts),0) t FROM wipe_log")["t"])
    with _RL:
        rows = _RDB.execute(f"""SELECT user, COUNT(*) n, SUM(ABS(delta)) turn, MAX(delta) best FROM events
                                WHERE kind IN {A.GAME_KINDS} AND ts>=? AND user>0 GROUP BY user ORDER BY turn DESC""", (since,)).fetchall()
    _CUR.update(ts=t, since=since, players=len(rows), rows={r[0]: {"place": i + 1, "rounds": r[1], "best": max(r[3] or 0, 0)} for i, r in enumerate(rows)})
    return _CUR


def _out(r):
    gift = None
    if r["gift"]:
        try:
            gift = json.loads(r["gift"])
        except Exception:
            pass
    return {"season": r["season"], "from": r["ts_from"], "to": r["ts_to"], "place": r["place"], "players": r["players"], "rounds": r["rounds"],
            "won": r["won"], "lost": r["lost"], "best": r["best"], "bestGame": r["best_game"], "hours": r["hours"], "gift": gift}


@app.get(R + "/legacy/hall")
def legacy_hall(uid=Depends(auth)):
    out = []
    for w in q("SELECT DISTINCT wipe, season, ts_to, players FROM legacy ORDER BY wipe DESC LIMIT 30"):
        top = []
        for r in q("SELECT l.place, l.won, l.lost, l.best, u.* FROM legacy l JOIN users u ON u.id=l.user WHERE l.wipe=? AND l.place<=10 AND u.banned=0 ORDER BY l.place LIMIT 3", w["wipe"]):
            top.append({"place": r["place"], "turn": r["won"] + r["lost"], "best": r["best"], **A.user_brief(r)})
        out.append({"season": w["season"], "to": w["ts_to"], "players": w["players"], "top": top})
    return {"seasons": out}


@app.get(R + "/legacy/{tid}")
def legacy_of(tid: int, uid=Depends(auth)):
    q1("SELECT 1 FROM users WHERE id=?", tid) or err("игрок не найден", 404)
    rows = q("SELECT * FROM legacy WHERE user=? ORDER BY wipe DESC", tid)
    cur = _current()
    c = cur["rows"].get(tid)
    wins = q1("SELECT n FROM gd_win WHERE user=?", tid) if q1("SELECT 1 FROM sqlite_master WHERE name='gd_win'") else None
    return {"seasons": [_out(r) for r in rows],
            "current": {"season": q1("SELECT COUNT(*) n FROM wipe_log")["n"] + 1, "from": cur.get("since", 0), "players": cur["players"], **(c or {"place": 0, "rounds": 0, "best": 0})},
            "summary": {"count": len(rows), "bestPlace": min((r["place"] for r in rows), default=0), "bestWin": max((r["best"] for r in rows), default=0),
                        "rounds": sum(r["rounds"] for r in rows), "dayWins": wins["n"] if wins else 0}}
