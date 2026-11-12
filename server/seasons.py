"""Сезоны (календарный месяц, UTC) и титулы.
Очки сезона = оборот в играх с ограничением 10 000 с одной ставки / 100 (чтобы один богач не забирал всё).
Итоги месяца: топ-10 получают звёзды и рамку аватарки до конца следующего сезона, 1-е место — титул «Чемпион сезона».
Титулы открываются за достижения; игрок выбирает, какой показывать под именем."""
from settings import conf
import asyncio
import calendar
import json
import time

from fastapi import Depends, Request

from app import (GAME_KINDS, R, RICH_RANK, app, auth, db, err, esc, event, notify, now, q, q1, qr, tx, user_brief)

CAP = 10_000
BASE_PRIZES = conf("season.prizes", [200_000, 100_000, 60_000, 30_000, 30_000, 20_000, 20_000, 10_000, 10_000, 10_000])



def prizes():
    """Призы сезона × курс банка (банк богаче — призы больше)."""
    import app as A
    return [A.prize_k(p) for p in BASE_PRIZES]


FRAMES = ["gold", "silver", "silver"] + ["bronze"] * 7
MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

TITLES = [  # id, название, условие (текст)
    ("rookie", "Новичок", "есть у всех"),
    ("veteran", "Ветеран", "30 дней в игре"),
    ("crash", "Покоритель Краша", "забрать ×50 в Краше"),
    ("highroller", "Хайроллер", "выиграть ⭐ 100 000 за одну игру"),
    ("lucky", "Везунчик", "поймать 3 «удачных момента»"),
    ("collector", "Коллекционер", "30 коллекций в альбоме"),
    ("tycoon", "Магнат", "5 бизнесов"),
    ("patron", "Меценат", "подарить 5 подарков"),
    ("clanlord", "Вождь", "глава клана 3+ уровня"),
    ("rich", "Богач", "быть в топ-10 богачей"),
    ("champion", "Чемпион сезона", "занять 1 место в сезоне"),
    ("savior", "Спаситель банка", "подарить банку ⭐ 10 000 во время кризиса"),
    ("gameday", "Игрок дня", "занять 1 место в Игре дня"),
]
TITLE_NAME = {t[0]: t[1] for t in TITLES}
import app as _app   # noqa: E402
_app.TITLE_NAMES.update(TITLE_NAME)

for _c in ("title TEXT DEFAULT ''", "frame TEXT DEFAULT ''", "frame_until INTEGER DEFAULT 0"):
    try:
        db.execute("ALTER TABLE users ADD COLUMN " + _c)
    except Exception:
        pass
db.executescript("""CREATE TABLE IF NOT EXISTS season_results(season TEXT PRIMARY KEY, result TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS season_excl(season TEXT, user INTEGER, why TEXT, PRIMARY KEY(season, user));""")
# Октябрь 2026: Севчик накрутил звёзды через дыру в бонусе за уровень (Плинко ×10) — в рейтинг сезона не попадает.
# Юни извинился и прощён — возвращён в сезон 16.10.2026.
db.executemany("INSERT OR IGNORE INTO season_excl(season,user,why) VALUES('2026-10',?,'накрутка бонуса за уровень')", [(6044718138,)])
db.execute("DELETE FROM season_excl WHERE season='2026-10' AND user=982643862")


def season_bounds(t=None):
    g = time.gmtime(t or time.time())
    start = calendar.timegm((g.tm_year, g.tm_mon, 1, 0, 0, 0))
    ny, nm = (g.tm_year + (g.tm_mon == 12), g.tm_mon % 12 + 1)
    end = calendar.timegm((ny, nm, 1, 0, 0, 0))
    return f"{g.tm_year}-{g.tm_mon:02d}", f"{MONTHS[g.tm_mon]} {g.tm_year}", start, end


def standings(start, end, limit=50):
    sid = season_bounds(start)[0]
    return qr(f"""SELECT user, SUM(MIN(ABS(delta), {CAP})) / 100 pts FROM events WHERE kind IN {GAME_KINDS} AND ts>=? AND ts<?
                 AND user NOT IN (SELECT user FROM season_excl WHERE season=?)
                 GROUP BY user ORDER BY pts DESC LIMIT ?""", max(start, __import__("app").season_from()), end, sid, limit)


def unlocked(uid):
    u = q1("SELECT * FROM users WHERE id=?", uid)
    if not u:
        return set()
    got = {"rookie"}
    if now() - (u["created"] or now()) >= 30 * 86400:
        got.add("veteran")
    if (u["best_crash"] or 0) >= 50:
        got.add("crash")
    if (q1(f"SELECT MAX(delta) m FROM events WHERE user=? AND kind IN {GAME_KINDS}", uid)["m"] or 0) >= 100_000:
        got.add("highroller")
    if q1("SELECT COUNT(*) n FROM events WHERE user=? AND kind='lucky'", uid)["n"] >= 3:
        got.add("lucky")
    if q1("SELECT COUNT(DISTINCT col) n FROM gifts WHERE owner=?", uid)["n"] >= 30:
        got.add("collector")
    if q1("SELECT COUNT(*) n FROM biz WHERE user=?", uid)["n"] >= 5:
        got.add("tycoon")
    if q1("SELECT COUNT(*) n FROM events WHERE user=? AND kind='present'", uid)["n"] + \
            q1("SELECT COUNT(*) n FROM gift_links WHERE sender=? AND status='taken'", uid)["n"] >= 5:
        got.add("patron")
    c = q1("SELECT treasury FROM clans WHERE owner=?", uid)
    if c:
        import clans
        if clans.clan_level(c["treasury"]) >= 3:
            got.add("clanlord")
    if RICH_RANK.get(uid):
        got.add("rich")
    try:
        import bank
        sv = q1("SELECT amount FROM bank_saviors WHERE user=?", uid)
        if sv and sv["amount"] >= bank.SAVIOR_MIN:
            got.add("savior")
    except Exception:
        pass
    if q1("SELECT 1 FROM gd_win WHERE user=?", uid):
        got.add("gameday")
    for r in q("SELECT result FROM season_results"):
        if any(x["place"] == 1 and x["user"] == uid for x in json.loads(r["result"])):
            got.add("champion")
    return got


