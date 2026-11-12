"""Кланы: до 20 игроков, казна (взносы идут в банк казино и качают уровень клана → бонус к доходу),
недельная битва кланов по обороту в играх: топ-3 получают призы от банка, делятся между участниками по вкладу."""
from settings import conf
import asyncio
import re
import time

from fastapi import Depends, Request

import app as A

import economy as E
from app import (bot_name, CLAN_TAG, CLAN_TAX, GAME_KINDS, R, app, auth, bal, db, err, esc, event, notify, now, q, q1, tx, user_brief, week_start)

db.executescript("""
CREATE TABLE IF NOT EXISTS clans(id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, tag TEXT UNIQUE COLLATE NOCASE,
  owner INTEGER, created INTEGER, treasury INTEGER DEFAULT 0, color INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS clan_members(user INTEGER PRIMARY KEY, clan INTEGER, role TEXT, joined INTEGER, donated INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS clan_members_clan ON clan_members(clan);
CREATE TABLE IF NOT EXISTS clan_left(user INTEGER PRIMARY KEY, ts INTEGER);
CREATE TABLE IF NOT EXISTS clan_wars(week INTEGER PRIMARY KEY, result TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS clan_requests(user INTEGER, clan INTEGER, ts INTEGER, PRIMARY KEY(user, clan));
CREATE TABLE IF NOT EXISTS clan_feed(id INTEGER PRIMARY KEY, clan INTEGER, user INTEGER, kind TEXT, data TEXT, ts INTEGER);
CREATE INDEX IF NOT EXISTS clan_feed_clan ON clan_feed(clan, id);
CREATE TABLE IF NOT EXISTS clan_goals(clan INTEGER, week INTEGER, tier INTEGER, ts INTEGER, PRIMARY KEY(clan, week, tier));
CREATE TABLE IF NOT EXISTS clan_chat(id INTEGER PRIMARY KEY, clan INTEGER, user INTEGER, text TEXT DEFAULT '', kind TEXT DEFAULT '', data TEXT DEFAULT '', ts INTEGER);
CREATE INDEX IF NOT EXISTS clan_chat_clan ON clan_chat(clan, id);
""")
for _c in ("emblem TEXT DEFAULT ''", "descr TEXT DEFAULT ''", "open INTEGER DEFAULT 1",
           "tax REAL DEFAULT 0", "bank INTEGER DEFAULT 0", "boost_until INTEGER DEFAULT 0", "slots INTEGER DEFAULT 20"):
    try:
        db.execute("ALTER TABLE clans ADD COLUMN " + _c)
    except Exception:
        pass
CREATE_COST = conf("clans.create_cost", 5000)
MAX_MEMBERS = 20
REJOIN = 12 * 3600
LEVELS = [0, 25_000, 75_000, 200_000, 500_000, 1_000_000, 2_000_000, 3_500_000, 5_500_000, 8_000_000]   # казна для уровней 1–10
# что открывает уровень (сверх +2% к доходу за каждый) — только «мягкие» перки, без прямых звёзд
PERKS = {3: "Цветной тег клана рядом с ником", 4: "Узор герба на обложке клана", 5: "Клановая рамка аватара всем участникам",
         6: "+5 мест в клане", 7: "−10% на оформление профиля", 8: "Сияющий тег клана", 9: "+5 мест в клане",
         10: "Золотая рамка клана и −20% на оформление"}
LEVEL_BONUS = conf("clans.level_bonus", 0.02)                                 # +2% к доходу (подарки + бизнесы) за уровень сверх первого
BASE_PRIZES = conf("clans.war_prizes", [50_000, 25_000, 10_000])


def prizes():
    """Призы битвы кланов × курс банка."""
    import app as A
    return [A.prize_k(p) for p in BASE_PRIZES]
# цели недели по обороту клана: каждому участнику — ключ от кейса
GOALS = [(250_000, "luck"), (1_000_000, "lux"), (3_000_000, "cups")]
STAFF = ("owner", "officer")
TAX_MAX = 0.05                 # налог клана: 0–5% с чистого выигрыша участников
PAY_TAX = 0.05                 # налог казино с раздачи из казны (с доли каждого участника) — меняется в админке, fees.py
DONATE_TAX = 0.0               # налог казино со взноса в казну
BOOST = (0.10, 86400)          # буст дохода: +10% на сутки
SLOTS_STEP, SLOTS_MAX = 5, 40  # расширение клана
try:
    db.execute("ALTER TABLE clan_members ADD COLUMN taxed INTEGER DEFAULT 0")
except Exception:
    pass


def boost_price(n):
    return 5_000 * max(n, 1)


