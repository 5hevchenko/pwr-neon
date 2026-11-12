"""Опросы в боте: сообщение всем игрокам с кнопками «Да»/«Нет» (callback pv:<id>:y|n), голос можно поменять до конца.
Анонимно для игроков: id храним только чтобы один человек = один голос. Через `hours` часов итоги — админам в бота.
Опрос создаётся строкой в таблице poll (sent=0) — цикл сам разошлёт его через бота каждого игрока (franchise.token_for)."""
import asyncio
import json
import re

from fastapi import Depends, Request

import app as A
from app import ADMINS, R, STEALTH, app, db, err, esc, notify, now, q, q1, tg_call, tx
from admin import admin, log

db.executescript("""
CREATE TABLE IF NOT EXISTS poll(id INTEGER PRIMARY KEY, text TEXT, yes TEXT, no TEXT, created INTEGER, ends INTEGER,
                                sent INTEGER DEFAULT 0, delivered INTEGER DEFAULT 0, done INTEGER DEFAULT 0, by INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS poll_vote(pid INTEGER, user INTEGER, choice TEXT, ts INTEGER, PRIMARY KEY(pid, user));
""")
# где показывать: плашка в игре / сообщение в боте (старые опросы — только бот); must — плашку нельзя закрыть, пока не проголосуешь
for _c, _d in (("ingame", 0), ("bot", 1), ("must", 0)):
    try:
        db.execute(f"ALTER TABLE poll ADD COLUMN {_c} INTEGER DEFAULT {_d}")
    except Exception:
        pass
ALLOWED = ["message", "pre_checkout_query", "callback_query"]


def _counts(pid):
    r = q1("SELECT COALESCE(SUM(choice='y'),0) y, COALESCE(SUM(choice='n'),0) n FROM poll_vote WHERE pid=?", pid)
    return r["y"], r["n"]


async def _send(p):
    fr = __import__("franchise")
    kb = {"inline_keyboard": [[{"text": p["yes"], "callback_data": f"pv:{p['id']}:y"}, {"text": p["no"], "callback_data": f"pv:{p['id']}:n"}]]}
    ids = [r["id"] for r in q("SELECT id FROM users WHERE banned=0")]
    ok = 0
    for uid in ids:
        try:
            tok = fr.token_for(uid)
            r = await tg_call("sendMessage", _token=tok, chat_id=uid, text=p["text"], parse_mode="HTML", reply_markup=kb)
            if not r.get("ok") and tok != A.TOKEN:   # бот-франшиза не смог — через главного
                r = await tg_call("sendMessage", _token=A.TOKEN, chat_id=uid, text=p["text"], parse_mode="HTML", reply_markup=kb)
            ok += bool(r.get("ok"))
        except Exception as e:
            print("poll send", uid, e, flush=True)
        await asyncio.sleep(0.05)
    with tx():
        db.execute("UPDATE poll SET delivered=? WHERE id=?", (ok, p["id"]))
    print("poll", p["id"], "доставлено", ok, "из", len(ids), flush=True)


def _finish(p):
    y, n = _counts(p["id"])
    tot = y + n
    pct = (lambda x: f"{round(x * 100 / tot)}%") if tot else (lambda x: "—")
    with tx():
        db.execute("UPDATE poll SET done=1 WHERE id=?", (p["id"],))
    text = (f"📊 <b>Итоги опроса</b>\n\n{p['text'].split(chr(10))[0]}\n\n"
            f"{esc(p['yes'])}: <b>{y}</b> ({pct(y)})\n{esc(p['no'])}: <b>{n}</b> ({pct(n)})\n\n"
            f"Проголосовали {tot} из {_reach(p)} {'видевших опрос' if p.get('ingame') else 'получивших'}.")
    for a in ADMINS:
        if a not in STEALTH:   # в режиме секретности админу не шлём
            notify(a, text)


def _reach(p):
    """Сколько игроков могли проголосовать: в игре — заходили за время опроса, в боте — кому доставлено."""
    if p.get("ingame"):
        seen = q1("SELECT COUNT(*) c FROM users WHERE banned=0 AND seen>=?", p["created"])["c"]
        return max(seen, p["delivered"] or 0)
    return p["delivered"] or 0


