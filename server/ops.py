"""Инструменты владельца: пульт (живые цифры на одном экране), тревоги ботом, разбор игрока, отмена действий админа.
Тревоги проверяются раз в минуту и уходят владельцам в личку (кто в «режиме секретности» — не получает).
Пороги и выключатели — kv 'alerts' (админка → Обзор → Тревоги). Повтор одной и той же тревоги — не чаще COOLDOWN."""
import asyncio
import json
import os
import shutil
import time

from fastapi import Depends, Request

from app import GAME_KINDS, R, STEALTH, app, bal, db, err, esc, event, kv_get, notify, now, q, q1, qr, tx, user_brief, day_start
from admin import ADMINS, BANNED, DB_PATH, OWNERS, admin, log

db.executescript("""
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, ts INTEGER, kind TEXT, key TEXT, text TEXT);
CREATE INDEX IF NOT EXISTS alerts_key ON alerts(key, ts);
""")
for _c in ("undo TEXT", "undone INTEGER DEFAULT 0"):
    try:
        db.execute("ALTER TABLE admin_log ADD COLUMN " + _c)
    except Exception:
        pass

# ---------------- тревоги ----------------
ALERTS = {   # вид → (название, описание порога, значение по умолчанию)
    "bigwin": ("Крупный выигрыш", "один выигрыш от, ⭐", 300_000),
    "hour": ("Игрок поднял за час", "чистый плюс в играх за час от, ⭐", 1_000_000),
    "bank": ("Просадка банка за сутки", "банк потерял за 24 ч от, ⭐", 2_000_000),
    "game": ("Игра в минусе за сегодня", "игра отдала игрокам больше, чем забрала, на ⭐", 1_000_000),
    "adminstars": ("Крупная выдача админом", "админ выдал или снял за раз от, ⭐", 1_000_000),
    "server": ("Сервер на пределе", "свободно памяти или диска меньше, %", 10),
}
COOLDOWN = {"bigwin": 0, "hour": 6 * 3600, "bank": 6 * 3600, "game": 12 * 3600, "adminstars": 0, "server": 6 * 3600}


def alerts_cfg():
    try:
        v = json.loads(kv_get("alerts", "{}") or "{}")
    except Exception:
        v = {}
    return {k: {"on": bool(v.get(k, {}).get("on", True)), "min": v.get(k, {}).get("min", d)} for k, (_, _, d) in ALERTS.items()}


def _raise(kind, key, text):
    """Записать и разослать тревогу, если такой же не было за COOLDOWN."""
    t = now()
    if COOLDOWN[kind] and q1("SELECT 1 FROM alerts WHERE key=? AND ts>?", key, t - COOLDOWN[kind]):
        return
    if not COOLDOWN[kind] and q1("SELECT 1 FROM alerts WHERE key=?", key):
        return
    with tx():
        db.execute("INSERT INTO alerts(ts,kind,key,text) VALUES(?,?,?,?)", (t, kind, key, text))
        db.execute("DELETE FROM alerts WHERE id < (SELECT MAX(id) FROM alerts) - 500")
    for o in OWNERS:
        if o not in STEALTH:
            notify(o, f"🚨 <b>{ALERTS[kind][0]}</b>\n{text}")


def _name(uid):
    u = q1("SELECT name, username FROM users WHERE id=?", uid)
    return f"{esc(u['name'])}{' @' + esc(u['username']) if u and u['username'] else ''} (id {uid})" if u else f"id {uid}"


def _fmt(n):
    return f"{int(n):,}".replace(",", " ")


_SEEN = {"bw": None, "log": None}


