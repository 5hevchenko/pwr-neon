"""Переводы звёзд между игроками (экран «Кошелёк» в стиле WeChat): свой QR «Получить», сканер, перевод по QR/поиску.
QR и ссылка ведут на бота: t.me/<бот>?start=pay_<id>[_<сумма>] → кнопка открывает игру с ?pay=<id>&amt=<сумма>.
Получатель получает ровно сумму перевода, комиссия (как в обменах) списывается с отправителя сверху и уходит в банк."""
import asyncio
import hashlib
import hmac
import json
import math
import re
import secrets

from fastapi import Depends, Request

import loans
import app as A
from app import BOT_NAME, R, bot_name, app, auth, bal, db, err, esc, event, kv_get, notify, now, q, q1, tg_call, tx, user_brief
from settings import conf

# настройки: по умолчанию из settings.toml, владелец меняет на лету в админке (вкладка «Переводы», хранится в kv 'paycfg')
DEFAULTS = {
    "on": True,
    "fee": conf("economy.transfer_fee", conf("economy.trade_fee", 0.05)),
    "fee_addr": conf("economy.transfer_fee_addr", conf("economy.transfer_fee", conf("economy.trade_fee", 0.05))),   # перевод по адресу NP…
    "min": conf("economy.transfer_min", 10),
    "max": conf("economy.transfer_max", 0),            # один перевод не больше (0 — без ограничения)
    "day": conf("economy.transfer_day_count", 50),     # переводов в сутки с одного аккаунта
    "inline_on": conf("economy.inline_on", True),      # инлайн-чеки: @бот <сумма> в любом чате
    "inline_ttl_h": conf("economy.inline_ttl_h", 24),  # через сколько часов невостребованный чек вернётся отправителю
}
LIMITS = {"fee": (0, 0.5), "fee_addr": (0, 0.5), "min": (1, 10 ** 7), "max": (0, 10 ** 10), "day": (1, 1000), "inline_ttl_h": (1, 720)}
CFG = {}
NOTE_MAX = 60


def _load():
    try:
        v = json.loads(kv_get("paycfg", "{}") or "{}")
        CFG.clear()
        CFG.update({k: x for k, x in v.items() if k in DEFAULTS})
    except Exception as e:
        print("paycfg:", e, flush=True)


def cfg(k):
    if k == "fee_addr" and k not in CFG:   # пока не задана отдельно — как обычная комиссия
        return cfg("fee")
    return CFG.get(k, DEFAULTS[k])


_load()

db.executescript("""
CREATE TABLE IF NOT EXISTS transfers(id INTEGER PRIMARY KEY, src INTEGER, dst INTEGER, amount INTEGER, fee INTEGER, note TEXT, ts INTEGER);
CREATE INDEX IF NOT EXISTS transfers_src ON transfers(src, ts);
CREATE INDEX IF NOT EXISTS transfers_dst ON transfers(dst, ts);
CREATE TABLE IF NOT EXISTS pay_pin(user INTEGER PRIMARY KEY, hash TEXT, salt TEXT, ts INTEGER, fails INTEGER DEFAULT 0, lock INTEGER DEFAULT 0,
  code TEXT, code_until INTEGER DEFAULT 0, code_fails INTEGER DEFAULT 0, code_ts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS pay_addr(user INTEGER PRIMARY KEY, addr TEXT UNIQUE NOT NULL, ts INTEGER);
CREATE TABLE IF NOT EXISTS pay_anon(user INTEGER PRIMARY KEY, addr TEXT UNIQUE NOT NULL, ts INTEGER);
CREATE TABLE IF NOT EXISTS cheques(code TEXT PRIMARY KEY, sender INTEGER, amount INTEGER, fee INTEGER,
  created INTEGER, claimed_by INTEGER DEFAULT 0, claimed_ts INTEGER DEFAULT 0, refunded INTEGER DEFAULT 0);
""")
try:   # anon=1 — перевод на анонимный адрес: отправитель не видит, кому ушли звёзды
    db.execute("ALTER TABLE transfers ADD COLUMN anon INTEGER DEFAULT 0")
except Exception:
    pass
# пасхалка: 5 раз подряд «скопировать адрес» → копируется анонимный адрес; переводящий видит «Неизвестный пользователь»
ANON = {"id": 0, "anon": True, "name": "Неизвестный пользователь", "username": None, "photo": None, "level": 0,
        "clan": None, "crown": None, "title": None, "frame": None, "vip": False}