def _vote(pid, uid, ch):
    """Голос (из игры или кнопкой в боте). Вернёт прошлый выбор или None."""
    with A.LOCK:
        old = q1("SELECT choice FROM poll_vote WHERE pid=? AND user=?", pid, uid)
        db.execute("INSERT INTO poll_vote(pid,user,choice,ts) VALUES(?,?,?,?) ON CONFLICT(pid,user) DO UPDATE SET choice=excluded.choice, ts=excluded.ts",
                   (pid, uid, ch, now()))
    return old["choice"] if old else None


def _title(p):
    """Первая строка текста без тегов — заголовок опроса."""
    return re.sub(r"<[^>]+>", "", (p["text"] or "").split("\n")[0]).replace("📊", "").strip()


def public(uid):
    """Для /me: активные опросы «в игре» с моим голосом; итоги в % — только после голоса."""
    out = []
    for p in q("SELECT * FROM poll WHERE ingame=1 AND done=0 AND ends>? ORDER BY id DESC LIMIT 3", now()):
        mine = q1("SELECT choice FROM poll_vote WHERE pid=? AND user=?", p["id"], uid)
        d = {"id": p["id"], "text": p["text"], "yes": p["yes"], "no": p["no"], "ends": p["ends"], "my": mine["choice"] if mine else None, "must": p["must"]}
        if mine:
            d["y"], d["n"] = _counts(p["id"])
        out.append(d)
    return out


@app.get(R + "/poll/active")
def poll_active(uid=Depends(A.auth)):
    """Лёгкая проверка раз в минуту из игры — чтобы новый опрос всплыл, не дожидаясь перезахода."""
    return {"polls": public(uid)}


@app.post(R + "/poll/vote")
async def poll_vote(req: Request, uid=Depends(A.auth)):
    b = await req.json()
    pid, ch = int(b.get("id", 0)), b.get("ch")
    p = q1("SELECT * FROM poll WHERE id=?", pid)
    if not p or ch not in ("y", "n"):
        err("опрос не найден")
    if p["done"] or now() >= p["ends"]:
        err("опрос уже закончился")
    _vote(pid, uid, ch)
    y, n = _counts(pid)
    return {"my": ch, "y": y, "n": n}


@app.get(R + "/admin/polls")
def admin_polls(aid=Depends(admin)):
    out = []
    for p in q("SELECT * FROM poll ORDER BY id DESC LIMIT 20"):
        p = dict(p)
        y, n = _counts(p["id"])
        hours = [dict(r) for r in q("SELECT (ts-?)/3600 h, SUM(choice='y') y, SUM(choice='n') n FROM poll_vote WHERE pid=? GROUP BY h ORDER BY h", p["created"], p["id"])]
        last = [dict(r) for r in q("SELECT v.choice, v.ts, u.name, u.xp FROM poll_vote v JOIN users u ON u.id=v.user WHERE v.pid=? ORDER BY v.ts DESC LIMIT 12", p["id"])]
        out.append({"id": p["id"], "title": _title(p), "text": p["text"], "yes": p["yes"], "no": p["no"], "created": p["created"], "ends": p["ends"],
                    "active": not p["done"] and p["ends"] > now(), "ingame": p["ingame"], "bot": p["bot"], "must": p["must"], "y": y, "n": n,
                    "reach": _reach(p), "hours": hours, "last": last})
    return {"polls": out, "now": now()}


