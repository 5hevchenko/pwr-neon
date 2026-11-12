"""«Старт новичка»: разовые шаги с наградами, ведут по основным механикам."""
from fastapi import Depends

from app import R, app, auth, bal, db, err, event, now, q1, tx, GAME_KINDS

db.executescript("CREATE TABLE IF NOT EXISTS onboard(user INTEGER, step TEXT, ts INTEGER, PRIMARY KEY(user, step));")

# id, иконка, текст, подсказка-действие, награда
STEPS = [
    ("free", "gift", "Открой бесплатный кейс", "case-free", 300),
    ("game", "games", "Сыграй в любую мини-игру", "tab-games", 300),
    ("income", "wallet", "Забери доход с подарков", "inc", 300),
    ("biz", "store", "Купи первый бизнес", "inc", 500),
    ("profile", "edit", "Оформи профиль: описание или баннер", "edit-profile", 200),
    ("friend", "userPlus", "Позови друга или добавь в друзья", "friends", 1000),
    ("clan", "users", "Вступи в клан или создай свой", "clans", 700),
    ("present", "gift", "Подари подарок другу", "tab-inv", 700),
]


def _done(uid):
    u = q1("SELECT opened, bio, banner, refs FROM users WHERE id=?", uid)
    bimg = q1("SELECT banner_img FROM users WHERE id=?", uid)["banner_img"]
    games = q1(f"SELECT COUNT(*) n FROM events WHERE user=? AND kind IN {GAME_KINDS} AND kind!='case'", uid)["n"]
    return {
        "free": u["opened"] >= 1,
        "game": games >= 1,
        "income": q1("SELECT 1 FROM events WHERE user=? AND kind='income' LIMIT 1", uid) is not None,
        "biz": q1("SELECT 1 FROM biz WHERE user=? LIMIT 1", uid) is not None,
        "profile": bool(u["bio"] or u["banner"] or bimg),
        "friend": u["refs"] > 0 or q1("SELECT 1 FROM friends WHERE (a=? OR b=?) AND status='ok' LIMIT 1", uid, uid) is not None,
        "clan": q1("SELECT 1 FROM clan_members WHERE user=?", uid) is not None,
        "present": q1("SELECT 1 FROM gift_links WHERE sender=? LIMIT 1", uid) is not None
                   or q1("SELECT 1 FROM events WHERE user=? AND kind='present' LIMIT 1", uid) is not None,
    }


@app.get(R + "/onboard")
def onboard(uid=Depends(auth)):
    done = _done(uid)
    got = {r[0] for r in db.execute("SELECT step FROM onboard WHERE user=?", (uid,)).fetchall()}
    steps = [{"id": i, "icon": ic, "t": t, "go": go, "reward": rw, "done": done[i], "claimed": i in got} for i, ic, t, go, rw in STEPS]
    return {"steps": steps, "all": all(s["claimed"] for s in steps)}


@app.post(R + "/onboard/{sid}/claim")
def onboard_claim(sid: str, uid=Depends(auth)):
    st = next((s for s in STEPS if s[0] == sid), None) or err("нет такого шага")
    with tx():
        if not _done(uid)[sid]:
            err("шаг ещё не выполнен")
        if q1("SELECT 1 FROM onboard WHERE user=? AND step=?", uid, sid):
            err("награда уже получена")
        db.execute("INSERT INTO onboard VALUES(?,?,?)", (uid, sid, now()))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (st[4], uid))
        event(uid, "onboard", st[4])
    return {"reward": st[4], "stars": bal(uid)}