def slots_price(slots):
    return 50_000 * (1 + (slots - 20) // SLOTS_STEP)


def refresh_tax():
    """Кэш налогов для app.event()."""
    CLAN_TAX.clear()
    for r in q("SELECT m.user, c.id, c.tax FROM clan_members m JOIN clans c ON c.id=m.clan WHERE c.tax>0"):
        CLAN_TAX[r["user"]] = (r["id"], r["tax"])


refresh_tax()
COLORS = 8
NAME_RE = re.compile(r"^[\w .\-!]{3,20}$")
TAG_RE = re.compile(r"^[A-ZА-ЯЁ0-9]{2,4}$")

for _r in q("SELECT m.user, c.tag FROM clan_members m JOIN clans c ON c.id=m.clan"):
    CLAN_TAG[_r["user"]] = _r["tag"]


def clan_level(treasury):
    return sum(1 for x in LEVELS if treasury >= x)


def perk_slots(lvl):
    return 5 * (lvl >= 6) + 5 * (lvl >= 9)


def cap(c):
    """Мест в клане: купленные расширения + перки уровня."""
    return (c["slots"] or MAX_MEMBERS) + perk_slots(clan_level(c["treasury"]))


def style_discount(uid):
    """Скидка на оформление профиля (style.py) по уровню клана."""
    r = q1("SELECT c.treasury FROM clan_members m JOIN clans c ON c.id=m.clan WHERE m.user=?", uid)
    lvl = clan_level(r["treasury"]) if r else 0
    return 0.2 if lvl >= 10 else 0.1 if lvl >= 7 else 0


# ---------------- вид клана в user_brief: цвет тега и уровень (кэш на 30 с) ----------------
_LOOK = {"ts": 0, "v": {}}


def look(uid):
    tag = A.CLAN_TAG.get(uid)
    if not tag:
        return {}
    if time.time() - _LOOK["ts"] > 30:
        _LOOK["v"] = {r["tag"]: (r["color"], clan_level(r["treasury"])) for r in q("SELECT tag, color, treasury FROM clans")}
        _LOOK["ts"] = time.time()
    v = _LOOK["v"].get(tag)
    return {"clanc": v[0], "clanl": v[1]} if v else {}


A.CLAN_LOOK = look


def income_bonus(uid):
    """Множитель дохода для игрока (зовёт income.py)."""
    r = q1("SELECT c.treasury, c.boost_until FROM clan_members m JOIN clans c ON c.id=m.clan WHERE m.user=?", uid)
    if not r:
        return 1.0
    return 1 + LEVEL_BONUS * (clan_level(r["treasury"]) - 1) + (BOOST[0] if (r["boost_until"] or 0) > now() else 0)


TURN_CAP = 10_000      # с одной ставки в оборот клана идёт не больше — иначе пара огромных ставок «качает» цели и битву
GOAL_ROUNDS = 20       # ключ за цель недели — только тем, кто сам сыграл хотя бы столько раундов за неделю


def _turnover(uid, since, until=None):
    return q1(f"SELECT COALESCE(SUM(MIN(ABS(delta), {TURN_CAP})),0) s FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=? AND ts<?",
              uid, since, until or 10 ** 12)["s"]


def _rounds(uid, since):
    return q1(f"SELECT COUNT(*) n FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=?", uid, since)["n"]


def _scores(clan, since):
    """Оборот участников в играх с начала недели (но не раньше, чем вступили)."""
    return {m["user"]: _turnover(m["user"], max(since, m["joined"], __import__("app").season_from())) for m in q("SELECT user, joined FROM clan_members WHERE clan=?", clan)}


def clan_brief(c, since=None):
    since = since or week_start()
    sc = _scores(c["id"], since)
    lvl = clan_level(c["treasury"])
    return {"id": c["id"], "name": c["name"], "tag": c["tag"], "color": c["color"], "emblem": c["emblem"] or "", "open": bool(c["open"]),
            "tax": c["tax"] or 0, "bank": c["bank"] or 0, "slots": cap(c), "boostUntil": c["boost_until"] or 0,
            "members": len(sc), "score": sum(sc.values()),
            "treasury": c["treasury"], "level": lvl, "next": LEVELS[lvl] if lvl < len(LEVELS) else None,
            "bonus": round(LEVEL_BONUS * (lvl - 1) * 100)}


def my_clan_id(uid):
    r = q1("SELECT clan FROM clan_members WHERE user=?", uid)
    return r["clan"] if r else None


def my_role(uid, cid):
    r = q1("SELECT role FROM clan_members WHERE user=? AND clan=?", uid, cid)
    return r["role"] if r else None


def feed(cid, uid, kind, data=""):
    """Запись в ленту клана (внутри tx). Храним последние ~60."""
    db.execute("INSERT INTO clan_feed(clan,user,kind,data,ts) VALUES(?,?,?,?,?)", (cid, uid, kind, str(data), now()))
    db.execute("DELETE FROM clan_feed WHERE clan=? AND id NOT IN (SELECT id FROM clan_feed WHERE clan=? ORDER BY id DESC LIMIT 60)", (cid, cid))
    chat_sys(cid, uid, kind, data)


def staff_ids(cid):
    return [r["user"] for r in q("SELECT user FROM clan_members WHERE clan=? AND role IN ('owner','officer')", cid)]


@app.get(R + "/clans")
def clans(uid=Depends(auth)):
    ws = week_start()
    allc = sorted((clan_brief(c, ws) for c in q("SELECT * FROM clans")), key=lambda x: -x["score"])
    for i, c in enumerate(allc):
        c["place"] = i + 1
    mine = my_clan_id(uid)
    last = q1("SELECT result FROM clan_wars ORDER BY week DESC LIMIT 1")
    return {"list": allc[:50], "mine": mine, "weekEnds": ws + 7 * 86400, "prizes": prizes(), "createCost": CREATE_COST,
            "maxMembers": MAX_MEMBERS, "levels": LEVELS, "perks": PERKS, "levelBonus": LEVEL_BONUS, "colors": COLORS,
            "last": __import__("json").loads(last["result"]) if last else None}


@app.get(R + "/clans/{cid}")
def clan(cid: int, uid=Depends(auth)):
    c = q1("SELECT * FROM clans WHERE id=?", cid) or err("клан не найден", 404)
    ws = week_start()
    sc = _scores(cid, ws)
    members = []
    for m in q("SELECT m.*, u.* FROM clan_members m JOIN users u ON u.id=m.user WHERE m.clan=?", cid):
        members.append({**user_brief(m), "role": m["role"], "donated": m["donated"], "taxed": m["taxed"] or 0, "score": sc.get(m["user"], 0), "joined": m["joined"]})
    members.sort(key=lambda x: (x["role"] != "owner", -x["score"]))
    role = my_role(uid, cid)
    br = clan_brief(c, ws)
    goals = [{"need": need, "key": E.case_title(cid_, uid), "done": bool(q1("SELECT 1 FROM clan_goals WHERE clan=? AND week=? AND tier=?", cid, ws, i))}
             for i, (need, cid_) in enumerate(GOALS)]
    fd = []
    for f in q("SELECT * FROM clan_feed WHERE clan=? ORDER BY id DESC LIMIT 25", cid):
        u = q1("SELECT * FROM users WHERE id=?", f["user"]) if f["user"] else None
        fd.append({"kind": f["kind"], "data": f["data"], "ts": f["ts"], "user": user_brief(u) if u else None})
    reqs = []
    if role in STAFF:
        for rq in q("SELECT * FROM clan_requests WHERE clan=? ORDER BY ts", cid):
            u = q1("SELECT * FROM users WHERE id=?", rq["user"])
            if u:
                reqs.append({**user_brief(u), "ts": rq["ts"]})
    return {**br, "owner": c["owner"], "created": c["created"], "descr": c["descr"] or "", "list": members, "mine": my_clan_id(uid) == cid,
            "isOwner": c["owner"] == uid, "role": role, "goals": goals, "feed": fd, "requests": reqs,
            "requested": bool(q1("SELECT 1 FROM clan_requests WHERE user=? AND clan=?", uid, cid)),
            "invite": f"https://t.me/{bot_name()}?start=clan_{cid}",
            "spend": {"boost": boost_price(len(members)), "boostPct": int(BOOST[0] * 100), "slots": slots_price(c["slots"] or MAX_MEMBERS)
                      if (c["slots"] or MAX_MEMBERS) < SLOTS_MAX else None, "slotsStep": SLOTS_STEP,
                      "keys": {k: E.CASES[k]["price"] * len(members) for k in ("luck", "lux", "cups")},
                      "keyTitles": {k: E.case_title(k, uid) for k in ("luck", "lux", "cups")}, "taxMax": TAX_MAX, "payTax": PAY_TAX, "donateTax": DONATE_TAX}}


@app.post(R + "/clans")
async def clan_create(req: Request, uid=Depends(auth)):
    b = await req.json()
    name, tag = " ".join(str(b.get("name", "")).split()), str(b.get("tag", "")).strip().upper()
    color = int(b.get("color", 0)) % COLORS
    if not NAME_RE.match(name):
        err("название: 3–20 символов, буквы, цифры, пробел")
    if not TAG_RE.match(tag):
        err("тег: 2–4 заглавные буквы или цифры")
    t = now()
    with tx():
        if my_clan_id(uid):
            err("ты уже в клане")
        if q1("SELECT 1 FROM clans WHERE name=? OR tag=?", name, tag):
            err("такое название или тег уже заняты")
        if bal(uid) < CREATE_COST:
            err(f"создание клана стоит ⭐ {CREATE_COST}")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (CREATE_COST, uid))
        event(uid, "clan", -CREATE_COST)
        cur = db.execute("INSERT INTO clans(name,tag,owner,created,color) VALUES(?,?,?,?,?)", (name, tag, uid, t, color))
        db.execute("INSERT INTO clan_members(user,clan,role,joined) VALUES(?,?,?,?)", (uid, cur.lastrowid, "owner", t))
        feed(cur.lastrowid, uid, "create")
    CLAN_TAG[uid] = tag
    return {"ok": True, "id": cur.lastrowid, "stars": bal(uid)}


