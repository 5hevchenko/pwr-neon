"""Входящие (колокольчик в шапке): копии всех сообщений бота игроку — пишет app.notify().
История операций: последние движения звёзд по журналу событий."""
import asyncio

from fastapi import Depends, Request

from app import R, app, auth, db, now, q, q1, tx
from live import NAMES

KEEP = 100   # сообщений на игрока
try:
    db.execute("ALTER TABLE users ADD COLUMN inbox_read INTEGER DEFAULT 0")
except Exception:
    pass
db.executescript("""
CREATE TABLE IF NOT EXISTS inbox(id INTEGER PRIMARY KEY, user INTEGER, text TEXT, ts INTEGER);
CREATE INDEX IF NOT EXISTS inbox_user ON inbox(user, id);
""")

HIST = {**NAMES, "carousel": "Карусель", "safe": "Сейф", "ladder": "Лестница", "bizgoods": "Закупка товара", "bankbet": "Ставка на банк", "forecast": "Прогноз дня", "gameday": "Игра дня", "auction": "Аукцион банка", "bizmgr": "Управляющий бизнеса", "clanbiz": "Доход бизнесов клана", "backing": "Обеспечение банка от покупок", "dep": "Вклад в банк", "depint": "Проценты по вкладу", "depfee": "Комиссия за досрочное закрытие вклада", "admgift": "Подарок от администрации", "comp": "Компенсация от администрации", "case": "Кейс", "admin": "Начисление от администрации", "bizbuy": "Покупка бизнеса", "bizsell": "Продажа бизнеса", "buy": "Покупка звёзд", "buy_gift": "Звёзды в подарок", "style": "Оформление профиля", "cashback": "Кэшбэк недели", "clan": "Клан",
        "clandep": "Взнос в казну клана", "clanspend": "Казна клана", "crypto": "Крипта", "daily": "Бонус дня", "div": "Дивиденды", "fee": "Комиссия",
        "futures": "Фьючерсы", "gift": "Подарки", "income": "Доход", "jackpot": "Розыгрыш", "stack": "Стопка", "loan": "Кредит", "lucky": "Удачный момент",
        "mkbank": "Маркет банка", "onboard": "Старт новичка", "present": "Подарок другу", "quest": "Задания", "league": "Лига недели", "ref": "Реферал",
        "frcut": "Пассивный доход: доля налогов и комиссий", "franchise": "Свой бот: награда",
        "ref_lvl": "Реферал: друг дорос до уровня", "ref_ms": "Реферал: награда за активных друзей", "ref_buy": "Реферал: % с покупки друга",
        "ref_top": "Топ приглашений недели", "flash": "Ивент: раздача звёзд",
        "share": "Акции банка", "stake": "Стейкинг", "ticket": "Билет розыгрыша", "season": "Приз сезона", "tourn": "Турнир",
        "clanprize": "Приз клану", "album": "Награда альбома", "clanpay": "Выплата из казны клана", "set": "Награда за сет", "sparks": "Огоньки: награда за серию", "level": "Бонус уровня", "trade": "Обмен", "transfer": "Перевод", "wipe": "Вайп: сброс баланса", "thanks": "Благодарность банка за сезон", "bankgift": "Перевод в банк", "comeback": "Подарок за возвращение", "clanshare": "Акции клана", "clandiv": "Дивиденды клана"}


@app.get(R + "/inbox")
def inbox(uid=Depends(auth)):
    rows = q("SELECT id, text, ts FROM inbox WHERE user=? ORDER BY id DESC LIMIT 60", uid)
    last = q1("SELECT inbox_read FROM users WHERE id=?", uid)["inbox_read"] or 0
    if rows and rows[0]["id"] > last:
        with tx():
            db.execute("UPDATE users SET inbox_read=? WHERE id=?", (rows[0]["id"], uid))
    return {"items": [{"id": r["id"], "text": r["text"], "ts": r["ts"], "new": r["id"] > last} for r in rows]}


@app.get(R + "/history")
def history(uid=Depends(auth)):
    rows = q("SELECT kind, delta, ts FROM events WHERE user=? AND delta<>0 ORDER BY ts DESC, rowid DESC LIMIT 80", uid)
    return {"items": [{"kind": r["kind"], "name": HIST.get(r["kind"], r["kind"]), "delta": r["delta"], "ts": r["ts"]} for r in rows]}


def _prune():
    with tx():
        db.execute("DELETE FROM inbox WHERE ts<?", (now() - 30 * 86400,))
        db.execute(f"""DELETE FROM inbox WHERE id IN (SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY user ORDER BY id DESC) rn FROM inbox) WHERE rn>{KEEP})""")


async def hub_loop():
    await asyncio.sleep(120)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _prune)
        except Exception as e:
            print("hub:", e, flush=True)
        await asyncio.sleep(6 * 3600)


@app.on_event("startup")
async def _hub_start():
    asyncio.create_task(hub_loop())


_ERRS = {}


@app.post(R + "/clienterr")
async def clienterr(req: Request, uid=Depends(auth)):
    """Ошибки JS с устройств игроков — в журнал сервиса (не больше 30 в час с игрока)."""
    h = now() // 3600
    k = (uid, h)
    _ERRS[k] = _ERRS.get(k, 0) + 1
    if len(_ERRS) > 5000:
        _ERRS.clear()
    if _ERRS[k] <= 30:
        try:
            d = await req.json()
        except Exception:
            d = {}
        print("CLIENTERR", uid, str(d.get("m", ""))[:300], str(d.get("s", ""))[:120], d.get("l"), str(d.get("ua", ""))[:80], flush=True)
    return {"ok": True}
