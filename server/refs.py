"""Реферальная программа: награды за друзей, которые реально играют, рубежи, доля с покупок, недельный топ.

Все числа — в админке («Рефералы»), kv 'refcfg'; settings.toml [start] ref_bonus — только значение по умолчанию.
- при регистрации по ссылке: другу new_bonus, пригласившему join_bonus;
- друг дорос до l1_level / l2_level — пригласившему l1_bonus / l2_bonus (только друзьям, пришедшим после запуска
  программы: иначе разом выплатили бы ~250 000 ⭐ за старых);
- рубежи по числу «активных» друзей (дошли до l1_level): «3:2000,10:7500,…» — считаются все друзья, и старые;
- доля с покупок: друг купил игровые звёзды за Telegram Stars — пригласившему buy_pct % (настоящие деньги — не накрутить);
- недельный топ: кто привёл больше активных друзей за неделю (по выплатам l1) — призы top_prizes, минимум top_min друзей.
Экономика: награды за друга растут с его уровнем, а не с оборотом ставок — правило «меньше 1% от оборота» не задето.
"""
import asyncio
import json
import re

from fastapi import Depends, Request

from settings import conf
import app as A
from app import R, app, auth, db, err, esc, event, notify, now, q, q1, tx, user_brief, week_start
from admin import OWNERS, admin, log


def nf(x):
    """12 345 — разделитель тысяч только в самом числе (замена по всей строке портила запятые в тексте и именах)."""
    return f"{x:,}".replace(",", " ")

DEFAULTS = {
    "on": True,
    "new_bonus": conf("start.ref_bonus", 2500),   # ⭐ другу при регистрации по ссылке
    "join_bonus": 1000,                            # ⭐ пригласившему сразу
    "l1_level": 3, "l1_bonus": 1500,               # друг дорос до уровня — пригласившему
    "l2_level": 5, "l2_bonus": 2500,
    "milestones": "3:2000,10:7500,25:20000,50:50000",   # активных друзей : ⭐
    "buy_pct": 10,                                  # % от игровых звёзд, купленных другом за Telegram Stars
    "top_on": True, "top_prizes": "15000,7500,3000", "top_min": 3,
    "gift_on": True,                                # новичку по ссылке — ключ от кейса «от друга»
    "duo_on": True, "duo_prize": 1000,              # цель на двоих: каждому (с поправкой на курс банка)
    "duo_friend": 50000, "duo_ref": 20000,          # оборот друга и пригласившего за неделю (сумма исходов)
}
LIMITS = {"new_bonus": (0, 100000), "join_bonus": (0, 100000), "l1_level": (2, 50), "l1_bonus": (0, 100000),
          "l2_level": (2, 100), "l2_bonus": (0, 200000), "buy_pct": (0, 50), "top_min": (1, 100),
          "duo_prize": (0, 50000), "duo_friend": (1000, 10_000_000), "duo_ref": (0, 10_000_000)}
CFG = {}
try:
    CFG.update({k: v for k, v in json.loads(A.kv_get("refcfg", "{}")).items() if k in DEFAULTS})
except Exception:
    pass


def cfg(k):
    return CFG.get(k, DEFAULTS[k])


def _pairs(s):
    out = []
    for p in str(s).replace(" ", "").split(","):
        if ":" in p:
            a, b = p.split(":", 1)
            out.append((int(a), int(b)))
    return sorted(out)


def _prizes(s):
    return [int(x) for x in str(s).replace(" ", "").split(",") if x]


def top_prizes():
    """Призы недельного топа с поправкой на курс банка: банк растёт — растут и призы."""
    return [A.prize_k(p) for p in _prizes(cfg("top_prizes"))]


def xp_for(L):
    return 100 * (L - 1) ** 2   # app.level(): L = √(xp/100) + 1


