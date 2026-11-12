"""Банк казино: история прибыли по дням, акции казино с дивидендами, рекордсмены против банка."""
import asyncio
import json
import time

from fastapi import Depends, Request

import app as A
from app import R, app, auth, bal, db, err, event, notify, now, q, q1, qr, qr_snap, tx, user_brief, gift_out, day_start, GAME_KINDS, BANK_START, kv_get
from settings import conf

db.executescript("""
CREATE TABLE IF NOT EXISTS shares(user INTEGER PRIMARY KEY, n INTEGER DEFAULT 0, cost INTEGER DEFAULT 0, ts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS div_days(day INTEGER PRIMARY KEY, profit INTEGER, per_share REAL, total INTEGER, holders INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS clan_shares(clan INTEGER PRIMARY KEY, n INTEGER DEFAULT 0, cost INTEGER DEFAULT 0, ts INTEGER DEFAULT 0, div INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS bank_saviors(user INTEGER PRIMARY KEY, amount INTEGER DEFAULT 0, ts INTEGER);
CREATE TABLE IF NOT EXISTS crisis_log(id INTEGER PRIMARY KEY, start INTEGER, end INTEGER DEFAULT 0, low INTEGER);
CREATE TABLE IF NOT EXISTS bank_vault(id INTEGER PRIMARY KEY, user INTEGER, gift TEXT, value INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS bank_recycled(day INTEGER PRIMARY KEY, n INTEGER DEFAULT 0, value INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY AUTOINCREMENT, user INTEGER, amount INTEGER, rate REAL,
  till INTEGER, accrued INTEGER DEFAULT 0, last INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS deposits_user ON deposits(user);
""")
SUPPLY = 100_000        # всего акций: цена = банк / SUPPLY
MAX_PER_USER = 2_000    # не больше 2% казино в одни руки
DIV_SHARE = 0.20        # доля дневной прибыли казино, уходящая держателям
DIV_FLOOR = 10_000      # делим минимум на столько акций: пара акций у единственного держателя не должна забирать всю долю
SELL_FEE = 0.03
LOCK = 86400            # продать можно через сутки после последней покупки
# С этого момента банк — единый контур: все бонусы, доходы и бизнесы платит банк, все траты идут в банк.
# Только с момента перехода: пересчёт старой истории разом обрушил бы банк в кризис.
if not kv_get("bank_v2_from"):
    db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('bank_v2_from',?)", (str(now()),))
BANK_V2 = int(kv_get("bank_v2_from"))
BANK_KINDS = f"kind IN {GAME_KINDS} OR kind IN ('jackpot','ticket','share','div','crypto','futures','fee','loan','clan','clanprize','mkbank','tourn','gameday','clanspend','lucky','season','cashback','frcut','flash','thanks','bankgift','clanshare','clandiv','league','admgift','admin','gift','comp','depint','depfee','bankyield','vaultbuy','vaultcost','giveaway','idletax','clanrecruit') OR (kind IN ('daily','quest','income','stake','bizbuy','bizsell','style','ref','ref_lvl','ref_ms','ref_buy','ref_top','ref_duo','sparks','set','album','onboard','comeback','franchise','stack','level','backing','clanbiz','auction','bizmgr','bizgoods') AND ts>={BANK_V2})"


_BV = {"ts": 0, "v": 0}
DONATE_MIN = 1
CLAN_MAX = 5_000                                         # акций у одного клана (из казны)
# кризис банка: банк ниже порога → ставки ограничены, дивиденды на паузе, подарки банку дают титул «Спаситель банка»
CRISIS_AT = conf("bank.crisis_at", 35_000_000)
CRISIS_MAX_BET = conf("bank.crisis_max_bet", 100_000)
SAVIOR_MIN = conf("bank.savior_min", 10_000)
# уровни банка: вехи размера. Каждый уровень бустит доходность вкладов (deposit_bonus за уровень)
LEVEL_AT = [conf("bank.level1_at", 50_000_000), conf("bank.level2_at", 100_000_000), conf("bank.level3_at", 250_000_000)]
DEPOSIT_BONUS = conf("bank.deposit_bonus", 0.25)
# вклады: звёзды в банке под процент. Звёзды замораживаются (банк растёт — у него больше «тела»),
# проценты капают непрерывно и выплачиваются в конце срока. Досрочно — тело минус комиссия, проценты сгорают.
DEP_MIN = conf("deposit.min", 1_000)
DEP_MAX_TOTAL = conf("deposit.max_total", 500_000)
DEP_EARLY_FEE = conf("deposit.early_fee", 0.02)
DEP_RATES = {1: conf("deposit.rate1", 0.004), 3: conf("deposit.rate3", 0.015), 7: conf("deposit.rate7", 0.04)}
DEP_MAX_N = 3


BACKING = conf("bank.backing", 0.25)   # доля купленных за Telegram Stars звёзд, которая добавляется к банку как обеспечение


def back(stars):
    """Покупка звёзд пополняет банк. Запись на служебного пользователя 0: баланс игрока не меняется."""
    v = int(stars * BACKING)
    if v > 0:
        event(0, "backing", -v)


_FK = {"ts": 0, "v": 1.0, "net": 0}
FAUCET_LOW = conf("bank.faucet_low", 0.6)