# ---------------- адрес кошелька (как в крипте): NP + 16 случайных символов + 4 символа контрольной суммы ----------------
# Случайный, а не из id: по адресу не узнать Telegram-аккаунт, подобрать чужой нельзя (80 бит). Контрольная сумма ловит опечатки.
ADDR_ABC = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # base32 Крокфорда: без I, L, O, U — их не спутать


def _addr_sum(body):
    h = hashlib.sha256(("np:" + body).encode()).digest()
    return "".join(ADDR_ABC[b % 32] for b in h[:4])


def addr_norm(s):
    """Приводим ввод к виду NP…: регистр, пробелы/дефисы, O→0, I/L→1. None — если это не похоже на адрес."""
    s = "".join(str(s or "").upper().split()).replace("-", "").translate(str.maketrans("OIL", "011"))
    if not (len(s) == 22 and s.startswith("NP") and all(c in ADDR_ABC for c in s[2:])):
        return None
    return s


def addr_of(uid, table="pay_addr"):
    """Постоянный адрес игрока (table="pay_anon" — анонимный). Создаётся при первом запросе."""
    r = q1(f"SELECT addr FROM {table} WHERE user=?", uid)
    if r:
        return r["addr"]
    while True:
        body = "".join(secrets.choice(ADDR_ABC) for _ in range(16))
        a = "NP" + body + _addr_sum(body)
        with tx():
            r = q1(f"SELECT addr FROM {table} WHERE user=?", uid)
            if r:
                return r["addr"]
            if not q1("SELECT 1 FROM pay_addr WHERE addr=? UNION SELECT 1 FROM pay_anon WHERE addr=?", a, a):
                db.execute(f"INSERT INTO {table}(user,addr,ts) VALUES(?,?,?)", (uid, a, now()))
                return a

# ---------------- пароль кошелька (6 цифр, как в WeChat): без него переводы не проходят ----------------
# Храним только PBKDF2-хэш с солью. 5 неверных подряд — блок переводов на 15 минут. Забыл — бот присылает код сброса в личку.
PIN_ITER, PIN_FAILS, PIN_LOCK = 120_000, 5, 15 * 60
CODE_TTL, CODE_FAILS, CODE_EVERY = 10 * 60, 5, 60
WEAK = {"000000", "111111", "222222", "333333", "444444", "555555", "666666", "777777", "888888", "999999",
        "123456", "654321", "012345", "543210", "123123", "112233"}


def _hash(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), PIN_ITER).hex()


def _pin_ok(pin):
    return isinstance(pin, str) and len(pin) == 6 and pin.isdigit()


def has_pin(uid):
    r = q1("SELECT hash FROM pay_pin WHERE user=?", uid)
    return bool(r and r["hash"])


async def _set_pin(uid, pin):
    if not _pin_ok(pin):
        err("пароль — 6 цифр")
    if pin in WEAK:
        err("слишком простой пароль — придумай другой")
    salt = secrets.token_hex(16)
    h = await asyncio.to_thread(_hash, pin, salt)   # PBKDF2 ~0,1 с — не держим цикл событий
    with tx():
        db.execute("INSERT INTO pay_pin(user,hash,salt,ts,fails,lock,code,code_until,code_fails) VALUES(?,?,?,?,0,0,NULL,0,0) "
                   "ON CONFLICT(user) DO UPDATE SET hash=excluded.hash, salt=excluded.salt, ts=excluded.ts, fails=0, lock=0, code=NULL, code_until=0, code_fails=0",
                   (uid, h, salt, now()))


async def check_pin(uid, pin):
    """Неверный пароль считает попытку и бросает err() — уже ПОСЛЕ записи счётчика (иначе tx откатил бы его)."""
    r = q1("SELECT * FROM pay_pin WHERE user=?", uid)
    if not r or not r["hash"]:
        err("сначала задай пароль кошелька")
    t = now()
    if r["lock"] > t:
        err(f"слишком много неверных попыток — переводы снова через {(r['lock'] - t + 59) // 60} мин")
    ok = _pin_ok(pin) and hmac.compare_digest(await asyncio.to_thread(_hash, pin, r["salt"]), r["hash"])
    with tx():
        if ok:
            db.execute("UPDATE pay_pin SET fails=0 WHERE user=?", (uid,))
        else:
            fails = (q1("SELECT fails FROM pay_pin WHERE user=?", uid)["fails"] or 0) + 1
            if fails >= PIN_FAILS:
                db.execute("UPDATE pay_pin SET fails=0, lock=? WHERE user=?", (t + PIN_LOCK, uid))
            else:
                db.execute("UPDATE pay_pin SET fails=? WHERE user=?", (fails, uid))
    if not ok:
        if fails >= PIN_FAILS:
            err(f"неверный пароль — переводы заблокированы на {PIN_LOCK // 60} минут")
        err(f"неверный пароль, осталось попыток: {PIN_FAILS - fails}")


