"""Слияние с PWR SKINBOX: боевой пропуск (ежедневные кейсы FREE / PWR / VIP с серией) и задания (подписка, друг, реклама).

Пропуск — как в SKINBOX:
  · у каждого уровня свой кейс раз в сутки (сутки — по UTC, как задания) и своя серия; 7-й кейс подряд — улучшенный, дальше круг заново;
  · серия FREE сгорает после пропущенного дня, платные серии не сгорают;
  · PWR и VIP покупаются на 7 дней за игровые ⭐; VIP Pass также входит в VIP-статус игры (premium.py, за Telegram Stars),
    но сам статус не даёт — иначе статус за звёзды обесценил бы его продажу.
Награда кейса — ⭐ или скин CS (обычный подарок в «Сумке»). Вывода скинов в Steam здесь нет: это отдельный этап.

Задания:
  · подписка на канал (PWR_CHANNEL, бот — админ канала) — разово;
  · реклама Adsgram (ADSGRAM_BLOCK) — до 5 в сутки; награду начисляет только обратный вызов Adsgram с секретом ADS_SECRET
    (в SKINBOX награда выдавалась по запросу клиента без подтверждения просмотра — аудит 11.11, находка A10).
С пропуском PWR или VIP награды за задания ×1,5."""
import hmac
import os
import secrets

from fastapi import Depends, Request

import economy as E
from app import DEV, R, app, auth, bal, db, day_start, err, event, gift_out, is_vip, now, q, q1, tg_call, tx
from settings import conf

DAYS = 7
PRICE = {"PWR": int(conf("pass.pwr_price", 9000)), "VIP": int(conf("pass.vip_price", 20000))}
TASK_K = conf("pass.task_k", 1.5)
SUB_REWARD = int(conf("pass.sub_reward", 1000))
AD_REWARDS = [int(x) for x in conf("pass.ad_rewards", [50, 50, 150, 200, 100])]
CHANNEL = os.environ.get("PWR_CHANNEL", "").strip()          # @канал или id: подписка проверяется ботом
ADS_BLOCK = os.environ.get("ADSGRAM_BLOCK", "").strip()      # блок Adsgram (Rewarded)
ADS_SECRET = os.environ.get("ADS_SECRET", "").strip()        # секрет в Reward URL блока
TIERS = ("FREE", "PWR", "VIP")
TITLE = {"FREE": "Free", "PWR": "PWR Pass", "VIP": "VIP Pass"}
BENEFITS = {
    "FREE": ["Ежедневный кейс со звёздами и стикерами", "На 7-й день — улучшенный кейс"],
    "PWR": ["Ежедневный кейс со скинами CS", "На 7-й день — улучшенный кейс", "Награды за задания ×1,5", "Серия не сгорает"],
    "VIP": ["Ежедневный кейс с редкими скинами CS", "На 7-й день — эксклюзивный кейс", "Награды за задания ×1,5", "Серия не сгорает",
            "Уже входит в VIP-статус"],
}

db.execute("CREATE TABLE IF NOT EXISTS pwr_pass(user INTEGER, tier TEXT, streak INTEGER DEFAULT 0, last_day INTEGER DEFAULT 0, "
           "best INTEGER DEFAULT 0, resets INTEGER DEFAULT 0, PRIMARY KEY(user, tier))")
db.execute("CREATE TABLE IF NOT EXISTS pwr_tasks(user INTEGER, tid TEXT, day INTEGER, ts INTEGER, PRIMARY KEY(user, tid, day))")
try:
    db.execute("ALTER TABLE users ADD COLUMN pwr_until INTEGER DEFAULT 0")
except Exception:
    pass
try:
    db.execute("ALTER TABLE users ADD COLUMN pvip_until INTEGER DEFAULT 0")
except Exception:
    pass


# ---------------- пропуск ----------------
def _case(tier, variant):
    c = E.PWR["pass"][tier][variant]
    if "w" not in c:   # вес как в SKINBOX: (1 / цена)^1.5 — дешёвое часто, дорогое редко
        while True:   # приз с шансом ниже E.PWR_MIN_P в кейс не кладём (как и в платных кейсах)
            c["w"] = [x["usd"] ** -1.5 for x in c["items"]]
            tw = sum(c["w"])
            rare = [x for x, w in zip(c["items"], c["w"]) if w / tw < E.PWR_MIN_P]
            if not rare:
                break
            c["items"].remove(max(rare, key=lambda x: x["usd"]))
    return c


def owned(u, tier):
    if tier == "FREE":
        return True
    if tier == "PWR":
        return (u["pwr_until"] or 0) > now()
    return (u["pvip_until"] or 0) > now() or is_vip(u)


