"""Заморозка кошелька и компенсации.

Заморозка: игрок играет как обычно, но не может отдать звёзды или подарки другим игрокам — переводы, чеки,
подарки другу и ссылки, маркет (выставить/купить), обмены, PvP (дуэли, комнаты 101, джекпот, битвы), казна клана.
Нужна на время разбора подозрительных выигрышей: ничего не утечёт на твинков, пока админы смотрят.

Компенсации: начислить звёзды (фикс или % от проигрыша) и/или ключи всем, кто играл в игру за период, —
с предпросмотром; в журнале с отменой (снимет начисленное)."""
import asyncio
import json
import re
import time

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

import economy as E
from app import GAME_KINDS, R, app, db, err, esc, event, now, q, q1, tx, user_brief
import app as A
from admin import OWNERS, admin, log

db.executescript("""
CREATE TABLE IF NOT EXISTS frozen(user INTEGER PRIMARY KEY, ts INTEGER, admin INTEGER, reason TEXT);
""")
FROZEN = {r[0] for r in db.execute("SELECT user FROM frozen")}
# что нельзя замороженному: всё, чем звёзды или подарки уходят другому игроку
BLOCK = [re.compile("^" + re.escape(R) + p + "$") for p in (
    r"/pay/send", r"/pay/qr/send", r"/gift/\d+/send", r"/gift/\d+/link", r"/gift/\d+/list", r"/market/\d+/buy",
    r"/trades", r"/trades/\d+/accept", r"/duels", r"/duels/\d+/accept", r"/cduel/\d+/accept", r"/rooms", r"/rooms/\d+/join",
    r"/jroul/bet", r"/battles", r"/battles/\d+/join", r"/clans/donate", r"/clans/spend", r"/clans/tax")]
FROZEN_MSG = "Кошелёк заморожен администрацией на время проверки: переводы, маркет, обмены и игры с другими игроками недоступны. Играть можно как обычно"
COMP_MAX = 1_000_000   # больше за одну компенсацию — только владелец


def _uid(request):
    """id игрока из подписи — без регистрации и побочек auth()."""
    from app import DEV
    try:
        if DEV and request.headers.get("x-dev-user"):
            return int(request.headers["x-dev-user"])
        import franchise
        v = franchise.verify(request.headers.get("x-init-data", ""))
        return int(json.loads(v[1]["user"])["id"]) if v and "user" in v[1] else None
    except Exception:
        return None


@app.middleware("http")
async def _freeze_gate(request: Request, call_next):
    if FROZEN and request.method == "POST" and any(rx.match(request.url.path) for rx in BLOCK) and _uid(request) in FROZEN:
        return JSONResponse({"detail": FROZEN_MSG}, status_code=403)
    return await call_next(request)


def is_frozen(uid):
    return uid in FROZEN


def set_frozen(tid, on, aid=0, reason=""):
    """Вызывать внутри tx()."""
    if on:
        db.execute("INSERT INTO frozen(user,ts,admin,reason) VALUES(?,?,?,?) ON CONFLICT(user) DO UPDATE SET ts=excluded.ts, admin=excluded.admin, reason=excluded.reason",
                   (tid, now(), aid, reason))
        FROZEN.add(tid)
    else:
        db.execute("DELETE FROM frozen WHERE user=?", (tid,))
        FROZEN.discard(tid)


@app.get(R + "/admin/user/{tid}/freeze")
def freeze_get(tid: int, aid=Depends(admin)):
    r = q1("SELECT * FROM frozen WHERE user=?", tid)
    return {"frozen": bool(r), "ts": r["ts"] if r else None, "reason": r["reason"] if r else "",
            "by": user_brief(q1("SELECT * FROM users WHERE id=?", r["admin"])) if r and r["admin"] and q1("SELECT 1 FROM users WHERE id=?", r["admin"]) else None}


