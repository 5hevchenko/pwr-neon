"""Ответственная игра: лимиты, которые игрок ставит себе сам, и итоги недели от бота.
Дневной лимит проигрыша: когда чистый проигрыш в играх за сутки (по UTC, как остальные дневные счётчики) дошёл до лимита,
ставки закрыты до конца суток. Поставить или уменьшить лимит — сразу; поднять или снять — только через 24 часа.
Перерыв: 1, 7 или 30 дней без ставок, отменить нельзя. Проверка — в app.check_bet и во входах игр, которые его не зовут.
Итоги недели: в понедельник бот присылает раунды, итог, лучший выигрыш и любимую игру; при заметном минусе
напоминает про лимиты."""
import asyncio
import time

from fastapi import Depends, Request

import app as A
from app import GAME_KINDS, R, app, auth, day_start, db, err, notify, now, q, q1, qr, tx, week_start

DELAY = 86400                       # поднять или снять лимит можно только через сутки
PAUSES = (1, 7, 30)                 # дней перерыва
REPORT_MIN = 20                     # раундов за неделю, чтобы прислать итоги
REPORT_LOSS = 20_000                # от такого минуса напоминаем про лимиты
HOURS = range(6, 18)                # по UTC = 9:00–21:00 по Москве

db.executescript("""
CREATE TABLE IF NOT EXISTS self_limit(user INTEGER PRIMARY KEY, day_loss INTEGER DEFAULT 0, next_loss INTEGER, next_at INTEGER DEFAULT 0,
  pause_until INTEGER DEFAULT 0, ts INTEGER);
CREATE TABLE IF NOT EXISTS week_report(week INTEGER, user INTEGER, ts INTEGER, PRIMARY KEY(week, user));
""")
LIM = {r["user"] for r in q("SELECT user FROM self_limit WHERE day_loss>0 OR pause_until>? OR next_at>0", now())}   # у кого вообще есть ограничения


def nf(n):
    return f"{int(n):,}".replace(",", " ")


def _msk(ts):
    return time.strftime("%d.%m %H:%M", time.gmtime(ts + 3 * 3600))


def _row(uid):
    """Строка лимитов с применённым отложенным изменением."""
    r = q1("SELECT * FROM self_limit WHERE user=?", uid)
    if r and r["next_at"] and now() >= r["next_at"]:
        with tx():
            db.execute("UPDATE self_limit SET day_loss=?, next_loss=NULL, next_at=0 WHERE user=?", (r["next_loss"] or 0, uid))
        r = q1("SELECT * FROM self_limit WHERE user=?", uid)
    return r


