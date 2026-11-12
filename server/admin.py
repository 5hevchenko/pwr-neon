"""Админ-панель: доступ только у Telegram id из ADMIN_IDS. Чужим отвечаем 404, будто маршрута нет."""
import asyncio
import base64
import os
import secrets
import shutil
import time

from fastapi import Depends, Request

import random
import re

import economy as E
from app import (ADMINS, BANNED, DB_PATH, GAME_KINDS, R, STEALTH, _PROMO, app, auth, bal, cancel_trades_with, db, err, esc, event, gift_out,
                 kv_get, notify, now, promo, q, q1, tg_call, tx, unpin, user_brief, APP_URL)

db.executescript("""
CREATE TABLE IF NOT EXISTS admin_log(id INTEGER PRIMARY KEY, ts INTEGER, admin INTEGER, action TEXT, target INTEGER, detail TEXT);
""")
STARTED = time.time()
MAX_ADJUST = 100_000_000


# владельцы — из ADMIN_IDS (.env): только они выдают и снимают админку; выданные админы хранятся в базе
OWNERS = frozenset(ADMINS)
db.execute("CREATE TABLE IF NOT EXISTS admins(user INTEGER PRIMARY KEY, by INTEGER, ts INTEGER)")
ADMINS.update(r["user"] for r in q("SELECT user FROM admins"))


def admin(uid=Depends(auth)):
    if uid not in ADMINS:
        err("Not Found", 404)
    return uid


# Действия, влияющие на экономику и шансы: копия уходит в публичный журнал. Команд очистки у него нет.
PUB_ACTIONS = {"stars", "gift", "gift-remove", "keys", "comp", "cosm", "undo", "promo", "event", "odds", "feecfg", "claw", "game",
               "flash_start", "flash_stop", "flashcfg", "refcfg", "paycfg", "frcfg", "wipecfg", "db_import", "shop", "adminlog_clear", "actlog_clear"}
db.execute("CREATE TABLE IF NOT EXISTS pub_journal(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, action TEXT, target INTEGER, detail TEXT)")


def log(aid, action, target=None, detail="", undo=None):
    """Запись в журнал админа. undo — как отменить действие (ops.py → «Отменить» в журнале)."""
    if action in PUB_ACTIONS:
        db.execute("INSERT INTO pub_journal(ts,action,target,detail) VALUES(?,?,?,?)", (now(), action, target if isinstance(target, int) else None, str(detail)[:300]))
    if undo is None:
        db.execute("INSERT INTO admin_log(ts,admin,action,target,detail) VALUES(?,?,?,?,?)", (now(), aid, action, target, detail))
    else:
        import json as _j
        db.execute("INSERT INTO admin_log(ts,admin,action,target,detail,undo) VALUES(?,?,?,?,?,?)", (now(), aid, action, target, detail, _j.dumps(undo)))


# ---------------- «режим секретности» (защита от подсматривания + мьют уведомлений) ----------------
# Пока режим включён: клиент прячет всю админскую разметку, а сервер не шлёт этому админу служебные
# уведомления (тикеты, идеи, итоги опросов, авто-отключения франшиз). НИЧЕГО не удаляется и не фальсифицируется:
# admin_log и actlog пишутся как обычно, у других админов их уведомления идут. Состояние хранится в таблице и
# переживает перезапуск; флаг STEALTH импортируется в app.py и модули рассылок.
db.execute("CREATE TABLE IF NOT EXISTS admin_stealth(user INTEGER PRIMARY KEY, ts INTEGER)")
STEALTH.update(r["user"] for r in q("SELECT user FROM admin_stealth"))


@app.post(R + "/admin/stealth")
def stealth_set(body: dict, aid=Depends(admin)):
    on = bool(body.get("on"))
    if on:
        db.execute("INSERT OR REPLACE INTO admin_stealth(user,ts) VALUES(?,?)", (aid, now()))
        STEALTH.add(aid)
    else:
        db.execute("DELETE FROM admin_stealth WHERE user=?", (aid,))
        STEALTH.discard(aid)
    log(aid, "stealth", detail=str(int(on)))
    return {"ok": True, "on": on}


def _mem():
    m = {"MemTotal": 0, "MemAvailable": 0, "SwapTotal": 0, "SwapFree": 0}   # не Linux (Windows) — нули
    try:
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            m[k] = int(v.split()[0]) * 1024
    except OSError:
        pass
    return m


def _rss():
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


