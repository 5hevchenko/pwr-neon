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
    "game_crash": ("hf_20261113_183944_e4ed7d97-cb76-4f9a-a3eb-2de93872aa36.png", 480),
    "game_mines": ("hf_20261113_183944_329b6858-0725-4e29-93e2-187a2a5d613b.png", 480),
    "game_slots": ("hf_20261113_183943_d65ca5ab-2178-4fc0-8893-5eb2d5ef7c12.png", 480),
    "game_wheel": ("hf_20261113_184103_76c2341b-8a69-40d5-9640-b59e94c5047c.png", 480),
    "game_dice": ("hf_20261113_184104_2a2abba0-493e-4c61-958f-583abe6dd84d.png", 480),
    # плитки игр перерисованы 13 ноября: вертикальная мультяшная иллюстрация 3:4 под большую сетку в два столбца; было — в том же виде, что и первые пять; имя файла целиком, с датой
    "game_avia": ("hf_20261113_184103_06128000-0ea1-4416-a5b7-6ddf66f2b3e3.png", 480),
    "game_battle": ("hf_20261113_184103_f6972a4a-02d6-42b2-be52-fe82ec448f66.png", 480),
    "game_blackjack": ("hf_20261113_184152_5d2adbc4-55e5-4fc7-afb3-3be93335b86b.png", 480),
    "game_101": ("hf_20261113_184152_b557458f-e96b-4887-952b-57676f33c0b6.png", 480),
    "game_chicken": ("hf_20261113_183944_b97ab74e-1a86-4952-b9a4-c87e15c3de36.png", 480),
    "game_claw": ("hf_20261113_184153_c3e0e6a0-f2e6-4b9c-a7e7-76da04b59098.png", 480),
    "game_darts": ("hf_20261113_184152_30b5c279-ba93-40e5-b5fd-e690fbac1dcb.png", 480),
    "game_dogs": ("hf_20261113_184335_ef739df6-1ed1-4bb0-8f96-6e77ebf78285.png", 480),
    "game_drill": ("hf_20261113_184336_3674d787-012b-40fd-ba42-af11cfeada83.png", 480),
    "game_fish": ("hf_20261113_184334_e89953e6-b468-4253-acef-a85b6ea2cde1.png", 480),
    "game_forecast": ("hf_20261113_184334_90431eec-bfb4-4d23-aa59-2dcb79cccbc8.png", 480),
    "game_duels": ("hf_20261113_184443_a9aeddd2-122c-4f60-a023-b8cf501c8e83.png", 480),
    "game_upgrade": ("hf_20261113_184443_bb867b91-09a4-4d37-aadf-c2071f94b8ff.png", 480),
    "game_swap": ("hf_20261113_184443_dbeabc7b-2d01-499b-9dcf-ddd3bbe480b9.png", 480),
    "game_tower": ("hf_20261113_184443_770c8dee-0bdb-4d71-99cc-8481ee336621.png", 480),
    "game_limbo": ("hf_20261113_184524_da4e1fcd-130a-4cba-8c28-4ff07febeb4b.png", 480),
    "game_jroul": ("hf_20261113_184524_9da615e1-ac27-4a25-af3b-ba10ecc67cdd.png", 480),
    "game_rlt": ("hf_20261113_184524_7cb5ff88-7acd-42c5-a620-2a28d3af373f.png", 480),
    "game_hilo": ("hf_20261113_184524_7f9ca5ad-e277-46db-bfb3-421387ec53da.png", 480),
    "game_craft": ("hf_20261113_184623_92ba20f0-2080-443f-8485-fd9d4fe68870.png", 480),
    "game_carousel": ("hf_20261113_184624_ed492cac-e4b3-4e87-b807-2fe96acbac4d.png", 480),
    "game_safe": ("hf_20261113_184620_b2bc3809-2f52-4b2d-880b-ec22f643cbd8.png", 480),
    "game_ladder": ("hf_20261113_184620_a7607e43-386f-4cd9-9981-3a13e917446a.png", 480),
    "game_bankbet": ("hf_20261113_184725_784c24c3-e9cd-4df5-b5a1-ee12bc7f2e7e.png", 480),
    "game_auction": ("hf_20261113_184724_5299d1ef-2f02-4db3-8f74-3359c4469a60.png", 480),
    "game_keno": ("hf_20261113_184725_3426900f-df84-4426-8bd1-8d031799f4b9.png", 480),
    "game_penalty": ("hf_20261113_184725_339c85f1-20c3-4fb1-9534-1d30d9281872.png", 480),
    "game_plinko": ("hf_20261113_184822_ba202067-b1d2-4887-9419-52692613be86.png", 480),
    "game_pump": ("hf_20261113_184821_2ed347fa-55b6-425a-a47d-6805b016405b.png", 480),
    "game_guess": ("hf_20261113_184821_0ba1d4b7-a7f8-42bd-91d9-ef7feacc053c.png", 480),
    "game_scratch": ("hf_20261113_184821_9d1e422a-f37b-49e1-a5af-27888c411fa5.png", 480),
    "game_stack": ("hf_20261113_184927_e6af8634-ca3f-4928-9d2e-88d97d39f827.png", 480),
    "game_starfall": ("hf_20261113_184924_3c3e503d-4a32-4266-ae73-6d1155737f82.png", 480),
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
    # кейсы пропуска
    "pass_free": "hf_20261112_162055_b7f2c3c2-5b7d-408b-9c71-ff9e88ad3476.png",
    "pass_pwr": "hf_20261112_162123_6fd960d8-b594-4529-976c-5c57783a7798.png",
    "pass_vip": "hf_20261112_162123_774d0bf7-b7f3-4296-bfa3-8e29052fc4b3.png",
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
    print(f"обложки кейсов из Higgsfield: {done} из {len(COVERS)}", flush=True)


def main():
    os.makedirs(GEN, exist_ok=True)
    covers()
    ready = {}
    for name, (src, width) in ART.items():
        out = os.path.join(GEN, name + (".webp" if width else ".mp4"))
        if not os.path.exists(out):
            try:
                data = urllib.request.urlopen(urllib.request.Request((CDN_USER if src.startswith("hf_") else CDN) + src, headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read()
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
