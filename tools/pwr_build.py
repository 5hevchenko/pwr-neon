"""Сборка данных слияния: кейсы и скины PWR SKINBOX (cs-bot) + кейсы RubUp Web → server/pwr/data.json и обложки.
Запуск: python tools/pwr_build.py <папка cs-bot-backend> <папка cs-bot-frontend>
Исходники: src/mock/cases.json, src/mock/cases-pass.json, public/cases/*.png, rubup-web/dist/assets/..."""
import collections
import json
import os
import re
import sys

from PIL import Image

SRC, FRONT = sys.argv[1], sys.argv[2]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server", "pwr")
ASSETS = os.path.join(OUT, "assets")
os.makedirs(ASSETS, exist_ok=True)
WEAR = {"Factory New": "FN", "Minimal Wear": "MW", "Field-Tested": "FT", "Well-Worn": "WW", "Battle-Scarred": "BS"}
KIND = {"Sticker": "Стикер", "Sealed Graffiti": "Граффити", "Music Kit": "Музыка", "Charm": "Брелок", "Patch": "Нашивка"}


def cover(src, name):
    """Обложка → квадрат 64/128/256/512 в webp (имена как у server/csgo_assets)."""
    im = Image.open(src).convert("RGBA")
    box = im.getbbox()
    if box:
        im = im.crop(box)
    s = max(im.size)
    sq = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sq.paste(im, ((s - im.width) // 2, (s - im.height) // 2), im)
    for size in (64, 128, 256, 512):
        r = sq.resize((size, size), Image.LANCZOS)
        r.save(os.path.join(ASSETS, f"{name}_{size}.webp"), quality=86, method=4)   # только webp: app._custom_asset отдаёт его и вместо png


def split(market):
    """'★ Navaja Knife | Slaughter (Field-Tested)' → ('Navaja Knife | Slaughter', 'Field-Tested')"""
    name = market.replace("★ ", "").replace("/", "-").strip()
    m = re.search(r" \(([^)]*)\)$", name)
    if m and m.group(1) in WEAR:
        return name[: m.start()], m.group(1)
    return name, None


cases = json.load(open(os.path.join(SRC, "src/mock/cases.json"), encoding="utf-8"))
cpass = json.load(open(os.path.join(SRC, "src/mock/cases-pass.json"), encoding="utf-8"))
every = [i for c in cases for i in c["items"]] + [i for t in cpass.values() for v in t.values() for i in v["items"] if i["type"] != "Coins"]
wears = collections.defaultdict(set)
for i in every:
    b, w = split(i["market_name"])
    wears[b].add(w)
cols = {}
# имена, уже занятые коллекциями игры (подарки Telegram и свои коллекции из economy.CUSTOM): скин с таким именем получает « | Vanilla»
TAKEN = set(json.load(open(os.path.join(OUT, "..", "catalog.json"), encoding="utf-8"))) | set(
    re.findall(r'^    "([^"]+)": (?:_WEAR|\[\[)', open(os.path.join(OUT, "..", "economy.py"), encoding="utf-8").read(), re.M))


def col_of(i):
    b, w = split(i["market_name"])
    name = f"{b} ({WEAR[w]})" if w and len(wears[b]) > 1 else b
    if name in TAKEN:
        name += " | Vanilla"
    kind = next((v for k, v in KIND.items() if i["type"].endswith(k) or b.startswith(k)), None)
    model = w or kind or "Коллекционный"
    img = i["image"].split("/economy/image/")[1].split("/")[0]
    cols.setdefault(name, {"m": model, "usd": i["price"], "img": img, "type": i["type"]})   # usd — справочная цена (первая встреченная)
    return name


out_cases = []
for n, c in enumerate(cases):
    cv = "sb_" + c["id"]
    cover(os.path.join(SRC, "public", "cases", os.path.basename(c["image"])), cv)
    # предметы кейса — как в SKINBOX: полный список с ценой предмета именно в этом кейсе (вес и ценность считаются от неё)
    out_cases.append({"id": "sb_" + c["id"], "sid": c["id"], "title": c["name"].replace(" Case", ""), "cover": cv, "color": c["color"],
                      "usd": c["price"], "items": [[col_of(i), i["price"]] for i in c["items"]]})

out_pass = {}
for tier, vs in cpass.items():
    out_pass[tier] = {}
    cover(os.path.join(SRC, "public", "cases", "pass", os.path.basename(vs["default"]["image"])), "pass_" + tier.lower())
    for var, c in vs.items():
        items = []
        for i in c["items"]:
            if i["type"] == "Coins":
                items.append({"coins": True, "usd": i["price"]})
            else:
                items.append({"col": col_of(i), "usd": i["price"]})
        out_pass[tier][var] = {"cover": "pass_" + tier.lower(), "color": c["color"], "items": items}

for f, name in (("battle-pass-no.png", "badge_free"), ("battle-pass-bronze.png", "badge_pwr"), ("battle-pass-gold.png", "badge_vip")):
    cover(os.path.join(FRONT, "src/shared/assets/images", f), name)

# ---- RubUp Web: 39 кейсов на подарках Telegram (состав — коллекции из case_contents.json)
RU = os.path.join(SRC, "rubup-web/dist/assets")
rc = json.load(open(os.path.join(RU, "data/case_contents.json"), encoding="utf-8"))
RENAME = {"West Coast Dog": "Snoop Dogg", "Legend's Glasses": "Durov's Glasses", "Fighter's Papakha": "Khabib's Papakha",
          "Plush Frog": "Plush Pepe", "Legend's Cap": "Durov's Cap"}
TITLES = ['Карамелька', 'Первый подарок', 'Год змеи', 'Вечеринка', 'Пекарня', 'Зимняя сказка', 'Праздничный', 'Весна', 'Сладости',
          'Уличный стиль', 'Летний вайб', 'Валентинка', 'Талисман', 'Вестсайд', 'Хэллоуин', 'Ведьмин', 'Игрушки', 'Цветочный', 'Космос',
          'Чемпион', 'Кубки', 'Мистика', 'Кибер', 'Ретро', 'Любовь', 'Бутик', 'Кольца', 'Лягушатник', 'Магия', 'Пояс и мускулы',
          'Мастерская', 'Часовщик', 'Самоцветы', 'Добыча', 'Персик', 'Медальон', 'Кепка легенды', 'Плюшевая лягушка', 'Сюрприз']
PRICES = [50, 100, 150, 200, 300, 500, 700, 1000, 1500, 2000, 3000, 5000, 7000, 10000, 15000, 20000, 30000, 50000, 70000, 100000, 150000, 200000,
          300000, 500000, 700000, 1000000, 1500000, 2000000, 3000000, 5000000, 7000000, 10000000, 20000000, 50000000, 100000000, 200000000,
          500000000, 1000000000, 0]   # цены кейсов RubUp Web (app.js), последний — бесплатный
TITLES[-1] = "Бесплатный"
catalog = json.load(open(os.path.join(OUT, "..", "catalog.json"), encoding="utf-8"))
slug = lambda x: re.sub(r"[^a-z0-9]+", "_", x.lower()).strip("_")


def real(items, name, file_slug):
    """Имя из каталога: как есть, иначе по слагу файла RubUp."""
    names = [x[0] for x in items]
    if name in names:
        return name
    return next((n for n in names if slug(n) == file_slug), None)


miss = collections.Counter()
ru_cases = []
for (cid, tiers), title, price in zip(rc["cases"].items(), TITLES, PRICES):
    out = {}
    for label, ids in tiers.items():
        out[label] = []
        for i in ids:
            g = rc["items"][i]["gift"]
            col = RENAME.get(g["collection"], g["collection"])
            d = catalog.get(col)
            if not d:
                miss["коллекция " + col] += 1
                continue
            # RubUp переименовал часть моделей и узоров; настоящее имя восстанавливаем по имени файла (anim / sym) — по нему же берётся картинка
            model = real(d["models"], g["model"], g.get("anim", "").split("__")[-1].rsplit(".", 1)[0])
            symbol = real(d["symbols"], g["symbol"], g.get("sym", "").split("__")[-1].rsplit(".", 1)[0])
            backdrop = real(d["backdrops"], g["backdrop"], "")
            for key, val in (("модель", model), ("узор", symbol), ("фон", backdrop)):
                if val is None:
                    miss[f"{key}: {col} / {g['model']} / {g['symbol']}"] += 1
            if None in (model, symbol, backdrop):
                continue
            out[label].append([col, model, backdrop, symbol, rc["items"][i]["price"]])
    cover(os.path.join(RU, "images/cases", cid + ".webp"), "ru_" + cid)
    ru_cases.append({"id": "ru_" + cid, "title": title, "cover": "ru_" + cid, "price": price, "tiers": out})
print("не найдено в каталоге:", dict(miss) or "—")

json.dump({"cols": cols, "cases": out_cases, "pass": out_pass, "rubup": ru_cases, "ru_tiers": [[t["label"], t["weight"]] for t in rc["tiers"]]},
          open(os.path.join(OUT, "data.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(cols), "скинов CS;", len(out_cases), "кейсов SKINBOX;", len(ru_cases), "кейсов RubUp;", len(os.listdir(ASSETS)), "файлов обложек")
