#!/usr/bin/env python3
"""Снимок состояния игры одним файлом — для переноса на другой хостинг.

Собирает в np-snapshot-<дата>.tar.gz:
  • game.db  — вся игра: игроки, балансы, подарки, кланы, СЕЗОНЫ, чеки, крипта и т. д. (целостная копия);
  • logs.db  — журнал действий (если есть, не обязателен);
  • u/        — загрузки игроков: свои аватарки и баннеры профиля.

Пути определяются сами (и переносная версия data/+web/u, и боевая /root/NePridymal+/var/www/nepridymal/u),
либо задай вручную: python snapshot.py --db путь/к/game.db --uploads путь/к/u [--with-env] [--out файл.tar.gz]

Перенос на новый сервер:
  1) здесь:     python snapshot.py            → получишь np-snapshot-….tar.gz
  2) скопируй этот файл на новый сервер в папку с игрой и переименуй в  restore.tar.gz
     (копируй напрямую — scp/флешка/облако; в публичный GitHub базу класть НЕЛЬЗЯ: там балансы и токен бота)
  3) там:       запусти start (или python run.py) — база и загрузки развернутся сами, игра поднимется
  Старый сервер перед этим останови: один бот не может работать в двух местах.
"""
import argparse
import os
import sqlite3
import sys
import tarfile
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))


def find_db(explicit):
    cand = [explicit, os.environ.get("DB_PATH"),
            os.path.join(ROOT, "data", "game.db"), os.path.join(ROOT, "game.db"),
            "/root/NePridymal/game.db"]
    for p in cand:
        if p and os.path.exists(p):
            return os.path.abspath(p)
    return None


def find_uploads(explicit, db_path):
    wd = os.environ.get("WEB_DIR")
    cand = [explicit, os.path.join(wd, "u") if wd else None,
            os.path.join(ROOT, "web", "u"),
            os.path.join(os.path.dirname(db_path), "..", "web", "u") if db_path else None,
            "/var/www/nepridymal/u"]
    for p in cand:
        if p and os.path.isdir(p):
            return os.path.abspath(p)
    return None


def main():
    ap = argparse.ArgumentParser(description="Снимок игры для переноса на другой хостинг")
    ap.add_argument("--db", help="путь к game.db (по умолчанию определяется сам)")
    ap.add_argument("--uploads", help="папка загрузок u/ (по умолчанию определяется сама)")
    ap.add_argument("--out", help="имя архива (по умолчанию np-snapshot-<дата>.tar.gz)")
    ap.add_argument("--with-env", action="store_true", help="вложить .env (ТАМ ТОКЕН БОТА — только для личного переноса!)")
    args = ap.parse_args()

    db = find_db(args.db)
    if not db:
        sys.exit("Не нашёл game.db. Укажи вручную: python snapshot.py --db путь/к/game.db")
    logs = os.path.join(os.path.dirname(db), "logs.db")
    uploads = find_uploads(args.uploads, db)
    out = args.out or os.path.join(os.getcwd(), f"np-snapshot-{time.strftime('%Y-%m-%d-%H%M')}.tar.gz")

    print(f"База:     {db}")
    print(f"Логи:     {logs if os.path.exists(logs) else '— нет (не обязательно)'}")
    print(f"Загрузки: {uploads or '— нет'}")

    with tempfile.TemporaryDirectory() as tmp:
        snap = os.path.join(tmp, "game.db")
        src, dst = sqlite3.connect(db), sqlite3.connect(snap)   # online backup — целостно при работающей игре
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        users = sqlite3.connect(snap).execute("SELECT COUNT(*) FROM users").fetchone()[0]

        with tarfile.open(out, "w:gz") as tar:
            tar.add(snap, arcname="game.db")
            if os.path.exists(logs):
                tar.add(logs, arcname="logs.db")
            if uploads:
                n = 0
                for name in sorted(os.listdir(uploads)):
                    fp = os.path.join(uploads, name)
                    if os.path.isfile(fp):
                        tar.add(fp, arcname=f"u/{name}")
                        n += 1
                print(f"Загрузок вложено: {n}")
            if args.with_env:
                env = os.path.join(ROOT, ".env")
                if os.path.exists(env):
                    tar.add(env, arcname=".env")
                    print("⚠️  .env вложён — в нём ТОКЕН БОТА. Храни архив как пароль, в публичный репозиторий не клади.")

    size = os.path.getsize(out) / 1048576
    print(f"\nГотово: {out}  ({size:.1f} МБ, игроков: {users})")
    print("Перенос: скопируй этот файл на новый сервер в папку с игрой, переименуй в restore.tar.gz и запусти start.")


if __name__ == "__main__":
    main()
