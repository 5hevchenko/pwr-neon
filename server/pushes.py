"""Пуши от бота по событиям в игре: что именно ждёт игрока прямо сейчас. Звёзд не раздают — только зовут к тому, что уже есть.

Правила:
  · на игрока — не больше push.day_max рекламных пушей в сутки и не чаще push.gap_hours (общий счёт app.push_take:
    сюда же входят анонсы ивентов flash.py, «возвращайся» retain.py, письма новичкам nudge.py и ежедневные отчёты);
  · у каждого события своя пауза повтора, и одно событие не идёт два раза подряд (кроме срочных: серия сгорает, турнир кончается);
  · у события несколько текстов — они чередуются; к каждому пушу — карточка-картинка (notifimg.make);
  · только с 9 до 21 по Москве, только тем, кто был в игре за последние 3 недели и вышел из неё больше 45 минут назад.
Событие — функция (игрок, контекст) → None или {"texts": [...], "card": (вид, заголовок, значение, со_звездой)}.
Вернулся ли игрок после пуша — отметка back в push_log (админка: GET /admin/pushes)."""
import asyncio
import random
import sys
import time

import app as A
import economy as E
from admin import admin
from app import Depends, R, Request, app, db, err, esc, now, q, q1
from settings import S, conf

ON = conf("push.on", True)
HOURS = range(9, 21)            # по Москве
EVERY = 300                     # проход раз в столько секунд
BATCH = 50                      # пушей за проход
SCAN = 150                      # игроков за проход
QUIET = 45 * 60                 # только что был в игре — не трогаем
ACTIVE = 21 * 86400             # дольше не заходил — им занимается «возвращайся» (retain.py)
RECHECK = 3600                  # ничего не нашлось — к игроку вернёмся через столько
_SKIP = {}                      # игрок → когда проверяли впустую
_ERR = set()                    # события, которые упали (в журнал — один раз)


def _m(name):
    return sys.modules.get(name)


def nm(u):
    n = (u["name"] or "").split()
    return esc(n[0][:20]) if n else "Привет"


