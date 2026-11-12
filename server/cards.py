"""Карточные игры: блэкджек против дилера, «21» и «101» за столом с друзьями."""
import asyncio
import json
import random

from fastapi import Depends, Request

from app import R, app, auth, bal, check_bet, db, err, esc, event, notify, now, q, q1, tx, user_brief, add_xp
from app import APP_URL as A_APP, bot_name
from app import unpin as A_unpin, cancel_trades_with as A_cancel, gift_out as A_gift_out

# ============================== колоды ==============================
SUITS = "SHDC"


def _shuffle(x, ref):
    """Перемешивание из общего сида дня (fair.py): колоду можно пересчитать, когда сид раскроется."""
    import fair
    rng = fair.pub("cards", ref)
    rng.shuffle(x)
    fair.close_pub(rng)


def deck52():
    d = [r + s for r in "23456789TJQKA" for s in SUITS]
    _shuffle(d, "deck52")
    return d


def deck36():
    d = [r + s for r in "6789TJQKA" for s in SUITS]
    _shuffle(d, "deck36")
    return d


def bj_value(cards):
    v, aces = 0, 0
    for c in cards:
        r = c[0]
        if r == "A":
            v, aces = v + 11, aces + 1
        elif r in "TJQK":
            v += 10
        else:
            v += int(r)
    while v > 21 and aces:
        v, aces = v - 10, aces - 1
    return v


# ============================== блэкджек против дилера ==============================
db.executescript("CREATE TABLE IF NOT EXISTS bj(user INTEGER PRIMARY KEY, bet INTEGER, deck TEXT, p TEXT, d TEXT, ts INTEGER);")


def _bj_view(r, final=False, extra=None):
    p, d = json.loads(r["p"]), json.loads(r["d"])
    out = {"active": not final, "bet": r["bet"], "player": p, "pv": bj_value(p),
           "dealer": d if final else [d[0], "??"], "dv": bj_value(d) if final else bj_value([d[0]])}
    return {**out, **(extra or {})}


def _bj_finish(uid, r, deck, p, d):
    """Дилер добирает до 17, считаем исход и выплату."""
    pv = bj_value(p)
    if pv <= 21:
        while bj_value(d) < 17:
            d.append(deck.pop())
    dv = bj_value(d)
    bj_p, bj_d = len(p) == 2 and pv == 21, len(d) == 2 and dv == 21
    bet = r["bet"]
    if pv > 21:
        res, pay = "bust", 0
    elif bj_p and not bj_d:
        res, pay = "blackjack", int(bet * 2.5)
    elif bj_d and not bj_p:
        res, pay = "lose", 0
    elif dv > 21 or pv > dv:
        res, pay = "win", bet * 2
    elif pv == dv:
        res, pay = "push", bet
    else:
        res, pay = "lose", 0
    db.execute("DELETE FROM bj WHERE user=?", (uid,))
    db.execute("UPDATE users SET stars=stars+? WHERE id=?", (pay, uid))
    event(uid, "blackjack", pay - bet, stake=bet)
    view = {"p": json.dumps(p), "d": json.dumps(d), "bet": bet}
    return _bj_view(view, True, {"result": res, "pay": pay, "stars": bal(uid)})


@app.get(R + "/bj")
def bj_get(uid=Depends(auth)):
    r = q1("SELECT * FROM bj WHERE user=?", uid)
    return _bj_view(r) if r else {"active": False}