db.executescript("""
CREATE TABLE IF NOT EXISTS ref_pay(friend INTEGER, stage TEXT, ref INTEGER, amount INTEGER, ts INTEGER, PRIMARY KEY(friend, stage));
CREATE INDEX IF NOT EXISTS ref_pay_ref ON ref_pay(ref, stage, ts);
CREATE TABLE IF NOT EXISTS ref_ms(user INTEGER, cnt INTEGER, amount INTEGER, ts INTEGER, PRIMARY KEY(user, cnt));
CREATE TABLE IF NOT EXISTS ref_top(week INTEGER, place INTEGER, user INTEGER, n INTEGER, amount INTEGER, PRIMARY KEY(week, place));
""")
db.execute("CREATE INDEX IF NOT EXISTS users_ref_by ON users(ref_by) WHERE ref_by IS NOT NULL")
LAUNCH = int(A.kv_get("ref_v2", 0) or 0)
if not LAUNCH:   # запуск программы: награды за уровни друзей — только за пришедших после
    LAUNCH = now()
    db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('ref_v2',?)", (str(LAUNCH),))


# ============================== регистрация (из app.register, внутри его транзакции) ==============================
def bonuses(has_ref):
    """(другу, пригласившему) при регистрации."""
    if not (has_ref and cfg("on")):
        return 0, 0
    return cfg("new_bonus"), cfg("join_bonus")


# ============================== выплаты ==============================
def _active_count(ref):
    return q1("SELECT COUNT(*) n FROM users WHERE ref_by=? AND xp>=? AND banned=0", ref, xp_for(cfg("l1_level")))["n"]


def _pay(uid, amount, kind, text):
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, uid))
    event(uid, kind, amount)
    return (uid, text)


def _levels():
    """Друг дорос до l1/l2 — пригласившему бонус (друзья после запуска, один раз на этап)."""
    msgs = []
    for stage, L, bonus in (("l1", cfg("l1_level"), cfg("l1_bonus")), ("l2", cfg("l2_level"), cfg("l2_bonus"))):
        rows = q("SELECT u.id, u.name, u.ref_by FROM users u JOIN users r ON r.id=u.ref_by AND r.banned=0 "
                 "WHERE u.ref_by IS NOT NULL AND u.created>=? AND u.xp>=? AND u.banned=0 "
                 "AND NOT EXISTS (SELECT 1 FROM ref_pay p WHERE p.friend=u.id AND p.stage=?) LIMIT 500", LAUNCH, xp_for(L), stage)
        for f in rows:
            with tx():
                if q1("SELECT 1 FROM ref_pay WHERE friend=? AND stage=?", f["id"], stage):
                    continue
                db.execute("INSERT INTO ref_pay(friend,stage,ref,amount,ts) VALUES(?,?,?,?,?)", (f["id"], stage, f["ref_by"], bonus, now()))
                if bonus:
                    msgs.append(_pay(f["ref_by"], bonus, "ref_lvl", f"🎯 Твой друг <b>{esc(f['name'])}</b> дошёл до {L} уровня — тебе +{nf(bonus)} ⭐"))
    return msgs


def _milestones():
    """Рубежи по числу активных друзей — каждый один раз."""
    msgs = []
    ms = _pairs(cfg("milestones"))
    if not ms:
        return msgs
    for r in q("SELECT ref_by r, COUNT(*) n FROM users WHERE ref_by IS NOT NULL AND xp>=? AND banned=0 GROUP BY ref_by HAVING n>=?",
               xp_for(cfg("l1_level")), ms[0][0]):
        for cnt, amount in ms:
            if r["n"] < cnt:
                break
            with tx():
                if q1("SELECT 1 FROM ref_ms WHERE user=? AND cnt=?", r["r"], cnt) or not q1("SELECT 1 FROM users WHERE id=? AND banned=0", r["r"]):
                    continue
                db.execute("INSERT INTO ref_ms(user,cnt,amount,ts) VALUES(?,?,?,?)", (r["r"], cnt, amount, now()))
                msgs.append(_pay(r["r"], amount, "ref_ms", f"🏅 У тебя {cnt} активных друзей в игре — награда <b>+{nf(amount)} ⭐</b>"))
    return msgs


