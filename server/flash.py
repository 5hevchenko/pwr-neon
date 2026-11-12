"""Ивенты по расписанию (≈ раз в 2 часа, по 20 минут): «Удача ×3/×5» и «Раздача ⭐».

- «Удача ×N»: шанс «удачного момента» (app.event, LUCKY) × N, и за ивент его можно поймать ещё раз, даже если сегодня уже был.
  Множитель — на шанс сюрприза, НЕ на выигрыши: сюрприз ограничен «раз за ивент», поэтому ставками по 10 ⭐ его не нафармить
  (выигрыши ×N при любом преимуществе казино превращают ивент в «станок» — правило «меньше 1% от оборота»).
- «Раздача»: кнопка «Забрать» — первым N игрокам с уровня L, игравшим за сутки, по разу за ивент (иначе твинки
  забирали бы раздачу каждые 2 часа).
Все числа — в админке («Ивенты»), kv 'flashcfg'. Бот предупреждает о начале не чаще раза в notify_gap часов одному игроку.
"""
import asyncio
import json
import random

from fastapi import Depends, Request

import app as A
from app import R, app, auth, db, err, esc, event, now, q, q1, tx
from admin import OWNERS, admin, log


def nf(x):
    return f"{x:,}".replace(",", " ")


KINDS = {
    "luck3": {"title": "🍀 Удача ×3", "icon": "sparkle"},
    "luck5": {"title": "🍀 Удача ×5", "icon": "sparkle"},
    "drop": {"title": "🎁 Раздача звёзд", "icon": "gift"},
}
DEFAULTS = {
    "on": True,
    "every_min": 120,          # примерно раз в столько минут…
    "jitter_min": 20,          # …± случайный сдвиг
    "dur_min": 20,             # длительность ивента
    "w_luck3": 40, "w_luck5": 20, "w_drop": 40,   # веса выбора типа
    "drop_amount": 1500,       # ⭐ в раздаче
    "drop_max": 100,           # сколько игроков успеют забрать
    "drop_level": 3,           # с какого уровня
    "notify": True,            # бот пишет о начале ивента
    "notify_gap_h": 6,         # одному игроку — не чаще раза в N часов
}
LIMITS = {"every_min": (15, 1440), "jitter_min": (0, 120), "dur_min": (5, 180), "w_luck3": (0, 100), "w_luck5": (0, 100),
          "w_drop": (0, 100), "drop_amount": (0, 100000), "drop_max": (1, 10000), "drop_level": (1, 100), "notify_gap_h": (1, 168)}
CFG = {}
try:
    CFG.update({k: v for k, v in json.loads(A.kv_get("flashcfg", "{}")).items() if k in DEFAULTS})
except Exception:
    pass


def cfg(k):
    return CFG.get(k, DEFAULTS[k])


db.executescript("""
CREATE TABLE IF NOT EXISTS flash(id INTEGER PRIMARY KEY, kind TEXT, start INTEGER, end INTEGER, claims INTEGER DEFAULT 0, by INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS flash_claim(fid INTEGER, user INTEGER, amount INTEGER, ts INTEGER, PRIMARY KEY(fid, user));
CREATE TABLE IF NOT EXISTS flash_notify(user INTEGER PRIMARY KEY, ts INTEGER);
""")


def current():
    t = now()
    r = q1("SELECT * FROM flash WHERE start<=? AND end>? ORDER BY id DESC LIMIT 1", t, t)
    return dict(r) if r else None


_LUCK = {"ts": 0, "v": None}


def luck():
    """Для app.event: (множитель, начало ивента) во время «Удачи», иначе None. Кэш 5 с — зовётся в каждой ставке."""
    t = now()
    if t - _LUCK["ts"] >= 5:
        f = current()
        _LUCK.update(ts=t, v=({"luck3": 3, "luck5": 5}[f["kind"]], f["start"]) if f and f["kind"] in ("luck3", "luck5") else None)
    v = _LUCK["v"]
    return v if v and cfg("on") else None


A.FLASH_LUCK = luck


def _next_ts():
    return int(A.kv_get("flash_next", 0) or 0)


def _plan_next(after):
    j = cfg("jitter_min")
    nxt = after + (cfg("every_min") + random.randint(-j, j)) * 60
    with A.LOCK:
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('flash_next',?)", (str(nxt),))
    return nxt