@app.post(R + "/bj/start")
async def bj_start(req: Request, uid=Depends(auth)):
    bet = int((await req.json()).get("bet", 0))
    with tx():
        if q1("SELECT 1 FROM bj WHERE user=?", uid):
            err("раздача уже идёт")
        check_bet(uid, bet)
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (bet, uid))
        deck = deck52()
        p, d = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]
        db.execute("INSERT INTO bj VALUES(?,?,?,?,?,?)", (uid, bet, json.dumps(deck), json.dumps(p), json.dumps(d), now()))
        lvl = add_xp(uid, max(1, bet // 20))
        r = q1("SELECT * FROM bj WHERE user=?", uid)
        if bj_value(p) == 21 or bj_value(d) == 21:     # блэкджек на раздаче — сразу итог
            return {**_bj_finish(uid, r, deck, p, d), "levelup": lvl}
        return {**_bj_view(r), "stars": bal(uid), "levelup": lvl}


@app.post(R + "/bj/{action}")
def bj_action(action: str, uid=Depends(auth)):
    with tx():
        r = q1("SELECT * FROM bj WHERE user=?", uid) or err("раздача не начата")
        deck, p, d = json.loads(r["deck"]), json.loads(r["p"]), json.loads(r["d"])
        if action == "hit":
            p.append(deck.pop())
            if bj_value(p) >= 21:
                return _bj_finish(uid, r, deck, p, d)
            db.execute("UPDATE bj SET deck=?, p=? WHERE user=?", (json.dumps(deck), json.dumps(p), uid))
            return _bj_view(q1("SELECT * FROM bj WHERE user=?", uid))
        if action == "stand":
            return _bj_finish(uid, r, deck, p, d)
        if action == "double":
            if len(p) != 2:
                err("удвоить можно только на первых двух картах")
            if bal(uid) < r["bet"]:
                err("Не хватает звёзд")
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (r["bet"], uid))
            db.execute("UPDATE bj SET bet=bet*2 WHERE user=?", (uid,))
            p.append(deck.pop())
            return _bj_finish(uid, q1("SELECT * FROM bj WHERE user=?", uid), deck, p, d)
        err("Действие устарело — обнови экран")


# ============================== столы с друзьями: «21» и «101» ==============================
db.executescript("""
CREATE TABLE IF NOT EXISTS rooms(id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, host INTEGER, stake INTEGER, maxp INTEGER,
  public INTEGER, status TEXT, players TEXT, invited TEXT, state TEXT, result TEXT, ts INTEGER, upd INTEGER);
CREATE INDEX IF NOT EXISTS rooms_status ON rooms(status);
""")
for _col in ("kind TEXT DEFAULT 'stars'", "escrow TEXT DEFAULT '{}'"):
    try:
        db.execute("ALTER TABLE rooms ADD COLUMN " + _col)
    except Exception:
        pass   # колонка уже есть
GIFT_MIN = 0.8   # на подарочный стол садятся с подарками не дешевле 80% ставки хозяина
ROOM_FEE = 0.05
TURN_SEC = 45
WAIT_TTL = 3600
GAMES = {"21": "Двадцать одно", "101": "101"}


def _room(rid):
    r = q1("SELECT * FROM rooms WHERE id=?", rid) or err("стол не найден", 404)
    return {**dict(r), "players": json.loads(r["players"]), "invited": json.loads(r["invited"] or "[]"),
            "state": json.loads(r["state"] or "{}"), "result": json.loads(r["result"] or "null"),
            "escrow": json.loads(r["escrow"] or "{}"), "kind": r["kind"] or "stars"}


def _save(r):
    db.execute("UPDATE rooms SET status=?, players=?, invited=?, state=?, result=?, escrow=?, upd=? WHERE id=?",
               (r["status"], json.dumps(r["players"]), json.dumps(r["invited"]), json.dumps(r["state"]),
                json.dumps(r["result"]), json.dumps(r["escrow"]), now(), r["id"]))


# ---------- подарки в банке стола: замораживаем (owner = -id стола), возвращаем, отдаём победителю ----------
def _esc_value(r, uid=None):
    ids = [g for u, gs in r["escrow"].items() if uid is None or u == str(uid) for g in gs]
    if not ids:
        return 0
    return q1(f"SELECT COALESCE(SUM(value),0) v FROM gifts WHERE id IN ({','.join('?' * len(ids))})", *ids)["v"]


def _esc_put(r, uid, gids):
    gids = list(dict.fromkeys(int(g) for g in gids))[:10]
    if not gids:
        err("выбери подарки для ставки")
    for g in gids:
        x = q1("SELECT owner, price FROM gifts WHERE id=?", g)
        if not x or x["owner"] != uid:
            err("это не твой подарок")
        if x["price"] is not None:
            err("сначала сними подарок с маркета")
    for g in gids:
        db.execute("UPDATE gifts SET owner=? WHERE id=?", (-r["id"], g))
        A_unpin(uid, g)
        A_cancel(g)
    r["escrow"][str(uid)] = gids


def _esc_return(r, uid):
    for g in r["escrow"].pop(str(uid), []):
        db.execute("UPDATE gifts SET owner=? WHERE id=? AND owner=?", (uid, g, -r["id"]))


def _refund(r, u):
    if r["kind"] == "gifts":
        _esc_return(r, u)
    else:
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (r["stake"], u))