def faucet_k():
    """Стабилизатор: если за 7 дней банк в минусе, пассивные доходы и бонусы платятся не полностью. Виден всем на экране банка."""
    t = time.time()
    if t - _FK["ts"] > 300:
        net = -q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE ({BANK_KINDS}) AND kind<>'thanks' AND ts>=?", max(bank_from(), now() - 7 * 86400))["s"]
        # бонусы и доходы зависят от банка: минус за неделю режет их, а размер банка двигает от 60% до 125%
        size = max(0.6, min(1.25, bank_k()["prize"]))
        # снижение плавное: полное FAUCET_LOW — только при минусе в 5% банка, копеечный минус почти ничего не меняет
        low = 1.0 if net >= 0 else 1 - (1 - FAUCET_LOW) * min(1.0, -net / max(1, bank_value() * 0.05))
        _FK.update(ts=t, net=net, size=size, v=round(low * size, 3))
    return _FK["v"]


import app as _app  # noqa: E402
_app.FAUCET_K = faucet_k


def crisis():
    return bank_value() < CRISIS_AT


A.BET_CAP = lambda: CRISIS_MAX_BET if crisis() else None   # app.check_bet режет ставку в кризис

# курс банка = банк / база (по умолчанию стартовые 50 млн), шагом 0,05 — чтобы цены не дёргались от каждой ставки.
# От него: призы (лиги, сезон, кланы, турниры, задания) ×0,6…×2; цена кейсов −8%…+8%; скупка подарков ±5 п. п.
K_REF = conf("bank.ref", BANK_START)


def bank_k():
    r = round(bank_value() / max(1, K_REF) * 20) / 20
    return {"r": r, "prize": round(min(2.0, max(0.6, 0.4 + 0.6 * r)), 2),
            "case": round(min(1.08, max(0.92, 1 - 0.1 * (r - 1))), 2),
            "sell": round(min(0.10, max(-0.10, 0.10 * (r - 1))), 3)}


A.BANK_K = bank_k


def crisis_since():
    r = q1("SELECT start FROM crisis_log WHERE end=0 ORDER BY id DESC LIMIT 1")
    return r["start"] if r else 0


def _owners():
    try:
        from admin import OWNERS
        return list(OWNERS)
    except Exception:
        return []


def _crisis_watch():
    """Раз в минуту: вход/выход из кризиса — в журнал и владельцам в личку."""
    on, since, b = crisis(), crisis_since(), bank_value()
    if on and not since:
        with tx():
            db.execute("INSERT INTO crisis_log(start,low) VALUES(?,?)", (now(), b))
        for o in _owners():
            notify(o, f"🚨 Банк игры упал ниже ⭐ {CRISIS_AT:,} — включён КРИЗИС: ставки до ⭐ {CRISIS_MAX_BET:,}, дивиденды на паузе.".replace(",", " "))
    elif on:
        with tx():
            db.execute("UPDATE crisis_log SET low=MIN(low,?) WHERE end=0", (b,))
    elif since:
        with tx():
            db.execute("UPDATE crisis_log SET end=? WHERE end=0", (now(),))
        for o in _owners():
            notify(o, f"✅ Банк снова выше ⭐ {CRISIS_AT:,} — кризис закончился.".replace(",", " "))


# ---------------- хранилище банка: подарки, проигранные в апгрейде. Через Vault TTL перерабатываются ----------------
# Ценность подарка банк получил ещё в момент проигрыша (событие upgrade с минусом) — переработка только убирает подарок из витрины.
# Пока подарок лежит в хранилище, он приносит банку аренду (bankyield). Подарок можно выкупить обратно с наценкой.
# Настройки меняются в админке («Хранилище»), kv 'bankcfg'; settings.toml — только значения по умолчанию.
VAULT_DEFAULTS = {
    "vault_rate": conf("bank.vault_rate", 0.0005),          # доля ценности подарка в час
    "vault_day_cap": conf("bank.vault_day_cap", 0.005),    # не больше этой доли банка в сутки
    "buyback_premium": conf("bank.buyback_premium", 0.20),  # наценка при выкупе
    "vault_days": conf("bank.vault_days", 7),               # сколько дней подарок лежит в хранилище
}
VAULT_CFG = dict(VAULT_DEFAULTS)
VAULT_CUSTOM = {}
try:
    VAULT_CUSTOM.update({k: v for k, v in json.loads(kv_get("bankcfg", "{}") or "{}").items() if k in VAULT_DEFAULTS})
except Exception as e:
    print("bankcfg:", e, flush=True)
VAULT_CFG.update(VAULT_CUSTOM)


def vault_cfg(k):
    return VAULT_CFG[k]


def vault_ttl():
    return int(VAULT_CFG["vault_days"] * 86400)


def vault_put(uid, gifts):
    """Внутри tx апгрейда: копия подарка (как его видел игрок) — в хранилище."""
    for g in gifts:
        db.execute("INSERT INTO bank_vault(user,gift,value,ts) VALUES(?,?,?,?)", (uid, json.dumps(A.gift_out(g)), g["value"], now()))


A.VAULT_PUT = vault_put


def vault_take(col, model, value=0):
    """Внутри tx апгрейда: проигранный кем-то такой же подарок из хранилища (ближайший по ценности) или None. Запись из хранилища удаляется."""
    r = q1("SELECT id, gift FROM bank_vault WHERE json_extract(gift,'$.col')=? AND json_extract(gift,'$.model')=? ORDER BY ABS(value-?), id LIMIT 1", col, model, value)
    if not r:
        return None
    db.execute("DELETE FROM bank_vault WHERE id=?", (r["id"],))
    return json.loads(r["gift"])


