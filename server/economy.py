"""Экономика: цены коллекций, ценность конкретного подарка, кейсы."""
from settings import conf
import json
import re
import math
import os
import random
from statistics import median

CATALOG = json.load(open(os.path.join(os.path.dirname(__file__), "catalog.json"), encoding="utf-8"))

# ---------------- свои подарки (не из Telegram): кейс CS:GO. Картинки — server/csgo_assets (скачаны со Steam CDN),
# фоны и узоры берём у коллекции-донора; отдаёт их app.asset, а не api.changes.tg
CUSTOM_DIR = os.path.join(os.path.dirname(__file__), "csgo_assets")
CUSTOM_MAP = json.load(open(os.path.join(CUSTOM_DIR, "map.json"), encoding="utf-8"))   # коллекция → модель → имя файла
CUSTOM_DONOR = "Light Sword"
COVER_DIR = os.path.join(os.path.dirname(__file__), "covers")   # свои обложки кейсов из админки
_WEAR = [["Factory New", 3], ["Minimal Wear", 8], ["Field-Tested", 20], ["Well-Worn", 10], ["Battle-Scarred", 9]]
CUSTOM = {
    "P90 Asiimov": _WEAR,
    "AK-47 Asiimov": _WEAR,
    "CS Gloves": [["Pandora's Box", 2], ["Vice", 3], ["Crimson Kimono", 4], ["Spearmint", 5], ["King Snake", 6], ["Cobalt Skulls", 10]],
    "Karambit": [["Fade", 3], ["Doppler", 5], ["Gamma Doppler", 4], ["Marble Fade", 4], ["Tiger Tooth", 6], ["Lore", 5], ["Slaughter", 7], ["Crimson Web", 10]],
    # кейс «CS:GO Легенды» (2026-11-11): у части скинов в игре нет всех степеней износа — берём те, что есть
    "AWP Asiimov": [["Field-Tested", 20], ["Well-Worn", 10], ["Battle-Scarred", 9]],
    "Desert Eagle Blaze": [["Factory New", 3], ["Minimal Wear", 8]],
    "Glock-18 Fade": [["Factory New", 3], ["Minimal Wear", 8]],
    "USP-S Kill Confirmed": _WEAR,
    "AK-47 Fire Serpent": _WEAR,
    "M4A4 Howl": [["Factory New", 3], ["Minimal Wear", 8], ["Field-Tested", 20], ["Well-Worn", 10]],
    "AWP Dragon Lore": _WEAR,
    "Butterfly Knife": [["Fade", 3], ["Doppler", 5], ["Gamma Doppler", 4], ["Marble Fade", 4], ["Tiger Tooth", 6], ["Lore", 5], ["Slaughter", 7], ["Crimson Web", 10]],
    "Sport Gloves": [["Omega", 3], ["Amphibious", 3], ["Hedge Maze", 4], ["Nocts", 5], ["Slingshot", 5], ["Scarlet Shamagh", 6], ["Bronze Morph", 7], ["Superconductor", 8]],
    # ещё скины в кейс «CS:GO» (2026-11-11)
    "AK-47 Redline": [["Minimal Wear", 8], ["Field-Tested", 20], ["Well-Worn", 10], ["Battle-Scarred", 9]],
    "AK-47 Vulcan": _WEAR,
    "M4A1-S Printstream": _WEAR,
    "M4A4 Neo-Noir": _WEAR,
    "AWP Neo-Noir": _WEAR,
    "AWP Hyper Beast": _WEAR,
    "Desert Eagle Code Red": _WEAR,
    "M9 Bayonet": [["Fade", 3], ["Doppler", 5], ["Gamma Doppler", 4], ["Marble Fade", 4], ["Tiger Tooth", 6], ["Lore", 5], ["Slaughter", 7], ["Crimson Web", 10]],
    "Driver Gloves": [["Crimson Weave", 3], ["Imperial Plaid", 4], ["Overtake", 5], ["Racing Green", 7], ["Lunar Weave", 6], ["Diamondback", 6], ["Black Tie", 5], ["Snow Leopard", 8]],
    # кейс «Brawl Stars» (2026-11-11): карточки бойцов по редкости, картинки — CDN Brawlify (api.brawlapi.com), обложка — фан-кит Supercell
    "Бравлеры редкие": [["Shelly", 20], ["Colt", 15], ["Bull", 12], ["Brock", 10], ["Barley", 8], ["Nita", 6], ["El Primo", 5], ["Poco", 4], ["Rosa", 3]],
    "Бравлеры супер редкие": [["Rico", 20], ["Jessie", 20], ["Dynamike", 15], ["Darryl", 12], ["Penny", 10], ["Tick", 8], ["Carl", 6], ["8-Bit", 5], ["Jacky", 4], ["Gus", 3]],
    "Бравлеры эпические": [["Bo", 20], ["Piper", 20], ["Pam", 20], ["Frank", 20], ["Bibi", 15], ["Bea", 15], ["Emz", 15], ["Gale", 12], ["Nani", 12], ["Colette", 12], ["Edgar", 10], ["Stu", 10], ["Belle", 10], ["Grom", 10], ["Griff", 8], ["Ash", 8], ["Lola", 8], ["Bonnie", 6], ["Sam", 6], ["Mandy", 6], ["Maisie", 5], ["Hank", 5], ["Pearl", 5], ["Larry & Lawrie", 5], ["Angelo", 4], ["Berry", 4], ["Shade", 4], ["Meeple", 3], ["Trunk", 3], ["Bolt", 3]],
    "Бравлеры мифические": [["Mortis", 20], ["Tara", 20], ["Gene", 20], ["Mr. P", 20], ["Max", 20], ["Sprout", 15], ["Lou", 15], ["Byron", 15], ["Ruffs", 15], ["Squeak", 15], ["Buzz", 12], ["Fang", 12], ["Eve", 12], ["Janet", 12], ["Otis", 12], ["Buster", 10], ["Gray", 10], ["R-T", 10], ["Willow", 10], ["Doug", 10], ["Chuck", 8], ["Charlie", 8], ["Mico", 8], ["Melodie", 8], ["Lily", 6], ["Clancy", 6], ["Moe", 6], ["Juju", 6], ["Ollie", 6], ["Lumi", 5], ["Finx", 5], ["Jae-Yong", 5], ["Alli", 5], ["Mina", 5], ["Ziggy", 4], ["Gigi", 4], ["Glowy", 4], ["Najia", 4], ["Damian", 4], ["Starr Nova", 3], ["Wendy", 3], ["Cosmo", 3], ["Vince", 3]],
    "Бравлеры легендарные": [["Spike", 20], ["Crow", 20], ["Leon", 15], ["Sandy", 15], ["Surge", 12], ["Amber", 12], ["Meg", 10], ["Chester", 10], ["Cordelius", 8], ["Kit", 6], ["Draco", 6], ["Kenji", 5], ["Kaze", 5], ["Pierce", 4], ["Sirius", 4], ["Nori", 3]],
    # кейс «Minecraft» (2026-11-11): инструменты шести материалов, текстуры — PrismarineJS/minecraft-assets, обложка — minecraft.wiki
    "Деревянные инструменты": [["Мотыга", 20], ["Лопата", 15], ["Топор", 10], ["Кирка", 7], ["Меч", 4]],
    "Каменные инструменты": [["Мотыга", 20], ["Лопата", 15], ["Топор", 10], ["Кирка", 7], ["Меч", 4]],
    "Золотые инструменты": [["Мотыга", 20], ["Лопата", 15], ["Топор", 10], ["Кирка", 7], ["Меч", 4]],
    "Железные инструменты": [["Мотыга", 20], ["Лопата", 15], ["Топор", 10], ["Кирка", 7], ["Меч", 4]],
    "Алмазные инструменты": [["Мотыга", 20], ["Лопата", 15], ["Топор", 10], ["Кирка", 7], ["Меч", 4]],
    "Незеритовые инструменты": [["Мотыга", 20], ["Лопата", 15], ["Топор", 10], ["Кирка", 7], ["Меч", 4]],
}
CUSTOM_COVERS = {"CS Case": "_cover", "CS Case 2": "CS Case 2", "Мегаящик": "Мегаящик", "Сундук": "Сундук"}   # обложки своих кейсов → ключ в map.json (не коллекции)
for _c, _m in CUSTOM.items():
    CATALOG[_c] = {"released": 1794355200, "models": [list(x) for x in _m],
                   "backdrops": CATALOG[CUSTOM_DONOR]["backdrops"], "symbols": CATALOG[CUSTOM_DONOR]["symbols"]}


