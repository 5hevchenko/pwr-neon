"""«Кран» — автомат с клешнёй. В автомате несколько подарков, у каждого свой множитель ставки.
Игрок выбирает подарок и опускает клешню: удержит — выплата ставка × множитель, сорвётся — ставка сгорает.
Шанс удержать = RTP / множитель (не выше CAP), поэтому любая цель честно отдаёт RTP (меняется во вкладке «Шансы»).
Состав автомата генерирует сервер и хранит до следующего хода — подменить множитель с клиента нельзя.
Настройки автомата (набор множителей, сколько призов, лимиты ставки) — в админке, вкладка «Кран» (kv 'claw')."""
import json
import random

from fastapi import Depends, Request

import economy as E
from app import R, add_xp, app, auth, bal, check_bet, db, edge, err, event, kv_get, now, preview_out, q, q1, tx
from settings import conf, tuned

db.executescript("""
CREATE TABLE IF NOT EXISTS claw(user INTEGER PRIMARY KEY, lineup TEXT, ts INTEGER);
""")
RTP = conf("games.claw_rtp", 0.95)
CAP = 0.95            # даже самый дешёвый приз клешня держит не всегда — иначе неинтересно
DEFAULTS = {"mults": [1.2, 1.5, 2, 3, 5, 10, 25, 50, 100], "size": 6, "min_bet": 10, "max_bet": 100000, "jackpot": 0.35}
# collections для «пушистых» призов в автомате — плюшевое и милое, как в настоящем кране
PRIZE_COLS = ["Toy Bear", "Jelly Bunny", "Plush Pepe", "Bunny Muffin", "Scared Cat", "Kissed Frog", "Lol Pop", "Jester Hat",
              "Homemade Cake", "Snoop Dogg", "Santa Hat", "Witch Hat", "Ginger Cookie", "Big Year", "Pet Snake", "Jack-in-the-Box"]


def cfg():
    """Настройки автомата: kv 'claw' из админки поверх значений по умолчанию."""
    try:
        v = json.loads(kv_get("claw", "{}") or "{}")
    except Exception:
        v = {}
    c = {**DEFAULTS, **{k: v[k] for k in DEFAULTS if k in v}}
    c["mults"] = sorted({round(float(x), 2) for x in c["mults"] if 1.05 <= float(x) <= 1000}) or DEFAULTS["mults"]
    c["size"] = max(3, min(8, int(c["size"])))
    return c


def rtp():
    return edge(tuned("games.claw_rtp", RTP))


def chance(m):
    return min(CAP, rtp() / m)


def _prize(col):
    col = col if col in E.CATALOG else random.choice(list(E.CATALOG))
    return preview_out(col, E.roll(col))


def new_lineup():
    """Состав автомата: size призов. Крупные (x10+) редкие — один, иногда (jackpot) — самый большой множитель."""
    c = cfg()
    ms = c["mults"]
    small = [m for m in ms if m < 10] or ms
    big = [m for m in ms if m >= 10]
    picks = random.sample(small, min(len(small), c["size"] - (1 if big else 0)))
    while len(picks) < c["size"] - (1 if big else 0):
        picks.append(random.choice(small))
    if big:
        picks.append(max(big) if random.random() < c["jackpot"] else random.choice(big))
    random.shuffle(picks)
    cols = random.sample(PRIZE_COLS, len(picks))
    return [{"m": m, "gift": _prize(col)} for m, col in zip(picks, cols)]


def _view(lineup):
    c = cfg()
    return {"lineup": [{**x, "p": round(chance(x["m"]) * 100, 1)} for x in lineup], "rtp": round(rtp() * 100, 1),
            "minBet": c["min_bet"], "maxBet": c["max_bet"]}


def _get(uid, fresh=False):
    r = q1("SELECT lineup FROM claw WHERE user=?", uid)
    if r and not fresh:
        return json.loads(r["lineup"])
    lineup = new_lineup()
    db.execute("INSERT INTO claw(user,lineup,ts) VALUES(?,?,?) ON CONFLICT(user) DO UPDATE SET lineup=excluded.lineup, ts=excluded.ts",
               (uid, json.dumps(lineup), now()))
    return lineup


@app.get(R + "/claw")
def claw(uid=Depends(auth)):
    with tx():
        lineup = _get(uid)
    return {**_view(lineup), "stars": bal(uid)}


