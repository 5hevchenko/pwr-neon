"""«Кено» — поле из 40 чисел: игрок отмечает от 1 до 10, сервер вытягивает 10 шаров. Выплата — по числу совпадений
из таблицы (зависит от того, сколько отмечено, и от риска). Шансы точные (гипергеометрия), множители масштабируются
под возврат RTP (games.keno_rtp, вкладка «Шансы») с округлением вниз — возврат никогда не выше заявленного."""
import secrets
from functools import lru_cache
from math import comb, floor

from fastapi import Depends, Request

from app import R, add_xp, app, auth, bal, check_bet, db, edge, err, event, tx
from settings import conf, tuned

RTP = conf("games.keno_rtp", 0.96)
N, DRAW, PICK = 40, 10, 10
RND = secrets.SystemRandom()
# форма выплат: [risk][отмечено-1][совпало] — относительные веса, итоговые иксы = форма × (RTP / матожидание формы)
SHAPES = {
    "low": [[.7, 1.85], [0, 2, 3.8], [0, 1.1, 1.38, 26], [0, 0, 2.2, 7.9, 90], [0, 0, 1.5, 4.2, 13, 300], [0, 0, 1.1, 2, 6.2, 100, 700],
            [0, 0, 1.1, 1.6, 3.5, 15, 225, 700], [0, 0, 1.1, 1.5, 2, 5.5, 39, 100, 800], [0, 0, 1.1, 1.3, 1.7, 2.5, 7.5, 50, 250, 1000],
            [0, 0, 1.1, 1.2, 1.3, 1.8, 3.5, 13, 50, 250, 1000]],
    "mid": [[.4, 2.75], [0, 1.8, 5.1], [0, 0, 2.8, 50], [0, 0, 1.7, 10, 100], [0, 0, 1.4, 4, 14, 390], [0, 0, 0, 3, 9, 180, 710],
            [0, 0, 0, 2, 7, 30, 400, 800], [0, 0, 0, 2, 4, 11, 67, 400, 900], [0, 0, 0, 2, 2.5, 5, 15, 100, 500, 1000],
            [0, 0, 0, 1.6, 2, 4, 7, 26, 100, 500, 1000]],
    "high": [[0, 3.96], [0, 0, 17.1], [0, 0, 0, 81.5], [0, 0, 0, 10, 259], [0, 0, 0, 4.5, 48, 450], [0, 0, 0, 0, 11, 350, 710],
             [0, 0, 0, 0, 7, 90, 400, 800], [0, 0, 0, 0, 5, 20, 270, 600, 900], [0, 0, 0, 0, 4, 11, 56, 500, 800, 1000],
             [0, 0, 0, 0, 3.5, 8, 13, 63, 500, 800, 1000]],
}


def chance(k, h):
    """P(совпало h из k отмеченных) при 10 шарах из 40."""
    return comb(k, h) * comb(N - k, DRAW - h) / comb(N, DRAW)


@lru_cache(maxsize=64)
def _table(risk, k, rtp):
    s = SHAPES[risk][k - 1]
    c = rtp / sum(chance(k, h) * s[h] for h in range(k + 1))
    return tuple(floor(x * c * 100) / 100 for x in s)


def table(risk, k):
    return list(_table(risk, k, round(edge(tuned("games.keno_rtp", RTP)), 4)))


@app.get(R + "/keno")
def keno(uid=Depends(auth)):
    return {"tables": {r: [table(r, k) for k in range(1, PICK + 1)] for r in SHAPES},
            "chances": [[round(chance(k, h) * 100, 4) for h in range(k + 1)] for k in range(1, PICK + 1)],
            "n": N, "draw": DRAW, "pick": PICK, "rtp": round(edge(tuned("games.keno_rtp", RTP)) * 100, 1)}


@app.post(R + "/keno")
async def keno_play(req: Request, uid=Depends(auth)):
    b = await req.json()
    bet, risk = int(b.get("bet", 0)), str(b.get("risk", "mid"))
    if risk not in SHAPES:
        err("нет такого риска")
    try:
        picks = sorted({int(x) for x in b.get("picks") or []})
    except (TypeError, ValueError):
        err("отметь числа на поле")
    if not 1 <= len(picks) <= PICK or len(picks) != len(b.get("picks") or []) or not all(1 <= x <= N for x in picks):
        err(f"отметь от 1 до {PICK} разных чисел от 1 до {N}")
    t = table(risk, len(picks))
    import fair
    with tx():
        check_bet(uid, bet)
        rr, pf = fair.rolls(uid, "keno", ref=",".join(map(str, picks)), n=DRAW)
        draw = fair.sample(rr, range(1, N + 1), DRAW)
        hits = len(set(draw) & set(picks))
        m = t[hits]
        pay = int(bet * m)
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (bet, pay, uid))
        event(uid, "keno", pay - bet, stake=bet, pf=pf, res={"draw": draw, "hits": hits, "mult": m, "N": N})
        lvl = add_xp(uid, max(1, bet // 20))
    return {"draw": draw, "hits": hits, "mult": m, "pay": pay, "bet": bet, "stars": bal(uid), "levelup": lvl, "pf": pf}
