"""Честность: доказуемо честные результаты и публичный учёт экономики. Работает только на этом сервере —
внешних сервисов нет. Проверить результат можно в самом приложении (считает телефон игрока, сервер не участвует)
и через POST /np/api/fair/verify.

1. ЛИЧНЫЕ СИДЫ (одиночные игры, как на Stake). Серверный сид скрыт, игроку показан его SHA-256 — обязательство.
       draw(i) = HMAC_SHA256(server_seed, f"{client_seed}:{nonce}:{game}:{ref}:{i}") — первые 15 hex → [0, 1)
   Сид раскрывается при смене. ВАЖНО, иначе игру можно взломать:
   - draw до раскрытия сида наружу НЕ отдаём: из него считаются мины/этажи/точка срыва ещё идущей партии;
   - сменить сид нельзя, пока не доиграна партия с заранее брошенным результатом (мины, башня, рыбалка);
   - смена клиентского сида тоже раскрывает серверный: nonce на одной паре сидов никогда не повторяется,
     иначе «вернул старый сид → nonce сбросился → известные результаты выпали снова».

2. КРАШ — цепочка хэшей (как bustabit). Заранее считается 1 000 000 сидов: seed[k] = sha256(seed[k+1]), последний хэш
   публикуется до первого раунда. Раунды идут от конца цепочки к началу, поэтому sha256(сид раунда) == сид прошлого
   раунда: сервер физически не может подобрать «удобный» сид под раунд — вся последовательность уже зафиксирована.

3. ОБЩИЙ СИД ДНЯ (дуэли, столы, розыгрыши — где игроков несколько). Хэш публикуется заранее, сид раскрывается
   через двое суток (когда все партии того дня точно закончились).

4. УЧЁТ ЭКОНОМИКИ. Каждое изменение users.stars ловит SQL-ТРИГГЕР (обойти кодом админки нельзя) и пишет в stars_log.
   Раз в 10 минут журнал запечатывается в блок с хэшем предыдущего блока. Сверка «сумма балансов = прошлая сумма +
   изменения блока» показывается всем. Стереть или подправить запись задним числом — цепочка не сойдётся.

5. СВИДЕТЕЛИ. Телефон каждого игрока запоминает хэши блоков и при следующем входе сверяет их с сервером. Переписанная
   история разойдётся с копиями на телефонах игроков, и это сразу покажет панель.

6. РЕЗЕРВ. Дерево Меркла с суммами по балансам всех игроков: каждый может проверить, что его баланс входит в общую сумму.
"""
import asyncio
import hashlib
import hmac as hmac_mod
import json
import os
import random
import re
import secrets
import threading
import time

from fastapi import Depends, Request

from settings import conf, tuned

from app import R, app, auth, db, edge, err, kv_get, now, q, q1, qr, tg_call, tx

db.executescript("""
CREATE TABLE IF NOT EXISTS pf_seed(user INTEGER PRIMARY KEY, seed TEXT, hash TEXT, nonce INTEGER DEFAULT 0,
  bets INTEGER DEFAULT 0, created INTEGER);
CREATE TABLE IF NOT EXISTS pf_archive(hash TEXT PRIMARY KEY, user INTEGER, seed TEXT, bets INTEGER, created INTEGER, revealed INTEGER);
CREATE INDEX IF NOT EXISTS pf_archive_user ON pf_archive(user, revealed);
CREATE TABLE IF NOT EXISTS pf_bets(id INTEGER PRIMARY KEY AUTOINCREMENT, user INTEGER, hash TEXT, cs TEXT, nonce INTEGER,
  game TEXT, ref TEXT, n INTEGER, digest TEXT, stake INTEGER, pay INTEGER, res TEXT, ts INTEGER);
CREATE INDEX IF NOT EXISTS pf_bets_user ON pf_bets(user, id);
CREATE INDEX IF NOT EXISTS pf_bets_game_ts ON pf_bets(user, game, ts);
CREATE TABLE IF NOT EXISTS pf_stat(day INTEGER, game TEXT, n INTEGER DEFAULT 0, stake INTEGER DEFAULT 0, pay INTEGER DEFAULT 0,
  PRIMARY KEY(day, game));
CREATE TABLE IF NOT EXISTS pf_chain(id INTEGER PRIMARY KEY AUTOINCREMENT, master TEXT, commit_hash TEXT, size INTEGER,
  pos INTEGER DEFAULT 0, marks TEXT, created INTEGER);
CREATE TABLE IF NOT EXISTS pf_crash(chain INTEGER, pos INTEGER, round INTEGER, crash REAL, seed TEXT, edge REAL, ts INTEGER,
  PRIMARY KEY(chain, pos));
CREATE TABLE IF NOT EXISTS pf_day(day INTEGER PRIMARY KEY, seed TEXT, hash TEXT, draws INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS pf_pub(id INTEGER PRIMARY KEY AUTOINCREMENT, day INTEGER, game TEXT, ref TEXT, n INTEGER, digest TEXT, res TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS pf_odds(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, game TEXT, old REAL, new REAL, promo INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS stars_log(id INTEGER PRIMARY KEY AUTOINCREMENT, user INTEGER, delta INTEGER, after INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS ledger_block(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, last_log INTEGER, n INTEGER, net INTEGER,
  supply INTEGER, gifts INTEGER, gifts_value INTEGER, ok INTEGER, prev TEXT, hash TEXT);
CREATE TRIGGER IF NOT EXISTS stars_log_upd AFTER UPDATE OF stars ON users WHEN NEW.stars <> OLD.stars BEGIN
  INSERT INTO stars_log(user,delta,after,ts) VALUES(NEW.id, NEW.stars-OLD.stars, NEW.stars, CAST(strftime('%s','now') AS INTEGER)); END;
CREATE TRIGGER IF NOT EXISTS stars_log_ins AFTER INSERT ON users WHEN NEW.stars <> 0 BEGIN
  INSERT INTO stars_log(user,delta,after,ts) VALUES(NEW.id, NEW.stars, NEW.stars, CAST(strftime('%s','now') AS INTEGER)); END;
CREATE TRIGGER IF NOT EXISTS stars_log_del AFTER DELETE ON users WHEN OLD.stars <> 0 BEGIN
  INSERT INTO stars_log(user,delta,after,ts) VALUES(OLD.id, -OLD.stars, 0, CAST(strftime('%s','now') AS INTEGER)); END;
CREATE TABLE IF NOT EXISTS pf_witness(user INTEGER PRIMARY KEY, ts INTEGER, checked INTEGER DEFAULT 0, bad INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS pf_reserve(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, root TEXT, total TEXT, n INTEGER);
CREATE TABLE IF NOT EXISTS gift_link(gift INTEGER PRIMARY KEY, prev INTEGER);
CREATE TABLE IF NOT EXISTS gift_history(id INTEGER PRIMARY KEY AUTOINCREMENT, gift INTEGER, owner INTEGER, event TEXT, value INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS gift_history_gift ON gift_history(gift, id);
CREATE TRIGGER IF NOT EXISTS gift_h_ins AFTER INSERT ON gifts BEGIN
  INSERT INTO gift_history(gift,owner,event,value,ts) VALUES(NEW.id,NEW.owner,'mint',NEW.value,CAST(strftime('%s','now') AS INTEGER)); END;
CREATE TRIGGER IF NOT EXISTS gift_h_upd AFTER UPDATE OF owner ON gifts WHEN NEW.owner IS NOT OLD.owner BEGIN
  INSERT INTO gift_history(gift,owner,event,value,ts) VALUES(NEW.id,NEW.owner,'move',NEW.value,CAST(strftime('%s','now') AS INTEGER)); END;
CREATE TRIGGER IF NOT EXISTS gift_h_del AFTER DELETE ON gifts BEGIN
  INSERT INTO gift_history(gift,owner,event,value,ts) VALUES(OLD.id,OLD.owner,'burn',OLD.value,CAST(strftime('%s','now') AS INTEGER)); END;
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_kind_ts ON events(kind, ts);
""")
try:
    db.execute("ALTER TABLE gift_history ADD COLUMN col TEXT")
