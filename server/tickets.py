"""Тикеты поддержки: игрок пишет из профиля («Поддержка»), переписка в тикете; админы (ADMINS — владельцы и все, кому
выдали права) получают каждое сообщение игрока в бота с кнопкой, открывающей тикет (?aticket=ID), отвечают во вкладке
«Тикеты» админки. Игрок видит ответ как «Поддержка» (без имени админа) — в боте, во «входящих» и красной точкой в профиле.
Статусы: open — ждёт поддержку, answered — ждёт игрока (через AUTO_CLOSE без ответа закрывается), closed."""
import asyncio

from fastapi import Depends, Request

import app as A
from app import ADMINS, R, STEALTH, app, auth, db, err, esc, notify, now, q, q1, tx, user_brief
from admin import admin, log

TOPICS = {"pay": "Покупка звёзд", "bug": "Ошибка в игре", "gift": "Подарки и баланс", "acc": "Аккаунт и бан", "other": "Другое"}


def _player_topics():
    """Тему про покупки показываем, только пока хоть что-то продаётся. Старые обращения с этой темой остаются читаемыми."""
    import shop
    return TOPICS if any(shop.sale_on(k) for k in shop.SALE_KEYS) else {k: v for k, v in TOPICS.items() if k != "pay"}

MAX_OPEN = 3            # открытых тикетов у игрока одновременно
DAY_NEW = 6             # новых тикетов в сутки
MSG_GAP = 5             # секунд между сообщениями игрока (антифлуд)
TEXT_MAX = 2000
AUTO_CLOSE = 3 * 86400  # ответили, игрок молчит — закрываем

db.executescript("""
CREATE TABLE IF NOT EXISTS ticket(id INTEGER PRIMARY KEY, user INTEGER, topic TEXT, status TEXT DEFAULT 'open', created INTEGER,
                                  updated INTEGER, unread_user INTEGER DEFAULT 0, closed_by INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ticket_user ON ticket(user, updated);
CREATE INDEX IF NOT EXISTS ticket_status ON ticket(status, updated);
CREATE TABLE IF NOT EXISTS ticket_msg(id INTEGER PRIMARY KEY, tid INTEGER, user INTEGER, staff INTEGER DEFAULT 0, text TEXT, ts INTEGER);
CREATE INDEX IF NOT EXISTS ticket_msg_tid ON ticket_msg(tid, id);
""")


def _text(body):
    t = str((body or {}).get("text", "")).strip()
    t = "\n".join(" ".join(x.split()) for x in t.splitlines()).strip()
    if len(t) < 3:
        err("напиши хотя бы пару слов")
    return t[:TEXT_MAX]


def _url(param, tid):
    return f"{A.APP_URL}?{param}={tid}"


def _to_admins(tid, uid, text, new):
    u = q1("SELECT name, username FROM users WHERE id=?", uid)
    t = q1("SELECT topic FROM ticket WHERE id=?", tid)
    who = esc(u["name"] if u else "?") + (f" (@{esc(u['username'])})" if u and u["username"] else "") + f" · id {uid}"
    head = f"🎫 <b>Новый тикет #{tid}</b>" if new else f"💬 <b>Тикет #{tid}</b> — новое сообщение"
    msg = f"{head} · {esc(TOPICS.get(t['topic'], ''))}\n{who}\n\n{esc(text[:1500])}"
    for a in list(ADMINS):
        if a != uid and a not in STEALTH:   # в режиме секретности админу не шлём
            notify(a, msg, url=_url("aticket", tid))


def me_info(uid):
    out = {"unread": q1("SELECT COUNT(*) n FROM ticket WHERE user=? AND unread_user=1", uid)["n"]}
    if uid in ADMINS:
        out["open"] = q1("SELECT COUNT(*) n FROM ticket WHERE status='open'")["n"]
    return out


def _thread(tid, staff_view):
    out = []
    for m in q("SELECT * FROM ticket_msg WHERE tid=? ORDER BY id", tid):
        x = {"id": m["id"], "text": m["text"], "ts": m["ts"], "staff": bool(m["staff"])}
        if staff_view and m["staff"]:
            x["by"] = "Админ"   # в тикетах имя администратора не показываем
        out.append(x)
    return out


def _row(t):
    last = q1("SELECT text, staff FROM ticket_msg WHERE tid=? ORDER BY id DESC LIMIT 1", t["id"])
    return {"id": t["id"], "topic": t["topic"], "topicTitle": TOPICS.get(t["topic"], t["topic"]), "status": t["status"],
            "created": t["created"], "updated": t["updated"], "unread": bool(t["unread_user"]),
            "last": (last["text"][:120] if last else ""), "lastStaff": bool(last and last["staff"])}


# ============================== игрок ==============================
@app.get(R + "/tickets")
def my_tickets(uid=Depends(auth)):
    return {"items": [_row(t) for t in q("SELECT * FROM ticket WHERE user=? ORDER BY status='closed', updated DESC LIMIT 30", uid)],
            "topics": _player_topics(), "maxOpen": MAX_OPEN}


