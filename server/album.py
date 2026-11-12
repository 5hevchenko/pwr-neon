"""Альбом коллекций: все коллекции подарков, собранные — цветные. Награды за каждые 10 коллекций.
В зачёт идут подарки, которые у игрока хотя бы сутки (против фарма передачей подарков между аккаунтами)."""
from fastapi import Depends, Request

import economy as E
from app import R, app, auth, bal, db, err, event, now, q, q1, tx

# (сколько коллекций, звёзды, ключ кейса)
TIERS = [(10, 3_000, None), (20, 0, "luck"), (30, 10_000, None), (40, 0, "lux"), (50, 25_000, None), (60, 0, "cups"),
         (70, 50_000, None), (80, 0, "peach"), (90, 100_000, None), (100, 200_000, None), (110, 0, "mega"), (len(E.CATALOG), 1_000_000, None)]

db.executescript("CREATE TABLE IF NOT EXISTS album_claims(user INTEGER, tier INTEGER, ts INTEGER, PRIMARY KEY(user, tier));")


def _owned(uid, aged):
    sql = "SELECT col, COUNT(DISTINCT model) n FROM gifts WHERE owner=?" + (" AND COALESCE(acq,0)<=?" if aged else "") + " GROUP BY col"
    return {r["col"]: r["n"] for r in (q(sql, uid, now() - 86400) if aged else q(sql, uid))}


@app.get(R + "/album")
def album(uid=Depends(auth)):
    have, aged = _owned(uid, False), _owned(uid, True)
    claimed = {r["tier"] for r in q("SELECT tier FROM album_claims WHERE user=?", uid)}
    cols = sorted(E.CATALOG, key=lambda c: -E.base(c))
    return {"cols": [{"col": c, "base": E.base(c), "models": len(E.CATALOG[c]["models"]), "have": have.get(c, 0), "aged": c in aged} for c in cols],
            "total": len(cols), "count": len(have), "eligible": len(aged),
            "tiers": [{"need": n, "stars": s, "key": E.case_title(k, uid) if k else None, "claimed": n in claimed} for n, s, k in TIERS]}


@app.post(R + "/album/claim")
async def album_claim(req: Request, uid=Depends(auth)):
    need = int((await req.json()).get("need", 0))
    tier = next((t for t in TIERS if t[0] == need), None) or err("нет такой награды")
    with tx():
        if q1("SELECT 1 FROM album_claims WHERE user=? AND tier=?", uid, need):
            err("награда уже получена")
        got = len(_owned(uid, True))
        if got < need:
            err(f"нужно {need} коллекций, засчитано {got} (новые подарки засчитываются через сутки)")
        db.execute("INSERT INTO album_claims(user,tier,ts) VALUES(?,?,?)", (uid, need, now()))
        _, stars, key = tier
        if stars:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (stars, uid))
            event(uid, "album", stars)
        if key:
            db.execute("INSERT INTO case_keys(user,cid,n) VALUES(?,?,1) ON CONFLICT(user,cid) DO UPDATE SET n=n+1", (uid, key))
    return {"ok": True, "stars": bal(uid), "reward": stars, "key": E.case_title(key, uid) if key else None}
