"""«Пока тебя не было»: игрок вернулся после 3+ дней. При первом заходе запоминаем, с какого момента его не было
(хук в app.touch), а клиент один раз забирает сводку: что начислено за это время, сколько дохода набежало,
готов ли бесплатный кейс, сколько ключей и какие друзья пришли. Звёзд сама сводка не даёт — только показывает."""
from fastapi import Depends

import app as A
from app import R, app, auth, db, now, q, q1, tx, user_brief

AWAY = 3 * 86400

db.executescript("CREATE TABLE IF NOT EXISTS away(user INTEGER PRIMARY KEY, since INTEGER, ts INTEGER);")

# начисления, которые стоит показать; ключ — вид события, значение — подпись
LABELS = {"div": "Дивиденды по акциям", "cashback": "Кэшбэк недели", "comeback": "Подарок за возвращение",
          "ref": "Бонусы за друзей", "ref_lvl": "Бонусы за друзей", "ref_ms": "Бонусы за друзей", "ref_buy": "Бонусы за друзей",
          "ref_top": "Бонусы за друзей", "ref_duo": "Бонусы за друзей", "giveaway": "Розыгрыш в канале", "gameday": "Призы Игры дня",
          "league": "Награда лиги", "tourn": "Призы турниров", "clanprize": "Призы клана", "transfer": "Переводы от игроков",
          "depint": "Проценты по вкладу", "jackpot": "Джекпот", "season": "Награда сезона"}


def on_return(uid, seen):
    """Из app.touch (внутри транзакции): игрок зашёл после долгого перерыва."""
    if seen and now() - seen >= AWAY:
        db.execute("INSERT INTO away(user,since,ts) VALUES(?,?,?) ON CONFLICT(user) DO UPDATE SET since=MIN(since, excluded.since), ts=excluded.ts",
                   (uid, seen, now()))


@app.get(R + "/away")
def away(uid=Depends(auth)):
    r = q1("SELECT * FROM away WHERE user=?", uid)
    if not r:
        return {"away": None}
    with tx():
        db.execute("DELETE FROM away WHERE user=?", (uid,))
    since, t = r["since"], now()
    got = {}
    kinds = tuple(LABELS)
    for e in q(f"SELECT kind, SUM(delta) s FROM events WHERE user=? AND ts>=? AND delta>0 AND kind IN ({','.join('?' * len(kinds))}) GROUP BY kind",
               uid, since, *kinds):
        lab = LABELS[e["kind"]]
        got[lab] = got.get(lab, 0) + e["s"]
    import income
    try:
        ready = income.income(uid=uid)["ready"]
    except Exception:
        ready = 0
    u = q1("SELECT * FROM users WHERE id=?", uid)
    free = not u["last_free"] or t >= u["last_free"] + A.free_every(u)
    keys = q1("SELECT COALESCE(SUM(n),0) n FROM case_keys WHERE user=?", uid)["n"]
    friends = [user_brief(f) for f in q("SELECT * FROM users WHERE ref_by=? AND created>=? ORDER BY created DESC LIMIT 5", uid, since)]
    return {"away": {"days": max(3, (t - since) // 86400), "got": [{"t": k, "v": v} for k, v in sorted(got.items(), key=lambda x: -x[1])],
                     "income": ready, "free": free, "keys": keys, "friends": friends}}


A.AWAY_HOOK = on_return
