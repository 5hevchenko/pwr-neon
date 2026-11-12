"""Картинки-карточки к уведомлениям бота: тип сообщения определяется по тексту, на фон-шаблон (web/notif/<вид>.png)
пишутся заголовок, крупное значение («+22 222 ⭐», название подарка, имя соперника) и подпись. Готовые карточки кэшируются.
Нет шаблонов/шрифтов или текст не распознан — None, бот шлёт обычное сообщение."""
import html as html_lib
import io
import os
import re
from collections import OrderedDict

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except Exception:   # без Pillow просто нет карточек
    Image = None

_HERE = os.path.dirname(os.path.abspath(__file__))
DIRS = [os.environ.get("NOTIF_DIR", ""), "/var/www/nepridymal", os.path.join(_HERE, "..", "web")]
BASE = next((d for d in DIRS if d and os.path.isfile(os.path.join(d, "notif", "stars.png"))), None)
_CACHE = OrderedDict()
_FONTS = {}

# правила: (вид, заголовок, ключевые слова в тексте) — первое совпадение
RULES = [
    ("alert", "Внимание", ["ликвидирован", "отключён", "отключен", "исключили", "не создан", "сняты", "сгорит"]),
    ("support", "Поддержка", ["поддержк", "тикет"]),
    ("clan", "Клан", ["клан"]),
    ("invite", "Твой ход", ["твой ход"]),
    ("invite", "Дуэль", ["дуэл"]),
    ("invite", "Приглашение", ["зовёт", "зовет", "приглаша"]),
    ("invite", "Обмен", ["обмен"]),
    ("win", "Джекпот!", ["джекпот"]),
    ("win", "Звездопад!", ["звездопад"]),
    ("win", "Победа!", ["выиграл", "место в розыгрыше", "побед"]),
    ("market", "Продажа на маркете", ["купил твой"]),
    ("gift", "Тебе подарок", ["подарил", "подарок от", "выдали", "открыл твой подарок", "подарок по ссылке"]),
    ("stars", "Дивиденды", ["дивиденд"]),
    ("stars", "Пассивный доход", ["пассивный доход"]),
    ("stars", "Перевод", ["перевод от", "чек"]),
    ("stars", "Оплата прошла", ["оплата прошла"]),
    ("stars", "Друг в игре", ["по твоей ссылке", "твой друг"]),
    ("event", "Праздник!", ["празд", "в честь", "ивент", "раздача", "удача", "акци", "нас уже"]),
    ("stars", "Начислено", ["начислен", "вернулись", "на баланс", "+"]),
]
AMOUNT = re.compile(r"([+\-−])?\s*(\d[\d\s  ]*\d|\d)\s*⭐")


def _font(name, size, var=None):
    key = (name, size, var)
    if key not in _FONTS:
        f = ImageFont.truetype(os.path.join(BASE, "fonts", name), size)
        if var:
            try:
                f.set_variation_by_name(var)
            except Exception:
                pass
        _FONTS[key] = f
    return _FONTS[key]


def classify(text):
    """→ (вид, заголовок, значение, есть_звезда) или None."""
    plain = html_lib.unescape(re.sub(r"<[^>]+>", "", text))
    low = plain.lower()
    kind = title = None
    for k, t, words in RULES:
        if any(w in low for w in words):
            kind, title = k, t
            break
    if not kind:
        return None
    m = AMOUNT.search(plain)
    if m:
        sign = "−" if m.group(1) in ("-", "−") else "+"
        num = re.sub(r"[\s  ]", "", m.group(2))
        if kind in ("stars", "win", "market", "event"):
            return kind, title, f"{sign}{int(num):,}".replace(",", " "), True
    bs = re.findall(r"<b>(.*?)</b>", text)   # без суммы — главное слово: у подарка — название (последнее), у остальных — имя (первое)
    b = (bs[-1] if kind == "gift" else bs[0]) if bs else None
    val = html_lib.unescape(re.sub(r"<[^>]+>", "", b)).strip() if b else ""
    if not val:
        val = {"invite": "Заходи!", "alert": "Проверь игру", "support": "Есть ответ", "clan": "Новости", "gift": "Загляни в сумку", "event": "Загляни в игру"}.get(kind, "")
    return (kind, title, val[:28], False) if val else None


def _fit(text, name, size, maxw, minsize=40, var=None):
    while size > minsize:
        f = _font(name, size, var)
        if f.getlength(text) <= maxw:
            return f
        size -= 4
    return _font(name, minsize, var)


def render(kind, title, value, star):
    key = (kind, title, value, star)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    im = Image.open(os.path.join(BASE, "notif", f"{kind}.png")).convert("RGBA")
    W, H = im.size
    d = ImageDraw.Draw(im)
    x0 = 76
    # бренд
    d.text((x0, 58), "GIFT CASES", font=_font("DelaGothicOne-Regular.ttf", 34), fill=(255, 214, 102))
    # заголовок
    ft = _font("Manrope.ttf", 50, "ExtraBold")
    d.text((x0, 190), title.upper(), font=ft, fill=(236, 226, 255))
    # значение: золотой градиент + объём + свечение
    sw = 130 if star else 0
    fv = _fit(value, "DelaGothicOne-Regular.ttf", 132, 700 - sw, 52)
    bx = d.textbbox((0, 0), value, font=fv)
    tw, th = bx[2] - bx[0], bx[3] - bx[1]
    y = 268 + (150 - th) // 2 - bx[1]
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((x0, y), value, font=fv, fill=255)
    glow = Image.new("RGBA", (W, H), (255, 150, 30, 0))
    glow.putalpha(mask.filter(ImageFilter.GaussianBlur(18)).point(lambda a: int(a * .7)))
    im = Image.alpha_composite(im, glow)
    depth = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(depth)
    for i in range(10, 0, -1):
        dd.text((x0 + i * .3, y + i), value, font=fv, fill=(37, 8, 87, 255))
    im = Image.alpha_composite(im, depth)
    grad = Image.new("RGBA", (1, 256))
    stops = [(0, (255, 251, 230)), (.28, (255, 230, 132)), (.6, (255, 187, 36)), (1, (255, 132, 0))]
    for yy in range(256):
        k = yy / 255
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if a <= k <= b:
                u = (k - a) / (b - a)
                grad.putpixel((0, yy), tuple(int(ca[c] + (cb[c] - ca[c]) * u) for c in range(3)) + (255,))
                break
    top, bot = y + bx[1], y + bx[3]
    fill = grad.resize((W, max(1, bot - top)))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(fill, (0, top))
    layer.putalpha(mask)
    im = Image.alpha_composite(im, layer)
    if star:
        s = Image.open(os.path.join(BASE, "notif", "star.png")).convert("RGBA")
        sz = int(th * 1.3)
        s = s.resize((sz, sz), Image.LANCZOS)
        im.alpha_composite(s, (int(x0 + tw + 22), int(top + (th - sz) / 2)))
    # подпись
    d = ImageDraw.Draw(im)
    d.text((x0, 488), "Игровые звёзды и подарки · не настоящие", font=_font("Manrope.ttf", 26, "SemiBold"), fill=(203, 186, 255))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=90, optimize=True)
    data = buf.getvalue()
    _CACHE[key] = data
    if len(_CACHE) > 300:
        _CACHE.popitem(last=False)
    return data


def card(text):
    """JPEG-байты карточки для текста уведомления или None."""
    if not BASE or Image is None:
        return None
    try:
        c = classify(text)
        return render(*c) if c else None
    except Exception as e:
        print("notifimg:", e, flush=True)
        return None
