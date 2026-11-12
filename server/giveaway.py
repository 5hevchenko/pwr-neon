"""Розыгрыши в канале игры. Владелец создаёт розыгрыш в админке, бот публикует пост в канале с кнопкой «Участвовать».
Условия: подписка на канал (бот проверяет через getChatMember, поэтому он должен быть админом канала) и аккаунт в игре
не ниже заданного уровня. Приз — игровые звёзды из банка (вид 'giveaway' в учёте банка).

Честность: при создании публикуем sha256(seed), seed держим в секрете. В конце победители — участники с наименьшим
sha256(seed:id); тех, кто к итогам отписался от канала, пропускаем по тому же порядку. Итоги раскрывают seed и список
участников, и любой может пересчитать победителей сам."""
import asyncio
import hashlib
import json
import secrets

from fastapi import Depends, Request

import app as A
from app import R, app, auth, db, err, esc, event, notify, now, q, q1, tx, user_brief
from admin import OWNERS, admin, log

db.executescript("""
CREATE TABLE IF NOT EXISTS gw(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, prize INTEGER, winners INTEGER, min_level INTEGER, start INTEGER,
  until INTEGER, seed TEXT, hash TEXT, chat TEXT, msg INTEGER DEFAULT 0, status TEXT DEFAULT 'open', result TEXT, by INTEGER);
CREATE TABLE IF NOT EXISTS gw_entry(gw INTEGER, user INTEGER, ts INTEGER, PRIMARY KEY(gw, user));
""")
MAX_TOTAL = 500_000        # общий приз одного розыгрыша
BANK_SHARE = 0.01          # и не больше этой доли банка
MEMBER = ("member", "administrator", "creator")


def channel():
    return A.kv_get("gw_channel", "") or ""


def nf(n):
    return f"{int(n):,}".replace(",", " ")


def _rank(seed, uid):
    return hashlib.sha256(f"{seed}:{uid}".encode()).hexdigest()


async def _is_member(chat, uid):
    try:
        r = await A.tg_call("getChatMember", chat_id=chat, user_id=uid)
    except Exception:
        return None
    if not r.get("ok"):
        return None
    m = r["result"]
    return m.get("status") in MEMBER or (m.get("status") == "restricted" and m.get("is_member"))


def _link(gid):
    return f"https://t.me/{A.franchise.face_name()}?start=gw_{gid}"


def _post_text(g):
    end = A.time.strftime("%d.%m %H:%M", A.time.gmtime(g["until"] + 3 * 3600))
    return (f"<b>Розыгрыш: {esc(g['title'])}</b>\n\n"
            f"Приз: <b>{nf(g['prize'])} ⭐</b> (игровые звёзды), победителей: <b>{g['winners']}</b>, каждому {nf(g['prize'] // g['winners'])} ⭐.\n"
            f"Условия: подписка на этот канал и аккаунт в игре" + (f" от {g['min_level']} уровня" if g["min_level"] > 1 else "") + ".\n"
            f"Итоги: {end} по Москве.\n\n"
            f"Честный выбор победителей. Хэш секретного числа: <code>{g['hash']}</code>. После итогов число опубликуем, и любой сможет проверить.")


def _view(g, uid=None):
    t = now()
    n = q1("SELECT COUNT(*) n FROM gw_entry WHERE gw=?", g["id"])["n"]
    out = {"id": g["id"], "title": g["title"], "prize": g["prize"], "winners": g["winners"], "each": g["prize"] // g["winners"], "minLevel": g["min_level"],
           "left": max(0, g["until"] - t), "until": g["until"], "hash": g["hash"], "status": g["status"], "count": n, "chat": g["chat"]}
    if uid is not None:
        out["joined"] = bool(q1("SELECT 1 FROM gw_entry WHERE gw=? AND user=?", g["id"], uid))
    if g["status"] == "done":
        res = json.loads(g["result"] or "{}")
        out["seed"] = g["seed"]
        out["entries"] = res.get("entries", [])
        out["skipped"] = res.get("skipped", [])
        wins = []
        for w in res.get("winners", []):
            u = q1("SELECT * FROM users WHERE id=?", w)
            if u:
                wins.append(user_brief(u))
        out["winnersList"] = wins
        out["winnerIds"] = res.get("winners", [])   # для проверки: список имён может быть короче, если аккаунт удалён
    return out


