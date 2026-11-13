"""«Ограбление сейфа» — повод заходить каждый день.

Пока игрок не заходит, у его сейфа (баланса звёзд) орудуют грабители, и бот пишет ему об этом всё тревожнее:
  1 день — присматриваются, 2 — подбирают отмычки, 3 — сверлят замок, 5 — замок почти сдался, 6 — последний день.
Не заходил burn_days (7) дней — сейф вскрыли: с баланса сгорают все звёзды, кроме купленных (сумма покупок за Telegram Stars
и крипту вместе с бонусами). Подарки, скины, вклады и прочее имущество не трогаем — горит только баланс.
Зашёл в любой день до взлома — грабители сбегают, отсчёт начинается заново; в игре показываем, что он успел.
  · у кого сгорать нечему (на балансе сверх купленного меньше min_loot) — того не трогаем и не пишем;
  · отсчёт для всех начинается не раньше дня запуска механики: давно ушедших игроков не грабим без предупреждений;
  · письма — только днём и не чаще, чем через 20 часов после письма «Возвращайся» (retain.py); сам взлом от писем не зависит.
Сгоревшие звёзды возвращаются в банк игры (событие heist)."""
from settings import S
import asyncio
import time

from fastapi import Depends

from app import R, app, auth, db, esc, event, kv_get, notify, now, q, q1, tx
from settings import conf

ON = conf("heist.on", True)
BURN = int(conf("heist.burn_days", 7))             # на какой день сейф вскрывают
MIN_LOOT = int(conf("heist.min_loot", 10_000))     # меньше на балансе сверх купленного — грабить нечего
STAGES = [d for d in (1, 2, 3, 5, 6) if d < BURN]  # в какие дни пишем
HOURS = range(6, 19)                               # письма с 9:00 до 21:00 по Москве
DAY = int(conf("heist.day_sec", 86400))            # длина «дня» (для проверки можно укоротить)

db.execute("CREATE TABLE IF NOT EXISTS heist(user INTEGER PRIMARY KEY, seen INTEGER, stage INTEGER, loot INTEGER, kept INTEGER, days INTEGER, ts INTEGER)")
if not kv_get("heist_start"):
    with tx():
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('heist_start',?)", (str(now()),))
START = int(kv_get("heist_start") or now())


def nf(n):
    return f"{int(n):,}".replace(",", " ")


def protected(uid):
    """Купленные звёзды: их грабители не трогают."""
    return q1("SELECT COALESCE(SUM(stars),0) s FROM payments WHERE user=? AND xtr>0 AND COALESCE(kind,'pack')<>'gift'", uid)["s"]


def _text(stage, name, loot, kept, days):
    left = max(1, BURN - days)
    if stage >= BURN:
        return (f"💥 {name}, сейф вскрыли. Грабители унесли <b>{S(loot)} ⭐</b>."
                + (f" Купленные звёзды остались на балансе: {S(kept)} ⭐." if kept else "") + " Возвращайся — отыграемся, и больше так надолго не пропадай.")
    return {
        1: f"🕵️ {name}, у твоего сейфа крутятся подозрительные типы. Внутри <b>{S(loot)} ⭐</b>. Загляни в игру — спугнёшь их.",
        2: f"🔦 {name}, грабители уже у двери сейфа и подбирают отмычки. Под угрозой <b>{S(loot)} ⭐</b>. Зайди, пока замок цел.",
        3: f"🔨 {name}, сейф ломают: слышно, как сверлят замок. До взлома {left} дн. — зайди, и они разбегутся.",
        5: f"💣 {name}, замок почти сдался. Через {left} дн. грабители вынесут <b>{S(loot)} ⭐</b>.",
        6: f"🚨 {name}, последний день. Завтра сейф вскроют и заберут всё, кроме купленных звёзд. Зайди сейчас — и они сбегут.",
    }[stage]


def _pass():
    if not ON:
        return
    t = now()
    quiet = time.gmtime().tm_hour not in HOURS
    msgs = []
    with tx():
        for u in q("SELECT * FROM users WHERE id>0 AND banned=0 AND seen>0 AND seen<? AND stars>=? LIMIT 3000", t - DAY, MIN_LOOT):
            days = (t - max(u["seen"], START)) // DAY
            if days < 1:
                continue
            h = q1("SELECT * FROM heist WHERE user=?", u["id"])
            done = h["stage"] if h and h["seen"] == u["seen"] else 0
            if done >= BURN:
                continue
            kept = min(u["stars"], protected(u["id"]))
            loot = u["stars"] - kept
            if loot < MIN_LOOT:
                continue
            name = esc(u["name"] or "Игрок")
            if days >= BURN:   # взлом: горит всё, кроме купленного
                db.execute("UPDATE users SET stars=? WHERE id=?", (kept, u["id"]))
                event(u["id"], "heist", -loot)
                db.execute("INSERT OR REPLACE INTO heist(user,seen,stage,loot,kept,days,ts) VALUES(?,?,?,?,?,?,?)", (u["id"], u["seen"], BURN, loot, kept, days, t))
                msgs.append((u["id"], _text(BURN, name, loot, kept, days)))
                continue
            due = max((s for s in STAGES if s <= days), default=0)
            if due <= done or quiet:
                continue
            mute = "notif" in u.keys() and not u["notif"]
            if not mute:
                last = q1("SELECT ts FROM comeback_log WHERE user=? ORDER BY id DESC LIMIT 1", u["id"])
                if last and t - last["ts"] < 20 * 3600:   # сегодня уже звали подарком — не частим
                    continue
                if len(msgs) >= 40:   # не больше 40 писем за проход
                    continue
                msgs.append((u["id"], _text(due, name, loot, kept, days)))
            db.execute("INSERT OR REPLACE INTO heist(user,seen,stage,loot,kept,days,ts) VALUES(?,?,?,?,?,?,?)", (u["id"], u["seen"], due, loot, kept, days, t))
    for uid, text in msgs:
        notify(uid, text, promo="heist")


@app.get(R + "/heist")
def heist_state(uid=Depends(auth)):
    """Игрок вернулся: один раз рассказать, чем кончилось у сейфа, пока его не было."""
    out = {"rule": {"on": bool(ON), "days": BURN, "min": MIN_LOOT}}
    h = q1("SELECT * FROM heist WHERE user=?", uid)
    if not h:
        return out
    u = q1("SELECT seen FROM users WHERE id=?", uid)
    if u["seen"] == h["seen"]:   # ещё не «вернулся» (вход обновляет seen не чаще раза в минуту)
        return out
    with tx():
        db.execute("DELETE FROM heist WHERE user=?", (uid,))
    return dict(out, back={"burned": h["stage"] >= BURN, "stage": h["stage"], "loot": h["loot"], "kept": h["kept"], "days": h["days"]})


async def _loop():
    await asyncio.sleep(60)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _pass)
        except Exception as e:
            print("heist:", type(e).__name__, e, flush=True)
        await asyncio.sleep(min(900, max(20, DAY // 20)))


@app.on_event("startup")
async def _start():
    asyncio.create_task(_loop())