@app.post(R + "/clans/{cid}/join")
def clan_join(cid: int, uid=Depends(auth)):
    t = now()
    with tx():
        c = q1("SELECT * FROM clans WHERE id=?", cid) or err("клан не найден", 404)
        if my_clan_id(uid):
            err("сначала выйди из своего клана")
        left = q1("SELECT ts FROM clan_left WHERE user=?", uid)
        if left and t - left["ts"] < REJOIN:
            err(f"вступить можно через {(left['ts'] + REJOIN - t) // 3600 + 1} ч после выхода")
        if q1("SELECT COUNT(*) n FROM clan_members WHERE clan=?", cid)["n"] >= cap(c):
            err("в клане нет мест")
        name = q1("SELECT name FROM users WHERE id=?", uid)["name"]
        if not c["open"]:   # закрытый клан — заявка, решают глава и офицеры
            if q1("SELECT 1 FROM clan_requests WHERE user=? AND clan=?", uid, cid):
                err("заявка уже отправлена")
            db.execute("INSERT INTO clan_requests(user,clan,ts) VALUES(?,?,?)", (uid, cid, t))
            staff = staff_ids(cid)
        else:
            db.execute("INSERT INTO clan_members(user,clan,role,joined) VALUES(?,?,?,?)", (uid, cid, "member", t))
            db.execute("DELETE FROM clan_requests WHERE user=?", (uid,))
            feed(cid, uid, "join")
    if not c["open"]:
        for a in staff:
            notify(a, f"🛡 <b>{esc(name)}</b> хочет вступить в клан [{esc(c['tag'])}] — открой клан, чтобы принять")
        return {"ok": True, "requested": True}
    CLAN_TAG[uid] = c["tag"]
    refresh_tax()
    notify(c["owner"], f"🛡 <b>{esc(name)}</b> вступил в клан [{esc(c['tag'])}] {esc(c['name'])}")
    return {"ok": True}