def _week_top(ws):
    """Активные друзья за неделю [ws, ws+7д): кому за неделю выплачен l1."""
    return q("SELECT ref, COUNT(*) n, MAX(ts) last FROM ref_pay WHERE stage='l1' AND ts>=? AND ts<? GROUP BY ref "
             "ORDER BY n DESC, last ASC LIMIT 20", ws, ws + 7 * 86400)


def _top_payout():
    """Понедельник: призы за прошлую неделю (один раз — по ref_top)."""
    if not cfg("top_on"):
        return []
    prev = week_start() - 7 * 86400
    if q1("SELECT 1 FROM ref_top WHERE week=?", prev) or prev < LAUNCH - 7 * 86400:
        return []
    msgs, prizes = [], top_prizes()
    with tx():
        if q1("SELECT 1 FROM ref_top WHERE week=?", prev):
            return []
        place = 0
        for r in _week_top(prev):
            if place >= len(prizes) or r["n"] < cfg("top_min"):
                break
            if not q1("SELECT 1 FROM users WHERE id=? AND banned=0", r["ref"]):
                continue
            amount = prizes[place]
            place += 1
            db.execute("INSERT INTO ref_top(week,place,user,n,amount) VALUES(?,?,?,?,?)", (prev, place, r["ref"], r["n"], amount))
            msgs.append(_pay(r["ref"], amount, "ref_top", f"🏆 {place} место в недельном топе приглашений ({r['n']} активных друзей) — <b>+{nf(amount)} ⭐</b>"))
        if not place:   # пометка «неделя закрыта», даже если никто не прошёл порог
            db.execute("INSERT INTO ref_top(week,place,user,n,amount) VALUES(?,0,0,0,0)", (prev,))
    return msgs


def _tick():
    if not cfg("on"):
        return
    for uid, text in _levels() + _milestones() + _top_payout() + _duo():
        notify(uid, text)


async def ref_loop():
    await asyncio.sleep(45)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _tick)
        except Exception as e:
            print("refs", e, flush=True)
        await asyncio.sleep(300)


def on_buy(uid, stars):
    """Из shop.on_paid: друг купил игровые звёзды за Telegram Stars — пригласившему buy_pct %."""
    if not (cfg("on") and cfg("buy_pct")):
        return
    u = q1("SELECT ref_by, name FROM users WHERE id=?", uid)
    if not (u and u["ref_by"]):
        return
    amount = int(stars * cfg("buy_pct") / 100)
    if amount <= 0:
        return
    with tx():
        if not q1("SELECT 1 FROM users WHERE id=? AND banned=0", u["ref_by"]):
            return
        _pay(u["ref_by"], amount, "ref_buy", "")
    notify(u["ref_by"], f"💎 Твой друг <b>{esc(u['name'])}</b> пополнил баланс — тебе {cfg('buy_pct')}%: <b>+{nf(amount)} ⭐</b>")


# ============================== подарок от друга и цель на двоих ==============================
GIFT_CASE = "starter"
DUO_DAYS = 7
DUO_LEVEL = 5   # друг должен дорасти до 5 уровня: против твинков, как во франшизе
db.executescript("""
CREATE TABLE IF NOT EXISTS ref_gift(user INTEGER PRIMARY KEY, ref INTEGER, cid TEXT, ts INTEGER, opened INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS ref_duo(friend INTEGER PRIMARY KEY, ref INTEGER, start INTEGER, until INTEGER, status TEXT DEFAULT 'open', prize INTEGER DEFAULT 0, ts INTEGER);
CREATE INDEX IF NOT EXISTS ref_duo_ref ON ref_duo(ref, status);
""")


def on_register(uid, ref):
    """Из app.register (внутри его транзакции): новичок пришёл по ссылке."""
    if not cfg("on"):
        return
    t = now()
    if cfg("gift_on"):
        db.execute("INSERT OR IGNORE INTO ref_gift(user,ref,cid,ts) VALUES(?,?,?,?)", (uid, ref, GIFT_CASE, t))
        db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,1) ON CONFLICT(user,cid) DO UPDATE SET n=n+1", (uid, GIFT_CASE))
    if cfg("duo_on"):
        db.execute("INSERT OR IGNORE INTO ref_duo(friend,ref,start,until,ts) VALUES(?,?,?,?,?)", (uid, ref, t, t + DUO_DAYS * 86400, t))


