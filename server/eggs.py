"""Пасхалки: секретные действия в игре. Звёзд не дают (экономика) — только находка в коллекцию
и достижение «Охотник за пасхалками» (значок в профиль) за EGG_NEED находок. Подсказок в игре нет — в этом и смысл."""
from fastapi import Depends, Request

from app import R, app, auth, db, err, now, q1, tx

# id → название (показываем, только когда нашёл)
EGGS = {
    "anon": "Человек-невидимка",     # 5 раз подряд «скопировать адрес» в кошельке
    "rain": "Звездопад в кармане",   # 7 тапов по балансу в кошельке
    "spin": "Бочка",                 # 7 тапов по своей аватарке в профиле
    "needle": "Раскрутка",           # 5 тапов по центру кольца апгрейда
    "leet": "1337",                  # перевод ровно 1337 ⭐
    "iddqd": "Режим бога",           # набрать iddqd в поиске кошелька
    "owl": "Сова",                   # зайти в игру с 3 до 5 утра
    "fri13": "Пятница, 13-е",        # зайти в пятницу 13-го
    "ny": "С Новым годом!",          # зайти 31 декабря или 1 января
}
EGG_NEED = 7

db.execute("CREATE TABLE IF NOT EXISTS eggs(user INTEGER, egg TEXT, ts INTEGER, PRIMARY KEY(user, egg))")


def egg_count(uid):
    return q1("SELECT COUNT(*) n FROM eggs WHERE user=?", uid)["n"]


@app.post(R + "/egg")
async def egg_found(req: Request, uid=Depends(auth)):
    e = str((await req.json()).get("id", ""))
    if e not in EGGS:
        err("нет такой пасхалки")
    with tx():
        new = db.execute("INSERT OR IGNORE INTO eggs(user,egg,ts) VALUES(?,?,?)", (uid, e, now())).rowcount == 1
        n = egg_count(uid)
    return {"new": new, "name": EGGS[e], "found": n, "total": len(EGGS), "need": EGG_NEED}
