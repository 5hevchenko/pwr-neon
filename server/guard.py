"""Защита от скриптов и твинков.

0. Мультиаккаунт: приложение шлёт метку устройства (случайная строка в памяти приложения на телефоне). Если новый игрок
   пришёл по ссылке с того же устройства, что и пригласивший, — это второй аккаунт того же человека: приглашение не
   засчитывается (ни бонусов, ни «друга» для бесплатного кейса), запись — в ref_blocked. Честным игрокам ничего делать не нужно.
   Обходится вторым телефоном — на этот случай остаются отпечатки адресов и тревога ниже.
1. Лимит частоты запросов на игрока («ведро с жетонами»): действий (POST) — в среднем не больше POST_RATE в секунду с запасом
   POST_BURST на серию быстрых нажатий; всех запросов игрока — ALL_RATE в секунду с запасом ALL_BURST. Человек в эти рамки
   укладывается с большим запасом (мины, башня, автоспин), скрипт — упирается и получает 429. Картинки (запросы без подписи
   игрока) не считаются. Кто и сколько раз упёрся в лимит — в таблице rl_hits (видно в разборе игрока в админке).
2. Отпечатки IP: с каких адресов заходил игрок (user_ips; сам адрес не храним — только его необратимый отпечаток). По ним
   в разборе игрока видно аккаунты с того же адреса, а владельцам приходит тревога, когда с одного адреса за сутки появилось
   несколько новых аккаунтов (ops.py: sameip). Совпадение адреса — подсказка, а не доказательство: у мобильных операторов
   и в общем Wi-Fi один адрес бывает у многих людей.
Настройки — settings.toml, раздел [guard]."""
import asyncio
import hashlib
import hmac
import re
import time

from fastapi import Request
from fastapi.responses import JSONResponse

import app as A
from app import R, app, db, now
from settings import conf
import sanctions

ON = bool(conf("guard.on", True))
POST_RATE, POST_BURST = float(conf("guard.post_per_sec", 8)), float(conf("guard.post_burst", 40))
ALL_RATE, ALL_BURST = float(conf("guard.all_per_sec", 30)), float(conf("guard.all_burst", 150))
IP_EVERY = 3600          # отметку «заходил с этого адреса» обновляем не чаще раза в час

db.executescript("""
CREATE TABLE IF NOT EXISTS user_ips(user INTEGER, ip TEXT, first INTEGER, last INTEGER, n INTEGER DEFAULT 1, PRIMARY KEY(user, ip));
CREATE INDEX IF NOT EXISTS user_ips_ip ON user_ips(ip);
CREATE TABLE IF NOT EXISTS rl_hits(user INTEGER, day INTEGER, n INTEGER DEFAULT 0, PRIMARY KEY(user, day));
CREATE TABLE IF NOT EXISTS user_devs(user INTEGER, dev TEXT, first INTEGER, PRIMARY KEY(user, dev));
CREATE INDEX IF NOT EXISTS user_devs_dev ON user_devs(dev);
CREATE TABLE IF NOT EXISTS ref_blocked(user INTEGER PRIMARY KEY, ref INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS ref_blocked_ref ON ref_blocked(ref);
""")
DEVS = set()             # (игрок, устройство), уже записанные в базу
DEV_RX = re.compile(r"^[a-f0-9]{16,40}$")
BUCKETS = {}             # ключ → [жетоны на все запросы, жетоны на действия, время]
HITS = {}                # игрок → сколько раз упёрся в лимит с прошлой записи в базу
SEEN = {}                # (игрок, отпечаток) → когда отмечали
SKIP = (R + "/tg/", R + "/admin")   # вебхуки ботов-франшиз (их шлёт Telegram) и админка


_SRC = set()


def ip_of(request):
    """Адрес игрока: его ставит прокси хостинга (x-real-ip); иначе последний адрес из x-forwarded-for (его дописал ближайший
    прокси — первые в списке игрок может подставить сам); иначе адрес соединения."""
    h = request.headers
    src, ip = next(((k, v) for k, v in (("x-real-ip", h.get("x-real-ip")), ("x-forwarded-for", (h.get("x-forwarded-for") or "").split(",")[-1]),
                                        ("соединение", request.client.host if request.client else "")) if v and v.strip()), ("нет", ""))
    if src not in _SRC:   # один раз в журнал: откуда берётся адрес (сам адрес не печатаем)
        _SRC.add(src)
        print("guard: адрес игрока берётся из:", src, flush=True)
    return ip.strip()


def ip_mark(ip):
    """Необратимый отпечаток адреса (с секретом сервера — по отпечатку адрес не восстановить и не подобрать)."""
    return hmac.new(A.SECRET, ("ip:" + ip).encode(), hashlib.sha256).hexdigest()[:16] if ip else ""


def _take(key, post):
    t = time.monotonic()
    b = BUCKETS.get(key)
    if b is None:
        if len(BUCKETS) > 50_000:   # не копим память: выбрасываем тех, кого давно не было
            for k in [k for k, v in BUCKETS.items() if t - v[2] > 120]:
                del BUCKETS[k]
        b = BUCKETS[key] = [ALL_BURST, POST_BURST, t]
    dt = t - b[2]
    b[0], b[1], b[2] = min(ALL_BURST, b[0] + dt * ALL_RATE), min(POST_BURST, b[1] + dt * POST_RATE), t
    if b[0] < 1 or (post and b[1] < 1):
        return False
    b[0] -= 1
    if post:
        b[1] -= 1
    return True