@app.post(R + "/admin/polls")
async def admin_poll_new(req: Request, aid=Depends(admin)):
    b = await req.json()
    title = str(b.get("title", "")).strip()[:150]
    desc = str(b.get("desc", "")).strip()[:800]
    yes, no = str(b.get("yes", "") or "Да").strip()[:30], str(b.get("no", "") or "Нет").strip()[:30]
    hours = float(b.get("hours", 24) or 24)
    ingame, bot, must = bool(b.get("ingame", True)), bool(b.get("bot", False)), bool(b.get("must", False))
    if len(title) < 3:
        err("напиши вопрос")
    if not 0.1 <= hours <= 24 * 14:
        err("длительность — от 6 минут до 14 дней")
    if not ingame and not bot:
        err("выбери, где показывать: в игре и/или в боте")
    t = now()
    text = f"📊 <b>{esc(title)}</b>" + (f"\n\n{esc(desc)}" if desc else "") + "\n\n🔒 Опрос анонимный."
    with tx():
        cur = db.execute("INSERT INTO poll(text,yes,no,created,ends,sent,by,ingame,bot,must) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (text, yes, no, t, t + int(hours * 3600), 0 if bot else 1, aid, int(ingame), int(bot), int(must and ingame)))
    log(aid, "poll", f"{cur.lastrowid}: {title}")
    return {"id": cur.lastrowid}


@app.post(R + "/admin/polls/{pid}/end")
def admin_poll_end(pid: int, aid=Depends(admin)):
    p = q1("SELECT * FROM poll WHERE id=?", pid)
    if not p:
        err("опрос не найден")
    if p["done"]:
        err("опрос уже закончен")
    with tx():
        db.execute("UPDATE poll SET ends=? WHERE id=?", (now(), pid))   # цикл через ≤30 с подведёт итоги и пришлёт админам
    log(aid, "poll_end", str(pid))
    return {"ok": True}


async def on_callback(cq):
    """Нажатие кнопки под опросом (из главного бота или франшизы — ответ уходит тем же ботом через CUR_TOKEN)."""
    data = cq.get("data") or ""
    if not data.startswith("pv:"):
        return await tg_call("answerCallbackQuery", callback_query_id=cq["id"])
    try:
        _, pid, ch = data.split(":")
        pid = int(pid)
    except ValueError:
        return await tg_call("answerCallbackQuery", callback_query_id=cq["id"])
    p = q1("SELECT * FROM poll WHERE id=?", pid)
    if not p or ch not in ("y", "n"):
        return await tg_call("answerCallbackQuery", callback_query_id=cq["id"], text="Опрос не найден")
    if p["done"] or now() >= p["ends"]:
        return await tg_call("answerCallbackQuery", callback_query_id=cq["id"], text="Опрос уже закончился", show_alert=True)
    old = _vote(pid, cq["from"]["id"], ch)
    label = p["yes"] if ch == "y" else p["no"]
    await tg_call("answerCallbackQuery", callback_query_id=cq["id"], show_alert=True,
                  text=(f"Голос изменён: {label}" if old and old != ch else f"Голос учтён: {label}") + "\nОпрос анонимный. Передумаешь — нажми другую кнопку.")


async def _ensure_webhooks():
    """Один раз: дочерним ботам — получать нажатия кнопок (callback_query)."""
    if A.kv_get("wh_cb"):
        return
    fr = __import__("franchise")
    for b in list(fr.BOTS.values()):
        if b["status"] != "on":
            continue
        r = await tg_call("setWebhook", _token=b["token"], url=f"{A.APP_URL}api/tg/{b['id']}", secret_token=b["secret"], allowed_updates=ALLOWED)
        if not r.get("ok"):
            print("poll webhook", b["id"], r, flush=True)
        await asyncio.sleep(0.2)
    with A.LOCK:
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('wh_cb','1')")


async def poll_loop():
    await asyncio.sleep(25)
    try:
        await _ensure_webhooks()
    except Exception as e:
        print("poll webhooks", e, flush=True)
    while True:
        try:
            for p in q("SELECT * FROM poll WHERE sent=0"):
                with tx():
                    db.execute("UPDATE poll SET sent=1 WHERE id=?", (p["id"],))
                asyncio.create_task(_send(dict(p)))
            for p in q("SELECT * FROM poll WHERE sent=1 AND done=0 AND ends<=?", now()):
                await asyncio.get_running_loop().run_in_executor(None, _finish, dict(p))
        except Exception as e:
            print("poll", e, flush=True)
        await asyncio.sleep(30)


@A.app.on_event("startup")
async def _poll_start():
    asyncio.create_task(poll_loop())