@app.get(R + "/gw/{gid}")
def gw_get(gid: int, uid=Depends(auth)):
    g = q1("SELECT * FROM gw WHERE id=?", gid) or err("Розыгрыш не найден")
    return _view(g, uid)


@app.post(R + "/gw/{gid}/join")
async def gw_join(gid: int, uid=Depends(auth)):
    g = q1("SELECT * FROM gw WHERE id=?", gid) or err("Розыгрыш не найден")
    if g["status"] != "open" or g["until"] <= now():
        err("Розыгрыш уже закончился")
    if q1("SELECT 1 FROM gw_entry WHERE gw=? AND user=?", gid, uid):
        return _view(g, uid)
    u = q1("SELECT xp, banned FROM users WHERE id=?", uid)
    if A.level(u["xp"]) < g["min_level"]:
        err(f"Участвовать можно с {g['min_level']} уровня. Сыграй пару раундов и возвращайся")
    m = await _is_member(g["chat"], uid)
    if m is None:
        err("Не получилось проверить подписку, попробуй через минуту")
    if not m:
        err("Сначала подпишись на канал")
    with tx():
        db.execute("INSERT OR IGNORE INTO gw_entry(gw,user,ts) VALUES(?,?,?)", (gid, uid, now()))
    return _view(g, uid)


async def _draw(g):
    entries = [r["user"] for r in q("SELECT e.user FROM gw_entry e JOIN users u ON u.id=e.user WHERE e.gw=? AND u.banned=0", g["id"])]
    order = sorted(entries, key=lambda u: _rank(g["seed"], u))
    winners, skipped = [], []
    for u in order:
        if len(winners) >= g["winners"]:
            break
        m = await _is_member(g["chat"], u)
        if m is False:
            skipped.append(u)
            continue
        winners.append(u)   # проверить не вышло (сбой Telegram) — в пользу игрока
    each = g["prize"] // g["winners"]
    with tx():
        if q1("SELECT status FROM gw WHERE id=?", g["id"])["status"] != "open":
            return
        for u in winners:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (each, u))
            event(u, "giveaway", each)
        db.execute("UPDATE gw SET status='done', result=? WHERE id=?", (json.dumps({"winners": winners, "skipped": skipped, "entries": sorted(entries)}), g["id"]))
    for u in winners:
        notify(u, f"Победа в розыгрыше «{esc(g['title'])}»: +{nf(each)} ⭐ уже на балансе")
    names = []
    for u in winners:
        r = q1("SELECT name, username FROM users WHERE id=?", u)
        names.append(("@" + esc(r["username"])) if r and r["username"] else esc(r["name"] if r else str(u)))
    text = (f"<b>Итоги розыгрыша «{esc(g['title'])}»</b>\n\nУчастников: {len(entries)}\n"
            + ("Победители:\n" + "\n".join(f"{i + 1}. {n}" for i, n in enumerate(names)) if names else "Победителей нет: никто не участвовал.")
            + f"\n\nСекретное число: <code>{g['seed']}</code>\nЕго sha256 совпадает с хэшем из поста. Победители: участники с наименьшим sha256(число:id), "
              f"участники без подписки на канал к итогам пропущены. Список участников и проверка в игре.")
    kb = {"inline_keyboard": [[{"text": "Проверить в игре", "url": _link(g["id"])}]]}
    try:
        await A.tg_call("sendMessage", chat_id=g["chat"], text=text, parse_mode="HTML", reply_markup=kb,
                        **({"reply_parameters": {"message_id": g["msg"], "allow_sending_without_reply": True}} if g["msg"] else {}))
    except Exception as e:
        print("gw post", e, flush=True)


