"""Личные рекорды: самый большой выигрыш, самый большой икс и самый дорогой подарок из кейса.
Первое значение запоминаем молча, праздник — только когда игрок побил уже заметный рекорд.
О новом рекорде клиент узнаёт по заголовку X-Rec у любого ответа API и забирает его через /records/new."""
from fastapi import Depends

import app as A
from app import R, app, auth, db, now, q, q1

MIN = {"win": 2_000, "x": 5.0, "gift": 2_000}   # меньше — рекорд пишем, но не празднуем
X_MIN_STAKE = 100                                # икс на копеечной ставке рекордом не считаем
TITLES = {"win": "Самый большой выигрыш", "x": "Самый большой икс", "gift": "Самый дорогой подарок"}

db.executescript("""
CREATE TABLE IF NOT EXISTS records(user INTEGER, kind TEXT, value REAL, ref TEXT, pay INTEGER DEFAULT 0, ts INTEGER, PRIMARY KEY(user, kind));
CREATE TABLE IF NOT EXISTS rec_new(user INTEGER PRIMARY KEY, kind TEXT, value REAL, prev REAL, ref TEXT, pay INTEGER DEFAULT 0, ts INTEGER);
""")
FLAG = {r["user"] for r in q("SELECT user FROM rec_new")}


def _set(uid, kind, value, ref, pay=0):
    """Внутри транзакции вызывающего. Возвращает True, если это праздничный рекорд."""
    old = q1("SELECT value FROM records WHERE user=? AND kind=?", uid, kind)
    prev = old["value"] if old else 0
    if value <= prev:
        return False
    db.execute("INSERT INTO records(user,kind,value,ref,pay,ts) VALUES(?,?,?,?,?,?) ON CONFLICT(user,kind) DO UPDATE SET "
               "value=excluded.value, ref=excluded.ref, pay=excluded.pay, ts=excluded.ts", (uid, kind, value, str(ref), pay, now()))
    if prev >= MIN[kind] and value >= MIN[kind]:
        db.execute("INSERT INTO rec_new(user,kind,value,prev,ref,pay,ts) VALUES(?,?,?,?,?,?,?) ON CONFLICT(user) DO UPDATE SET "
                   "kind=excluded.kind, value=excluded.value, prev=excluded.prev, ref=excluded.ref, pay=excluded.pay, ts=excluded.ts",
                   (uid, kind, value, prev, str(ref), pay, now()))
        FLAG.add(uid)
        return True
    return False


def on_win(uid, kind, delta, stake):
    """Из app.event(): выигрыш в игре со ставкой."""
    if uid <= 0 or delta <= 0 or not stake:
        return
    _set(uid, "win", delta, kind, delta)
    if stake >= X_MIN_STAKE:
        _set(uid, "x", round((delta + stake) / stake, 2), kind, delta)


def on_gift(uid, gift_id, value):
    """Из open_case: подарок из кейса."""
    if uid > 0 and value > 0:
        _set(uid, "gift", value, gift_id)


@app.middleware("http")
async def _rec_header(request, call_next):
    resp = await call_next(request)
    uid = getattr(request.state, "uid", None)
    if uid and uid in FLAG:
        resp.headers["X-Rec"] = "1"
    return resp


def _gift_brief(gid):
    try:
        g = q1("SELECT id, col, model, value FROM gifts WHERE id=?", int(gid))
    except (TypeError, ValueError):
        return None
    return dict(g) if g else None


@app.get(R + "/records/new")
def records_new(uid=Depends(auth)):
    r = q1("SELECT * FROM rec_new WHERE user=?", uid)
    with A.tx():
        db.execute("DELETE FROM rec_new WHERE user=?", (uid,))
    FLAG.discard(uid)
    if not r:
        return {"rec": None}
    return {"rec": {"kind": r["kind"], "title": TITLES[r["kind"]], "value": r["value"], "prev": r["prev"], "pay": r["pay"],
                    "gift": _gift_brief(r["ref"]) if r["kind"] == "gift" else None, "game": r["ref"] if r["kind"] != "gift" else None}}


@app.get(R + "/records/{tid}")
def records_of(tid: int, uid=Depends(auth)):
    rows = {r["kind"]: r for r in q("SELECT * FROM records WHERE user=?", tid)}
    return {"items": [{"kind": k, "title": TITLES[k], "value": r["value"], "ts": r["ts"],
                       "gift": _gift_brief(r["ref"]) if k == "gift" else None, "game": r["ref"] if k != "gift" else None}
                      for k in ("win", "x", "gift") if (r := rows.get(k))]}


A.REC_WIN = on_win
