"""«Стопка» — игра на ловкость: блок ездит туда-сюда, тап — ставишь его на башню, что свисает — отрезается.
Бесплатно и без ставок. Недельный турнир: лучший результат недели (пн–вс по Москве), призы скромные и только тем,
кто построил хотя бы MIN_SCORE этажей — без тренировки не взять.
Рекорд не подделать: сервер выдаёт стартовые положения блоков, клиент присылает моменты тапов (мс от появления блока),
сервер сам пересчитывает башню по тем же целочисленным формулам, что и клиент (stack.js)."""
import asyncio
import json
import secrets

from fastapi import Depends, Request

from app import R, app, auth, db, err, event, level, notify, now, q, q1, tx, user_brief

# --- поле и сложность (те же числа уходят клиенту в /stack/start) ---
F = 1000            # ширина поля
W0 = 340            # стартовая ширина блока
OVER = 160          # насколько блок выезжает за край поля с каждой стороны
PERFECT = 8         # «идеально» — промах не больше 8 из 1000; блок встаёт ровно, ширина не теряется
GROW_AFTER = 3      # 3 идеальных подряд — блок шире на GROW
GROW = 14
P0, PMIN, PSTEP = 2400, 900, 15    # период «туда-обратно», мс: 2400 → быстрее на 15 мс каждый этаж, до 900
MIN_E = 140         # быстрее 140 мс после прошлого тапа — нечеловеческая скорость
MAX_LEVELS = 400

# --- турнир ---
TZ = 3 * 3600
MIN_SCORE = 40                                            # меньше — призов нет (без тренировки не дойти)
PRIZE_LEVEL = 5                                           # призы — с 5 уровня (против твинков)
BOT_PERFECT = 0.75                                        # идеальных больше 75% на длинной башне — так играет скрипт, не человек
PRIZES = [5000, 3000, 2000, 1000, 1000, 500, 500, 500, 500, 500]   # места 1–10, ⭐ (всего 14 500 в неделю)

db.executescript("""
CREATE TABLE IF NOT EXISTS stack_runs(id INTEGER PRIMARY KEY, user INTEGER, off TEXT, ts INTEGER, done INTEGER DEFAULT 0, score INTEGER);
CREATE INDEX IF NOT EXISTS stack_runs_user ON stack_runs(user, ts);
CREATE TABLE IF NOT EXISTS stack_best(user INTEGER, week INTEGER, score INTEGER, ts INTEGER, PRIMARY KEY(user, week));
CREATE INDEX IF NOT EXISTS stack_best_week ON stack_best(week, score DESC, ts);
CREATE TABLE IF NOT EXISTS stack_paid(week INTEGER PRIMARY KEY, ts INTEGER, winners TEXT);
""")
CFG = {"F": F, "W0": W0, "OVER": OVER, "PERFECT": PERFECT, "GROW_AFTER": GROW_AFTER, "GROW": GROW,
       "P0": P0, "PMIN": PMIN, "PSTEP": PSTEP, "MIN_E": MIN_E}