def on_key_open(uid, cid, col):
    """Из open_case (внутри транзакции): новичок открыл кейс ключом. Если это подарок друга — говорим другу."""
    r = q1("SELECT * FROM ref_gift WHERE user=? AND cid=? AND opened=0", uid, cid)
    if not r:
        return
    db.execute("UPDATE ref_gift SET opened=? WHERE user=?", (now(), uid))
    u = q1("SELECT name FROM users WHERE id=?", uid)
    notify(r["ref"], f"Подарок дошёл: у <b>{esc(u['name'] if u else 'друга')}</b> из кейса от тебя выпал <b>{esc(col)}</b>")


def gift_of(uid):
    """Неоткрытый подарок от друга — для приветствия в игре."""
    r = q1("SELECT g.ref, g.cid, u.name, k.n FROM ref_gift g JOIN users u ON u.id=g.ref LEFT JOIN case_keys k ON k.user=g.user AND k.cid=g.cid "
           "WHERE g.user=? AND g.opened=0", uid)
    if not r or not r["n"]:
        return None
    import economy as E
    c = E.CASES.get(r["cid"])
    return {"from": r["ref"], "name": r["name"], "cid": r["cid"], "title": c["title"] if c else r["cid"]}


def _turn(uid, a, b):
    return q1(f"SELECT COALESCE(SUM(ABS(delta)),0) s FROM events WHERE user=? AND kind IN {A.GAME_KINDS} AND ts>=? AND ts<?", uid, a, b)["s"]


def duo_view(d, me):
    t = now()
    other = d["ref"] if me == d["friend"] else d["friend"]
    o = q1("SELECT * FROM users WHERE id=?", other)
    f = q1("SELECT xp FROM users WHERE id=?", d["friend"])
    return {"friend": d["friend"], "ref": d["ref"], "me": "friend" if me == d["friend"] else "ref", "other": user_brief(o) if o else None,
            "fTurn": _turn(d["friend"], d["start"], d["until"]), "rTurn": _turn(d["ref"], d["start"], d["until"]),
            "fNeed": cfg("duo_friend"), "rNeed": cfg("duo_ref"), "level": A.level(f["xp"]) if f else 0, "levelNeed": DUO_LEVEL,
            "left": max(0, d["until"] - t), "prize": A.prize_k(cfg("duo_prize")), "status": d["status"]}


def _duo():
    """Цель на двоих: за неделю друг дорос до 5 уровня и набрал оборот, пригласивший тоже — награда обоим.
    Оборот — сумма исходов раундов: при возврате 94% потеря игрока не меньше 3,1% этой суммы, поэтому
    награда (по умолчанию 2 × 1 000) дешевле, чем твинку набрать оборот 50 000 + 20 000, — накрутка убыточна."""
    msgs = []
    if not (cfg("on") and cfg("duo_on")):
        return msgs
    t = now()
    for d in q("SELECT * FROM ref_duo WHERE status='open' ORDER BY start LIMIT 500"):
        f = q1("SELECT id, name, xp, banned FROM users WHERE id=?", d["friend"])
        r = q1("SELECT id, name, banned FROM users WHERE id=?", d["ref"])
        if not f or not r or f["banned"] or r["banned"]:
            with tx():
                db.execute("UPDATE ref_duo SET status='void' WHERE friend=?", (d["friend"],))
            continue
        end = min(t, d["until"])
        ok = (A.level(f["xp"]) >= DUO_LEVEL and _turn(f["id"], d["start"], end + 1) >= cfg("duo_friend")
              and _turn(r["id"], d["start"], end + 1) >= cfg("duo_ref"))
        if ok:
            prize = A.prize_k(cfg("duo_prize"))
            with tx():
                if q1("SELECT status FROM ref_duo WHERE friend=?", d["friend"])["status"] != "open":
                    continue
                db.execute("UPDATE ref_duo SET status='done', prize=? WHERE friend=?", (prize, d["friend"]))
                if prize:
                    msgs.append(_pay(f["id"], prize, "ref_duo", f"Цель с другом <b>{esc(r['name'])}</b> выполнена: тебе +{nf(prize)} ⭐"))
                    msgs.append(_pay(r["id"], prize, "ref_duo", f"Цель с другом <b>{esc(f['name'])}</b> выполнена: тебе +{nf(prize)} ⭐"))
        elif t >= d["until"]:
            with tx():
                db.execute("UPDATE ref_duo SET status='expired' WHERE friend=? AND status='open'", (d["friend"],))
    return msgs