def _fee(amount, k="fee"):
    return math.ceil(amount * cfg(k))


def _brief(uid):
    u = q1("SELECT * FROM users WHERE id=?", uid)
    return user_brief(u) if u else None


@app.get(R + "/pay")
def pay_home(uid=Depends(auth)):
    rows = q("SELECT * FROM transfers WHERE src=? OR dst=? ORDER BY id DESC LIMIT 30", uid, uid)
    peers = {}
    out = []
    for r in rows:
        other = r["dst"] if r["src"] == uid else r["src"]
        if other not in peers:
            peers[other] = _brief(other)
        if peers[other]:
            hide = bool(r["anon"])   # анонимный перевод скрыт в обе стороны (в transfers src/dst остаются — админу видно для откатов)
            out.append({"in": r["dst"] == uid, "amount": r["amount"], "fee": r["fee"], "note": r["note"], "ts": r["ts"], "user": ANON if hide else peers[other]})
    wk = now() - 7 * 86400
    week = {"in": q1("SELECT COALESCE(SUM(amount),0) s FROM transfers WHERE dst=? AND ts>=?", uid, wk)["s"],
            "out": q1("SELECT COALESCE(SUM(amount),0) s FROM transfers WHERE src=? AND ts>=?", uid, wk)["s"]}
    return {"stars": bal(uid), "week": week, "fee": cfg("fee"), "feeAddr": cfg("fee_addr"), "min": cfg("min"), "max": cfg("max"), "on": cfg("on"), "link": f"https://t.me/{bot_name()}?start=pay_{uid}", "history": out, "pin": has_pin(uid), "addr": addr_of(uid)}


@app.get(R + "/pay/peer/{tid}")
def pay_peer(tid: int, uid=Depends(auth)):
    if tid == uid:
        err("это твой QR-код — дай его отсканировать другу")
    u = q1("SELECT * FROM users WHERE id=?", tid)
    if not u or u["banned"]:
        err("игрок не найден")
    return user_brief(u)


def addr_key(a):
    """Ввод → как хранится: заглавные, без пробелов и дефисов (свои адреса от админа — любые латинские буквы и цифры)."""
    return "".join(str(a or "").upper().split()).replace("-", "")


def addr_find(a):
    """(id владельца, анонимный ли) или None — без ошибок. Сначала точное совпадение (свой адрес), потом стандартный NP…"""
    for k in {addr_key(a), addr_norm(a)} - {None, ""}:
        for t, anon in (("pay_addr", False), ("pay_anon", True)):
            r = q1(f"SELECT user FROM {t} WHERE addr=?", k)
            if r:
                return r["user"], anon
    return None


def addr_owner(a):
    """Адрес → (id владельца, анонимный ли адрес) или err с понятной причиной."""
    f = addr_find(a)
    if f:
        return f
    n = addr_norm(a)
    if not n:
        err("кошелёк с таким адресом не найден")
    if _addr_sum(n[2:18]) != n[18:]:
        err("в адресе опечатка — проверь символы")
    r = q1("SELECT user FROM pay_addr WHERE addr=?", n)
    if r:
        return r["user"], False
    r = q1("SELECT user FROM pay_anon WHERE addr=?", n)
    if not r:
        err("кошелёк с таким адресом не найден")
    return r["user"], True


BANK_BRIEF = {"id": 0, "bank": True, "name": "Банк игры", "username": None, "photo": None, "level": 0,
              "clan": None, "crown": None, "title": None, "frame": None, "vip": False}


@app.get(R + "/pay/addrfind/{a}")
def pay_addrfind(a: str, uid=Depends(auth)):
    """Тихий поиск по адресу для поля «кому» (там же ищут по нику): не нашли — {"user": None}, без ошибки."""
    f = addr_find(a) if 3 <= len(addr_key(a)) <= 32 else None
    if not f or f[0] == uid:
        return {"user": None}
    u = q1("SELECT * FROM users WHERE id=?", f[0])
    if not u or u["banned"]:
        return {"user": None}
    return {"user": ANON if f[1] else user_brief(u), "addr": addr_key(a)}