@app.post(R + "/claw/play")
async def claw_play(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, idx = int(b.get("bet", 0)), int(b.get("idx", -1))
    c = cfg()
    with tx():
        lineup = _get(uid)
        if not 0 <= idx < len(lineup):
            err("выбери подарок")
        check_bet(uid, bet, c["min_bet"], c["max_bet"])
        m = lineup[idx]["m"]
        p = chance(m)
        import fair
        rr, pf = fair.rolls(uid, "claw", ref=str(m))
        win = rr[0] < p
        pay = int(bet * m) if win else 0
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
        event(uid, "claw", pay - bet, stake=bet, pf=pf, res={"p": round(p, 6), "win": win})
        lvl = add_xp(uid, max(1, bet // 20))
        # клешня «срывается» на разной высоте — для анимации (0 — сразу, 1 — у самого лотка)
        slip = None if win else round(random.uniform(.15, .9), 2)
        nxt = _get(uid, fresh=True)
    return {"win": win, "pay": pay, "m": m, "idx": idx, "slip": slip, "stars": bal(uid), "levelup": lvl, "pf": pf, **_view(nxt)}


@app.post(R + "/claw/shuffle")
def claw_shuffle(uid=Depends(auth)):
    """Перемешать автомат — бесплатно, но не чаще раза в 2 секунды (чтобы не «ловить» состав)."""
    with tx():
        r = q1("SELECT ts FROM claw WHERE user=?", uid)
        if r and now() - r["ts"] < 2:
            err("подожди секунду")
        lineup = _get(uid, fresh=True)
    return _view(lineup)


# ---------------- админка: вкладка «Кран» ----------------
def _admin_routes():
    from admin import OWNERS, admin, log

    @app.get(R + "/admin/claw")
    def adm_claw(aid=Depends(admin)):
        since = now() - 7 * 86400
        st = q1("SELECT COUNT(*) n, COALESCE(-SUM(delta),0) house, COUNT(DISTINCT user) players FROM events WHERE kind='claw' AND ts>=?", since)
        best = q1("SELECT user, MAX(delta) d FROM events WHERE kind='claw' AND ts>=?", since)
        top = None
        if best and best["d"] and best["d"] > 0:
            u = q1("SELECT name FROM users WHERE id=?", best["user"])
            top = {"name": u["name"] if u else str(best["user"]), "win": best["d"]}
        days = [{"day": d0, "house": -(q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind='claw' AND ts>=? AND ts<?", d0, d0 + 86400)["s"])}
                for d0 in [(now() // 86400 - i) * 86400 for i in range(6, -1, -1)]]
        c = cfg()
        return {"cfg": c, "defaults": DEFAULTS, "rtp": round(rtp() * 100, 1), "cap": CAP,
                "odds": [{"m": m, "p": round(chance(m) * 100, 1)} for m in c["mults"]],
                "stats": {"rounds": st["n"], "house": st["house"], "players": st["players"], "best": top, "days": days},
                "canEdit": aid in OWNERS}

    @app.post(R + "/admin/claw")
    async def adm_claw_set(req: Request, aid=Depends(admin)):
        from app import err as _err
        if aid not in OWNERS:
            _err("менять автомат может только владелец")
        b = await req.json()
        if b.get("reset"):
            new = {}
        else:
            try:
                mults = sorted({round(float(x), 2) for x in b.get("mults", [])})
                new = {"mults": mults, "size": int(b.get("size", 6)), "min_bet": int(b.get("min_bet", 10)),
                       "max_bet": int(b.get("max_bet", 100000)), "jackpot": float(b.get("jackpot", .35))}
            except (TypeError, ValueError):
                _err("проверь числа")
            if not 3 <= len(new["mults"]) <= 20 or min(new["mults"]) < 1.05 or max(new["mults"]) > 1000:
                _err("множителей от 3 до 20, каждый от 1,05 до 1000 (меньше — приз дешевле ставки)")
            if not 3 <= new["size"] <= 8:
                _err("призов в автомате — от 3 до 8")
            if not 1 <= new["min_bet"] <= new["max_bet"] <= conf("games.max_bet", 1000000):
                _err("неверные лимиты ставки")
            if not 0 <= new["jackpot"] <= 1:
                _err("шанс главного приза — от 0 до 100%")
        with tx():
            db.execute("INSERT INTO kv(k,v) VALUES('claw',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(new),))
            db.execute("DELETE FROM claw")   # у всех пересобрать автомат по новым правилам
            log(aid, "claw", None, "сброс" if not new else f"x{new['mults'][0]}–x{new['mults'][-1]}, призов {new['size']}, ставка {new['min_bet']}–{new['max_bet']}")
        return {"ok": True, "cfg": cfg()}


_admin_routes()