def custom_file(col, model=None):
    """Путь к своей картинке без суффикса размера (model или обложка коллекции) или None — это подарок Telegram."""
    if col.startswith("~"):   # загруженная в админке обложка кейса (admin.py → «Кейсы»): covers/<имя>_<размер>.png
        name = col[1:]
        return os.path.join(COVER_DIR, name) if re.fullmatch(r"[A-Za-z0-9_]{1,80}", name) else None
    m = CUSTOM_MAP.get(CUSTOM_COVERS.get(col, col))
    if not m:
        return None
    name = m.get(model) if model else next(iter(m.values()))
    return os.path.join(CUSTOM_DIR, name) if name else None

# базовая цена коллекции в игровых ⭐ — по мотивам реального рынка, но это игра
BASE = {
    "Lucky Locket": 3500,
    "Plush Pepe": 600000, "Heart Locket": 300000, "Durov's Cap": 120000, "Precious Peach": 60000,
    "Intelligence Cup": 50000, "Algorithm Cup": 50000, "Mighty Arm": 30000,
    "Ion Gem": 15000, "Loot Bag": 15000, "Astral Shard": 15000, "Nail Bracelet": 15000,
    "Perfume Bottle": 12000, "Mini Oscar": 10000, "Magic Potion": 9000, "Gem Signet": 9000,
    "Westside Sign": 8000, "Low Rider": 6000, "Khabib's Papakha": 6000, "UFC Strike": 3000,
    "Swiss Watch": 5000, "Genie Lamp": 5000, "Scared Cat": 5000, "Bonded Ring": 5000,
    "Kissed Frog": 4500, "Sharp Tongue": 4000, "Electric Skull": 4000, "Signet Ring": 4000,
    "Durov's Glasses": 4000, "Vintage Cigar": 3500, "Heroic Helmet": 3500, "Toy Bear": 3000,
    "Rare Bird": 3000, "Neko Helmet": 3000, "Eternal Rose": 2500, "Diamond Ring": 2500,
    "Artisan Brick": 2500, "Mad Pumpkin": 2000, "Voodoo Doll": 1800, "Top Hat": 1800,
    "Love Potion": 1500, "Crystal Ball": 1500, "Flying Broom": 1500, "Sky Stilettos": 1500,
    "Cupid Charm": 1500, "Record Player": 1300, "Trapped Heart": 1200, "Skull Flower": 1200,
    "Sakura Flower": 1000, "Berry Box": 1000, "Love Candle": 1000, "Jelly Bunny": 900,
    "Evil Eye": 900, "Sleigh Bell": 900, "Valentine Box": 900, "Snoop Cigar": 900,
    "Hanging Star": 800, "Eternal Candle": 700, "Spy Agaric": 700, "Bunny Muffin": 700,
    "Snow Globe": 700, "Restless Jar": 700, "Hex Pot": 600, "Witch Hat": 600, "Hypno Lollipop": 600,
    "Star Notepad": 600, "Spiced Wine": 600, "Santa Hat": 600, "Input Key": 600, "Light Sword": 600,
    "Jester Hat": 500, "Ginger Cookie": 500, "Snow Mittens": 500, "Winter Wreath": 500,
    "Tama Gadget": 500, "Lush Bouquet": 500, "Joyful Bundle": 500, "Bow Tie": 500, "Swag Bag": 500,
    "Homemade Cake": 350, "Xmas Stocking": 400, "Candy Cane": 400, "Party Sparkler": 400,
    "Cookie Heart": 400, "Jingle Bells": 400, "Holiday Drink": 400, "Pet Snake": 400,
    "Snake Box": 400, "Big Year": 400, "Fresh Socks": 400, "Snoop Dogg": 400,
    "Lol Pop": 300, "B-Day Candle": 300, "Desk Calendar": 300, "Lunar Snake": 300,
}
DEFAULT_BASE = 600
BASE.update({"P90 Asiimov": 3660, "AK-47 Asiimov": 9150, "CS Gloves": 29280, "Karambit": 73200})   # кейс CS:GO: при цене 11 111 возврат ≈ 90% (проверено симуляцией)
BASE.update({"AK-47 Redline": 5230, "Desert Eagle Code Red": 6540, "AWP Hyper Beast": 7850, "M4A4 Neo-Noir": 9160, "AWP Neo-Noir": 10470, "AK-47 Vulcan": 15700,
             "M4A1-S Printstream": 19630, "Driver Gloves": 39260, "M9 Bayonet": 78520})   # добавка в кейс CS:GO (13 коллекций): возврат ≈ 90% при 11 111 (симуляция 200к, 2026-11-11)
