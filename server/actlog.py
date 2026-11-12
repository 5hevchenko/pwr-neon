"""Подробный журнал действий: каждый POST к API — кто, что нажал, с какими параметрами, ответ (код и текст ошибки),
время обработки и баланс сразу после. Пишется пачками в отдельную базу logs.db (не раздувает game.db и бэкапы),
хранится KEEP_DAYS дней. Читать: GET /admin/actlog?user=…&path=…&limit=… (только админы)."""
import asyncio
import os
import sqlite3
import threading
import time
from collections import deque

from fastapi import Depends, Request
from fastapi.responses import Response

from app import DB_PATH, R, VIA_BOT, app, err
from admin import OWNERS, admin, log

KEEP_DAYS = 10
LOG_DB = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "logs.db")
ldb = sqlite3.connect(LOG_DB, check_same_thread=False, isolation_level=None)
ldb.execute("PRAGMA journal_mode=WAL")
ldb.execute("PRAGMA synchronous=NORMAL")
ldb.executescript("""
CREATE TABLE IF NOT EXISTS actlog(id INTEGER PRIMARY KEY, ts REAL, user INTEGER, path TEXT, body TEXT, status INTEGER, ms INTEGER, stars INTEGER, err TEXT);
CREATE INDEX IF NOT EXISTS actlog_user ON actlog(user, ts);
CREATE INDEX IF NOT EXISTS actlog_ts ON actlog(ts);
""")
try:   # bot — бот франшизы, через которого сделано действие (0 — главный): для разбора и отката краж
    ldb.execute("ALTER TABLE actlog ADD COLUMN bot INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
LLOCK = threading.Lock()
# баланс читаем отдельным соединением только на чтение — не вмешиваемся в транзакции игры
rdb = sqlite3.connect(f"file:{os.path.abspath(DB_PATH)}?mode=ro", uri=True, check_same_thread=False)
RLOCK = threading.Lock()
BUF = deque(maxlen=50_000)
LOGCFG = {"on": True, "keep_days": KEEP_DAYS}   # живые настройки журнала из админки: вкл/выкл и срок хранения (дней)
ldb.execute("CREATE TABLE IF NOT EXISTS cfg(k TEXT PRIMARY KEY, v TEXT)")


def _loadcfg():
    try:
        rows = dict(ldb.execute("SELECT k, v FROM cfg").fetchall())
        LOGCFG["on"] = rows.get("on", "1") != "0"
        LOGCFG["keep_days"] = max(1, min(365, int(rows.get("keep_days", KEEP_DAYS))))
    except Exception as e:
        print("actlog cfg:", e, flush=True)


_loadcfg()


@app.middleware("http")
async def _actlog(request: Request, call_next):
    if request.method != "POST" or not request.url.path.startswith(R) or not LOGCFG["on"]:
        return await call_next(request)
    body = (await request.body())[:400].decode("utf-8", "replace")
    t0 = time.time()
    resp = await call_next(request)
    ms = int((time.time() - t0) * 1000)
    uid = getattr(request.state, "uid", None)
    detail = ""
    if resp.status_code >= 400:   # текст ошибки — для разбора жалоб («не даёт ставить» и т. п.)
        raw = b"".join([c async for c in resp.body_iterator])
        detail = raw[:200].decode("utf-8", "replace")
        resp = Response(raw, status_code=resp.status_code, headers=dict(resp.headers), media_type=resp.media_type)
    stars = None
    if uid:
        try:
            with RLOCK:
                r = rdb.execute("SELECT stars FROM users WHERE id=?", (uid,)).fetchone()
            stars = r[0] if r else None
        except Exception:
            pass
    BUF.append((t0, uid, request.url.path[len(R):], body, resp.status_code, ms, stars, detail, VIA_BOT.get()))
    return resp


def _flush():
    rows = []
    while BUF:
        rows.append(BUF.popleft())
    if rows:
        with LLOCK:
            ldb.execute("BEGIN")
            ldb.executemany("INSERT INTO actlog(ts,user,path,body,status,ms,stars,err,bot) VALUES(?,?,?,?,?,?,?,?,?)", rows)
            ldb.execute("COMMIT")


def _prune():
    with LLOCK:
        ldb.execute("DELETE FROM actlog WHERE ts<?", (time.time() - LOGCFG["keep_days"] * 86400,))


async def _loop():
    n = 0
    while True:
        await asyncio.sleep(3)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _flush)
            n += 1
            if n % 1200 == 1:   # раз в час
                await asyncio.get_running_loop().run_in_executor(None, _prune)
        except Exception as e:
            print("actlog:", e, flush=True)


@app.on_event("startup")
async def _start():
    asyncio.create_task(_loop())


@app.on_event("shutdown")
def _stop():
    _flush()


@app.get(R + "/admin/actlog")
def actlog(user: int = 0, path: str = "", hours: float = 24, limit: int = 300, aid=Depends(admin)):
    _flush()
    sql, args = "SELECT * FROM actlog WHERE ts>?", [time.time() - hours * 3600]
    if user:
        sql += " AND user=?"
        args.append(user)
    if path:
        sql += " AND path LIKE ?"
        args.append("%" + path.strip("/") + "%")
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(limit, 5000)))
    with LLOCK:
        cur = ldb.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return {"rows": [dict(zip(cols, r)) for r in cur.fetchall()]}


@app.get(R + "/admin/actlog/cfg")
def actlog_cfg(aid=Depends(admin)):
    """Настройки подробного журнала + сводка: вкл/выкл, срок хранения, сколько записей и места занимает."""
    _flush()
    with LLOCK:
        n, oldest = ldb.execute("SELECT COUNT(*), MIN(ts) FROM actlog").fetchone()
    size = 0
    for ext in ("", "-wal", "-shm"):
        try:
            size += os.path.getsize(LOG_DB + ext)
        except OSError:
            pass
    return {"on": LOGCFG["on"], "keep_days": LOGCFG["keep_days"], "rows": n or 0,
            "oldest": oldest, "bytes": size, "canEdit": aid in OWNERS}


@app.post(R + "/admin/actlog/cfg")
async def actlog_cfg_set(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Менять журнал может только владелец")
    b = await req.json()
    with LLOCK:
        if "on" in b:
            LOGCFG["on"] = bool(b["on"])
            ldb.execute("INSERT INTO cfg(k,v) VALUES('on',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", ("1" if LOGCFG["on"] else "0",))
        if "keep_days" in b:
            try:
                LOGCFG["keep_days"] = max(1, min(365, int(b["keep_days"])))
            except (TypeError, ValueError):
                err("Введи число дней (1–365)")
            ldb.execute("INSERT INTO cfg(k,v) VALUES('keep_days',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(LOGCFG["keep_days"]),))
    log(aid, "actlog_cfg", detail=f"журнал {'вкл' if LOGCFG['on'] else 'выкл'}, хранить {LOGCFG['keep_days']} дн")
    _prune()   # применить новый срок сразу
    return {"ok": True, "on": LOGCFG["on"], "keep_days": LOGCFG["keep_days"]}


@app.post(R + "/admin/actlog/clear")
def actlog_clear(aid=Depends(admin)):
    if aid not in OWNERS:
        err("Очистить журнал может только владелец")
    BUF.clear()
    with LLOCK:
        ldb.execute("DELETE FROM actlog")
        try:
            ldb.execute("VACUUM")
        except sqlite3.OperationalError:
            pass
    log(aid, "actlog_clear", detail="подробный журнал очищен")
    return {"ok": True}