def _leave(uid, t, kicked=False):
    m = q1("SELECT * FROM clan_members WHERE user=?", uid) or err("ты не в клане")
    db.execute("DELETE FROM clan_members WHERE user=?", (uid,))
    feed(m["clan"], uid, "kick" if kicked else "leave")
    db.execute("INSERT INTO clan_left(user,ts) VALUES(?,?) ON CONFLICT(user) DO UPDATE SET ts=excluded.ts", (uid, t))
    CLAN_TAG.pop(uid, None)
    CLAN_TAX.pop(uid, None)
    if m["role"] == "owner":   # главу передаём самому давнему участнику; пустой клан распускаем
        heir = q1("SELECT user FROM clan_members WHERE clan=? ORDER BY role='officer' DESC, joined LIMIT 1", m["clan"])   # офицеры первыми
        if heir:
            db.execute("UPDATE clan_members SET role='owner' WHERE user=?", (heir["user"],))
            db.execute("UPDATE clans SET owner=? WHERE id=?", (heir["user"], m["clan"]))
            feed(m["clan"], heir["user"], "owner")
        else:
            db.execute("DELETE FROM clans WHERE id=?", (m["clan"],))
            db.execute("DELETE FROM clan_requests WHERE clan=?", (m["clan"],))


@app.post(R + "/clans/leave")
def clan_leave(uid=Depends(auth)):
    with tx():
        _leave(uid, now())
    return {"ok": True}


@app.post(R + "/clans/kick/{tid}")
def clan_kick(tid: int, uid=Depends(auth)):
    with tx():
        cid = my_clan_id(uid)
        role = my_role(uid, cid) if cid else None
        if role not in STAFF:
            err("исключать могут глава и офицеры")
        c = q1("SELECT * FROM clans WHERE id=?", cid)
        if tid == uid or my_clan_id(tid) != cid:
            err("этого игрока нет в клане")
        if role == "officer" and my_role(tid, cid) != "member":
            err("офицер может исключать только рядовых")
        _leave(tid, now(), kicked=True)
    notify(tid, f"🛡 Тебя исключили из клана [{esc(c['tag'])}] {esc(c['name'])}")
    return {"ok": True}