BASE.update({"Деревянные инструменты": 1400, "Каменные инструменты": 2100, "Золотые инструменты": 3040, "Железные инструменты": 4090, "Алмазные инструменты": 9340, "Незеритовые инструменты": 29200})   # Minecraft: возврат ≈ 90% при 3 333 (симуляция 200к, 2026-11-11)
BASE.update({"Бравлеры редкие": 2320, "Бравлеры супер редкие": 3710, "Бравлеры эпические": 6490, "Бравлеры мифические": 13910, "Бравлеры легендарные": 37100})   # Brawl Stars: возврат ≈ 90% при 5 555 (симуляция 200к, 2026-11-11)
BASE.update({"AWP Asiimov": 11500, "Desert Eagle Blaze": 18450, "Glock-18 Fade": 27700, "USP-S Kill Confirmed": 13850, "AK-47 Fire Serpent": 57700,
             "M4A4 Howl": 138400, "Sport Gloves": 115300, "Butterfly Knife": 207600, "AWP Dragon Lore": 461300})   # кейс «CS:GO Легенды»: при цене 33 333 возврат ≈ 90% (симуляция 200к открытий, 2026-11-11)


def base(col):
    return BASE.get(col, DEFAULT_BASE)


# медианная редкость по каждому типу черты внутри коллекции — от неё считаем множитель
_MED = {c: (median(m[1] for m in d["models"]), median(b[1] for b in d["backdrops"]), median(s[1] for s in d["symbols"]))
        for c, d in CATALOG.items()}