except Exception:
    pass
# триггеры истории пересоздаём, чтобы писать коллекцию
db.executescript("""
DROP TRIGGER IF EXISTS gift_h_ins; DROP TRIGGER IF EXISTS gift_h_upd; DROP TRIGGER IF EXISTS gift_h_del;
CREATE TRIGGER gift_h_ins AFTER INSERT ON gifts BEGIN
  INSERT INTO gift_history(gift,owner,event,value,ts,col) VALUES(NEW.id,NEW.owner,'mint',NEW.value,CAST(strftime('%s','now') AS INTEGER),NEW.col); END;
CREATE TRIGGER gift_h_upd AFTER UPDATE OF owner ON gifts WHEN NEW.owner IS NOT OLD.owner BEGIN
  INSERT INTO gift_history(gift,owner,event,value,ts,col) VALUES(NEW.id,NEW.owner,'move',NEW.value,CAST(strftime('%s','now') AS INTEGER),NEW.col); END;
CREATE TRIGGER gift_h_del AFTER DELETE ON gifts BEGIN
  INSERT INTO gift_history(gift,owner,event,value,ts,col) VALUES(OLD.id,OLD.owner,'burn',OLD.value,CAST(strftime('%s','now') AS INTEGER),OLD.col); END;
""")
try:
    db.execute("ALTER TABLE users ADD COLUMN client_seed TEXT")
except Exception:
    pass

SEAL_EVERY = 600
DAY_REVEAL = 2                       # сид дня раскрывается через столько суток
KEEP_BETS = 14 * 86400
KEEP_LOG = 30 * 86400
ASSET_CACHE_MAX = 300 * 1024 * 1024
CHAIN_SIZE = 1_000_000
CHAIN_MARK = 1000
HOLD_TABLES = ("mines", "tower", "fish")   # партии, где результат брошен заранее и лежит в базе


def _salt():
    s = kv_get("pf_salt", "")
    if not s:
        s = secrets.token_hex(16)
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('pf_salt',?)", (s,))
    return s


SALT = _salt()


def pseudo(uid, ts):
    """Псевдоним игрока в публичной ленте: меняется каждые сутки — нельзя собрать всю историю одного игрока."""
    return hmac_mod.new(SALT.encode(), f"{uid}:{int(ts) // 86400}".encode(), hashlib.sha256).hexdigest()[:6]


