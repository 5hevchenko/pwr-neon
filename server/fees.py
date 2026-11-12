"""Все комиссии и налоги игры в одном месте — владелец меняет их на лету в админке (вкладка «Комиссии», kv 'feecfg').

Ставки по-прежнему живут константами в своих модулях (app.MARKET_FEE, crypto.FEE…), функции читают их при каждом вызове —
здесь мы просто переписываем эти константы (и их копии, импортированные через `from app import …`). По умолчанию —
то, что стояло в коде / settings.toml на момент запуска. Переводы хранятся в своём 'paycfg' (pay.py) — здесь только прокси.
"""
import json

import app as A
from app import R, app, db, err, tx
from fastapi import Depends, Request
from admin import OWNERS, admin, log
import bank as BANKMOD
import cards
import clans
import crypto
import games4
import income
import loans
import pay
import pvp

# key: (группа, название, подсказка, [(модуль, атрибут)], потолок, инверсия) — инверсия: атрибут = 1 − ставка (скупка банком)
REG = {
    "market": ("Подарки", "Маркет", "с продавца; топ-богачам и VIP — своя скидка", [(A, "MARKET_FEE")], 0.3, False),
    "sell": ("Подарки", "Мгновенная продажа банку", "сколько банк недоплачивает от ценности", [(A, "SELL_RATE")], 0.5, True),
    "trade": ("Подарки", "Обмены", "со звёзд, переданных в обмене", [(A, "TRADE_FEE")], 0.3, False),
    "transfer": ("Переводы", "Перевод по QR / ссылке", "отправитель платит сверху", "pay:fee", 0.5, False),
    "transfer_addr": ("Переводы", "Перевод по адресу NP…", "анонимный перевод", "pay:fee_addr", 0.5, False),
    "income": ("Налоги", "Налог с пассивного дохода", "доход подарков, сейф, бизнесы — в банк", [(A, "INCOME_TAX"), (income, "INCOME_TAX")], 0.5, False),
    "clan_pay": ("Кланы", "Раздача из казны", "с доли каждого участника — в банк казино", [(clans, "PAY_TAX")], 0.5, False),
    "clan_donate": ("Кланы", "Взнос в казну", "в казну доходит взнос минус налог", [(clans, "DONATE_TAX")], 0.5, False),
    "clan_max": ("Кланы", "Потолок налога клана", "налог, который глава берёт с выигрышей участников в казну", [(clans, "TAX_MAX")], 0.2, False),
    "duel": ("Игры между игроками", "Дуэли и краш-дуэли", "с банка дуэли", [(A, "DUEL_FEE"), (games4, "DUEL_FEE")], 0.2, False),
    "jackpot": ("Игры между игроками", "Джекпот", "только со звёзд банка", [(pvp, "FEE")], 0.2, False),
    "room": ("Игры между игроками", "Карточные столы", "21, 101, блэкджек на звёзды", [(cards, "ROOM_FEE")], 0.2, False),
    "crypto": ("Биржа и банк", "Крипто: покупка и продажа", "с каждой сделки", [(crypto, "FEE")], 0.05, False),
    "swap": ("Биржа и банк", "Крипто: обмен монет", "", [(crypto, "SWAP_FEE")], 0.05, False),
    "futures": ("Биржа и банк", "Фьючерсы", "от объёма при открытии и закрытии", [(crypto, "FUT_FEE")], 0.02, False),
    "stake": ("Биржа и банк", "Налог со стейкинга", "часть наград в монетах", [(crypto, "STAKE_TAX")], 0.5, False),
    "shares": ("Биржа и банк", "Продажа акций казино", "", [(BANKMOD, "SELL_FEE")], 0.2, False),
    "loan": ("Биржа и банк", "Базовая ставка по кредиту", "начальный рейтинг, 3 дня; остальные считаются от неё", [(loans, "FEE")], 1.0, False),
}
# нижние границы: скупка банком дороже 90% ценности — «станок» на сезонных скидках кейсов (Хэллоуин −15%: кейс отдаёт 90% цены)
MIN = {"sell": 0.10}