@app.get(R + "/season")
def season(uid=Depends(auth)):
    sid, title, start, end = season_bounds()
    b = _board()
    rows = b["rows"][:50]
    top = []
    for i, r in enumerate(rows[:20]):
        u = q1("SELECT * FROM users WHERE id=?", r["user"])
        if u:
            top.append({**user_brief(u), "pts": r["pts"], "prize": prizes()[i] if i < len(BASE_PRIZES) else 0, "medal": FRAMES[i] if i < len(FRAMES) else None})
    me = q1(f"SELECT COALESCE(SUM(MIN(ABS(delta), {CAP})),0) / 100 pts FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=?", uid, max(start, __import__("app").season_from()))["pts"]
    place = b["rank"].get(uid) if b["rank"].get(uid, 10**9) <= 1000 else None
    last = q1("SELECT * FROM season_results ORDER BY season DESC LIMIT 1")
    return {"id": sid, "title": title, "ends": end, "top": top, "me": {"pts": me, "place": place,
            "excluded": bool(q1("SELECT 1 FROM season_excl WHERE season=? AND user=?", sid, uid))},
            "prizes": prizes(), "frames": FRAMES, "last": {"season": last["season"], "result": json.loads(last["result"])} if last else None}


@app.get(R + "/titles")
def titles(uid=Depends(auth)):
    got = unlocked(uid)
    cur = q1("SELECT title FROM users WHERE id=?", uid)["title"]
    return {"titles": [{"id": i, "name": n, "how": h, "got": i in got} for i, n, h in TITLES], "current": cur}


@app.post(R + "/titles/select")
async def title_select(req: Request, uid=Depends(auth)):
    tid = str((await req.json()).get("id", ""))
    if tid and tid not in unlocked(uid):
        err("этот титул ещё не открыт")
    with tx():
        db.execute("UPDATE users SET title=? WHERE id=?", (tid, uid))
    return {"ok": True}


def _settle():
    """Итоги прошлого месяца (идемпотентно): призы топ-10, рамки до конца текущего сезона."""
    sid, _, start, end = season_bounds()
    psid, ptitle, pstart, pend = season_bounds(start - 1)
    if q1("SELECT 1 FROM season_results WHERE season=?", psid):
        return
    msgs = []
    with tx():
        if q1("SELECT 1 FROM season_results WHERE season=?", psid):
            return
        res = []
        pz = prizes()
        for i, r in enumerate(standings(pstart, pend, len(pz))):
            db.execute("UPDATE users SET stars=stars+?, frame=?, frame_until=? WHERE id=?", (pz[i], FRAMES[i], end, r["user"]))
            event(r["user"], "season", pz[i])
            res.append({"place": i + 1, "user": r["user"], "pts": r["pts"], "prize": pz[i]})
            msgs.append((r["user"], f"🏆 Сезон «{esc(ptitle)}» окончен: ты на {i + 1} месте! Приз ⭐ {pz[i]:,} и рамка аватарки на весь следующий сезон."
                         .replace(",", " ")))
        db.execute("INSERT INTO season_results(season,result,ts) VALUES(?,?,?)", (psid, json.dumps(res), now()))
    for u, t in msgs:
        notify(u, t)


async def seasons_loop():
    await asyncio.sleep(50)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _settle)
        except Exception as e:
            print("seasons:", e, flush=True)
        await asyncio.sleep(1800)


@app.on_event("startup")
async def _seasons_start():
    asyncio.create_task(seasons_loop())


_BRIEF = {"t": 0, "rank": {}, "pts": {}, "rows": []}
BOARD_TTL = 30   # таблица сезона одна на всех: пересчёт не чаще раза в 30 с, а не на каждый запрос каждого игрока


def _board():
    sid, _, start, end = season_bounds()
    if now() - _BRIEF["t"] > BOARD_TTL or _BRIEF.get("sid") != sid:
        rows = standings(start, end, 100000)
        _BRIEF.update(t=now(), sid=sid, rows=rows, rank={r["user"]: i + 1 for i, r in enumerate(rows)}, pts={r["user"]: r["pts"] for r in rows})
    return _BRIEF


@app.get(R + "/season/brief")
def season_brief(uid=Depends(auth)):
    """Для карточки на главной: место и очки из общей таблицы сезона."""
    sid, title, start, end = season_bounds()
    _board()
    return {"title": title, "ends": end, "place": _BRIEF["rank"].get(uid), "pts": _BRIEF["pts"].get(uid, 0), "players": len(_BRIEF["rank"]), "prize": prizes()[0]}
