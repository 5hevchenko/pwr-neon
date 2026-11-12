"""«Живая» игра: лента крупных выигрышей по всем играм, онлайн, «играют сейчас» по играм, реакции на чужие выигрыши.
Крупный выигрыш пишет app.event() (BIGWIN_MIN), здесь — чтение и реакции."""

import time

from fastapi import Depends, Request

from app import R, app, auth, db, err, esc, notify, now, q, q1, tx, user_brief

REACTS = ["🔥", "👏", "😱", "💰"]
NOTIFY_AT = 3          # столько реакций — бот сообщает хозяину выигрыша
NAMES = {"crash": "Краш", "mines": "Мины", "wheel": "Колесо", "duel": "Дуэль", "dice": "Кубик", "limbo": "Лимбо", "plinko": "Плинко",
         "tower": "Башня", "slots": "Слоты", "blackjack": "Блэкджек", "dogs": "Пёсики", "roulette": "Рулетка", "hilo": "Больше/меньше",
         "chicken": "Курица", "avia": "Самолётик", "scratch": "Скретч-карты", "battle": "Битва кейсов", "starfall": "Звездопад",
         "upgrade": "Апгрейд", "jroul": "Джекпот", "cards": "Столы", "craft": "Крафт",
         "claw": "Кран", "pump": "Насос", "drill": "Бур", "darts": "Дартс", "fish": "Рыбалка", "keno": "Кено", "penalty": "Пенальти",
         "safe": "Сейф", "ladder": "Лестница", "carousel": "Карусель", "bankbet": "Ставка на банк", "forecast": "Прогноз дня"}

db.executescript("""
CREATE TABLE IF NOT EXISTS bigwin_reacts(win INTEGER, user INTEGER, emoji TEXT, ts INTEGER, PRIMARY KEY(win, user));
CREATE INDEX IF NOT EXISTS bigwin_reacts_user ON bigwin_reacts(user, win);
""")
TTL = 3                 # лента общая для всех: пересобираем не чаще раза в 3 с, а не на каждый запрос каждого игрока
_FEED = {}              # limit -> (время, данные)
_OK = {}                # id выигрыша -> подтверждён ли записью честности (подтверждённый уже не меняется)


def _verified(w):
    """Выигрыш подкреплён записью: раундом цепочки хэшей или ставкой с зафиксированным сидом.
    Ответ запоминаем: «да» навсегда, «нет» — когда выигрышу больше 2 минут (запись честности к тому времени уже есть)."""
    if w["id"] in _OK:
        return _OK[w["id"]]
    ok = _verified_q(w)
    if ok or now() - w["ts"] > 120:
        if len(_OK) > 5000:
            _OK.clear()
        _OK[w["id"]] = ok
    return ok


def _verified_q(w):
    g = {"roulette": "rlt"}.get(w["kind"], w["kind"])
    if g == "crash":
        return bool(q1("SELECT 1 FROM pf_crash WHERE ts BETWEEN ? AND ?", w["ts"] - 60, w["ts"] + 60))
    return bool(q1("SELECT 1 FROM pf_bets WHERE user=? AND game=? AND ts BETWEEN ? AND ? AND digest<>''", w["user"], g, w["ts"] - 900, w["ts"] + 5))


def _feed(limit):
    """Общая часть ленты (одинакова для всех): выигрыши с игроками, реакциями и проверкой, онлайн, «играют сейчас»."""
    c = _FEED.get(limit)
    if c and time.time() - c[0] < TTL:
        return c[1]
    t = now()
    wins = q("SELECT * FROM bigwins ORDER BY id DESC LIMIT ?", limit)
    ids = [w["id"] for w in wins]
    users = {u["id"]: u for u in q(f"SELECT * FROM users WHERE id IN ({','.join('?' * len(wins)) or 'NULL'})", *[w["user"] for w in wins])}
    rs = {}
    for r in q(f"SELECT win, emoji, COUNT(*) n FROM bigwin_reacts WHERE win IN ({','.join('?' * len(ids)) or 'NULL'}) GROUP BY win, emoji", *ids):
        rs.setdefault(r["win"], {})[r["emoji"]] = r["n"]
    out = []
    for w in wins:
        u = users.get(w["user"])
        if not u:
            continue
        out.append({"id": w["id"], "user": user_brief(u), "kind": w["kind"], "game": NAMES.get(w["kind"], w["kind"]), "amount": w["amount"],
                    "ok": _verified(w), "ts": w["ts"], "reacts": rs.get(w["id"], {})})
    online = q1("SELECT COUNT(*) n FROM users WHERE seen>=?", t - 300)["n"]
    playing = {r["kind"]: r["n"] for r in q("SELECT kind, COUNT(DISTINCT user) n FROM events WHERE ts>=? GROUP BY kind", t - 300)}
    v = {"online": max(1, online), "playing": playing, "wins": out}
    _FEED[limit] = (time.time(), v)
    return v


def _wins(uid, limit):
    f = _feed(limit)
    ids = [w["id"] for w in f["wins"]]
    mine = {r["win"]: r["emoji"] for r in q(f"SELECT win, emoji FROM bigwin_reacts WHERE user=? AND win IN ({','.join('?' * len(ids)) or 'NULL'})", uid, *ids)}
    return [{**w, "mine": mine.get(w["id"])} for w in f["wins"]]


@app.get(R + "/live")
def live(full: int = 0, uid=Depends(auth)):
    limit = 30 if full else 12
    f = _feed(limit)
    return {"online": f["online"], "playing": f["playing"], "wins": _wins(uid, limit), "reactsList": REACTS}


@app.post(R + "/live/{wid}/react")
async def react(wid: int, req: Request, uid=Depends(auth)):
    emoji = str((await req.json()).get("emoji", ""))
    if emoji not in REACTS:
        err("Действие устарело — обнови экран")
    note = None
    with tx():
        w = q1("SELECT * FROM bigwins WHERE id=?", wid) or err("выигрыш не найден")
        if w["user"] == uid:
            err("на свой выигрыш реагировать нельзя")
        db.execute("INSERT INTO bigwin_reacts(win,user,emoji,ts) VALUES(?,?,?,?) ON CONFLICT(win,user) DO UPDATE SET emoji=excluded.emoji",
                   (wid, uid, emoji, now()))
        n = q1("SELECT COUNT(*) n FROM bigwin_reacts WHERE win=?", wid)["n"]
        _FEED.clear()   # своя реакция видна сразу, а не через 3 с
        if n == NOTIFY_AT:
            note = (w["user"], f"Твой выигрыш ⭐ {w['amount']:,} в игре «{esc(NAMES.get(w['kind'], w['kind']))}» оценили уже {n} игрока!".replace(",", " "))
    if note:
        notify(*note)
    return {"ok": True}


def _backfill():
    """Первый запуск: заполняем ленту крупными выигрышами за последние 2 дня из журнала событий."""
    from app import BIG_KINDS, BIGWIN_MIN
    if q1("SELECT 1 FROM bigwins LIMIT 1"):
        return
    ks = "(" + ",".join("'%s'" % k for k in BIG_KINDS) + ")"
    with tx():
        for r in reversed(q(f"SELECT user, kind, delta, ts FROM events WHERE kind IN {ks} AND delta>=? AND ts>=? ORDER BY ts DESC LIMIT 100",
                            BIGWIN_MIN, now() - 2 * 86400)):
            db.execute("INSERT INTO bigwins(user,kind,amount,ts) VALUES(?,?,?,?)", (r["user"], r["kind"], r["delta"], r["ts"]))


_backfill()