@app.post(R + "/clans/donate")
async def clan_donate(req: Request, uid=Depends(auth)):
    amount = int((await req.json()).get("amount", 0))
    if not 100 <= amount <= 10_000_000:
        err("взнос от ⭐ 100")
    with tx():
        cid = my_clan_id(uid) or err("ты не в клане")
        import loans
        if loans.stars_locked(uid):   # казну глава раздаёт участникам — иначе кредит уходит на основной аккаунт
            err("пока не закрыт кредит без залога, вносить в казну нельзя")
        if bal(uid) < amount:
            err("Не хватает звёзд")
        before = clan_level(q1("SELECT treasury FROM clans WHERE id=?", cid)["treasury"])
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        tax = int(amount * DONATE_TAX)
        if tax:
            event(uid, "fee", -tax)
        amount -= tax   # дальше — то, что дошло до казны
        db.execute("UPDATE clans SET treasury=treasury+?, bank=bank+? WHERE id=?", (amount, amount, cid))
        feed(cid, uid, "donate", amount)
        after = clan_level(q1("SELECT treasury FROM clans WHERE id=?", cid)["treasury"])
        if after > before:
            feed(cid, uid, "level", after)
        db.execute("UPDATE clan_members SET donated=donated+? WHERE user=?", (amount, uid))
        event(uid, "clandep", -amount)   # взнос — в казну клана (не в банк казино)
        c = q1("SELECT treasury FROM clans WHERE id=?", cid)
    return {"ok": True, "stars": bal(uid), "treasury": c["treasury"], "level": clan_level(c["treasury"]), "tax": tax}


# ---------------- итоги недели ----------------
def _settle():
    """Раз в неделю (идемпотентно): топ-3 клана по обороту получают призы, делим по вкладу участников."""
    import json
    week = week_start() - 7 * 86400
    if q1("SELECT 1 FROM clan_wars WHERE week=?", week):
        return
    msgs = []
    with tx():
        if q1("SELECT 1 FROM clan_wars WHERE week=?", week):
            return
        res = []
        for c in q("SELECT * FROM clans"):
            sc = {}
            for m in q("SELECT user, joined FROM clan_members WHERE clan=?", c["id"]):
                s = _turnover(m["user"], max(week, m["joined"]), week + 7 * 86400)
                if s > 0:
                    sc[m["user"]] = s
            if sc:
                res.append((c, sc))
        res.sort(key=lambda x: -sum(x[1].values()))
        out = []
        pz = prizes()
        for place, (c, sc) in enumerate(res[:len(pz)]):
            prize, tot = pz[place], sum(sc.values())
            for u, s in sc.items():
                pay = int(prize * s / tot)
                if pay:
                    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, u))
                    event(u, "clanprize", pay)
                    msgs.append((u, f"🏆 Клан [{esc(c['tag'])}] занял {place + 1} место в битве кланов! Твоя доля: ⭐ {pay}"))
            out.append({"place": place + 1, "id": c["id"], "name": c["name"], "tag": c["tag"], "score": tot, "prize": prize})
        db.execute("INSERT INTO clan_wars(week,result,ts) VALUES(?,?,?)", (week, json.dumps(out, ensure_ascii=False), now()))
    for u, text in msgs:
        notify(u, text)


async def clans_loop():
    await asyncio.sleep(20)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _settle)
            await asyncio.get_running_loop().run_in_executor(None, _goals)
        except Exception as e:
            print("clans:", e, flush=True)
        await asyncio.sleep(600)


@app.on_event("startup")
async def _clans_start():
    asyncio.create_task(clans_loop())


# ---------------- управление кланом ----------------
@app.post(R + "/clans/settings")
async def clan_settings(req: Request, uid=Depends(auth)):
    """Описание, герб (коллекция подарка) и открытость — глава и офицеры."""
    b = await req.json()
    with tx():
        cid = my_clan_id(uid) or err("ты не в клане")
        role = my_role(uid, cid)
        if role not in STAFF:
            err("менять клан могут глава и офицеры")
        descr = " ".join(str(b.get("descr", "")).split())[:140]
        emblem = str(b.get("emblem", ""))
        if emblem and emblem not in E.CATALOG:
            err("нет такого подарка")
        db.execute("UPDATE clans SET descr=?, emblem=?, open=? WHERE id=?", (descr, emblem, int(bool(b.get("open", True))), cid))
        if "tag" in b:   # сменить тег клана — только глава; меняется у всех участников сразу
            new_tag = str(b.get("tag", "")).strip().upper()
            cur_tag = q1("SELECT tag FROM clans WHERE id=?", cid)["tag"]
            if new_tag != cur_tag:
                if role != "owner":
                    err("менять тег клана может только глава")
                if not TAG_RE.match(new_tag):
                    err("тег: 2–4 заглавные буквы или цифры")
                if q1("SELECT 1 FROM clans WHERE tag=? AND id<>?", new_tag, cid):
                    err("такой тег уже занят")
                db.execute("UPDATE clans SET tag=? WHERE id=?", (new_tag, cid))
                for m in q("SELECT user FROM clan_members WHERE clan=?", cid):
                    CLAN_TAG[m["user"]] = new_tag   # обновляем тег в шапке у каждого члена клана
                _LOOK["ts"] = 0                      # сбросить кэш цвета/уровня тега
                feed(cid, uid, "tag", new_tag)
    return {"ok": True}


