"""«Пёсики» — слот 5×3 на 20 линий: собаки, вайлд-будка с множителем, лапки-скаттеры → фриспины с липкими вайлдами."""
from settings import _LIVE, conf
import random

ROWS, REELS = 3, 5
# символы: 0–4 — низкие (10 J Q K A), 5–9 — собаки (от дешёвой к дорогой), W — будка (вайлд), S — лапка (скаттер)
LOW = ["10", "J", "Q", "K", "A"]
DOGS = [("Spring Basket", "Chihuahua"), ("Spring Basket", "Dalmatian Pup"), ("Bunny Muffin", "Shiba Inu"),
        ("Neko Helmet", "Bulldog Bob"), ("Plush Pepe", "Puppy Pug")]
W, S = 10, 11
# базовые выплаты на 1 линию (в ставках на линию) за 3/4/5 подряд; итоговый масштаб подгоняется под RTP
PAY = [[12, 20, 40], [12, 20, 40], [15, 25, 50], [15, 25, 50], [18, 30, 60],   # «плоские» выплаты: даже 3 в ряд
       [25, 50, 120], [30, 60, 160], [40, 80, 220], [50, 110, 320], [80, 180, 800]]  # заметны относительно ставки
LINES = [[1, 1, 1, 1, 1], [0, 0, 0, 0, 0], [2, 2, 2, 2, 2], [0, 1, 2, 1, 0], [2, 1, 0, 1, 2], [1, 0, 0, 0, 1], [1, 2, 2, 2, 1],
         [0, 0, 1, 2, 2], [2, 2, 1, 0, 0], [1, 2, 1, 0, 1], [1, 0, 1, 2, 1], [0, 1, 1, 1, 0], [2, 1, 1, 1, 2], [0, 1, 0, 1, 0],
         [2, 1, 2, 1, 2], [1, 1, 0, 1, 1], [1, 1, 2, 1, 1], [0, 0, 2, 0, 0], [2, 2, 0, 2, 2], [0, 2, 2, 2, 0]]
NL = len(LINES)
FREE_SPINS = 6
FREE_BY_SCAT = {3: 6, 4: 10, 5: 15}   # лапок → фриспинов (5 и больше — 15)
BUY_PRICE = {3: 20, 4: 67}   # покупка бонуса, в ставках: средний выигрыш ~19,4× и ~64,7× → возврат ~97%
MAX_WIN = 5000          # кап выигрыша, в ставках
# веса символов на барабане: вайлд только на 2–4, скаттер только на 1, 3, 5
_BASE = [32, 22, 8, 3, 2, 6, 5, 4, 3, 2]   # низкие символы сконцентрированы — линии собираются часто


def _weights(reel, bonus=False):
    w = list(_BASE) + [0, 0]
    if reel in (1, 2, 3):
        w[W] = 3.6 if bonus else 3.0
    if reel in (0, 2, 4):
        w[S] = 0.6 if bonus else 5.3
    return w


SCALE = conf("games.dogs_scale", 0.405)   # симуляция 1,8 млн спинов: возврат ≈ SCALE × 2,43 → 0,405 ≈ 98,4% (было 0,395 ≈ 96%); покупка бонуса ≈ 98% / 96%


def _cell(reel, bonus, rng=random):
    s = rng.choices(range(12), weights=_weights(reel, bonus))[0]
    return s


def _grid(bonus=False, sticky=None, rng=random):
    g = [[_cell(r, bonus, rng) for _ in range(ROWS)] for r in range(REELS)]
    wm = {}
    for r in range(REELS):
        for c in range(ROWS):
            if g[r][c] == W:
                wm[(r, c)] = rng.choice((2, 2, 3))
    if sticky:   # липкие вайлды из фриспинов
        for (r, c), m in sticky.items():
            g[r][c] = W
            wm[(r, c)] = m
    return g, wm


def _eval(g, wm, line_bet, sc=None):
    sc = SCALE if sc is None else sc
    wins, total = [], 0.0
    for li, line in enumerate(LINES):
        first = g[0][line[0]]
        if first in (W, S):
            continue
        n, mult = 1, 1
        for r in range(1, REELS):
            s = g[r][line[r]]
            if s == first or s == W:
                n += 1
                if s == W:
                    mult *= wm[(r, line[r])]
            else:
                break
        if n >= 3:
            pay = PAY[first][n - 3] * sc * mult * line_bet
            total += pay
            wins.append({"line": li, "n": n, "sym": first, "mult": mult, "pay": pay})
    return wins, total


RTP_PER_SCALE = 2.43   # возврат ≈ SCALE × 2,43 (симуляция)


# доли возврата при SCALE = 1 (симуляция 400k спинов): обычные спины 1,742, фриспины 0,719; купленный бонус ≈ 97%
NB, BB, BUY_RTP = 1.742, 0.719, 0.97


