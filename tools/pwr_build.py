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


def col_of(i):
    b, w = split(i["market_name"])
    name = f"{b} ({WEAR[w]})" if w and len(wears[b]) > 1 else b
    kind = next((v for k, v in KIND.items() if i["type"].endswith(k) or b.startswith(k)), None)
    model = w or kind or "Коллекционный"
    img = i["image"].split("/economy/image/")[1].split("/")[0]
    old = cols.get(name)
    if old and abs(old["usd"] - i["price"]) > 1e-9:   # один предмет с разной ценой в разных кейсах — берём среднее
        old["usd"] = round((old["usd"] + i["price"]) / 2, 4)
    cols.setdefault(name, {"m": model, "usd": i["price"], "img": img, "type": i["type"]})
    return name


LEVELS = [1, 1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16]
out_cases = []
for n, c in enumerate(cases):
    cv = "sb_" + c["id"]
    cover(os.path.join(SRC, "public", "cases", os.path.basename(c["image"])), cv)
    names = []
    for i in c["items"]:
        x = col_of(i)
        if x not in names:
            names.append(x)
    out_cases.append({"id": "sb_" + c["id"], "title": c["name"].replace(" Case", ""), "cover": cv, "color": c["color"],
                      "usd": c["price"], "level": LEVELS[n], "cols": names})

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
ru_cases = []
for (cid, tiers), title in zip(rc["cases"].items(), TITLES):
    names = []
    for ids in tiers.values():
        for i in ids:
            x = rc["items"][i]["gift"]["collection"]
            x = RENAME.get(x, x)
            if x not in names:
                names.append(x)
    cover(os.path.join(RU, "images/cases", cid + ".webp"), "ru_" + cid)
    ru_cases.append({"id": "ru_" + cid, "title": title, "cover": "ru_" + cid, "cols": names})

json.dump({"cols": cols, "cases": out_cases, "pass": out_pass, "rubup": ru_cases},
          open(os.path.join(OUT, "data.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(cols), "скинов CS;", len(out_cases), "кейсов SKINBOX;", len(ru_cases), "кейсов RubUp;", len(os.listdir(ASSETS)), "файлов обложек")
