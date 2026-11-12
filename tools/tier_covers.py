"""Запасные обложки тир-кейсов: рисуются кодом (свои, без чужих картинок). Арт из Higgsfield, если скачался при сборке,
ложится поверх них (tools/fetch_art.py). Запуск: python tools/tier_covers.py"""
import colorsys
import json
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server", "pwr")
ASSETS = os.path.join(ROOT, "assets")


def draw(n, total, label):
    S = 512
    hue = (0.52 + 0.9 * n / max(1, total)) % 1.0
    c = tuple(int(x * 255) for x in colorsys.hsv_to_rgb(hue, 0.85, 1.0))
    im = Image.new("RGB", (S, S), (11, 7, 24))
    glow = Image.new("RGB", (S, S), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    pts = [(S / 2 + 190 * math.cos(math.radians(a)), S / 2 + 190 * math.sin(math.radians(a))) for a in range(30, 390, 60)]
    g.polygon(pts, outline=c, width=14)
    g.line([pts[0], (S / 2, S / 2), pts[2]], fill=c, width=10)
    g.line([(S / 2, S / 2), pts[4]], fill=c, width=10)
    im = Image.composite(glow, im, glow.filter(ImageFilter.GaussianBlur(18)).convert("L").point(lambda v: min(255, v * 3)))
    d = ImageDraw.Draw(im)
    d.polygon(pts, outline=c, width=6)
    d.line([pts[0], (S / 2, S / 2), pts[2]], fill=c, width=4)
    d.line([(S / 2, S / 2), pts[4]], fill=c, width=4)
    try:
        f = ImageFont.load_default(size=120)
    except TypeError:
        f = ImageFont.load_default()
    box = d.textbbox((0, 0), label, font=f)
    d.text(((S - box[2] + box[0]) / 2 - box[0], S / 2 - 150 - box[1] / 2), label, fill=(255, 255, 255), font=f)
    return im


def main():
    cases = json.load(open(os.path.join(ROOT, "data.json"), encoding="utf-8"))["rubup"]
    for i, c in enumerate(sorted(cases, key=lambda x: x["price"])):
        im = draw(i, len(cases), str(i) if c["price"] else "0")
        for size in (64, 128, 256, 512):
            im.resize((size, size), Image.LANCZOS).save(os.path.join(ASSETS, f"{c['cover']}_{size}.webp"), quality=84, method=4)
    print(len(cases), "запасных обложек")


if __name__ == "__main__":
    main()
