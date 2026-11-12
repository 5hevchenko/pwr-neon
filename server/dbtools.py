"""Админка → «База»: экспорт и импорт базы игры (только владелец — ADMIN_IDS из .env).
Экспорт: горячая копия SQLite → gzip → бот присылает файл владельцу в личку (в Telegram это надёжнее скачивания из мини-аппа).
Импорт: .db или .db.gz телом запроса → проверка целостности и таблиц → бэкап текущей базы → замена → перезапуск сервиса
(systemd / launchd / планировщик Windows поднимают его сами: в памяти остаются кэши старой базы, поэтому без перезапуска нельзя)."""
import asyncio
import gzip
import os
import sqlite3
import time

from fastapi import Depends, Request

import app as A
from app import DB_PATH, LOCK, R, TOKEN, app, db, err

MAX_UPLOAD = 300 * 1024 * 1024        # больше — точно не наша база
NEED_TABLES = {"users", "events", "kv", "gifts"}
TMP_DIR = os.path.dirname(os.path.abspath(DB_PATH))
BACKUP_DIR = os.path.join(TMP_DIR, "backups")


def _snapshot(path):
    """Согласованная копия живой базы (backup API — безопасно при работающей игре)."""
    dst = sqlite3.connect(path)
    with LOCK:
        db.backup(dst)
    dst.close()


def _check(path):
    """Это база нашей игры и она цела? Возвращает число игроков или бросает err()."""
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0] if "users" in tables else 0
        c.close()
    except sqlite3.DatabaseError:
        err("это не база SQLite")
    if ok != "ok":
        err(f"база повреждена: {ok[:80]}")
    miss = NEED_TABLES - tables
    if miss:
        err("это не база этой игры: нет таблиц " + ", ".join(sorted(miss)))
    return users


def _routes():
    from admin import OWNERS, admin, log

    @app.post(R + "/admin/db/export")
    async def db_export(aid=Depends(admin)):
        if aid not in OWNERS:
            err("Экспорт базы — только владелец")
        stamp = time.strftime("%Y-%m-%d-%H%M")
        tmp = os.path.join(TMP_DIR, f".export-{stamp}.db")
        try:
            await asyncio.to_thread(_snapshot, tmp)
            users = sqlite3.connect(tmp).execute("SELECT COUNT(*) FROM users").fetchone()[0]
            data = await asyncio.to_thread(lambda: gzip.compress(open(tmp, "rb").read(), 6))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        if len(data) > 49 * 1024 * 1024:
            err("база больше 50 МБ — бот не сможет её прислать, забери файл с сервера")
        r = await A.http.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", timeout=120,
                            data={"chat_id": str(aid), "caption": f"🗄 База игры · {stamp} · игроков: {users}"},
                            files={"document": (f"game-{stamp}.db.gz", data, "application/gzip")})
        if not r.json().get("ok"):
            err("бот не смог отправить файл — открой чат с ботом и нажми «Старт»")
        log(aid, "db_export", None, f"{users} игроков, {len(data) // 1024} КБ")
        return {"ok": True, "users": users, "kb": len(data) // 1024}

    @app.post(R + "/admin/db/import")
    async def db_import(req: Request, aid=Depends(admin)):
        if aid not in OWNERS:
            err("Импорт базы — только владелец")
        if int(req.headers.get("content-length") or 0) > MAX_UPLOAD:
            err("файл слишком большой")
        raw = await req.body()
        if len(raw) < 1024:
            err("пустой файл")
        stamp = time.strftime("%Y-%m-%d-%H%M%S")
        tmp = os.path.join(TMP_DIR, f".import-{stamp}.db")
        try:
            if raw[:2] == b"\x1f\x8b":   # .gz
                try:
                    raw = await asyncio.to_thread(gzip.decompress, raw)
                except Exception:
                    err("не получилось распаковать .gz")
                if len(raw) > MAX_UPLOAD:
                    err("файл слишком большой")
            if not raw.startswith(b"SQLite format 3\x00"):
                err("это не база SQLite (нужен файл .db или .db.gz)")
            with open(tmp, "wb") as f:
                f.write(raw)
            del raw
            users = await asyncio.to_thread(_check, tmp)
            # бэкап текущей базы — откатиться можно всегда
            os.makedirs(BACKUP_DIR, exist_ok=True)
            before = os.path.join(BACKUP_DIR, f"game-before-import-{stamp}.db")
            await asyncio.to_thread(_snapshot, before)
            await asyncio.to_thread(lambda: (open(before + ".gz", "wb").write(gzip.compress(open(before, "rb").read(), 6)), os.remove(before)))
            # замена: копируем загруженную базу поверх живой через backup API под общим замком (ни одна ставка не пересечётся)
            src = sqlite3.connect(tmp)
            with LOCK:
                src.backup(db)
                log(aid, "db_import", None, f"{users} игроков; старая база: backups/{os.path.basename(before)}.gz")
            src.close()
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        # в памяти кэши старой базы (шансы, баны, раунд краша…) — перезапускаемся; менеджер сервиса поднимет за секунды.
        # os._exit, а не штатная остановка: штатная записала бы возвраты ставок краша из старой базы в новую.
        asyncio.get_running_loop().call_later(1.5, os._exit, 0)
        return {"ok": True, "users": users, "backup": os.path.basename(before) + ".gz"}


_routes()