@app.get(R + "/pay/addr/{a}")
def pay_addr(a: str, uid=Depends(auth)):
    import bank
    if addr_norm(a) == bank.bank_addr():   # адрес банка: перевод = подарок банку (клиент открывает окно банка)
        return BANK_BRIEF
    owner, anon = addr_owner(a)
    if owner == uid:
        err("это твой адрес — дай его другу")
    u = q1("SELECT * FROM users WHERE id=?", owner)
    if not u or u["banned"]:
        err("кошелёк с таким адресом не найден")
    return ANON if anon else user_brief(u)


@app.get(R + "/pay/anon")
def pay_anon(uid=Depends(auth)):
    return {"addr": addr_of(uid, "pay_anon")}


@app.post(R + "/pay/send")
async def pay_send(req: Request, uid=Depends(auth)):
    b = await req.json()
    try:
        to, amount = int(b.get("to", 0) or 0), int(b.get("amount", 0))
    except (TypeError, ValueError):
        err("введи сумму")
    fee_k, anon = "fee", False
    import bank
    if b.get("addr") and addr_norm(b["addr"]) == bank.bank_addr():   # перевод на адрес банка — без комиссии и пароля
        return bank.donate(uid, amount)
    if b.get("addr"):   # перевод по адресу — своя комиссия (админка → «Переводы»)
        (to, anon), fee_k = addr_owner(b["addr"]), "fee_addr"
    note = " ".join(str(b.get("note", "")).split())[:NOTE_MAX]
    if to == uid:
        err("себе перевести нельзя")
    if not cfg("on"):
        err("Переводы временно отключены")
    if amount < cfg("min"):
        err(f"минимум {cfg('min')} ⭐")
    if cfg("max") and amount > cfg("max"):
        err(f"за один раз не больше {cfg('max'):,} ⭐".replace(",", " "))
    await check_pin(uid, str(b.get("pin", "")))
    fee = _fee(amount, fee_k)
    with tx():
        dst = q1("SELECT id, banned FROM users WHERE id=?", to)
        if not dst or dst["banned"]:
            err("игрок не найден")
        if loans.stars_locked(uid):
            err("пока не закрыт кредит без залога или баланс в минусе, переводить звёзды нельзя")
        if q1("SELECT COUNT(*) n FROM transfers WHERE src=? AND ts>?", uid, now() - 86400)["n"] >= cfg("day"):
            err(f"не больше {cfg('day')} переводов в сутки")
        if bal(uid) < amount + fee:
            err(f"Не хватает звёзд: нужно {amount + fee} ⭐ с комиссией")
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount + fee, uid))
        db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, to))
        event(uid, "transfer", -amount)
        if fee:
            event(uid, "fee", -fee)
        event(to, "transfer", amount)
        db.execute("INSERT INTO transfers(src,dst,amount,fee,note,ts,anon) VALUES(?,?,?,?,?,?,?)", (uid, to, amount, fee, note, now(), int(anon)))
        name = "Неизвестный пользователь" if anon else q1("SELECT name FROM users WHERE id=?", uid)["name"]
        left = bal(uid)
    notify(to, f"💸 Перевод от <b>{esc(name)}</b>: <b>{amount:,} ⭐</b>".replace(",", " ") + (f"\n\n<i>«{esc(note)}»</i>" if note else ""))
    return {"ok": True, "stars": left, "amount": amount, "fee": fee}


@app.post(R + "/pay/pin")
async def pin_set(req: Request, uid=Depends(auth)):
    """Задать пароль (первый раз) или сменить (нужен старый)."""
    b = await req.json()
    if has_pin(uid):
        await check_pin(uid, str(b.get("old", "")))
    await _set_pin(uid, str(b.get("pin", "")))
    return {"ok": True}


@app.post(R + "/pay/pin/forgot")
async def pin_forgot(uid=Depends(auth)):
    """Код сброса — ботом в личку (аккаунт Telegram = личность игрока)."""
    t = now()
    r = q1("SELECT code_ts FROM pay_pin WHERE user=?", uid)
    if r and t - (r["code_ts"] or 0) < CODE_EVERY:
        err("код уже отправлен — проверь сообщения от бота (повторно — через минуту)")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    # бот, где игрок играет; protect_content — владелец бота-франшизы не перешлёт себе код (forwardMessage по message_id)
    res = await tg_call("sendMessage", _token=__import__("franchise").token_for(uid), chat_id=uid, parse_mode="HTML", protect_content=True,
                        text=f"🔐 Код для сброса пароля кошелька: <b>{code}</b>\n\nДействует 10 минут. Никому его не сообщай — администрация никогда его не спрашивает.")
    if not res.get("ok"):
        err("бот не смог написать — открой чат с ботом, нажми «Старт» и попробуй снова")
    with tx():
        db.execute("INSERT INTO pay_pin(user,code,code_until,code_fails,code_ts) VALUES(?,?,?,0,?) "
                   "ON CONFLICT(user) DO UPDATE SET code=excluded.code, code_until=excluded.code_until, code_fails=0, code_ts=excluded.code_ts",
                   (uid, hashlib.sha256(code.encode()).hexdigest(), t + CODE_TTL, t))
    return {"ok": True}