@app.get(R + "/admin/stats")
def stats(aid=Depends(admin)):
    import bank
    t = now()
    sums = lambda since: {r["kind"]: {"n": r["n"], "sum": r["s"]} for r in q(
        "SELECT kind, COUNT(*) n, SUM(delta) s FROM events WHERE ts>=? GROUP BY kind", since)}
    house = lambda since: -q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind IN {GAME_KINDS} AND ts>=?", since)["s"]
    m, disk = _mem(), shutil.disk_usage(os.path.dirname(os.path.abspath(DB_PATH)))
    dbsize = sum(os.path.getsize(DB_PATH + x) for x in ("", "-wal") if os.path.exists(DB_PATH + x))
    return {
        "users": q1("SELECT COUNT(*) n FROM users")["n"],
        "new24": q1("SELECT COUNT(*) n FROM users WHERE created>=?", t - 86400)["n"],
        "active24": q1("SELECT COUNT(DISTINCT user) n FROM events WHERE ts>=?", t - 86400)["n"],
        "active7": q1("SELECT COUNT(DISTINCT user) n FROM events WHERE ts>=?", t - 7 * 86400)["n"],
        "online": q1("SELECT COUNT(*) n FROM users WHERE seen>=?", t - 300)["n"],
        "banned": len(BANNED),
        "stars": q1("SELECT COALESCE(SUM(stars),0) s FROM users")["s"],
        "gifts": q1("SELECT COUNT(*) n FROM gifts WHERE owner>0")["n"],
        "bank": bank.bank_value(),
        "fees24": -q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind='fee' AND ts>=?", t - 86400)["s"],
        "house24": house(t - 86400), "house7": house(t - 7 * 86400),
        "kinds24": sums(t - 86400),
        "server": {"load": os.getloadavg() if hasattr(os, "getloadavg") else [0, 0, 0], "cpus": os.cpu_count(), "memTotal": m["MemTotal"], "memAvail": m["MemAvailable"],
                   "swapTotal": m["SwapTotal"], "swapFree": m["SwapFree"], "diskTotal": disk.total, "diskFree": disk.free,
                   "rss": _rss(), "db": dbsize, "uptime": int(time.time() - STARTED)},
    }


@app.get(R + "/admin/users")
def users(qs: str = "", sort: str = "seen", aid=Depends(admin)):
    order = {"seen": "seen DESC", "rich": "stars DESC", "new": "created DESC"}.get(sort, "seen DESC")
    qs = qs.strip().lstrip("@")
    if qs.isdigit():
        rows = q("SELECT * FROM users WHERE id=?", int(qs))
    elif qs:
        like = f"%{qs}%"
        rows = q(f"SELECT * FROM users WHERE name LIKE ? OR username LIKE ? ORDER BY {order} LIMIT 50", like, like)
    else:
        rows = q(f"SELECT * FROM users ORDER BY {order} LIMIT 50")
    return {"users": [{**user_brief(r), "stars": r["stars"], "seen": r["seen"], "created": r["created"], "banned": bool(r["banned"])}
                      for r in rows]}