@app.post(R + "/clans/requests/{tid}/{action}")
def clan_request(tid: int, action: str, uid=Depends(auth)):
    msg = None
    with tx():
        cid = my_clan_id(uid) or err("ты не в клане")
        if my_role(uid, cid) not in (*STAFF, "captain"):
            err("заявки разбирают глава и офицеры")
        q1("SELECT 1 FROM clan_requests WHERE user=? AND clan=?", tid, cid) or err("заявки уже нет")
        db.execute("DELETE FROM clan_requests WHERE user=? AND clan=?", (tid, cid))
        c = q1("SELECT * FROM clans WHERE id=?", cid)
        if action == "accept":
            if my_clan_id(tid):
                err("игрок уже в другом клане")
            if q1("SELECT COUNT(*) n FROM clan_members WHERE clan=?", cid)["n"] >= cap(c):
                err("в клане нет мест")
            db.execute("INSERT INTO clan_members(user,clan,role,joined) VALUES(?,?,?,?)", (tid, cid, "member", now()))
            db.execute("DELETE FROM clan_requests WHERE user=?", (tid,))
            feed(cid, tid, "join")
            CLAN_TAG[tid] = c["tag"]
            if c["tax"]:
                CLAN_TAX[tid] = (cid, c["tax"])
            msg = f"🛡 Тебя приняли в клан [{esc(c['tag'])}] {esc(c['name'])}!"
        elif action != "decline":
            err("Действие устарело — обнови экран")
    if msg:
        notify(tid, msg)
    return {"ok": True}


@app.post(R + "/clans/role/{tid}")
async def clan_role(tid: int, req: Request, uid=Depends(auth)):
    """Глава: назначить офицером / разжаловать / передать главенство."""
    role = str((await req.json()).get("role", ""))
    if role not in ("officer", "member", "owner", "treasurer", "captain"):
        err("Действие устарело — обнови экран")
    with tx():
        cid = my_clan_id(uid) or err("ты не в клане")
        if my_role(uid, cid) != "owner":
            err("роли назначает только глава")
        if tid == uid or my_clan_id(tid) != cid:
            err("этого игрока нет в клане")
        if role == "owner":
            db.execute("UPDATE clan_members SET role='officer' WHERE user=?", (uid,))
            db.execute("UPDATE clan_members SET role='owner' WHERE user=?", (tid,))
            db.execute("UPDATE clans SET owner=? WHERE id=?", (tid, cid))
            feed(cid, tid, "owner")
        else:
            db.execute("UPDATE clan_members SET role=? WHERE user=?", (role, tid))
            feed(cid, tid, "officer" if role in ("officer", "treasurer", "captain") else "demote")
    return {"ok": True}


def _goals():
    """Цели недели: клан набрал оборот — каждому участнику ключ от кейса (идемпотентно, раз в 10 минут)."""
    ws = week_start()
    msgs = []
    with tx():
        for c in q("SELECT * FROM clans"):
            score = sum(_scores(c["id"], ws).values())
            for i, (need, cid_) in enumerate(GOALS):
                if score < need or q1("SELECT 1 FROM clan_goals WHERE clan=? AND week=? AND tier=?", c["id"], ws, i):
                    continue
                db.execute("INSERT INTO clan_goals(clan,week,tier,ts) VALUES(?,?,?,?)", (c["id"], ws, i, now()))
                feed(c["id"], 0, "goal", f"{need}|{E.CASES[cid_]['title']}")
                for m in q("SELECT user FROM clan_members WHERE clan=?", c["id"]):
                    if _rounds(m["user"], ws) < GOAL_ROUNDS:   # неактивным (и твинкам) ключ не положен
                        continue
                    db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,1) ON CONFLICT(user,cid) DO UPDATE SET n=n+1", (m["user"], cid_))
                    msgs.append((m["user"], f"🎯 Клан [{esc(c['tag'])}] выполнил цель недели — оборот ⭐ {need:,}! ".replace(",", " ")
                                            + f"Тебе ключ от кейса «{esc(E.case_title(cid_, m['user']))}»."))
    for u, t in msgs:
        notify(u, t)