@app.get(R + "/refs/bar")
def refs_bar(uid=Depends(auth)):
    """Баннер во вкладке «Игры»: цель на двоих (если идёт) и неделя приглашений."""
    duo = q1("SELECT * FROM ref_duo WHERE status='open' AND (friend=? OR ref=?) ORDER BY friend=? DESC, until LIMIT 1", uid, uid, uid)
    ws = week_start()
    week = None
    if cfg("on") and cfg("top_on"):
        mine = q1("SELECT COUNT(*) n FROM ref_pay WHERE stage='l1' AND ref=? AND ts>=?", uid, ws)["n"]
        top = _week_top(ws)
        place = next((i + 1 for i, r in enumerate(top) if r["ref"] == uid), 0)
        week = {"mine": mine, "place": place, "lead": top[0]["n"] if top else 0, "prizes": top_prizes(), "min": cfg("top_min"), "left": ws + 7 * 86400 - now()}
    return {"duo": duo_view(duo, uid) if duo else None, "week": week, "gift": gift_of(uid)}


# ============================== игроку ==============================
def summary(uid):
    """Для /me и /ref: что даёт программа."""
    return {"on": cfg("on"), "new": cfg("new_bonus"), "join": cfg("join_bonus"), "l1": [cfg("l1_level"), cfg("l1_bonus")],
            "l2": [cfg("l2_level"), cfg("l2_bonus")], "buyPct": cfg("buy_pct")}


@app.get(R + "/refs")
def my_refs(uid=Depends(auth)):
    u = q1("SELECT refs FROM users WHERE id=?", uid)
    active = _active_count(uid)
    earned = q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind IN ('ref','ref_lvl','ref_ms','ref_buy','ref_top','ref_duo')", uid)["s"]
    ms = _pairs(cfg("milestones"))
    got = {r["cnt"] for r in q("SELECT cnt FROM ref_ms WHERE user=?", uid)}
    friends = [{**user_brief(f), "lv": A.level(f["xp"]), "ts": f["created"]}
               for f in q("SELECT * FROM users WHERE ref_by=? ORDER BY created DESC LIMIT 50", uid)]
    ws = week_start()
    top = []
    if cfg("top_on"):
        for r in _week_top(ws)[:10]:
            b = q1("SELECT * FROM users WHERE id=?", r["ref"])
            if b:
                top.append({**user_brief(b), "n": r["n"]})
    mine = q1("SELECT COUNT(*) n FROM ref_pay WHERE stage='l1' AND ref=? AND ts>=?", uid, ws)["n"]
    return {**summary(uid), "invited": u["refs"], "active": active, "earned": earned,
            "milestones": [{"n": c, "amount": a, "done": c in got} for c, a in ms],
            "friends": friends, "top": top, "topOn": cfg("top_on"), "prizes": top_prizes(), "topMin": cfg("top_min"),
            "myWeek": mine, "weekEnds": ws + 7 * 86400, "link": f"https://t.me/{A.bot_name()}?start=ref_{uid}",
            "duos": [duo_view(d, uid) for d in q("SELECT * FROM ref_duo WHERE (ref=? OR friend=?) AND status='open' ORDER BY until LIMIT 20", uid, uid)],
            "duoOn": cfg("on") and cfg("duo_on"), "duoPrize": A.prize_k(cfg("duo_prize")), "duoFriend": cfg("duo_friend"), "duoRef": cfg("duo_ref"),
            "duoLevel": DUO_LEVEL, "duoDays": DUO_DAYS, "giftOn": cfg("on") and cfg("gift_on"),
            "giftLinks": q1("SELECT COUNT(*) n FROM gift_links WHERE sender=?", uid)["n"],
            "giftFriends": q1("SELECT COUNT(*) n FROM gift_links g JOIN users u ON u.id=g.taker WHERE g.sender=? AND u.ref_by=? AND u.created>=g.ts", uid, uid)["n"]}