@app.get(R + "/admin/user/{tid}")
def user(tid: int, aid=Depends(admin)):
    u = q1("SELECT * FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
    t = now()
    pnl = lambda since: q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=?", tid, since)["s"]
    return {**user_brief(u), "stars": u["stars"], "xp": u["xp"], "refs": u["refs"], "refBy": u["ref_by"], "created": u["created"],
            "seen": u["seen"], "banned": bool(u["banned"]), "opened": u["opened"],
            "gifts": q1("SELECT COUNT(*) n, COALESCE(SUM(value),0) v FROM gifts WHERE owner=?", tid)["n"],
            "giftsValue": q1("SELECT COALESCE(SUM(value),0) v FROM gifts WHERE owner=?", tid)["v"],
            "pnl24": pnl(t - 86400), "pnlAll": pnl(0),
            "events": [dict(r) for r in q("SELECT kind, delta, ts FROM events WHERE user=? ORDER BY ts DESC LIMIT 40", tid)],
            "giftList": [gift_out(g) for g in q("SELECT * FROM gifts WHERE owner=? ORDER BY value DESC LIMIT 100", tid)],
            "log": [dict(r) for r in q("SELECT action, detail, ts FROM admin_log WHERE target=? ORDER BY id DESC LIMIT 10", tid)],
            "isAdmin": tid in ADMINS, "isOwner": tid in OWNERS, "canGrant": aid in OWNERS, **_ref_info(u)}


def _ref_info(u):
    """Кто пригласил и по какой ссылке: подарок по ссылке тоже засчитывается приглашением (presents.py)."""
    inviter, src = None, None
    if u["ref_by"]:
        r = q1("SELECT * FROM users WHERE id=?", u["ref_by"])
        inviter = {**user_brief(r), "created": r["created"]} if r else {"id": u["ref_by"], "name": f"id {u['ref_by']}", "username": None, "photo": None}
        gift = q1("SELECT 1 FROM gift_links WHERE taker=? AND sender=?", u["id"], u["ref_by"])
        src = "gift" if gift else "ref"
    invited = [{**user_brief(r), "created": r["created"], "seen": r["seen"]}
               for r in q("SELECT * FROM users WHERE ref_by=? ORDER BY created DESC LIMIT 100", u["id"])]
    return {"inviter": inviter, "refSrc": src, "invited": invited}


@app.post(R + "/admin/user/{tid}/admin")
async def grant(tid: int, req: Request, aid=Depends(admin)):
    """Выдать / снять админку — только владелец. Владельцев снять нельзя."""
    on = bool((await req.json()).get("on"))
    if aid not in OWNERS:
        err("выдавать админку может только владелец")
    if tid in OWNERS:
        err("это владелец — его права не меняются")
    with tx():
        u = q1("SELECT name, banned FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
        if on and u["banned"]:
            err("игрок заблокирован")
        if on:
            db.execute("INSERT INTO admins(user,by,ts) VALUES(?,?,?) ON CONFLICT(user) DO NOTHING", (tid, aid, now()))
        else:
            db.execute("DELETE FROM admins WHERE user=?", (tid,))
        log(aid, "admin_on" if on else "admin_off", tid)
    (ADMINS.add if on else ADMINS.discard)(tid)
    notify(tid, "🛠 Тебе выдали права администратора — в профиле появилась админ-панель." if on else "🛠 Права администратора сняты.")
    return {"ok": True, "admin": on}


@app.get(R + "/admin/admins")
def admins_list(aid=Depends(admin)):
    out = []
    for i in sorted(ADMINS):
        u = q1("SELECT * FROM users WHERE id=?", i)
        if u:
            out.append({**user_brief(u), "owner": i in OWNERS})
    return {"list": out, "canGrant": aid in OWNERS}


@app.post(R + "/admin/user/{tid}/stars")
async def adjust(tid: int, req: Request, aid=Depends(admin)):
    b = await req.json()
    delta, reason = int(b.get("delta", 0)), str(b.get("reason", ""))[:200]
    if not delta or abs(delta) > MAX_ADJUST:
        err("неверная сумма")
    with tx():
        u = q1("SELECT stars FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
        if u["stars"] + delta < 0 and not b.get("neg"):   # в минус — только явно (neg): долг гасится доходом, ставить и переводить нельзя
            err(f"у игрока только ⭐ {u['stars']}")
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (delta, tid))
        event(tid, "admin", delta)
        log(aid, "stars", tid, (f"{delta:+d} {reason}" + (" (в минус)" if u["stars"] + delta < 0 else "")).strip(), undo={"t": "stars", "delta": -delta})
    return {"ok": True, "stars": bal(tid)}


@app.post(R + "/admin/user/{tid}/ban")
async def ban(tid: int, req: Request, aid=Depends(admin)):
    on = bool((await req.json()).get("ban"))
    if tid in ADMINS:
        err("админа заблокировать нельзя")
    with tx():
        q1("SELECT 1 FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
        db.execute("UPDATE users SET banned=? WHERE id=?", (int(on), tid))
        log(aid, "ban" if on else "unban", tid, undo={"t": "ban", "on": not on})
    (BANNED.add if on else BANNED.discard)(tid)
    return {"ok": True, "banned": on}


BROADCAST = {"running": False, "sent": 0, "failed": 0, "total": 0}


async def _broadcast(ids, text, image=None):
    kb = {"inline_keyboard": [[{"text": "Открыть", "web_app": {"url": APP_URL}}]]}
    from app import notif_card, tg_photo
    img = image or await asyncio.get_running_loop().run_in_executor(None, notif_card, text)   # своя картинка, иначе праздник/начисление → карточка
    try:
        for uid in ids:
            try:
                tok = __import__("franchise").token_for(uid)
                r = await tg_photo(tok, uid, img, text, kb) if img else {}
                if not r.get("ok"):
                    r = await tg_call("sendMessage", _token=tok, chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb)
                BROADCAST["sent" if r.get("ok") else "failed"] += 1
            except Exception:
                BROADCAST["failed"] += 1
            await asyncio.sleep(0.05)   # лимит Telegram ~30 сообщений/с
    finally:
        BROADCAST["running"] = False


@app.post(R + "/admin/broadcast")
async def broadcast(req: Request, aid=Depends(admin)):
    body = await req.json()
    text = str(body.get("text", "")).strip()
    if not 1 <= len(text) <= 3000:
        err("текст от 1 до 3000 символов")
    image = base64.b64decode(body["image"]) if body.get("image") else None
    if image and len(text) > 1024:
        err("подпись к картинке: не больше 1024 символов")
    if BROADCAST["running"]:
        err("рассылка уже идёт")
    ids = [r["id"] for r in q("SELECT id FROM users WHERE banned=0")]
    BROADCAST.update(running=True, sent=0, failed=0, total=len(ids))
    with tx():
        log(aid, "broadcast", None, text[:200])
    asyncio.create_task(_broadcast(ids, esc(text), image))
    return {"ok": True, "total": len(ids)}


@app.get(R + "/admin/broadcast")
def broadcast_state(aid=Depends(admin)):
    return BROADCAST


# ---------- регулярные рассылки: текст + «раз в N дней в ЧЧ:ММ по Москве»; хранятся в kv 'bc_sched' ----------
# Получают только игроки с включёнными напоминаниями от бота (notif=1): ежедневная реклама всем — путь к блокировкам бота.
import json as _json
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
SCHED_EVERY = (1, 2, 3, 7)


def _sched():
    r = q1("SELECT v FROM kv WHERE k='bc_sched'")
    try:
        return _json.loads(r["v"]) if r else []
    except Exception:
        return []


def _sched_save(lst):
    db.execute("INSERT INTO kv(k,v) VALUES('bc_sched',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (_json.dumps(lst, ensure_ascii=False),))


def _first_at(hhmm):
    """Ближайшее ЧЧ:ММ по Москве (сегодня, если ещё не прошло, иначе завтра) — unix-время."""
    h, m = map(int, hhmm.split(":"))
    d = datetime.now(MSK).replace(hour=h, minute=m, second=0, microsecond=0)
    if d.timestamp() <= time.time():
        d += timedelta(days=1)
    return int(d.timestamp())


def _sched_ids():
    return [r["id"] for r in q("SELECT id FROM users WHERE banned=0 AND notif=1")]


def _start_broadcast(text):
    ids = _sched_ids()
    BROADCAST.update(running=True, sent=0, failed=0, total=len(ids))
    asyncio.create_task(_broadcast(ids, esc(text)))
    return len(ids)


@app.get(R + "/admin/broadcast/sched")
def sched_list(aid=Depends(admin)):
    return {"list": _sched(), "now": now(), "every": SCHED_EVERY, "audience": len(_sched_ids())}


@app.post(R + "/admin/broadcast/sched")
async def sched_edit(req: Request, aid=Depends(admin)):
    b = await req.json()
    act, sid = str(b.get("action", "")), int(b.get("id") or 0)
    with tx():
        lst = _sched()
        cur = next((x for x in lst if x["id"] == sid), None)
        if act == "add":
            text, every, at = str(b.get("text", "")).strip(), int(b.get("every") or 0), str(b.get("time", ""))
            if not 1 <= len(text) <= 3000:
                err("текст от 1 до 3000 символов")
            if every not in SCHED_EVERY:
                err("период: 1, 2, 3 или 7 дней")
            try:
                hh, mm = map(int, at.split(":"))
                assert 0 <= hh <= 23 and 0 <= mm <= 59
                at = f"{hh:02d}:{mm:02d}"
            except Exception:
                err("время в формате ЧЧ:ММ")
            if len(lst) >= 10:
                err("не больше 10 регулярных рассылок")
            lst.append({"id": int(time.time() * 1000) % 10 ** 12, "text": text, "every": every, "time": at,
                        "next": _first_at(at), "on": True, "last": 0, "lastSent": 0})
            log(aid, "broadcast_sched", None, f"+ раз в {every} дн. в {at}: {text[:120]}")
        elif not cur:
            err("рассылка не найдена — обнови экран")
        elif act == "toggle":
            cur["on"] = not cur["on"]
            if cur["on"]:
                cur["next"] = _first_at(cur["time"])
            log(aid, "broadcast_sched", None, ("вкл: " if cur["on"] else "пауза: ") + cur["text"][:120])
        elif act == "del":
            lst.remove(cur)
            log(aid, "broadcast_sched", None, "удалена: " + cur["text"][:120])
        elif act == "now":
            if BROADCAST["running"]:
                err("рассылка уже идёт")
            n = _start_broadcast(cur["text"])
            cur["last"], cur["lastSent"] = now(), n
            log(aid, "broadcast", None, "регулярная вручную: " + cur["text"][:150])
        else:
            err("неизвестное действие")
        _sched_save(lst)
    return {"ok": True, "list": lst}


async def _sched_loop():
    while True:
        await asyncio.sleep(60)
        try:
            t = now()
            with tx():
                lst = _sched()
                due = next((x for x in lst if x["on"] and x["next"] <= t), None)
                if due and not BROADCAST["running"]:
                    due["last"], due["lastSent"] = t, _start_broadcast(due["text"])
                    while due["next"] <= t:   # сервер мог лежать — не догоняем пачкой, а идём дальше по расписанию
                        due["next"] += due["every"] * 86400
                    log(0, "broadcast", None, f"регулярная (раз в {due['every']} дн.): " + due["text"][:150])
                    _sched_save(lst)
        except Exception as e:
            print("bc_sched:", e, flush=True)


@app.on_event("startup")
async def _sched_start():
    asyncio.create_task(_sched_loop())


def _alog_keep():
    r = q1("SELECT v FROM kv WHERE k='admin_log_keep'")
    try:
        return max(0, min(365, int(r["v"]))) if r else 0   # 0 — хранить всё
    except (ValueError, TypeError):
        return 0


@app.get(R + "/admin/log")
def admin_log(aid=Depends(admin)):
    keep = _alog_keep()
    if keep:
        db.execute("DELETE FROM admin_log WHERE ts<?", (now() - keep * 86400,))
    st = q1("SELECT COUNT(*) c, MIN(ts) o FROM admin_log")
    rows = [dict(r) for r in q("SELECT * FROM admin_log ORDER BY id DESC LIMIT 80")]
    names = {}
    for r in rows:   # имена админа и игрока — чтобы журнал читался без поиска по id
        for k in ("admin", "target"):
            i = r.get(k)
            if i and i not in names:
                u = q1("SELECT name FROM users WHERE id=?", i)
                names[i] = u["name"] if u else f"id {i}"
        r["adminName"], r["targetName"] = names.get(r["admin"]), names.get(r["target"])
        r["canUndo"] = bool(r.get("undo")) and not r.get("undone") and (aid in OWNERS or r["admin"] == aid)
        r.pop("undo", None)
    return {"log": rows,
            "keep_days": keep, "total": st["c"], "oldest": st["o"], "canEdit": aid in OWNERS}


@app.post(R + "/admin/log/cfg")
def admin_log_cfg(body: dict, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Менять журнал может только владелец")
    try:
        keep = max(0, min(365, int(body.get("keep_days", 0))))
    except (TypeError, ValueError):
        err("Введи число дней (0 — хранить всё)")
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('admin_log_keep',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(keep),))
        if keep:
            db.execute("DELETE FROM admin_log WHERE ts<?", (now() - keep * 86400,))
        log(aid, "adminlog_cfg", detail=f"хранить {keep} дн" if keep else "хранить всё")
    return {"ok": True, "keep_days": keep}


@app.post(R + "/admin/log/clear")
def admin_log_clear(aid=Depends(admin)):
    if aid not in OWNERS:
        err("Очистить журнал может только владелец")
    with tx():
        db.execute("DELETE FROM admin_log")
        log(aid, "adminlog_clear", detail="админский журнал очищен")   # сам факт очистки остаётся в журнале
    return {"ok": True}


# ---------------- переименование кейсов ----------------
# kv case_names: {cid: {"title": "...", "who": "all"|"only"|"except", "ids": [...]}}. Применяется на лету (E.CASE_NAMES),
# настоящие названия (из economy.CASES_DEF) не меняются: E.case_title(cid, uid) решает, что видит конкретный игрок.
import json as _json

CASE_WHO = ("all", "only", "except")


def _load_case_names():
    try:
        raw = _json.loads(kv_get("case_names", "{}") or "{}")
    except ValueError:
        raw = {}
    E.CASE_NAMES.clear()
    for cid, o in raw.items():
        if cid in E.CASES and isinstance(o, dict) and o.get("title"):
            E.CASE_NAMES[cid] = {"title": str(o["title"]), "who": o.get("who") if o.get("who") in CASE_WHO else "all",
                                 "ids": {int(x) for x in o.get("ids", []) if str(x).lstrip("-").isdigit()}}


_load_case_names()


def _load_case_covers():
    try:
        raw = _json.loads(kv_get("case_covers", "{}") or "{}")
    except ValueError:
        raw = {}
    E.CASE_COVERS.clear()
    for cid, o in raw.items():
        if cid in E.CASES and isinstance(o, dict) and o.get("cover"):
            E.CASE_COVERS[cid] = {"cover": str(o["cover"]), "who": o.get("who") if o.get("who") in CASE_WHO else "all",
                                  "ids": {int(x) for x in o.get("ids", []) if str(x).lstrip("-").isdigit()}}


_load_case_covers()
os.makedirs(E.COVER_DIR, exist_ok=True)
COVER_MAX = 2 * 1024 * 1024


def _save_cover(cid, img):
    """data URL картинки (png/jpeg/webp) → covers/c_<cid>_<hex>_{64,128,256,512}.{png,webp}; вернуть "~имя"."""
    from io import BytesIO
    from PIL import Image
    try:
        raw = base64.b64decode(img.split(",", 1)[1], validate=True)
    except Exception:
        err("картинка повреждена")
    if len(raw) > COVER_MAX:
        err("картинка больше 2 МБ")
    try:
        im = Image.open(BytesIO(raw))
        im.load()
        im = im.convert("RGBA")
    except Exception:
        err("не удалось прочитать картинку (нужен PNG, JPEG или WebP)")
    im.thumbnail((512, 512), Image.LANCZOS)
    sq = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    sq.paste(im, ((512 - im.width) // 2, (512 - im.height) // 2))
    name = f"c_{cid}_{secrets.token_hex(4)}"
    for sz in (64, 128, 256, 512):
        v = sq if sz == 512 else sq.resize((sz, sz), Image.LANCZOS)
        v.save(os.path.join(E.COVER_DIR, f"{name}_{sz}.png"), optimize=True)
        v.save(os.path.join(E.COVER_DIR, f"{name}_{sz}.webp"), quality=85, method=4)
    return "~" + name


@app.get(R + "/admin/cases")
def adm_cases(aid=Depends(admin)):
    out = []
    for c in E.CASES.values():
        o, v = E.CASE_NAMES.get(c["id"]), E.CASE_COVERS.get(c["id"])
        out.append({"id": c["id"], "real": c["title"], "price": c["price"], "level": c["level"], "cover": c["cover"],
                    "title": o["title"] if o else "", "who": o["who"] if o else "all", "ids": sorted(o["ids"]) if o else [],
                    "ncover": v["cover"] if v else "", "cwho": v["who"] if v else "all", "cids": sorted(v["ids"]) if v else []})
    return {"list": out, "cols": sorted(c for c in E.CATALOG if c not in E.CUSTOM) + sorted(E.CUSTOM)}


@app.post(R + "/admin/cases/cover")
async def adm_case_cover(req: Request, aid=Depends(admin)):
    """Обложка кейса: cover — имя коллекции (картинка подарка), img — своя картинка (data URL), пусто — вернуть оригинал."""
    b = await req.json()
    cid = str(b.get("cid", ""))
    c = E.CASES.get(cid) or err("нет такого кейса")
    who = b.get("who") if b.get("who") in CASE_WHO else "all"
    ids = sorted({int(x) for x in re.findall(r"-?\d+", str(b.get("ids", "")))})[:500]
    try:
        cur = _json.loads(kv_get("case_covers", "{}") or "{}")
    except ValueError:
        cur = {}
    prev = cur.get(cid)
    img, cover = str(b.get("img", "")), str(b.get("cover", ""))
    if img:
        cover = _save_cover(cid, img)
    elif cover and cover not in E.CATALOG and not (cover.startswith("~") and E.custom_file(cover)):
        err("нет такой коллекции")
    if cover and who != "all" and not ids:
        err("Укажи id игроков или выбери «всем»")
    if cover:
        cur[cid] = {"cover": cover, "who": who, "ids": ids}
        detail = f"{c['title']}: обложка → {'своя картинка' if cover.startswith('~') else cover} (" + {"all": "всем", "only": f"только {len(ids)} игрокам", "except": f"всем, кроме {len(ids)}"}[who] + ")"
    else:
        cur.pop(cid, None)
        detail = f"{c['title']}: оригинальная обложка"
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('case_covers',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (_json.dumps(cur, ensure_ascii=False),))
        log(aid, "case_cover", None, detail, undo={"t": "case_cover", "cid": cid, "prev": prev})
    _load_case_covers()
    # файлы прежней загруженной обложки не удаляем: «Отменить» в журнале может вернуть её (4 размера × 2 формата ≈ 100 КБ на обложку).
    return {"ok": True, "cover": cover}


@app.post(R + "/admin/cases/name")
async def adm_case_name(req: Request, aid=Depends(admin)):
    b = await req.json()
    cid = str(b.get("cid", ""))
    c = E.CASES.get(cid) or err("нет такого кейса")
    title = " ".join(str(b.get("title", "")).split())[:40]
    who = b.get("who") if b.get("who") in CASE_WHO else "all"
    ids = sorted({int(x) for x in re.findall(r"-?\d+", str(b.get("ids", "")))})[:500]
    if who != "all" and not ids:
        err("Укажи id игроков или выбери «всем»")
    try:
        cur = _json.loads(kv_get("case_names", "{}") or "{}")
    except ValueError:
        cur = {}
    prev = cur.get(cid)
    if title:
        cur[cid] = {"title": title, "who": who, "ids": ids}
        detail = f"{c['title']} → «{title}» (" + {"all": "всем", "only": f"только {len(ids)} игрокам", "except": f"всем, кроме {len(ids)}"}[who] + ")"
    else:
        cur.pop(cid, None)
        detail = f"{c['title']}: настоящее название"
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('case_names',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (_json.dumps(cur, ensure_ascii=False),))
        log(aid, "case_name", None, detail, undo={"t": "case_name", "cid": cid, "prev": prev})
    _load_case_names()
    return {"ok": True}


# ---------------- выдача подарков и кейсов ----------------
@app.get(R + "/admin/catalog")
def catalog(col: str = "", aid=Depends(admin)):
    if not col:
        return {"cols": sorted(E.CATALOG, key=lambda c: -E.base(c)), "bases": {c: E.base(c) for c in E.CATALOG}, "cases": [{"id": c["id"], "title": c["title"], "price": c["price"]}
                                                                          for c in E.CASES.values()]}
    d = E.CATALOG.get(col) or err("нет такой коллекции")
    srt = lambda xs: [x[0] for x in sorted(xs, key=lambda x: x[1])]   # редкие первыми
    return {"col": col, "base": E.base(col), "models": srt(d["models"]), "backdrops": srt(d["backdrops"]), "symbols": srt(d["symbols"])}


def _make_gift(col, model="", backdrop="", symbol=""):
    d = E.CATALOG.get(col) or err("нет такой коллекции")
    pick = lambda key, name: next((x for x in d[key] if x[0] == name), None) or (err(f"нет такого: {name}") if name else E._pick(col, key))
    m, b, s = pick("models", model), pick("backdrops", backdrop), pick("symbols", symbol)
    return {"col": col, "model": m[0], "backdrop": b[0], "symbol": s[0], "num": random.randint(1, E.supply(col)),
            "value": max(1, round(E.base(col) * E.mult(col, m[1], b[1], s[1])))}


@app.post(R + "/admin/user/{tid}/gift")
async def give_gift(tid: int, req: Request, aid=Depends(admin)):
    b = await req.json()
    n = max(1, min(20, int(b.get("n", 1))))
    t = now()
    out = []
    with tx():
        q1("SELECT 1 FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
        for _ in range(n):
            g = _make_gift(str(b.get("col", "")), str(b.get("model", "")), str(b.get("backdrop", "")), str(b.get("symbol", "")))
            cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                             (tid, g["col"], g["model"], g["backdrop"], g["symbol"], g["num"], g["value"], t))
            event(tid, "admgift", g["value"])   # эмиссия администрации: виден в экономике и на публике (bank.py)
            if b.get("feed"):   # по желанию админа — показать в живой ленте
                db.execute("INSERT INTO feed(user,gift,cs,ts) VALUES(?,?,?,?)", (tid, cur.lastrowid, "admin", t))
            out.append(gift_out(q1("SELECT * FROM gifts WHERE id=?", cur.lastrowid)))
        log(aid, "gift", tid, f"{n}× {b.get('col')} {b.get('model') or ''}".strip(), undo={"t": "gift", "ids": [g["id"] for g in out]})
    if b.get("notify", True):
        notify(tid, f"🎁 Тебе подарок от администрации: <b>{esc(out[0]['col'])}</b>" + (f" и ещё {n - 1}" if n > 1 else "") + ". Загляни в сумку!")
    return {"ok": True, "gifts": out}


@app.post(R + "/admin/user/{tid}/keys")
async def give_keys(tid: int, req: Request, aid=Depends(admin)):
    b = await req.json()
    cid, n = str(b.get("cid", "")), int(b.get("n", 1))
    c = E.CASES.get(cid) or err("нет такого кейса")
    if not 1 <= n <= 100:
        err("от 1 до 100")
    with tx():
        q1("SELECT 1 FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
        db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,?) ON CONFLICT(user,cid) DO UPDATE SET n=n+?", (tid, cid, n, n))
        log(aid, "keys", tid, f"{n}× {c['title']}", undo={"t": "keys", "cid": cid, "n": n})
    if b.get("notify", True):
        notify(tid, f"🔑 Тебе выдали {n} {'кейс' if n == 1 else 'кейса' if n < 5 else 'кейсов'} «{esc(c['title'])}» — открывай бесплатно!")
    return {"ok": True}


# ---------------- акция «щедрые выходные» ----------------
@app.get(R + "/admin/promo")
def promo_get(aid=Depends(admin)):
    r = q1("SELECT v FROM kv WHERE k='promo'")
    return {"mode": r["v"] if r else "auto", "active": promo()}


@app.post(R + "/admin/promo")
async def promo_set(req: Request, aid=Depends(admin)):
    mode = str((await req.json()).get("mode", "auto"))
    if mode not in ("auto", "on", "off"):
        err("auto, on или off")
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('promo',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (mode,))
        log(aid, "promo", None, mode)
    _PROMO["ts"] = 0
    return {"mode": mode, "active": promo()}


@app.post(R + "/admin/user/{tid}/gift/{gid}/remove")
def remove_gift(tid: int, gid: int, aid=Depends(admin)):
    """Забрать подарок у игрока (удаляется насовсем; снимается с маркета, обмены с ним отменяются)."""
    with tx():
        g = q1("SELECT * FROM gifts WHERE id=? AND owner=?", gid, tid) or err("у игрока нет этого подарка")
        db.execute("DELETE FROM gifts WHERE id=?", (gid,))
        unpin(tid, gid)
        cancel_trades_with(gid)
        event(tid, "gift", -g["value"])
        log(aid, "gift-remove", tid, f"{g['col']} #{g['num']} {g['model']} (⭐ {g['value']})")
    return {"ok": True}


# ---------------- идеи и предложения от игроков → админам в личку ----------------
db.executescript("CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, user INTEGER, text TEXT, ts INTEGER);")
FEEDBACK_GAP = 10 * 60


@app.post(R + "/feedback")
async def feedback(req: Request, uid=Depends(auth)):
    text = " ".join(str((await req.json()).get("text", "")).split())[:1000]
    if len(text) < 5:
        err("напиши хотя бы пару слов")
    t = now()
    with tx():
        last = q1("SELECT MAX(ts) t FROM feedback WHERE user=?", uid)["t"]
        if last and t - last < FEEDBACK_GAP:
            err(f"следующее сообщение можно через {(last + FEEDBACK_GAP - t + 59) // 60} мин")
        db.execute("INSERT INTO feedback(user,text,ts) VALUES(?,?,?)", (uid, text, t))
        u = q1("SELECT name, username FROM users WHERE id=?", uid)
    who = esc(u["name"]) + (f" (@{esc(u['username'])})" if u["username"] else "") + f" · id {uid}"
    for a in ADMINS:
        if a not in STEALTH:   # в режиме секретности админу не шлём
            notify(a, f"💡 <b>Идея от игрока</b>\n{who}\n\n{esc(text)}")
    return {"ok": True}


# ---------------- покупки за Telegram Stars ----------------
@app.get(R + "/admin/sales")
def sales(aid=Depends(admin)):
    t = now()
    per = lambda since: dict(q1("SELECT COUNT(*) n, COALESCE(SUM(xtr),0) xtr, COALESCE(SUM(stars),0) stars, COUNT(DISTINCT user) buyers "
                                "FROM payments WHERE ts>=?", since))
    days = [dict(r) for r in q("SELECT (ts/86400)*86400 day, SUM(xtr) xtr, COUNT(*) n FROM payments WHERE ts>=? GROUP BY day ORDER BY day", t - 14 * 86400)]
    top = []
    for r in q("SELECT user, SUM(xtr) xtr, COUNT(*) n FROM payments GROUP BY user ORDER BY xtr DESC LIMIT 10"):
        u = q1("SELECT * FROM users WHERE id=?", r["user"])
        top.append({**(user_brief(u) if u else {"id": r["user"], "name": "?"}), "xtr": r["xtr"], "n": r["n"]})
    last = []
    for r in q("SELECT * FROM payments ORDER BY ts DESC LIMIT 30"):
        u = q1("SELECT * FROM users WHERE id=?", r["user"])
        last.append({"user": user_brief(u) if u else {"id": r["user"], "name": "?"}, "xtr": r["xtr"], "stars": r["stars"], "ts": r["ts"]})
    import shop
    return {"today": per(t - t % 86400), "week": per(t - 7 * 86400), "all": per(0), "days": days, "top": top, "last": last,
            "sale": {k: shop.sale_on(k) for k in shop.SALE_KEYS}, "canEdit": aid in OWNERS}


@app.post(R + "/admin/shop")
async def shop_toggle(req: Request, aid=Depends(admin)):
    """Вкл/выкл продаж за Telegram Stars: what = shop (игровые звёзды) | vip | chest (только владелец)."""
    import shop
    if aid not in OWNERS:
        err("Включать продажи может только владелец")
    b = await req.json()
    what, on = str(b.get("what") or "shop"), bool(b.get("on"))
    if what not in shop.SALE_KEYS:
        err("нет такой продажи")
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (shop.SALE_KEYS[what], "1" if on else "0"))
        log(aid, "shop", None, {"shop": "игровые звёзды", "vip": "VIP", "chest": "звёздный сундук"}[what] + " за Telegram Stars: " + ("включено" if on else "выключено"))
    if what == "shop":   # описание ботов упоминает покупку звёзд: обновляем сразу, не дожидаясь перезапуска
        import asyncio
        async def _refresh():
            import app as A
            for tok in [None] + [r["token"] for r in q("SELECT token FROM bots WHERE token IS NOT NULL")]:
                try:
                    await A.bot_description(tok)
                except Exception as e:
                    print("bot description", e, flush=True)
                await asyncio.sleep(0.5)
        asyncio.create_task(_refresh())
    return {"ok": True, "on": on}


@app.post(R + "/admin/event")
async def event_set(req: Request, aid=Depends(admin)):
    """Сезонный ивент: auto (по датам) | off | id ивента (включить сейчас, чтобы посмотреть)."""
    from app import EVENTS
    mode = str((await req.json()).get("mode", "auto"))
    if mode not in ("auto", "off") and mode not in [e["id"] for e in EVENTS]:
        err("Действие устарело — обнови экран")
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('event',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (mode,))
        log(aid, "event", None, mode)
    from app import _EV
    _EV["ts"] = 0
    return {"ok": True, "mode": mode}


@app.get(R + "/admin/event")
def event_get(aid=Depends(admin)):
    from app import EVENTS, event_public
    r = q1("SELECT v FROM kv WHERE k='event'")
    return {"mode": r["v"] if r else "auto", "active": event_public(), "events": [{"id": e["id"], "title": e["title"], "from": e["from"], "to": e["to"]} for e in EVENTS]}


# ---------------- оформление игрока: забрать рамку/ник (с возвратом звёзд или без) ----------------
@app.get(R + "/admin/user/{tid}/cosm")
def cosm_list(tid: int, aid=Depends(admin)):
    import style as ST
    return {"list": [{"item": r["item"], "kind": ST.ITEMS[r["item"]][0], "title": ST.ITEMS[r["item"]][1], "until": r["until"],
                      "price": ST.price_for(tid, ST.ITEMS[r["item"]][2])}
                     for r in q("SELECT item, until FROM cosm WHERE user=? AND until>? ORDER BY until DESC", tid, now()) if r["item"] in ST.ITEMS]}


@app.post(R + "/admin/user/{tid}/cosm/{item}/remove")
async def cosm_remove(tid: int, item: str, req: Request, aid=Depends(admin)):
    import style as ST
    refund = bool((await req.json()).get("refund"))
    if item not in ST.ITEMS:
        err("нет такого товара")
    kind, title, price = ST.ITEMS[item]
    col = "p_frame" if kind == "frame" else "p_nick"
    with tx():
        if not q1("SELECT 1 FROM cosm WHERE user=? AND item=?", tid, item):
            err("у игрока этого нет")
        amt = ST.price_for(tid, price) if refund else 0
        db.execute("DELETE FROM cosm WHERE user=? AND item=?", (tid, item))
        db.execute(f"UPDATE users SET {col}='', {col}_until=0 WHERE id=? AND {col}=?", (tid, item))
        if amt:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amt, tid))
            event(tid, "admin", amt)
        log(aid, "cosm", tid, f"забрал «{title}»" + (f", вернул ⭐ {amt}" if amt else " без возврата"))
    if amt:
        notify(tid, f"↩️ Покупку «{esc(title)}» отменили — ⭐ {amt:,} вернулись на баланс.".replace(",", " "))
    return {"ok": True, "refund": amt}


# ---------------- друзья игрока ----------------
@app.get(R + "/admin/user/{tid}/friends")
def friends_of(tid: int, aid=Depends(admin)):
    out = {"ok": [], "in": [], "out": []}
    for r in q("SELECT * FROM friends WHERE a=? OR b=? ORDER BY ts DESC", tid, tid):
        other = r["b"] if r["a"] == tid else r["a"]
        u = q1("SELECT * FROM users WHERE id=?", other)
        if not u:
            continue
        key = "ok" if r["status"] == "ok" else ("out" if r["a"] == tid else "in")   # pending: a — кто позвал
        out[key].append({**user_brief(u), "since": r["ts"], "seen": u["seen"]})
    return out