def _check():
    c, t = alerts_cfg(), now()
    import live
    # 1) крупные выигрыши (новые записи ленты)
    last = _SEEN["bw"] if _SEEN["bw"] is not None else (q1("SELECT MAX(id) m FROM bigwins")["m"] or 0)
    for w in q("SELECT * FROM bigwins WHERE id>? ORDER BY id", last):
        last = w["id"]
        if c["bigwin"]["on"] and w["amount"] >= c["bigwin"]["min"]:
            _raise("bigwin", f"bw{w['id']}", f"{_name(w['user'])} выиграл ⭐ {_fmt(w['amount'])} в игре «{live.NAMES.get(w['kind'], w['kind'])}»")
    _SEEN["bw"] = last
    # 2) игрок поднял за час
    if c["hour"]["on"]:
        for r in q(f"SELECT user, SUM(delta) s FROM events WHERE kind IN {GAME_KINDS} AND ts>=? GROUP BY user HAVING s>=?", t - 3600, c["hour"]["min"]):
            _raise("hour", f"hour{r['user']}", f"{_name(r['user'])}: +⭐ {_fmt(r['s'])} в играх за последний час")
    # 3) просадка банка
    if c["bank"]["on"]:
        import bank
        d = -q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE ({bank.BANK_KINDS}) AND ts>=?", t - 86400)["s"]
        if d <= -c["bank"]["min"]:
            _raise("bank", "bank", f"Банк за сутки: −⭐ {_fmt(-d)}. Сейчас в банке ⭐ {_fmt(bank.bank_value())}")
    # 4) игра в минусе за сегодня
    if c["game"]["on"]:
        for r in q(f"SELECT kind, -SUM(delta) h FROM events WHERE kind IN {GAME_KINDS} AND ts>=? GROUP BY kind HAVING h<=?", day_start(), -c["game"]["min"]):
            _raise("game", f"game{r['kind']}{day_start()}", f"«{live.NAMES.get(r['kind'], r['kind'])}» сегодня в минусе для банка: −⭐ {_fmt(-r['h'])}")
    # 5) крупные выдачи звёзд админами
    lid = _SEEN["log"] if _SEEN["log"] is not None else (q1("SELECT MAX(id) m FROM admin_log")["m"] or 0)
    for r in q("SELECT * FROM admin_log WHERE id>? ORDER BY id", lid):
        lid = r["id"]
        if c["adminstars"]["on"] and r["action"] == "stars":
            try:
                v = int(str(r["detail"]).split()[0])
            except (ValueError, IndexError):
                continue
            if abs(v) >= c["adminstars"]["min"]:
                _raise("adminstars", f"as{r['id']}", f"{_name(r['admin'])} {'выдал' if v > 0 else 'снял'} ⭐ {_fmt(abs(v))} игроку {_name(r['target'])}")
    _SEEN["log"] = lid
    # 6) сервер: память и диск
    if c["server"]["on"]:
        try:
            m = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
            mem = m["MemAvailable"] / m["MemTotal"] * 100
        except Exception:
            mem = 100
        dk = shutil.disk_usage(os.path.dirname(os.path.abspath(DB_PATH)))
        disk = dk.free / dk.total * 100
        if min(mem, disk) < c["server"]["min"]:
            _raise("server", "server", f"Свободно памяти {mem:.0f}%, диска {disk:.0f}%")


