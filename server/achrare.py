"""Редкость достижений: у какой доли игроков оно есть. Считаем раз в час в фоне, профиль берёт готовые цифры из A.ACH_PCT.
Игроки — все, кто хоть что-то делал в игре (открыл кейс или набрал опыт), без забаненных."""
import asyncio

import app as A
from app import qr

EVERY = 3600
_XP10 = 100 * (10 - 1) ** 2   # 10 уровень, как в app.level()


def _rare_pairs():
    return [(col, m) for col, (ml, _, _) in A.LOOK.items() for m, mp in ml.items() if mp and mp <= 5]


def compute():
    import eggs
    base = "u.banned=0 AND u.id>0 AND (u.opened>0 OR u.xp>0)"
    total = qr(f"SELECT COUNT(*) n FROM users u WHERE {base}")[0]["n"]
    if not total:
        return {}
    cnt = lambda sql, *a: qr(sql, *a)[0]["n"]   # отдельным соединением: подсчёт по всем игрокам не держит общий лок
    out = {
        "Первый кейс": cnt(f"SELECT COUNT(*) n FROM users u WHERE {base} AND u.opened>=1"),
        "Кейсоман": cnt(f"SELECT COUNT(*) n FROM users u WHERE {base} AND u.opened>=100"),
        "Космонавт": cnt(f"SELECT COUNT(*) n FROM users u WHERE {base} AND u.best_crash>=10"),
        "На Луну": cnt(f"SELECT COUNT(*) n FROM users u WHERE {base} AND u.best_crash>=100"),
        "Вербовщик": cnt(f"SELECT COUNT(*) n FROM users u WHERE {base} AND u.refs>=3"),
        "Ветеран": cnt(f"SELECT COUNT(*) n FROM users u WHERE {base} AND u.xp>=?", _XP10),
        "Магнат": cnt(f"SELECT COUNT(*) n FROM users u WHERE {base} AND u.stars + COALESCE((SELECT SUM(value) FROM gifts WHERE owner=u.id),0) >= 100000"),
        "Коллекционер": cnt(f"SELECT COUNT(*) n FROM (SELECT g.owner FROM gifts g JOIN users u ON u.id=g.owner WHERE {base} GROUP BY g.owner HAVING COUNT(DISTINCT g.col)>=20)"),
        "Душа компании": cnt(f"""SELECT COUNT(*) n FROM (SELECT x.id FROM (SELECT a id FROM friends WHERE status='ok' UNION ALL SELECT b FROM friends WHERE status='ok') x
                                JOIN users u ON u.id=x.id WHERE {base} GROUP BY x.id HAVING COUNT(*)>=5)"""),
        "Охотник за пасхалками": cnt(f"SELECT COUNT(*) n FROM (SELECT e.user FROM eggs e JOIN users u ON u.id=e.user WHERE {base} GROUP BY e.user HAVING COUNT(*)>=?)", eggs.EGG_NEED),
    }
    pairs = _rare_pairs()
    owners = set()
    for i in range(0, len(pairs), 400):   # по кускам: у SQLite ограничение на число параметров
        ch = pairs[i:i + 400]
        vals = ",".join("(?,?)" for _ in ch)
        rows = qr(f"WITH r(col,model) AS (VALUES {vals}) SELECT DISTINCT g.owner FROM gifts g JOIN r ON r.col=g.col AND r.model=g.model "
                  f"JOIN users u ON u.id=g.owner WHERE {base}", *[x for p in ch for x in p])
        owners.update(r[0] for r in rows)
    out["Легенда"] = len(owners)
    return {k: round(v * 100 / total, 1) for k, v in out.items()}


def refresh():
    try:
        A.ACH_PCT = compute()
    except Exception as e:
        print("achrare:", e, flush=True)


async def _loop():
    while True:
        await asyncio.get_running_loop().run_in_executor(None, refresh)
        await asyncio.sleep(EVERY)


@A.app.on_event("startup")
async def _start():
    if A.DEV:
        refresh()
    else:
        asyncio.create_task(_loop())