A.VAULT_TAKE = vault_take


def _kv_set(k, v):
    db.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def vault_stats():
    """Сколько подарков в хранилище и сколько аренды они приносят банку."""
    tot = q1("SELECT COUNT(*) n, COALESCE(SUM(value),0) v FROM bank_vault")
    value = tot["v"] or 0
    rate, cap = vault_cfg("vault_rate"), vault_cfg("vault_day_cap")
    per_hour = int(value * rate)
    per_day = min(int(per_hour * 24), int(bank_value() * cap))
    y = q1("SELECT COALESCE(-SUM(delta),0) s FROM events WHERE kind='bankyield' AND ts>=?", now() - 86400)["s"]
    return {"count": tot["n"], "value": value, "rate": rate, "perHour": per_hour, "perDay": per_day,
            "yield24": y or 0, "dayCap": cap, "buyback": vault_cfg("buyback_premium"), "days": VAULT_CFG["vault_days"]}


def _vault_yield():
    """Раз в минуту: начисляем банку аренду за подарки в хранилище, не больше лимита в сутки."""
    t = now()
    last = int(kv_get("vault_yield_ts", 0) or 0)
    total = q1("SELECT COALESCE(SUM(value),0) v FROM bank_vault")["v"] or 0
    if total <= 0:
        if last:
            _kv_set("vault_yield_ts", t)
        return
    if not last:
        _kv_set("vault_yield_ts", t)
        return
    elapsed = t - last
    if elapsed < 3600:
        return
    hours = min(24, elapsed // 3600)
    gain = int(total * vault_cfg("vault_rate") * hours)
    day = day_start()
    used = int(kv_get("vault_yield_day_amt", 0) or 0) if int(kv_get("vault_yield_day", 0) or 0) == day else 0
    cap = int(bank_value() * vault_cfg("vault_day_cap"))
    gain = max(0, min(gain, cap - used))
    with tx():
        if gain > 0:
            event(0, "bankyield", -gain)
            _BV["ts"] = 0
        _kv_set("vault_yield_ts", t if elapsed >= 25 * 3600 else last + hours * 3600)
        _kv_set("vault_yield_day", day)
        _kv_set("vault_yield_day_amt", used + gain)


def _vault_recycle():
    """Раз в минуту: подарки старше срока перерабатываются (статистика по дням — bank_recycled)."""
    old = q1("SELECT COUNT(*) n, COALESCE(SUM(value),0) v FROM bank_vault WHERE ts<=?", now() - vault_ttl())
    if not old["n"]:
        return
    with tx():
        db.execute("INSERT INTO bank_recycled(day,n,value) VALUES(?,?,?) ON CONFLICT(day) DO UPDATE SET n=n+excluded.n, value=value+excluded.value",
                   (day_start(), old["n"], old["v"]))
        db.execute("DELETE FROM bank_vault WHERE ts<=?", (now() - vault_ttl(),))


@app.get(R + "/bank/vault")
def bank_vault(uid=Depends(auth)):
    t = now()
    rows = q("SELECT * FROM bank_vault ORDER BY value DESC LIMIT 200")
    seen = {r["id"] for r in rows}
    rows = list(rows) + [r for r in q("SELECT * FROM bank_vault WHERE user=?", uid) if r["id"] not in seen]
    rows.sort(key=lambda r: r["value"], reverse=True)
    names = {}
    out = []
    for r in rows:
        if r["user"] not in names:
            u = q1("SELECT * FROM users WHERE id=?", r["user"])
            names[r["user"]] = user_brief(u) if u else {"id": r["user"], "name": "Игрок"}
        g = json.loads(r["gift"])
        mine = r["user"] == uid
        out.append({"id": r["id"], "gift": g, "value": r["value"], "from": names[r["user"]], "left": max(0, r["ts"] + vault_ttl() - t), "mine": mine,
                    "buy": int(round(r["value"] * (1 + vault_cfg("buyback_premium")))) if mine else 0})
    st = vault_stats()
    rec = q1("SELECT COALESCE(SUM(n),0) n, COALESCE(SUM(value),0) v FROM bank_recycled WHERE day>=?", day_start() - 6 * 86400)
    return {"items": out, "count": st["count"], "value": st["value"], "ttl": vault_ttl(), "rent": st, "recycled": {"n": rec["n"], "value": rec["v"]}}


@app.post(R + "/bank/vault/{vid}/buy")
def bank_vault_buy(vid: int, uid=Depends(auth)):
    """Бывший владелец выкупает свой подарок из хранилища с наценкой — наценка остаётся банку."""
    with tx():
        r = q1("SELECT * FROM bank_vault WHERE id=?", vid) or err("подарок уже выкуплен или переработан", 404)
        if r["user"] != uid:
            err("выкупить может только прежний владелец")
        price = int(round(r["value"] * (1 + vault_cfg("buyback_premium"))))
        if bal(uid) < price:
            err(f"для выкупа нужно ⭐ {price:,}".replace(",", " "))
        g = json.loads(r["gift"])
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (price, uid))
        db.execute("DELETE FROM bank_vault WHERE id=?", (vid,))
        cur = db.execute("INSERT INTO gifts(owner,col,model,backdrop,symbol,num,value,created) VALUES(?,?,?,?,?,?,?,?)",
                         (uid, g["col"], g["model"], g["backdrop"], g["symbol"], g.get("num") or 0, r["value"], now()))
        event(uid, "vaultbuy", -price)
        event(0, "vaultcost", r["value"])
        _BV["ts"] = 0
        new = q1("SELECT * FROM gifts WHERE id=?", cur.lastrowid)
    return {"ok": True, "gift": gift_out(new), "stars": bal(uid), "paid": price, "bank": bank_value()}