def mult(col, pm, pb, ps):
    mm, mb, ms = _MED[col]
    k = (mm / max(pm, 1)) ** 0.5 * (mb / max(pb, 1)) ** 0.25 * (ms / max(ps, 1)) ** 0.2
    return min(8.0, max(0.6, k))


def supply(col):
    return int(min(300000, max(1000, 4e6 / base(col) ** 0.6)))


_CUM = {}


def _cum(col, key):
    k = (col, key)
    if k not in _CUM:
        items = CATALOG[col][key]
        acc, out = 0.0, []
        for it in items:
            acc += max(it[1], 0.1)
            out.append(acc)
        _CUM[k] = (items, out)
    return _CUM[k]


def _pick(col, key, rng=random):
    items, cum = _cum(col, key)
    return rng.choices(items, cum_weights=cum)[0]


def roll(col, rng=random):
    m, b, s = _pick(col, "models", rng), _pick(col, "backdrops", rng), _pick(col, "symbols", rng)
    return {
        "col": col, "model": m[0], "backdrop": b[0], "symbol": s[0],
        "num": rng.randint(1, supply(col)),
        "value": max(1, round(base(col) * mult(col, m[1], b[1], s[1]))),
    }


def expected_value(col):
    """Матожидание ценности подарка коллекции. Множитель — произведение по чертам, поэтому считаем раздельно."""
    d = CATALOG[col]
    mm, mb, ms = _MED[col]
    def part(items, med, k):
        t = sum(x[1] for x in items)
        return sum(x[1] / t * (med / max(x[1], 1)) ** k for x in items)
    e = part(d["models"], mm, 0.5) * part(d["backdrops"], mb, 0.25) * part(d["symbols"], ms, 0.2)
    return base(col) * min(8.0, e)


_EV = {}


def ev(col):
    if col not in _EV:
        _EV[col] = expected_value(col)
    return _EV[col]