def _pot(r):
    if r["kind"] == "gifts":
        return _esc_value(r)
    return int(r["stake"] * len(r["state"].get("all", r["players"])) * (1 - ROOM_FEE))


def _finish(r, winners):
    """Раздать банк победителям (ничья — делят), записать события, уведомить."""
    allp = r["state"].get("all", r["players"])
    pot = _pot(r)
    share = pot // max(1, len(winners))
    if r["kind"] == "gifts":
        # все подарки банка — победителям; при ничьей раздаём по очереди, начиная с дорогих
        gifts = q("SELECT id, value FROM gifts WHERE owner=? ORDER BY value DESC", -r["id"])
        staked = {u: _esc_value(r, u) for u in allp}
        got = {u: 0 for u in winners}
        for g in gifts:
            w = min(winners, key=lambda u: got[u])
            db.execute("UPDATE gifts SET owner=? WHERE id=?", (w, g["id"]))
            got[w] += g["value"]
        for u in allp:
            event(u, "cards", got.get(u, 0) - staked[u], stake=staked[u])
        r["result"] = {"winners": winners, "share": share, "pot": pot, "gifts": [g["id"] for g in gifts]}
        r["escrow"] = {}
        r["status"] = "done"
        _save(r)
        return
    for u in allp:
        got = share if u in winners else 0
        if got:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (got, u))
        event(u, "cards", got - r["stake"], stake=r["stake"])
    r["status"] = "done"
    r["result"] = {"winners": winners, "share": share, "pot": pot}
    _save(r)


# ---------- «21»: все тянут по очереди, ближе к 21 без перебора — забирает банк ----------
def _21_start(r):
    deck = deck52()
    st = {"deck": deck, "hands": {}, "done": {}, "turn": 0, "all": list(r["players"]), "deadline": now() + TURN_SEC}
    for u in r["players"]:
        st["hands"][str(u)] = [deck.pop(), deck.pop()]
        st["done"][str(u)] = bj_value(st["hands"][str(u)]) >= 21
    r["state"] = st
    _21_advance(r, first=True)


def _21_advance(r, first=False):
    st, ps = r["state"], r["players"]
    n = len(ps)
    start = st["turn"] if first else st["turn"] + 1
    for k in range(n):
        i = (start + k) % n
        if not st["done"][str(ps[i])]:
            st["turn"], st["deadline"] = i, now() + TURN_SEC
            return
    # все закончили — итог
    best, winners = -1, []
    for u in ps:
        v = bj_value(st["hands"][str(u)])
        if v <= 21 and v > best:
            best, winners = v, [u]
        elif v <= 21 and v == best:
            winners.append(u)
    _finish(r, winners or list(ps))   # все перебрали — банк возвращается всем поровну


def _21_act(r, uid, a):
    st = r["state"]
    if a == "hit":
        h = st["hands"][str(uid)]
        h.append(st["deck"].pop())
        if bj_value(h) >= 21:
            st["done"][str(uid)] = True
            _21_advance(r)
        else:
            st["deadline"] = now() + TURN_SEC
    elif a == "stand":
        st["done"][str(uid)] = True
        _21_advance(r)
    else:
        err("Действие устарело — обнови экран")


# ---------- «101»: скинь все карты первым ----------
def _101_start(r):
    deck = deck36()
    st = {"deck": deck, "hands": {}, "pile": [], "turn": 0, "dir": 1, "all": list(r["players"]),
          "suit": None, "drew": False, "must": False, "log": [], "deadline": now() + TURN_SEC}
    for u in r["players"]:
        st["hands"][str(u)] = [deck.pop() for _ in range(5)]
    top = deck.pop()
    st["pile"], st["suit"] = [top], top[1]
    r["state"] = st