def held_total():
    """Все акции на руках: у игроков и у кланов."""
    return q1("SELECT COALESCE(SUM(n),0) s FROM shares")["s"] + q1("SELECT COALESCE(SUM(n),0) s FROM clan_shares")["s"]


def bank_addr():
    """Адрес банка в формате кошелька (NP + 16 + контрольная сумма): на него можно перевести звёзды просто так."""
    from pay import _addr_sum
    body = "BANKGC0000000000"
    return "NP" + body + _addr_sum(body)


def donate(uid, amount):
    """Подарок банку: звёзды игрока уходят в банк, взамен ничего. Банк = старт − сумма событий, поэтому событие с минусом растит банк."""
    if amount < DONATE_MIN:
        err(f"минимум {DONATE_MIN} ⭐")
    with tx():
        if bal(uid) < amount:
            err("Не хватает звёзд")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        event(uid, "bankgift", -amount)
        if crisis():   # в кризис подарок засчитывается в «Спасители банка»
            db.execute("INSERT INTO bank_saviors(user,amount,ts) VALUES(?,?,?) ON CONFLICT(user) DO UPDATE SET amount=amount+excluded.amount, ts=excluded.ts",
                       (uid, amount, now()))
    _BV["ts"] = 0
    return {"ok": True, "stars": bal(uid), "bank": bank_value()}


def bank_from():
    """С какого момента считаем банк: вайп (wipe.py) сбрасывает его к стартовому резерву — kv 'bank_from'."""
    return int(kv_get("bank_from", 0) or 0)


_TOPS = {"t": 0, "from": None}
TOPS_TTL = 20   # лучшие и худшие за сезон — один проход по журналу на всех, не чаще раза в 20 с


def _tops():
    frm = bank_from()
    if time.time() - _TOPS["t"] > TOPS_TTL or _TOPS["from"] != frm:
        rows = [(r["user"], r["s"]) for r in qr(f"SELECT user, SUM(delta) s FROM events WHERE kind IN {GAME_KINDS} AND ts>=? GROUP BY user", frm)]
        rows.sort(key=lambda x: -x[1])
        _TOPS.update(t=time.time(), **{"from": frm, "DESC": rows[:5], "ASC": sorted(rows[-5:], key=lambda x: x[1]) if rows else []})
    return _TOPS


def bank_value():
    """Банк казино. Журнал быстро растёт, поэтому считаем только новые записи; раз в час — полная сверка."""
    t = time.time()
    if t - _BV["ts"] > 15:
        with A.LOCK:   # снимок «последняя запись + сумма» целиком, чтобы фоновая сверка и запрос не перемешались
            last = (q1("SELECT MAX(rowid) m FROM events") or {"m": 0})["m"] or 0
            frm = bank_from()
            # ts=0 после операции с банком — только подтянуть новые записи; с нуля — при смене сезона банка и раз в час в фоне (_bv_loop)
            if _BV.get("from") != frm or "sum" not in _BV:
                s_ = q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE ({BANK_KINDS}) AND ts>=? AND rowid<=?", frm, last)["s"]
                _BV.update(sum=s_, full=t, **{"from": frm})
            elif last > _BV.get("last", 0):
                _BV["sum"] += q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE ({BANK_KINDS}) AND ts>=? AND rowid>?", frm, _BV["last"])["s"]
            _BV.update(ts=t, last=last, v=BANK_START - _BV["sum"])
    return _BV["v"]


def price():
    return max(1, round(bank_value() / SUPPLY))


def house_profit(day):
    return -q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind IN {GAME_KINDS} AND ts>=? AND ts<?", max(day, bank_from()), day + 86400)["s"]


def _pay(day):
    """Дивиденды за прошедший день (идемпотентно): DIV_SHARE прибыли делится на все акции у игроков."""
    with tx():
        if q1("SELECT 1 FROM div_days WHERE day BETWEEN ? AND ?", day - 60, day + 60):   # за этот день уже платили
            return []
        profit = house_profit(day)
        holders = q("SELECT user, n FROM shares WHERE n>0")
        clans_h = q("SELECT clan, n FROM clan_shares WHERE n>0")
        held = sum(h["n"] for h in holders) + sum(c["n"] for c in clans_h)
        per = DIV_SHARE * profit / max(held, DIV_FLOOR) if profit > 0 and held and not crisis() else 0   # в кризис дивиденды на паузе
        paid, cpaid = [], []
        for c in clans_h:   # клановые акции — дивиденды в казну клана
            amount = int(per * c["n"])
            if amount > 0:
                db.execute("UPDATE clans SET bank=bank+? WHERE id=?", (amount, c["clan"]))
                db.execute("UPDATE clan_shares SET div=div+? WHERE clan=?", (amount, c["clan"]))
                event(0, "clandiv", amount)
                cpaid.append((c["clan"], amount))
        for h in holders:
            amount = int(per * h["n"])
            if amount > 0:
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, h["user"]))
                event(h["user"], "div", amount)
                paid.append((h["user"], amount))
        db.execute("INSERT INTO div_days VALUES(?,?,?,?,?,?)", (day, profit, per, sum(a for _, a in paid) + sum(a for _, a in cpaid), len(paid), now()))
        if cpaid:
            import clans
            for cid, a in cpaid:
                o = q1("SELECT owner FROM clans WHERE id=?", cid)
                clans.feed(cid, o["owner"] if o else 0, "sharediv", a)
    for u, a in paid:
        notify(u, f"Дивиденды банка: +{a} ⭐ (игровых) за вчера.")
    return paid


