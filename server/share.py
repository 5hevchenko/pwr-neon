"""Карточка большого выигрыша: картинка для чата и для сторис с реферальной ссылкой.
Сумму и множитель клиент не присылает: они берутся из журнала сервера, подарок проверяется по владельцу, поэтому подделать карточку нельзя.
Картинка открывается по случайному адресу без авторизации: её забирают серверы Telegram."""
import hashlib
import io
import math
import os
import random
import re
import secrets
import time
import urllib.parse
import urllib.request
from collections import OrderedDict

from fastapi import Depends, Request
from fastapi.responses import Response

import app as A
import notifimg as N
from app import R, app, auth, db, err, now, q1, tx
from live import NAMES

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
except Exception:
    Image = None

db.execute("""CREATE TABLE IF NOT EXISTS share_card(token TEXT PRIMARY KEY, user INTEGER, kind TEXT, amount INTEGER, x REAL,
    gift TEXT, gift_col TEXT, gift_model TEXT, name TEXT, lang TEXT DEFAULT 'ru', ts INTEGER)""")
db.execute("CREATE INDEX IF NOT EXISTS share_card_user ON share_card(user, ts)")

DAY_LIMIT = 30        # карточек в сутки на игрока
WIN_WINDOW = 900      # за сколько секунд ищем выигрыш
_CACHE = OrderedDict()
_ART_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".share_art")
_EN = {"hilo": "Hi-Lo", "jroul": "Jackpot", "avia": "Plane", "bankbet": "Bank bet", "rlt": "Roulette", "case": "Cases"}
_SAFE = re.compile(r"[^0-9A-Za-zА-Яа-яЁё _.\-]+")


def _clean(name):
    """В шрифте карточки нет эмодзи и редких символов: без них имя не превратится в квадратики."""
    s = _SAFE.sub("", name or "").strip()
    return s[:22] or "Игрок"


def _xs(x):
    return (f"x{round(x)}" if x >= 100 else f"x{x:.2f}".replace(".", ","))


def _gold(im, x, y, value, font):
    """Золотой текст с объёмом и свечением, как в уведомлениях бота."""
    W, H = im.size
    bx = ImageDraw.Draw(im).textbbox((0, 0), value, font=font)
    ty = y - bx[1]
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((x, ty), value, font=font, fill=255)
    glow = Image.new("RGBA", (W, H), (255, 150, 30, 0))
    glow.putalpha(mask.filter(ImageFilter.GaussianBlur(20)).point(lambda a: int(a * .7)))
    im = Image.alpha_composite(im, glow)
    depth = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(depth)
    for i in range(10, 0, -1):
        dd.text((x + i * .3, ty + i), value, font=font, fill=(37, 8, 87, 255))
    im = Image.alpha_composite(im, depth)
    top, bot = y, max(y + 1, y + bx[3] - bx[1])
    stops = [(0, (255, 251, 230)), (.28, (255, 230, 132)), (.6, (255, 187, 36)), (1, (255, 132, 0))]
    grad = Image.new("RGBA", (1, 256))
    for yy in range(256):
        k = yy / 255
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if a <= k <= b:
                u = (k - a) / (b - a)
                grad.putpixel((0, yy), tuple(int(ca[c] + (cb[c] - ca[c]) * u) for c in range(3)) + (255,))
                break
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(grad.resize((W, bot - top)), (0, top))
    layer.putalpha(mask)
    return Image.alpha_composite(im, layer), bx[2] - bx[0], bx[3] - bx[1]


def _star(im, x, y, size):
    s = Image.open(os.path.join(N.BASE, "notif", "star.png")).convert("RGBA").resize((size, size), Image.LANCZOS)
    im.alpha_composite(s, (int(x), int(y)))


