"""«Самолётик» (в духе Aviamasters): самолёт летит над облаками и собирает бонусы — «+0,1…+1» ставки
и «×2–×5»; ракеты делят счётчик пополам. В конце — посадка на корабль: сел — выплата счётчика, промахнулся — ноль.
Весь полёт считается на сервере сразу, клиент только анимирует. Шанс посадки подобран под RTP ≈ 97%."""
import random

from settings import tuned

from fastapi import Depends, Request

from app import R, add_xp, app, auth, check_bet, db, edge, err, event, tx, bal

MAX_X = 250
# (вид, значение, вес): add — прибавить долю ставки, mul — умножить, rocket — пополам
ITEMS = [("add", 0.1, 30), ("add", 0.2, 22), ("add", 0.5, 10), ("add", 1, 4),
         ("mul", 2, 4), ("mul", 3, 1.2), ("mul", 4, 0.4), ("mul", 5, 0.2), ("rocket", 0, 14)]
STEPS = (6, 12)       # сколько облаков пролетает
LAND_BASE = 0.3226    # симуляция 300k полётов: E[min(счётчик, 250)] ≈ 3,01 → 0,97 / 3,01; медиана ×2,05


def fly(rr):
    import fair
    k, path = 1.0, []
    for i in range(STEPS[0] + fair.idx(rr[0], STEPS[1] - STEPS[0] + 1)):
        kind, v, _ = ITEMS[fair.pick(rr[1 + i], [x[2] for x in ITEMS])]
        if kind == "add":
            k += v
        elif kind == "mul":
            k *= v
        else:
            k = k / 2
        k = min(k, MAX_X)
        path.append({"t": kind, "v": v, "k": round(k, 2)})
    return path, round(k, 2)


def land_chance():
    return LAND_BASE * edge(tuned("games.avia_rtp", 0.96)) / 0.97   # RTP ≈ 96% (в акцию 98%)


@app.post(R + "/avia")
async def avia(req: Request, uid=Depends(auth)):
    bet = int((await req.json()).get("bet", 0))
    import fair
    with tx():
        check_bet(uid, bet)
        rr, pf = fair.rolls(uid, "avia", n=14)   # 1 — число облаков, 12 — максимум предметов, 1 — посадка
        path, k = fly(rr)
        landed = rr[13] < land_chance()
        pay = int(bet * k) if landed else 0
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
        event(uid, "avia", pay - bet, stake=bet, pf=pf, res={"k": k, "landed": landed})
        lvl = add_xp(uid, max(1, bet // 20))
    return {"path": path, "k": k, "landed": landed, "pay": pay, "stars": bal(uid), "levelup": lvl, "pf": pf}


def simulate(n=400_000):
    tot = 0.0
    for _ in range(n):
        tot += fly()[1]
    return tot / n


if __name__ == "__main__":
    random.seed(1)
    e = simulate()
    print("E[k] =", round(e, 3), "→ LAND_BASE =", round(0.97 / e, 4))