async def div_loop():
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _pay, day_start() - 86400)
        except Exception as e:
            print("div:", e, flush=True)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _vault_yield)
        except Exception as e:
            print("vault yield:", e, flush=True)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _vault_recycle)
        except Exception as e:
            print("vault:", e, flush=True)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _crisis_watch)
        except Exception as e:
            print("crisis:", e, flush=True)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _dep_accrue)
        except Exception as e:
            print("dep:", e, flush=True)
        await asyncio.sleep(60)


@app.on_event("startup")
async def _div_start():
    asyncio.create_task(div_loop())


@app.get(R + "/bank/info")
def bank_info(uid=Depends(auth)):
    d = day_start()
    days = []
    for i in range(13, -1, -1):
        s = d - i * 86400
        days.append({"day": s, "profit": house_profit(s)})
    me = q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind IN {GAME_KINDS} AND ts>=?", uid, bank_from())["s"]
    sh = q1("SELECT * FROM shares WHERE user=?", uid)
    held = held_total()
    frm = bank_from()   # экран банка показывает только текущий сезон
    last = q1("SELECT * FROM div_days WHERE ts>=? ORDER BY day DESC LIMIT 1", frm)
    my_div = q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind='div' AND ts>=?", uid, frm)["s"]

    tops = _tops()

    def top(order):
        out = []
        for uid_, s_ in tops["DESC" if order == "DESC" else "ASC"]:
            u = q1("SELECT * FROM users WHERE id=?", uid_)
            if u and (s_ > 0 if order == "DESC" else s_ < 0):
                out.append({**user_brief(u), "sum": s_})
        return out
    donors = []
    for r in qr("SELECT user, -SUM(delta) s FROM events WHERE kind='bankgift' AND ts>=? GROUP BY user ORDER BY s DESC LIMIT 5", bank_from()):
        u = q1("SELECT * FROM users WHERE id=?", r["user"])
        if u:
            donors.append({**user_brief(u), "sum": r["s"]})
    gifted = q1("SELECT COALESCE(-SUM(delta),0) s FROM events WHERE user=? AND kind='bankgift' AND ts>=?", uid, frm)["s"]
    saviors = []
    for r in q("SELECT * FROM bank_saviors ORDER BY amount DESC LIMIT 5"):
        u = q1("SELECT * FROM users WHERE id=?", r["user"])
        if u:
            saviors.append({**user_brief(u), "sum": r["amount"]})
    sv = q1("SELECT amount FROM bank_saviors WHERE user=?", uid)
    clan_holders = [{"id": r["id"], "tag": r["tag"], "name": r["name"], "n": r["n"]}
                    for r in q("SELECT c.id, c.tag, c.name, s.n FROM clan_shares s JOIN clans c ON c.id=s.clan WHERE s.n>0 ORDER BY s.n DESC LIMIT 5")]
    holders = []
    for r in q("SELECT * FROM shares WHERE n>0 ORDER BY n DESC LIMIT 5"):
        u = q1("SELECT * FROM users WHERE id=?", r["user"])
        if u:
            holders.append({**user_brief(u), "n": r["n"]})
    p = price()
    n = sh["n"] if sh else 0
    today = house_profit(d)
    return {
        "bank": bank_value(), "start": BANK_START, "k": {**bank_k(), "sellRate": A.sell_rate(), "ref": K_REF}, "today": today, "days": days, "me": me,
        "price": p, "supply": SUPPLY, "held": held, "maxPer": MAX_PER_USER, "sellFee": SELL_FEE, "divShare": DIV_SHARE, "divFloor": DIV_FLOOR,
        "mine": {"n": n, "cost": sh["cost"] if sh else 0, "value": n * p, "div": my_div,
                 "sellIn": max(0, sh["ts"] + LOCK - now()) if n else 0,
                 "est": int(DIV_SHARE * max(0, today) / max(held, DIV_FLOOR) * n) if n else 0},
        "lastDiv": {"perShare": round(last["per_share"], 2), "total": last["total"], "profit": last["profit"]} if last else None,
        "endsIn": d + 86400 - now(), "robbers": top("DESC"), "sponsors": top("ASC"), "holders": holders,
        "vault": vault_stats(),
        "addr": bank_addr(), "donors": donors, "gifted": gifted, "clanHolders": clan_holders, "clanMax": CLAN_MAX,
        "lvl": level_info(), "faucet": {"k": faucet_k(), "net7": _FK["net"], "backing": BACKING},
        "emission": {   # публичная прозрачность: сколько напечатала администрация (игроки видят на экране банка)
            "week": q1("SELECT COALESCE(SUM(delta),0) s, COUNT(*) n FROM events WHERE kind IN ('admgift','admin','comp') AND delta>0 AND ts>=?", max(frm, now() - 7 * 86400)),
            "total": q1("SELECT COALESCE(SUM(delta),0) s, COUNT(*) n FROM events WHERE kind IN ('admgift','admin','comp') AND delta>0 AND ts>=?", frm),
            "keysWeek": q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind='gift' AND delta>0 AND ts>=?", max(frm, now() - 7 * 86400)),
        },
        "crisis": {"on": crisis(), "at": CRISIS_AT, "maxBet": CRISIS_MAX_BET, "since": crisis_since(), "saviorMin": SAVIOR_MIN,
                   "saviors": saviors, "mine": sv["amount"] if sv else 0, "need": max(0, CRISIS_AT - bank_value())},
    }