def _101_can(st, c):
    top = st["pile"][-1]
    if st["must"]:   # шестёрку нужно покрыть: масть шестёрки, другая шестёрка или дама
        return c[1] == st["suit"] or c[0] in "6Q"
    return c[0] == "Q" or c[1] == st["suit"] or c[0] == top[0]


def _101_draw(st, n=1):
    got = []
    for _ in range(n):
        if not st["deck"]:
            if len(st["pile"]) <= 1:
                break
            top = st["pile"][-1]
            st["deck"] = st["pile"][:-1]
            _shuffle(st["deck"], "reshuffle")
            st["pile"] = [top]
        got.append(st["deck"].pop())
    return got


def _101_next(r, skip=0):
    st, n = r["state"], len(r["players"])
    st["turn"] = (st["turn"] + st["dir"] * (1 + skip)) % n
    st["drew"], st["deadline"] = False, now() + TURN_SEC


def _101_log(st, txt):
    st["log"] = (st["log"] + [txt])[-6:]


def _101_act(r, uid, a, card=None, suit=None):
    st, ps = r["state"], r["players"]
    hand = st["hands"][str(uid)]
    name = q1("SELECT name FROM users WHERE id=?", uid)["name"]
    if a == "play":
        if card not in hand:
            err("нет такой карты")
        if not _101_can(st, card):
            err("эту карту сюда нельзя")
        hand.remove(card)
        st["pile"].append(card)
        st["must"] = False
        rank = card[0]
        st["suit"] = card[1]
        if rank == "Q":
            st["suit"] = suit if suit in SUITS else card[1]
        _101_log(st, f"{name}: {card}" + (f" → {st['suit']}" if rank == "Q" else ""))
        if not hand:
            return _finish(r, [uid])
        nxt = ps[(st["turn"] + st["dir"]) % len(ps)]
        if rank == "6":
            st["must"], st["drew"] = True, False      # шестёрку кроет тот же игрок
            st["deadline"] = now() + TURN_SEC
        elif rank == "7":
            st["hands"][str(nxt)] += _101_draw(st, 1)
            _101_next(r, skip=1)
        elif rank == "8":
            st["hands"][str(nxt)] += _101_draw(st, 2)
            _101_next(r, skip=1)
        elif rank == "K" and card[1] == "S":
            st["hands"][str(nxt)] += _101_draw(st, 4)
            _101_next(r, skip=1)
        elif rank == "A":
            _101_next(r, skip=1)
        else:
            _101_next(r)
    elif a == "draw":
        if st["drew"] and not st["must"]:
            err("уже взял карту — ходи или пасуй")
        got = _101_draw(st, 1)
        hand += got
        st["drew"] = True
        st["deadline"] = now() + TURN_SEC
        if not got and st["must"]:   # брать нечего — шестёрку покрыть нельзя, разрешаем пас
            st["must"] = False
            _101_log(st, f"{name}: колода пуста, пас")
            _101_next(r)
    elif a == "pass":
        if st["must"]:
            err("шестёрку нужно покрыть — бери карты, пока не покроешь")
        if not st["drew"]:
            err("сначала возьми карту")
        _101_next(r)
    else:
        err("Действие устарело — обнови экран")


def _auto(r):
    """Ход по таймауту: в 21 — «хватит», в 101 — взять и пасовать."""
    if r["status"] != "playing" or now() < r["state"].get("deadline", 1e18):
        return False
    uid = r["players"][r["state"]["turn"]]
    if r["game"] == "21":
        _21_act(r, uid, "stand")
    else:
        st = r["state"]
        for _ in range(12):   # «шестёрку» добираем, пока не покроем
            hand = st["hands"][str(uid)]
            playable = [c for c in hand if _101_can(st, c)]
            if playable:
                _101_act(r, uid, "play", playable[0], playable[0][1])
                break
            _101_act(r, uid, "draw")
            if not st["must"]:
                if not [c for c in st["hands"][str(uid)] if _101_can(st, c)]:
                    _101_act(r, uid, "pass")
                    break
    if r["status"] != "done":
        _save(r)
    return True