# ============================== админка ==============================
@app.get(R + "/admin/refs")
def admin_refs(aid=Depends(admin)):
    t = now()
    w = t - 7 * 86400
    st = {"new7": q1("SELECT COUNT(*) n FROM users WHERE ref_by IS NOT NULL AND created>=?", w)["n"],
          "all": q1("SELECT COUNT(*) n FROM users WHERE ref_by IS NOT NULL")["n"],
          "users": q1("SELECT COUNT(*) n FROM users")["n"],
          "active": q1("SELECT COUNT(*) n FROM users WHERE ref_by IS NOT NULL AND xp>=?", xp_for(cfg("l1_level")))["n"],
          "paid7": {r["kind"]: r["s"] for r in q("SELECT kind, SUM(delta) s FROM events WHERE kind IN ('ref','ref_lvl','ref_ms','ref_buy','ref_top','ref_duo') AND ts>=? GROUP BY kind", w)}}
    top = []
    for r in q("SELECT ref_by r, COUNT(*) n, SUM(xp>=?) a FROM users WHERE ref_by IS NOT NULL AND created>=? GROUP BY ref_by ORDER BY n DESC LIMIT 10",
               xp_for(cfg("l1_level")), w):
        b = q1("SELECT * FROM users WHERE id=?", r["r"])
        if b:
            top.append({**user_brief(b), "n": r["n"], "a": r["a"]})
    return {"cfg": {k: cfg(k) for k in DEFAULTS}, "defaults": DEFAULTS, "changed": list(CFG), "canEdit": aid in OWNERS, "stats": st, "top": top}


@app.post(R + "/admin/refs")
async def admin_refs_set(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Менять рефералку может только владелец")
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
        elif k == "milestones":
            parts = [x for x in str(v).replace(" ", "").split(",") if x]   # пусто — без рубежей
            if any(not re.fullmatch(r"\d+:\d+", x) for x in parts):
                err("формат: 3:2000,10:7500 (друзей:звёзд)")
            ps = _pairs(v)
            if len(ps) > 10 or any(not (1 <= a <= 10000 and 0 <= b <= 1_000_000) for a, b in ps):
                err("до 10 рубежей, друзей 1–10000, звёзд до 1 000 000")
            cur[k] = ",".join(f"{a}:{b}" for a, b in ps)
        elif k == "top_prizes":
            if any(not x.isdigit() for x in str(v).replace(" ", "").split(",") if x):
                err("формат: 15000,7500,3000")
            ps = _prizes(v)
            if len(ps) > 10 or any(not 0 <= p <= 1_000_000 for p in ps):
                err("до 10 призов, до 1 000 000 ⭐")
            cur[k] = ",".join(map(str, ps))
        else:
            try:
                v = int(v)
            except (TypeError, ValueError):
                err("введи целое число")
            lo, hi = LIMITS[k]
            if not lo <= v <= hi:
                err(f"от {lo} до {hi}")
            cur[k] = v
    if cur.get("l2_level", DEFAULTS["l2_level"]) <= cur.get("l1_level", DEFAULTS["l1_level"]):
        err("второй уровень должен быть выше первого")
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('refcfg',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur),))
        log(aid, "refcfg", None, ", ".join(f"{k}={cur.get(k, DEFAULTS[k])}" for k in DEFAULTS))
    CFG.clear()
    CFG.update(cur)
    return {"ok": True, "cfg": {k: cfg(k) for k in DEFAULTS}}


@app.on_event("startup")
async def _start():
    if not A.DEV:
        asyncio.create_task(ref_loop())