@app.post(R + "/admin/user/{tid}/freeze")
async def freeze_set(tid: int, req: Request, aid=Depends(admin)):
    b = await req.json()
    on, reason = bool(b.get("on")), " ".join(str(b.get("reason", "")).split())[:200]
    if on and tid in A.ADMINS:
        err("админа заморозить нельзя")
    with tx():
        q1("SELECT 1 FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
        if on == (tid in FROZEN):
            err("уже заморожен" if on else "и так не заморожен")
        set_frozen(tid, on, aid, reason)
        log(aid, "freeze" if on else "unfreeze", tid, reason, undo={"t": "freeze", "on": not on})
    A.notify(tid, ("🧊 Кошелёк заморожен на время проверки. Играть можно, но переводы, маркет, обмены и игры с другими игроками пока недоступны."
                   + (f"\nПричина: {esc(reason)}" if reason else "")) if on else "✅ Кошелёк разморожен — переводы и маркет снова доступны.")
    return {"ok": True, "frozen": on}


@app.get(R + "/admin/frozen")
def frozen_list(aid=Depends(admin)):
    return {"list": [{**user_brief(u), "ts": r["ts"], "reason": r["reason"]}
                     for r in q("SELECT * FROM frozen ORDER BY ts DESC") for u in [q1("SELECT * FROM users WHERE id=?", r["user"])] if u]}


# ---------------- компенсации ----------------
def _kinds(game):
    if game == "any":
        return [k.strip("'") for k in GAME_KINDS.strip("()").split(",")]
    if not re.fullmatch(r"[a-z0-9_]{2,20}", game or ""):
        err("выбери игру")
    return [game]


def comp_calc(b):
    """Кому и сколько: [(uid, раундов, проигрыш, звёзд)], параметры."""
    game = str(b.get("game", "any"))
    t0, t1 = int(b.get("from") or 0), int(b.get("to") or 0) or now()
    if not 0 < t0 < t1 or t1 - t0 > 31 * 86400:
        err("период — до 31 дня")
    minr = max(1, int(b.get("minRounds") or 1))
    mode = b.get("mode", "fixed")
    amount, pct, cap = max(0, int(b.get("amount") or 0)), max(0.0, min(100.0, float(b.get("pct") or 0))), max(0, int(b.get("cap") or 0))
    cid, keys = str(b.get("cid") or ""), max(0, min(10, int(b.get("keys") or 0)))
    if keys and cid not in E.CASES:
        err("нет такого кейса")
    if mode not in ("fixed", "loss"):
        err("неизвестный способ")
    if not (amount if mode == "fixed" else pct) and not keys:
        err("укажи звёзды или ключи")
    ks = _kinds(game)
    rows = q(f"SELECT user, COUNT(*) n, SUM(delta) s FROM events WHERE kind IN ({','.join('?' * len(ks))}) AND ts>=? AND ts<? GROUP BY user HAVING n>=?",
             *ks, t0, t1, minr)
    out = []
    for r in rows:
        if r["user"] in A.BANNED:
            continue
        loss = max(0, -(r["s"] or 0))
        st = amount if mode == "fixed" else int(loss * pct / 100)
        if cap and mode == "loss":
            st = min(st, cap)
        if st or keys:
            out.append((r["user"], r["n"], loss, st))
    out.sort(key=lambda x: -x[3])
    return out, {"game": game, "from": t0, "to": t1, "keys": keys, "cid": cid if keys else ""}


@app.post(R + "/admin/comp/preview")
async def comp_preview(req: Request, aid=Depends(admin)):
    out, p = comp_calc(await req.json())
    top = []
    for uid, n, loss, st in out[:15]:
        u = q1("SELECT * FROM users WHERE id=?", uid)
        if u:
            top.append({**user_brief(u), "rounds": n, "loss": loss, "stars": st})
    return {"players": len(out), "stars": sum(x[3] for x in out), "keys": p["keys"] * len(out), "top": top, "max": COMP_MAX, "owner": aid in OWNERS}


async def _paced(msgs):
    """Сообщения по одному с паузой — лимит Telegram ~30/с."""
    for uid, text in msgs:
        A.notify(uid, text)
        await asyncio.sleep(0.06)


@app.post(R + "/admin/comp/send")
async def comp_send(req: Request, aid=Depends(admin)):
    b = await req.json()
    out, p = comp_calc(b)
    if not out:
        err("под условия никто не попал")
    total = sum(x[3] for x in out)
    if total > COMP_MAX and aid not in OWNERS:
        err(f"больше ⭐ {COMP_MAX:,} за раз — только владелец".replace(",", " "))
    note = " ".join(str(b.get("note", "")).split())[:300] or "Компенсация от администрации"
    cname = E.CASES[p["cid"]]["title"] if p["keys"] else ""
    with tx():
        for uid, _, _, st in out:
            if st:
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (st, uid))
                event(uid, "comp", st)
            if p["keys"]:
                db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,?) ON CONFLICT(user,cid) DO UPDATE SET n=n+?", (uid, p["cid"], p["keys"], p["keys"]))
        import live
        gname = "все игры" if p["game"] == "any" else live.NAMES.get(p["game"], p["game"])
        log(aid, "comp", None, f"{len(out)} игр. · ⭐ {total:,}".replace(",", " ") + (f" + {p['keys']}× {cname}" if p["keys"] else "") + f" · {gname} · {note}",
            undo={"t": "comp", "items": [[u, st] for u, _, _, st in out], "cid": p["cid"], "keys": p["keys"]})
    msgs = []
    for uid, _, _, st in out:
        gift = " и ".join(x for x in (f"⭐ {st:,}".replace(",", " ") if st else "", f"{p['keys']}× ключ «{esc(cname)}»" if p["keys"] else "") if x)
        msgs.append((uid, f"🎁 {esc(note)}\nНачислено: {gift}"))
    asyncio.get_running_loop().create_task(_paced(msgs))
    return {"ok": True, "players": len(out), "stars": total}


@app.get(R + "/admin/comp/meta")
def comp_meta(aid=Depends(admin)):
    import live
    ks = _kinds("any")
    return {"games": [[k, live.NAMES.get(k, {"case": "Кейсы", "upgrade": "Апгрейд", "battle": "Битва кейсов", "craft": "Крафт", "cards": "21 с друзьями",
                                           "jroul": "Джекпот", "starfall": "Звездопад", "duel": "Дуэли"}.get(k, k))] for k in ks],
            "cases": [[cid, c["title"]] for cid, c in E.CASES.items()], "max": COMP_MAX, "owner": aid in OWNERS, "now": now(),
            "frozen": len(FROZEN)}