@app.post(R + "/pay/pin/reset")
async def pin_reset(req: Request, uid=Depends(auth)):
    b = await req.json()
    code, t = str(b.get("code", "")), now()
    r = q1("SELECT code, code_until, code_fails FROM pay_pin WHERE user=?", uid)
    if not r or not r["code"] or r["code_until"] < t:
        err("код устарел — запроси новый")
    if r["code_fails"] >= CODE_FAILS:
        err("слишком много неверных кодов — запроси новый")
    if not hmac.compare_digest(hashlib.sha256(code.encode()).hexdigest(), r["code"]):
        with tx():
            db.execute("UPDATE pay_pin SET code_fails=code_fails+1 WHERE user=?", (uid,))
        err("неверный код")
    await _set_pin(uid, str(b.get("pin", "")))   # заодно стирает код и снимает блокировку
    return {"ok": True}


@app.post(R + "/pay/qr/send")
async def qr_send(req: Request, uid=Depends(auth)):
    """Постоянный QR для печати: картинку рисует телефон (PNG), бот присылает её игроку в чат — оттуда печатать/сохранять."""
    data = await req.body()
    if not 1000 < len(data) < 3 * 1024 * 1024 or not data.startswith(b"\x89PNG"):
        err("не получилось сделать картинку")
    r = await A.http.post(f"https://api.telegram.org/bot{A.TOKEN}/sendDocument", timeout=60,
                          data={"chat_id": str(uid), "caption": "🧾 Твой постоянный QR для приёма звёзд — его можно распечатать. Он не меняется."},
                          files={"document": ("qr-oplata.png", data, "image/png")})
    if not r.json().get("ok"):
        err("бот не смог написать — открой чат с ботом и нажми «Старт»")
    return {"ok": True}


# ---------------- админка: переводы игрока (в карточке игрока) ----------------
# ---------------- инлайн-чеки: «@бот <сумма>» в любом чате → карточка «Получить» ----------------
# Чек забирает ПЕРВЫЙ, кто откроет t.me/<бот>?start=claim_<код> (кроме отправителя). Средства резервируются
# при отправке чека (chosen_inline_result); невостребованный чек возвращается через inline_ttl_h. В коде зашита
# сумма (вид «8000xСЛУЧ»), т.к. chosen_inline_result не передаёт текст карточки. src/dst пишутся в transfers при заборе.
def _cheque_amt(code):
    try:
        return int(code.split("x", 1)[0])
    except (ValueError, IndexError, AttributeError):
        return 0


def _cheque_sender(code):
    # формат кода: «<сумма>x<id_отправителя>x<случайное>» — отправитель зашит, чтобы забор мог
    # сам списать средства, если chosen_inline_result не пришёл (у бота выключен inline-feedback)
    try:
        return int(code.split("x")[1])
    except (ValueError, IndexError, AttributeError):
        return 0


async def _inline_hint(qid, text):
    await tg_call("answerInlineQuery", inline_query_id=qid, results=[], cache_time=1, is_personal=True,
                  switch_pm_text=text[:64], switch_pm_parameter="wallet")


async def on_inline(iq):
    """@бот <сумма> → карточка «Перевести N ⭐». Код с суммой кладём в кнопку; резерв — на chosen_inline_result."""
    qid, uid = iq["id"], iq["from"]["id"]
    amount = int(re.sub(r"\D", "", (iq.get("query") or "")) or 0)
    if not cfg("inline_on") or not cfg("on"):
        return await _inline_hint(qid, "Переводы сейчас отключены")
    if amount < cfg("min"):
        return await _inline_hint(qid, f"Напиши сумму чека — минимум {cfg('min')} ⭐")
    if cfg("max") and amount > cfg("max"):
        return await _inline_hint(qid, f"Максимум за раз — {cfg('max')} ⭐")
    fee = _fee(amount)
    u = q1("SELECT stars FROM users WHERE id=?", uid)   # отправитель мог ни разу не открыть игру — аккаунта нет
    if not u:
        return await _inline_hint(qid, "Сначала открой игру — потом сможешь отправлять чеки")
    if u["stars"] < amount + fee:
        return await _inline_hint(qid, f"Не хватает звёзд: нужно {amount + fee} ⭐ с комиссией")
    code = f"{amount}x{uid}x{secrets.token_hex(5)}"   # отправитель зашит в код — забор сможет списать сам, если feedback выкл.
    link = f"https://t.me/{BOT_NAME}?start=claim_{code}"   # главный бот — только он обрабатывает /start claim_
    res = {"type": "article", "id": code, "title": f"Перевести {amount} ⭐",
           "description": f"Комиссия {fee} ⭐ · заберёт первый, кто откроет",
           "input_message_content": {"message_text": f"💸 Чек на <b>{amount} ⭐</b> в игре GiftBot\nЗаберёт первый, кто откроет кнопкой ниже.", "parse_mode": "HTML"},
           "reply_markup": {"inline_keyboard": [[{"text": f"🎁 Получить {amount} ⭐", "url": link}]]}}
    await tg_call("answerInlineQuery", inline_query_id=qid, results=[res], cache_time=1, is_personal=True)