def describe(kind):
    if kind == "drop":
        return f"Забери {nf(cfg('drop_amount'))} ⭐ — успеют первые {cfg('drop_max')} игроков (с {cfg('drop_level')} уровня)"
    m = 3 if kind == "luck3" else 5
    return f"Шанс «удачного момента» после раунда ×{m} — до 2 500 ⭐ сюрпризом. Можно поймать, даже если сегодня уже был"


def start(kind, by=0):
    t = now()
    with tx():
        db.execute("INSERT INTO flash(kind,start,end,by) VALUES(?,?,?,?)", (kind, t, t + cfg("dur_min") * 60, by))
        fid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    _LUCK["ts"] = 0
    _plan_next(t + cfg("dur_min") * 60)
    print("flash start", fid, kind, flush=True)
    return fid


def _pick():
    kinds = [k for k in KINDS if cfg("w_" + k) > 0]
    if not kinds:
        return None
    return random.choices(kinds, [cfg("w_" + k) for k in kinds])[0]


async def _notify(fid, kind):
    """Предупредить активных игроков (notif=1, заходили за 3 дня), не чаще notify_gap_h одному."""
    if not cfg("notify"):
        return
    t = now()
    ids = [r[0] for r in q("SELECT u.id FROM users u LEFT JOIN flash_notify n ON n.user=u.id WHERE u.banned=0 AND COALESCE(u.notif,1)=1 "
                           "AND u.seen>? AND (n.ts IS NULL OR n.ts<?) ORDER BY u.seen DESC LIMIT 2000", t - 3 * 86400, t - cfg("notify_gap_h") * 3600)]
    text = f"⚡ <b>{KINDS[kind]['title']}</b> — {cfg('dur_min')} минут!\n\n{describe(kind)}"
    kb = {"inline_keyboard": [[{"text": "Играть", "web_app": {"url": A.APP_URL}}]]}
    fr = __import__("franchise")
    for uid in ids:
        if not current() or current()["id"] != fid:
            break   # ивент закончился — дальше не шлём
        with A.LOCK:
            db.execute("INSERT INTO flash_notify(user,ts) VALUES(?,?) ON CONFLICT(user) DO UPDATE SET ts=excluded.ts", (uid, now()))
        try:
            tok = fr.token_for(uid)
            r = await A.tg_call("sendMessage", _token=tok, chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb)
            if not r.get("ok") and tok != A.TOKEN:
                await A.tg_call("sendMessage", _token=A.TOKEN, chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            print("flash notify", uid, e, flush=True)
        await asyncio.sleep(0.05)


async def flash_loop():
    await asyncio.sleep(30)
    if not _next_ts():
        _plan_next(now())
    while True:
        try:
            if cfg("on") and not current() and now() >= _next_ts():
                kind = _pick()
                if kind:
                    fid = start(kind)
                    asyncio.create_task(_notify(fid, kind))
                else:
                    _plan_next(now())
        except Exception as e:
            print("flash", e, flush=True)
        await asyncio.sleep(20)


# ============================== игроку ==============================
def public(uid):
    """Для /me: текущий ивент (и можно ли забрать раздачу) или время до следующего."""
    if not cfg("on"):
        return None
    f = current()
    if not f:
        n = _next_ts()
        return {"next": n} if n else None
    out = {"id": f["id"], "kind": f["kind"], "title": KINDS[f["kind"]]["title"], "desc": describe(f["kind"]), "end": f["end"]}
    if f["kind"] == "drop":
        out.update(amount=cfg("drop_amount"), left=max(0, cfg("drop_max") - f["claims"]), level=cfg("drop_level"),
                   claimed=bool(q1("SELECT 1 FROM flash_claim WHERE fid=? AND user=?", f["id"], uid)))
    return out


@app.post(R + "/flash/claim")
def claim(uid=Depends(auth)):
    f = current()
    if not (f and f["kind"] == "drop" and cfg("on")):
        err("раздача уже закончилась")
    u = q1("SELECT xp FROM users WHERE id=?", uid)
    if A.level(u["xp"]) < cfg("drop_level"):
        err(f"раздача — с {cfg('drop_level')} уровня")
    if not q1(f"SELECT 1 FROM events WHERE user=? AND ts>? AND kind IN {A.GAME_KINDS} LIMIT 1", uid, now() - 86400):
        err("сыграй хотя бы раунд за сутки — и забирай")
    amount = cfg("drop_amount")
    with tx():
        if q1("SELECT 1 FROM flash_claim WHERE fid=? AND user=?", f["id"], uid):
            err("ты уже забрал")
        if q1("SELECT claims FROM flash WHERE id=?", f["id"])["claims"] >= cfg("drop_max"):
            err("не успел — раздачу уже разобрали")
        db.execute("INSERT INTO flash_claim(fid,user,amount,ts) VALUES(?,?,?,?)", (f["id"], uid, amount, now()))
        db.execute("UPDATE flash SET claims=claims+1 WHERE id=?", (f["id"],))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, uid))
        event(uid, "flash", amount)
    return {"ok": True, "amount": amount, "stars": A.bal(uid)}