def ticker():
    """Для плашки банка: кризис и последний крупный выигрыш (не старше минуты)."""
    w = q1("SELECT * FROM bigwins WHERE ts>=? ORDER BY id DESC LIMIT 1", now() - 60)
    win = None
    if w:
        import live
        u = q1("SELECT * FROM users WHERE id=?", w["user"])
        win = {"id": w["id"], "amount": w["amount"], "game": live.NAMES.get(w["kind"], w["kind"]), "name": user_brief(u)["name"] if u else "Игрок"}
    return {"crisis": crisis(), "crisisAt": CRISIS_AT, "win": win, "lvl": bank_level()}


# ---------------- акции банка у кланов: покупает и продаёт глава из казны, дивиденды — в казну ----------------
def _my_clan(uid):
    import clans
    cid = clans.my_clan_id(uid)
    return (cid, clans.my_role(uid, cid)) if cid else (None, None)


@app.get(R + "/bank/clan")
def bank_clan(uid=Depends(auth)):
    cid, role = _my_clan(uid)
    if not cid:
        return {"clan": None}
    c = q1("SELECT bank FROM clans WHERE id=?", cid)
    sh = q1("SELECT * FROM clan_shares WHERE clan=?", cid)
    n, p, held = (sh["n"] if sh else 0), price(), held_total()
    return {"clan": cid, "owner": role == "owner", "pool": c["bank"] or 0, "n": n, "cost": sh["cost"] if sh else 0, "value": n * p, "price": p,
            "div": sh["div"] if sh else 0, "max": CLAN_MAX, "room": max(0, min(CLAN_MAX - n, SUPPLY - held)),
            "sellIn": max(0, sh["ts"] + LOCK - now()) if n else 0, "sellFee": SELL_FEE, "crisis": crisis(),
            "est": int(DIV_SHARE * max(0, house_profit(day_start())) / max(held, DIV_FLOOR) * n) if n and not crisis() else 0}


@app.post(R + "/bank/clan")
async def bank_clan_trade(req: Request, uid=Depends(auth)):
    n = int((await req.json()).get("n", 0))
    if not n or abs(n) > CLAN_MAX:
        err("Неверное количество")
    import clans
    with tx():
        cid, role = _my_clan(uid)
        if not cid:
            err("ты не в клане")
        if role != "owner":
            err("акциями клана распоряжается только глава")
        p = price()
        c = q1("SELECT bank FROM clans WHERE id=?", cid)
        sh = q1("SELECT * FROM clan_shares WHERE clan=?", cid) or {"n": 0, "cost": 0, "ts": 0}
        if n > 0:
            if sh["n"] + n > CLAN_MAX:
                err(f"клан может держать не больше {CLAN_MAX:,} акций".replace(",", " "))
            if held_total() + n > SUPPLY:
                err("Свободных акций не осталось")
            cost = n * p
            if (c["bank"] or 0) < cost:
                err(f"в казне только ⭐ {c['bank'] or 0:,}".replace(",", " "))
            db.execute("UPDATE clans SET bank=bank-? WHERE id=?", (cost, cid))
            db.execute("INSERT INTO clan_shares(clan,n,cost,ts) VALUES(?,?,?,?) ON CONFLICT(clan) DO UPDATE SET n=n+?, cost=cost+?, ts=?",
                       (cid, n, cost, now(), n, cost, now()))
            event(0, "clanshare", -cost)
            clans.feed(cid, uid, "sharebuy", n)
        else:
            n = -n
            if n > sh["n"]:
                err("у клана нет столько акций")
            if sh["ts"] + LOCK > now():
                left = sh["ts"] + LOCK - now()
                err(f"Продать можно через {left // 3600} ч {left % 3600 // 60} мин после покупки")
            got = int(n * p * (1 - SELL_FEE))
            db.execute("UPDATE clans SET bank=bank+? WHERE id=?", (got, cid))
            db.execute("UPDATE clan_shares SET n=n-?, cost=cost-? WHERE clan=?", (n, round(sh["cost"] * n / sh["n"]), cid))
            event(0, "clanshare", got)
            clans.feed(cid, uid, "sharesell", got)
    _BV["ts"] = 0
    return bank_clan(uid)


@app.post(R + "/bank/donate")
async def bank_donate(req: Request, uid=Depends(auth)):
    b = await req.json()
    try:
        amount = int(b.get("amount", 0))
    except (TypeError, ValueError):
        err("введи сумму")
    return donate(uid, amount)


