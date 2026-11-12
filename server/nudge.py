"""Напоминания от бота, которых не было: новичкам и про Игру дня. Звёзд не раздают — только зовут к тому, что уже ждёт в игре.
1) Новичок ушёл в первые дни (меньше 30 раундов — «возвращайся» в retain.py таких не трогает). Два письма за всё время:
   через 18 ч тишины и, если не вернулся, ещё одно через 2 дня после первого. В письме — что именно его ждёт:
   несобранные награды «Старта новичка» и готовый бесплатный кейс.
2) Игра дня началась — тем, кто в эту игру реально играет (от 20 раундов за 30 дней) и заходил за последние 3 дня.
3) Тебя вытеснили из призовой тройки Игры дня — раз в сутки на игрока, пока до конца дня больше 20 минут.
Все письма — только с включёнными уведомлениями, с 9 до 21 по Москве (кроме п. 3) и не чаще раза в 3 часа
на игрока вместе с напоминаниями из app.py (общая отметка users.rem_last). Кто вернулся за 3 дня — отмечаем в nudge_log."""
import asyncio
import time

import app as A
from app import GAME_KINDS, app, db, esc, notify, now, q, q1, tx

HOURS = range(6, 18)            # по UTC = 9:00–21:00 по Москве
GAP = 3 * 3600                  # общий интервал с напоминаниями app.py
BATCH = 40                      # писем за проход
NEW_QUIET = 18 * 3600           # новичок молчит столько — первое письмо
NEW_AGAIN = 2 * 86400           # второе — через столько после первого
NEW_MAX_AGE = 10 * 86400        # старше — уже не новичок
NEW_ROUNDS = 30
GD_ROUNDS = 20                  # «играет в эту игру»: раундов за 30 дней
GD_SEEN = 3 * 86400

db.executescript("""
CREATE TABLE IF NOT EXISTS nudge_log(id INTEGER PRIMARY KEY, user INTEGER, kind TEXT, day INTEGER DEFAULT 0, ts INTEGER, back INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS nudge_log_user ON nudge_log(user, kind);
CREATE INDEX IF NOT EXISTS nudge_log_ts ON nudge_log(ts);
""")
_TOP = {"day": None, "users": set()}


def nf(n):
    return f"{int(n):,}".replace(",", " ")


def _sent(uid, kind, day=None):
    if day is None:
        return q1("SELECT ts FROM nudge_log WHERE user=? AND kind=? ORDER BY id DESC LIMIT 1", uid, kind)
    return q1("SELECT ts FROM nudge_log WHERE user=? AND kind=? AND day=? LIMIT 1", uid, kind, day)


def _mark(uid, kind, day=0):
    db.execute("INSERT INTO nudge_log(user,kind,day,ts) VALUES(?,?,?,?)", (uid, kind, day, now()))
    db.execute("UPDATE users SET rem_last=? WHERE id=?", (now(), uid))


def _ok(u, t):
    return not u["banned"] and ("notif" not in u.keys() or u["notif"]) and t - (u["rem_last"] or 0) >= GAP


def _rounds(uid):
    """Раундов в играх, но не больше NEW_ROUNDS: дальше считать незачем."""
    return q1(f"SELECT COUNT(*) n FROM (SELECT 1 FROM events WHERE user=? AND kind IN {GAME_KINDS} LIMIT ?)", uid, NEW_ROUNDS)["n"]


def _onboard_left(uid):
    """Награды «Старта новичка», которые ещё можно забрать: (звёзд, шагов)."""
    import onboard
    got = {r[0] for r in db.execute("SELECT step FROM onboard WHERE user=?", (uid,)).fetchall()}
    left = [s for s in onboard.STEPS if s[0] not in got]
    return sum(s[4] for s in left), len(left)