def _pill(im, x, y, text, font, fill=(255, 255, 255, 34), color=(255, 233, 168)):
    d = ImageDraw.Draw(im)
    w = d.textlength(text, font=font)
    h = font.size + 22
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((x, y, x + w + 36, y + h), radius=h // 2, fill=fill)
    im = Image.alpha_composite(im, layer)
    ImageDraw.Draw(im).text((x + 18, y + 9), text, font=font, fill=color)
    return im, w + 36


def _gift_art(col, model, size=512):
    """Картинка модели подарка из того же источника, что и в игре. Нет сети — вернём None, будет фон с персонажем."""
    own = A.E.custom_file(col, model) if hasattr(A, "E") else None   # свои подарки (CS:GO) — с диска
    if own:
        try:
            return Image.open(f"{own}_512.png").convert("RGBA")
        except Exception:
            return None
    url = f"https://api.changes.tg/model/{urllib.parse.quote(col)}/{urllib.parse.quote(model)}.png?size={size}"
    os.makedirs(_ART_DIR, exist_ok=True)
    f = os.path.join(_ART_DIR, hashlib.md5(url.encode()).hexdigest() + ".png")
    try:
        if not os.path.exists(f):
            req = urllib.request.Request(url, headers={"User-Agent": "NePridymal/1.0"})
            data = urllib.request.urlopen(req, timeout=8).read()
            with open(f, "wb") as o:
                o.write(data)
        return Image.open(f).convert("RGBA")
    except Exception as e:
        print("share art:", e, flush=True)
        return None


def _space(W, H, seed):
    """Космос для карточек без шаблона: растянутый шаблон на сторис выглядит мыльно."""
    rnd = random.Random(seed)
    stops = [(0, (15, 7, 44)), (.5, (44, 18, 92)), (1, (19, 8, 50))]
    col = Image.new("RGB", (1, 256))
    for y in range(256):
        k = y / 255
        (a, ca), (b, cb) = (stops[0], stops[1]) if k < .5 else (stops[1], stops[2])
        u = (k - a) / (b - a)
        col.putpixel((0, y), tuple(int(ca[c] + (cb[c] - ca[c]) * u) for c in range(3)))
    im = col.resize((W, H), Image.BICUBIC).convert("RGBA")
    blobs = Image.new("RGBA", (W // 4, H // 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(blobs)
    for _ in range(5):
        x, y, r = rnd.randint(0, W // 4), rnd.randint(0, H // 4), rnd.randint(W // 12, W // 5)
        d.ellipse((x - r, y - r, x + r, y + r), fill=rnd.choice([(120, 60, 230, 46), (225, 70, 190, 30), (70, 90, 240, 38)]))
    im = Image.alpha_composite(im, blobs.filter(ImageFilter.GaussianBlur(40)).resize((W, H), Image.BICUBIC))
    d = ImageDraw.Draw(im)
    for _ in range(W * H // 14000):
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.choice([1, 1, 1, 2, 2, 3])
        v = rnd.randint(110, 240)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(v, v, 255, 255))
    return im


def _halo(im, c, r):
    """Сияние за героем карточки: мягкие лучи, фиолетовое свечение и тёплая середина."""
    W, H = im.size
    k = 3
    sm = (W // k, H // k)
    cx, cy, rr = c[0] / k, c[1] / k, r / k
    rays = Image.new("L", sm, 0)
    d = ImageDraw.Draw(rays)
    for i in range(20):
        a = i / 20 * math.tau
        L = rr * 2.1
        d.polygon([(cx, cy), (cx + L * math.cos(a - .06), cy + L * math.sin(a - .06)), (cx + L * math.cos(a + .06), cy + L * math.sin(a + .06))], fill=64)
    fade = Image.new("L", sm, 0)
    ImageDraw.Draw(fade).ellipse((cx - rr * 2, cy - rr * 2, cx + rr * 2, cy + rr * 2), fill=255)
    fade = fade.filter(ImageFilter.GaussianBlur(rr * .55))
    rays = ImageChops.multiply(rays.filter(ImageFilter.GaussianBlur(3)), fade)
    glow = Image.new("L", sm, 0)
    ImageDraw.Draw(glow).ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=170)
    glow = glow.filter(ImageFilter.GaussianBlur(rr * .42))
    core = Image.new("L", sm, 0)
    ImageDraw.Draw(core).ellipse((cx - rr * .55, cy - rr * .55, cx + rr * .55, cy + rr * .55), fill=120)
    core = core.filter(ImageFilter.GaussianBlur(rr * .3))
    for mask, color in ((rays, (205, 170, 255)), (glow, (136, 84, 255)), (core, (255, 196, 120))):
        layer = Image.new("RGBA", (W, H), color + (0,))
        layer.putalpha(mask.resize((W, H), Image.BICUBIC))
        im = Image.alpha_composite(im, layer)
    return im


def _sparkles(im, pts):
    """Четырёхлучевые искры, как на шаблоне с лягушкой."""
    W, H = im.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x, y, r in pts:
        t = r * .13
        d.polygon([(x, y - r), (x + t, y - t), (x + r, y), (x + t, y + t), (x, y + r), (x - t, y + t), (x - r, y), (x - t, y - t)], fill=(255, 255, 255, 255))
    glow = layer.filter(ImageFilter.GaussianBlur(9))
    return Image.alpha_composite(Image.alpha_composite(im, glow), layer)


def _frame(im):
    W, H = im.size
    ImageDraw.Draw(im).rectangle((0, 0, W - 1, H - 1), outline=(224, 176, 78), width=7)
    return im


def _paste_art(im, art, c, box):
    k = box / max(art.size)
    a = art.resize((int(art.width * k), int(art.height * k)), Image.LANCZOS)
    x, y = c[0] - a.width // 2, c[1] - a.height // 2
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.paste((12, 0, 40, 170), (x + box // 60, y + box // 28), a.split()[3])
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(box // 30)))
    im.alpha_composite(a, (x, y))
    return im


def _frog(tpl):
    """Лягушка с шаблона: вырезка с растворением по кругу, чтобы края не читались как квадрат."""
    cut = tpl.crop((740, 55, 1270, 585)).convert("RGBA")
    m = Image.new("L", cut.size, 0)
    ImageDraw.Draw(m).ellipse((22, 22, cut.width - 22, cut.height - 22), fill=255)
    cut.putalpha(m.filter(ImageFilter.GaussianBlur(12)))
    return cut


def _center(im, text, y, font, fill):
    d = ImageDraw.Draw(im)
    d.text(((im.width - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)


def render(c, portrait=False):
    key = (c["token"], portrait)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    art = _gift_art(c["gift_col"], c["gift_model"]) if c["gift_col"] else None
    en = c.get("lang") == "en"
    title = (c["gift"] or "Gift") if c["gift_col"] else (_EN.get(c["kind"], c["kind"].capitalize()) if en else NAMES.get(c["kind"], "Игра"))
    value = f"{'' if c['gift_col'] else '+'}{c['amount']:,}".replace(",", " ")
    sub = ("Gift drop" if c["gift_col"] else "Big win") if en else ("Выпал подарок" if c["gift_col"] else "Большой выигрыш")
    chips = [title] + ([_xs(c["x"])] if c["x"] else [])
    line = "In-game stars and gifts · not real" if en else "Игровые звёзды и подарки · не настоящие"
    bot = "@" + c["bot"]
    gold, lilac, soft = (255, 214, 102), (203, 186, 255), (236, 226, 255)
    tpl = Image.open(os.path.join(N.BASE, "notif", "win.png")).convert("RGB")
    if portrait:
        W, H = 1080, 1920
        im = _space(W, H, c["token"])
        cx, cy = W // 2, 680
        im = _halo(im, (cx, cy), 400)
        if art:
            im = _paste_art(im, art, (cx, cy), 780)
        else:
            im = _paste_art(im, _frog(tpl), (cx, cy), 930)
        im = _sparkles(im, [(190, 400, 46), (900, 470, 34), (150, 900, 28), (930, 950, 42), (320, 300, 18), (790, 280, 22)])
        _center(im, "GIFT CASES", 150, N._font("DelaGothicOne-Regular.ttf", 54), gold)
        _center(im, sub.upper(), 1130, N._font("Manrope.ttf", 46, "ExtraBold"), soft)
        fv = N._fit(value, "DelaGothicOne-Regular.ttf", 170, W - 300, 70)
        tw = ImageDraw.Draw(im).textlength(value, font=fv)
        sz = 130
        im, tw, th = _gold(im, int((W - tw - sz - 16) / 2), 1215, value, fv)
        _star(im, (W - tw - sz - 16) / 2 + tw + 16, 1215 + (th - sz) / 2, sz)
        fp = N._font("Manrope.ttf", 40, "Bold")
        widths = [ImageDraw.Draw(im).textlength(p, font=fp) + 36 for p in chips]
        px = (W - sum(widths) - 14 * (len(chips) - 1)) / 2
        for p in chips:
            im, w = _pill(im, int(px), 1420, p, fp)
            px += w + 14
        _center(im, _clean(c["name"]), 1520, N._font("Manrope.ttf", 42, "SemiBold"), (255, 255, 255))
        _center(im, bot, 1610, N._font("Manrope.ttf", 46, "ExtraBold"), gold)
        _center(im, line, 1690, N._font("Manrope.ttf", 28, "SemiBold"), lilac)
    else:
        W, H = 1280, 640
        if art:
            night = tpl.crop((10, 10, 640, 630))
            bg = Image.new("RGB", (night.width * 2, night.height))
            bg.paste(night, (0, 0))
            bg.paste(ImageOps.mirror(night), (night.width, 0))
            im = bg.resize((W, H), Image.LANCZOS).convert("RGBA")
            im = _halo(im, (985, 320), 250)
            im = _paste_art(im, art, (985, 320), 450)
            im = _sparkles(im, [(760, 150, 28), (1215, 120, 22), (1205, 505, 26), (745, 500, 16)])
            _frame(im)
        else:
            im = tpl.convert("RGBA")
        x0 = 76
        d = ImageDraw.Draw(im)
        d.text((x0, 58), "GIFT CASES", font=N._font("DelaGothicOne-Regular.ttf", 34), fill=gold)
        d.text((x0, 170), sub.upper(), font=N._font("Manrope.ttf", 42, "ExtraBold"), fill=soft)
        fv = N._fit(value, "DelaGothicOne-Regular.ttf", 122, 580, 52)
        im, tw, th = _gold(im, x0, 240, value, fv)
        sz = min(100, int(th * 1.15))
        _star(im, x0 + tw + 18, 240 + (th - sz) / 2, sz)
        fp = N._font("Manrope.ttf", 30, "Bold")
        px = x0
        for p in chips:
            im, w = _pill(im, int(px), 372, p, fp)
            px += w + 10
        d = ImageDraw.Draw(im)
        d.text((x0, 450), _clean(c["name"]), font=N._font("Manrope.ttf", 32, "SemiBold"), fill=(255, 255, 255))
        d.text((x0, 496), bot, font=N._font("Manrope.ttf", 32, "ExtraBold"), fill=gold)
        d.text((x0, 556), line, font=N._font("Manrope.ttf", 24, "SemiBold"), fill=lilac)
    if portrait:
        _frame(im)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=90, optimize=True)
    data = buf.getvalue()
    _CACHE[key] = data
    if len(_CACHE) > 40:
        _CACHE.popitem(last=False)
    return data


def _find_win(uid, pay):
    """Выигрыш из памяти сервера (там есть ставка, значит, и честный множитель), иначе из журнала."""
    t = now()
    wins = [w for w in A.RECENT_WINS.get(uid, []) if t - w[3] <= WIN_WINDOW]
    if wins:
        w = min(wins, key=lambda w: abs(w[2] + w[1] - pay)) if pay else max(wins, key=lambda w: w[2])
        return w[0], w[2], round((w[2] + w[1]) / w[1], 2) if w[1] > 0 else None
    r = q1(f"SELECT kind, delta FROM events WHERE user=? AND ts>=? AND delta>0 AND kind IN {A.GAME_KINDS} ORDER BY delta DESC LIMIT 1", uid, t - WIN_WINDOW)
    return (r["kind"], r["delta"], None) if r else None


@app.post(R + "/share/win")
async def share_win(req: Request, uid=Depends(auth)):
    if Image is None or not N.BASE:
        err("Карточки сейчас недоступны")
    try:
        body = await req.json()
    except Exception:
        body = {}
    t = now()
    lang = "en" if body.get("lang") == "en" else "ru"
    if q1("SELECT COUNT(*) n FROM share_card WHERE user=? AND ts>=?", uid, t - 86400)["n"] >= DAY_LIMIT:
        err("На сегодня карточек хватит, загляни завтра")
    u = q1("SELECT * FROM users WHERE id=?", uid)
    name = A.user_brief(u)["name"]
    kind, amount, x, gname, col, model = "", 0, None, None, None, None
    gid = body.get("gift")
    if gid:
        g = q1("SELECT * FROM gifts WHERE id=? AND owner=?", int(gid), uid) or err("Подарок не найден")
        kind, amount, gname, col, model = "gift", g["value"], g["col"], g["col"], g["model"]
    else:
        w = _find_win(uid, int(body.get("pay") or 0)) or err("Выигрыш не найден")
        kind, amount, x = w
    token = secrets.token_urlsafe(12)
    with tx():
        db.execute("INSERT INTO share_card(token,user,kind,amount,x,gift,gift_col,gift_model,name,lang,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (token, uid, kind, amount, x, gname, col, model, name, lang, t))
        db.execute("DELETE FROM share_card WHERE ts<?", (t - 30 * 86400,))
    base = A.APP_URL.rstrip("/") + "/api/share/img/" + token
    bot = A.bot_name()
    link = f"https://t.me/{bot}?start=ref_{uid}"
    num = f"{amount:,}".replace(",", " ")
    if lang == "en":
        text = (f"Look what dropped: {gname}. " if gname else f"Look at this win: {num} stars. ") + "Come and try it too"
    else:
        text = (f"Смотри, какой подарок выпал: {gname}. " if gname else f"Смотри, какой занос: {num} звёзд. ") + "Залетай, попробуй тоже"
    prepared = None
    try:
        import franchise
        tok = franchise.token_for(uid)
        res = await A.tg_call("savePreparedInlineMessage", _token=tok, user_id=uid, allow_user_chats=True, allow_group_chats=True, allow_channel_chats=True,
                              result={"type": "photo", "id": token[:32], "photo_url": base + ".jpg", "thumbnail_url": base + ".jpg", "photo_width": 1280, "photo_height": 640,
                                      "caption": text, "reply_markup": {"inline_keyboard": [[{"text": "Играть", "url": link}]]}})
        if res.get("ok"):
            prepared = res["result"]["id"]
        else:
            print("share prepare:", res.get("description"), flush=True)
    except Exception as e:
        print("share prepare:", e, flush=True)
    return {"prepared": prepared, "img": base + ".jpg", "story": base + "_s.jpg", "link": link, "text": text,
            "page": A.APP_URL.rstrip("/") + "/api/share/p/" + token}


@app.get(R + "/share/img/{name}")
def share_img(name: str):
    m = re.fullmatch(r"([A-Za-z0-9_\-]{16})(_s)?\.jpg", name)
    if not m:
        return Response(status_code=404)
    r = q1("SELECT * FROM share_card WHERE token=?", m.group(1))
    if not r:
        return Response(status_code=404)
    try:
        data = render({**dict(r), "bot": A.bot_name()}, portrait=bool(m.group(2)))
    except Exception as e:
        print("share render:", e, flush=True)
        return Response(status_code=500)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


# ---------------- публичная страница карточки: открывается в любом браузере, превью ссылки — сама карточка ----------------
_PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><meta name="description" content="{desc}">
<meta property="og:type" content="website"><meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:image" content="{img}"><meta property="og:image:width" content="1280"><meta property="og:image:height" content="640">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{img}">
<style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;background:radial-gradient(120% 80% at 50% 0%,#2a1f6e,#0b0a14 70%);
font:16px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#f3f0ff}}
main{{width:100%;max-width:560px;text-align:center}}
img{{display:block;width:100%;height:auto;border-radius:20px;box-shadow:0 18px 50px rgba(0,0,0,.5)}}
h1{{margin:20px 0 6px;font-size:22px;line-height:1.25}}p{{margin:0 0 20px;color:#c9c2e6}}
a.go{{display:inline-flex;align-items:center;justify-content:center;gap:8px;width:100%;max-width:360px;padding:15px 20px;border-radius:16px;text-decoration:none;
font-weight:800;font-size:17px;color:#2a1700;background:linear-gradient(180deg,#ffe08a,#ffb020);box-shadow:0 8px 24px rgba(255,176,32,.35)}}
small{{display:block;margin-top:14px;color:#8d86ad;font-size:12.5px}}
</style></head><body><main><img src="{img}" alt="{title}" width="1280" height="640">
<h1>{title}</h1><p>{desc}</p><a class="go" href="{link}">{btn}</a><small>{note}</small></main></body></html>"""


@app.get(R + "/share/p/{token}")
def share_page(token: str):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{16}", token):
        return Response(status_code=404)
    r = q1("SELECT * FROM share_card WHERE token=?", token)
    if not r:
        return Response(status_code=404)
    import html as H
    en = r["lang"] == "en"
    num = f"{r['amount']:,}".replace(",", " ")
    if r["gift"]:
        title = (f"{r['name']} got {r['gift']}" if en else f"{r['name']}: выпал {r['gift']}")
    else:
        title = (f"{r['name']} won {num} stars" if en else f"{r['name']}: выигрыш {num} звёзд")
    desc = "Open cases, catch rare Telegram gifts and play mini games." if en else "Открывай кейсы, лови редкие подарки Telegram и играй в мини-игры."
    base = A.APP_URL.rstrip("/") + "/api/share/img/" + token
    link = f"https://t.me/{A.bot_name()}?start=ref_{r['user']}"
    page = _PAGE.format(lang="en" if en else "ru", title=H.escape(title), desc=H.escape(desc), img=H.escape(base + ".jpg"), link=H.escape(link),
                        btn="Play in Telegram" if en else "Играть в Telegram",
                        note="Stars here are in-game currency." if en else "Звёзды в игре игровые.")
    return Response(page, media_type="text/html; charset=utf-8", headers={"Cache-Control": "public, max-age=3600"})