@app.post(R + "/tickets")
async def new_ticket(req: Request, uid=Depends(auth)):
    body = await req.json()
    topic = str(body.get("topic", ""))
    if topic not in TOPICS:
        err("выбери тему")
    text, t = _text(body), now()
    with tx():
        if q1("SELECT COUNT(*) n FROM ticket WHERE user=? AND status!='closed'", uid)["n"] >= MAX_OPEN:
            err(f"у тебя уже {MAX_OPEN} открытых тикета — дождись ответа или закрой старый")
        if q1("SELECT COUNT(*) n FROM ticket WHERE user=? AND created>=?", uid, t - 86400)["n"] >= DAY_NEW:
            err("слишком много тикетов за сутки — напиши в уже открытый")
        tid = db.execute("INSERT INTO ticket(user,topic,status,created,updated) VALUES(?,?,'open',?,?)", (uid, topic, t, t)).lastrowid
        db.execute("INSERT INTO ticket_msg(tid,user,staff,text,ts) VALUES(?,?,0,?,?)", (tid, uid, text, t))
    _to_admins(tid, uid, text, True)
    return {"ok": True, "id": tid}


def _mine(tid, uid):
    t = q1("SELECT * FROM ticket WHERE id=? AND user=?", tid, uid)
    return t or err("тикет не найден", 404)


@app.get(R + "/tickets/{tid}")
def get_ticket(tid: int, uid=Depends(auth)):
    t = _mine(tid, uid)
    if t["unread_user"]:
        with tx():
            db.execute("UPDATE ticket SET unread_user=0 WHERE id=?", (tid,))
    return {**_row(dict(t)), "unread": False, "msgs": _thread(tid, False)}


@app.post(R + "/tickets/{tid}/msg")
async def ticket_msg(tid: int, req: Request, uid=Depends(auth)):
    text, t = _text(await req.json()), now()
    with tx():
        tk = _mine(tid, uid)
        if tk["status"] == "closed":
            err("тикет закрыт — создай новый")
        last = q1("SELECT MAX(ts) t FROM ticket_msg WHERE tid=? AND user=? AND staff=0", tid, uid)["t"]
        if last and t - last < MSG_GAP:
            err("не так быстро — подожди пару секунд")
        db.execute("INSERT INTO ticket_msg(tid,user,staff,text,ts) VALUES(?,?,0,?,?)", (tid, uid, text, t))
        db.execute("UPDATE ticket SET status='open', updated=?, unread_user=0 WHERE id=?", (t, tid))
    _to_admins(tid, uid, text, False)
    return {"ok": True}


@app.post(R + "/tickets/{tid}/close")
def close_ticket(tid: int, uid=Depends(auth)):
    with tx():
        _mine(tid, uid)
        db.execute("UPDATE ticket SET status='closed', updated=?, unread_user=0, closed_by=? WHERE id=?", (now(), uid, tid))
    return {"ok": True}


# ============================== админка ==============================
@app.get(R + "/admin/tickets")
def admin_tickets(status: str = "open", aid=Depends(admin)):
    if status not in ("open", "answered", "closed"):
        status = "open"
    items = []
    for t in q("SELECT * FROM ticket WHERE status=? ORDER BY updated " + ("ASC" if status == "open" else "DESC") + " LIMIT 100", status):
        u = q1("SELECT * FROM users WHERE id=?", t["user"])
        items.append({**_row(dict(t)), "user": user_brief(u) if u else {"id": t["user"], "name": "?"}})
    cnt = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) n FROM ticket GROUP BY status")}
    return {"items": items, "counts": cnt, "topics": TOPICS}


def _any(tid):
    return q1("SELECT * FROM ticket WHERE id=?", tid) or err("тикет не найден", 404)


@app.get(R + "/admin/tickets/{tid}")
def admin_ticket(tid: int, aid=Depends(admin)):
    t = _any(tid)
    u = q1("SELECT * FROM users WHERE id=?", t["user"])
    other = q1("SELECT COUNT(*) n FROM ticket WHERE user=? AND id!=?", t["user"], tid)["n"]
    return {**_row(dict(t)), "user": {**(user_brief(u) if u else {"id": t["user"], "name": "?"}),
                                      "stars": u["stars"] if u else 0, "banned": bool(u and u["banned"])},
            "others": other, "msgs": _thread(tid, True)}


@app.post(R + "/admin/tickets/{tid}/reply")
async def admin_reply(tid: int, req: Request, aid=Depends(admin)):
    text, t = _text(await req.json()), now()
    with tx():
        tk = _any(tid)
        db.execute("INSERT INTO ticket_msg(tid,user,staff,text,ts) VALUES(?,?,1,?,?)", (tid, aid, text, t))
        db.execute("UPDATE ticket SET status='answered', updated=?, unread_user=1 WHERE id=?", (t, tid))
        log(aid, "ticket_reply", tk["user"], f"#{tid}: {text[:150]}")
    notify(tk["user"], f"🎫 <b>Ответ поддержки</b> · тикет #{tid}\n\n{esc(text[:1500])}", url=_url("ticket", tid))
    return {"ok": True}


@app.post(R + "/admin/tickets/{tid}/status")
async def admin_status(tid: int, req: Request, aid=Depends(admin)):
    st = str((await req.json()).get("status", ""))
    if st not in ("open", "closed"):
        err("неверный статус")
    with tx():
        tk = _any(tid)
        db.execute("UPDATE ticket SET status=?, updated=?, closed_by=? WHERE id=?", (st, now(), aid if st == "closed" else 0, tid))
        log(aid, "ticket_" + st, tk["user"], f"#{tid}")
    return {"ok": True}


async def tickets_loop():
    await asyncio.sleep(60)
    while True:
        try:
            with tx():
                db.execute("UPDATE ticket SET status='closed', closed_by=-1 WHERE status='answered' AND updated<?", (now() - AUTO_CLOSE,))
        except Exception as e:
            print("tickets", e, flush=True)
        await asyncio.sleep(3600)


@app.on_event("startup")
async def _tickets_start():
    asyncio.create_task(tickets_loop())