async def _loop():
    await asyncio.sleep(30)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _check)
        except Exception as e:
            print("alerts:", e, flush=True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _start():
    asyncio.create_task(_loop())


@app.get(R + "/admin/alerts")
def alerts_get(aid=Depends(admin)):
    c = alerts_cfg()
    return {"cfg": [{"k": k, "title": ALERTS[k][0], "hint": ALERTS[k][1], **c[k]} for k in ALERTS],
            "last": [dict(r) for r in q("SELECT ts, kind, text FROM alerts ORDER BY id DESC LIMIT 30")], "canEdit": aid in OWNERS}


@app.post(R + "/admin/alerts")
async def alerts_set(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("менять тревоги может только владелец")
    b = await req.json()
    k = str(b.get("k", ""))
    if k not in ALERTS:
        err("нет такой тревоги")
    c = alerts_cfg()
    if "on" in b:
        c[k]["on"] = bool(b["on"])
    if "min" in b:
        try:
            c[k]["min"] = max(1, int(float(b["min"])))
        except (TypeError, ValueError):
            err("введи число")
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('alerts',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(c),))
        log(aid, "alerts", None, f"{ALERTS[k][0]}: {'вкл' if c[k]['on'] else 'выкл'}, порог {c[k]['min']}")
    return {"ok": True}


# ---------------- пульт ----------------
@app.get(R + "/admin/pulse")
def pulse(aid=Depends(admin)):
    import bank
    import live
    t, d0 = now(), day_start()
    import hub
    games = [{"kind": r["kind"], "name": hub.HIST.get(r["kind"], r["kind"]), "rounds": r["n"], "players": r["p"], "house": r["h"]}
             for r in qr(f"SELECT kind, COUNT(*) n, COUNT(DISTINCT user) p, -SUM(delta) h FROM events WHERE kind IN {GAME_KINDS} AND ts>=? GROUP BY kind ORDER BY n DESC", d0)]
    wins = []
    for w in q("SELECT * FROM bigwins WHERE ts>=? ORDER BY amount DESC LIMIT 5", d0):
        u = q1("SELECT * FROM users WHERE id=?", w["user"])
        if u:
            wins.append({**user_brief(u), "amount": w["amount"], "game": live.NAMES.get(w["kind"], w["kind"]), "ts": w["ts"]})
    bank24 = -q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE ({bank.BANK_KINDS}) AND ts>=?", t - 86400)["s"]
    online = [q1("SELECT COUNT(*) n FROM users WHERE seen>=? AND seen<?", t - (h + 1) * 3600, t - h * 3600)["n"] for h in range(23, -1, -1)]
    sales = q1("SELECT COUNT(*) n, COALESCE(SUM(xtr),0) xtr FROM payments WHERE ts>=?", d0) if q1("SELECT name FROM sqlite_master WHERE name='payments'") else {"n": 0, "xtr": 0}
    try:
        tick = q1("SELECT COUNT(*) n FROM ticket WHERE status='open'")["n"]
    except Exception:
        tick = 0
    back = q1("SELECT COUNT(*) n, COALESCE(SUM(back),0) b FROM comeback_log WHERE ts>=?", t - 7 * 86400) if q1("SELECT name FROM sqlite_master WHERE name='comeback_log'") else {"n": 0, "b": 0}
    return {"online": q1("SELECT COUNT(*) n FROM users WHERE seen>=?", t - 300)["n"], "onlineHours": online,
            "active24": q1("SELECT COUNT(DISTINCT user) n FROM events WHERE ts>=?", t - 86400)["n"],
            "new24": q1("SELECT COUNT(*) n FROM users WHERE created>=?", t - 86400)["n"],
            "bank": bank.bank_value(), "bank24": bank24, "crisis": bank.crisis(), "houseToday": sum(g["house"] for g in games),
            "games": games, "wins": wins, "tickets": tick, "sales": dict(sales),
            "comeback": {"sent": back["n"], "back": back["b"]},
            "alerts": [dict(r) for r in q("SELECT ts, kind, text FROM alerts ORDER BY id DESC LIMIT 5")]}


# ---------------- разбор игрока ----------------
@app.get(R + "/admin/user/{tid}/insight")
def insight(tid: int, aid=Depends(admin)):
    import hub
    import live
    u = q1("SELECT * FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
    kinds = [{"kind": r["kind"], "name": hub.HIST.get(r["kind"], r["kind"]), "sum": r["s"], "n": r["n"]}
             for r in q("SELECT kind, SUM(delta) s, COUNT(*) n FROM events WHERE user=? GROUP BY kind ORDER BY ABS(SUM(delta)) DESC LIMIT 14", tid)]
    import hub
    games = [{"kind": r["kind"], "name": hub.HIST.get(r["kind"], r["kind"]), "sum": r["s"], "n": r["n"], "best": r["b"]}
             for r in q(f"SELECT kind, SUM(delta) s, COUNT(*) n, MAX(delta) b FROM events WHERE user=? AND kind IN {GAME_KINDS} GROUP BY kind ORDER BY n DESC", tid)]
    flags = []
    # переводы: с кем гоняет звёзды и сколько
    peers = []
    if q1("SELECT name FROM sqlite_master WHERE name='transfers'"):
        for r in q("""SELECT peer, SUM(sent) sent, SUM(got) got, COUNT(*) n FROM (
                        SELECT dst peer, amount sent, 0 got FROM transfers WHERE src=? UNION ALL
                        SELECT src peer, 0 sent, amount got FROM transfers WHERE dst=?) GROUP BY peer ORDER BY sent+got DESC LIMIT 6""", tid, tid):
            pu = q1("SELECT * FROM users WHERE id=?", r["peer"])
            peers.append({**(user_brief(pu) if pu else {"id": r["peer"], "name": f"id {r['peer']}"}), "sent": r["sent"], "got": r["got"], "n": r["n"]})
        for p in peers:
            if p["got"] >= 200_000 and p["got"] > 3 * max(1, p["sent"]):
                flags.append(f"Получил от {p['name']} ⭐ {p['got']:,} — возможно, перегон с другого аккаунта".replace(",", " "))
            if p["sent"] >= 200_000 and p["sent"] > 3 * max(1, p["got"]):
                flags.append(f"Отправил {p['name']} ⭐ {p['sent']:,}".replace(",", " "))
    invited_payers = q1("SELECT COUNT(*) n FROM transfers WHERE dst=? AND src IN (SELECT id FROM users WHERE ref_by=?)", tid, tid)["n"] if peers else 0
    if invited_payers >= 3:
        flags.append(f"{invited_payers} переводов от собственных рефералов — похоже на фарм приглашений")
    tot_games = sum(g["sum"] for g in games)
    rounds = sum(g["n"] for g in games)
    if rounds >= 50 and tot_games > 0 and tot_games >= 0.5 * sum(abs(g["sum"]) for g in games):
        flags.append(f"Подозрительно стабильный плюс в играх: +⭐ {tot_games:,} за {rounds} раундов".replace(",", " "))
    adm = sum(k["sum"] for k in kinds if k["kind"] == "admin")
    if adm:
        flags.append(f"Начислено администрацией: ⭐ {adm:,}".replace(",", " "))
    return {"kinds": kinds, "games": games, "peers": peers, "flags": flags, "stars": u["stars"]}


# ---------------- отмена действий админа ----------------
@app.post(R + "/admin/log/{lid}/undo")
def undo(lid: int, aid=Depends(admin)):
    with tx():
        r = q1("SELECT * FROM admin_log WHERE id=?", lid) or err("нет такой записи", 404)
        if not r["undo"]:
            err("это действие нельзя отменить")
        if r["undone"]:
            err("уже отменено")
        if aid not in OWNERS and r["admin"] != aid:
            err("отменять чужие действия может только владелец")
        u, tid = json.loads(r["undo"]), r["target"]
        k = u.get("t")
        if k == "stars":
            d = int(u["delta"])
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (d, tid))
            event(tid, "admin", d)
            what = f"звёзды {d:+d}"
        elif k == "ban":
            on = bool(u["on"])
            db.execute("UPDATE users SET banned=? WHERE id=?", (int(on), tid))
            (BANNED.add if on else BANNED.discard)(tid)
            what = "бан" if on else "разбан"
        elif k == "gift":
            n = 0
            for gid in u["ids"]:
                g = q1("SELECT * FROM gifts WHERE id=? AND owner=?", gid, tid)
                if g:
                    db.execute("DELETE FROM gifts WHERE id=?", (gid,))
                    event(tid, "gift", -g["value"])
                    n += 1
            what = f"подарки: забрано {n} из {len(u['ids'])}"
        elif k == "keys":
            db.execute("UPDATE case_keys SET n=MAX(0, n-?) WHERE user=? AND cid=?", (int(u["n"]), tid, u["cid"]))
            what = f"ключи −{u['n']}"
        elif k == "game":
            import gates
            cur = dict(gates.states())
            if u["prev"] == "on":
                cur.pop(u["gid"], None)
            else:
                cur[u["gid"]] = u["prev"]
            db.execute("INSERT INTO kv(k,v) VALUES('games',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur),))
            gates._C["t"] = 0
            what = f"{u['gid']} → {u['prev']}"
        elif k == "odds":
            if aid not in OWNERS:
                err("шансы откатывает только владелец")
            import settings
            cur = dict(settings._LIVE)
            if u["prev"] is None:
                cur.pop(u["key"], None)
            else:
                cur[u["key"]] = u["prev"]
            db.execute("INSERT INTO kv(k,v) VALUES('odds',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur),))
            settings._LIVE.clear(); settings._LIVE.update(cur)
            what = f"шансы {u['key']} → {'по умолчанию' if u['prev'] is None else u['prev']}"
        elif k == "case_name":
            import admin as _adm
            cur = json.loads(kv_get("case_names", "{}") or "{}")
            if u["prev"] is None:
                cur.pop(u["cid"], None)
            else:
                cur[u["cid"]] = u["prev"]
            db.execute("INSERT INTO kv(k,v) VALUES('case_names',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur, ensure_ascii=False),))
            _adm._load_case_names()
            what = f"название кейса {u['cid']} → {'настоящее' if u['prev'] is None else u['prev'].get('title')}"
        elif k == "case_cover":
            import admin as _adm
            cur = json.loads(kv_get("case_covers", "{}") or "{}")
            if u["prev"] is None:
                cur.pop(u["cid"], None)
            else:
                cur[u["cid"]] = u["prev"]
            db.execute("INSERT INTO kv(k,v) VALUES('case_covers',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur, ensure_ascii=False),))
            _adm._load_case_covers()
            what = f"обложка кейса {u['cid']} → {'оригинал' if u['prev'] is None else u['prev'].get('cover')}"
        elif k == "freeze":
            import sanctions
            sanctions.set_frozen(tid, bool(u["on"]), aid, "отмена")
            what = "заморозка" if u["on"] else "разморозка"
        elif k == "comp":
            got = 0
            for uid, st in u["items"]:
                take = min(int(st), max(0, bal(uid)))   # уже потраченное не уводим в минус
                if take:
                    db.execute("UPDATE users SET stars=stars-? WHERE id=?", (take, uid))
                    event(uid, "comp", -take)
                    got += take
                if u.get("keys"):
                    db.execute("UPDATE case_keys SET n=MAX(0, n-?) WHERE user=? AND cid=?", (int(u["keys"]), uid, u["cid"]))
            what = f"компенсация: снято ⭐ {got:,} у {len(u['items'])} игр.".replace(",", " ")
        elif k == "addr":
            import pay
            if u["prev"]:
                pay.addr_set(tid, u["kind"], u["prev"])
            else:
                db.execute(f"DELETE FROM {'pay_anon' if u['kind'] == 'anon' else 'pay_addr'} WHERE user=?", (tid,))
            what = f"адрес кошелька → {u['prev'] or 'новый при первом входе'}"
        else:
            err("неизвестное действие")
        db.execute("UPDATE admin_log SET undone=? WHERE id=?", (now(), lid))
        log(aid, "undo", tid, f"отмена #{lid}: {what}")
    return {"ok": True, "what": what}