def _newcomers(out):
    t = now()
    for u in q("SELECT * FROM users WHERE created>? AND seen<? AND banned=0 AND rem_last<=? "
               "AND NOT EXISTS (SELECT 1 FROM nudge_log n WHERE n.user=users.id AND n.kind='new2')", t - NEW_MAX_AGE, t - NEW_QUIET, t - GAP):
        if len(out) >= BATCH:
            return
        if not _ok(u, t):
            continue
        rounds = _rounds(u["id"])
        if rounds >= NEW_ROUNDS:
            continue
        first = _sent(u["id"], "new1")
        if first and (t - first["ts"] < NEW_AGAIN or u["seen"] > first["ts"]):
            continue
        stars, steps = _onboard_left(u["id"])
        free = not u["last_free"] or t >= u["last_free"] + A.free_every(u)
        name = esc(u["name"] or "Привет")
        played = rounds > 0
        bits = []
        if steps:
            bits.append(f"{nf(stars)} ⭐ за шаги «Старта новичка» (осталось {steps})")
        if free:
            bits.append("бесплатный кейс")
        if not bits and not played:
            bits.append(f"{nf(u['stars'])} ⭐ на балансе")
        if not bits:
            continue
        if not first:
            text = (f"{name}, первая игра ещё впереди, а тебя уже ждут: " if not played else f"{name}, ты недавно с нами, и тебя уже ждут: ") + ", ".join(bits) + "."
            kind = "new1"
        else:
            text = f"{name}, награды за старт ещё на месте: " + ", ".join(bits) + ". Всё уже в игре, заходи."
            kind = "new2"
        with tx():
            _mark(u["id"], kind)
        out.append((u["id"], text))


def _gd_start(out):
    import gameday as G
    r = G.today()
    d, t = r["day"], now()
    if t - G.day_start(d) > 12 * 3600:   # к вечеру анонс уже не к месту
        return
    title = esc(r["title"])
    pool, _ = G._pool(r["kind"], d)
    ds = G.day_start(d)
    rows = q("""SELECT u.* FROM (SELECT user FROM events WHERE kind=? AND ts>? AND user>0 GROUP BY user HAVING COUNT(*)>=?) e
                JOIN users u ON u.id=e.user
                WHERE u.banned=0 AND u.seen>=? AND u.seen<=? AND COALESCE(u.rem_last,0)<=?
                  AND NOT EXISTS (SELECT 1 FROM nudge_log n WHERE n.user=u.id AND n.kind='gd' AND n.day=?)""",
             r["kind"], t - 30 * 86400, GD_ROUNDS, t - GD_SEEN, ds, t - GAP, d)
    for u in rows:
        if len(out) >= BATCH:
            return
        if not _ok(u, t):
            continue
        prize = f" Фонд уже {nf(pool)} ⭐ и растёт с каждой ставкой." if pool >= 1000 else " Фонд растёт с каждой ставкой."
        text = f"Игра дня сегодня — «{title}», твоя игра. Трое лучших за сутки делят фонд.{prize}"
        with tx():
            _mark(u["id"], "gd", d)
        out.append((u["id"], text))


def _gd_overtake(out):
    import gameday as G
    r = G.today()
    d, t = r["day"], now()
    rows = G._scores(r["kind"], d, 3)
    top = {s["user"] for s in rows if s["s"] // 100 >= G.MIN_PTS}
    if _TOP["day"] != d:   # новый день или перезапуск — запоминаем без писем
        _TOP.update(day=d, users=top)
        return
    gone, _TOP["users"] = _TOP["users"] - top, top
    left = G.day_start(d) + G.DAY - t
    if left < 20 * 60:
        return
    prizes = G._prizes(G._pool(r["kind"], d)[0])
    hours = left // 3600
    for uid in gone:
        u = q1("SELECT * FROM users WHERE id=?", uid)
        if not u or u["banned"] or ("notif" in u.keys() and not u["notif"]) or t - u["seen"] < 600 or _sent(uid, "gdout", d):
            continue
        when = f"{hours} ч" if hours else "меньше часа"
        third = f" Приз за 3 место сейчас {nf(prizes[2])} ⭐." if prizes[2] >= 500 else ""
        with tx():
            _mark(uid, "gdout", d)
        out.append((uid, f"Тебя вытеснили из призовой тройки Игры дня «{esc(r['title'])}». До конца дня {when}.{third}"))


def _back():
    with tx():
        db.execute("UPDATE nudge_log SET back=1 WHERE back=0 AND ts>? AND EXISTS (SELECT 1 FROM users u WHERE u.id=nudge_log.user AND u.seen>nudge_log.ts)", (now() - 3 * 86400,))


def run():
    import wipe
    if wipe.frozen():
        return
    _back()
    out = []
    _gd_overtake(out)   # срочное — в любое время
    if time.gmtime().tm_hour in HOURS:
        _gd_start(out)
        _newcomers(out)
    for u, text in out:
        notify(u, text)
    if out:
        print(f"nudge: sent {len(out)}", flush=True)


async def _loop():
    await asyncio.sleep(50)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, run)
        except Exception as e:
            print("nudge:", e, flush=True)
        await asyncio.sleep(120)


@app.on_event("startup")
async def _start():
    if not A.DEV:
        asyncio.create_task(_loop())
