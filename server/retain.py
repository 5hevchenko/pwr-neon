"""Удержание игроков.
1) Кэшбэк недели: в понедельник каждому, кто за прошлую неделю ушёл в минус в играх, возвращаем 5% чистого проигрыша
   (от ⭐ 2000 минуса, не больше ⭐ 250K). В среднем это ~0,2% оборота — преимущество казино сохраняется.
2) «Возвращайся» — три ступени по тому, сколько игрок не заходил: 2–6 дней — ключ от «Ширпотреба»,
   7–14 — ключ «Удача» + звёзды, 15–45 — ключ «Роскошь» + звёзды побольше. Каждая ступень — не чаще своего интервала.
   Только тем, кто реально играл (от 30 раундов), и с включёнными уведомлениями. Кто вернулся за 3 дня — отмечаем
   в comeback_log (статистика в админке → Обзор)."""
from settings import conf
import asyncio
import time

from app import GAME_KINDS, app, db, esc, event, notify, now, q, q1, tx, week_start

CB_RATE = conf("cashback.rate", 0.05)
CB_MIN_LOSS = conf("cashback.min_loss", 2_000)
CB_MAX = conf("cashback.max", 250_000)
BACK_AFTER = 2 * 86400      # не заходил столько — зовём
BACK_UNTIL = 14 * 86400     # дольше — уже не дёргаем
BACK_EVERY = 7 * 86400      # одному игроку — не чаще
BACK_ROUNDS = 30            # твинкам без игры ключ не положен
BACK_CASE = conf("comeback.case", "starter")
BACK_HOURS = range(6, 19)   # 9:00–21:00 по Москве

db.executescript("""
CREATE TABLE IF NOT EXISTS cashback(week INTEGER, user INTEGER, loss INTEGER, amount INTEGER, ts INTEGER, PRIMARY KEY(week, user));
CREATE TABLE IF NOT EXISTS comeback(user INTEGER PRIMARY KEY, ts INTEGER);
CREATE TABLE IF NOT EXISTS comeback_log(id INTEGER PRIMARY KEY, user INTEGER, tier INTEGER, ts INTEGER, back INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS comeback_log_ts ON comeback_log(ts);
""")
# ступени: (не заходил от, до, ключ, звёзды, не чаще)
TIERS = [(2 * 86400, 7 * 86400, conf("comeback.case", "starter"), 0, 7 * 86400),
         (7 * 86400, 15 * 86400, "luck", 1_000, 7 * 86400),
         (15 * 86400, 45 * 86400, "lux", 3_000, 30 * 86400)]


def week_net(uid, since=None):
    """Чистый итог игрока в играх с начала недели (минус — проигрыш)."""
    return q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=?", uid, max(since or week_start(), __import__("app").season_from()))["s"]


def cashback_preview(uid):
    """Сколько вернётся в понедельник, если неделя закончится сейчас (для /me)."""
    net = week_net(uid)
    return min(CB_MAX, int(-net * CB_RATE)) if -net >= CB_MIN_LOSS else 0


def _cashback():
    week = week_start() - 7 * 86400
    if q1("SELECT 1 FROM cashback WHERE week=? AND user=0", week):
        return
    msgs = []
    with tx():
        if q1("SELECT 1 FROM cashback WHERE week=? AND user=0", week):
            return
        for r in q(f"SELECT user, SUM(delta) s FROM events WHERE kind IN {GAME_KINDS} AND ts>=? AND ts<? GROUP BY user HAVING s<=?",
                   max(week, __import__("app").season_from()), week + 7 * 86400, -CB_MIN_LOSS):
            amt = min(CB_MAX, int(-r["s"] * CB_RATE))
            if amt <= 0 or not q1("SELECT 1 FROM users WHERE id=?", r["user"]):
                continue
            db.execute("INSERT INTO cashback VALUES(?,?,?,?,?)", (week, r["user"], -r["s"], amt, now()))
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amt, r["user"]))
            event(r["user"], "cashback", amt)
            msgs.append((r["user"], f"💸 <b>Кэшбэк недели</b>: прошлая неделя не задалась — возвращаем 5% проигрыша, "
                                    f"+{amt:,} ⭐ уже на балансе. Удачи на этой неделе!".replace(",", " ")))
        db.execute("INSERT INTO cashback VALUES(?,0,0,0,?)", (week, now()))   # отметка «неделя выплачена»
    for u, t in msgs:
        notify(u, t)
    print(f"cashback: week {week}, paid {len(msgs)}", flush=True)


def _comeback():
    t = now()
    # кто вернулся в течение 3 дней после письма — для статистики
    with tx():
        db.execute("UPDATE comeback_log SET back=1 WHERE back=0 AND ts>? AND user IN (SELECT id FROM users WHERE seen>comeback_log.ts)", (t - 3 * 86400,))
    if time.gmtime().tm_hour not in BACK_HOURS:
        return
    import economy as E
    msgs = []
    with tx():
        for tier, (lo, hi, cid, stars, every) in enumerate(TIERS, 1):
            if cid not in E.CASES:
                continue
            title = E.CASES[cid]["title"]
            for u in q("SELECT * FROM users WHERE seen<? AND seen>? AND banned=0 LIMIT 200", t - lo, t - hi):
                if "notif" in u.keys() and not u["notif"]:
                    continue
                last = q1("SELECT ts FROM comeback_log WHERE user=? AND tier=? ORDER BY id DESC LIMIT 1", u["id"], tier)
                if last and t - last["ts"] < every:
                    continue
                if q1(f"SELECT COUNT(*) n FROM (SELECT 1 FROM events WHERE user=? AND kind IN {GAME_KINDS} LIMIT ?)", u["id"], BACK_ROUNDS)["n"] < BACK_ROUNDS:
                    continue
                db.execute("INSERT INTO comeback(user,ts) VALUES(?,?) ON CONFLICT(user) DO UPDATE SET ts=excluded.ts", (u["id"], t))
                db.execute("INSERT INTO comeback_log(user,tier,ts) VALUES(?,?,?)", (u["id"], tier, t))
                db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,1) ON CONFLICT(user,cid) DO UPDATE SET n=n+1", (u["id"], cid))
                if stars:
                    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (stars, u["id"]))
                    event(u["id"], "comeback", stars)
                days = (t - u["seen"]) // 86400
                gift = f"ключ от кейса «{esc(title)}»" + (f" и {stars:,} ⭐".replace(",", " ") if stars else "")
                text = (f"👋 {esc(u['name'])}, давно не виделись! Положили тебе {gift} — открой бесплатно. Бонус дня тоже ждёт 🎁" if tier == 1 else
                        f"🎁 {esc(u['name'])}, тебя не было {days} дн. — мы скучали! Держи {gift}. Заходи забрать, пока не сгорело." if tier == 2 else
                        f"💎 {esc(u['name'])}, без тебя тут не то. Подарок за возвращение: {gift}. Всё уже в игре — открывай!")
                msgs.append((u["id"], text))
                if len(msgs) >= 40:   # не больше 40 писем за проход — без всплесков к Telegram API
                    break
            if len(msgs) >= 40:
                break
    for u, text in msgs:
        notify(u, text)


async def _loop():
    await asyncio.sleep(40)
    while True:
        for f in (_cashback, _comeback):
            try:
                await asyncio.get_running_loop().run_in_executor(None, f)
            except Exception as e:
                print("retain:", f.__name__, e, flush=True)
        await asyncio.sleep(900)


@app.on_event("startup")
async def _start():
    asyncio.create_task(_loop())