# ============================== админка ==============================
@app.get(R + "/admin/flash")
def admin_flash(aid=Depends(admin)):
    hist = []
    for r in q("SELECT * FROM flash ORDER BY id DESC LIMIT 15"):
        lucky = q1("SELECT COUNT(*) n, COALESCE(SUM(delta),0) s FROM events WHERE kind='lucky' AND ts>=? AND ts<?", r["start"], r["end"])
        paid = q1("SELECT COALESCE(SUM(amount),0) s FROM flash_claim WHERE fid=?", r["id"])["s"]
        hist.append({"id": r["id"], "kind": r["kind"], "title": KINDS[r["kind"]]["title"], "start": r["start"], "end": r["end"],
                     "claims": r["claims"], "paid": paid if r["kind"] == "drop" else lucky["s"], "lucky": lucky["n"], "manual": bool(r["by"])})
    return {"cfg": {k: cfg(k) for k in DEFAULTS}, "defaults": DEFAULTS, "changed": list(CFG), "canEdit": aid in OWNERS,
            "current": current(), "next": _next_ts(), "kinds": {k: v["title"] for k, v in KINDS.items()}, "history": hist}


@app.post(R + "/admin/flash")
async def admin_flash_set(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Менять ивенты может только владелец")
    body = await req.json()
    if not isinstance(body, dict):
        err("неверные данные")
    cur = dict(CFG)
    for k, v in body.items():
        if k not in DEFAULTS:
            continue
        if v is None:
            cur.pop(k, None)
        elif isinstance(DEFAULTS[k], bool):
            cur[k] = v in (True, 1, "1", "true")
        else:
            try:
                v = int(v)
            except (TypeError, ValueError):
                err("введи целое число")
            lo, hi = LIMITS[k]
            if not lo <= v <= hi:
                err(f"от {lo} до {hi}")
            cur[k] = v
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('flashcfg',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur),))
        log(aid, "flashcfg", None, ", ".join(f"{k}={cur.get(k, DEFAULTS[k])}" for k in DEFAULTS))
    CFG.clear()
    CFG.update(cur)
    _LUCK["ts"] = 0
    return {"ok": True}


@app.post(R + "/admin/flash/start")
async def admin_flash_start(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Запускать ивенты может только владелец")
    kind = str((await req.json()).get("kind", ""))
    if kind not in KINDS:
        err("нет такого ивента")
    if current():
        err("ивент уже идёт — дождись конца или останови")
    fid = start(kind, aid)
    with tx():
        log(aid, "flash_start", None, kind)
    asyncio.create_task(_notify(fid, kind))
    return {"ok": True}


@app.post(R + "/admin/flash/stop")
async def admin_flash_stop(aid=Depends(admin)):
    if aid not in OWNERS:
        err("Останавливать ивенты может только владелец")
    f = current() or err("сейчас ивента нет")
    with tx():
        db.execute("UPDATE flash SET end=? WHERE id=?", (now(), f["id"]))
        log(aid, "flash_stop", None, f["kind"])
    _LUCK["ts"] = 0
    _plan_next(now())
    return {"ok": True}


@app.on_event("startup")
async def _start():
    if not A.DEV:
        asyncio.create_task(flash_loop())