def _h(seed, msg):
    return hmac_mod.new(seed.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _to_float(hx):
    return int(hx, 16) / 16 ** 15


def digest(hexes):
    """Слепок бросков: фиксирует их в базе, но не раскрывает."""
    return _sha(",".join(hexes))[:32]


def client_seed(uid):
    u = q1("SELECT client_seed FROM users WHERE id=?", uid)
    cs = u["client_seed"] if u and u["client_seed"] else None
    if not cs:
        cs = secrets.token_hex(8)
        db.execute("UPDATE users SET client_seed=? WHERE id=?", (cs, uid))
    return cs


def _ensure(uid):
    row = q1("SELECT * FROM pf_seed WHERE user=?", uid)
    if not row:
        seed = secrets.token_hex(32)
        db.execute("INSERT INTO pf_seed(user,seed,hash,nonce,bets,created) VALUES(?,?,?,0,0,?)", (uid, seed, _sha(seed), now()))
        row = q1("SELECT * FROM pf_seed WHERE user=?", uid)
    return row


def _begin(uid, game, ref):
    s = _ensure(uid)
    nonce, cs = s["nonce"] + 1, client_seed(uid)
    db.execute("UPDATE pf_seed SET nonce=?, bets=bets+1 WHERE user=?", (nonce, uid))
    cur = db.execute("INSERT INTO pf_bets(user,hash,cs,nonce,game,ref,n,digest,ts) VALUES(?,?,?,?,?,?,0,'',?)",
                     (uid, s["hash"], cs, nonce, game, ref[:120], now()))
    return s["seed"], cs, nonce, s["hash"], cur.lastrowid


def rolls(uid, game, ref="", n=1):
    """n случайных чисел [0,1) на одну ставку. Вызывать внутри tx() ставки, после всех проверок.
    Сами числа наружу не уходят: только номер ставки и хэш сида."""
    ref = str(ref)
    seed, cs, nonce, h, bid = _begin(uid, game, ref)
    hexes = [_h(seed, f"{cs}:{nonce}:{game}:{ref[:120]}:{i}")[:15] for i in range(n)]
    d = digest(hexes)
    db.execute("UPDATE pf_bets SET n=?, digest=? WHERE id=?", (n, d, bid))
    return [_to_float(x) for x in hexes], {"id": bid, "nonce": nonce, "hash": h, "client_seed": cs, "game": game, "ref": ref[:120], "n": n, "digest": d}


def one(uid, game, ref=""):
    rs, pf = rolls(uid, game, ref, 1)
    return rs[0], pf


class FairRng(random.Random):
    """Генератор для игр с заранее неизвестным числом бросков (пёсики, кейсы, колоды): все методы random.Random,
    но каждое случайное число — следующий draw(i). Число бросков фиксируется в close()."""

    def __init__(self, seed_str, prefix):
        self._seed_str, self._prefix, self.i, self._hexes = seed_str, prefix, 0, []
        super().__init__(0)

    def seed(self, *a, **k):   # random.Random.__init__ зовёт seed(): внутренний Mersenne Twister не используется
        pass

    def _next(self):
        hx = _h(self._seed_str, f"{self._prefix}:{self.i}")[:15]
        self.i += 1
        self._hexes.append(hx)
        return hx

    def random(self):
        return _to_float(self._next())

    def getrandbits(self, k):
        out, got = 0, 0
        while got < k:
            out = (out << 60) | int(self._next(), 16)
            got += 60
        return out >> (got - k)

    def proof(self):
        return self.i, digest(self._hexes)


def stream(uid, game, ref=""):
    """Личный поток случайных чисел. После использования — close_stream()."""
    ref = str(ref)
    seed, cs, nonce, h, bid = _begin(uid, game, ref)
    rng = FairRng(seed, f"{cs}:{nonce}:{game}:{ref[:120]}")
    rng.pf = {"id": bid, "nonce": nonce, "hash": h, "client_seed": cs, "game": game, "ref": ref[:120]}
    return rng


def close_stream(rng):
    n, d = rng.proof()
    db.execute("UPDATE pf_bets SET n=?, digest=? WHERE id=?", (n, d, rng.pf["id"]))
    return {**rng.pf, "n": n, "digest": d}


def _day_seed(day):
    r = q1("SELECT * FROM pf_day WHERE day=?", day)
    if not r:
        seed = secrets.token_hex(32)
        db.execute("INSERT OR IGNORE INTO pf_day(day,seed,hash) VALUES(?,?,?)", (day, seed, _sha(seed)))
        r = q1("SELECT * FROM pf_day WHERE day=?", day)
    return r


def pub(game, ref=""):
    """Поток из общего сида дня: для игр на нескольких игроков. Результат не зависит от сида одного участника."""
    ref = str(ref)[:120]
    day = now() // 86400
    d = _day_seed(day)
    cur = db.execute("INSERT INTO pf_pub(day,game,ref,n,digest,ts) VALUES(?,?,?,0,'',?)", (day, game, ref, now()))
    rng = FairRng(d["seed"], f"{game}:{ref}:{cur.lastrowid}")
    rng.pub_id = cur.lastrowid
    return rng


def close_pub(rng, res=None):
    n, d = rng.proof()
    db.execute("UPDATE pf_pub SET n=?, digest=?, res=? WHERE id=?", (n, d, json.dumps(res, ensure_ascii=False) if res is not None else None, rng.pub_id))


def idx(r, n):
    return min(int(r * n), n - 1)


def pick(r, weights):
    tot = sum(weights)
    x, acc = r * tot, 0.0
    for i, w in enumerate(weights):
        acc += w
        if x < acc:
            return i
    return len(weights) - 1


def sample(r_list, population, k):
    pool, out = list(population), []
    for i in range(k):
        out.append(pool.pop(idx(r_list[i], len(pool))))
    return out


# ---------------- учёт ставок: заявленный возврат против фактического ----------------
KIND = {"roulette": "rlt"}


def stat(kind, stake, pay):
    g, d = KIND.get(kind, kind), now() // 86400
    db.execute("INSERT INTO pf_stat(day,game,n,stake,pay) VALUES(?,?,1,?,?) ON CONFLICT(day,game) DO UPDATE SET "
               "n=n+1, stake=stake+excluded.stake, pay=pay+excluded.pay", (d, g, int(stake), int(pay)))


def record(uid, kind, stake, pay, res=None, pf=None):
    """Итог ставки — к её записи: номер из pf или последняя незакрытая ставка этой игры."""
    body = json.dumps(res, ensure_ascii=False, separators=(",", ":")) if res is not None else None
    g = KIND.get(kind, kind)
    bid = pf["id"] if pf else (q1("SELECT id FROM pf_bets WHERE user=? AND game=? AND res IS NULL ORDER BY id DESC LIMIT 1", uid, g) or {"id": None})["id"]
    if bid:
        db.execute("UPDATE pf_bets SET stake=?, pay=?, res=? WHERE id=?", (int(stake), int(pay), body or "{}", bid))


def _done(uid, kind, stake, pay, pf=None, res=None):
    stat(kind, stake, pay)
    if pf is not None or res is not None:
        record(uid, kind, stake, pay, res, pf)


import app as _app  # noqa: E402
_app.FAIR_DONE = _done


# ---------------- цепочка хэшей краша ----------------
_CH_LOCK = threading.Lock()
_CH = {"id": 0, "marks": [], "master": "", "size": 0, "pos": 0, "commit": ""}


def _chain_new():
    master = secrets.token_hex(32)
    marks, cur = [], master
    for i in range(CHAIN_SIZE):   # marks[j] = master, прохешированный j × CHAIN_MARK раз
        if i % CHAIN_MARK == 0:
            marks.append(cur)
        cur = _sha(cur)
    with tx():
        cur_id = db.execute("INSERT INTO pf_chain(master,commit_hash,size,pos,marks,created) VALUES(?,?,?,0,?,?)",
                            (master, cur, CHAIN_SIZE, json.dumps(marks), now())).lastrowid
    return q1("SELECT * FROM pf_chain WHERE id=?", cur_id)


def _chain_load():
    with _CH_LOCK:
        if _CH["id"] and _CH["pos"] < _CH["size"] - 1:
            return
        r = q1("SELECT * FROM pf_chain ORDER BY id DESC LIMIT 1")
        if not r or r["pos"] >= r["size"] - 1:
            r = _chain_new()
        _CH.update(id=r["id"], marks=json.loads(r["marks"]), master=r["master"], size=r["size"], pos=r["pos"], commit=r["commit_hash"])


def _chain_seed(pos):
    """Сид раунда pos (1 — первый раунд): это master, прохешированный (size − pos) раз."""
    times = _CH["size"] - pos
    j = times // CHAIN_MARK
    cur = _CH["marks"][j]
    for _ in range(times - j * CHAIN_MARK):
        cur = _sha(cur)
    return cur


def crash_next():
    """Следующий сид цепочки: {seed, chain, pos}. Позиция пишется в базу ДО раунда, так что рестарт её не повторит."""
    if not _CH["id"] or _CH["pos"] >= _CH["size"] - 1:
        _chain_load()
    pos = _CH["pos"] + 1
    _CH["pos"] = pos
    db.execute("UPDATE pf_chain SET pos=? WHERE id=?", (pos, _CH["id"]))
    return {"seed": _chain_seed(pos), "chain": _CH["id"], "pos": pos}


def crash_log(chain, pos, rnd, crash, seed, e):
    db.execute("INSERT OR REPLACE INTO pf_crash(chain,pos,round,crash,seed,edge,ts) VALUES(?,?,?,?,?,?,?)",
               (chain, pos, rnd, crash, seed, e, now()))


# ---------------- публичная таблица игр ----------------
def _G(id_, title, kind, fn, how):
    return {"id": id_, "title": title, "kind": kind, "fn": fn, "how": how}


def _dogs():
    return tuned("games.dogs_rtp", round(conf("games.dogs_scale", 0.395) * 2.43, 3))


def _x():
    return edge(tuned("games.edge", 0.96))


# kind: seed — личные сиды, chain — цепочка хэшей, day — общий сид дня, skill — результат решает игрок
GAMES = [
    _G("crash", "Краш", "chain", lambda: edge(tuned("games.crash_edge", 0.96), 0.98), "Взрыв = возврат ÷ (1 − r). r — из сида раунда, сид — из заранее опубликованной цепочки хэшей."),
    _G("upgrade", "Апгрейд", "seed", lambda: edge(tuned("games.upgrade_edge", 0.92), 0.93), "Шанс = ставка ÷ цель × возврат, но не больше 80%. Победа, если r < шанса."),
    _G("mines", "Мины", "seed", lambda: edge(tuned("games.mines_edge", 0.96)), "Мины раскладываются частичным перемешиванием 25 клеток. Икс = возврат ÷ вероятность дойти до этой клетки."),
    _G("dice", "Кубик", "seed", _x, "Бросок = r × 10000 ÷ 100. Икс = возврат × 100 ÷ шанс."),
    _G("limbo", "Лимбо", "seed", _x, "Результат = возврат ÷ (1 − r). Победа, если результат не меньше цели."),
    _G("tower", "Башня", "seed", _x, "На каждом этаже мина — случайная плитка. Икс = возврат ÷ вероятность пройти этажи."),
    _G("wheel", "Колесо", "seed", lambda: tuned("games.wheel_rtp", 0.935), "Сектор = r × число секторов, все секторы равновероятны."),
    _G("slots", "Слоты", "seed", lambda: tuned("games.slots_rtp", 0.92), "Каждый барабан — символ по весам из таблицы, таблица выплат масштабируется под возврат."),
    _G("plinko", "Плинко", "seed", lambda: edge(tuned("games.plinko_rtp", 0.96)), "На каждом из 12 рядов шарик идёт влево или вправо с шансом 50/50."),
    _G("rlt", "Рулетка", "seed", lambda: 36 / 37, "Число = r × 37. Европейская рулетка с одним зеро."),
    _G("keno", "Кено", "seed", lambda: tuned("games.keno_rtp", 0.96), "Тираж — частичное перемешивание номеров. Таблица выплат масштабируется под возврат."),
    _G("chicken", "Курица", "seed", lambda: edge(tuned("games.chicken_edge", 0.96)), "На каждом шаге отдельный бросок: сбита, если r < риска шага."),
    _G("pump", "Насос", "seed", lambda: tuned("games.pump_rtp", 0.96), "На каждом качке отдельный бросок: лопнул, если r < риска шага."),
    _G("fish", "Рыбалка", "seed", lambda: edge(tuned("games.fish_rtp", 0.96)), "Точка срыва = возврат ÷ (1 − r), бросается в момент заброса."),
    _G("penalty", "Пенальти", "seed", lambda: tuned("games.penalty_rtp", 0.96), "Вратарь закрывает случайные зоны. Икс = возврат ÷ вероятность забить все."),
    _G("drill", "Бур", "seed", lambda: tuned("games.drill_rtp", 0.96), "На каждом пласте отдельный бросок на прохождение."),
    _G("darts", "Дартс", "seed", lambda: tuned("games.darts_rtp", 0.96), "Зона попадания — по весам, множители масштабируются под возврат."),
    _G("avia", "Самолётик", "seed", lambda: edge(tuned("games.avia_rtp", 0.96)), "Путь и посадка считаются из бросков ставки."),
    _G("claw", "Кран", "seed", lambda: edge(tuned("games.claw_rtp", 0.95)), "Шанс удержать приз = возврат ÷ множитель приза."),
    _G("hilo", "Больше/меньше", "seed", lambda: edge(tuned("games.hilo_edge", 0.96)), "Каждая карта — отдельный бросок. Икс = возврат ÷ шанс угадать."),
    _G("dogs", "Пёсики", "seed", _dogs, "Каждая клетка и вайлд — следующий бросок потока ставки, веса фиксированы в коде."),
    _G("scratch", "Скретч-карты", "seed", lambda: edge(tuned("games.scratch_rtp", 0.94), 0.96), "Приз определяется по таблице шансов первым броском ставки."),
    _G("case", "Кейсы", "seed", lambda: conf("economy.case_rtp", 0.88), "Коллекция — по весам кейса, вид подарка — по редкости. Шансы по коллекциям открыты ниже."),
    _G("safe", "Сейф", "seed", lambda: tuned("games.safe_rtp", 0.94), "Код — 3 броска ставки. Открыть за k попыток можно с шансом не выше (k/10)³, множители рассчитаны под возврат."),
    _G("carousel", "Карусель", "chain", lambda: tuned("games.carousel_rtp", 0.94), "Сектор — бросок из сида раунда, сиды идут отдельной цепочкой хэшей. Шанс сектора = возврат ÷ его множитель, в бонусах любой выбор даёт тот же средний возврат."),
    _G("ladder", "Лестница", "seed", lambda: tuned("games.ladder_rtp", 0.94), "Верная дверь на каждой ступени — бросок ставки, шанс 50/50. Икс = возврат × 2 в степени ступени."),
    _G("bankbet", "Ставка на банк", "skill", lambda: 1 - conf("games.bankbet_rake", 0.08), "Тотализатор: победители делят ставки проигравших. Исход — фактическое изменение банка за час без участников раунда."),
    _G("forecast", "Прогноз дня", "skill", lambda: 1 - conf("games.forecast_rake", 0.08), "Тотализатор на итоги суток: победители делят ставки проигравших. Исходы: иксы краша и бонусы Карусели из цепочек хэшей, изменение банка без участников рынка. Линия фиксируется до приёма ставок."),
    _G("craft", "Крафт", "seed", None, "Ценность результата: 72% — ×0,55–0,90, 23% — ×0,95–1,50, 5% — ×1,50–2,50 от вложенного."),
    _G("duel", "Дуэли", "day", lambda: 1 - conf("economy.duel_fee", 0.05), "Игрок против игрока, комиссия казино фиксирована. Результат — из общего сида дня."),
    _G("cards", "Карточные столы", "day", None, "Колода перемешивается из общего сида дня. Комиссия — как в дуэлях."),
    _G("jroul", "Джекпот-рулетка", "day", None, "Шанс игрока = его вклад ÷ весь банк. Билет — из общего сида дня."),
    _G("battle", "Битвы кейсов", "day", None, "Дропы и разбор ничьей — из общего сида дня."),
    _G("starfall", "Звездопад", "day", None, "Шанс = доля вклада. Победитель и приз — из общего сида дня."),
    _G("jackpot", "Розыгрыш банка", "day", None, "Шанс = доля билетов. Победители — из общего сида дня."),
    _G("stack", "Стопка", "skill", None, "Игра на ловкость: результат решают нажатия игрока, случайна только раскладка."),
]
_GI = {g["id"]: g for g in GAMES}


def declared():
    out = {}
    for g in GAMES:
        if g["fn"]:
            try:
                out[g["id"]] = round(float(g["fn"]()), 4)
            except Exception as e:
                print("fair rtp:", g["id"], e, flush=True)
    return out


def _measured(since=0):
    return {r["game"]: {"n": r["n"], "stake": r["s"], "pay": r["p"]}
            for r in q("SELECT game, SUM(n) n, SUM(stake) s, SUM(pay) p FROM pf_stat WHERE day>=? GROUP BY game", since // 86400)}


def _odds_watch():
    """Любое изменение возврата — из админки, файла настроек или акции — попадает в публичную историю автоматически."""
    cur = declared()
    try:
        last = json.loads(kv_get("pf_odds_last", "") or "{}")
    except Exception:
        last = {}
    if cur == last:
        return
    is_promo = 0
    try:
        from app import promo
        is_promo = 1 if promo() else 0
    except Exception:
        pass
    with tx():
        for k, v in cur.items():
            if last.get(k) != v:
                db.execute("INSERT INTO pf_odds(ts,game,old,new,promo) VALUES(?,?,?,?,?)", (now(), k, last.get(k), v, is_promo))
        db.execute("INSERT OR REPLACE INTO kv(k,v) VALUES('pf_odds_last',?)", (json.dumps(cur),))


# ---------------- начало учёта ----------------
def fair_from():
    """С какого момента панель показывает движения звёзд (kv 'fair_from'): всё, что было раньше, в ней не показывается."""
    return int(kv_get("fair_from", "0") or 0)


# ---------------- запечатывание журнала ----------------
def seal():
    with tx():
        last = q1("SELECT * FROM ledger_block ORDER BY id DESC LIMIT 1")
        frm = last["last_log"] if last else 0
        rows = q("SELECT id, user, delta, after, ts FROM stars_log WHERE id>? ORDER BY id", frm)
        supply = q1("SELECT COALESCE(SUM(stars),0) s FROM users")["s"]
        gifts = q1("SELECT COUNT(*) n, COALESCE(SUM(value),0) v FROM gifts")
        if last and not rows and last["supply"] == supply and last["gifts_value"] == gifts["v"]:
            return None
        net = sum(r["delta"] for r in rows)
        ok = 1 if (not last or last["supply"] + net == supply) else 0   # 0 — балансы менялись мимо журнала (триггер снят?)
        prev = last["hash"] if last else "0" * 64
        h = hashlib.sha256(prev.encode())
        for r in rows:
            h.update(f"{r['id']}:{r['user']}:{r['delta']}:{r['after']}:{r['ts']}\n".encode())
        h.update(f"{supply}:{gifts['n']}:{gifts['v']}".encode())
        hx = h.hexdigest()
        db.execute("INSERT INTO ledger_block(ts,last_log,n,net,supply,gifts,gifts_value,ok,prev,hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (now(), rows[-1]["id"] if rows else frm, len(rows), net, supply, gifts["n"], gifts["v"], ok, prev, hx))
    return hx


def audit(limit=200):
    """Пересчёт последних блоков из записей журнала: подправленная или удалённая запись не сойдётся по хэшу."""
    blocks = list(reversed(q("SELECT * FROM ledger_block ORDER BY id DESC LIMIT ?", limit)))
    broken, floor = [], (q1("SELECT MIN(id) m FROM stars_log")["m"] or 0)
    for i, b in enumerate(blocks):
        if i and b["prev"] != blocks[i - 1]["hash"]:
            broken.append({"id": b["id"], "why": "цепочка блоков разорвана"})
            continue
        frm = blocks[i - 1]["last_log"] if i else (q1("SELECT last_log FROM ledger_block WHERE id<? ORDER BY id DESC LIMIT 1", b["id"]) or {"last_log": 0})["last_log"]
        if frm + 1 < floor:   # старые записи журнала уже убраны по сроку хранения — блок проверяется только по цепочке
            continue
        h = hashlib.sha256(b["prev"].encode())
        for r in q("SELECT id, user, delta, after, ts FROM stars_log WHERE id>? AND id<=? ORDER BY id", frm, b["last_log"]):
            h.update(f"{r['id']}:{r['user']}:{r['delta']}:{r['after']}:{r['ts']}\n".encode())
        h.update(f"{b['supply']}:{b['gifts']}:{b['gifts_value']}".encode())
        if h.hexdigest() != b["hash"]:
            broken.append({"id": b["id"], "why": "записи журнала не совпадают с хэшем блока"})
        if not b["ok"]:
            broken.append({"id": b["id"], "why": "сумма балансов разошлась с журналом"})
    return {"checked": len(blocks), "broken": broken, "ok": not broken}


def _trigger_ok():
    return q1("SELECT COUNT(*) n FROM sqlite_master WHERE type='trigger' AND name IN ('stars_log_upd','stars_log_ins','stars_log_del')")["n"] == 3


def _cleanup():
    t = now()
    with tx():
        db.execute("DELETE FROM pf_bets WHERE ts<?", (t - KEEP_BETS,))
        db.execute("DELETE FROM pf_pub WHERE ts<?", (t - KEEP_BETS,))
        db.execute("DELETE FROM pf_crash WHERE ts<?", (t - KEEP_BETS,))
        db.execute("DELETE FROM stars_log WHERE ts<? AND id<=(SELECT COALESCE(MAX(last_log),0) FROM ledger_block)", (t - KEEP_LOG,))
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # кэш картинок: сверх лимита удаляем самые давно не нужные файлы
    from app import ASSET_CACHE
    try:
        files = [e for e in os.scandir(ASSET_CACHE) if e.is_file()]
        size = sum(e.stat().st_size for e in files)
        for e in sorted(files, key=lambda x: x.stat().st_mtime):
            if size <= ASSET_CACHE_MAX:
                break
            size -= e.stat().st_size
            os.remove(e.path)
    except OSError:
        pass


@app.on_event("startup")
async def _fair_start():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _chain_load)
    await loop.run_in_executor(None, _odds_watch)
    await loop.run_in_executor(None, seal)
    await loop.run_in_executor(None, reserve_build)
    asyncio.create_task(_fair_loop())


async def _fair_loop():
    loop = asyncio.get_running_loop()
    last_seal, last_clean = time.time(), time.time()
    while True:
        await asyncio.sleep(60)
        try:
            await loop.run_in_executor(None, _odds_watch)
            t = time.time()
            if t - last_seal >= SEAL_EVERY:
                last_seal = t
                await loop.run_in_executor(None, seal)
                await loop.run_in_executor(None, reserve_build)
            if t - last_clean >= 86400:
                last_clean = t
                await loop.run_in_executor(None, _cleanup)
        except Exception as e:
            print("fair loop:", e, flush=True)


# ---------------- резерв: дерево Меркла с суммами ----------------
_RES = {"levels": None, "idx": {}, "nonce": ""}


def _node(lh, ls, rh, rs):
    return _sha(f"{lh}:{ls}:{rh}:{rs}"), ls + rs


def reserve_build():
    """Снимок балансов. Лист — хэш от соли и баланса: чужие балансы из дерева не прочитать."""
    rows = q("SELECT id, stars FROM users WHERE stars>0 ORDER BY id")
    nonce = secrets.token_hex(16)
    leaves = [(_sha(f"{_res_salt(nonce, r['id'])}:{int(r['stars'])}"), int(r["stars"])) for r in rows]
    levels, cur = [leaves], leaves
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            nxt.append(_node(*cur[i], *cur[i + 1]) if i + 1 < len(cur) else cur[i])
        levels.append(nxt)
        cur = nxt
    root, total = cur[0] if cur else (_sha("empty"), 0)
    _RES.update(levels=levels, idx={r["id"]: i for i, r in enumerate(rows)}, nonce=nonce, ts=now(), root=root, total=total, balances={r["id"]: int(r["stars"]) for r in rows})
    db.execute("INSERT INTO pf_reserve(ts,root,total,n) VALUES(?,?,?,?)", (now(), root, str(total), len(rows)))
    db.execute("DELETE FROM pf_reserve WHERE id NOT IN (SELECT id FROM pf_reserve ORDER BY id DESC LIMIT 500)")


def _res_salt(nonce, uid):
    return hmac_mod.new(nonce.encode(), str(uid).encode(), hashlib.sha256).hexdigest()


def _reserve_public():
    return {"root": _RES.get("root"), "total": str(_RES.get("total", 0)), "ts": _RES.get("ts"), "n": len(_RES.get("idx", {}))}


@app.get(R + "/fair/reserve/me")
def reserve_me(uid=Depends(auth)):
    i = _RES["idx"].get(uid)
    if i is None:
        return {"included": False, **_reserve_public()}
    path = []
    for lv in _RES["levels"][:-1]:
        sib = i ^ 1
        if sib < len(lv):
            path.append({"h": lv[sib][0], "s": str(lv[sib][1]), "left": sib < i})
        i //= 2
    return {"included": True, "salt": _res_salt(_RES["nonce"], uid), "balance": str(_RES["balances"][uid]), "path": path, **_reserve_public()}


# ---------------- свидетели ----------------
def _witness_stats():
    t = now()
    return {"day": q1("SELECT COUNT(*) n FROM pf_witness WHERE ts>=?", t - 86400)["n"], "checked": q1("SELECT COALESCE(SUM(checked),0) n FROM pf_witness")["n"],
            "bad": q1("SELECT COUNT(*) n FROM pf_witness WHERE bad>0")["n"]}


@app.post(R + "/fair/witness")
async def fair_witness(req: Request, uid=Depends(auth)):
    """Телефон присылает запомненные хэши блоков, сервер отвечает текущими. Сверяет сам телефон."""
    b = await req.json()
    pairs = [(int(x[0]), str(x[1])) for x in (b.get("blocks") or [])[:200] if isinstance(x, list) and len(x) == 2]
    if b.get("v") != 3:   # старая вкладка хранит хэши журнала, который начат заново: сверять их не с чем
        pairs = []
    bad = []
    for bid, h in pairs:
        r = q1("SELECT hash FROM ledger_block WHERE id=?", bid)
        if r and r["hash"] != h:
            bad.append(bid)
    with tx():
        db.execute("INSERT INTO pf_witness(user,ts,checked,bad) VALUES(?,?,?,?) ON CONFLICT(user) DO UPDATE SET ts=excluded.ts, checked=checked+excluded.checked, bad=MAX(bad,excluded.bad)",
                   (uid, now(), len(pairs), 1 if bad else 0))
    return {"bad": bad, "checked": len(pairs), "stats": _witness_stats()}


# ---------------- API: игрок ----------------
def _open_game(uid):
    return any(q1(f"SELECT 1 FROM {t} WHERE user=?", uid) for t in HOLD_TABLES)


def _reveal(uid):
    """Раскрыть текущий серверный сид и заменить новым. Внутри tx()."""
    if _open_game(uid):
        err("Сначала доиграй партию: сид раскрывает результат, который сейчас разыгрывается")
    old = _ensure(uid)
    db.execute("INSERT OR REPLACE INTO pf_archive(hash,user,seed,bets,created,revealed) VALUES(?,?,?,?,?,?)",
               (old["hash"], uid, old["seed"], old["bets"], old["created"], now()))
    seed = secrets.token_hex(32)
    db.execute("UPDATE pf_seed SET seed=?, hash=?, nonce=0, bets=0, created=? WHERE user=?", (seed, _sha(seed), now(), uid))
    return old


def _state(uid):
    s = q1("SELECT hash, nonce, bets, created FROM pf_seed WHERE user=?", uid)
    return {"client_seed": client_seed(uid), "hash": s["hash"] if s else None, "nonce": s["nonce"] if s else 0,
            "bets": s["bets"] if s else 0, "created": s["created"] if s else None, "busy": _open_game(uid),
            "archive": [dict(r) for r in q("SELECT hash, seed, bets, created, revealed FROM pf_archive WHERE user=? ORDER BY revealed DESC LIMIT 20", uid)]}


@app.get(R + "/fair")
def fair_state(uid=Depends(auth)):
    return _state(uid)


@app.post(R + "/fair/rotate")
def fair_rotate(uid=Depends(auth)):
    with tx():
        old = _reveal(uid)
    return {**_state(uid), "old_seed": old["seed"], "old_hash": old["hash"], "old_bets": old["bets"]}


@app.post(R + "/fair/client-seed")
async def fair_client_seed(req: Request, uid=Depends(auth)):
    cs = str((await req.json()).get("seed", "")).strip()
    if not 4 <= len(cs) <= 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", cs):
        err("сид — от 4 до 64 символов: латиница, цифры, - и _")
    with tx():
        old = _reveal(uid)   # новая пара сидов: nonce на старой паре больше никогда не повторится
        db.execute("UPDATE users SET client_seed=? WHERE id=?", (cs, uid))
    return {**_state(uid), "old_seed": old["seed"], "old_hash": old["hash"], "old_bets": old["bets"]}


@app.get(R + "/fair/history")
def fair_history(limit: int = 30, before: int = 0, game: str = "", uid=Depends(auth)):
    limit = max(1, min(100, limit))
    rows = q("SELECT b.*, a.seed FROM pf_bets b LEFT JOIN pf_archive a ON a.hash=b.hash WHERE b.user=? AND (?='' OR b.game=?) AND (?=0 OR b.id<?) "
             "ORDER BY b.id DESC LIMIT ?", uid, game, game, before, before, limit)
    items = []
    for r in rows:
        g = _GI.get(r["game"])
        items.append({"id": r["id"], "game": r["game"], "title": g["title"] if g else r["game"], "nonce": r["nonce"], "hash": r["hash"], "cs": r["cs"],
                      "ref": r["ref"], "n": r["n"], "digest": r["digest"], "stake": r["stake"], "pay": r["pay"],
                      "res": json.loads(r["res"]) if r["res"] else None, "ts": r["ts"], "seed": r["seed"]})
    return {"items": items}


@app.post(R + "/fair/verify")
async def fair_verify(req: Request):
    """Проверка без авторизации. {server_seed, hash, client_seed, nonce, game, ref, n} → совпал ли хэш и какие броски."""
    b = await req.json()
    seed, h, game, ref, cs = (str(b.get(k) or "") for k in ("server_seed", "hash", "game", "ref", "client_seed"))
    try:
        nonce, n = int(b["nonce"]), max(1, min(5000, int(b.get("n", 1))))
    except (KeyError, TypeError, ValueError):
        err("нужны: server_seed, hash, client_seed, nonce, game, ref, n")
    if not seed:
        err("нет server_seed")
    hexes = [_h(seed, f"{cs}:{nonce}:{game}:{ref}:{i}")[:15] for i in range(n)]
    want = str(b.get("digest") or "")
    return {"hash_ok": _sha(seed) == h, "digest_ok": (digest(hexes) == want) if want else None,
            "r": hexes[:200], "digest": digest(hexes), "uniform": [round(_to_float(x), 8) for x in hexes[:200]]}


# ---------------- API: публичное (без входа — проверить может кто угодно) ----------------
_CACHE = {}


def _cached(key, ttl, fn):
    t = time.time()
    c = _CACHE.get(key)
    if c and t - c[0] < ttl:
        return c[1]
    v = fn()
    _CACHE[key] = (t, v)
    return v


def _public():
    d, all_, wk = declared(), _measured(), _measured(now() - 7 * 86400)
    games = []
    for g in GAMES:
        a, w = all_.get(g["id"]), wk.get(g["id"])
        games.append({"id": g["id"], "title": g["title"], "kind": g["kind"], "how": g["how"], "rtp": d.get(g["id"]),
                      "n": a["n"] if a else 0, "stake": a["stake"] if a else 0, "pay": a["pay"] if a else 0,
                      "n7": w["n"] if w else 0, "stake7": w["stake"] if w else 0, "pay7": w["pay"] if w else 0})
    b = q1("SELECT * FROM ledger_block ORDER BY id DESC LIMIT 1")
    wk_ts = now() - 7 * 86400
    start = fair_from()
    wk_ts = max(wk_ts, start)
    emis = lambda since: q1("SELECT COALESCE(SUM(delta),0) s, COUNT(*) n FROM events WHERE kind IN ('admin','admgift','comp') AND delta>0 AND ts>=?", max(since, start))
    from hub import HIST
    return {"names": HIST, "games": games, "chain": {"id": _CH["id"], "commit": _CH["commit"], "pos": _CH["pos"], "size": _CH["size"]},
            "day": {"today_hash": _day_seed(now() // 86400)["hash"]},
            "ledger": {"trigger": _trigger_ok(), "block": dict(b) if b else None, "blocks": q1("SELECT COUNT(*) n FROM ledger_block")["n"]},
            "witness": _witness_stats(), "reserve": _reserve_public(),
            "emission": {"week": dict(emis(wk_ts)), "total": dict(emis(0))},
            "sources": [dict(r) for r in q("SELECT kind, SUM(CASE WHEN delta>0 THEN delta ELSE 0 END) plus, SUM(CASE WHEN delta<0 THEN -delta ELSE 0 END) minus, COUNT(*) n "
                                           "FROM events WHERE ts>=? AND kind<>'wipe' GROUP BY kind ORDER BY plus+minus DESC LIMIT 60", wk_ts)],
            "odds": [dict(r) for r in q("SELECT ts, game, old, new, promo FROM pf_odds ORDER BY id DESC LIMIT 60")]}


@app.get(R + "/fair/public")
def fair_public():
    return _cached("public", 15, _public)


@app.get(R + "/fair/tx")
def fair_tx(before: int = 0, kind: str = "", limit: int = 40):
    """Лента движений звёзд: сумма, тип, время, суточный псевдоним. Имён и id здесь нет."""
    limit = max(1, min(100, limit))
    first = int(kv_get("fair_from_row", "0") or 0)   # по номеру записи, а не по времени: иначе пустая лента просматривала бы весь журнал
    rows = q("SELECT rowid id, user, kind, delta, ts FROM events WHERE rowid>? AND kind<>'wipe' AND (?=0 OR rowid<?) AND (?='' OR kind=?) ORDER BY rowid DESC LIMIT ?",
             first, before, before, kind, kind, limit)
    return {"items": [{"id": r["id"], "who": pseudo(r["user"], r["ts"]), "kind": r["kind"], "delta": r["delta"], "ts": r["ts"]} for r in rows]}


@app.get(R + "/fair/me-tag")
def fair_me_tag(uid=Depends(auth)):
    return {"who": pseudo(uid, now())}


@app.get(R + "/fair/journal")
def fair_journal(before: int = 0, limit: int = 40):
    """Журнал действий администрации, влияющих на экономику. Очистить его из админки нельзя."""
    limit = max(1, min(100, limit))
    rows = q("SELECT id, ts, action, target, detail FROM pub_journal WHERE ts>=? AND (?=0 OR id<?) ORDER BY id DESC LIMIT ?", fair_from(), before, before, limit)
    return {"items": [{"id": r["id"], "ts": r["ts"], "action": r["action"], "who": pseudo(r["target"], r["ts"]) if r["target"] else None, "detail": r["detail"]} for r in rows]}


@app.get(R + "/fair/blocks")
def fair_blocks(limit: int = 30):
    limit = max(1, min(200, limit))
    return {"items": [dict(r) for r in q("SELECT id, ts, n, net, supply, gifts, gifts_value, ok, prev, hash FROM ledger_block ORDER BY id DESC LIMIT ?", limit)]}


@app.get(R + "/fair/block/{bid}")
def fair_block(bid: int, limit: int = 100):
    """Блок журнала и его записи: как в обозревателе блокчейна. Вместо игроков — суточные псевдонимы."""
    b = q1("SELECT * FROM ledger_block WHERE id=?", bid) or err("нет такого блока", 404)
    p = q1("SELECT last_log FROM ledger_block WHERE id<? ORDER BY id DESC LIMIT 1", bid)
    rows = q("SELECT id, user, delta, after, ts FROM stars_log WHERE id>? AND id<=? ORDER BY id DESC LIMIT ?", p["last_log"] if p else 0, b["last_log"], max(1, min(500, limit)))
    return {"block": dict(b), "items": [{"id": r["id"], "who": pseudo(r["user"], r["ts"]), "delta": r["delta"], "after": r["after"], "ts": r["ts"]} for r in rows]}


@app.get(R + "/gift/{gid}/history")
def gift_history(gid: int, uid=Depends(auth)):
    """История подарка: кто им владел. Пишется триггерами базы при каждой смене владельца."""
    from app import user_brief
    # подарок из хранилища банка возвращается под новым номером: идём по цепочке к его прошлым записям
    ids, cur = [gid], gid
    for _ in range(20):
        p = q1("SELECT prev FROM gift_link WHERE gift=?", cur)
        if not p:
            break
        cur = p["prev"]
        ids.append(cur)
    rows = q(f"SELECT owner, event, value, ts FROM gift_history WHERE gift IN ({','.join('?' * len(ids))}) ORDER BY id DESC LIMIT 60", *ids)
    out = []
    for r in rows:
        u = q1("SELECT * FROM users WHERE id=?", r["owner"]) if r["owner"] and r["owner"] > 0 else None
        b = user_brief(u) if u else None
        out.append({"event": r["event"], "value": r["value"], "ts": r["ts"], "user": {"id": b["id"], "name": b["name"]} if b else None})
    return {"items": out}


# ---------------- счётчик подарков по коллекциям ----------------
def _gift_stats():
    # выпуск и сжигание считаются с момента ведения истории; подарок из хранилища не считается новым выпуском
    mint = {r["c"]: r["n"] for r in q("SELECT g.col c, COUNT(*) n FROM gift_history h JOIN (SELECT DISTINCT gift, col FROM gift_history WHERE col IS NOT NULL) g ON g.gift=h.gift WHERE h.event='mint' AND h.gift NOT IN (SELECT gift FROM gift_link) GROUP BY g.col")}
    burn = {r["col"]: r["n"] for r in q("SELECT col, COUNT(*) n FROM gift_history WHERE event='burn' AND col IS NOT NULL GROUP BY col")}
    alive = {r["col"]: (r["n"], r["v"]) for r in q("SELECT col, COUNT(*) n, COALESCE(SUM(value),0) v FROM gifts GROUP BY col")}
    vault = {r["c"]: r["n"] for r in q("SELECT json_extract(gift,'$.col') c, COUNT(*) n FROM bank_vault GROUP BY c")}
    rows = [{"col": c, "alive": alive.get(c, (0, 0))[0], "value": alive.get(c, (0, 0))[1], "minted": mint.get(c, 0), "burned": burn.get(c, 0), "vault": vault.get(c, 0)}
            for c in sorted(set(alive) | set(mint) | set(burn) | set(vault))]
    rows.sort(key=lambda r: -r["alive"])
    return {"items": rows, "alive": sum(r["alive"] for r in rows), "minted": sum(r["minted"] for r in rows), "burned": sum(r["burned"] for r in rows), "vault": sum(r["vault"] for r in rows)}


@app.get(R + "/fair/gifts")
def fair_gifts():
    return _cached("gifts", 60, _gift_stats)


# ---------------- страница подарка по номеру ----------------
@app.get(R + "/gift/find")
def gift_find(num: int = 0, col: str = "", limit: int = 20, uid=Depends(auth)):
    """Поиск подарка по номеру: номер уникален в пределах коллекции не всегда, поэтому возвращаем все совпадения."""
    if num <= 0:
        err("введи номер подарка")
    rows = q("SELECT * FROM gifts WHERE num=? AND (?='' OR col=?) ORDER BY id LIMIT ?", num, col, col, max(1, min(50, limit)))
    from app import gift_out
    return {"items": [{**gift_out(r), "owner": _owner(r["owner"])} for r in rows]}


def _owner(o):
    from app import user_brief
    if o and o > 0:
        u = q1("SELECT * FROM users WHERE id=?", o)
        if u:
            b = user_brief(u)
            return {"id": b["id"], "name": b["name"]}
    return None


# ---------------- отчёт банка за неделю ----------------
REPORT_GROUPS = [("Игры и кейсы", None), ("Комиссии и налоги", ("fee", "frcut", "loan")), ("Бизнесы и покупки", ("bizbuy", "bizsell", "bizgoods", "style", "mkbank", "share", "crypto", "futures", "bizmgr", "auction")),
                 ("Доходы игроков", ("income", "stake", "depint", "depfee", "div", "clanbiz", "clandiv", "clanshare", "clanprize", "clan", "clanspend")),
                 ("Бонусы и награды", ("daily", "quest", "level", "ref", "ref_lvl", "ref_ms", "ref_buy", "ref_top", "sparks", "set", "album", "onboard", "comeback", "franchise", "stack", "lucky", "flash", "cashback", "season", "tourn", "league", "jackpot", "ticket", "thanks", "bankgift", "gift")),
                 ("Выдано администрацией", ("admin", "admgift", "comp")), ("Обеспечение от покупок", ("backing",))]


def _report():
    import bank
    from app import week_start
    w0, start = week_start(), max(fair_from(), bank.bank_from())
    known = {k: g[0] for g in REPORT_GROUPS if g[1] for k in g[1]}
    weeks = []
    for i in range(8):
        a, b = w0 - i * 7 * 86400, w0 - (i - 1) * 7 * 86400
        if b <= start:
            break
        a = max(a, start)
        rows = qr(f"SELECT kind, SUM(delta) s FROM events WHERE ({bank.BANK_KINDS}) AND ts>=? AND ts<? GROUP BY kind", a, b)
        groups = {}
        for r in rows:
            g = known.get(r["kind"], "Игры и кейсы")
            groups[g] = groups.get(g, 0) - int(r["s"])   # плюс — банк заработал
        if not rows and i:
            continue
        weeks.append({"from": a, "to": min(b, now()), "net": sum(groups.values()), "groups": [{"title": k, "net": v} for k, v in sorted(groups.items(), key=lambda x: -x[1])]})
    return {"bank": bank.bank_value(), "weeks": weeks}


@app.get(R + "/fair/report")
def fair_report():
    return _cached("report", 120, _report)


@app.get(R + "/fair/audit")
def fair_audit():
    return _cached("audit", 30, lambda: {**audit(), "trigger": _trigger_ok()})


@app.get(R + "/fair/crash")
def fair_crash(limit: int = 30, before: int = 0):
    limit = max(1, min(100, limit))
    rows = q("SELECT chain, pos, round, crash, seed, edge, ts FROM pf_crash WHERE chain=? AND (?=0 OR pos<?) ORDER BY pos DESC LIMIT ?", _CH["id"], before, before, limit)
    return {"commit": _CH["commit"], "chain": _CH["id"], "pos": _CH["pos"], "size": _CH["size"], "items": [dict(r) for r in rows]}


@app.get(R + "/fair/days")
def fair_days(limit: int = 14):
    today = now() // 86400
    rows = q("SELECT day, hash, seed FROM pf_day ORDER BY day DESC LIMIT ?", max(1, min(60, limit)))
    return {"items": [{"day": r["day"], "hash": r["hash"], "seed": r["seed"] if r["day"] <= today - DAY_REVEAL else None,
                       "draws": q1("SELECT COUNT(*) n FROM pf_pub WHERE day=?", r["day"])["n"]} for r in rows]}


@app.get(R + "/fair/case/{cid}")
def fair_case(cid: str):
    """Шансы кейса: коллекция, вероятность, средняя ценность."""
    import economy as E
    c = E.CASES.get(cid) or err("нет такого кейса", 404)
    cum, prev, out = c["cum"], 0.0, []
    tot = cum[-1] if cum else 1
    for col, x in zip(c["cols"], cum):
        out.append({"col": col, "p": round((x - prev) / tot * 100, 3), "ev": round(E.expected_value(col))})
        prev = x
    out.sort(key=lambda r: -r["p"])
    return {"id": cid, "title": c.get("title"), "items": out}
