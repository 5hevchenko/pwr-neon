"""Клиент площадки подарков Tonnel (market.tonnel.network): только то, что нужно игре — цены, покупка, баланс.

Официального API у площадки нет: это те же запросы, что делает её мини-приложение (разобраны в открытой библиотеке tonnelmp, MIT).
  · listings(name)  — самые дешёвые предложения по названию подарка, цена в TON без комиссии (сессия не нужна);
  · buy(id, price, receiver) — купить предложение сразу на аккаунт игрока (нужна сессия и TON на балансе площадки);
    площадка берёт сверху комиссию 10% от цены;
  · balance() — баланс TON на площадке (нужна сессия).
Сессия — переменная окружения TONNEL_AUTH (строка web-initData из мини-приложения площадки). В коде и в базе её нет.
Площадка стоит за Cloudflare, обычный HTTP-клиент получает 403 — поэтому curl_cffi с отпечатком браузера."""
import base64
import hashlib
import json
import os
import time

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

try:
    from curl_cffi.requests import AsyncSession
except ImportError:   # библиотека не поставилась — коллекционные подарки просто выключены
    AsyncSession = None

AUTH = os.environ.get("TONNEL_AUTH", "").strip()
API = os.environ.get("TONNEL_URL", "https://gifts2.tonnel.network/api/")       # TONNEL_URL / TONNEL_BUY_URL — только для тестов
BUY = os.environ.get("TONNEL_BUY_URL", "https://gifts.coffin.meme/api/")
FEE = 0.10                                     # комиссия площадки сверху цены
_PASS = b"yowtfisthispieceofshitiiit"          # ключ подписи времени из клиента площадки (не секрет: он зашит в её сайт)
_HEAD = {"accept": "*/*", "content-type": "application/json", "origin": "https://market.tonnel.network", "referer": "https://market.tonnel.network/"}


class TonnelError(Exception):
    pass


def available():
    return AsyncSession is not None


def has_session():
    return bool(AUTH and AsyncSession)


def _wtf():
    """Подпись запроса на покупку: текущее время, зашифрованное AES-CBC в формате OpenSSL «Salted__» (как CryptoJS в клиенте)."""
    ts = str(int(time.time()))
    salt = os.urandom(8)
    d, prev = b"", b""
    while len(d) < 48:
        prev = hashlib.md5(prev + _PASS + salt).digest()
        d += prev
    p = padding.PKCS7(128).padder()
    enc = Cipher(algorithms.AES(d[:32]), modes.CBC(d[32:48])).encryptor()
    ct = enc.update(p.update(ts.encode()) + p.finalize()) + enc.finalize()
    return ts, base64.b64encode(b"Salted__" + salt + ct).decode()


PROXY = os.environ.get("TONNEL_PROXY", "").strip()   # http://user:pass@host:port — если площадка не пускает запросы с адреса сервера
_PROFILES = ["chrome110", "chrome", "safari", "chrome131_android"]   # отпечатки браузера: первый — тот, с которым работает tonnelmp
_UA110 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
_STATE = {"profile": 0, "logged": False}


async def _try(url, payload, timeout, profile):
    head = dict(_HEAD, **{"accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7", "sec-fetch-dest": "empty", "sec-fetch-mode": "cors",
                          "sec-fetch-site": "same-site"})
    if profile == "chrome110":
        head["user-agent"] = _UA110
    kw = {"proxies": {"https": PROXY, "http": PROXY}} if PROXY else {}
    async with AsyncSession(impersonate=profile, **kw) as s:
        return await s.post(url, headers=head, json=payload, timeout=timeout)


async def _post(url, payload, timeout=15, retry=True):
    """Запрос к площадке. На 403 от защиты (только для безопасных к повтору запросов) пробуем другие отпечатки браузера и запоминаем рабочий."""
    if AsyncSession is None:
        raise TonnelError("curl_cffi не установлен")
    order = [_STATE["profile"]] + ([i for i in range(len(_PROFILES)) if i != _STATE["profile"]] if retry else [])
    r = None
    for i in order:
        try:
            r = await _try(url, payload, timeout, _PROFILES[i])
        except Exception as e:
            raise TonnelError(f"нет связи: {type(e).__name__}") from e
        if r.status_code not in (403, 429):
            _STATE["profile"] = i
            break
    if r.status_code in (403, 429):
        if not _STATE["logged"]:   # один раз — что именно ответила защита (страница проверки, запрет адреса…)
            _STATE["logged"] = True
            import re
            t = r.text
            print("tonnel 403:", {k: v for k, v in r.headers.items() if k.lower() in ("server", "cf-mitigated")},
                  "| title:", (re.findall(r"<title>(.*?)</title>", t, re.S) or [""])[0].strip()[:80],
                  "| code:", re.findall(r"(?:Error code|error code:?)\s*<?[^0-9]{0,40}(\d{4})", t)[:2] or re.findall(r"\b(10\d\d)\b", t)[:3],
                  "| h:", [" ".join(re.sub(r"<[^>]+>", " ", x).split())[:90] for x in re.findall(r"<h[12][^>]*>(.*?)</h[12]>", t, re.S)[:3]], flush=True)
        raise TonnelError(f"площадка отклонила запрос ({r.status_code}, защита Cloudflare)")
    if r.status_code != 200:
        raise TonnelError(f"ответ {r.status_code}")
    try:
        return r.json()
    except Exception as e:
        raise TonnelError("ответ не разобран") from e


async def listings(name, limit=5):
    """Самые дешёвые предложения подарка: [{id, price (TON, без комиссии), model, backdrop, num}] по возрастанию цены."""
    flt = {"price": {"$exists": True}, "buyer": {"$exists": False}, "asset": "TON", "refunded": {"$ne": True},
           "export_at": {"$exists": True}, "gift_name": name}
    r = await _post(API + "pageGifts", {"filter": json.dumps(flt), "limit": limit, "page": 1, "sort": '{"price":1,"gift_id":-1}',
                                        "ref": 0, "user_auth": AUTH, "price_range": 0})
    if not isinstance(r, list):
        raise TonnelError("неожиданный ответ на список")
    out = []
    for g in r:
        try:
            if g.get("auction") or float(g["price"]) <= 0:
                continue
            out.append({"id": int(g["gift_id"]), "price": float(g["price"]), "model": str(g.get("model") or ""),
                        "backdrop": str(g.get("backdrop") or ""), "num": g.get("gift_num")})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda x: x["price"])


async def buy(gift_id, price, receiver):
    """Купить предложение на аккаунт игрока. → (True, "") куплено; (False, причина) площадка отказала — деньги не списаны.
    TonnelError — ответа нет, исход неизвестен: такую заявку разбирает человек."""
    ts, wtf = _wtf()
    r = await _post(f"{BUY}buyGift/{int(gift_id)}", {"authData": AUTH, "asset": "TON", "price": float(price), "timestamp": ts, "wtf": wtf,
                                                     "receiver": int(receiver), "anonymously": True, "showPrice": False}, timeout=25, retry=False)
    if isinstance(r, dict) and r.get("status") == "success":
        return True, ""
    return False, str((r or {}).get("message") or r)[:200] if isinstance(r, dict) else str(r)[:200]


async def balance():
    """Баланс TON на площадке; TonnelError — сессия не принята или площадка недоступна."""
    r = await _post(API + "balance/info", {"authData": AUTH})
    if not isinstance(r, dict) or r.get("status") != "success":
        raise TonnelError("сессия не принята: " + str((r or {}).get("message") if isinstance(r, dict) else r)[:120])
    return float(r.get("balance") or 0)