def _get(k):
    tgt, inv = REG[k][3], REG[k][5]
    if isinstance(tgt, str):
        return pay.cfg(tgt.split(":")[1])
    v = getattr(*tgt[0])
    return round(1 - v, 6) if inv else v


DEFAULTS = {k: (pay.DEFAULTS[REG[k][3].split(":")[1]] if isinstance(REG[k][3], str) else _get(k)) for k in REG}
CFG = {}


def _apply():
    for k, (_, _, _, tgt, _, inv) in REG.items():
        if isinstance(tgt, str):
            continue
        v = CFG.get(k, DEFAULTS[k])
        for mod, attr in tgt:
            setattr(mod, attr, round(1 - v, 6) if inv else v)


try:
    CFG.update({k: v for k, v in json.loads(A.kv_get("feecfg", "{}") or "{}").items() if k in REG})
    _apply()
except Exception as e:
    print("feecfg:", e, flush=True)


def public():
    """Ставки, которые фронт показывает текстом (обмены, столы, маркет, налог дохода, продажа банку)."""
    out = {k: _get(k) for k in ("market", "sell", "trade", "income", "room", "duel", "jackpot")}
    out["sell"] = round(1 - A.sell_rate(), 4)   # с поправкой курса банка
    return out


def _pct(v):
    return f"{round(v * 100, 3):g}".replace(".", ",") + "%"


@app.get(R + "/admin/fees")
def admin_fees(aid=Depends(admin)):
    t = A.now()
    fees24 = -A.q1("SELECT COALESCE(SUM(delta),0) s FROM events WHERE kind='fee' AND ts>=?", t - 86400)["s"]
    items = [{"k": k, "group": g, "title": ti, "hint": h, "v": _get(k), "def": DEFAULTS[k], "max": mx, "min": MIN.get(k, 0),
              "changed": (k in CFG) if not isinstance(tgt, str) else (tgt.split(":")[1] in pay.CFG)}
             for k, (g, ti, h, tgt, mx, _) in REG.items()]
    return {"items": items, "canEdit": aid in OWNERS, "fees24": fees24}


@app.post(R + "/admin/fees")
async def admin_fees_set(req: Request, aid=Depends(admin)):
    if aid not in OWNERS:
        err("Менять комиссии может только владелец")
    body = await req.json()
    if not isinstance(body, dict):
        err("неверные данные")
    cur, pcur, msg = dict(CFG), dict(pay.CFG), []
    for k, v in body.items():
        if k not in REG:
            continue
        tgt, mx = REG[k][3], REG[k][4]
        if v is not None:
            try:
                v = round(float(str(v).replace(",", ".").replace("%", "").strip()) / 100, 6)   # из админки приходят проценты
            except (TypeError, ValueError):
                err("введи число процентов, например 5 или 2,5")
            lo = MIN.get(k, 0)
            if not lo <= v <= mx:
                err(f"от {_pct(lo)} до {_pct(mx)}")
        if isinstance(tgt, str):
            pk = tgt.split(":")[1]
            pcur.pop(pk, None) if v is None else pcur.__setitem__(pk, v)
        else:
            cur.pop(k, None) if v is None else cur.__setitem__(k, v)
        msg.append(f"{k}={'по умолч.' if v is None else _pct(v)}")
    with tx():
        db.execute("INSERT INTO kv(k,v) VALUES('feecfg',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(cur),))
        db.execute("INSERT INTO kv(k,v) VALUES('paycfg',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (json.dumps(pcur),))
        log(aid, "feecfg", None, ", ".join(msg))
    CFG.clear()
    CFG.update(cur)
    pay.CFG.clear()
    pay.CFG.update(pcur)
    _apply()
    if "clan_max" in body:   # потолок снизили — кланы с налогом выше сразу опускаем до него
        with tx():
            db.execute("UPDATE clans SET tax=? WHERE tax>?", (clans.TAX_MAX, clans.TAX_MAX))
        clans.refresh_tax()
    return {"ok": True}
