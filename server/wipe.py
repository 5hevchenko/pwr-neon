"""Сезоны-вайпы: полный сброс экономики по расписанию или вручную из админки (вкладка «Вайп», kv 'wipecfg').
Сезон = время между вайпами («Сезон N», N = вайпов + 1). В начале нового сезона банк благодарит игроков: thanks_pct %
от того, что игрок внёс в банк за прошлый сезон (чистый вклад: проигрыши + комиссии − всё, что банк ему выплатил;
или — по настройке — от купленных за Telegram Stars звёзд). Игрок видит плашку при входе (wipe_thanks.seen).

Сбрасывается: баланс звёзд (до стартового), подарки (с сейфом, залогами, ссылками-подарками, лотами маркета), бизнесы,
крипта / стейкинг / фьючерсы, акции казино, ключи от кейсов, казна и банк кланов, открытые обмены и ставки в незаконченных
играх. Остаётся: уровень и опыт, профиль, титулы и рамки, друзья, рефералы, кланы (участники), боты-франшизы, история.

За freeze минут до вайпа все POST игроков закрыты (кроме админки и вебхуков ботов) — нельзя поставить старые звёзды и
забрать выигрыш уже после сброса. Перед вайпом — предупреждения всем игрокам за warn часов, после — сообщение «вайп прошёл».
"""
import asyncio
import json
import re
import time

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

import app as A
from app import R, app, db, err, esc, now, q, q1, tx
from admin import OWNERS, admin, log

# флажки: что сбрасывать (звёзды сбрасываются всегда — ради этого вайп и делается)
PARTS = {
    "gifts": "Подарки, сейф, залоги и лоты маркета",
    "biz": "Бизнесы",
    "crypto": "Крипта, стейкинг и фьючерсы",
    "shares": "Акции казино",
    "loans": "Кредиты — долги списываются, кредитная история с нуля",
    "keys": "Ключи от кейсов",
    "clans": "Казна и банк кланов",
    "bank": "Банк казино — к стартовому резерву (и акции, и дивиденды с нуля)",
}
BASES = {"bank": "чистый вклад в банк (проигрыши и комиссии − выплаты банка)", "buy": "купленные звёзды (Telegram Stars)"}
DEFAULTS = {"on": False, "next": 0, "days": 14, "start": A.START_STARS, "freeze": 5, "warn": [24, 1], "warned": [],
            "thanks_pct": 10, "thanks_base": "bank", "thanks_cap": 0, "deny": [], **{k: True for k in PARTS}}
CFG = dict(DEFAULTS)
STATE = {"running": False}

db.executescript("""
CREATE TABLE IF NOT EXISTS wipe_log(id INTEGER PRIMARY KEY, ts INTEGER, by INTEGER, stats TEXT);
CREATE TABLE IF NOT EXISTS wipe_thanks(wipe INTEGER, user INTEGER, base INTEGER, amount INTEGER, seen INTEGER DEFAULT 0,
                                       PRIMARY KEY(wipe, user));
""")
try:
    db.execute("ALTER TABLE wipe_thanks ADD COLUMN stats TEXT DEFAULT '{}'")
except Exception:
    pass
try:
    db.execute("ALTER TABLE wipe_thanks ADD COLUMN bad INTEGER DEFAULT 0")   # 1 — без благодарности: багоюзер (список deny)
except Exception:
    pass



def nf(x):
    return f"{int(x):,}".replace(",", " ")


def _load():
    try:
        CFG.update({k: v for k, v in json.loads(A.kv_get("wipecfg", "{}") or "{}").items() if k in DEFAULTS})
    except Exception as e:
        print("wipecfg:", e, flush=True)


_load()


