"""«Бур» — гонка трёх буров вглубь. Игрок ставит на один бур; каждый бур проходит пласты, пока не сломается.
Твой бур прошёл глубже всех — выплата = множитель пласта, где он остановился (чем глубже, тем больше).
Ничья на самом глубоком пласте — множитель делится поровну между лидерами. Не первый — ставка сгорает.
Глубины трёх буров независимы и одинаково распределены, поэтому выбор бура — только азарт, не шанс.
Множители пластов масштабируются так, чтобы возврат был RTP (games.drill_rtp, вкладка «Шансы»).
Режим «Глубина»: игрок выбирает пласт-цель; если его бур дошёл до цели или глубже — ставка × множитель цели
(= RTP / шанс дойти, до x92 за ядро). Соперники в этом режиме не участвуют."""
import itertools
import random

from fastapi import Depends, Request

from app import R, add_xp, app, auth, bal, check_bet, db, edge, err, event, tx
from settings import conf, tuned

RTP = conf("games.drill_rtp", 0.96)
LAYERS = 10                                                  # 0 — сломался сразу, 10 — дошёл до ядра
SURVIVE = [.93, .88, .84, .8, .76, .72, .68, .64, .58, .4]   # шанс пройти пласт k+1, если дошёл до k
SHAPE = [0, 1.6, 1.8, 2, 2.2, 2.5, 2.9, 3.5, 4.5, 6.5, 25]     # форма таблицы; итог — × коэффициент под RTP
NAMES = ["Поверхность", "Дёрн", "Глина", "Песчаник", "Известняк", "Гранит", "Базальт", "Обсидиан", "Магма", "Кристаллы", "Ядро"]


def _dist():
    """P(бур остановился ровно на пласте k), k = 0..LAYERS."""
    reach = [1.0]
    for s in SURVIVE:
        reach.append(reach[-1] * s)
    return [reach[k] - reach[k + 1] for k in range(LAYERS)] + [reach[LAYERS]], reach


def _win_w():
    """Ожидаемая доля выигрыша на каждом пласте (с делением ничьих) — для нормировки под RTP."""
    p, _ = _dist()
    w = [0.0] * (LAYERS + 1)
    for a, b, c in itertools.product(range(LAYERS + 1), repeat=3):
        m = max(a, b, c)
        if a == m and a > 0:
            w[a] += p[a] * p[b] * p[c] / (a, b, c).count(m)
    return w


W = _win_w()


def mults():
    c = edge(tuned("games.drill_rtp", RTP)) / sum(W[k] * SHAPE[k] for k in range(LAYERS + 1))
    return [0] + [max(1.0, round(SHAPE[k] * c, 2)) for k in range(1, LAYERS + 1)]   # победа никогда не меньше ставки


def _depth(surv=None, rr=None):
    surv = surv or SURVIVE
    k = 0
    while k < LAYERS and (rr[k] if rr is not None else random.random()) < surv[k]:
        k += 1
    return k


# режим «Глубина»: свой шанс пройти пласт (глубже — реже), множитель цели = RTP / P(дойти до цели)
SURVIVE_D = [.9, .85, .8, .75, .7, .65, .6, .55, .5, .3]


def depth_reach():
    r, out = 1.0, [1.0]
    for s in SURVIVE_D:
        r *= s
        out.append(r)
    return out


def depth_mults():
    rtp = edge(tuned("games.drill_rtp", RTP))
    return [0] + [int(rtp / r * 100) / 100 for r in depth_reach()[1:]]   # вниз до копейки — возврат не выше заявленного


@app.get(R + "/drill")
def drill(uid=Depends(auth)):
    _, reach = _dist()
    return {"layers": LAYERS, "mults": mults(), "names": NAMES, "reach": [round(r * 100, 1) for r in reach],
            "depthMults": depth_mults(), "depthReach": [round(r * 100, 2) for r in depth_reach()],
            "rtp": round(edge(tuned("games.drill_rtp", RTP)) * 100, 1)}


@app.post(R + "/drill/play")
async def drill_play(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, pick = int(b.get("bet", 0)), int(b.get("pick", -1))
    if pick not in (0, 1, 2):
        err("выбери бур")
    if b.get("mode") == "depth":
        target = int(b.get("target", 0))
        if not 1 <= target <= LAYERS:
            err("выбери пласт-цель")
        dm = depth_mults()
        import fair
        with tx():
            check_bet(uid, bet)
            rr, pf = fair.rolls(uid, "drill", ref=f"depth:{target}", n=LAYERS)
            d = _depth(SURVIVE_D, rr)
            won = d >= target
            m = dm[target] if won else 0
            pay = int(bet * m)
            db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
            event(uid, "drill", pay - bet, stake=bet, pf=pf, res={"pay": pay})
            lvl = add_xp(uid, max(1, bet // 20))
        depths = [0, 0, 0]
        depths[pick] = d
        return {"mode": "depth", "depths": depths, "pick": pick, "target": target, "won": won, "tie": 0, "mult": m, "pay": pay, "bet": bet,
                "stars": bal(uid), "levelup": lvl, "mults": mults(), "depthMults": dm, "pf": pf}
    ms = mults()
    import fair
    with tx():
        check_bet(uid, bet)
        rr, pf = fair.rolls(uid, "drill", ref="classic", n=3 * LAYERS)
        depths = [_depth(None, rr[i * LAYERS:(i + 1) * LAYERS]) for i in range(3)]
        d, top = depths[pick], max(depths)
        lead = depths.count(top)
        won = d == top and d > 0
        m = round(ms[d] / lead, 2) if won else 0
        pay = int(bet * m)
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
        event(uid, "drill", pay - bet, stake=bet, pf=pf, res={"pay": pay})
        lvl = add_xp(uid, max(1, bet // 20))
    return {"depths": depths, "pick": pick, "won": won, "tie": lead if won and lead > 1 else 0, "mult": m, "pay": pay, "bet": bet,
            "stars": bal(uid), "levelup": lvl, "mults": ms, "pf": pf}
