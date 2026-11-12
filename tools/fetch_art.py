"""Арт и ролики, сгенерированные в Higgsfield: скачиваются при сборке в web/gen/ (картинки — в webp нужного размера, ролики — как есть).
Список готовых файлов пишется в web/genart.js (window.GEN_ART) — интерфейс использует только то, что реально скачалось.
Запускается из build.py; нет сети или файла — сборка идёт дальше, интерфейс остаётся на прежнем оформлении."""
import io
import json
import os
import urllib.request

WEB = os.environ.get("WEB_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
GEN = os.path.join(WEB, "gen")
CDN = "https://d8j0ntlcm91z4.cloudfront.net/user_2xas94ULgBi6nItEeRfU5Qg6aPS/hf_20261112_"
ART = {   # имя → (файл на CDN, ширина webp в пикселях; None — ролик mp4 без перекодирования)
    "bg": ("113021_8a01ec58-99f7-4279-868e-b23aa19e578d.png", 720),
    "pass_banner": ("113104_25b0ddcf-cc69-4d80-b265-be8067f04018.png", 960),
    "pass_crest": ("113020_98c86401-c825-4533-841a-7ea416ceff0e.png", 720),
    "cat_tg": ("113105_0cc4ea79-58ba-4357-884e-a465b45944ea.png", 192),
    "cat_cs": ("113104_29b09215-896f-4323-aa90-d3cfbcdae677.png", 192),
    "cat_ru": ("113021_6da12aa4-8ca7-46c9-948f-61d95207e486.png", 192),
    "game_crash": ("113020_62e8388a-7faa-4dd9-aa52-6e04b02434c5.png", 256),
    "game_mines": ("113210_4480ba14-65af-4ae0-af38-0ad732055485.png", 256),
    "game_slots": ("113210_72ac6b00-989a-448d-be46-bdb7498ae0fb.png", 256),
    "game_wheel": ("113209_bb648115-ab8e-46b1-a5ac-b77d41f21232.png", 256),
    "game_dice": ("113209_b5ef138a-edbc-46c6-a563-5b7354bb1a9d.png", 256),
    "pass_loop": ("113147_720e4dcb-174d-4b15-b075-23c134bea231.mp4", None),
    "case_burst": ("113150_4c15d707-a7ac-4564-be67-2fe7af47e760.mp4", None),
}


def main():
    os.makedirs(GEN, exist_ok=True)
    ready = {}
    for name, (src, width) in ART.items():
        out = os.path.join(GEN, name + (".webp" if width else ".mp4"))
        if not os.path.exists(out):
            try:
                data = urllib.request.urlopen(urllib.request.Request(CDN + src, headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read()
                if width:
                    from PIL import Image
                    im = Image.open(io.BytesIO(data)).convert("RGB")
                    if im.width > width:
                        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
                    im.save(out + ".part", "WEBP", quality=82, method=4)
                else:
                    with open(out + ".part", "wb") as f:
                        f.write(data)
                os.replace(out + ".part", out)
            except Exception as e:
                print(f"арт {name}: не скачан ({e})", flush=True)
                continue
        ready[name] = "gen/" + os.path.basename(out)
    with open(os.path.join(WEB, "genart.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write("// создаётся tools/fetch_art.py при сборке\nwindow.GEN_ART = " + json.dumps(ready, ensure_ascii=False) + ";\n")
    print(f"арт Higgsfield: {len(ready)} из {len(ART)} файлов, {sum(os.path.getsize(os.path.join(WEB, p)) for p in ready.values()) // 1024} КБ", flush=True)


if __name__ == "__main__":
    main()