# ---------------- налог и траты казны ----------------
@app.post(R + "/clans/tax")
async def clan_tax(req: Request, uid=Depends(auth)):
    rate = round(float((await req.json()).get("rate", 0)), 3)
    if not 0 <= rate <= TAX_MAX:
        err(f"налог от 0 до {int(TAX_MAX * 100)}%")
    with tx():
        cid = my_clan_id(uid) or err("ты не в клане")
        if my_role(uid, cid) != "owner":
            err("налог устанавливает только глава")
        c = q1("SELECT * FROM clans WHERE id=?", cid)
        db.execute("UPDATE clans SET tax=? WHERE id=?", (rate, cid))
        feed(cid, uid, "tax", rate)
        members = [r["user"] for r in q("SELECT user FROM clan_members WHERE clan=?", cid)]
    refresh_tax()
    pct = f"{rate * 100:g}%"
    for m in members:
        if m != uid:
            notify(m, f"🛡 Глава клана [{esc(c['tag'])}] " + (f"установил налог {pct} с выигрышей в казну клана." if rate else "отменил налог клана."))
    return {"ok": True, "tax": rate}


@app.post(R + "/clans/spend")
async def clan_spend(req: Request, uid=Depends(auth)):
    """Траты казны (только глава): раздача участникам, ключи всем, буст дохода, расширение клана."""
    b = await req.json()
    kind = str(b.get("kind", ""))
    msgs = []
    with tx():
        cid = my_clan_id(uid) or err("ты не в клане")
        if my_role(uid, cid) != "owner":
            err("тратить казну может только глава")
        c = q1("SELECT * FROM clans WHERE id=?", cid)
        mem = q("SELECT user FROM clan_members WHERE clan=?", cid)
        bank = c["bank"] or 0
        if kind == "pay":
            amount, mode = int(b.get("amount", 0)), str(b.get("mode", "equal"))
            if amount < 100 * len(mem):
                err(f"минимум ⭐ {100 * len(mem)} — по ⭐ 100 на участника")
            if bank < amount:
                err(f"в казне только ⭐ {bank:,}".replace(",", " "))
            if mode == "contrib":   # по вкладу за неделю (оборот в играх)
                sc = _scores(cid, week_start())
                tot = sum(sc.values())
                if not tot:
                    err("за неделю ещё никто не играл — раздай поровну")
                shares = {m["user"]: int(amount * sc.get(m["user"], 0) / tot) for m in mem}
            else:
                shares = {m["user"]: amount // len(mem) for m in mem}
            need = sum(shares.values())
            for u, x in shares.items():
                if x > 0:
                    tax = int(x * PAY_TAX)
                    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (x - tax, u))
                    event(u, "clanpay", x - tax)
                    if tax:
                        event(u, "fee", -tax)
                    msgs.append((u, f"🛡 Казна клана [{esc(c['tag'])}]: тебе ⭐ {x - tax:,}".replace(",", " ")
                                 + (f" (налог ⭐ {tax:,})".replace(",", " ") if tax else "")))
            detail = need
        elif kind == "keys":
            k = str(b.get("cid", ""))
            if k not in ("luck", "lux", "cups"):
                err("нет такого кейса")
            need = E.CASES[k]["price"] * len(mem)
            if bank < need:
                err(f"в казне не хватает: нужно ⭐ {need:,}".replace(",", " "))
            for m in mem:
                db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,1) ON CONFLICT(user,cid) DO UPDATE SET n=n+1", (m["user"], k))
                msgs.append((m["user"], f"🛡 Клан [{esc(c['tag'])}] купил всем ключ от кейса «{esc(E.case_title(k, m['user']))}» — открывай!"))
            event(uid, "clanspend", -need)
            detail = E.CASES[k]["title"]
        elif kind == "boost":
            need = boost_price(len(mem))
            if bank < need:
                err(f"в казне не хватает: нужно ⭐ {need:,}".replace(",", " "))
            db.execute("UPDATE clans SET boost_until=? WHERE id=?", (max(now(), c["boost_until"] or 0) + BOOST[1], cid))
            event(uid, "clanspend", -need)
            detail = int(BOOST[0] * 100)
            for m in mem:
                msgs.append((m["user"], f"🛡 Клан [{esc(c['tag'])}] включил буст: +{detail}% к доходу на сутки"))
        elif kind == "slots":
            sl = c["slots"] or MAX_MEMBERS
            if sl >= SLOTS_MAX:
                err("клан уже максимального размера")
            need = slots_price(sl)
            if bank < need:
                err(f"в казне не хватает: нужно ⭐ {need:,}".replace(",", " "))
            db.execute("UPDATE clans SET slots=? WHERE id=?", (sl + SLOTS_STEP, cid))
            event(uid, "clanspend", -need)
            detail = sl + SLOTS_STEP + perk_slots(clan_level(c["treasury"]))
        else:
            err("Действие устарело — обнови экран")
        db.execute("UPDATE clans SET bank=bank-? WHERE id=?", (need, cid))
        feed(cid, uid, "spend_" + kind, detail)
    for u, t in msgs:
        if u != uid:
            notify(u, t)
    return {"ok": True}