def _until(u, tier):
    return 0 if tier == "FREE" else ((u["pwr_until"] or 0) if tier == "PWR" else max(u["pvip_until"] or 0, u["vip_until"] or 0))


def _state(uid, tier):
    """(серия в круге 0..7, открыт ли сегодня, номер следующего открытия 1..7)"""
    r = q1("SELECT * FROM pwr_pass WHERE user=? AND tier=?", uid, tier)
    d0 = day_start()
    streak, last = (r["streak"], r["last_day"]) if r else (0, 0)
    if tier == "FREE" and last and d0 - last >= 2 * 86400:   # пропущен день — бесплатная серия сгорает
        streak = 0
    done = last == d0
    nxt = streak % DAYS + 1
    return streak, done, nxt


def _preview(c):
    """Что лежит в кейсе: скины по убыванию цены + диапазон звёзд."""
    tw = sum(c["w"])
    coins = [(x, w) for x, w in zip(c["items"], c["w"]) if x.get("coins")]
    skins = {}
    for x, w in zip(c["items"], c["w"]):
        if not x.get("coins"):
            s = skins.setdefault(x["col"], {"col": x["col"], "p": 0.0, "ev": E.base(x["col"])})
            s["p"] += w / tw * 100
    out = sorted(skins.values(), key=lambda s: -s["ev"])
    for s in out:
        s["p"] = round(s["p"], 2)
    stars = None
    if coins:
        vals = [E.usd_stars(x["usd"]) for x, _ in coins]
        stars = {"min": min(vals), "max": max(vals), "p": round(sum(w for _, w in coins) / tw * 100, 1)}
    return {"skins": out, "stars": stars}


def pass_state(uid):
    u = q1("SELECT * FROM users WHERE id=?", uid)
    out = []
    for tier in TIERS:
        streak, done, nxt = _state(uid, tier)
        day = (streak if streak else DAYS) if done else nxt      # день серии, который показываем: сегодняшний, если уже открыт
        variant = "improved" if day == DAYS else "default"
        c = _case(tier, variant)
        out.append({"id": tier, "title": TITLE[tier], "color": c["color"], "cover": c["cover"], "badge": "badge_" + tier.lower(),
                    "owned": owned(u, tier), "until": _until(u, tier) if owned(u, tier) else 0, "price": PRICE.get(tier, 0), "days": DAYS,
                    "day": day, "done": done, "improved": variant == "improved", "benefits": BENEFITS[tier], **_preview(c)})
    return {"tiers": out, "resetIn": day_start() + 86400 - now(), "stars": u["stars"]}


@app.post(R + "/pwr/pass/{tier}/open")
def pass_open(tier: str, uid=Depends(auth)):
    if tier not in TIERS:
        err("нет такого пропуска")
    rng = secrets.SystemRandom()
    with tx():
        u = q1("SELECT * FROM users WHERE id=?", uid)
        if not owned(u, tier):
            err(f"Нужен {TITLE[tier]}")
        streak, done, nxt = _state(uid, tier)
        if done:
            err("Сегодняшний кейс уже открыт — приходи завтра")
        c = _case(tier, "improved" if nxt == DAYS else "default")
        it = rng.choices(c["items"], weights=c["w"])[0]
        t, d0 = now(), day_start()
        old = q1("SELECT * FROM pwr_pass WHERE user=? AND tier=?", uid, tier)
        reset = 1 if old and old["streak"] and streak == 0 else 0
        db.execute("INSERT INTO pwr_pass(user,tier,streak,last_day,best,resets) VALUES(?,?,?,?,?,0) ON CONFLICT(user,tier) DO UPDATE SET "
                   "streak=?, last_day=?, best=MAX(best,?), resets=resets+?", (uid, tier, nxt, d0, nxt, nxt, d0, nxt, reset))
        out = {"day": nxt, "improved": nxt == DAYS}
        if it.get("coins"):
            got = E.usd_stars(it["usd"])
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got, uid))
            event(uid, "pass", got)
            out["reward"] = got
        else:
            d = E.roll(it["col"], rng)
            cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                             (uid, d["col"], d["model"], d["backdrop"], d["symbol"], d["num"], d["value"], t))
            event(uid, "gift", d["value"])
            out["gift"] = gift_out(q1("SELECT * FROM gifts WHERE id=?", cur.lastrowid))
    return {**out, "stars": bal(uid), "pass": pass_state(uid)}