# ---------------- кейсы: от дешёвых до мега ----------------
# id, название, эмодзи-обложка (коллекция для превью), мин. уровень, состав
# Лимитные кейсы: у каждого тираж, открытые не возвращаются. Счётчик остатка хранится в базе (таблица case_limit).
JOKE_DROPS = {"mega": {"Desk Calendar": 0.01}}   # шуточные подарки: календарь в МЕГЕ с шансом ровно 1%
LIMITED = {"first_ed": 5000, "gold_ed": 1000}
CASES_DEF = [
    ("first_ed", "Первый тираж", "Lucky Locket", 5, ["Lucky Locket", "Timeless Book", "Liberty Figure", "Mirage Lamp", "Moon Pendant", "Genie Lamp"]),
    ("gold_ed", "Золотая серия", "Money Pot", 8, ["Money Pot", "Mini Oscar", "Swiss Watch", "Signet Ring", "Durov's Glasses", "Diamond Ring"]),
    ("champ", "Чемпион", "Victory Medal", 3, ["Victory Medal", "UFC Strike", "Khabib's Papakha", "Mighty Arm", "Heroic Helmet", "Intelligence Cup", "Algorithm Cup"]),
    ("gadgets", "Электроника", "Tama Gadget", 3, ["Tama Gadget", "Input Key", "Ionic Dryer", "Record Player", "Star Notepad", "Fine Pen", "Surge Board"]),
    ("treasure", "Клад", "Loot Bag", 5, ["Loot Bag", "Money Pot", "Lucky Locket", "Timeless Book", "Mini Oscar", "Moon Pendant", "Faith Amulet"]),
    ("knight", "Рыцарь", "Light Sword", 6, ["Light Sword", "Heroic Helmet", "Liberty Figure", "Artisan Brick", "Mighty Arm", "Neko Helmet"]),
    ("cozy", "Уют", "Spiced Wine", 2, ["Spiced Wine", "Holiday Drink", "Love Candle", "Eternal Candle", "Mood Pack", "Winter Wreath", "Snow Globe"]),
    ("nightlife", "Ночная жизнь", "Vice Cream", 4, ["Vice Cream", "Bling Binky", "Chill Flame", "Swag Bag", "Vintage Cigar", "Snoop Cigar", "Party Sparkler"]),
    ("crown", "Корона", "Signet Ring", 7, ["Signet Ring", "Swiss Watch", "Mini Oscar", "Genie Lamp", "Bonded Ring", "Perfume Bottle", "Magic Potion"]),
    ("free", "Бесплатный", "Lol Pop", 1, ["Lol Pop", "Desk Calendar", "B-Day Candle", "Lunar Snake", "Homemade Cake", "Jingle Bells", "Hex Pot"]),
    ("starter", "Ширпотреб", "Desk Calendar", 1, ["Lol Pop", "Desk Calendar", "B-Day Candle", "Lunar Snake", "Homemade Cake",
                                                  "Party Sparkler", "Cookie Heart", "Big Year", "Snake Box", "Pet Snake", "Sakura Flower"]),
    ("sweet", "Сладкоежка", "Homemade Cake", 1, ["Homemade Cake", "Lol Pop", "Hypno Lollipop", "Cookie Heart", "Ginger Cookie",
                                                 "Candy Cane", "Bunny Muffin", "Whip Cupcake", "Mousse Cake", "Ice Cream", "Happy Brownie", "Berry Box"]),
    ("winter", "Новогодний", "Santa Hat", 2, ["Santa Hat", "Snow Mittens", "Ginger Cookie", "Winter Wreath", "Sleigh Bell", "Snow Globe",
                                              "Candy Cane", "Xmas Stocking", "Jingle Bells", "Holiday Drink", "Party Sparkler"]),
    ("spooky", "Хэллоуин", "Mad Pumpkin", 3, ["Witch Hat", "Eternal Candle", "Spy Agaric", "Hex Pot", "Evil Eye", "Scared Cat",
                                              "Voodoo Doll", "Flying Broom", "Trapped Heart", "Skull Flower", "Crystal Ball", "Mad Pumpkin", "Electric Skull"]),
    ("love", "Валентинка", "Heart Locket", 4, ["Cupid Charm", "Valentine Box", "Love Potion", "Diamond Ring", "Restless Jar", "Sky Stilettos",
                                               "Toy Bear", "Bonded Ring", "Lush Bouquet", "Joyful Bundle", "Love Candle", "Eternal Rose", "Heart Locket"]),
    ("gangsta", "Westside", "Low Rider", 5, ["Snoop Dogg", "Swag Bag", "Snoop Cigar", "Low Rider", "Westside Sign", "Vintage Cigar", "Top Hat"]),
    ("jewel", "Ювелирка", "Signet Ring", 6, ["Signet Ring", "Gem Signet", "Diamond Ring", "Bonded Ring", "Nail Bracelet", "Ion Gem",
                                             "Astral Shard", "Swiss Watch", "Moon Pendant", "Faith Amulet", "Clover Pin"]),
    ("magic", "Магия", "Magic Potion", 8, ["Magic Potion", "Genie Lamp", "Crystal Ball", "Astral Shard", "Mirage Lamp", "Perfume Bottle",
                                           "Kissed Frog", "Sharp Tongue", "Love Potion", "Hex Pot"]),
    ("party", "Вечеринка", "Party Sparkler", 1, ["Party Sparkler", "B-Day Candle", "Homemade Cake", "Jester Hat", "Lol Pop", "Cookie Heart",
                                                 "Big Year", "Joyful Bundle", "Jack-in-the-Box", "Hanging Star"]),
    ("spring", "Весна", "Easter Egg", 1, ["Easter Egg", "Spring Basket", "Pretty Posy", "Clover Pin", "Sakura Flower", "Bunny Muffin",
                                          "Jelly Bunny", "Lush Bouquet", "Eternal Rose"]),
    ("food", "Фастфуд", "Instant Ramen", 2, ["Instant Ramen", "Ice Cream", "Whip Cupcake", "Mousse Cake", "Happy Brownie", "Ginger Cookie",
                                             "Holiday Drink", "Spiced Wine", "Homemade Cake", "Berry Box"]),
    ("summer", "Лето", "Pool Float", 2, ["Pool Float", "Surge Board", "Ice Cream", "Vice Cream", "Chill Flame", "Bling Binky", "Fresh Socks", "Mood Pack"]),
    ("zoo", "Зоопарк", "Scared Cat", 4, ["Scared Cat", "Toy Bear", "Jolly Chimp", "Pet Snake", "Rare Bird", "Kissed Frog", "Lunar Snake",
                                         "Neko Helmet", "Jelly Bunny"]),
    ("style", "Стиль", "Top Hat", 4, ["Top Hat", "Bow Tie", "Fresh Socks", "Sky Stilettos", "Durov's Glasses", "Swag Bag", "Fine Pen",
                                      "Mood Pack", "Ionic Dryer", "Perfume Bottle"]),
    ("space", "Космос", "Stellar Rocket", 5, ["Stellar Rocket", "Astral Shard", "Moon Pendant", "Hanging Star", "Star Notepad", "Crystal Ball",
                                              "Lunar Snake", "Mirage Lamp", "Sleigh Bell"]),
    ("luck", "Удача", "Lucky Locket", 6, ["Lucky Locket", "Clover Pin", "Money Pot", "Faith Amulet", "Evil Eye", "Jack-in-the-Box", "Swiss Watch",
                                        "Genie Lamp", "Loot Bag", "Victory Medal"]),
    ("heroes", "Герои", "Heroic Helmet", 7, ["Heroic Helmet", "Light Sword", "Victory Medal", "Liberty Figure", "UFC Strike",
                                             "Khabib's Papakha", "Mighty Arm", "Timeless Book", "Artisan Brick"]),
    ("elite", "Элитный", "Mini Oscar", 12, ["Mini Oscar", "Perfume Bottle", "Loot Bag", "Ion Gem", "Nail Bracelet", "Astral Shard",
                                            "Gem Signet", "Magic Potion", "Mighty Arm", "Westside Sign"]),
    ("durov", "Дуров", "Durov's Cap", 13, ["Durov's Cap", "Durov's Glasses", "Precious Peach", "Plush Pepe", "Swiss Watch", "Signet Ring", "Vintage Cigar"]),
    ("fresh", "Новинки", "Algorithm Cup", 5, ["Algorithm Cup", "Intelligence Cup", "UFC Strike", "Khabib's Papakha",
                                             "Durov's Glasses", "Low Rider", "Westside Sign", "Rare Bird"]),
    ("flea", "Барахолка", "Record Player", 1, ["Record Player", "Tama Gadget", "Input Key", "Hex Pot", "Witch Hat", "Love Candle",
                                               "Light Sword", "Restless Jar", "Valentine Box", "Snoop Dogg", "Snoop Cigar", "Jolly Chimp",
                                               "Timeless Book", "Liberty Figure", "Signet Ring"]),
    ("pepehunt", "Охота на Пепе", "Plush Pepe", 1, ["Lol Pop", "Desk Calendar", "B-Day Candle", "Homemade Cake", "Plush Pepe"]),
    ("hearthunt", "Охота на Сердце", "Heart Locket", 3, ["Eternal Rose", "Love Potion", "Cupid Charm", "Sky Stilettos", "Heart Locket"]),
    ("retro", "Ретро", "Record Player", 2, ["Record Player", "Vintage Cigar", "Top Hat", "Tama Gadget", "Input Key", "Voodoo Doll", "Crystal Ball"]),
    ("lux", "Роскошь", "Swiss Watch", 7, ["Swiss Watch", "Bonded Ring", "Gem Signet", "Perfume Bottle", "Mini Oscar", "Diamond Ring", "Genie Lamp"]),
    ("cups", "Кубки", "Algorithm Cup", 10, ["Algorithm Cup", "Intelligence Cup", "Mighty Arm", "Loot Bag", "Ion Gem", "Nail Bracelet"]),
    ("peach", "Персик", "Precious Peach", 12, ["Precious Peach", "Algorithm Cup", "Intelligence Cup", "Mighty Arm", "Durov's Cap"]),
    # новые кейсы (10-10): охоты, тематические и «Монетка»
    ("coin", "Монетка", "Lucky Locket", 1, ["Lol Pop", "Lucky Locket"]),
    ("cute", "Милашки", "Jelly Bunny", 1, ["Jelly Bunny", "Bunny Muffin", "Toy Bear", "Scared Cat", "Neko Helmet", "Pet Snake", "Kissed Frog", "Jolly Chimp"]),
    ("tech", "Гаджеты", "Tama Gadget", 2, ["Tama Gadget", "Input Key", "Ionic Dryer", "Record Player", "Fine Pen", "Star Notepad", "Light Sword", "Electric Skull"]),
    ("peachhunt", "Охота на Персик", "Precious Peach", 2, ["Lol Pop", "Desk Calendar", "B-Day Candle", "Homemade Cake", "Precious Peach"]),
    ("night", "Ночной клуб", "Vice Cream", 3, ["Vice Cream", "Bling Binky", "Party Sparkler", "Spiced Wine", "Swag Bag", "Chill Flame", "Snoop Cigar", "Snoop Dogg"]),
    ("caphunt", "Охота на Кепку", "Durov's Cap", 3, ["Lol Pop", "Desk Calendar", "B-Day Candle", "Homemade Cake", "Durov's Cap"]),
    ("sport", "Спорт", "UFC Strike", 4, ["UFC Strike", "Khabib's Papakha", "Victory Medal", "Surge Board", "Heroic Helmet", "Bling Binky"]),
    ("royal", "Королевский", "Heart Locket", 18, ["Plush Pepe", "Heart Locket"]),
    ("csgo", "CS:GO", "CS Case", 3, ["P90 Asiimov", "AK-47 Asiimov", "AK-47 Redline", "Desert Eagle Code Red", "AWP Hyper Beast", "M4A4 Neo-Noir", "AWP Neo-Noir",
                                     "AK-47 Vulcan", "M4A1-S Printstream", "CS Gloves", "Driver Gloves", "Karambit", "M9 Bayonet"]),
    ("mc", "Minecraft", "Сундук", 1, ["Деревянные инструменты", "Каменные инструменты", "Золотые инструменты", "Железные инструменты", "Алмазные инструменты", "Незеритовые инструменты"]),
    ("brawl", "Brawl Stars", "Мегаящик", 2, ["Бравлеры редкие", "Бравлеры супер редкие", "Бравлеры эпические", "Бравлеры мифические", "Бравлеры легендарные"]),
    ("csgo2", "CS:GO Легенды", "CS Case 2", 5, ["AWP Asiimov", "Desert Eagle Blaze", "Glock-18 Fade", "USP-S Kill Confirmed", "AK-47 Fire Serpent", "M4A4 Howl", "Sport Gloves", "Butterfly Knife", "AWP Dragon Lore"]),
    ("mega", "МЕГА", "Plush Pepe", 15, ["Plush Pepe", "Heart Locket", "Durov's Cap", "Precious Peach", "Mighty Arm", "Ion Gem", "Loot Bag"]),
]
RTP = conf("economy.case_rtp", 0.9)  # возврат игроку
FIXED_PRICE = {"csgo": 11111, "csgo2": 33333, "brawl": 5555, "mc": 3333}   # цена ровно такая (базовые цены коллекций подобраны под RTP)
CASES = {}