def reserve_cheque(uid, code):
    """chosen_inline_result: игрок реально отправил чек в чат — резервируем сумму+комиссию под этим кодом."""
    amount = _cheque_amt(code)
    if amount <= 0:
        return
    fee = _fee(amount)
    with tx():
        if q1("SELECT 1 FROM cheques WHERE code=?", code):
            return
        if not cfg("inline_on") or not cfg("on") or amount < cfg("min") or (cfg("max") and amount > cfg("max")):
            return
        if loans.stars_locked(uid):
            notify(uid, "↩️ Чек не создан: пока открыт кредит, переводить звёзды нельзя")
            return
        if __import__("sanctions").is_frozen(uid):
            notify(uid, "↩️ Чек не создан: кошелёк заморожен на время проверки")
            return
        u = q1("SELECT stars FROM users WHERE id=?", uid)
        if not u or u["stars"] < amount + fee:
            notify(uid, f"↩️ Чек на {amount} ⭐ не создан: не хватило звёзд с комиссией")
            return
        db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount + fee, uid))
        db.execute("INSERT INTO cheques(code,sender,amount,fee,created) VALUES(?,?,?,?,?)", (code, uid, amount, fee, now()))


def claim_cheque(uid, code):
    """start=claim_<код>: зачисляем первому открывшему (кроме отправителя). Возвращает dict для ответа боту."""
    with tx():
        c = q1("SELECT * FROM cheques WHERE code=?", code)
        if c:   # чек уже зарезервирован (chosen_inline_result пришёл) — просто зачисляем
            if c["refunded"]:
                return {"err": "Чек истёк и вернулся отправителю"}
            if c["claimed_by"]:
                return {"err": "Этот чек уже забрали"}
            if c["sender"] == uid:
                return {"err": "Это твой чек — его может забрать кто-то другой"}
            cu = q1("SELECT banned FROM users WHERE id=?", uid)
            if not cu or cu["banned"]:
                return {"err": "Аккаунт заблокирован"}
            if now() - c["created"] > cfg("inline_ttl_h") * 3600:
                return {"err": "Чек истёк"}
            sender, amount, fee = c["sender"], c["amount"], c["fee"]
            db.execute("UPDATE cheques SET claimed_by=?, claimed_ts=? WHERE code=?", (uid, now(), code))
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, uid))
        else:   # резерв не сработал (у бота выключен inline-feedback) — списываем с отправителя прямо сейчас
            amount, sender = _cheque_amt(code), _cheque_sender(code)
            if amount <= 0 or sender <= 0:
                return {"err": "Чек не найден или ещё не активирован — попробуй открыть чуть позже"}
            if not cfg("on") or not cfg("inline_on"):
                return {"err": "Переводы сейчас отключены"}
            if amount < cfg("min") or (cfg("max") and amount > cfg("max")):
                return {"err": "Чек недействителен"}
            if sender == uid:
                return {"err": "Это твой чек — его может забрать кто-то другой"}
            cu = q1("SELECT banned FROM users WHERE id=?", uid)
            if not cu or cu["banned"]:
                return {"err": "Аккаунт заблокирован"}
            if loans.stars_locked(sender):
                return {"err": "Отправитель сейчас не может переводить звёзды"}
            fee = _fee(amount)
            su = q1("SELECT stars FROM users WHERE id=?", sender)
            if not su or su["stars"] < amount + fee:
                return {"err": "У отправителя не хватает звёзд — чек недействителен"}
            db.execute("UPDATE users SET stars=stars-? WHERE id=?", (amount + fee, sender))
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (amount, uid))
            db.execute("INSERT INTO cheques(code,sender,amount,fee,created,claimed_by,claimed_ts) VALUES(?,?,?,?,?,?,?)",
                       (code, sender, amount, fee, now(), uid, now()))
        event(sender, "transfer", -amount)
        if fee:
            event(sender, "fee", -fee)
        event(uid, "transfer", amount)
        db.execute("INSERT INTO transfers(src,dst,amount,fee,note,ts,anon) VALUES(?,?,?,?,?,?,0)", (sender, uid, amount, fee, "чек", now()))
        snm = q1("SELECT name FROM users WHERE id=?", sender)
    rnm = q1("SELECT name FROM users WHERE id=?", uid)
    amt_s = f"{amount:,}".replace(",", " ")
    notify(sender, f"🎁 Твой чек на <b>{amt_s} ⭐</b> забрал <b>{esc(rnm['name'] if rnm else 'игрок')}</b>")
    return {"ok": True, "amount": amount, "from": snm["name"] if snm else "игрок"}