def tune():
    """(масштаб выплат, множитель фриспинов, множитель купленного бонуса) по возврату из админки (games.dogs_rtp).
    Ниже обычного — урезаем все выплаты равномерно. Выше — обычные спины как были, а вся прибавка уходит в бонуски:
    чем выше процент, тем жирнее фриспины."""
    v = _LIVE.get("games.dogs_rtp")
    if not v or v <= SCALE * RTP_PER_SCALE:
        return (v / RTP_PER_SCALE if v else SCALE), 1.0, 1.0
    return SCALE, (v - SCALE * NB) / (SCALE * BB), v / BUY_RTP


def scale():
    return tune()[0]


def spin(bet, rng=random):
    """Полный раунд: базовый спин + (если 3+ лапки) фриспины. Возвращает кадры для анимации."""
    lb = bet / NL
    sc, fb, _ = tune()
    g, wm = _grid(rng=rng)
    wins, total = _eval(g, wm, lb, sc)
    frames = [{"grid": g, "wilds": _wl(wm), "wins": _wr(wins), "pay": int(total)}]
    scat = sum(1 for r in range(REELS) for c in range(ROWS) if g[r][c] == S)
    bonus_total = 0.0
    if scat >= 3:
        sticky, left = {}, FREE_BY_SCAT[min(scat, 5)]
        while left > 0:
            left -= 1
            g2, wm2 = _grid(True, sticky, rng)
            for k, m in wm2.items():
                sticky.setdefault(k, m)
            w2, t2 = _eval(g2, wm2, lb * fb, sc)
            bonus_total += t2
            frames.append({"grid": g2, "wilds": _wl(wm2), "wins": _wr(w2), "pay": int(t2), "free": True, "left": left})
    pay = min(int(total + bonus_total), bet * MAX_WIN)
    return {"frames": frames, "bonus": scat >= 3, "pay": pay, "scatters": scat}


def bonus_round(bet, scat, rng=random):
    """Купленный бонус: стартовый экран с ровно scat лапками (3 или 4) → фриспины. Кадры — как у обычного спина."""
    lb = bet / NL
    sc, _, fb = tune()
    g, wm = _grid(rng=rng)
    for r in range(REELS):   # убираем случайные лапки и раскладываем нужное количество на барабаны 1, 3, 5
        for c in range(ROWS):
            if g[r][c] == S:
                g[r][c] = rng.choice(range(5))
    spots = [(r, rng.randrange(ROWS)) for r in (0, 2, 4)]
    if scat > 3:
        r = rng.choice((0, 2, 4))
        c = rng.choice([x for x in range(ROWS) if (r, x) not in spots])
        spots.append((r, c))
    for r, c in spots:
        if (r, c) in wm:
            del wm[(r, c)]
        g[r][c] = S
    wins, total = _eval(g, wm, lb, sc)
    frames = [{"grid": g, "wilds": _wl(wm), "wins": _wr(wins), "pay": int(total)}]
    sticky, left, bonus_total = {}, FREE_BY_SCAT[scat], 0.0
    while left > 0:
        left -= 1
        g2, wm2 = _grid(True, sticky, rng)
        for k, m in wm2.items():
            sticky.setdefault(k, m)
        w2, t2 = _eval(g2, wm2, lb * fb, sc)
        bonus_total += t2
        frames.append({"grid": g2, "wilds": _wl(wm2), "wins": _wr(w2), "pay": int(t2), "free": True, "left": left})
    pay = min(int(total + bonus_total), bet * MAX_WIN)
    return {"frames": frames, "bonus": True, "pay": pay, "scatters": scat}


def _wl(wm):
    return [[r, c, m] for (r, c), m in wm.items()]


def _wr(wins):
    return [{"line": w["line"], "n": w["n"], "sym": w["sym"], "mult": w["mult"], "pay": int(w["pay"])} for w in wins]


def calibrate(target=0.95, n=60000, seed=1):
    """Подбор SCALE под нужный возврат игроку (быстрая симуляция при старте)."""
    global SCALE
    state = random.getstate()
    random.seed(seed)
    SCALE = 1.0
    tot = sum(spin(100)["pay"] for _ in range(n))
    SCALE = target / (tot / (n * 100))
    random.setstate(state)
    return SCALE


if __name__ == "__main__":
    import time
    t = time.time()
    s = calibrate()
    print("SCALE", round(s, 3), "за", round(time.time() - t, 1), "с")
    random.seed(7)
    N, tot, bon, big = 100000, 0, 0, 0
    for _ in range(N):
        r = spin(100)
        tot += r["pay"]
        bon += r["bonus"]
        big = max(big, r["pay"])
    print("RTP", round(tot / (N * 100), 3), "бонус раз в", round(N / max(1, bon)), "спинов, макс x", big / 100)