def week_of(t):
    """Номер недели, недели начинаются в понедельник 00:00 по Москве (1 января 1970 — четверг, отсюда +3)."""
    return ((t + TZ) // 86400 + 3) // 7


def week_end(w):
    return (w * 7 - 3 + 7) * 86400 - TZ


def period(i):
    return max(PMIN, P0 - PSTEP * i)


def simulate(off, taps):
    """Башня по тапам → (этажей, из них идеальных). Только целые числа — совпадает с клиентом бит в бит."""
    pl, pw, streak, score, perfect = (F - W0) // 2, W0, 0, 0, 0
    for i, e in enumerate(taps[:MAX_LEVELS], start=1):
        if not isinstance(e, int) or e < MIN_E or e > 60000:
            break
        w = pw
        d = F + 2 * OVER - w
        s = (off[i - 1] * 2 * d // 10000 + e * 2 * d // period(i)) % (2 * d)
        x = -OVER + (s if s < d else 2 * d - s)
        if abs(x - pl) <= PERFECT:
            streak += 1
            perfect += 1
            if streak >= GROW_AFTER:
                pw = min(W0, pw + GROW)
        else:
            lo, hi = max(x, pl), min(x + w, pl + pw)
            if hi - lo <= 0:
                break
            pl, pw, streak = lo, hi - lo, 0
        score += 1
    return score, perfect


def _top(w, n=10):
    return [{"user": user_brief(u), "score": r["score"]}
            for r in q("SELECT * FROM stack_best WHERE week=? ORDER BY score DESC, ts LIMIT ?", w, n)
            if (u := q1("SELECT * FROM users WHERE id=?", r["user"])) and not u["banned"]]


@app.get(R + "/stack")
def stack_home(uid=Depends(auth)):
    t = now()
    w = week_of(t)
    me = q1("SELECT score FROM stack_best WHERE user=? AND week=?", uid, w)
    ever = q1("SELECT MAX(score) m FROM stack_best WHERE user=?", uid)["m"] or 0
    rank = None
    if me:
        rank = 1 + q1("SELECT COUNT(*) n FROM stack_best WHERE week=? AND (score>? OR (score=? AND ts<(SELECT ts FROM stack_best WHERE user=? AND week=?)))",
                      w, me["score"], me["score"], uid, w)["n"]
    last = q1("SELECT * FROM stack_paid ORDER BY week DESC LIMIT 1")
    return {"week": me["score"] if me else 0, "best": ever, "rank": rank, "top": _top(w), "prizes": PRIZES, "min": MIN_SCORE, "minLevel": PRIZE_LEVEL,
            "endsIn": week_end(w) - t, "last": json.loads(last["winners"]) if last else []}


@app.post(R + "/stack/start")
def stack_start(uid=Depends(auth)):
    t = now()
    with tx():
        r = q1("SELECT ts FROM stack_runs WHERE user=? ORDER BY id DESC LIMIT 1", uid)
        if r and t - r["ts"] < 1:
            err("секунду…")
        off = [secrets.randbelow(10000) for _ in range(MAX_LEVELS)]
        db.execute("DELETE FROM stack_runs WHERE user=? AND done=0", (uid,))   # одна незаконченная попытка на игрока
        cur = db.execute("INSERT INTO stack_runs(user,off,ts) VALUES(?,?,?)", (uid, json.dumps(off), t))
    return {"id": cur.lastrowid, "off": off, "cfg": CFG}


@app.post(R + "/stack/finish")
async def stack_finish(req: Request, uid=Depends(auth)):
    b = await req.json()
    taps = b.get("taps")
    if not isinstance(taps, list) or len(taps) > MAX_LEVELS + 1:
        err("неверные данные")
    taps = [int(x) if isinstance(x, (int, float)) and x == x else -1 for x in taps]
    t = now()
    with tx():
        r = q1("SELECT * FROM stack_runs WHERE id=? AND user=? AND done=0", int(b.get("id") or 0), uid)
        if not r:
            err("попытка уже засчитана — начни новую")
        if sum(x for x in taps if x > 0) > (t - r["ts"] + 2) * 1000 or t - r["ts"] > 3600:   # быстрее реального времени — подделка
            db.execute("UPDATE stack_runs SET done=1, score=0 WHERE id=?", (r["id"],))
            err("попытка не засчитана")
        score, perfect = simulate(json.loads(r["off"]), taps)
        bot = score >= 25 and perfect > score * BOT_PERFECT
        if bot:   # результат не в зачёт; админ увидит в журнале действий
            print(f"stack: bot? user={uid} score={score} perfect={perfect}", flush=True)
            score = 0
        db.execute("UPDATE stack_runs SET done=1, score=? WHERE id=?", (score, r["id"]))
        w = week_of(t)
        old = q1("SELECT score FROM stack_best WHERE user=? AND week=?", uid, w)
        new_best = score > 0 and (not old or score > old["score"])
        if new_best:
            db.execute("INSERT INTO stack_best(user,week,score,ts) VALUES(?,?,?,?) ON CONFLICT(user,week) DO UPDATE SET score=excluded.score, ts=excluded.ts",
                       (uid, w, score, t))
    return {"score": score, "newBest": new_best, "rejected": bot, **stack_home(uid)}


def _pay(w):
    """Призы за прошедшую неделю (идемпотентно)."""
    msgs = []
    with tx():
        if q1("SELECT 1 FROM stack_paid WHERE week=?", w):
            return
        winners = []
        rows = [r for r in q("SELECT b.*, u.xp FROM stack_best b JOIN users u ON u.id=b.user WHERE b.week=? AND b.score>=? AND u.banned=0 "
                             "ORDER BY b.score DESC, b.ts", w, MIN_SCORE) if level(r["xp"]) >= PRIZE_LEVEL][:len(PRIZES)]
        for i, r in enumerate(rows):
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (PRIZES[i], r["user"]))
            event(r["user"], "stack", PRIZES[i])
            u = q1("SELECT * FROM users WHERE id=?", r["user"])
            winners.append({"user": user_brief(u), "score": r["score"], "prize": PRIZES[i]})
            msgs.append((r["user"], f"🏗 «Стопка»: <b>{i + 1} место</b> за неделю ({r['score']} этажей) — +{PRIZES[i]} ⭐ (игровых)!"))
        db.execute("INSERT INTO stack_paid(week,ts,winners) VALUES(?,?,?)", (w, now(), json.dumps(winners, ensure_ascii=False)))
    for uid, text in msgs:
        notify(uid, text)


async def stack_loop():
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _pay, week_of(now()) - 1)
            with tx():   # старые попытки больше не нужны
                db.execute("DELETE FROM stack_runs WHERE ts<?", (now() - 86400,))
        except Exception as e:
            print("stack:", e, flush=True)
        await asyncio.sleep(300)


@app.on_event("startup")
async def _stack_start():
    asyncio.create_task(stack_loop())
