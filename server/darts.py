"""«Дартс» — бросок дротика в мишень. Зоны мишени — с разными множителями по выбранному риску:
низкий — частые небольшие выплаты, высокий — почти всё мимо, но яблочко даёт много.
Шансы зон фиксированы, множители масштабируются под возврат RTP (games.darts_rtp, вкладка «Шансы»).
Сервер выбирает зону и точку попадания внутри неё — клиент только рисует полёт."""
import math
import random

from fastapi import Depends, Request

from app import R, add_xp, app, auth, bal, check_bet, db, edge, err, event, tx
from settings import conf, tuned

RTP = conf("games.darts_rtp", 0.96)
# зона → (шанс, радиусы от/до в долях радиуса мишени)
ZONES = [
    ("miss", 0.16, (1.04, 1.16)),
    ("outer", 0.30, (0.64, 0.94)),
    ("inner", 0.24, (0.11, 0.57)),
    ("double", 0.12, (0.955, 0.995)),
    ("treble", 0.11, (0.585, 0.625)),
    ("obull", 0.05, (0.045, 0.09)),
    ("bull", 0.02, (0.0, 0.032)),
]
NAMES = {"miss": "Мимо", "outer": "Сектор", "inner": "Сектор", "double": "Удвоение", "treble": "Утроение", "obull": "Внешнее яблочко", "bull": "Яблочко"}
SHAPES = {
    "low": {"miss": 0, "outer": 0.5, "inner": 1.1, "double": 1.5, "treble": 2, "obull": 3, "bull": 5},
    "mid": {"miss": 0, "outer": 0, "inner": 1, "double": 2, "treble": 3, "obull": 6, "bull": 15},
    "high": {"miss": 0, "outer": 0, "inner": 0, "double": 0, "treble": 4, "obull": 12, "bull": 50},
}
ORDER = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]   # номера секторов по часовой от верха


def table(risk):
    s = SHAPES[risk]
    ev = sum(p * s[z] for z, p, _ in ZONES)
    c = edge(tuned("games.darts_rtp", RTP)) / ev
    return {z: math.floor(s[z] * c * 100) / 100 for z, _, _ in ZONES}   # вниз до копейки — возврат не выше заявленного


@app.get(R + "/darts")
def darts(uid=Depends(auth)):
    return {"tables": {r: table(r) for r in SHAPES}, "chances": {z: p for z, p, _ in ZONES}, "names": NAMES,
            "rtp": round(edge(tuned("games.darts_rtp", RTP)) * 100, 1)}


@app.post(R + "/darts/throw")
async def darts_throw(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, risk = int(b.get("bet", 0)), str(b.get("risk", "mid"))
    if risk not in SHAPES:
        err("нет такого риска")
    t = table(risk)
    import fair
    with tx():
        check_bet(uid, bet)
        rr, pf = fair.rolls(uid, "darts", ref=risk, n=4)
        x = rr[0]
        for z, p, (r0, r1) in ZONES:
            x -= p
            if x < 0:
                break
        m = t[z]
        pay = int(bet * m)
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
        event(uid, "darts", pay - bet, stake=bet, pf=pf, res={"pay": pay})
        lvl = add_xp(uid, max(1, bet // 20))
    # точка попадания внутри зоны: радиус равномерно по площади, угол — середина сектора ± чуть-чуть (те же честные броски)
    r = math.sqrt(rr[1] * (r1 * r1 - r0 * r0) + r0 * r0)
    seg = fair.idx(rr[2], 20)
    ang = seg * 18 + rr[3] * 14 - 7
    num = 25 if z == "obull" else 50 if z == "bull" else ORDER[seg] * (2 if z == "double" else 3 if z == "treble" else 1) if z != "miss" else 0
    return {"zone": z, "name": NAMES[z], "mult": m, "pay": pay, "bet": bet, "r": round(r, 4), "a": round(ang, 2), "score": num,
            "stars": bal(uid), "levelup": lvl, "pf": pf}