def _expire():
    for x in q("SELECT id FROM rooms WHERE status='waiting' AND ts<?", now() - WAIT_TTL):
        with tx():
            r = _room(x["id"])
            if r["status"] == "waiting":
                for u in r["players"]:
                    _refund(r, u)
                r["status"] = "cancelled"
                _save(r)


def _sweep_turns():
    """Доигрываем просроченные ходы в фоне: иначе стол, который все закрыли, зависает навсегда вместе со ставками.
    Заодно возвращаем ставки по просроченным вызовам на дуэль."""
    from app import duel_expire
    from games4 import cd_finish
    duel_expire()
    for x in q("SELECT id FROM duels WHERE status='live'"):   # краш-дуэли, которые бросили: подводим итог/возвращаем ставки
        with tx():
            d = q1("SELECT * FROM duels WHERE id=?", x["id"])
            if d and d["status"] == "live":
                cd_finish(d)
    _expire()
    for x in q("SELECT id FROM rooms WHERE status='playing'"):
        with tx():
            r = _room(x["id"])
            for _ in range(40):   # каждый вызов — один ход; за раз доигрываем до конца или до живого дедлайна
                if not _auto(r) or r["status"] == "done":
                    break


async def rooms_loop():
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _sweep_turns)
        except Exception as e:
            print("rooms:", e, flush=True)
        await asyncio.sleep(30)


@app.on_event("startup")
async def _rooms_start():
    asyncio.create_task(rooms_loop())


SEEN = {}        # (стол, игрок) -> когда последний раз смотрел стол
PINGED = {}      # (стол, игрок) -> номер хода, о котором уже напомнили


def _ping_turn(r):
    """Напомнить ботом о ходе тому, кто не смотрит на стол дольше 15 секунд (один раз за ход)."""
    if r["status"] != "playing":
        return
    u = r["players"][r["state"]["turn"]]
    mark = (len(r["state"].get("log", [])), r["state"].get("deadline"))
    if now() - SEEN.get((r["id"], u), 0) > 15 and PINGED.get((r["id"], u)) != mark:
        PINGED[(r["id"], u)] = mark
        notify(u, f"🃏 Твой ход в «{GAMES[r['game']]}» — на ход {TURN_SEC} секунд", url=A_APP + "?room=" + str(r["id"]))


def _view(r, uid):
    st, ps = r["state"], r["players"]
    users = {u: user_brief(q1("SELECT * FROM users WHERE id=?", u)) for u in set(ps + st.get("all", []))}
    done = r["status"] == "done"
    out = {"id": r["id"], "game": r["game"], "title": GAMES[r["game"]], "stake": r["stake"], "kind": r["kind"], "maxp": r["maxp"], "public": bool(r["public"]),
           "status": r["status"], "host": r["host"], "me": uid, "pot": _pot(r) if r["status"] != "waiting" else int(r["stake"] * len(ps) * (1 - ROOM_FEE)),
           "players": [], "result": r["result"], "turn": None, "deadline": st.get("deadline"), "now": now(),
           "link": f"https://t.me/{bot_name()}?start=room_{r['id']}"}
    if r["kind"] == "gifts":
        ids = [g for gs in r["escrow"].values() for g in gs] or (r["result"] or {}).get("gifts", [])
        rows = [q1("SELECT * FROM gifts WHERE id=?", g) for g in ids]
        out["potGifts"] = [A_gift_out(x) for x in rows if x]
        out["pot"] = sum(g["value"] for g in out["potGifts"])
    for i, u in enumerate(st.get("all", ps)):
        p = {**users[u], "left": u not in ps}
        if r["kind"] == "gifts":
            p["staked"] = _esc_value(r, u)
        if r["status"] in ("playing", "done") and st.get("hands"):
            h = st["hands"].get(str(u), [])
            if r["game"] == "21":
                show = done or u == uid
                p.update(cards=h if show else [h[0]] + ["??"] * (len(h) - 1), value=bj_value(h) if show else None,
                         done=st["done"].get(str(u)))
            else:
                p.update(count=len(h))
        out["players"].append(p)
    if r["status"] == "playing":
        out["turn"] = ps[st["turn"]]
        if r["game"] == "101":
            out.update(hand=st["hands"][str(uid)] if str(uid) in st["hands"] else [], top=st["pile"][-1], suit=st["suit"],
                       must=st["must"], drew=st["drew"], deck=len(st["deck"]), log=st["log"],
                       playable=[c for c in st["hands"].get(str(uid), []) if _101_can(st, c)] if out["turn"] == uid else [])
    if done and r["game"] == "101":
        out.update(top=st["pile"][-1], suit=st["suit"], log=st["log"])
    return out