def _nice(x):
    """Красивая цена: 1234 → 1250, 87654 → 90000."""
    if x < 100:
        return int(max(10, round(x / 5) * 5))
    p = 10 ** (int(math.log10(x)) - 1)
    for step in (1, 2.5, 5, 10):
        if x <= 10 * p * step / 2.5 * 2.5:
            break
    return int(math.ceil(x / (p * 2.5)) * p * 2.5)


FLOOR = 0.4    # из платного кейса не выпадает подарок дешевле ~40% его цены
SAMPLES = 2000


def _draw(c, floor, rng=random):
    """Дроп кейса: коллекция по весу, внутри неё перебрасываем вариант, пока ценность ниже планки."""
    col = rng.choices(c["cols"], cum_weights=c["cum"])[0]
    if col in c.get("joke", ()):   # шуточный подарок выпадает как есть, без планки ценности
        return roll(col, rng)
    best = None
    for _ in range(25):
        d = roll(col, rng)
        if d["value"] >= floor:
            return d
        if not best or d["value"] > best["value"]:
            best = d
    return best


def build_cases():
    for cid, title, cover, lvl, cols in CASES_DEF:
        cols = [x for x in cols if x in CATALOG]
        while True:   # выкидываем коллекции, которые сильно дешевле кейса
            price = len(cols) / sum(1 / ev(x) for x in cols) / RTP
            low = [x for x in cols if ev(x) < 0.5 * price]
            if cid in ("free", *FIXED_PRICE) or not low or len(cols) <= 3:
                break
            cols.remove(min(low, key=ev))
        w = [1 / ev(x) for x in cols]            # вклад каждой коллекции в ожидание одинаковый → дорогие редкие
        tw = sum(w)
        cum, acc = [], 0.0
        for x in w:
            acc += x
            cum.append(acc)
        odds = {x: wi / tw for x, wi in zip(cols, w)}
        c = {"id": cid, "title": title, "cover": cover, "level": lvl, "cols": cols, "cum": cum, "floor": 0, "odds": odds}
        floor = 0 if cid == "free" else FLOOR * price
        for _ in range(2 if floor else 1):   # средняя ценность каждой коллекции с учётом планки
            evs = {}
            for x in cols:
                one = {"cols": [x], "cum": [1.0]}
                evs[x] = sum(_draw(one, floor)["value"] for _ in range(SAMPLES // len(cols) + 150)) / (SAMPLES // len(cols) + 150)
            if floor:
                price = _nice(sum(odds[x] * evs[x] for x in cols) / RTP)
                floor = FLOOR * price
        c.update(evs=evs, floor=floor, price=0 if cid == "free" else price)
        if cid in FIXED_PRICE:   # цена ровно заданная; базовые цены коллекций кейса подобраны так, что возврат ≈ RTP
            c.update(price=FIXED_PRICE[cid], floor=FLOOR * FIXED_PRICE[cid])
        extra = {k: p for k, p in JOKE_DROPS.get(cid, {}).items() if k in CATALOG}
        if extra:   # точный шанс; цена пересчитывается, чтобы заявленный возврат кейса не изменился
            keep = 1 - sum(extra.values())
            odds = {**{x: p * keep for x, p in odds.items()}, **extra}
            evs = {**evs, **{k: ev(k) for k in extra}}
            names = list(odds)
            acc, cum = 0.0, []
            for x in names:
                acc += odds[x]
                cum.append(acc)
            c.update(cols=names, cum=cum, odds=odds, evs=evs, joke=set(extra), price=_nice(sum(odds[x] * evs[x] for x in names) / RTP))
        CASES[cid] = c


# Переименования кейсов из админки (admin.py → «Кейсы», kv case_names): cid → {"title", "who": all|only|except, "ids": set}.
# who=all — новое имя видят все; only — только игроки из ids; except — все, кроме ids (они видят настоящее).
CASE_NAMES = {}


def case_title(cid, uid=None):
    """Название кейса для конкретного игрока (uid=None — настоящее, без переименования)."""
    c = CASES.get(cid)
    if not c:
        return cid
    o = CASE_NAMES.get(cid)
    if not o or uid is None:
        return c["title"]
    who, ids = o.get("who", "all"), o.get("ids", ())
    if who == "all" or (who == "only" and uid in ids) or (who == "except" and uid not in ids):
        return o["title"]
    return c["title"]


# Свои обложки кейсов (admin.py → «Кейсы», kv case_covers): cid → {"cover": коллекция или "~файл", "who", "ids"} — как у названий.
CASE_COVERS = {}


def case_cover(cid, uid=None):
    """Обложка кейса для конкретного игрока: имя коллекции или "~имя" загруженной картинки."""
    c = CASES.get(cid)
    if not c:
        return CUSTOM_DONOR
    o = CASE_COVERS.get(cid)
    if not o or uid is None:
        return c["cover"]
    who, ids = o.get("who", "all"), o.get("ids", ())
    if who == "all" or (who == "only" and uid in ids) or (who == "except" and uid not in ids):
        return o["cover"]
    return c["cover"]


def open_case(cid, rng=random):
    c = CASES[cid]
    return _draw(c, c["floor"], rng)


build_cases()

if __name__ == "__main__":
    for c in CASES.values():
        print(f'{c["id"]:8} {c["title"]:12} lvl{c["level"]:>3} price {c["price"]:>8}  EV {sum(c["odds"][x]*ev(x) for x in c["odds"]):>9.0f}')
    print(roll("Plush Pepe"))
