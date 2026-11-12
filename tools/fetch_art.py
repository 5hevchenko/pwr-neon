"""Арт и ролики, сгенерированные в Higgsfield: скачиваются при сборке в web/gen/ (картинки — в webp нужного размера, ролики — как есть).
Список готовых файлов пишется в web/genart.js (window.GEN_ART) — интерфейс использует только то, что реально скачалось.
Запускается из build.py; нет сети или файла — сборка идёт дальше, интерфейс остаётся на прежнем оформлении."""
import io
import json
import os
import urllib.request

WEB = os.environ.get("WEB_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
GEN = os.path.join(WEB, "gen")
CDN_USER = "https://d8j0ntlcm91z4.cloudfront.net/user_2xas94ULgBi6nItEeRfU5Qg6aPS/"
CDN = CDN_USER + "hf_20261112_"
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


COVERS = {   # обложка тир-кейса → файл на CDN; при сборке ложится поверх запасной обложки из tools/tier_covers.py
    "tier_free": "hf_20261112_154509_eec9951e-ae5b-49dd-a499-1d0cb7189c0e.png",
    "tier_01": "hf_20261112_154510_bf2bba2a-612b-43bc-a5ea-764920e34b19.png",
    "tier_02": "hf_20261112_154417_b14ecbfc-1834-4fa5-aae3-78605321a495.png",
    "tier_03": "hf_20261112_154508_fefdca09-92b7-4d2c-ad0a-452ee70a296d.png",
    "tier_04": "hf_20261112_154509_6283d3d4-405e-41ee-b142-624a712f225b.png",
    "tier_05": "hf_20261112_154606_01737775-0919-4227-aafc-02338aabc216.png",
    "tier_06": "hf_20261112_154418_36b3b697-682b-4ee9-886c-dd901a84342b.png",
    "tier_07": "hf_20261112_154606_e1be1773-9b4a-42f2-bad8-f072e7ddc477.png",
    "tier_08": "hf_20261112_154606_d4d7d4af-bd3a-4ae3-a09c-8ae4f3c53b6f.png",
    "tier_09": "hf_20261112_154417_6d03ae35-f408-42bf-a89b-100b6a814682.png",
    "tier_10": "hf_20261112_154417_da94a583-3339-4ab3-9684-b1fba402760b.png",
    "tier_11": "hf_20261112_154607_5b20ab45-c7cd-4892-8539-1c012e0bb447.png",
    "tier_12": "hf_20261112_154639_ff1d3356-c348-4b4c-ac63-452fcc9f7e17.png",
    "tier_13": "hf_20261112_154738_df8fa112-7340-4754-8221-cfb147f91eb9.png",
    "tier_14": "hf_20261112_154638_d2af893c-9918-4e99-9e3a-ad7c5dc53823.png",
    "tier_15": "hf_20261112_154638_57dc0432-2d21-4cd8-ba5c-e4a7526e3525.png",
    "tier_16": "hf_20261112_154739_e14d31fc-1b05-470d-b7e1-5782bbf256af.png",
    "tier_17": "hf_20261112_154739_cbf1126c-f6d8-4a8a-b11f-bedda6503a4e.png",
    "tier_18": "hf_20261112_154739_47747736-98d4-460e-9db8-d91ed77a2249.png",
    "tier_19": "hf_20261112_154819_13175591-8d46-419d-8eba-5d1cf2e22eb5.png",
    "tier_20": "hf_20261112_154820_2b3ea08c-86c8-41d1-af4c-1f20e21fd17b.png",
}
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server", "pwr", "assets")


def covers():
    """Свои обложки тир-кейсов из Higgsfield → server/pwr/assets/<имя>_<размер>.webp. Не скачалось — остаётся запасная."""
    done = 0
    for name, src in COVERS.items():
        mark = os.path.join(ASSETS, name + ".hf")
        if os.path.exists(mark):
            done += 1
            continue
        try:
            from PIL import Image
            data = urllib.request.urlopen(urllib.request.Request(CDN_USER + src, headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read()
            im = Image.open(io.BytesIO(data)).convert("RGB")
            side = min(im.size)
            im = im.crop(((im.width - side) // 2, (im.height - side) // 2, (im.width + side) // 2, (im.height + side) // 2))
            for size in (64, 128, 256, 512):
                im.resize((size, size), Image.LANCZOS).save(os.path.join(ASSETS, f"{name}_{size}.webp"), "WEBP", quality=86, method=4)
            open(mark, "w").close()
            done += 1
        except Exception as e:
            print(f"обложка {name}: не скачана ({e})", flush=True)
    print(f"обложки тир-кейсов из Higgsfield: {done} из {len(COVERS)}", flush=True)


def main():
    os.makedirs(GEN, exist_ok=True)
    covers()
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