async def _loop():
    await asyncio.sleep(35)
    while True:
        try:
            import wipe
            for g in ([] if wipe.frozen() else q("SELECT * FROM gw WHERE status='open' AND until<=?", now())):
                await _draw(g)
        except Exception as e:
            print("giveaway:", e, flush=True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _start():
    if not A.DEV:
        asyncio.create_task(_loop())


# ============================== админка ==============================
@app.get(R + "/admin/gw")
def admin_gw(aid=Depends(admin)):
    import bank
    cap = min(MAX_TOTAL, int(bank.bank_value() * BANK_SHARE))
    return {"channel": channel(), "canEdit": aid in OWNERS, "cap": cap, "list": [_view(g) for g in q("SELECT * FROM gw ORDER BY id DESC LIMIT 10")]}


@app.post(R + "/admin/gw/channel")
async def admin_gw_channel(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Только владелец")
    ch = str((await req.json()).get("channel", "")).strip()
    if ch.startswith("https://t.me/"):
        ch = "@" + ch.split("/")[-1]
    if not ch:
        err("Укажи канал: @имя или id")
    r = await A.tg_call("getChat", chat_id=ch)
    if not r.get("ok"):
        err("Канал не найден. Добавь бота в канал администратором и проверь @имя")
    me = await A.tg_call("getMe")
    m = await A.tg_call("getChatMember", chat_id=ch, user_id=me["result"]["id"]) if me.get("ok") else {}
    if not (m.get("ok") and m["result"].get("status") == "administrator"):
        err(f"Бот @{me.get('result', {}).get('username', '')} должен быть администратором канала с правом публиковать")
    cid = str(r["result"]["id"])
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('gw_channel',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (cid,))
        log(aid, "gw_channel", None, f"{ch} {cid}")
    return {"channel": cid, "title": r["result"].get("title", "")}


@app.post(R + "/admin/gw")
async def admin_gw_create(req: Request, aid=Depends(admin)):
    import bank
    if aid not in OWNERS:
        err("Создавать розыгрыши может только владелец")
    ch = channel() or err("Сначала укажи канал")
    b = await req.json()
    try:
        prize, winners, hours, lvl = int(b.get("prize")), int(b.get("winners")), int(b.get("hours")), int(b.get("minLevel", 2))
    except (TypeError, ValueError):
        err("Введи целые числа")
    title = str(b.get("title", "")).strip()[:60] or err("Название обязательно")
    cap = min(MAX_TOTAL, int(bank.bank_value() * BANK_SHARE))
    if not 1 <= winners <= 50:
        err("Победителей от 1 до 50")
    if not 1000 <= prize <= cap:
        err(f"Приз от 1 000 до {nf(cap)} ⭐")
    if prize // winners < 100:
        err("Каждому победителю не меньше 100 ⭐")
    if not 1 <= hours <= 24 * 14:
        err("Длительность от 1 часа до 14 дней")
    if not 1 <= lvl <= 50:
        err("Уровень от 1 до 50")
    seed = secrets.token_hex(16)
    t = now()
    with tx():
        cur = db.execute("INSERT INTO gw(title,prize,winners,min_level,start,until,seed,hash,chat,by) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (title, prize, winners, lvl, t, t + hours * 3600, seed, hashlib.sha256(seed.encode()).hexdigest(), ch, aid))
        gid = cur.lastrowid
        log(aid, "gw_create", None, f"#{gid} {title} {prize}/{winners} {hours}ч")
    g = q1("SELECT * FROM gw WHERE id=?", gid)
    r = await A.tg_call("sendMessage", chat_id=ch, text=_post_text(g), parse_mode="HTML",
                        reply_markup={"inline_keyboard": [[{"text": "Участвовать", "url": _link(gid)}]]})
    if not r.get("ok"):
        with tx():
            db.execute("UPDATE gw SET status='void' WHERE id=?", (gid,))
        err("Бот не смог опубликовать пост: " + str(r.get("description", ""))[:120])
    with tx():
        db.execute("UPDATE gw SET msg=? WHERE id=?", (r["result"]["message_id"], gid))
    return _view(q1("SELECT * FROM gw WHERE id=?", gid))


@app.post(R + "/admin/gw/{gid}/cancel")
def admin_gw_cancel(gid: int, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Только владелец")
    with tx():
        g = q1("SELECT status FROM gw WHERE id=?", gid) or err("нет такого")
        if g["status"] != "open":
            err("Розыгрыш уже закрыт")
        db.execute("UPDATE gw SET status='void' WHERE id=?", (gid,))
        log(aid, "gw_cancel", None, f"#{gid}")
    return {"ok": True}