def _save():
    """Раз в минуту: счётчики «упёрся в лимит» и отметки адресов — в базу одной транзакцией."""
    hits = dict(HITS)
    HITS.clear()
    marks = [(k, v) for k, v in SEEN.items() if v[1]]
    if not hits and not marks:
        return
    day, t = A.day_start(), now()
    with A.tx():
        for uid, n in hits.items():
            db.execute("INSERT INTO rl_hits(user,day,n) VALUES(?,?,?) ON CONFLICT(user,day) DO UPDATE SET n=n+excluded.n", (uid, day, n))
        for (uid, mark), v in marks:
            db.execute("INSERT INTO user_ips(user,ip,first,last,n) VALUES(?,?,?,?,1) ON CONFLICT(user,ip) DO UPDATE SET last=excluded.last, n=n+1", (uid, mark, t, t))
            v[1] = False
        db.execute("DELETE FROM rl_hits WHERE day<?", (day - 30 * 86400,))
    if len(SEEN) > 100_000:
        SEEN.clear()
    for uid, n in hits.items():
        if n >= 20:
            print(f"guard: игрок {uid} упёрся в лимит запросов {n} раз за минуту", flush=True)


@app.middleware("http")
async def _guard(request: Request, call_next):
    path = request.url.path
    if not path.startswith(R) or path.startswith(SKIP):
        return await call_next(request)
    post = request.method == "POST"
    uid = sanctions._uid(request)
    if uid is None and not post:   # картинки и прочее без подписи игрока
        return await call_next(request)
    dev = request.headers.get("x-dev-id", "")
    if uid and DEV_RX.match(dev) and (uid, dev) not in DEVS:
        # сразу в базу (а не раз в минуту): регистрация по ссылке идёт в этом же запросе и должна видеть устройство
        mark = hmac.new(A.SECRET, ("dev:" + dev).encode(), hashlib.sha256).hexdigest()[:16]
        try:
            with A.tx():
                db.execute("INSERT OR IGNORE INTO user_devs(user,dev,first) VALUES(?,?,?)", (uid, mark, now()))
            if len(DEVS) > 200_000:
                DEVS.clear()
            DEVS.add((uid, dev))
        except Exception as e:
            print("guard dev:", type(e).__name__, e, flush=True)
    ip = ip_of(request)
    if uid and ip:
        k = (uid, ip_mark(ip))
        v = SEEN.get(k)
        if v is None or time.time() - v[0] > IP_EVERY:
            SEEN[k] = [time.time(), True]
    if ON and not _take(uid or "ip:" + ip, post):
        if uid:
            HITS[uid] = HITS.get(uid, 0) + 1
        return JSONResponse({"detail": "Слишком много запросов — подожди пару секунд"}, status_code=429, headers={"Retry-After": "2"})
    return await call_next(request)


async def _loop():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _save)
        except Exception as e:
            print("guard:", type(e).__name__, e, flush=True)


@app.on_event("startup")
async def _start():
    asyncio.create_task(_loop())


# ---------------- мультиаккаунт ----------------
def same_device(a, b):
    """Заходили ли два игрока с одного устройства."""
    return bool(A.q1("SELECT 1 FROM user_devs x JOIN user_devs y ON y.dev=x.dev WHERE x.user=? AND y.user=? LIMIT 1", a, b))


def ref_block(uid, ref):
    """Приглашение не засчитано: новый игрок uid пришёл по ссылке ref с его же устройства. Вызывается внутри транзакции регистрации."""
    db.execute("INSERT OR REPLACE INTO ref_blocked(user,ref,ts) VALUES(?,?,?)", (uid, ref, now()))
    print(f"guard: приглашение не засчитано — игрок {uid} с того же устройства, что и пригласивший {ref}", flush=True)


def same_dev(uid, limit=12):
    """Другие аккаунты с тех же устройств: [{id, name}]."""
    return [dict(r) for r in A.q("""SELECT DISTINCT b.user id, COALESCE(u.name, 'id ' || b.user) name FROM user_devs a JOIN user_devs b ON b.dev=a.dev AND b.user!=a.user
                                    LEFT JOIN users u ON u.id=b.user WHERE a.user=? LIMIT ?""", uid, limit)]


def blocked_refs(uid):
    return A.q1("SELECT COUNT(*) n FROM ref_blocked WHERE ref=?", uid)["n"]


# ---------------- для разбора игрока и тревог (ops.py) ----------------
def same_ip(uid, limit=12):
    """Другие аккаунты, заходившие с тех же адресов, что и игрок: [{id, name, shared — сколько общих адресов, last}]."""
    return [dict(r) for r in A.q("""SELECT b.user id, COALESCE(u.name, 'id ' || b.user) name, COUNT(DISTINCT b.ip) shared, MAX(b.last) last,
                                           u.ref_by ref_by, u.created created
                                    FROM user_ips a JOIN user_ips b ON b.ip=a.ip AND b.user!=a.user LEFT JOIN users u ON u.id=b.user
                                    WHERE a.user=? GROUP BY b.user ORDER BY shared DESC, last DESC LIMIT ?""", uid, limit)]


def hits(uid, days=7):
    r = A.q1("SELECT COALESCE(SUM(n),0) s FROM rl_hits WHERE user=? AND day>=?", uid, A.day_start() - days * 86400)
    return r["s"] if r else 0


def flush():
    """Для проверок и перед чтением: записать накопленное сразу."""
    _save()