def loss_today(uid):
    return max(0, -q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=?", uid, day_start())["s"])


def guard(uid, amount=0):
    """Ставка разрешена? Иначе err с понятной причиной. Для игроков без лимитов — одна проверка множества."""
    if uid not in LIM:
        return
    r = _row(uid)
    if not r:
        LIM.discard(uid)
        return
    t = now()
    if r["pause_until"] > t:
        err(f"Перерыв до {_msk(r['pause_until'])} по Москве. Ставки до этого времени закрыты")
    if r["day_loss"] > 0:
        left = r["day_loss"] - loss_today(uid)
        if left <= 0:
            err(f"Дневной лимит проигрыша {nf(r['day_loss'])} ⭐ исчерпан. Ставки откроются в {_msk(day_start() + 86400)[-5:]} по Москве")
        if amount > left:
            err(f"До дневного лимита проигрыша осталось {nf(left)} ⭐, ставка не больше этой суммы")
    if not (r["day_loss"] > 0 or r["pause_until"] > t or r["next_at"]):
        LIM.discard(uid)


@app.get(R + "/limits")
def limits_get(uid=Depends(auth)):
    r = _row(uid)
    t = now()
    return {"dayLoss": r["day_loss"] if r else 0, "next": ({"loss": r["next_loss"] or 0, "at": r["next_at"]} if r and r["next_at"] else None),
            "pauseUntil": r["pause_until"] if r and r["pause_until"] > t else 0, "lossToday": loss_today(uid), "pauses": PAUSES,
            "resetIn": day_start() + 86400 - t}


@app.post(R + "/limits")
async def limits_set(req: Request, uid=Depends(auth)):
    b = await req.json()
    t = now()
    r = _row(uid)
    cur = r["day_loss"] if r else 0
    with tx():
        db.execute("INSERT OR IGNORE INTO self_limit(user,ts) VALUES(?,?)", (uid, t))
        if "dayLoss" in b:
            try:
                v = max(0, int(b["dayLoss"]))
            except (TypeError, ValueError):
                err("Введи целое число")
            if v and not 100 <= v <= 100_000_000:
                err("Лимит от 100 ⭐")
            if v and (not cur or v < cur):   # строже — сразу
                db.execute("UPDATE self_limit SET day_loss=?, next_loss=NULL, next_at=0, ts=? WHERE user=?", (v, t, uid))
            elif v != cur:                   # мягче или снять — через сутки
                db.execute("UPDATE self_limit SET next_loss=?, next_at=?, ts=? WHERE user=?", (v, t + DELAY, t, uid))
            else:                            # вернул как было — отменяем отложенное
                db.execute("UPDATE self_limit SET next_loss=NULL, next_at=0 WHERE user=?", (uid,))
        if "pause" in b:
            try:
                days = int(b["pause"])
            except (TypeError, ValueError):
                err("Выбери срок перерыва")
            if days not in PAUSES:
                err("Выбери срок перерыва")
            until = max(r["pause_until"] if r else 0, t + days * 86400)
            db.execute("UPDATE self_limit SET pause_until=?, ts=? WHERE user=?", (until, t, uid))
    LIM.add(uid)
    return limits_get(uid=uid)


# ============================== итоги недели ==============================
GAME_NAMES = {"crash": "Краш", "mines": "Мины", "wheel": "Колесо", "dice": "Кубик", "limbo": "Лимбо", "plinko": "Плинко", "tower": "Башня",
              "slots": "Слоты", "blackjack": "Блэкджек", "dogs": "Пёсики", "roulette": "Рулетка", "hilo": "Больше/меньше", "chicken": "Курица",
              "avia": "Самолётик", "battle": "Битва кейсов", "scratch": "Скретч", "claw": "Кран", "pump": "Насос", "drill": "Бур",
              "darts": "Дартс", "fish": "Рыбалка", "keno": "Кено", "penalty": "Пенальти", "case": "Кейсы", "upgrade": "Апгрейд",
              "duel": "Дуэли", "jroul": "Джекпот-рулетка", "starfall": "Звездопад", "cards": "Карты", "forecast": "Прогнозы",
              "carousel": "Карусель", "safe": "Сейф", "ladder": "Лестница", "craft": "Крафт", "bankbet": "Ставка на банк"}


def _report():
    import wipe
    if wipe.frozen() or time.gmtime().tm_hour not in HOURS:
        return
    ws = week_start()
    week = ws - 7 * 86400
    if q1("SELECT 1 FROM week_report WHERE week=? AND user=0", week):
        return
    rows = qr(f"""SELECT user, COUNT(*) n, SUM(delta) net, MAX(delta) best FROM events
                 WHERE kind IN {GAME_KINDS} AND ts>=? AND ts<? AND user>0 GROUP BY user HAVING n>=?""", week, ws, REPORT_MIN)
    sent = 0
    for r in rows:
        u = q1("SELECT id, notif, banned FROM users WHERE id=?", r["user"])
        if not u or u["banned"] or not u["notif"] or q1("SELECT 1 FROM week_report WHERE week=? AND user=?", week, u["id"]):
            continue
        fav = q1(f"SELECT kind, COUNT(*) n FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=? AND ts<? GROUP BY kind ORDER BY n DESC LIMIT 1",
                 u["id"], week, ws)
        bk = q1(f"SELECT kind FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=? AND ts<? ORDER BY delta DESC LIMIT 1", u["id"], week, ws)
        net = r["net"] or 0
        text = (f"<b>Твоя неделя в играх</b>\n\nРаундов: {nf(r['n'])}\n"
                f"Итог: <b>{'+' if net >= 0 else '−'}{nf(abs(net))} ⭐</b>\n"
                + (f"Лучший выигрыш: +{nf(r['best'])} ⭐ ({GAME_NAMES.get(bk['kind'], bk['kind'])})\n" if r["best"] and r["best"] > 0 and bk else "")
                + (f"Чаще всего: {GAME_NAMES.get(fav['kind'], fav['kind'])}\n" if fav else ""))
        if net <= -REPORT_LOSS:
            text += "\nЕсли хочешь притормозить, в настройках есть дневной лимит проигрыша и перерыв от суток."
        with tx():
            db.execute("INSERT OR IGNORE INTO week_report(week,user,ts) VALUES(?,?,?)", (week, u["id"], now()))
        notify(u["id"], text)
        sent += 1
    with tx():
        db.execute("INSERT OR IGNORE INTO week_report(week,user,ts) VALUES(?,0,?)", (week, now()))
    if sent:
        print(f"week report: {sent}", flush=True)


async def _loop():
    await asyncio.sleep(80)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _report)
        except Exception as e:
            print("week report:", e, flush=True)
        await asyncio.sleep(900)


@app.on_event("startup")
async def _start():
    if not A.DEV:
        asyncio.create_task(_loop())


A.SELF_GUARD = guard