@app.post(R + "/bank/shares")
async def bank_shares(req: Request, uid=Depends(auth)):
    b = await req.json()
    n = int(b.get("n", 0))
    if not n or abs(n) > MAX_PER_USER:
        err("Неверное количество")
    with tx():
        p = price()
        sh = q1("SELECT * FROM shares WHERE user=?", uid) or {"n": 0, "cost": 0, "ts": 0}
        if n > 0:
            if sh["n"] + n > MAX_PER_USER:
                err(f"Можно держать не больше {MAX_PER_USER} акций")
            held = held_total()
            if held + n > SUPPLY:
                err("Свободных акций не осталось")
            cost = n * p
            if bal(uid) < cost:
                err("Не хватает звёзд")
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (cost, uid))
            db.execute("INSERT INTO shares(user,n,cost,ts) VALUES(?,?,?,?) ON CONFLICT(user) DO UPDATE SET n=n+?, cost=cost+?, ts=?",
                       (uid, n, cost, now(), n, cost, now()))
            event(uid, "share", -cost)
        else:
            n = -n
            if n > sh["n"]:
                err("У тебя нет столько акций")
            if sh["ts"] + LOCK > now():
                left = sh["ts"] + LOCK - now()
                err(f"Продать можно через {left // 3600} ч {left % 3600 // 60} мин после покупки")
            got = int(n * p * (1 - SELL_FEE))
            cost_part = round(sh["cost"] * n / sh["n"])
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got, uid))
            db.execute("UPDATE shares SET n=n-?, cost=cost-? WHERE user=?", (n, cost_part, uid))
            event(uid, "share", got)
    return {"ok": True, "stars": bal(uid)}


# ---------------- уровни банка и вклады ----------------
def bank_level(v=None):
    """0–3: сколько вех размера банка пройдено. Вехи — в settings.toml [bank] level1_at…"""
    v = bank_value() if v is None else v
    return int(v >= LEVEL_AT[0]) + int(v >= LEVEL_AT[1]) + int(v >= LEVEL_AT[2])


def level_info():
    v, l = bank_value(), bank_level()
    nxt = next((x for x in LEVEL_AT if v < x), None)
    return {"lvl": l, "next": nxt, "at": LEVEL_AT, "bonus": DEPOSIT_BONUS,
            "progress": 0 if nxt is None else round((v - (LEVEL_AT[l - 1] if l else 0)) / (nxt - (LEVEL_AT[l - 1] if l else 0)) * 100, 1)}


def _dep_earned(d, t=None):
    """Начислено на сейчас. rate — доходность за весь срок: растёт равномерно от открытия до конца срока."""
    t = now() if t is None else t
    term = max(1, d["till"] - d["ts"])
    return int(d["amount"] * d["rate"] * min(1.0, max(0, t - d["ts"]) / term))


def _dep_accrue():
    """Раз в минуту закрываем вклады с вышедшим сроком. Проценты платит банк (depint), тело — это деньги игрока (dep)."""
    t = now()
    for d in q("SELECT * FROM deposits WHERE till<=?", t):
        with tx():
            d = q1("SELECT * FROM deposits WHERE id=?", d["id"])   # перечитали под локом
            if not d:
                continue
            earned = _dep_earned(d, d["till"])
            db.execute("DELETE FROM deposits WHERE id=?", (d["id"],))
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (d["amount"] + earned, d["user"]))
            event(d["user"], "dep", d["amount"])
            if earned:
                event(d["user"], "depint", earned)
        _BV["ts"] = 0
        notify(d["user"], f"🏦 Вклад закрылся: <b>+{d['amount'] + earned:,} ⭐</b>, из них проценты {earned:,} ⭐.".replace(",", " "))


@app.get(R + "/bank/deposits")
def dep_info(uid=Depends(auth)):
    bonus = 1 + DEPOSIT_BONUS * bank_level()
    t = now()
    mine = []
    total = 0
    for d in q("SELECT * FROM deposits WHERE user=? ORDER BY till", uid):
        total += d["amount"]
        mine.append({"id": d["id"], "amount": d["amount"], "rate": round(d["rate"] * 100, 2), "accrued": _dep_earned(d, t),
                     "till": d["till"], "left": max(0, d["till"] - t), "days": round((d["till"] - d["ts"]) / 86400, 1)})
    return {"rates": {str(k): round(v * bonus * 100, 2) for k, v in DEP_RATES.items()}, "days": list(DEP_RATES),
            "min": DEP_MIN, "maxTotal": DEP_MAX_TOTAL, "earlyFee": DEP_EARLY_FEE, "maxN": DEP_MAX_N,
            "mine": mine, "total": total, "level": level_info(), "crisis": crisis(), "stars": bal(uid)}