def _short(r):
    host = q1("SELECT * FROM users WHERE id=?", r["host"])
    ps = json.loads(r["players"])
    return {"id": r["id"], "game": r["game"], "title": GAMES[r["game"]], "stake": r["stake"], "maxp": r["maxp"], "kind": r["kind"] or "stars",
            "count": len(ps), "status": r["status"], "host": user_brief(host), "public": bool(r["public"])}


@app.get(R + "/rooms")
def rooms(uid=Depends(auth)):
    _expire()
    mine, open_, invites = [], [], []
    for r in q("SELECT * FROM rooms WHERE status IN ('waiting','playing') ORDER BY id DESC LIMIT 200"):
        ps, inv = json.loads(r["players"]), json.loads(r["invited"] or "[]")
        if uid in ps:
            mine.append(_short(r))
        elif r["status"] == "waiting" and len(ps) < r["maxp"]:
            if uid in inv:
                invites.append(_short(r))
            elif r["public"]:
                open_.append(_short(r))
    return {"mine": mine, "invites": invites, "open": open_[:30]}


@app.post(R + "/rooms")
async def room_new(req: Request, uid=Depends(auth)):
    from app import _pvp_guard
    _pvp_guard(uid)
    b = await req.json()
    game, stake = str(b.get("game", "21")), int(b.get("stake", 0))
    maxp, public = max(2, min(4, int(b.get("maxp", 2)))), bool(b.get("public", True))
    invite = [int(x) for x in b.get("invite", [])][:3]
    kind = "gifts" if b.get("kind") == "gifts" else "stars"
    if game not in GAMES:
        err("нет такой игры")
    with tx():
        if q1("SELECT COUNT(*) n FROM rooms WHERE status IN ('waiting','playing') AND host=?", uid)["n"] >= 3:
            err("не больше 3 столов одновременно")
        if kind == "stars":
            check_bet(uid, stake, 10, 1_000_000)
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (stake, uid))
        cur = db.execute("INSERT INTO rooms(game,host,stake,maxp,public,status,players,invited,state,ts,upd,kind,escrow) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (game, uid, stake if kind == "stars" else 0, maxp, int(public), "waiting", json.dumps([uid]),
                          json.dumps(invite), "{}", now(), now(), kind, "{}"))
        if kind == "gifts":
            r = _room(cur.lastrowid)
            _esc_put(r, uid, b.get("gifts", []))
            r["stake"] = stake = _esc_value(r, uid)
            db.execute("UPDATE rooms SET stake=? WHERE id=?", (stake, r["id"]))
            _save(r)
        name = q1("SELECT name FROM users WHERE id=?", uid)["name"]
    for u in invite:
        notify(u, f"🃏 <b>{esc(name)}</b> зовёт тебя за стол «{GAMES[game]}» — " + ("ставка подарками на ~" if kind == "gifts" else "ставка ") + f"{stake} ⭐",
               url=A_APP + "?room=" + str(cur.lastrowid))
    return {"id": cur.lastrowid, "stars": bal(uid)}


@app.get(R + "/rooms/{rid}")
def room_get(rid: int, uid=Depends(auth)):
    SEEN[(rid, uid)] = now()
    with tx():
        r = _room(rid)
        moved = _auto(r)
        r = _room(rid)
    if moved:
        _ping_turn(r)
    return _view(r, uid)