def _save():
    with A.LOCK:
        db.execute("INSERT INTO kv(k,v) VALUES('wipecfg',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(CFG),))


def frozen():
    if STATE["running"]:
        return True
    return bool(CFG["on"] and CFG["next"] and now() >= CFG["next"] - CFG["freeze"] * 60)


def season_no():
    return q1("SELECT COUNT(*) n FROM wipe_log")["n"] + 1


def last_wipe():
    return q1("SELECT COALESCE(MAX(ts),0) t FROM wipe_log")["t"]


def thanks_calc(since, until):
    """{игрок: (база, благодарность)} за сезон [since, until)."""
    import bank
    if CFG["thanks_base"] == "buy":
        rows = q("SELECT user, SUM(stars) s FROM payments WHERE ts>=? AND ts<? AND stars>0 GROUP BY user", since, until)
    else:
        rows = q(f"SELECT user, -SUM(delta) s FROM events WHERE ({bank.BANK_KINDS}) AND user>0 AND ts>=? AND ts<? GROUP BY user", since, until)
    out, pct, cap = {}, CFG["thanks_pct"], int(CFG["thanks_cap"] or 0)
    for r in rows:
        if r["s"] and r["s"] > 0:
            a = int(r["s"] * pct / 100)
            out[r["user"]] = (int(r["s"]), min(a, cap) if cap else a)
    return out


def season_stats(since, until):
    """Итоги сезона каждого игрока для письма: часы в игре (5-минутки с действиями), раунды, выиграно/проиграно в играх,
    заработано/потрачено всего, лучший выигрыш, любимые игры."""
    from live import NAMES
    w = (since, until)
    out = {}
    get = lambda u: out.setdefault(u, {"hours": 0, "rounds": 0, "won": 0, "lost": 0, "earned": 0, "spent": 0, "best": 0, "bestGame": "", "games": []})
    for r in q("SELECT user, COUNT(DISTINCT ts/300) n FROM events WHERE ts>=? AND ts<? AND kind NOT IN ('wipe','thanks') GROUP BY user", *w):
        get(r["user"])["hours"] = round(r["n"] * 5 / 60, 1)
    for r in q("SELECT user, SUM(CASE WHEN delta>0 THEN delta ELSE 0 END) p, SUM(CASE WHEN delta<0 THEN -delta ELSE 0 END) m FROM events "
               "WHERE ts>=? AND ts<? AND kind NOT IN ('wipe','thanks') GROUP BY user", *w):
        x = get(r["user"]); x["earned"], x["spent"] = r["p"] or 0, r["m"] or 0
    for r in q(f"SELECT user, kind, COUNT(*) n, SUM(CASE WHEN delta>0 THEN delta ELSE 0 END) p, SUM(CASE WHEN delta<0 THEN -delta ELSE 0 END) m, "
               f"MAX(delta) mx FROM events WHERE kind IN {A.GAME_KINDS} AND ts>=? AND ts<? GROUP BY user, kind", *w):
        x = get(r["user"])
        x["rounds"] += r["n"]; x["won"] += r["p"] or 0; x["lost"] += r["m"] or 0
        x["games"].append([NAMES.get(r["kind"], r["kind"]), r["n"]])
        if (r["mx"] or 0) > x["best"]:
            x["best"], x["bestGame"] = r["mx"], NAMES.get(r["kind"], r["kind"])
    for x in out.values():
        x["games"] = sorted(x["games"], key=lambda g: -g[1])[:4]
    return out


def public(uid):
    """Для /me: следующий вайп (отсчёт на главной) и непоказанная плашка «благодарность банка» нового сезона."""
    out = {"season": season_no()}
    if CFG["on"] and CFG["next"]:
        out.update(next=CFG["next"], start=CFG["start"], frozen=frozen())
    t = q1("SELECT t.*, w.ts FROM wipe_thanks t JOIN wipe_log w ON w.id=t.wipe WHERE t.user=? AND t.seen=0 ORDER BY t.wipe DESC LIMIT 1", uid)
    if t:
        u = q1("SELECT name FROM users WHERE id=?", uid)
        out["thanks"] = {"wipe": t["wipe"], "ended": t["wipe"], "season": t["wipe"] + 1, "base": t["base"], "amount": t["amount"],
                         "kind": CFG["thanks_base"], "pct": CFG["thanks_pct"], "start": CFG["start"], "name": u["name"] if u else "",
                         "stats": json.loads(t["stats"] or "{}"), "days": CFG["days"], "bad": bool(t["bad"]),
                         "next": CFG["next"] if CFG["on"] else 0, "from": q1("SELECT COALESCE(MAX(ts),0) t FROM wipe_log WHERE id<?", t["wipe"])["t"],
                         "to": t["ts"]}
    return out


_OPEN = re.compile(r"^" + re.escape(R) + r"/(admin/|tg/)")


@app.middleware("http")
async def _wipe_gate(request: Request, call_next):
    if request.method == "POST" and frozen() and not _OPEN.match(request.url.path):
        return JSONResponse({"detail": "Идёт вайп — игра откроется через пару минут"}, status_code=503)
    return await call_next(request)


def _stats():
    return {"players": q1("SELECT COUNT(*) n FROM users")["n"],
            "stars": q1("SELECT COALESCE(SUM(stars),0) s FROM users")["s"],
            "gifts": q1("SELECT COUNT(*) n FROM gifts")["n"],
            "biz": q1("SELECT COUNT(*) n FROM biz")["n"],
            "treasury": q1("SELECT COALESCE(SUM(treasury+bank),0) s FROM clans")["s"]}


def _do_wipe(by):
    """Сам сброс — одной транзакцией. Возвращает статистику «до»."""
    st, t, start = _stats(), now(), int(CFG["start"])
    A.CR["bets"].clear()   # ставки текущего раунда краша сгорают (вывод после сброса дал бы новые звёзды)
    with tx():
        thanks = thanks_calc(last_wipe(), t + 1) if CFG["thanks_pct"] > 0 else {}
        stats = season_stats(last_wipe(), t + 1)
        st["thanks"] = sum(a for _, a in thanks.values())
        st["season"] = season_no()
        since = last_wipe()
        wid = db.execute("INSERT INTO wipe_log(ts,by,stats) VALUES(?,?,?)", (t, by, "{}")).lastrowid
        import legacy
        legacy.capture(wid, st["season"], since, t, stats, set(CFG["deny"]))   # до удаления подарков: итоги сезона остаются в профиле навсегда
        for r in q("SELECT id, stars FROM users WHERE stars!=?", start):
            A.event(r["id"], "wipe", start - r["stars"])
        db.execute("UPDATE users SET stars=?, inc_ts=?", (start, t))
        # незаконченные игры и сделки — всегда (в них заморожены старые звёзды и подарки)
        db.execute("DELETE FROM safe_game")
        db.execute("DELETE FROM ladder_game")
        db.execute("DELETE FROM cr_bet")
        db.execute("DELETE FROM bb_bet")
        db.execute("DELETE FROM fc_bet")   # и рынки: линии и итоги нового сезона считаются заново
        db.execute("DELETE FROM fc_market")
        db.execute("DELETE FROM fc_stat")
        db.execute("DELETE FROM deposits")
        db.execute("UPDATE auction SET done=1 WHERE done=0")
        db.execute("UPDATE cheques SET refunded=1 WHERE claimed_by=0 AND refunded=0")   # старые чеки не переносят звёзды в новый сезон
        db.execute("DELETE FROM bigwins")
        for tb in ("mines", "tower", "chicken", "hilo", "bj", "pump", "fish", "penalty"):
            db.execute(f"DELETE FROM {tb}")
        db.execute("UPDATE trades SET status='cancelled' WHERE status='open'")
        db.execute("UPDATE rooms SET status='cancelled' WHERE status NOT IN ('done','cancelled')")
        db.execute("UPDATE duels SET status='cancelled' WHERE status NOT IN ('done','cancelled','declined','expired')")
        db.execute("UPDATE battles SET status='cancelled' WHERE status NOT IN ('done','cancelled')")
        db.execute("DELETE FROM jr_bets WHERE round IN (SELECT id FROM jr_rounds WHERE status='open')")
        db.execute("UPDATE jr_rounds SET status='cancelled' WHERE status='open'")
        db.execute("DELETE FROM sf_bets WHERE round IN (SELECT id FROM sf_rounds WHERE status='open')")
        db.execute("UPDATE sf_rounds SET status='cancelled' WHERE status='open'")
        db.execute("DELETE FROM jp_tickets WHERE day>=?", (A.day_start(),))
        if CFG["gifts"]:
            db.execute("DELETE FROM gifts")
            db.execute("DELETE FROM feed")
            db.execute("DELETE FROM sales")
            db.execute("DELETE FROM vault")
            db.execute("DELETE FROM bank_vault")   # проигранные в апгрейде подарки: иначе они вернутся в новый сезон через аукцион и апгрейд
            db.execute("UPDATE gift_links SET status='cancelled' WHERE status='open'")
        if CFG["loans"]:
            db.execute("DELETE FROM loans")   # и долги, и история: рейтинг тоже с нуля
            db.execute("DELETE FROM credit")
        elif CFG["gifts"]:
            db.execute("DELETE FROM loans WHERE status='open' AND gift IS NOT NULL")   # залоги исчезли вместе с подарками
        if CFG["biz"]:
            db.execute("DELETE FROM biz")
            if not CFG["loans"]:
                db.execute("UPDATE loans SET status='cancelled', closed=? WHERE status='open' AND biz IS NOT NULL", (t,))
            db.execute("DELETE FROM biz_mgr")
        if CFG["crypto"]:
            db.execute("DELETE FROM crypto")
            db.execute("DELETE FROM crypto_stake")
            db.execute("UPDATE crypto_pos SET status='closed', close=entry, pnl=0, closed=? WHERE status='open'", (t,))
        if CFG["shares"]:
            db.execute("DELETE FROM shares")
        if CFG["keys"]:
            db.execute("DELETE FROM case_keys")
        if CFG["clans"]:
            db.execute("DELETE FROM clan_biz")
            import clans as C
            for c in q("SELECT * FROM clans"):   # места за уровень остаются купленными — иначе состав больше лимита (30/25)
                db.execute("UPDATE clans SET slots=? WHERE id=?", (max(C.cap(c), q1("SELECT COUNT(*) n FROM clan_members WHERE clan=?", c["id"])["n"]), c["id"]))
            db.execute("UPDATE clans SET treasury=0, bank=0")
        if CFG["bank"]:
            db.execute("INSERT INTO kv(k,v) VALUES('bank_from',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(t),))
            db.execute("DELETE FROM shares")
            db.execute("DELETE FROM clan_shares")
            db.execute("DELETE FROM bank_saviors")
            db.execute("DELETE FROM bank_recycled")
            db.execute("UPDATE crisis_log SET end=? WHERE end=0", (t,))
        # благодарность банка — уже после сброса, платит банк нового сезона (kind thanks входит в BANK_KINDS)
        deny = set(CFG["deny"])
        for r in q("SELECT id FROM users WHERE banned=0"):
            base, amount = thanks.get(r["id"], (0, 0))
            bad = r["id"] in deny
            if bad:
                st["thanks"] -= amount
                amount = 0
            db.execute("INSERT OR REPLACE INTO wipe_thanks(wipe,user,base,amount,seen,stats,bad) VALUES(?,?,?,?,0,?,?)",
                       (wid, r["id"], base, amount, json.dumps(stats.get(r["id"], {}), ensure_ascii=False), int(bad)))
            if amount > 0:
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, r["id"]))
                A.event(r["id"], "thanks", amount)
        db.execute("UPDATE wipe_log SET stats=? WHERE id=?", (json.dumps(st), wid))
        CFG["deny"] = []   # список «без благодарности» — только на один вайп
        db.execute("INSERT INTO kv(k,v) VALUES('wipecfg',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(CFG),))
        log(by, "wipe", None, f"сезон {st['season']}: игроков {st['players']}, звёзд {st['stars']}, подарков {st['gifts']}, "
                              f"бизнесов {st['biz']}, благодарность {st['thanks']}")
    try:
        import bank
        import clans
        bank._BV["ts"] = 0
        bank._FK["ts"] = 0
        clans.refresh_tax()
    except Exception as e:
        print("wipe after:", e, flush=True)
    return st


def _kept():
    gone = ["звёзды"] + [PARTS[k].lower() for k in PARTS if CFG[k]]
    return ", ".join(gone)


async def _mass(text):
    """Всем игрокам: во «входящие» + в бота (через бота игрока, без флуда — ~20 сообщений/с). text — строка или uid → строка."""
    fr = __import__("franchise")
    ids = [r["id"] for r in q("SELECT id FROM users WHERE banned=0")]
    txt = text if callable(text) else (lambda _u: text)
    msgs = {u: txt(u) for u in ids}
    with tx():
        db.executemany("INSERT INTO inbox(user,text,ts) VALUES(?,?,?)", [(u, re.sub(r"<[^>]+>", "", msgs[u]), now()) for u in ids])
    kb = {"inline_keyboard": [[{"text": "Открыть", "web_app": {"url": A.APP_URL}}]]}
    for uid in ids:
        text = msgs[uid]
        try:
            tok = fr.token_for(uid)
            r = await A.tg_call("sendMessage", _token=tok, chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb)
            if not r.get("ok") and tok != A.TOKEN:
                await A.tg_call("sendMessage", _token=A.TOKEN, chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            print("wipe msg", uid, e, flush=True)
        await asyncio.sleep(0.05)


def _when(ts):
    return time.strftime("%d.%m в %H:%M", time.gmtime(ts + 3 * 3600)) + " МСК"


def _left(h):
    return "сутки" if h == 24 else f"{h} ч" if h < 24 or h % 24 else f"{h // 24} дн."


async def _run(by):
    STATE["running"] = True
    try:
        await asyncio.sleep(3)   # запросы, начатые до заморозки, успевают закончиться
        st = await asyncio.get_running_loop().run_in_executor(None, _do_wipe, by)
        print("wipe done", st, flush=True)
    finally:
        STATE["running"] = False
    nxt = CFG["next"] if CFG["on"] and CFG["next"] > now() else 0
    wid = q1("SELECT MAX(id) i FROM wipe_log")["i"]
    rows = {r["user"]: r for r in q("SELECT t.user, t.amount, t.stats, t.bad, u.name FROM wipe_thanks t JOIN users u ON u.id=t.user WHERE t.wipe=?", wid)}
    every = f"Вайп — раз в {CFG['days']} дн." if CFG["days"] else ""

    def letter(uid):
        r = rows.get(uid)
        x = json.loads(r["stats"] or "{}") if r else {}
        head = f"✉️ <b>Дорогой друг, {esc(r['name'])}!</b>\n\nСезон {wid} завершён — спасибо, что играл с нами." if r else \
            f"🧹 <b>Сезон {wid + 1} начался — вайп прошёл!</b>"
        st = ""
        if x.get("rounds") or x.get("hours"):
            fav = ", ".join(g[0] for g in x.get("games", [])[:3])
            st = (f"\n\n📊 <b>Твой сезон:</b>\n⏱ В игре: ~{f"{x['hours']:g}".replace('.', ',')} ч\n🎲 Раундов: {nf(x['rounds'])}"
                  f"\n📈 Заработал: +{nf(x['earned'])} ⭐\n📉 Потратил: −{nf(x['spent'])} ⭐"
                  + (f"\n🏆 Лучший выигрыш: +{nf(x['best'])} ⭐ ({esc(x['bestGame'])})" if x.get("best") else "")
                  + (f"\n❤️ Любимые игры: {esc(fav)}" if fav else ""))
        th = "\n\n🚫 <b>Благодарность банка: 0 ⭐.</b> Ты себя плохо вёл — багоюзер. В новом сезоне играй честно." if r and r["bad"] else \
            f"\n\n🏦 <b>Банк благодарит тебя: +{nf(r['amount'])} ⭐</b> — {str(CFG['thanks_pct']).replace('.', ',')}% от того, что ты внёс в банк. Уже на балансе!" \
            if r and r["amount"] > 0 else ""
        return (head + st + th + f"\n\n🧹 Сезон {wid + 1} начался: всё сброшено, уровень сохранён, старт — <b>{nf(int(CFG['start']))} ⭐</b>."
                + (f"\n{every}" if every else "") + (f" Следующий — {_when(nxt)}." if nxt else ""))
    await _mass(letter)


PART_LINES = {"gifts": "подарки, сейф и залоги", "biz": "бизнесы", "crypto": "крипта, стейкинг и фьючерсы",
              "shares": "акции казино", "bank": "банк казино", "loans": "кредиты — долги спишутся, кредитная история с нуля", "keys": "ключи от кейсов", "clans": "казна кланов"}


def announce_text():
    """Объявление о сезонах со всеми условиями — из текущих настроек (кнопка в админке)."""
    c = CFG
    gone = [f"звёзды — у всех станет <b>{nf(int(c['start']))} ⭐</b>"] + [PART_LINES[k] for k in PART_LINES if c.get(k)]
    every = f"сезон длится <b>{c['days']} дней</b>" if c["days"] else "сезон длится до следующего вайпа"
    th = (f"\n\n🏦 <b>Благодарность от банка</b>\nВ начале нового сезона банк вернёт каждому <b>{str(c['thanks_pct']).replace('.', ',')}%</b> от того, "
          + ("сколько звёзд он купил за сезон." if c["thanks_base"] == "buy" else "что он внёс в банк за сезон (проигрыши и комиссии минус выплаты банка).")
          + (f" Не больше {nf(int(c['thanks_cap']))} ⭐ одному." if c["thanks_cap"] else "")
          + "\nЗвёзды сразу придут на баланс, а в игре будет ждать письмо с итогами твоего сезона: часы в игре, раунды, "
            "сколько заработал и потратил, любимые игры и лучший выигрыш.") if c["thanks_pct"] > 0 else ""
    warn = " и за ".join(_left(h) for h in sorted(c["warn"], reverse=True))
    return (f"🏆 <b>В GiftBot приходят сезоны!</b>\n\n"
            f"Вы проголосовали — и мы решили. Теперь {every}, а в конце каждого — <b>вайп</b>: полный сброс экономики "
            f"и равный старт для всех.\n\n"
            + (f"📅 <b>Ближайший вайп — {_when(c['next'])}</b>" + (f", дальше — раз в {c['days']} дней." if c["days"] else ".") if c["on"] and c["next"] else "")
            + "\n\n🧹 <b>Что сбросится:</b>\n" + "\n".join("• " + x for x in gone)
            + "\n\n⭐ <b>Что останется:</b>\n• уровень и опыт\n• профиль, титулы и рамки\n• друзья, рефералы и клан"
            + th
            + (f"\n\n⏰ Предупредим за {warn} до вайпа. За {c['freeze']} мин до него игры закроются — "
               "незаконченные ставки и обмены отменятся.")
            + "\n\nУдачи в сезоне! 🍀")


async def wipe_loop():
    await asyncio.sleep(40)
    while True:
        try:
            if A.kv_get("wipe_ann"):   # разослать объявление (кнопка в админке)
                with A.LOCK:
                    db.execute("DELETE FROM kv WHERE k='wipe_ann'")
                await _mass(announce_text())
            c, t = CFG, now()
            if c["on"] and c["next"] and not STATE["running"]:
                if t >= c["next"]:
                    nxt = c["next"] + c["days"] * 86400 if c["days"] else 0
                    while nxt and nxt <= t + 3600:
                        nxt += c["days"] * 86400
                    c["next"] = nxt
                    c["warned"] = []
                    _save()
                    await _run(0)
                else:
                    warned = set(c.get("warned") or [])
                    for h in sorted(c["warn"], reverse=True):
                        if h not in warned and t >= c["next"] - h * 3600:
                            warned.update(x for x in c["warn"] if x >= h)   # сразу закрываем и более ранние (их время прошло)
                            c["warned"] = sorted(warned)
                            _save()
                            await _mass(f"⚠️ <b>Через {_left(h)} — вайп</b> ({_when(c['next'])}).\n"
                                        + (f"Вайпы — раз в {c['days']} дн.\n" if c["days"] else "") + "\n"
                                        + f"Сбросятся {esc(_kept())}. Уровень останется. После вайпа у всех будет "
                                        f"<b>{nf(int(c['start']))} ⭐</b>"
                                        + (f" + благодарность банка: {c['thanks_pct']}% от того, что ты внёс в банк за сезон" if c["thanks_pct"] > 0 else "")
                                        + f".\n\nЗа {c['freeze']} мин до вайпа игры закроются.")
                            break
        except Exception as e:
            print("wipe loop:", e, flush=True)
        await asyncio.sleep(20)


@app.on_event("startup")
async def _wipe_start():
    asyncio.create_task(wipe_loop())


# ============================== админка ==============================
@app.get(R + "/admin/wipe")
def admin_wipe(aid=Depends(admin)):
    last = [{"ts": r["ts"], "by": r["by"], **json.loads(r["stats"])} for r in q("SELECT * FROM wipe_log ORDER BY id DESC LIMIT 5")]
    th = {u: v for u, v in thanks_calc(last_wipe(), now() + 1).items() if u not in set(CFG["deny"])}
    top = sorted(th.items(), key=lambda x: -x[1][1])[:5]
    deny = [{**A.user_brief(u), "id": u["id"]} for u in (q1("SELECT * FROM users WHERE id=?", i) for i in CFG["deny"]) if u]
    return {"cfg": {k: CFG[k] for k in DEFAULTS if k != "warned"}, "parts": PARTS, "bases": BASES, "now": _stats(), "last": last,
            "canEdit": aid in OWNERS, "frozen": frozen(), "running": STATE["running"], "season": season_no(), "since": last_wipe(), "deny": deny,
            "thanks": {"players": len(th), "total": sum(a for _, a in th.values()),
                       "top": [{**A.user_brief(r), "base": b, "amount": a} for u, (b, a) in top for r in [q1("SELECT * FROM users WHERE id=?", u)] if r]}}


@app.post(R + "/admin/wipe")
async def admin_wipe_set(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Настраивать вайп может только владелец")
    b = await req.json()
    if not isinstance(b, dict):
        err("неверные данные")
    new = dict(CFG)
    try:
        if "on" in b:
            new["on"] = bool(b["on"])
        if "next" in b:   # timestamp UTC (фронт переводит из МСК)
            new["next"] = int(b["next"] or 0)
        if "days" in b:
            new["days"] = int(b["days"])
        if "start" in b:
            new["start"] = int(b["start"])
        if "freeze" in b:
            new["freeze"] = int(b["freeze"])
        if "warn" in b:
            w = b["warn"]
            w = [int(x) for x in (re.split(r"[ ,;]+", w.strip()) if isinstance(w, str) else w) if str(x).strip()]
            new["warn"] = sorted(set(w), reverse=True)
        for k in PARTS:
            if k in b:
                new[k] = bool(b[k])
        if "thanks_pct" in b:
            new["thanks_pct"] = float(str(b["thanks_pct"]).replace(",", "."))
        if "thanks_cap" in b:
            new["thanks_cap"] = int(b["thanks_cap"] or 0)
        if "deny" in b:
            d = b["deny"]
            new["deny"] = sorted({int(x) for x in (re.split(r"[ ,;]+", d.strip()) if isinstance(d, str) else d) if str(x).strip()})
        if "thanks_base" in b:
            new["thanks_base"] = str(b["thanks_base"])
    except (TypeError, ValueError):
        err("проверь числа")
    if not 0 <= new["days"] <= 365:
        err("период — от 0 (только вручную) до 365 дней")
    if not 0 <= new["start"] <= 10_000_000:
        err("стартовый баланс — до 10 000 000 ⭐")
    if not 0 <= new["thanks_pct"] <= 100:
        err("благодарность — от 0 до 100%")
    if new["thanks_base"] not in BASES or new["thanks_cap"] < 0:
        err("неверная база благодарности")
    if not 1 <= new["freeze"] <= 60:
        err("заморозка — от 1 до 60 минут")
    if any(not 1 <= h <= 168 for h in new["warn"]) or len(new["warn"]) > 5:
        err("предупреждения — до 5 значений, от 1 до 168 часов")
    if new["on"] and new["next"] and new["next"] < now() + new["freeze"] * 60 + 60:
        err("дата вайпа должна быть в будущем (позже, чем через время заморозки)")
    if new["on"] and not new["next"]:
        err("укажи дату вайпа")
    if new["next"] != CFG["next"]:
        new["warned"] = [h for h in new["warn"] if new["next"] - h * 3600 <= now()]   # прошедшие предупреждения не шлём задним числом
    CFG.update(new)
    _save()
    with tx():
        log(aid, "wipecfg", None, ", ".join(f"{k}={new[k]}" for k in DEFAULTS if k != "warned"))
    return {"ok": True}


@app.post(R + "/admin/wipe/now")
async def admin_wipe_now(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Вайп может запустить только владелец")
    if str((await req.json()).get("confirm", "")).strip().upper() != "ВАЙП":
        err("для подтверждения введи слово ВАЙП")
    if STATE["running"]:
        err("вайп уже идёт")
    if CFG["on"] and CFG["days"]:   # ручной вайп — расписание сдвигается: следующий через days дней от сегодня, в 12:00 МСК
        d = (now() + 10800) // 86400 * 86400 - 10800 + 12 * 3600 + CFG["days"] * 86400
        CFG.update(next=d, warned=[])
        _save()
    asyncio.create_task(_run(aid))
    return {"ok": True}


@app.post(R + "/wipe/seen")
async def wipe_seen(req: Request, uid=Depends(A.auth)):
    w = int((await req.json()).get("wipe", 0))
    with tx():
        db.execute("UPDATE wipe_thanks SET seen=1 WHERE user=? AND wipe<=?", (uid, w))
    return {"ok": True}


@app.post(R + "/admin/wipe/announce")
def admin_wipe_announce(aid=Depends(admin)):
    if aid not in OWNERS:
        err("Рассылать может только владелец")
    with tx():
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('wipe_ann','1')")
        log(aid, "wipe_announce", None, "объявление о сезонах")
    return {"ok": True}


@app.get(R + "/admin/wipe/announce")
def admin_wipe_announce_preview(aid=Depends(admin)):
    return {"text": announce_text()}
