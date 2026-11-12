"""Скретч-карты: 3×3 скрытых подарка, три одинаковых — выигрыш по таблице. Исход решается сервером при покупке,
стирание на клиенте — только анимация. Возврат ≈ 95%, выигрыш примерно в каждой третьей карте."""
import random

from settings import tuned

from fastapi import Depends, Request

import app as A
from app import R, add_xp, app, auth, bal, db, edge, err, event, tx

TIERS = {"bronze": 100, "gold": 1000, "diamond": 10000}
# (множитель, вероятность, символ-подарок)
PRIZES = [(1, .16, "Lol Pop"), (2, .09, "Jelly Bunny"), (3, .05, "Toy Bear"), (5, .03, "Signet Ring"),
          (10, .015, "Swiss Watch"), (25, .004, "Durov's Cap"), (100, .0006, "Plush Pepe")]   # Σ p·x ≈ 0,95
SYMS = [p[2] for p in PRIZES]


def _grid(win_sym, rng=random):
    """9 клеток: если есть выигрыш — ровно три win_sym, остальные символы максимум по два (без второй тройки)."""
    cells = [win_sym] * 3 if win_sym else []
    pool = [s for s in SYMS if s != win_sym]
    rng.shuffle(pool)
    counts = {}
    while len(cells) < 9:
        s = rng.choice(pool)
        if counts.get(s, 0) < 2:
            counts[s] = counts.get(s, 0) + 1
            cells.append(s)
    rng.shuffle(cells)
    return cells


LOW_MAX = 5   # призы меньше x5 — «мелочь» (вернули ставку), x5 и выше — крутые комбинации
_EV_LOW = sum(x * p for x, p, _ in PRIZES if x < LOW_MAX)    # ожидаемый возврат от мелких призов ≈ 0,49
_EV_HIGH = sum(x * p for x, p, _ in PRIZES if x >= LOW_MAX)  # ... от крутых ≈ 0,46
LOW_SENS = 0.545   # насколько резко частота мелких призов растёт с настройкой возврата


def _roll(rng=random):
    """Возврат игроку = настройка scratch_rtp (в акцию edge() поднимает его ещё). С ростом настройки
    растут обе части: чаще выигрывает карта (мелкие призы) И заметно чаще крутые комбинации (x5+).
    Крутые тиры подгоняются так, чтобы фактический возврат точно равнялся настройке — процент не врёт.
    Настройке дан широкий потолок (до 300%), чтобы разница между «обычно» и «на максимум» была явной."""
    rtp = edge(tuned("games.scratch_rtp", 0.94), 0.96)
    low_k = max(0.0, 1 + LOW_SENS * (rtp - 0.95))                       # частота мелких призов (x1–x3)
    high_k = max(0.0, (rtp - low_k * _EV_LOW) / _EV_HIGH) if _EV_HIGH else 0.0   # частота крутых — под точный возврат
    r = rng.random()
    for x, p, sym in PRIZES:
        pr = p * (low_k if x < LOW_MAX else high_k)
        if r < pr:
            return x, sym
        r -= pr
    return 0, None


@app.post(R + "/scratch")
async def scratch(req: Request, uid=Depends(auth)):
    tier = str((await req.json()).get("tier", "bronze"))
    price = TIERS.get(tier) or err("нет такой карты")
    if A.SELF_GUARD:
        A.SELF_GUARD(uid, price)
    import fair
    with tx():
        if bal(uid) < price:
            err("Не хватает звёзд")
        rng = fair.stream(uid, "scratch", tier)
        x, sym = _roll(rng)
        cells = _grid(sym, rng)
        pay = price * x
        pf = fair.close_stream(rng)
        db.execute("UPDATE users SET stars=stars-?+? WHERE id=?", (price, pay, uid))
        event(uid, "scratch", pay - price, stake=price, pf=pf, res={"mult": x})
        lvl = add_xp(uid, max(1, price // 20))
    return {"cells": cells, "mult": x, "sym": sym, "win": [i for i, c in enumerate(cells) if c == sym] if sym else [],
            "pay": pay, "price": price, "stars": bal(uid), "levelup": lvl}


@app.get(R + "/scratch")
def scratch_info(uid=Depends(auth)):
    return {"tiers": TIERS, "prizes": [{"mult": x, "sym": s} for x, _, s in PRIZES]}