@app.post(R + "/bank/deposit")
async def dep_open(req: Request, uid=Depends(auth)):
    b = await req.json()
    amount, days = int(b.get("amount", 0)), int(b.get("days", 0))
    rate = DEP_RATES.get(days) or err("срок — 1, 3 или 7 дней")
    rate *= 1 + DEPOSIT_BONUS * bank_level()
    if crisis():
        err("Банк в кризисе — вклады закрыты, дождись восстановления")
    with tx():
        if amount < DEP_MIN:
            err(f"вклад от ⭐ {DEP_MIN:,}".replace(",", " "))
        if bal(uid) < amount:
            err("Не хватает звёзд")
        if q1("SELECT COUNT(*) n FROM deposits WHERE user=?", uid)["n"] >= DEP_MAX_N:
            err(f"не больше {DEP_MAX_N} вкладов одновременно")
        if q1("SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE user=?", uid)["s"] + amount > DEP_MAX_TOTAL:
            err(f"вклады суммарно не больше ⭐ {DEP_MAX_TOTAL:,}".replace(",", " "))
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount, uid))
        db.execute("INSERT INTO deposits(user,amount,rate,till,accrued,last,ts) VALUES(?,?,?,?,0,?,?)",
                   (uid, amount, rate, now() + days * 86400, now(), now()))
        event(uid, "dep", -amount)   # тело вклада остаётся деньгами игрока и в размер банка не входит
    _BV["ts"] = 0
    return {"ok": True, "stars": bal(uid), "bank": bank_value()}


@app.post(R + "/bank/deposit/withdraw")
async def dep_withdraw(req: Request, uid=Depends(auth)):
    did = int((await req.json()).get("id", 0))
    with tx():
        d = q1("SELECT * FROM deposits WHERE id=? AND user=?", did, uid) or err("вклад не найден")
        early = now() < d["till"]
        fee = int(d["amount"] * DEP_EARLY_FEE) if early else 0
        earned = 0 if early else _dep_earned(d, d["till"])
        pay = d["amount"] - fee + earned
        db.execute("DELETE FROM deposits WHERE id=?", (did,))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
        event(uid, "dep", d["amount"])
        if fee:
            event(uid, "depfee", -fee)   # комиссия за досрочное закрытие — доход банка
        if earned:
            event(uid, "depint", earned)
    _BV["ts"] = 0
    return {"ok": True, "pay": pay, "early": early, "stars": bal(uid), "bank": bank_value()}


# ---------------- публичная сводка банка: без входа, для страницы прозрачности (web/bank.html) ----------------
_PUB = {"at": 0, "v": None}


@app.get(R + "/bank/public")
def bank_public():
    import idletax
    t = time.time()
    if _PUB["v"] and t - _PUB["at"] < 30:
        return _PUB["v"]
    d = day_start()
    d0 = d - 13 * 86400   # 14 дней одним запросом (сутки по UTC, как в house_profit)
    by = {r["day"]: -r["s"] for r in qr(f"SELECT ts/86400*86400 day, SUM(delta) s FROM events WHERE kind IN {GAME_KINDS} AND ts>=? GROUP BY day",
                                         max(d0, bank_from()))}
    days = [{"day": x, "profit": by.get(x, 0)} for x in range(d0, d + 86400, 86400)]
    since = max(bank_from(), now() - 86400)
    g = q1(f"SELECT COUNT(DISTINCT user) n, COALESCE(SUM(CASE WHEN delta>0 THEN delta ELSE 0 END),0) won FROM events WHERE kind IN {GAME_KINDS} AND ts>=? AND user>0", since)
    last = q1("SELECT * FROM div_days WHERE ts>=? ORDER BY day DESC LIMIT 1", bank_from())
    v = {"bank": bank_value(), "start": BANK_START, "today": days[-1]["profit"], "days": days, "players24": g["n"], "won24": g["won"],
         "crisis": {"on": crisis(), "at": CRISIS_AT}, "lvl": level_info(),
         "lastDiv": {"total": last["total"], "profit": last["profit"], "day": last["day"]} if last else None,
         "idletax": idletax.public(), "since": bank_from(), "ts": now(), "bot": A.bot_name()}
    _PUB.update(at=t, v=v)
    return v


def _bv_full():
    """Полная сверка банка с журналом: пересчёт с нуля вместо накопленной суммы. Долгая сумма считается отдельным
    соединением по снимку базы (без общего лока), под лок — только короткая досчётка записей, появившихся за это время."""
    frm = bank_from()
    (m,), (s_,) = qr_snap(("SELECT MAX(rowid) m FROM events", ()),
                          (f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE ({BANK_KINDS}) AND ts>=? AND rowid<=(SELECT MAX(rowid) FROM events)", (frm,)))
    last = m["m"] or 0
    with A.LOCK:
        if bank_from() != frm:
            return
        cur = (q1("SELECT MAX(rowid) m FROM events") or {"m": 0})["m"] or 0
        s_ = s_["s"] + q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE ({BANK_KINDS}) AND ts>=? AND rowid>? AND rowid<=?", frm, last, cur)["s"]
        _BV.update(sum=s_, full=time.time(), last=cur, ts=time.time(), v=BANK_START - s_, **{"from": frm})


async def _bv_loop():
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _bv_full)
        except Exception as e:
            print("bank full recount:", e, flush=True)


def _warm():
    """Прогрев после перезапуска: банк, лучшие и худшие за сезон, таблица сезона — чтобы первый игрок не ждал подсчёта."""
    import seasons
    for f in (bank_value, _tops, seasons._board):
        try:
            f()
        except Exception as e:
            print("bank warm:", e, flush=True)


@app.on_event("startup")
async def _bv_start():
    asyncio.create_task(_bv_loop())
    asyncio.get_running_loop().run_in_executor(None, _warm)