def plural(n, one, few, many):
    n = abs(int(n))
    return one if n % 10 == 1 and n % 100 != 11 else few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def hours_left(sec):
    h = int(sec // 3600)
    return f"{h} ч" if h >= 1 else "меньше часа"


# ------------------------------------------------------------------ контекст прохода (общее для всех игроков)
def _ctx(t):
    g = time.gmtime(t + 10800)
    c = {"t": t, "hour": g.tm_hour, "wday": g.tm_wday, "d0": A.day_start(), "promo": A.promo(), "event": A.event_active(), "lazy": {}}
    rg = _m("realgifts")
    c["rg"] = rg if rg and rg.enabled() else None
    c["cases"] = sorted(((b["price"], b["title"], b["level"]) for b in rg._BUILT.values() if not b["paused"] and b["price"] and not b.get("hide"))) if c["rg"] else []
    c["free_gifts"] = bool(c["rg"] and rg.FREE_GIFTS)
    return c


def lazy(c, key, fn):
    """Тяжёлое общее значение считаем один раз за проход и только если понадобилось."""
    if key not in c["lazy"]:
        try:
            c["lazy"][key] = fn()
        except Exception as e:
            print("pushes ctx", key, type(e).__name__, e, flush=True)
            c["lazy"][key] = None
    return c["lazy"][key]


def _payer(c, uid):
    return bool(c["rg"] and c["rg"].payer(uid))


def _need_friend(u, c):
    """Бесплатный кейс подарков со второго раза открывается только за нового друга."""
    rg = c["rg"]
    if not rg or rg.FREE_FRIENDS <= 0:
        return False
    row = q1("SELECT opens, refs_at FROM free_gate WHERE user=? AND cid='free'", u["id"])
    return bool(row and row["opens"] and (u["refs"] or 0) - row["refs_at"] < rg.FREE_FRIENDS)


def _free_ready(u, c):
    return bool(u["last_free"]) and c["t"] >= u["last_free"] + A.free_every(u)


# ------------------------------------------------------------------ события: личное
def ev_free_ready(u, c):
    if not _free_ready(u, c) or _need_friend(u, c):
        return None
    g = c["free_gifts"]
    return {"card": ("gift", "Бесплатный кейс", "Готов!", False), "texts": [
        "🎁 Бесплатный кейс снова готов" + (" — внутри настоящий подарок Telegram." if g else ".") + " Открой, пока не забыл.",
        f"{nm(u)}, бесплатный кейс перезарядился. " + ("В нём только подарки, без звёзд." if g else "Загляни и открой."),
        "⏰ Кейс за 0 ⭐ ждёт. Открыть — пара секунд" + (", а подарок останется в сумке." if g else "."),
        "🎁 Твой бесплатный прокрут на месте." + (" Что выпадет сегодня — мишка, роза или что-то дороже?" if g else " Заходи и крути.")]}


def ev_free_friend(u, c):
    if not _free_ready(u, c) or not _need_friend(u, c):
        return None
    return {"card": ("invite", "Бесплатный кейс", "+1 друг", False), "texts": [
        "🎁 Бесплатный кейс с подарком готов — чтобы открыть, позови одного друга. Ссылка для приглашения в игре.",
        f"{nm(u)}, кейс за 0 ⭐ ждёт. Один новый друг по твоей ссылке — и он открывается.",
        "👥 Друг заходит по твоей ссылке — ты крутишь бесплатный кейс с настоящим подарком. Сегодня он ещё не открыт."]}


def ev_streak_risk(u, c):
    gone = c["t"] - (u["last_daily"] or 0)
    if (u["streak"] or 0) < 2 or not 40 * 3600 <= gone < 48 * 3600:
        return None
    left, n = hours_left(48 * 3600 - gone), u["streak"]
    return {"card": ("alert", "Серия сгорает", f"{n} {plural(n, 'день', 'дня', 'дней')}", False), "texts": [
        f"🔥 Серия бонусов ({n} дн.) сгорит через {left} — забери бонус дня!",
        f"{nm(u)}, {n} {plural(n, 'день', 'дня', 'дней')} подряд — и всё обнулится через {left}. Один заход, и серия цела.",
        f"⏳ До сгорания серии ({n} дн.) осталось {left}. Бонус дня ждёт в игре."]}


def ev_streak_key(u, c):
    gone, n = c["t"] - (u["last_daily"] or 0), (u["streak"] or 0) + 1
    if not (n == 7 or (n > 7 and n % 7 == 0)) or not A.DAILY_EVERY <= gone < 40 * 3600:
        return None
    title = esc(E.case_title(A.STREAK_KEYS[7], u["id"]))
    return {"card": ("gift", f"День {n} серии", "Ключ от кейса", False), "texts": [
        f"🔑 Сегодня {n}-й день серии: вместе с бонусом дня ты получишь ключ от кейса «{title}».",
        f"{nm(u)}, ты дошёл до {n}-го дня подряд. Забери бонус — к нему идёт ключ от кейса «{title}».",
        f"🎁 {n} дней без пропусков. Сегодняшний бонус — с ключом от кейса «{title}». Не пропусти."]}


def ev_daily_ready(u, c):
    gone = c["t"] - (u["last_daily"] or 0)
    if not u["last_daily"] or not A.DAILY_EVERY <= gone < 40 * 3600 or c["t"] - u["seen"] < 20 * 3600:
        return None
    n = (u["streak"] or 0) + 1
    return {"card": ("stars", "Бонус дня", f"День {n}", False), "texts": [
        f"⭐ Бонус дня готов — это будет {n}-й день серии. Чем длиннее серия, тем больше бонус.",
        f"{nm(u)}, бонус дня ждёт. Серия сейчас {n - 1} дн. — забери, чтобы она росла.",
        "⭐ Звёзды за вход на месте. Один тап — и они на балансе."]}


def ev_keys_wait(u, c):
    if c["t"] - u["seen"] < 12 * 3600:
        return None
    r = q1("SELECT cid, n, (SELECT SUM(n) FROM case_keys WHERE user=?1 AND n>0) total FROM case_keys WHERE user=?1 AND n>0 ORDER BY n DESC LIMIT 1", u["id"])
    if not r or r["cid"] not in E.CASES:
        return None
    title, n = esc(E.case_title(r["cid"], u["id"])), r["total"]
    return {"card": ("gift", "Ключ ждёт", E.case_title(r["cid"], u["id"]), False), "texts": [
        f"🔑 У тебя {n} {plural(n, 'ключ', 'ключа', 'ключей')} от кейсов. «{title}» открывается бесплатно — загляни.",
        f"{nm(u)}, ключ от кейса «{title}» лежит без дела. Открой — платить не нужно.",
        f"🎁 Неоткрытый кейс «{title}» ждёт тебя: ключ уже у тебя."]}


def ev_gift_wait(u, c):
    if not c["rg"]:
        return None
    r = q1("SELECT title, value, (SELECT COUNT(*) FROM real_items WHERE user=?1 AND status='bag') n FROM real_items "
           "WHERE user=?1 AND status='bag' AND ts<?2 ORDER BY value DESC LIMIT 1", u["id"], c["t"] - 86400)
    if not r:
        return None
    title, val = esc(r["title"]), S(r["value"])
    more = f" И ещё {r['n'] - 1} в сумке." if r["n"] > 1 else ""
    if _payer(c, u["id"]):
        texts = [f"🎁 Подарок «{title}» лежит в сумке. Выведи его на свой аккаунт Telegram или продай игре за ⭐ {val}.{more}",
                 f"{nm(u)}, твой «{title}» всё ещё в сумке. Забрать в Telegram или обменять на ⭐ {val} — решать тебе.{more}",
                 f"📦 В сумке ждёт «{title}» (⭐ {val}). Вывод — в пару тапов.{more}"]
    else:
        texts = [f"🎁 Подарок «{title}» лежит в сумке. Продай его игре за ⭐ {val} и открой кейс подороже.{more}",
                 f"{nm(u)}, твой «{title}» всё ещё в сумке: это ⭐ {val} на новый кейс.{more}",
                 f"📦 В сумке ждёт «{title}» (⭐ {val}). Вывод в Telegram открывается после пополнения баланса.{more}"]
    return {"card": ("gift", "Подарок в сумке", r["title"], False), "texts": texts}


def ev_skin_wait(u, c):
    r = q1("SELECT col, model, value FROM gifts WHERE owner=? AND src='cs' AND price IS NULL AND COALESCE(acq, created)<? ORDER BY value DESC LIMIT 1",
           u["id"], c["t"] - 86400)
    if not r:
        return None
    name, val = esc(f"{r['col']} {r['model']}"), S(r["value"])
    steam = " или выведи в Steam" if A.skins_real() else ""
    return {"card": ("gift", "Скин в сумке", r["col"], False), "texts": [
        f"🔫 Скин «{name}» лежит в сумке. Выставь на маркет, продай за ⭐ {val}{steam}.",
        f"{nm(u)}, твой «{name}» ценностью ⭐ {val} ждёт решения: маркет, продажа{steam}.",
        f"📦 В сумке скин «{name}». На маркете за него можно получить больше, чем у банка."]}


def _quests(u, c):
    """Задания игрока на сегодня — только если он сегодня был в игре (иначе прогресса нет)."""
    if u["seen"] < c["d0"]:
        return []
    if "quests" not in u["_x"]:
        u["_x"]["quests"] = A.quests_state(u["id"])
    return u["_x"]["quests"]


def ev_quest_claim(u, c):
    ready = [x for x in _quests(u, c) if x["have"] >= x["need"] and not x["claimed"]]
    if not ready:
        return None
    total, n = sum(x["reward"] for x in ready), len(ready)
    return {"card": ("stars", "Задания выполнены", f"+{S(total)}", True), "texts": [
        f"✅ {n} {plural(n, 'задание выполнено', 'задания выполнены', 'заданий выполнено')}, а награда не забрана: ⭐ {S(total)} ждут в «Заданиях».",
        f"{nm(u)}, ты заработал ⭐ {S(total)} за задания — осталось нажать «Забрать».",
        f"⭐ {S(total)} за задания дня лежат незабранными. В полночь задания обновятся."]}


def ev_quest_almost(u, c):
    if c["hour"] < 17:
        return None
    near = [x for x in _quests(u, c) if x["need"] > 1 and not x["claimed"] and x["need"] * 0.6 <= x["have"] < x["need"] and x["tier"] not in ("chest", "week")]
    if not near:
        return None
    x = max(near, key=lambda i: i["reward"])
    left = x["need"] - x["have"]
    return {"card": ("stars", "Почти готово", f"+{S(x['reward'])}", True), "texts": [
        f"🎯 Задание «{esc(x['t'])}»: осталось {left} из {x['need']}. Награда ⭐ {S(x['reward'])}, до полуночи успеешь.",
        f"{nm(u)}, до ⭐ {S(x['reward'])} за «{esc(x['t'])}» не хватает совсем чуть-чуть: {left}.",
        f"⏳ Задания дня обновятся в полночь. «{esc(x['t'])}» почти готово — ещё {left}, и ⭐ {S(x['reward'])} твои."]}


def ev_quest_new(u, c):
    if c["hour"] >= 13 or u["seen"] >= c["d0"]:
        return None
    if not q1("SELECT 1 FROM quest_claims WHERE user=? AND day>=? LIMIT 1", u["id"], c["d0"] - 7 * 86400):
        return None
    qs = lazy(c, "quests", lambda: [A.prize_k(x[8]) for x in A.quests_today()])
    if not qs:
        return None
    n, total = len(qs), sum(qs) + A.prize_k(A.QCHEST)
    return {"card": ("stars", "Задания дня", f"+{S(total)}", True), "texts": [
        f"📋 Новые задания дня: {n} {plural(n, 'задание', 'задания', 'заданий')} и сундук — всего до ⭐ {S(total)}.",
        f"{nm(u)}, задания обновились. Выполни все {n} и открой сундук: до ⭐ {S(total)} за день.",
        f"⭐ Сегодня за задания можно заработать до {S(total)} звёзд. Список уже в игре."]}


def ev_chest_week(u, c):
    if c["hour"] < 15 or q1("SELECT 1 FROM quest_claims WHERE user=? AND qid='chest' AND day=?", u["id"], c["d0"]):
        return None
    st = A.chest_streak(u["id"])
    if not 3 <= st < 7:
        return None
    left, prize = 7 - st, S(A.prize_k(A.QWEEK))
    return {"card": ("stars", "Сундук недели", f"{st} из 7", False), "texts": [
        f"🏆 Сундук {st} {plural(st, 'день', 'дня', 'дней')} подряд. До недельной награды ⭐ {prize} — ещё {left} {plural(left, 'день', 'дня', 'дней')}. Сегодняшний пока не открыт.",
        f"{nm(u)}, серия сундуков {st} из 7. Пропустишь сегодня — начнёшь заново, а награда за неделю ⭐ {prize}.",
        f"⏳ Сегодняшний сундук заданий ещё закрыт. Серия {st} из 7, в конце — ⭐ {prize}."]}


def ev_level_close(u, c):
    li = A.level_info(u["xp"] or 0)
    L, need = li["level"], li["to"] - li["xp"]
    if L < 2 or (li["xp"] - li["from"]) < 0.85 * (li["to"] - li["from"]):
        return None
    new = [t for p, t, lv in c["cases"] if lv == L + 1]
    bonus = S(A.level_bonus(L + 1)) if (u["lvl_paid"] or 0) <= L and A.level_bonus(L + 1) >= 1000 else None
    tail = f" и откроется кейс «{esc(new[0])}»" if new else ""
    return {"card": ("event", "Почти новый уровень", f"Уровень {L + 1}", False), "texts": [
        f"⬆️ До {L + 1} уровня осталось {need} опыта" + (f": бонус ⭐ {bonus}" if bonus else "") + tail + ".",
        f"{nm(u)}, ещё немного — и {L + 1} уровень" + (f". За него ⭐ {bonus}" if bonus else "") + tail + ".",
        f"🎯 {need} опыта до {L + 1} уровня. Опыт идёт за каждый кейс и каждую игру."]}


def ev_afford(u, c):
    L = A.level(u["xp"] or 0)
    ok = [(p, t) for p, t, lv in c["cases"] if lv <= L and p <= (u["stars"] or 0)]
    if not ok or c["t"] - u["seen"] < 12 * 3600:
        return None
    if q1("SELECT 1 FROM events WHERE user=? AND kind='case' AND ts>? LIMIT 1", u["id"], c["t"] - 2 * 86400):
        return None
    p, title = ok[-1]
    return {"card": ("gift", "Хватает на кейс", title, False), "texts": [
        f"⭐ На балансе {S(u['stars'])} — хватает на кейс «{esc(title)}» за ⭐ {S(p)}. Внутри только подарки.",
        f"{nm(u)}, твоих звёзд хватает на «{esc(title)}». Подарок из него останется в сумке.",
        f"🎁 Кейс «{esc(title)}» (⭐ {S(p)}) тебе по карману. Что выпадет?"]}


def ev_almost_afford(u, c):
    L = A.level(u["xp"] or 0)
    ok = [(p, t) for p, t, lv in c["cases"] if lv <= L]
    if not ok:
        return None
    p, title = ok[0]
    stars = u["stars"] or 0
    if not 0.6 * p <= stars < p:
        return None
    miss = S(p - stars)
    return {"card": ("stars", "Почти хватает", miss, True), "texts": [
        f"⭐ До кейса «{esc(title)}» не хватает {miss}. Задания дня и бонус за вход закроют разницу.",
        f"{nm(u)}, ещё ⭐ {miss} — и кейс «{esc(title)}» твой. Загляни в «Задания».",
        f"🎯 {miss} звёзд до первого кейса с подарками. Самый быстрый путь — задания дня."]}


def ev_first_buy(u, c):
    shop = _m("shop")
    if not shop or not shop.shop_on() or not shop.is_first(u["id"]) or (u["opened"] or 0) < 5 or u["_n"].get("first_buy", 0) >= 3:
        return None
    x2 = ("звёзд вдвое больше" if shop.FIRST_X == 1 else f"звёзд на {int(shop.FIRST_X * 100)}% больше") if shop.FIRST_X > 0 else ""
    odds = bool(c["rg"] and c["rg"].RTP_FREE < c["rg"].RTP)
    if x2 and odds:
        texts = [f"⭐ Первая покупка — {x2}. И после пополнения шансы на дорогие призы в кейсах подарков выше.",
                 f"{nm(u)}, на первую покупку {x2}, а шансы на дорогие призы в кейсах подарков вырастут. Пополнить можно за Telegram Stars.",
                 f"💎 У игроков с пополнением шансы на дорогие призы выше. А на первую покупку ещё и {x2}."]
    elif x2:
        texts = [f"⭐ Первая покупка — {x2}. Пополнить можно за Telegram Stars.",
                 f"{nm(u)}, на первую покупку {x2}. Хватит на кейсы подороже."]
    elif odds:
        texts = ["💎 У игроков с пополнением шансы на дорогие призы в кейсах подарков выше. Пополнить можно за Telegram Stars.",
                 f"{nm(u)}, после первого пополнения шансы на дорогие призы в кейсах подарков вырастут."]
    else:
        return None
    return {"card": ("stars", "Первая покупка", "×2" if shop.FIRST_X == 1 else "Бонус", False), "texts": texts}


def ev_pass_case(u, c):
    pw = _m("pwr")
    if not pw:
        return None
    for tier in ("VIP", "PWR", "FREE"):
        if not pw.owned(u, tier):
            continue
        row = q1("SELECT last_day FROM pwr_pass WHERE user=? AND tier=?", u["id"], tier)
        if tier == "FREE" and (not row or c["d0"] - row["last_day"] > 86400):   # бесплатную дорожку напоминаем, только пока серия жива
            continue
        streak, done, nxt = pw._state(u["id"], tier)
        if done:
            continue
        burn = " Пропустишь день — серия начнётся заново." if tier == "FREE" else ""
        return {"card": ("gift", "Кейс пропуска", f"День {nxt} из 7", False), "texts": [
            f"🎫 Ежедневный кейс пропуска «{pw.TITLE[tier]}» ещё не открыт: сегодня день {nxt} из 7.{burn}",
            f"{nm(u)}, кейс пропуска ждёт. День {nxt} из 7, седьмой — улучшенный.{burn}",
            f"🎁 Сегодняшний кейс пропуска на месте. Серия {streak % 7} из 7.{burn}"]}
    return None


def ev_pass_end(u, c):
    pw = _m("pwr")
    if not pw:
        return None
    for tier, col in (("VIP", "pvip_until"), ("PWR", "pwr_until")):
        left = (u[col] or 0) - c["t"]
        if 0 < left < 36 * 3600:
            return {"card": ("alert", "Пропуск", "Заканчивается", False), "texts": [
                f"🎫 Пропуск «{pw.TITLE[tier]}» заканчивается через {hours_left(left)}. Серия платной дорожки не сгорает — продли и продолжай с того же дня.",
                f"{nm(u)}, пропуск «{pw.TITLE[tier]}» действует ещё {hours_left(left)}. Сегодняшний кейс успей открыть."]}
    return None


def ev_friend_none(u, c):
    refs = _m("refs")
    if not refs or not refs.cfg("on") or (u["refs"] or 0) > 0 or u["created"] > c["t"] - 3 * 86400 or (u["opened"] or 0) < 3:
        return None
    jb, nb = refs.cfg("join_bonus"), refs.cfg("new_bonus")
    key = " и ключ от кейса" if refs.cfg("gift_on") else ""
    free = " Каждый новый друг открывает тебе бесплатный кейс с подарком." if c["rg"] and c["rg"].FREE_FRIENDS > 0 else ""
    you = f"тебе ⭐ {S(jb)}" if jb else "бонусы тебе"
    return {"card": ("invite", "Позови друга", f"+{S(jb)}" if jb else "Бонус", bool(jb)), "texts": [
        f"👥 Позови друга: {you}, ему ⭐ {S(nb)}{key}.{free}",
        f"{nm(u)}, по твоей ссылке ещё никто не пришёл. За друга — {you}, а с его пополнений идёт процент.{free}",
        f"🔗 Твоя ссылка для приглашения — в игре. Друг получает ⭐ {S(nb)}{key}, {you}.{free}"]}


def ev_market_stale(u, c):
    r = q1("SELECT col, price, listed FROM gifts WHERE owner=? AND price IS NOT NULL AND listed<? ORDER BY listed LIMIT 1", u["id"], c["t"] - 3 * 86400)
    if not r:
        return None
    days = (c["t"] - r["listed"]) // 86400
    return {"card": ("market", "Лот не продан", r["col"], False), "texts": [
        f"🏷 «{esc(r['col'])}» стоит на маркете уже {days} {plural(days, 'день', 'дня', 'дней')} за ⭐ {S(r['price'])}. Снизь цену — или продай в «Скупке» сразу.",
        f"{nm(u)}, твой лот «{esc(r['col'])}» пока никто не купил. Посмотри цены соседних лотов — возможно, он дороже рынка."]}


# ------------------------------------------------------------------ события: общее (турнир, сезон, розыгрыш…)
def _tourn(c):
    T = _m("tourn")
    if not T:
        return None
    ps = T.period_start(c["t"])
    out = {"ps": ps, "left": ps + T.PERIOD - c["t"], "since": c["t"] - ps, "games": T.games_of(ps), "place": {}, "fans": {}, "T": T}
    for g in out["games"]:
        for i, r in enumerate(T.standings(g, ps, 30)):
            if r["user"] not in out["place"] or out["place"][r["user"]][1] > i + 1:
                out["place"][r["user"]] = (g, i + 1)
    return out


def ev_tourn_end(u, c):
    tr = lazy(c, "tourn", lambda: _tourn(c))
    if not tr or tr["left"] > 8 * 3600 or u["id"] not in tr["place"]:
        return None
    g, place = tr["place"][u["id"]]
    name, left = esc(tr["T"].NAMES.get(g, g)), hours_left(tr["left"])
    prize = "ты в призах" if place <= 5 else "призы получают первые пять"
    return {"card": ("win", "Турнир", f"{place} место", False), "texts": [
        f"🏆 Турнир «{name}» заканчивается через {left}. Ты на {place} месте — {prize}.",
        f"{nm(u)}, до итогов турнира «{name}» {left}. Сейчас у тебя {place} место, {prize}."]}


def ev_tourn_start(u, c):
    tr = lazy(c, "tourn", lambda: _tourn(c))
    if not tr or tr["since"] > 12 * 3600:
        return None
    for g in tr["games"]:
        if g not in tr["fans"]:
            tr["fans"][g] = {r["user"] for r in q("SELECT user FROM events WHERE kind=? AND ts>? GROUP BY user HAVING COUNT(*)>=20", g, c["t"] - 30 * 86400)}
        if u["id"] in tr["fans"][g]:
            name, days = esc(tr["T"].NAMES.get(g, g)), max(1, tr["left"] // 86400)
            return {"card": ("event", "Турнир начался", tr["T"].NAMES.get(g, g), False), "texts": [
                f"🏆 Начался турнир по «{name}» — твоя игра. Первые пять делят призовой фонд, до конца {days} {plural(days, 'день', 'дня', 'дней')}.",
                f"{nm(u)}, стартовал турнир «{name}». Считается чистый выигрыш в игре, таблица уже открыта."]}
    return None


def ev_season_end(u, c):
    Sn = _m("seasons")
    if not Sn:
        return None
    _, title, _, end = Sn.season_bounds(c["t"])
    left = end - c["t"]
    if left > 48 * 3600:
        return None
    rank = lazy(c, "season", lambda: dict(Sn._board()["rank"])) or {}
    place = rank.get(u["id"])
    if not place or place > 30:
        return None
    tail = "ты в призовой десятке: звёзды и рамка аватарки" if place <= 10 else "призы получает первая десятка"
    return {"card": ("win", "Сезон", f"{place} место", False), "texts": [
        f"🏁 Сезон «{esc(title)}» заканчивается через {hours_left(left)}. Ты на {place} месте — {tail}.",
        f"{nm(u)}, до конца сезона {hours_left(left)}. Сейчас {place} место, {tail}."]}


def ev_jackpot(u, c):
    J = _m("jackpot")
    if not J or c["hour"] < 18:
        return None
    jp = lazy(c, "jackpot", lambda: (J._tickets(c["d0"]), J._pool(c["d0"])))
    if not jp or not jp[0].get(u["id"]):
        return None
    n, pool = jp[0][u["id"]], S(jp[1])
    return {"card": ("win", "Розыгрыш банка", pool, True), "texts": [
        f"🎟 Сегодня ночью розыгрыш банка: у тебя {n} {plural(n, 'билет', 'билета', 'билетов')}, в фонде ⭐ {pool}. Билеты идут за сыгранные раунды.",
        f"{nm(u)}, ты участвуешь в розыгрыше банка — {n} {plural(n, 'билет', 'билета', 'билетов')}. Фонд ⭐ {pool}, итоги в полночь по серверу."]}


def ev_starfall(u, c):
    F = _m("starfall")
    if not F:
        return None
    r = lazy(c, "starfall", lambda: q1("SELECT * FROM sf_rounds WHERE status='open' ORDER BY id DESC LIMIT 1"))
    if not r or not r["target"] or r["filled"] < 0.8 * r["target"]:
        return None
    mine = q1("SELECT COALESCE(SUM(amount),0) s FROM sf_bets WHERE round=? AND user=?", r["id"], u["id"])["s"]
    if not mine:
        return None
    pct = int(r["filled"] * 100 / r["target"])
    return {"card": ("win", "Звездопад", f"{pct}%", False), "texts": [
        f"🌠 Шкала «Звездопада» заполнена на {pct}%. Ты в игре — приз разыграют, как только шкала дойдёт до конца.",
        f"{nm(u)}, «Звездопад» почти заполнен ({pct}%). Твой вклад участвует в розыгрыше подарка."]}


def ev_league_end(u, c):
    Lg = _m("league")
    if not Lg or c["wday"] != 6 or c["hour"] < 15:
        return None
    ws = A.week_start()
    m = q1("SELECT gid FROM league_mem WHERE week=? AND user=?", ws, u["id"])
    if not m:
        return None
    rows = Lg.standings(ws, m["gid"])
    place = next((i + 1 for i, r in enumerate(rows) if r["user"] == u["id"]), None)
    if not place:
        return None
    tier = esc(Lg.TIERS[min(Lg.tier_of(u["id"]), len(Lg.TIERS) - 1)])
    tail = "ты в тройке, она получает звёзды" if place <= 3 else "первая тройка получает звёзды, верхние места идут в лигу выше"
    return {"card": ("win", "Лига недели", f"{place} место", False), "texts": [
        f"🏅 Неделя в лиге «{tier}» заканчивается сегодня ночью. Ты на {place} месте из {len(rows)} — {tail}.",
        f"{nm(u)}, итоги лиги «{tier}» — в полночь по серверу. Сейчас {place} место из {len(rows)}."]}


def ev_promo(u, c):
    p = c["promo"]
    if not p:
        return None
    perks = ", ".join(x[0].lower() + x[1:] for x in p["perks"][:3])
    return {"card": ("event", p["title"], "Сегодня", False), "texts": [
        f"🎉 «{esc(p['title'])}» в игре: {esc(perks)}.",
        f"{nm(u)}, сегодня «{esc(p['title'])}»: {esc(perks)}. Полный список — в игре."]}


def ev_event(u, c):
    e = c["event"]
    if not e:
        return None
    perks = "; ".join(e["perks"][:3])
    return {"card": ("event", e["title"], "Ивент", False), "texts": [
        f"🎉 В игре ивент «{esc(e['title'])}»: {esc(perks)}.",
        f"{nm(u)}, идёт «{esc(e['title'])}». {esc(perks)}."]}


def ev_bigwin(u, c):
    if not c["rg"] or c["t"] - u["seen"] < 24 * 3600:
        return None
    w = lazy(c, "bigwin", lambda: q1("SELECT r.user, r.title, r.value, r.paid, u.name FROM real_items r JOIN users u ON u.id=r.user "
                                     "WHERE r.ts>? AND r.paid>0 AND r.value>=r.paid*4 ORDER BY r.value DESC LIMIT 1", c["t"] - 86400))
    if not w or w["user"] == u["id"]:
        return None
    who = esc((w["name"] or "Игрок").split()[0][:16])
    return {"card": ("win", "Выигрыш дня", w["title"], False), "texts": [
        f"🔥 Сегодня {who} выбил «{esc(w['title'])}» ценностью ⭐ {S(w['value'])} из кейса за ⭐ {S(w['paid'])}.",
        f"{nm(u)}, пока тебя не было: {who} открыл кейс за ⭐ {S(w['paid'])} и забрал «{esc(w['title'])}» (⭐ {S(w['value'])})."]}


def ev_cashback(u, c):
    R = _m("retain")
    if not R or c["wday"] != 6:
        return None
    amt = R.cashback_preview(u["id"])
    if amt <= 0:
        return None
    pct = f"{R.CB_RATE * 100:g}%"
    return {"card": ("stars", "Кэшбэк недели", f"+{S(amt)}", True), "texts": [
        f"💸 Неделя не задалась? В понедельник вернём {pct} проигрыша в играх — сейчас это ⭐ {S(amt)}.",
        f"{nm(u)}, завтра кэшбэк недели: {pct} от минуса в играх. По текущим цифрам тебе придёт ⭐ {S(amt)}."]}


# (событие, приоритет, пауза повтора в сутках, срочное, функция). Срочное идёт первым и может повторяться подряд.
EVENTS = [
    ("streak_risk", 100, 0.8, True, ev_streak_risk),
    ("tourn_end", 90, 2, True, ev_tourn_end),
    ("season_end", 88, 20, True, ev_season_end),
    ("pass_end", 85, 6, True, ev_pass_end),
    ("league_end", 80, 6, True, ev_league_end),
    ("streak_key", 78, 6, False, ev_streak_key),
    ("starfall", 75, 2, False, ev_starfall),
    ("quest_claim", 72, 1, False, ev_quest_claim),
    ("pass_case", 70, 2, False, ev_pass_case),
    ("free_ready", 66, 2, False, ev_free_ready),
    ("free_friend", 64, 3, False, ev_free_friend),
    ("gift_wait", 62, 4, False, ev_gift_wait),
    ("keys_wait", 61, 3, False, ev_keys_wait),
    ("jackpot", 60, 3, False, ev_jackpot),
    ("quest_almost", 58, 2, False, ev_quest_almost),
    ("chest_week", 57, 2, False, ev_chest_week),
    ("tourn_start", 56, 3, False, ev_tourn_start),
    ("event", 55, 20, False, ev_event),
    ("promo", 54, 6, False, ev_promo),
    ("cashback", 53, 6, False, ev_cashback),
    ("level_close", 50, 5, False, ev_level_close),
    ("afford", 48, 4, False, ev_afford),
    ("daily_ready", 46, 3, False, ev_daily_ready),
    ("quest_new", 44, 3, False, ev_quest_new),
    ("skin_wait", 42, 5, False, ev_skin_wait),
    ("almost_afford", 40, 5, False, ev_almost_afford),
    ("first_buy", 38, 7, False, ev_first_buy),
    ("market_stale", 36, 7, False, ev_market_stale),
    ("bigwin", 30, 4, False, ev_bigwin),
    ("friend_none", 28, 10, False, ev_friend_none),
]
TITLES = {"streak_risk": "Серия бонусов сгорает", "tourn_end": "Турнир заканчивается", "season_end": "Сезон заканчивается", "pass_end": "Пропуск заканчивается",
          "league_end": "Итоги лиги сегодня", "streak_key": "День серии с ключом", "starfall": "Звездопад почти заполнен", "quest_claim": "Награда за задания не забрана",
          "pass_case": "Кейс пропуска не открыт", "free_ready": "Бесплатный кейс готов", "free_friend": "Бесплатный кейс: нужен друг", "gift_wait": "Подарок лежит в сумке",
          "keys_wait": "Есть неиспользованные ключи", "jackpot": "Розыгрыш банка сегодня", "quest_almost": "Задание почти выполнено", "chest_week": "Серия сундуков",
          "tourn_start": "Турнир начался", "event": "Сезонный ивент", "promo": "Акция выходных", "cashback": "Кэшбэк недели завтра", "level_close": "Почти новый уровень",
          "afford": "Хватает на кейс", "daily_ready": "Бонус дня готов", "quest_new": "Новые задания дня", "skin_wait": "Скин лежит в сумке", "almost_afford": "Почти хватает на кейс",
          "first_buy": "Первая покупка", "market_stale": "Лот на маркете не продан", "bigwin": "Крупный выигрыш дня", "friend_none": "Позови друга",
          # события других модулей, которые идут через тот же лимит
          "flash_luck3": "Ивент «Удача ×3»", "flash_luck5": "Ивент «Удача ×5»", "flash_drop": "Ивент «Раздача звёзд»", "nudge": "Письмо новичку / Игра дня",
          "comeback": "Возвращайся (с ключом)", "heist": "Возвращайся (копилка)", "report": "Ежедневный отчёт о доходе", "sparks": "Серия огоньков сгорает",
          "week": "Итоги недели в играх", "likes": "Выигрыш оценили", "starfall_done": "Звездопад разыгран"}


def pick(u, c, hist):
    """Событие для игрока: срочное — первое подходящее; иначе случайное из трёх самых важных (по весу), чтобы пуши не шли по кругу."""
    last2 = [h["ev"] for h in hist[:2]]
    last = {}
    for h in hist:
        last.setdefault(h["ev"], h["ts"])
    found = []
    for ev, prio, cd, urgent, fn in EVENTS:
        if ev in last and c["t"] - last[ev] < cd * 86400:
            continue
        if not urgent and ev in last2:
            continue
        try:
            r = fn(u, c)
        except Exception as e:
            if ev not in _ERR:
                _ERR.add(ev)
                print("pushes event", ev, type(e).__name__, e, flush=True)
            continue
        if not r:
            continue
        if urgent:
            return ev, r
        found.append((ev, prio, r))
        if len(found) >= 3:
            break
    if not found:
        return None
    ev, _, r = random.choices(found, weights=[f[1] for f in found])[0]
    return ev, r


def _row(r):
    u = dict(r)
    u["_x"] = {}
    return u


def run(only=None, dry=False):
    """Один проход. only — проверить одного игрока (для тестов и админки), dry — ничего не отправлять."""
    wipe = _m("wipe")
    if not ON or (wipe and wipe.frozen()):
        return []
    t = now()
    with A.LOCK:
        db.execute("UPDATE push_log SET back=1 WHERE back=0 AND ts>? AND EXISTS (SELECT 1 FROM users u WHERE u.id=push_log.user AND u.seen>push_log.ts)", (t - 2 * 86400,))
    c = _ctx(t)
    if c["hour"] not in HOURS and not only:
        return []
    day = A.push_day(t)
    if only:
        rows = q("SELECT * FROM users WHERE id=?", only)
    else:
        rows = q("""SELECT u.* FROM users u WHERE u.banned=0 AND COALESCE(u.notif,1)=1 AND u.id>0 AND u.seen>? AND u.seen<?
                    AND (SELECT COUNT(*) FROM push_log p WHERE p.user=u.id AND p.ts>=?)<?
                    AND COALESCE((SELECT MAX(ts) FROM push_log p WHERE p.user=u.id),0)<=?
                    ORDER BY u.seen DESC LIMIT 3000""", t - ACTIVE, t - QUIET, day, A.PUSH_DAY_MAX, t - A.PUSH_GAP)
    out, seen = [], 0
    for r in rows:
        uid = r["id"]
        if not only and t - _SKIP.get(uid, 0) < RECHECK:
            continue
        if seen >= SCAN or len(out) >= BATCH:
            break
        seen += 1
        u = _row(r)
        hist = q("SELECT ev, ts FROM push_log WHERE user=? AND ts>? ORDER BY id DESC LIMIT 60", uid, t - 30 * 86400)
        u["_n"] = {}
        for h in q("SELECT ev, COUNT(*) n FROM push_log WHERE user=? GROUP BY ev", uid):
            u["_n"][h["ev"]] = h["n"]
        got = pick(u, c, hist)
        if not got:
            _SKIP[uid] = t
            continue
        ev, res = got
        var = u["_n"].get(ev, 0) % len(res["texts"])
        out.append((uid, ev, res["texts"][var], res.get("card")))
    if not dry:
        for uid, ev, text, card in out:
            A.notify(uid, text, promo=ev, card=card)
        if out:
            print(f"pushes: sent {len(out)} ({', '.join(sorted({o[1] for o in out}))})", flush=True)
    if len(_SKIP) > 20000:
        _SKIP.clear()
    return out


async def _loop():
    await asyncio.sleep(70)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, run)
        except Exception as e:
            print("pushes:", type(e).__name__, e, flush=True)
        await asyncio.sleep(EVERY)


@app.on_event("startup")
async def _start():
    if not A.DEV:
        asyncio.create_task(_loop())


@app.get(R + "/admin/pushes")
def admin_pushes(days: int = 7, aid=Depends(admin)):
    """Сколько пушей ушло по каждому событию и сколько игроков после них вернулось."""
    t = now() - max(1, min(days, 90)) * 86400
    rows = q("SELECT ev, COUNT(*) n, SUM(back) back FROM push_log WHERE ts>? GROUP BY ev ORDER BY n DESC", t)
    per = q1("SELECT COUNT(*) n, COUNT(DISTINCT user) users FROM push_log WHERE ts>?", t)
    return {"days": days, "dayMax": A.PUSH_DAY_MAX, "gapHours": A.PUSH_GAP // 3600, "total": per["n"], "users": per["users"],
            "events": [{"ev": r["ev"], "title": TITLES.get(r["ev"], r["ev"]), "sent": r["n"], "back": r["back"] or 0} for r in rows]}


@app.post(R + "/admin/pushes/test")
async def admin_pushes_test(req: Request, aid=Depends(admin)):
    """Какие события подходят игроку прямо сейчас. {uid} — по умолчанию сам админ.
    {send: true, ev?, var?} — отправить ему образец пуша (мимо лимита): так админ смотрит текст и картинку у себя в Telegram."""
    b = await req.json()
    uid = int(b.get("uid") or aid)
    u = q1("SELECT * FROM users WHERE id=?", uid) or err("нет такого игрока")
    c, u = _ctx(now()), _row(u)
    u["_n"] = {}
    out = []
    for ev, prio, cd, urgent, fn in EVENTS:
        try:
            r = fn(u, c)
        except Exception as e:
            out.append({"ev": ev, "error": f"{type(e).__name__}: {e}"})
            continue
        if r:
            out.append({"ev": ev, "title": TITLES[ev], "texts": r["texts"], "card": list(r["card"])})
    sent = None
    if b.get("send"):
        ok = [o for o in out if "texts" in o and (not b.get("ev") or o["ev"] == b["ev"])]
        if not ok:
            err("это событие сейчас игроку не подходит")
        o = ok[0]
        sent = o["ev"]
        A.notify(uid, o["texts"][int(b.get("var") or 0) % len(o["texts"])], card=tuple(o["card"]), inbox=False)
    return {"uid": uid, "events": out, "sent": sent}
