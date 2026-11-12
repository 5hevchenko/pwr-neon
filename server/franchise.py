"""Франшиза: игрок одной кнопкой создаёт своего бота (Telegram Managed Bots, Bot API 9.6+), бот сразу открывает эту же игру.

База, баланс, подарки, кланы — общие: id игрока в Telegram один во всех ботах.
- главный бот (BOT_TOKEN) — менеджер: в @BotFather → Mini App → включить управление ботами (can_manage_bots);
- кнопка request_managed_bot (/franchise) или ссылка t.me/newbot/<главный> → апдейт managed_bot → getManagedBotToken
  → вебхук R/tg/<id> с секретом + кнопка «Играть» на этот же APP_URL;
- вход из дочернего бота: initData проверяем Ed25519-подписью Telegram (поле signature), НЕ токеном —
  токен знает владелец бота и мог бы подделать вход за любого игрока общей базы;
- владелец бота может подменить Mini App и снять настоящую initData своих игроков. Ограничений в дочерних ботах нет
  (решение владельца игры: удобство важнее) — вместо них сторож раз в 3 минуты сверяет вебхук и кнопку «Играть» и при подмене
  отключает бота (все входы через него — 403), а actlog пишет bot у каждого действия — для отката;
- оплата Telegram Stars, код сброса PIN — только главным ботом (дочерний мог бы переслать себе сообщение по message_id);
- награды владельцу, каждая один раз на аккаунт: create_reward — за создание бота (если сам владелец не ниже create_level:
  иначе любой твинк создаёт бота в один тап и забирает звёзды; дорастёт — получит), reward — когда бот приведёт N игроков нужного уровня.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.parse

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from settings import conf
import app as A
from app import (ADMINS, APP_URL, BOT_NAME, CUR_TOKEN, R, STEALTH, TOKEN, VIA_BOT, app, db, err, esc, event, notify, now, q, q1, tg_call, tx)
from admin import OWNERS, admin, log


def nf(x):
    """12 345 — разделитель тысяч только в самом числе (замена по всей строке портила запятые в тексте и именах)."""
    return f"{x:,}".replace(",", " ")

# настройки — в админке («Боты»), хранятся в kv 'frcfg'; settings.toml [franchise] — только значения по умолчанию
DEFAULTS = {
    "on": True,                                          # франшиза включена: кнопка в игре, /franchise, подключение новых ботов
    "create_reward": 25000,                              # ⭐ сразу за создание бота (один раз на аккаунт)…
    "create_level": 5,                                   # …если владелец сам не ниже этого уровня (иначе — когда дорастёт)
    "reward": conf("franchise.reward", 25000),           # ⭐ владельцу, один раз на аккаунт…
    "players": conf("franchise.reward_players", 10),     # …когда бот приведёт столько новых игроков…
    "level": conf("franchise.reward_level", 5),          # …не ниже этого уровня
    "cut_pct": 0.5,                                      # % КАЖДОМУ владельцу бота и админу от всего дохода игры (игры + налоги и комиссии), каждую минуту, без потолка (решение владельца игры)
    "cap_on": False,                                     # общий потолок: всем получателям вместе не больше cap_pct %…
    "cap_pct": 10.0,                                     # …дохода игры (сверх — делится поровну)
    "max_per_owner": conf("franchise.max_per_owner", 5),  # сверх — бот создан в Telegram, но игра его не подключает
    "game_promo": True,                                  # баннер на главной в игре
    "bot_promo": True,                                   # бот сам предлагает игрокам создать франшизу…
    "promo_days": 30,                                    # …не чаще раза в N дней одному игроку…
    "promo_level": 3,                                    # …и только с этого уровня (новичкам рано)
}
LIMITS = {"cap_pct": (0.1, 100), "cut_pct": (0, 20), "create_reward": (0, 1_000_000), "create_level": (1, 100), "reward": (0, 1_000_000), "players": (1, 1000), "level": (1, 100), "max_per_owner": (1, 50),
          "promo_days": (1, 365), "promo_level": (1, 100)}
CFG = {}
try:
    CFG.update({k: v for k, v in json.loads(A.kv_get("frcfg", "{}")).items() if k in DEFAULTS})
except Exception:
    pass


def cfg(k):
    return CFG.get(k, DEFAULTS[k])


MAX_AGE = conf("franchise.max_age_hours", 24) * 3600    # срок initData из дочернего бота (у главного — 7 дней)
# публичный ключ Telegram для initData.signature (core.telegram.org/bots/webapps, production); TG_PUBKEY — для тестов
PUBKEY = os.environ.get("TG_PUBKEY", "e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d")

db.executescript("""
CREATE TABLE IF NOT EXISTS bots(id INTEGER PRIMARY KEY, username TEXT, name TEXT, token TEXT, owner INTEGER,
  secret TEXT, status TEXT DEFAULT 'on', created INTEGER, paid INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS bots_owner ON bots(owner);
CREATE TABLE IF NOT EXISTS fr_acc(owner INTEGER PRIMARY KEY, frac REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS fr_cut(day INTEGER, bot INTEGER, income INTEGER, amount INTEGER, PRIMARY KEY(day, bot));
CREATE TABLE IF NOT EXISTS fr_create(owner INTEGER PRIMARY KEY, bot INTEGER, amount INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS fr_promo(user INTEGER PRIMARY KEY, ts INTEGER, n INTEGER DEFAULT 1);
""")
for _c in ("bot", "came_bot"):   # bot — через какого бота игрок заходил последним (уведомления, ссылки); came_bot — откуда пришёл
    try:
        db.execute(f"ALTER TABLE users ADD COLUMN {_c} INTEGER DEFAULT 0")
    except Exception:
        pass
db.execute("CREATE INDEX IF NOT EXISTS users_came_bot ON users(came_bot) WHERE came_bot!=0")
try:   # photo=1 — аватарку главного бота уже ставили (один раз: свою аватарку владельца не перезаписываем)
    db.execute("ALTER TABLE bots ADD COLUMN photo INTEGER DEFAULT 0")
except Exception:
    pass

BOTS = {r["id"]: dict(r) for r in db.execute("SELECT * FROM bots")}
BOT_OF = {r[0]: r[1] for r in db.execute("SELECT id, bot FROM users WHERE bot!=0")}
_KEY = None
CAN_MANAGE = {"on": bool(BOTS)}   # главный бот — менеджер (getMe при старте); пока нет — кнопку в игре не показываем
_CACHE = {}   # hash initData → (bot, data): Ed25519 по всем ботам считаем один раз на сессию


def _key():
    global _KEY
    if _KEY is None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        _KEY = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBKEY))
    return _KEY


def active(bid):
    b = BOTS.get(bid)
    return b if b and b["status"] == "on" else None


def username(bid):
    b = active(bid)
    return b["username"] if b else face_name()


# ---------- «главный» бот, назначаемый в админке (kv 'mainbot') ----------
# face — лицо игры: ссылки по умолчанию, «играй в @…». Можно любой работающий бот.
# pay — через какого бота выставляются счета Telegram Stars: ТОЛЬКО бот админа (настоящие звёзды копятся у владельца бота
#       в @BotFather — бот игрока вывел бы выручку себе). Создание франшиз (Bot Management) и опрос getUpdates
#       навсегда остаются за исходным ботом из .env. pay_ok — все боты, когда-либо назначенные для оплат: по их старым счетам
#       ещё могут прийти платежи; у остальных дочерних ботов pre_checkout отклоняем (владелец знает токен и мог бы
#       выставить «наш» счёт сам себе).
MAIN = {"face": 0, "pay": 0, "pay_ok": []}
try:
    MAIN.update(json.loads(A.kv_get("mainbot", "{}") or "{}"))
except Exception as e:
    print("mainbot:", e, flush=True)


def face_name():
    b = active(MAIN["face"])
    return b["username"] if b else BOT_NAME


def can_pay(bid):
    b = BOTS.get(bid)
    return bool(b and b["owner"] in ADMINS)


def pay_bot():
    b = active(MAIN["pay"])
    return b if b and can_pay(b["id"]) else None


def pay_token():
    b = pay_bot()
    return b["token"] if b else TOKEN


def pay_allowed(bid):
    return bid in MAIN["pay_ok"] and can_pay(bid)


def token_for(uid):
    """Токен бота, через которого игрок играет сейчас (им и пишем); отключённый/неизвестный — главный."""
    b = active(BOT_OF.get(uid, 0))
    return b["token"] if b else TOKEN


def verify(init):
    """initData → (bot, data): bot 0 — главный (HMAC токеном), иначе id дочернего (подпись Telegram). Неверная — None."""
    if not init:
        return None
    hit = _CACHE.get(init)
    if hit:   # срок проверяем и для кэша — иначе сессия жила бы, пока кэш не переполнится
        return hit if now() - hit[2] <= (MAX_AGE if hit[0] else 7 * 86400) else None
    data = dict(urllib.parse.parse_qsl(init, keep_blank_values=True))
    h = data.pop("hash", None)
    if not h:
        return None
    ad = int(data.get("auth_date", 0) or 0) if str(data.get("auth_date", "")).isdigit() else 0
    age = now() - ad
    dcs = "\n".join(f"{k}={data[k]}" for k in sorted(data))   # для HMAC — все поля, кроме hash (signature тоже)
    sig = data.pop("signature", None)
    res = None
    if hmac.compare_digest(hmac.new(A.SECRET, dcs.encode(), hashlib.sha256).hexdigest(), h):
        if age <= 7 * 86400:
            res = (0, data, ad)
    elif sig and BOTS:
        try:
            raw = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        except Exception:
            return None
        dcs = "\n".join(f"{k}={data[k]}" for k in sorted(data))   # для Ed25519 — без hash и signature
        for bid in list(BOTS):
            try:
                _key().verify(raw, f"{bid}:WebAppData\n{dcs}".encode())
            except Exception:
                continue
            if age <= MAX_AGE:
                res = (bid, data, ad)
            break
    if res:
        if len(_CACHE) > 20000:
            _CACHE.clear()
        _CACHE[init] = res
    return res   # (bot, data, auth_date)


@app.middleware("http")
async def _via_bot(request: Request, call_next):
    """Через какого бота пришёл запрос — в VIA_BOT (контекст доходит до эндпоинта и loans.stars_locked)."""
    init = request.headers.get("x-init-data")
    if init and BOTS:
        v = verify(init)
        if v and v[0]:
            if not active(v[0]):
                return JSONResponse({"detail": f"Этот бот отключён — играй в @{face_name()}"}, status_code=403)
            VIA_BOT.set(v[0])
    return await call_next(request)


def seen_via(uid, bid):
    """Из auth: запомнить, через какого бота игрок играет (уведомления пойдут им)."""
    if BOT_OF.get(uid, 0) != bid:
        with A.LOCK:
            db.execute("UPDATE users SET bot=? WHERE id=?", (bid, uid))
        if bid:
            BOT_OF[uid] = bid
        else:
            BOT_OF.pop(uid, None)


# ============================== создание и настройка ботов ==============================
AVATAR = os.path.join(os.path.dirname(os.path.abspath(A.DB_PATH)), "franchise_avatar.jpg")   # аватарка главного бота (кэш)


async def _main_avatar():
    """JPG аватарки главного бота: из кэша или getUserProfilePhotos → getFile → скачать."""
    if os.path.exists(AVATAR):
        return open(AVATAR, "rb").read()
    me = await tg_call("getMe", _token=TOKEN)
    ph = await tg_call("getUserProfilePhotos", _token=TOKEN, user_id=me["result"]["id"], limit=1)
    sizes = ((ph.get("result") or {}).get("photos") or [[]])[0]
    if not sizes:
        return None
    f = await tg_call("getFile", _token=TOKEN, file_id=sizes[-1]["file_id"])
    r = await A.http.get(f"https://api.telegram.org/file/bot{TOKEN}/{f['result']['file_path']}", timeout=60)
    if r.status_code != 200:
        return None
    with open(AVATAR, "wb") as fh:
        fh.write(r.content)
    return r.content


async def _set_avatar(b):
    """Новому боту — аватарка главного (Telegram создаёт ботов без фото). Один раз."""
    if b.get("photo"):
        return
    try:
        img = await _main_avatar()
        if not img:
            print("franchise avatar: у главного бота нет аватарки", flush=True)
            return
        r = (await A.http.post(f"https://api.telegram.org/bot{b['token']}/setMyProfilePhoto", timeout=60,
                               data={"photo": '{"type": "static", "photo": "attach://p"}'},
                               files={"p": ("avatar.jpg", img, "image/jpeg")})).json()
        if not r.get("ok"):
            print("franchise avatar", b["id"], r.get("description"), flush=True)
            return
        with A.LOCK:
            db.execute("UPDATE bots SET photo=1 WHERE id=?", (b["id"],))
        b["photo"] = 1
    except Exception as e:
        print("franchise avatar", b["id"], e, flush=True)


async def _setup(b):
    """Вебхук + кнопка «Играть» + описание — как у главного бота."""
    tok = b["token"]
    r = await tg_call("setWebhook", _token=tok, url=f"{APP_URL}api/tg/{b['id']}", secret_token=b["secret"],
                      allowed_updates=["message", "pre_checkout_query", "callback_query"], drop_pending_updates=True)
    if not r.get("ok"):
        print("franchise setWebhook", b["id"], r, flush=True)
    await A.bot_setup(tok)
    await _set_avatar(b)
    return r.get("ok")


async def on_managed(mb):
    """Апдейт managed_bot главному боту: создан бот, сменился токен или владелец."""
    owner, bot = mb["user"]["id"], mb["bot"]
    bid = bot["id"]
    r = await tg_call("getManagedBotToken", _token=TOKEN, user_id=bid)
    if not r.get("ok"):
        print("franchise token", bid, r, flush=True)
        return
    tok, old = r["result"], BOTS.get(bid)
    if old:
        with tx():
            db.execute("UPDATE bots SET token=?, owner=?, username=?, name=? WHERE id=?", (tok, owner, bot.get("username"), bot.get("first_name"), bid))
        old.update(token=tok, owner=owner, username=bot.get("username"), name=bot.get("first_name"))
        if old["status"] == "on":
            await _setup(old)
        return
    n = q1("SELECT COUNT(*) n FROM bots WHERE owner=? AND status!='limit'", owner)["n"]
    st = "limit" if n >= cfg("max_per_owner") else "on" if cfg("on") else "off"
    b = {"id": bid, "username": bot.get("username"), "name": bot.get("first_name"), "token": tok, "owner": owner,
         "secret": secrets.token_urlsafe(24), "status": st, "created": now(), "paid": 0, "photo": 0}
    with tx():
        db.execute("INSERT INTO bots(id,username,name,token,owner,secret,status,created,paid) VALUES(?,?,?,?,?,?,?,?,0)",
                   (bid, b["username"], b["name"], tok, owner, b["secret"], st, b["created"]))
    BOTS[bid] = b
    if st == "limit":
        notify(owner, f"🤖 Бот @{esc(b['username'])} создан, но в игру не подключён: у тебя уже {cfg('max_per_owner')} ботов — это максимум")
        return
    if st == "off":
        notify(owner, f"🤖 Бот @{esc(b['username'])} создан, но подключение новых ботов сейчас выключено — подключим, когда откроем снова")
        return
    await _setup(b)
    paid = q1("SELECT 1 FROM bots WHERE owner=? AND paid=1", owner)
    cr = cfg("create_reward") and not q1("SELECT 1 FROM fr_create WHERE owner=?", owner)
    lvl_ok = A.level(q1("SELECT xp FROM users WHERE id=?", owner)["xp"] if q1("SELECT 1 FROM users WHERE id=?", owner) else 0) >= cfg("create_level")
    notify(owner, f"🤖 Твой бот @{esc(b['username'])} готов — в нём та же игра и тот же аккаунт.\n\nДелись ссылкой t.me/{esc(b['username'])}"
           + ("" if not cr or lvl_ok else f"\n\n🎁 <b>{nf(cfg('create_reward'))} ⭐</b> за создание — придут, когда дойдёшь до {cfg('create_level')} уровня")
           + ("" if paid or not cfg("reward") else f"\n\n🎁 Когда через него придут {cfg('players')} новых игроков и дорастут до {cfg('level')} уровня — "
                                                    f"ещё <b>{nf(cfg('reward'))} ⭐</b>"))
    await asyncio.get_running_loop().run_in_executor(None, _create_rewards)   # 25 000 за создание — сразу, если уровень позволяет


NEW_LINK = f"https://t.me/newbot/{BOT_NAME}?name=" + urllib.parse.quote("Кейсы и подарки")   # окно создания бота, менеджер — главный


def offer(uid):
    """Для /me: ссылка создания бота, награда (если ещё не получена), мои боты с прогрессом, показывать ли баннер."""
    if not (CAN_MANAGE["on"] and cfg("on")):
        return None
    mine = [b for b in BOTS.values() if b["owner"] == uid]
    paid = any(b["paid"] for b in mine)
    got = q1("SELECT 1 FROM fr_create WHERE owner=?", uid)
    return {"link": NEW_LINK, "reward": 0 if paid else cfg("reward"), "need": cfg("players"), "level": cfg("level"),
            "create": 0 if got else cfg("create_reward"), "createLevel": cfg("create_level"), "cut": cfg("cut_pct"),
            "cutTotal": q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind='frcut'", uid)["s"],
            "banner": cfg("game_promo"),
            "mine": [{"username": b["username"], "status": b["status"], "progress": _progress(b["id"], uid)} for b in mine]}


def _progress(bid, owner):
    xp = 100 * (cfg("level") - 1) ** 2   # app.level(): L = √(xp/100) + 1
    return q1("SELECT COUNT(*) n FROM users WHERE came_bot=? AND id!=? AND banned=0 AND xp>=?", bid, owner, xp)["n"]


def _create_rewards():
    """create_reward владельцу работающего бота: один раз на аккаунт, когда владелец не ниже create_level."""
    amount = cfg("create_reward")
    if not amount:
        return
    xp = 100 * (cfg("create_level") - 1) ** 2
    for r in q("SELECT b.owner, MIN(b.id) bot, MIN(b.username) un FROM bots b JOIN users u ON u.id=b.owner "
               "WHERE b.status='on' AND u.banned=0 AND u.xp>=? AND b.owner NOT IN (SELECT owner FROM fr_create) GROUP BY b.owner", xp):
        with tx():
            if q1("SELECT 1 FROM fr_create WHERE owner=?", r["owner"]):
                continue
            db.execute("INSERT INTO fr_create(owner,bot,amount,ts) VALUES(?,?,?,?)", (r["owner"], r["bot"], amount, now()))
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, r["owner"]))
            event(r["owner"], "franchise", amount)
        notify(r["owner"], f"🎁 За создание бота @{esc(r['un'])} — <b>+{nf(amount)} ⭐</b>"
               + (f"\n\nКогда через него придут {cfg('players')} новых игроков {cfg('level')}+ уровня — ещё <b>{nf(cfg('reward'))} ⭐</b>" if cfg("reward") else ""))


CUT_KINDS = A.GAME_KINDS[:-1] + ",'fee')"   # весь доход игры: проигрыши в играх + все налоги и комиссии


def fee_income(t0, t1):
    """Весь доход игры за [t0, t1): проигрыши игроков в играх минус выигрыши + налоги и комиссии (маркет, обмены, переводы, кредиты, бизнес)."""
    return -q1(f"SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind IN {CUT_KINDS} AND ts>=? AND ts<?", t0, t1)["s"]


def cut_recipients():
    """Кто получает долю: владельцы работающих ботов (не ниже create_level) и все админы (без условия). [(id, бот)]"""
    xp = 100 * (cfg("create_level") - 1) ** 2
    rows = [(r["owner"], r["un"]) for r in q("SELECT b.owner, MIN(b.username) un FROM bots b JOIN users u ON u.id=b.owner "
                                             "WHERE b.status='on' AND u.banned=0 AND u.xp>=? GROUP BY b.owner", xp)]
    have = {r[0] for r in rows}
    return rows + [(o, BOT_NAME) for o in sorted(ADMINS) if o not in have and q1("SELECT 1 FROM users WHERE id=? AND banned=0", o)]


def cut_share(n):
    """Доля одного получателя, %: cut_pct, а при включённом потолке и многих получателях — cap_pct / n."""
    pct = cfg("cut_pct")
    if cfg("cap_on") and n and n * pct > cfg("cap_pct"):
        return cfg("cap_pct") / n
    return pct


def _cut_tick():
    """Каждую минуту: cut_pct % всего дохода игры (игры + fee), собранного с прошлого тика, — каждому получателю. Дробные части копятся
    в fr_acc (за минуту комиссий бывает ~100 ⭐ → 0,5 ⭐), начисляется целое. Из банка игры (kind frcut)."""
    t1 = now()
    t0 = int(A.kv_get("frcut_ts", 0) or 0) or t1
    if t1 - t0 < 30:
        if not A.kv_get("frcut_ts"):
            with A.LOCK:
                db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('frcut_ts',?)", (str(t1),))
        return
    t0 = max(t0, t1 - 3600)   # после долгого простоя не начисляем задним числом больше часа
    base = fee_income(t0, t1)   # минута, где игроки выиграли больше, чем проиграли, — просто без выплаты (минус не копится)
    rcp = cut_recipients() if base > 0 and cfg("cut_pct") > 0 else []
    pct = cut_share(len(rcp))
    with tx():
        for uid, _ in rcp:
            r = q1("SELECT frac FROM fr_acc WHERE owner=?", uid)
            acc = (r["frac"] if r else 0) + base * pct / 100
            whole = int(acc)
            db.execute("INSERT INTO fr_acc(owner,frac) VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET frac=excluded.frac", (uid, acc - whole))
            if whole:
                db.execute("UPDATE users SET stars=stars+? WHERE id=?", (whole, uid))
                event(uid, "frcut", whole)
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('frcut_ts',?)", (str(t1),))


def _cut_daily():
    """Раз в сутки — сводка «пассивный доход за вчера» (сами начисления идут каждую минуту, без сообщений)."""
    day = A.day_start() - 86400
    if int(A.kv_get("frcut_day", 0) or 0) >= day:
        return
    with A.LOCK:
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('frcut_day',?)", (str(day),))
    for uid, un in cut_recipients():
        got = q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind='frcut' AND ts>=? AND ts<?", uid, day, day + 86400)["s"]
        if got > 0:
            notify(uid, f"💼 Пассивный доход за вчера: <b>+{nf(got)} ⭐</b> — {str(cfg('cut_pct')).replace('.', ',')}% от всего дохода игры (игры + налоги и комиссии).\n"
                        f"Это отчёт: звёзды уже зачислены на баланс в течение вчерашнего дня (начисляются каждую минуту, "
                        f"пока у тебя есть бот @{esc(un)}). История — в профиле → «История».")


async def cut_loop():
    await asyncio.sleep(20)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _cut_tick)
            await asyncio.get_running_loop().run_in_executor(None, _cut_daily)
        except Exception as e:
            print("franchise cut", e, flush=True)
        await asyncio.sleep(60)


def _rewards():
    _create_rewards()
    for b in list(BOTS.values()):
        if b["status"] != "on" or b["paid"]:
            continue
        if not cfg("reward") or _progress(b["id"], b["owner"]) < cfg("players"):
            continue
        reward = cfg("reward")
        with tx():   # один раз на владельца — даже если ботов несколько
            if q1("SELECT 1 FROM bots WHERE owner=? AND paid=1", b["owner"]) or not q1("SELECT 1 FROM users WHERE id=?", b["owner"]):
                continue
            db.execute("UPDATE bots SET paid=1 WHERE id=?", (b["id"],))
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (reward, b["owner"]))
            event(b["owner"], "franchise", reward)
        b["paid"] = 1
        notify(b["owner"], f"🎉 Твой бот @{esc(b['username'])} привёл {cfg('players')} игроков — тебе <b>{nf(reward)} ⭐</b>")


async def reward_loop():
    await asyncio.sleep(60)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, _rewards)
        except Exception as e:
            print("franchise rewards", e, flush=True)
        await asyncio.sleep(600)


async def cmd(m):
    """/franchise в главном боте: кнопка создания + мои боты и прогресс награды."""
    uid = m["from"]["id"]
    if not (CAN_MANAGE["on"] and cfg("on")):
        await tg_call("sendMessage", chat_id=uid, text="🤖 Свои боты скоро появятся — следи за новостями")
        return
    mine = [b for b in BOTS.values() if b["owner"] == uid]
    paid = any(b["paid"] for b in mine)
    lines = ["🤖 <b>Свой бот с этой игрой</b>\n",
             "Жми кнопку — Telegram создаст бота за пару секунд, без @BotFather. В нём та же игра, тот же баланс и подарки у всех игроков.\n"]
    if cfg("create_reward") and not q1("SELECT 1 FROM fr_create WHERE owner=?", uid):
        lines.append(f"🎁 <b>{nf(cfg('create_reward'))} ⭐ сразу</b> за создание (с {cfg('create_level')} уровня, один раз)")
    if cfg("cut_pct"):
        lines.append(f"💼 <b>{str(cfg('cut_pct')).replace('.', ',')}%</b> от всего дохода игры (игры + налоги и комиссии) — начисляется каждую минуту, пока у тебя есть бот (с {cfg('create_level')} уровня)")
    if not paid and cfg("reward"):
        lines.append(f"🎁 Ещё <b>{nf(cfg('reward'))} ⭐</b> — когда через твоего бота придут {cfg('players')} новых игроков и дорастут до {cfg('level')} уровня\n")
    for b in mine:
        st = {"on": "работает", "off": "отключён", "limit": "не подключён (лимит)"}.get(b["status"], b["status"])
        lines.append(f"• @{esc(b['username'])} — {st}" + ("" if paid or b["status"] != "on" else f", игроков: {_progress(b['id'], uid)}/{cfg('players')}"))
    kb = {"keyboard": [[{"text": "🤖 Создать своего бота",
                         "request_managed_bot": {"request_id": 1, "suggested_name": "Кейсы и подарки", "suggested_username": "gifts_case"}}]],
          "resize_keyboard": True, "one_time_keyboard": True}
    await tg_call("sendMessage", chat_id=uid, parse_mode="HTML", text="\n".join(lines), reply_markup=kb)


# ============================== вебхук дочерних ботов ==============================
async def _handle(bid, upd):
    if upd.get("pre_checkout_query") or (upd.get("message") or {}).get("successful_payment"):
        return await _handle_pay(bid, upd)
    b = active(bid)
    if not b:
        return
    CUR_TOKEN.set(b["token"])   # ответы on_command — этим же ботом
    VIA_BOT.set(bid)            # ссылки (реф, кланы, подарки) — на этого бота
    m = upd.get("message")
    try:
        if upd.get("callback_query"):   # кнопки под опросом (polls.py)
            await A.polls.on_callback(upd["callback_query"])
        elif m and m.get("text", "").startswith("/"):
            await A.on_command(m)
    except Exception as e:
        print("franchise update", bid, e, flush=True)


async def _handle_pay(bid, upd):
    """Оплата Stars через дочерний бот — только если его назначали ботом оплат и он принадлежит админу."""
    b = BOTS.get(bid)
    if not b:
        return
    CUR_TOKEN.set(b["token"])
    import shop
    try:
        if upd.get("pre_checkout_query"):
            pq = upd["pre_checkout_query"]
            if pay_allowed(bid):
                await shop.on_pre_checkout(pq)
            else:
                print("franchise: чужой счёт отклонён", bid, pq.get("from", {}).get("id"), flush=True)
                await tg_call("answerPreCheckoutQuery", pre_checkout_query_id=pq["id"], ok=False,
                              error_message=f"Покупки — только в @{face_name()}")
        elif pay_allowed(bid):
            await asyncio.get_running_loop().run_in_executor(None, shop.on_paid, upd["message"])
        else:
            print("franchise: платёж через неразрешённого бота", bid, upd["message"].get("successful_payment"), flush=True)
    except Exception as e:
        print("franchise pay", bid, e, flush=True)


@app.post(R + "/tg/{bid}")
async def webhook(bid: int, request: Request):
    b = BOTS.get(bid)
    if not b or not hmac.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", ""), b["secret"] or ""):
        return JSONResponse({}, status_code=403)
    upd = await request.json()
    asyncio.create_task(_handle(bid, upd))
    return {}


# ============================== админка ==============================
@app.get(R + "/admin/franchise")
def admin_list(aid=Depends(admin)):
    out = []
    for r in q("SELECT b.id, b.username, b.name, b.owner, b.status, b.created, b.paid, u.name oname, "
               "(SELECT COUNT(*) FROM users WHERE came_bot=b.id) came, (SELECT COUNT(*) FROM users WHERE bot=b.id) now "
               "FROM bots b LEFT JOIN users u ON u.id=b.owner ORDER BY b.created DESC"):
        out.append({**dict(r), "progress": _progress(r["id"], r["owner"]),
                    "cut": q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind='frcut'", r["owner"])["s"],
                    "today": q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE user=? AND kind='frcut' AND ts>=?", r["owner"], A.day_start())["s"]})
    pr = q1("SELECT COUNT(*) n, COALESCE(SUM(ts>?),0) w FROM fr_promo", now() - 7 * 86400)
    n = len(cut_recipients())
    return {"bots": out, "cut": {"n": n, "share": round(cut_share(n), 4), "total": round(cut_share(n) * n, 2)}, "cfg": {k: cfg(k) for k in DEFAULTS}, "defaults": DEFAULTS, "changed": list(CFG), "canEdit": aid in OWNERS,
            "manager": CAN_MANAGE["on"], "promo": {"total": pr["n"], "week": pr["w"], "running": PROMO["running"]},
            "need": cfg("players"), "reward": cfg("reward"), "level": cfg("level")}


@app.post(R + "/admin/franchise/cfg")
async def admin_cfg(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Менять настройки франшизы может только владелец")
    body = await req.json()
    if not isinstance(body, dict):
        err("неверные данные")
    cur = dict(CFG)
    for k, v in body.items():
        if k not in DEFAULTS:
            continue
        if v is None:
            cur.pop(k, None)
        elif isinstance(DEFAULTS[k], bool):
            cur[k] = v in (True, 1, "1", "true")
        else:
            try:
                v = round(float(str(v).replace(",", ".")), 2) if isinstance(DEFAULTS[k], float) else int(v)
            except (TypeError, ValueError):
                err("введи число")
            lo, hi = LIMITS[k]
            if not lo <= v <= hi:
                err(f"от {lo} до {hi}")
            cur[k] = v
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('frcfg',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur),))
        log(aid, "frcfg", None, ", ".join(f"{k}={cur.get(k, DEFAULTS[k])}" for k in DEFAULTS))
    CFG.clear()
    CFG.update(cur)
    return {"ok": True, "cfg": {k: cfg(k) for k in DEFAULTS}}


def _announce_targets():
    """«Разослать всем»: все с включёнными сообщениями от бота, кроме владельцев ботов — без ограничения «раз в N дней»."""
    return [r[0] for r in q("SELECT id FROM users WHERE banned=0 AND COALESCE(notif,1)=1 AND id NOT IN (SELECT owner FROM bots) ORDER BY seen DESC")]


@app.get(R + "/admin/franchise/announce")
def admin_announce_preview(aid=Depends(admin)):
    return {"total": len(_announce_targets()), "text": promo_text()}


@app.post(R + "/admin/franchise/announce")
async def admin_announce(aid=Depends(admin)):
    if aid not in OWNERS:
        err("Рассылку может запустить только владелец")
    if PROMO["running"]:
        err("рассылка уже идёт")
    if not (CAN_MANAGE["on"] and cfg("on")):
        err("франшиза выключена или главный бот ещё не менеджер (@BotFather)")
    ids = await asyncio.get_running_loop().run_in_executor(None, _announce_targets)
    with tx():
        log(aid, "frannounce", None, f"{len(ids)} игрокам")
    asyncio.create_task(_promo_send(ids))
    return {"ok": True, "total": len(ids)}


@app.post(R + "/admin/franchise/promo")
async def admin_promo(aid=Depends(admin)):
    """Разослать предложение сейчас (тем же правилам: уровень, раз в N дней, включённые уведомления)."""
    if PROMO["running"]:
        err("рассылка уже идёт")
    if not (CAN_MANAGE["on"] and cfg("on")):
        err("франшиза выключена или главный бот ещё не менеджер (@BotFather)")
    ids = await asyncio.get_running_loop().run_in_executor(None, _promo_targets, 2000)
    with tx():
        log(aid, "frpromo", None, f"{len(ids)} игрокам")
    asyncio.create_task(_promo_send(ids))
    return {"ok": True, "total": len(ids)}


def _main_info():
    def row(b):
        return {"id": b["id"], "username": b["username"], "owner": b["owner"], "admin": can_pay(b["id"])}
    return {"face": MAIN["face"] if active(MAIN["face"]) else 0, "pay": (pay_bot() or {}).get("id", 0), "base": BOT_NAME,
            "faceSet": MAIN["face"], "paySet": MAIN["pay"],
            "bots": [row(b) for b in sorted(BOTS.values(), key=lambda x: x["username"].lower()) if b["status"] == "on"]}


@app.get(R + "/admin/franchise/main")
def admin_main(aid=Depends(admin)):
    return {**_main_info(), "canEdit": aid in OWNERS}


@app.post(R + "/admin/franchise/main")
async def admin_main_set(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Назначать главного бота может только владелец")
    body = await req.json()
    if not isinstance(body, dict):
        err("неверные данные")
    cur = dict(MAIN, pay_ok=list(MAIN["pay_ok"]))
    for k in ("face", "pay"):
        if k not in body:
            continue
        try:
            bid = int(body[k] or 0)
        except (TypeError, ValueError):
            err("неверный бот")
        if bid:
            b = active(bid) or err("бот не найден или отключён")
            if k == "pay":
                if not can_pay(bid):
                    err("Для оплат — только бот, владелец которого админ: настоящие звёзды копятся у владельца бота")
                r = await tg_call("setWebhook", _token=b["token"], url=f"{APP_URL}api/tg/{bid}", secret_token=b["secret"],
                                  allowed_updates=["message", "pre_checkout_query", "callback_query"])   # без drop: не терять апдейты
                if not r.get("ok"):
                    err("Telegram не принял вебхук этого бота — попробуй позже")
                if bid not in cur["pay_ok"]:
                    cur["pay_ok"].append(bid)
        cur[k] = bid
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('mainbot',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur),))
        log(aid, "mainbot", None, f"лицо={cur['face'] or BOT_NAME}, оплаты={cur['pay'] or BOT_NAME}")
    MAIN.update(cur)
    return {"ok": True, **_main_info()}


@app.post(R + "/admin/franchise/{bid}")
async def admin_toggle(bid: int, req: Request, aid=Depends(admin)):
    b = BOTS.get(bid) or err("нет такого бота", 404)
    on = bool((await req.json()).get("on"))
    with tx():
        db.execute("UPDATE bots SET status=? WHERE id=?", ("on" if on else "off", bid))
        log(aid, "franchise_on" if on else "franchise_off", b["owner"], f"@{b['username']}")
    b["status"] = "on" if on else "off"
    if on:
        await _setup(b)
    else:
        await tg_call("deleteWebhook", _token=b["token"])
    return {"ok": True, "status": b["status"]}


# ============================== бот предлагает игрокам создать франшизу ==============================
PROMO = {"running": False}


def _promo_targets(limit):
    """Активные игроки нужного уровня с включёнными сообщениями от бота, без своего бота; одному — не чаще раза в promo_days."""
    xp = 100 * (cfg("promo_level") - 1) ** 2
    t = now()
    return [r[0] for r in q("SELECT u.id FROM users u LEFT JOIN fr_promo p ON p.user=u.id "
                             "WHERE u.banned=0 AND COALESCE(u.notif,1)=1 AND u.xp>=? AND u.seen>? AND (p.ts IS NULL OR p.ts<?) "
                             "AND u.id NOT IN (SELECT owner FROM bots) ORDER BY u.seen DESC LIMIT ?",
                             xp, t - 14 * 86400, t - cfg("promo_days") * 86400, limit)]


def promo_text():
    """Предложение создать бота: и авто-рассылка, и «Разослать всем» из админки. Суммы — из настроек."""
    r, c, pct = cfg("reward"), cfg("create_reward"), cfg("cut_pct")
    pc = str(pct).replace(".", ",")
    perks = ([f"• <b>{nf(c)} ⭐ сразу</b> за создание (с {cfg('create_level')} уровня)"] if c else []) \
        + ([f"• <b>{pc}% от всего дохода игры (игры + налоги и комиссии)</b> — пассивный доход каждую минуту, пока у тебя есть бот"] if pct else []) \
        + ([f"• ещё <b>{nf(r)} ⭐</b>, когда придут {cfg('players')} игроков {cfg('level')}+ уровня"] if r else [])
    return ("🤖 <b>Свой бот с этой игрой" + (" — и доход каждую минуту</b>" if pct else "</b>") + "\n\n"
            "Одной кнопкой создай свой бот с нашей игрой — без @BotFather и без кода. "
            "Та же игра, тот же баланс, подарки и турниры."
            + ("\n\n💰 <b>Что получаешь:</b>\n" + "\n".join(perks) if perks else "")
            + "\n\nСоздай бота — и получай доход каждую минуту 👇")


async def _promo_send(ids):
    PROMO["running"] = True
    kb = {"inline_keyboard": [[{"text": "🤖 Создать бота", "url": NEW_LINK}],
                              [{"text": "Открыть игру", "web_app": {"url": APP_URL}}]]}
    try:
        for uid in ids:
            with tx():   # отмечаем до отправки: сбой посреди рассылки не приведёт к повтору
                db.execute("INSERT INTO fr_promo(user,ts) VALUES(?,?) ON CONFLICT(user) DO UPDATE SET ts=excluded.ts, n=n+1", (uid, now()))
            try:
                r = await tg_call("sendMessage", _token=token_for(uid), chat_id=uid, text=promo_text(), parse_mode="HTML", reply_markup=kb)
                if not r.get("ok") and token_for(uid) != TOKEN:
                    await tg_call("sendMessage", _token=TOKEN, chat_id=uid, text=promo_text(), parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                print("franchise promo", uid, e, flush=True)
            await asyncio.sleep(0.05)   # лимит Telegram ~30 сообщений/с
    finally:
        PROMO["running"] = False


async def promo_loop():
    await asyncio.sleep(300)
    while True:
        try:
            if CAN_MANAGE["on"] and cfg("on") and cfg("bot_promo") and not PROMO["running"]:
                ids = await asyncio.get_running_loop().run_in_executor(None, _promo_targets, 300)   # понемногу, раз в 30 мин
                if ids:
                    await _promo_send(ids)
        except Exception as e:
            print("franchise promo loop", e, flush=True)
        await asyncio.sleep(1800)


FIXED = {}   # id бота → когда в последний раз сами вернули вебхук/кнопку (повтор в течение суток — отключаем)


async def _restore(b):
    await _setup(b)
    FIXED[b["id"]] = now()


async def _check(b):
    """Вебхук и кнопка «Играть» — наши? Иначе владелец мог подменить Mini App и собирать входы игроков."""
    w = await tg_call("getWebhookInfo", _token=b["token"])
    if not w.get("ok"):
        if w.get("error_code") != 401:
            return None   # сбой Telegram — проверим в следующий раз
        # токен не принимается: сменили (апдейт managed_bot мог потеряться) или бота удалили
        r = await tg_call("getManagedBotToken", _token=TOKEN, user_id=b["id"])
        if not r.get("ok"):
            return "бот удалён или больше не управляется игрой"
        with tx():
            db.execute("UPDATE bots SET token=? WHERE id=?", (r["result"], b["id"]))
        b["token"] = r["result"]
        await _setup(b)
        return None
    why = None
    if w["result"].get("url") != f"{APP_URL}api/tg/{b['id']}":
        why = "сменён вебхук"
    else:
        mb = await tg_call("getChatMenuButton", _token=b["token"])
        if mb.get("ok") and not ((mb["result"].get("web_app") or {}).get("url", "")).startswith(APP_URL):
            why = "сменена кнопка «Играть»"
    return why


async def watch_loop():
    await asyncio.sleep(90)
    while True:
        try:   # управление ботами могли включить в @BotFather после запуска — кнопка в игре появится без перезапуска
            r = await tg_call("getMe", _token=TOKEN)
            if r.get("ok"):
                CAN_MANAGE["on"] = bool(r["result"].get("can_manage_bots"))
        except Exception:
            pass
        for b in [b for b in BOTS.values() if b["status"] == "on"]:
            try:
                why = await _check(b)
            except Exception as e:
                print("franchise watch", b["id"], e, flush=True)
                continue
            if why and now() - FIXED.get(b["id"], 0) > 86400:
                # первый раз — возвращаем сами: бывает, что Telegram не принял кнопку при создании бота (ложная тревога)
                print("franchise restore", b["id"], b["username"], why, flush=True)
                await _restore(b)
                why = None
            if why:
                with tx():
                    db.execute("UPDATE bots SET status='off' WHERE id=?", (b["id"],))
                b["status"] = "off"
                print("franchise OFF", b["id"], b["username"], why, flush=True)
                notify(b["owner"], f"⛔ Бот @{esc(b['username'])} отключён от игры: {why}. Игроки могут играть в @{face_name()}")
                for a in ADMINS:
                    if a not in STEALTH:   # в режиме секретности админу не шлём
                        notify(a, f"⛔ Франшиза @{esc(b['username'])} (владелец {b['owner']}) отключена автоматически: {why}")
            await asyncio.sleep(0.3)
        await asyncio.sleep(180)


async def startup():
    r = await tg_call("getMe", _token=TOKEN)
    CAN_MANAGE["on"] = bool((r.get("result") or {}).get("can_manage_bots"))
    if not CAN_MANAGE["on"]:
        print("franchise: главный бот не менеджер — включи управление ботами в @BotFather (Mini App)", flush=True)
    asyncio.create_task(reward_loop())
    asyncio.create_task(watch_loop())
    asyncio.create_task(promo_loop())
    asyncio.create_task(cut_loop())
    for b in [b for b in BOTS.values() if b["status"] == "on" and not b.get("photo")]:   # боты, созданные до аватарок
        await _set_avatar(b)