@app.post(R + "/rooms/{rid}/{action}")
async def room_action(rid: int, action: str, req: Request, uid=Depends(auth)):
    if action == "join":
        from app import _pvp_guard
        _pvp_guard(uid)
    b = {}
    try:
        b = await req.json()
    except Exception:
        pass
    notify_list = []
    with tx():
        r = _room(rid)
        if action == "join":
            if r["status"] != "waiting":
                err("игра уже началась")
            if uid in r["players"]:
                return _view(r, uid)
            if len(r["players"]) >= r["maxp"]:
                err("стол заполнен")
            if not r["public"] and uid not in r["invited"]:
                err("стол закрытый — нужно приглашение")
            if r["kind"] == "gifts":
                _esc_put(r, uid, b.get("gifts", []))
                if _esc_value(r, uid) < GIFT_MIN * r["stake"]:
                    err(f"нужны подарки минимум на {int(GIFT_MIN * r['stake'])} ⭐ ценности")
            else:
                check_bet(uid, r["stake"], 1, 10 ** 9)
                db.execute("UPDATE users SET stars=stars-? WHERE id=?", (r["stake"], uid))
            r["players"].append(uid)
            _save(r)
            notify_list.append((r["host"], "🃏 К твоему столу «%s» присоединился игрок" % GAMES[r["game"]]))
        elif action == "leave":
            if uid not in r["players"]:
                err("тебя нет за столом")
            if r["status"] == "waiting":
                _refund(r, uid)
                r["players"].remove(uid)
                if not r["players"]:
                    r["status"] = "cancelled"
                elif r["host"] == uid:
                    r["host"] = r["players"][0]
                    db.execute("UPDATE rooms SET host=? WHERE id=?", (r["host"], rid))
                _save(r)
            elif r["status"] == "playing":   # вышел посреди игры — ставка остаётся в банке
                st, ps = r["state"], r["players"]
                idx, cur = ps.index(uid), ps[st["turn"]]
                ps.remove(uid)
                if r["game"] == "21":
                    st["done"][str(uid)] = True
                if len(ps) == 1:
                    _finish(r, ps[:])
                elif cur != uid:
                    st["turn"] = ps.index(cur)
                    _save(r)
                elif r["game"] == "21":
                    st["turn"] = (idx - 1) % len(ps)
                    _21_advance(r)
                    if r["status"] != "done":
                        _save(r)
                else:
                    st["turn"] = idx % len(ps)
                    st["drew"], st["must"], st["deadline"] = False, False, now() + TURN_SEC
                    _save(r)
        elif action == "start":
            if r["host"] != uid:
                err("начать может только хозяин стола")
            if r["status"] != "waiting":
                err("уже идёт")
            if len(r["players"]) < 2:
                err("нужно минимум 2 игрока")
            r["status"] = "playing"
            _shuffle(r["players"], "seats")
            (_21_start if r["game"] == "21" else _101_start)(r)
            if r["status"] != "done":
                _save(r)
            for u in r["players"]:
                if u != uid:
                    notify_list.append((u, f"🃏 Игра «{GAMES[r['game']]}» началась — заходи, твой ход может быть следующим"))
        elif action == "cancel":
            if r["host"] != uid or r["status"] != "waiting":
                err("отменить может только хозяин до начала игры")
            for u in r["players"]:
                _refund(r, u)
            r["status"] = "cancelled"
            _save(r)
        elif action == "invite":
            to = int(b.get("to", 0))
            if uid not in r["players"] or r["status"] != "waiting":
                err("звать можно только до начала игры")
            if to not in r["invited"]:
                r["invited"].append(to)
                _save(r)
            name = q1("SELECT name FROM users WHERE id=?", uid)["name"]
            notify_list.append((to, f"🃏 <b>{esc(name)}</b> зовёт тебя за стол «{GAMES[r['game']]}» — ставка {r['stake']} ⭐", A_APP + "?room=" + str(rid)))
        elif action == "act":
            if r["status"] != "playing":
                err("игра не идёт")
            if r["players"][r["state"]["turn"]] != uid:
                err("сейчас не твой ход")
            if r["game"] == "21":
                _21_act(r, uid, b.get("a"))
            else:
                _101_act(r, uid, b.get("a"), b.get("card"), b.get("suit"))
            if r["status"] != "done":
                _save(r)
        else:
            err("Действие устарело — обнови экран")
        r = _room(rid)
    SEEN[(rid, uid)] = now()
    for n in notify_list:
        notify(*n)
    if action in ("act", "start", "leave"):
        _ping_turn(r)
    return {**_view(r, uid), "stars": bal(uid), "link": f"https://t.me/{bot_name()}?start=room_{rid}"}