# ---------------- чат клана ----------------
CHAT_LEN = 300        # символов в сообщении
CHAT_KEEP = 400       # храним последние сообщения клана
CHAT_GAP = 1.2        # секунд между сообщениями одного игрока
CHAT_WIN = 10_000     # крупный выигрыш участника — системное сообщение в чат
_CHAT_LAST = {}


def chat_sys(cid, uid, kind, data=""):
    """Системное сообщение (внутри tx): события ленты, крупные выигрыши."""
    cur = db.execute("INSERT INTO clan_chat(clan,user,kind,data,ts) VALUES(?,?,?,?,?)", (cid, uid, kind, str(data), now()))
    if cur.lastrowid % 50 == 0:
        db.execute("DELETE FROM clan_chat WHERE clan=? AND id <= (SELECT id FROM clan_chat WHERE clan=? ORDER BY id DESC LIMIT 1 OFFSET ?)", (cid, cid, CHAT_KEEP))


def _chat_win(uid, kind, delta):
    if delta < CHAT_WIN:
        return
    cid = my_clan_id(uid)
    if cid:
        import hub
        chat_sys(cid, uid, "win", f"{hub.HIST.get(kind, kind)}|{delta}")


def chat_unread(uid):
    r = q1("SELECT clan, chat_read FROM clan_members WHERE user=?", uid)
    if not r:
        return 0
    return q1("SELECT COUNT(*) n FROM (SELECT 1 FROM clan_chat WHERE clan=? AND id>? AND kind='' AND user<>? LIMIT 99)",
              r["clan"], r["chat_read"] or 0, uid)["n"]


A.CLAN_WIN = _chat_win
A.CLAN_UNREAD = chat_unread
try:
    db.execute("ALTER TABLE clan_members ADD COLUMN chat_read INTEGER DEFAULT 0")
except Exception:
    pass


@app.get(R + "/clanchat")
def clan_chat(after: int = 0, uid=Depends(auth)):
    cid = my_clan_id(uid) or err("ты не в клане")
    rows = q("SELECT * FROM clan_chat WHERE clan=? AND id>? ORDER BY id DESC LIMIT 60", cid, max(0, after))[::-1]
    ids = {r["user"] for r in rows if r["user"]}
    users = {}
    if ids:
        for u in q(f"SELECT * FROM users WHERE id IN ({','.join('?' * len(ids))})", *ids):
            users[u["id"]] = user_brief(u)
    if rows:
        with tx():
            db.execute("UPDATE clan_members SET chat_read=MAX(COALESCE(chat_read,0),?) WHERE user=?", (rows[-1]["id"], uid))
    return {"msgs": [{"id": r["id"], "u": r["user"], "text": r["text"], "kind": r["kind"], "data": r["data"], "ts": r["ts"]} for r in rows],
            "users": users, "role": my_role(uid, cid), "max": CHAT_LEN}


@app.post(R + "/clanchat")
async def clan_chat_send(req: Request, uid=Depends(auth)):
    text = str((await req.json()).get("text", ""))
    text = re.sub(r"[\x00-\x09\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()[:CHAT_LEN]
    if not text:
        err("пустое сообщение")
    t = time.time()
    if t - _CHAT_LAST.get(uid, 0) < CHAT_GAP:
        err("не так быстро")
    _CHAT_LAST[uid] = t
    with tx():
        cid = my_clan_id(uid) or err("ты не в клане")
        cur = db.execute("INSERT INTO clan_chat(clan,user,text,ts) VALUES(?,?,?,?)", (cid, uid, text, now()))
        db.execute("UPDATE clan_members SET chat_read=? WHERE user=?", (cur.lastrowid, uid))
        if cur.lastrowid % 50 == 0:
            db.execute("DELETE FROM clan_chat WHERE clan=? AND id <= (SELECT id FROM clan_chat WHERE clan=? ORDER BY id DESC LIMIT 1 OFFSET ?)", (cid, cid, CHAT_KEEP))
    return {"ok": True, "id": cur.lastrowid}


@app.post(R + "/clanchat/del/{mid}")
def clan_chat_del(mid: int, uid=Depends(auth)):
    """Удалить сообщение: своё — любому, чужое — главе и офицерам."""
    with tx():
        cid = my_clan_id(uid) or err("ты не в клане")
        m = q1("SELECT * FROM clan_chat WHERE id=? AND clan=?", mid, cid) or err("сообщения уже нет")
        if m["user"] != uid and my_role(uid, cid) not in STAFF:
            err("удалять чужие сообщения могут глава и офицеры")
        db.execute("DELETE FROM clan_chat WHERE id=?", (mid,))
    return {"ok": True}