@app.post(R + "/pwr/pass/{tier}/buy")
def pass_buy(tier: str, uid=Depends(auth)):
    if tier not in PRICE:
        err("нет такого пропуска")
    with tx():
        u = q1("SELECT * FROM users WHERE id=?", uid)
        price = PRICE[tier]
        if u["stars"] < price:
            err("Не хватает звёзд")
        col = "pwr_until" if tier == "PWR" else "pvip_until"
        until = max(now(), u[col] or 0) + DAYS * 86400
        db.execute(f"UPDATE users SET stars=stars-?, {col}=? WHERE id=?", (price, until, uid))
        event(uid, "pass", -price)
    return {"until": until, "stars": bal(uid), "pass": pass_state(uid)}


# ---------------- задания ----------------
def _k(u):
    return TASK_K if owned(u, "PWR") or owned(u, "VIP") else 1.0


def _ads_today(uid):
    return q1("SELECT COUNT(*) n FROM pwr_tasks WHERE user=? AND tid LIKE 'ad%' AND day=?", uid, day_start())["n"]


def tasks_state(uid):
    u = q1("SELECT * FROM users WHERE id=?", uid)
    k = _k(u)
    sub_done = bool(q1("SELECT 1 FROM pwr_tasks WHERE user=? AND tid='sub'", uid))
    sub_on = bool(CHANNEL) and not DEV
    ads_on = bool(ADS_BLOCK and ADS_SECRET)
    n = _ads_today(uid)
    items = [
        {"id": "sub", "icon": "megaphone", "t": "Подпишись на канал", "reward": int(SUB_REWARD * k), "done": sub_done, "on": sub_on,
         "why": "" if sub_on else "Заработает с ботом и каналом (PWR_CHANNEL)",
         "url": ("https://t.me/" + CHANNEL.lstrip("@")) if CHANNEL.startswith("@") else ""},
        {"id": "invite", "icon": "userPlus", "t": "Пригласи друга", "reward": 0, "done": False, "on": True, "why": "", "have": u["refs"]},
        {"id": "ad", "icon": "play", "t": "Посмотри рекламу", "reward": int(AD_REWARDS[min(n, len(AD_REWARDS) - 1)] * k), "done": n >= len(AD_REWARDS),
         "on": ads_on, "why": "" if ads_on else "Реклама не подключена (ADSGRAM_BLOCK)", "have": n, "need": len(AD_REWARDS)},
    ]
    return {"items": items, "k": k, "adsBlock": ADS_BLOCK if ads_on else "", "resetIn": day_start() + 86400 - now()}


@app.get(R + "/pwr")
def pwr(uid=Depends(auth)):
    return {"pass": pass_state(uid), "tasks": tasks_state(uid)}


@app.post(R + "/pwr/task/sub/claim")
async def task_sub(uid=Depends(auth)):
    if not CHANNEL or DEV:
        err("Задание пока недоступно")
    if q1("SELECT 1 FROM pwr_tasks WHERE user=? AND tid='sub'", uid):
        err("Награда уже получена")
    try:
        r = await tg_call("getChatMember", chat_id=CHANNEL, user_id=uid)
    except Exception:
        r = {}
    m = r.get("result") or {}
    if not r.get("ok") or not (m.get("status") in ("member", "administrator", "creator") or (m.get("status") == "restricted" and m.get("is_member"))):
        err("Подписка не найдена — подпишись и нажми ещё раз")
    with tx():
        if q1("SELECT 1 FROM pwr_tasks WHERE user=? AND tid='sub'", uid):
            err("Награда уже получена")
        u = q1("SELECT * FROM users WHERE id=?", uid)
        got = int(SUB_REWARD * _k(u))
        db.execute("INSERT INTO pwr_tasks VALUES(?,?,?,?)", (uid, "sub", 0, now()))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got, uid))
        event(uid, "task", got)
    return {"reward": got, "stars": bal(uid), "tasks": tasks_state(uid)}


@app.get(R + "/pwr/ads/reward")
def ads_reward(request: Request, userid: int = 0, secret: str = ""):
    """Reward URL блока Adsgram: …/np/api/pwr/ads/reward?userid=[userId]&secret=<ADS_SECRET>. Вызывает сервер Adsgram после досмотра."""
    if not ADS_SECRET or not hmac.compare_digest(secret, ADS_SECRET):
        err("forbidden", 403)
    with tx():
        u = q1("SELECT * FROM users WHERE id=?", userid) or err("нет такого игрока", 404)
        n = _ads_today(userid)
        if n >= len(AD_REWARDS):
            return {"ok": True, "limit": True}
        got = int(AD_REWARDS[n] * _k(u))
        db.execute("INSERT INTO pwr_tasks VALUES(?,?,?,?)", (userid, f"ad{n + 1}", day_start(), now()))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got, userid))
        event(userid, "task", got)
    return {"ok": True, "reward": got}