def sweep_cheques():
    """Невостребованные чеки старше inline_ttl_h — вернуть отправителю сумму+комиссию."""
    cut = now() - cfg("inline_ttl_h") * 3600
    with tx():
        rows = q("SELECT code, sender, amount, fee FROM cheques WHERE claimed_by=0 AND refunded=0 AND created<?", cut)
        for r in rows:
            db.execute("UPDATE users SET stars=stars+? WHERE id=?", (r["amount"] + r["fee"], r["sender"]))
            db.execute("UPDATE cheques SET refunded=1 WHERE code=?", (r["code"],))
    for r in rows:
        amt_s = f"{r['amount']:,}".replace(",", " ")
        notify(r["sender"], f"↩️ Чек на <b>{amt_s} ⭐</b> никто не забрал — звёзды вернулись на баланс")


async def cheque_loop():
    while True:
        await asyncio.sleep(600)
        try:
            await asyncio.get_running_loop().run_in_executor(None, sweep_cheques)
        except Exception as e:
            print("cheque sweep:", e, flush=True)


def _admin_routes():
    from admin import OWNERS, admin, log

    @app.get(R + "/admin/pay")
    def admin_pay(aid=Depends(admin)):
        since = now() - 7 * 86400
        st = q1("SELECT COUNT(*) n, COALESCE(SUM(amount),0) s, COALESCE(SUM(fee),0) f, COUNT(DISTINCT src) u FROM transfers WHERE ts>=?", since)
        top = q("SELECT src, dst, SUM(amount) s, COUNT(*) n FROM transfers WHERE ts>=? GROUP BY src, dst ORDER BY s DESC LIMIT 10", since)
        recent = q("SELECT * FROM transfers ORDER BY id DESC LIMIT 40")
        peers = {}
        b = lambda i: peers.setdefault(i, _brief(i))
        return {"cfg": {k: cfg(k) for k in DEFAULTS}, "defaults": DEFAULTS, "changed": list(CFG), "canEdit": aid in OWNERS,
                "week": {"n": st["n"], "sum": st["s"], "fee": st["f"], "users": st["u"]},
                "top": [{"a": b(r["src"]), "b": b(r["dst"]), "sum": r["s"], "n": r["n"]} for r in top if b(r["src"]) and b(r["dst"])],
                "recent": [{"a": b(r["src"]), "b": b(r["dst"]), "amount": r["amount"], "note": r["note"], "ts": r["ts"]}
                           for r in recent if b(r["src"]) and b(r["dst"])]}

    @app.post(R + "/admin/pay")
    async def admin_pay_set(req: Request, aid=Depends(admin)):
        if aid not in OWNERS:
            err("Менять настройки переводов может только владелец")
        body = await req.json()
        if not isinstance(body, dict):
            err("неверные данные")
        cur = dict(CFG)
        for k, v in body.items():
            if k not in DEFAULTS:
                continue
            if v is None:
                cur.pop(k, None)
            elif k in ("on", "inline_on"):
                cur[k] = v in (True, 1, "1", "true")
            else:
                try:
                    v = round(float(v), 4) if k in ("fee", "fee_addr") else int(v)
                except (TypeError, ValueError):
                    err("введи число")
                lo, hi = LIMITS[k]
                if not lo <= v <= hi:
                    err("недопустимое значение")
                cur[k] = v
        with tx():
            db.execute("INSERT INTO kv(k,v) VALUES('paycfg',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur),))
            log(aid, "paycfg", None, ", ".join(f"{k}={cur.get(k, DEFAULTS[k])}" for k in DEFAULTS))
        CFG.clear()
        CFG.update(cur)
        return {"ok": True}

    @app.get(R + "/admin/user/{tid}/transfers")
    def admin_transfers(tid: int, aid=Depends(admin)):
        rows = q("SELECT * FROM transfers WHERE src=? OR dst=? ORDER BY id DESC LIMIT 50", tid, tid)
        sent = q1("SELECT COALESCE(SUM(amount),0) s FROM transfers WHERE src=?", tid)["s"]
        got = q1("SELECT COALESCE(SUM(amount),0) s FROM transfers WHERE dst=?", tid)["s"]
        peers, out = {}, []
        for r in rows:
            other = r["dst"] if r["src"] == tid else r["src"]
            if other not in peers:
                peers[other] = _brief(other)
            if peers[other]:
                out.append({"in": r["dst"] == tid, "amount": r["amount"], "note": r["note"], "ts": r["ts"], "user": peers[other]})
        return {"sent": sent, "got": got, "list": out}


_admin_routes()


# ---------------- админ: смена адреса кошелька игрока (новый случайный или «красивый» свой) ----------------
from admin import admin as _admin, log as _alog   # noqa: E402


ADDR_FREE = re.compile(r"[0-9A-Z]{3,32}")


def addr_make(raw):
    """Ввод админа → адрес. Пусто — новый случайный NP…; иначе ставим ровно как ввели: латинские буквы и цифры, 3–32 знака
    (кириллицу не берём — «А» и «A» не отличить, легко подсунуть чужой адрес)."""
    s = addr_key(raw)
    if not s:
        body = "".join(secrets.choice(ADDR_ABC) for _ in range(16))
        return "NP" + body + _addr_sum(body)
    if not ADDR_FREE.fullmatch(s):
        bad = sorted({c for c in s if not ("0" <= c <= "9" or "A" <= c <= "Z")})
        err(f"нельзя символы: {' '.join(bad)} — только латинские буквы и цифры" if bad else "адрес — от 3 до 32 символов")
    return s


@app.get(R + "/admin/user/{tid}/addr")
def adm_addr(tid: int, aid=Depends(_admin)):
    q1("SELECT 1 FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
    return {"addr": addr_of(tid), "anon": addr_of(tid, "pay_anon")}


def addr_set(tid, kind, a):
    """Поставить адрес (kind: main | anon). Возвращает прежний. Вызывать внутри tx()."""
    table = "pay_anon" if kind == "anon" else "pay_addr"
    import bank
    if a == bank.bank_addr() or addr_norm(a) == bank.bank_addr():
        err("это адрес банка")
    taken = q1("SELECT user FROM pay_addr WHERE addr=? UNION SELECT user FROM pay_anon WHERE addr=?", a, a)
    if not taken and addr_norm(a):   # «NPK0…» и «NPKO…» для стандартных адресов одно и то же — не даём завести двойника
        taken = q1("SELECT user FROM pay_addr WHERE addr=? UNION SELECT user FROM pay_anon WHERE addr=?", addr_norm(a), addr_norm(a))
    if taken and taken["user"] != tid:
        err("такой адрес уже занят другим игроком")
    other = q1(f"SELECT 1 FROM {'pay_addr' if table == 'pay_anon' else 'pay_anon'} WHERE user=? AND addr=?", tid, a)
    if other:
        err("это второй адрес этого же игрока")
    old = q1(f"SELECT addr FROM {table} WHERE user=?", tid)
    db.execute(f"INSERT INTO {table}(user,addr,ts) VALUES(?,?,?) ON CONFLICT(user) DO UPDATE SET addr=excluded.addr, ts=excluded.ts", (tid, a, now()))
    return old["addr"] if old else None


@app.post(R + "/admin/user/{tid}/addr")
async def adm_addr_set(tid: int, req: Request, aid=Depends(_admin)):
    b = await req.json()
    kind = "anon" if b.get("kind") == "anon" else "main"
    a = addr_make(b.get("value", ""))
    with tx():
        q1("SELECT 1 FROM users WHERE id=?", tid) or err("нет такого игрока", 404)
        old = addr_set(tid, kind, a)
        if old == a:
            err("у игрока уже этот адрес")
        _alog(aid, "addr", tid, f"{'анонимный' if kind == 'anon' else 'адрес'}: {old or '—'} → {a}", undo={"t": "addr", "kind": kind, "prev": old})
    if kind == "main" and b.get("notify", True):
        notify(tid, f"🔑 Адрес твоего кошелька изменён администрацией.\nНовый адрес: <code>{a}</code>\nСтарый больше не принимает переводы.")
    return {"ok": True, "addr": a, "prev": old}
