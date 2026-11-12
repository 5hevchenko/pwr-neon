"""Разовая перекраска исходников web/*.css под неон: жёстко заданные золотые оттенки → бирюзовый / фиолетовый.
Переменная --gold (валюта, редкость «легендарный») остаётся тёплой — её задаёт web/neon.css. Уже применено; повторный запуск ничего не меняет."""
import glob
import os
import re

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
LIGHT, MID, DEEP, DARK, SHADE = "#a8fbff", "#22e9ff", "#7a6bff", "#031018", "#3b2fa8"
HEX = {**{h: LIGHT for h in "ffe58a ffe17a ffe08a fff3c4 fff3b0 fff6c8 ffe7a3 ffe36e".split()},
       **{h: MID for h in "ffd76a ffd23f ffc93d ffc53d ffc21a".split()},
       **{h: DEEP for h in "ffab2e ffb52e ffb31f ffb81f ffb020 ff9f1c f08c00".split()},
       **{h: DARK for h in "3a2300 3a2800 2c1500".split()},
       **{h: SHADE for h in "c88a00 a86a00".split()}}
RGB = {"255,215,106": "34,233,255", "255,200,80": "34,233,255", "255,214,120": "168,251,255", "255,190,60": "122,107,255",
       "255,170,30": "122,107,255", "255,210,90": "34,233,255", "255,200,60": "34,233,255", "255,197,61": "34,233,255", "255,210,63": "34,233,255"}
n = 0
for f in glob.glob(os.path.join(WEB, "*.css")):
    if os.path.basename(f) in ("bundle.css", "neon.css", "pwr.css"):
        continue
    s = open(f, encoding="utf-8").read()
    o = s
    s = re.sub(r"#([0-9a-fA-F]{6})\b", lambda m: HEX.get(m.group(1).lower(), m.group(0)), s)
    s = re.sub(r"(rgba?\()\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", lambda m: m.group(1) + RGB.get(f"{m.group(2)},{m.group(3)},{m.group(4)}", f"{m.group(2)},{m.group(3)},{m.group(4)}"), s)
    if s != o:
        n += 1
        open(f, "w", encoding="utf-8", newline="\n").write(s)
print("перекрашено файлов:", n)
