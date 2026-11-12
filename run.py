"""Запуск NePridymal одной командой (Windows / Linux / macOS).

  start.bat / ./start.sh        — первый запуск: спросит токен бота и твой Telegram ID, предложит автозапуск
  python run.py --install       — включить автозапуск (systemd / launchd / Планировщик Windows)
  python run.py --uninstall     — выключить автозапуск
  python run.py --status        — работает ли автозапуск, где логи

Что делает: поднимает бесплатный HTTPS-туннель Cloudflare (Telegram открывает игру только по https),
собирает фронтенд, ставит боту кнопку «Играть», запускает сервер и следит за ним — упал или перезапустился
после импорта базы из админки — поднимает снова. Раз в 6 часов кладёт бэкап базы в data/backups.

Свой домен с HTTPS? Впиши в .env PUBLIC_URL=https://твой-домен (сервер слушает 127.0.0.1:PORT) — туннель не нужен.
"""
import atexit
import gzip
import json
import os
import platform
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(ROOT, ".env")
DATA = os.path.join(ROOT, "data")
BIN = os.path.join(ROOT, "bin")
LOGS = os.path.join(DATA, "logs")
BACKUPS = os.path.join(DATA, "backups")
SYSTEM = platform.system().lower()          # linux / darwin / windows
SERVICE = "nepridymal"
BACKUP_EVERY, BACKUP_KEEP = 6 * 3600, 28
HEADLESS = not sys.stdin or not sys.stdin.isatty()   # автозапуск: спрашивать некого
DRY = "--dry-run" in sys.argv                         # --install --dry-run: показать, что будет установлено, ничего не меняя


def say(msg):
    print(msg, flush=True)


# ---------------- настройки (.env) ----------------
def load_env():
    env = {}
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def save_env(env):
    with open(ENV, "w", encoding="utf-8") as f:
        f.write("# Настройки запуска NePridymal (не выкладывай этот файл — тут токен бота)\n")
        for k, v in env.items():
            f.write(f"{k}={v}\n")
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass


def tg(token, method, **params):
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=json.dumps(params).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def setup(env):
    """Спрашиваем токен (пока не подойдёт) и ID админа. В фоне (автозапуск) — только проверяем, что всё есть."""
    if HEADLESS:
        if not env.get("BOT_TOKEN") or not env.get("BOT_USERNAME"):
            sys.exit("Нет .env с токеном бота — сначала запусти start.bat / ./start.sh вручную.")
        return env
    while True:
        token = env.get("BOT_TOKEN") or input("\nВставь токен бота от @BotFather и нажми Enter:\n> ").strip()
        try:
            me = tg(token, "getMe")["result"]
            env["BOT_TOKEN"], env["BOT_USERNAME"] = token, me["username"]
            say(f"Бот найден: @{me['username']}")
            break
        except Exception:
            say("Токен не подошёл (или нет интернета). Проверь и вставь ещё раз.")
            env.pop("BOT_TOKEN", None)
    if "ADMIN_IDS" not in env:
        a = input("\nТвой Telegram ID для админ-панели (узнать у @userinfobot). Enter — пропустить:\n> ").strip()
        env["ADMIN_IDS"] = ",".join(x for x in re.split(r"[ ,;]+", a) if x.isdigit())
    env.setdefault("PORT", "8795")
    env.setdefault("PUBLIC_URL", "")
    save_env(env)
    return env


# ---------------- туннель Cloudflare ----------------
def cloudflared_path():
    arch = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(arch, "arm" if arch.startswith("arm") else "386")
    exe = os.path.join(BIN, "cloudflared.exe" if SYSTEM == "windows" else "cloudflared")
    if os.path.exists(exe):
        return exe
    found = shutil.which("cloudflared")
    if found:
        return found
    os.makedirs(BIN, exist_ok=True)
    base = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    name = {"windows": f"cloudflared-windows-{arch}.exe", "linux": f"cloudflared-linux-{arch}", "darwin": f"cloudflared-darwin-{arch}.tgz"}.get(SYSTEM)
    if not name:
        sys.exit(f"Не знаю, где взять cloudflared для {SYSTEM}. Поставь его сам: https://github.com/cloudflare/cloudflared")
    say(f"Скачиваю cloudflared ({name}) — один раз…")
    tmp = exe + ".part"
    urllib.request.urlretrieve(base + name, tmp)
    if name.endswith(".tgz"):
        with tarfile.open(tmp) as t:
            t.extract("cloudflared", BIN)
        os.remove(tmp)
    else:
        os.replace(tmp, exe)
    os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
    return exe


def start_tunnel(port):
    """Возвращает (процесс, https-адрес). Адрес случайный и меняется, только если туннель перезапустился."""
    exe = cloudflared_path()
    say("Поднимаю HTTPS-туннель…")
    p = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         **_no_window())
    atexit.register(p.terminate)
    url, deadline = None, time.time() + 90
    while time.time() < deadline:
        line = p.stdout.readline()
        if not line:
            if p.poll() is not None:
                break
            continue
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            url = m.group(0)
            break
    if not url:
        p.terminate()
        return None, None
    threading.Thread(target=lambda: [None for _ in p.stdout], daemon=True).start()   # читаем лог, чтобы туннель не встал
    return p, url


def _no_window():
    """На Windows дочерние процессы без чёрного окна."""
    return {"creationflags": 0x08000000} if SYSTEM == "windows" else {}


# ---------------- HTTPS по IP без домена (Let's Encrypt, короткоживущий сертификат) ----------------
LEGO_VER = "5.5.2"
CERTS = os.path.join(DATA, "certs")


def lego_path():
    """ACME-клиент lego (один бинарник под Windows / Linux / macOS); скачиваем один раз, сверяем SHA-256."""
    import hashlib, zipfile
    exe = os.path.join(BIN, "lego.exe" if SYSTEM == "windows" else "lego")
    if os.path.exists(exe):
        return exe
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    if not arch or SYSTEM not in ("linux", "darwin", "windows"):
        return None
    name = f"lego_v{LEGO_VER}_{SYSTEM}_{arch}." + ("zip" if SYSTEM == "windows" else "tar.gz")
    base = f"https://github.com/go-acme/lego/releases/download/v{LEGO_VER}/"
    os.makedirs(BIN, exist_ok=True)
    say(f"Скачиваю lego ({name}) — один раз…")
    tmp = os.path.join(BIN, name)
    urllib.request.urlretrieve(base + name, tmp)
    sums = urllib.request.urlopen(base + f"lego_{LEGO_VER}_checksums.txt", timeout=30).read().decode()
    want = next((l.split()[0] for l in sums.splitlines() if l.strip().endswith(name)), None)
    got = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
    if want != got:
        os.remove(tmp)
        say("lego: контрольная сумма не совпала — не использую")
        return None
    if name.endswith(".zip"):
        with zipfile.ZipFile(tmp) as z:
            z.extract("lego.exe", BIN)
    else:
        with tarfile.open(tmp) as t:
            t.extract("lego", BIN)
    os.remove(tmp)
    os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
    return exe


def public_ip():
    """Внешний IPv4 этого компьютера (None — если его нет: домашняя сеть за роутером, мобильный интернет и т. п.)."""
    import ipaddress
    for url in ("https://api.ipify.org", "https://ipv4.icanhazip.com", "https://ifconfig.me/ip"):
        try:
            ip = urllib.request.urlopen(url, timeout=10).read().decode().strip()
            if ipaddress.ip_address(ip).is_global and ipaddress.ip_address(ip).version == 4:
                return ip
        except Exception:
            continue
    return None


def ip_cert(ip, quiet=False):
    """Получить / продлить сертификат на IP. lego сам ненадолго слушает порт 80 (проверка Let's Encrypt).
    Возвращает (crt, key) или None. Повторный вызов продлевает, только если пора (сертификат живёт ~6 дней)."""
    exe = lego_path()
    if not exe:
        return None
    if SYSTEM == "linux" and hasattr(os, "geteuid") and os.geteuid() != 0:
        if not quiet:
            say("Сертификат на IP: нужны порты 80 и 443, а для них на Linux нужен root — запусти: sudo ./start.sh")
        return None
    if SYSTEM == "windows":   # входящие 80/443 в брандмауэре (нужны права администратора; без них — как получится)
        _run(["netsh", "advfirewall", "firewall", "add", "rule", "name=NePridymal HTTPS", "dir=in", "action=allow",
              "protocol=TCP", "localport=80,443"], check=False)
    crt, key = os.path.join(CERTS, "certificates", f"{ip}.crt"), os.path.join(CERTS, "certificates", f"{ip}.key")
    cmd = [exe, "run", "--accept-tos", "--server", "letsencrypt", "--domains", ip, "--profile", "shortlived",
           "--http", "--http.address", ":80", "--path", CERTS, "--log.format", "text", "--log.level", "warn"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, **_no_window())
    except Exception as e:
        r = None
        err = str(e)
    if os.path.exists(crt) and os.path.exists(key) and (r is None or r.returncode == 0 or os.path.getsize(crt)):
        return crt, key
    if not quiet:
        out = (r.stderr or r.stdout).strip().splitlines()[-1:] if r else [err]
        say("Сертификат на IP не получился: " + (out[0][:200] if out else "?") +
            "\n(нужен публичный IP и открытые порты 80 и 443 — на VPS обычно так и есть)")
    return None


# ---------------- бэкапы ----------------
def backup(db_path):
    """Горячая копия SQLite → gzip в data/backups, храним BACKUP_KEEP последних."""
    if not os.path.exists(db_path):
        return
    os.makedirs(BACKUPS, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d-%H%M")
    tmp = os.path.join(BACKUPS, f"game-{stamp}.db")
    src, dst = sqlite3.connect(db_path), sqlite3.connect(tmp)
    src.backup(dst)
    dst.close()
    src.close()
    with open(tmp, "rb") as f, gzip.open(tmp + ".gz", "wb", 6) as g:
        shutil.copyfileobj(f, g)
    os.remove(tmp)
    old = sorted(f for f in os.listdir(BACKUPS) if f.startswith("game-") and f.endswith(".db.gz"))
    for f in old[:-BACKUP_KEEP]:
        os.remove(os.path.join(BACKUPS, f))
    say(f"Бэкап базы: data/backups/game-{stamp}.db.gz")


# ---------------- перенос с другого хостинга ----------------
RESTORE_NAMES = ("restore.tar.gz", "restore.tgz", "restore.db.gz", "restore.db")


def _valid_db(path):
    """Это действительно база игры (SQLite + есть таблица users)?"""
    try:
        with open(path, "rb") as f:
            if f.read(16) != b"SQLite format 3\x00":
                return False
        c = sqlite3.connect(path)
        ok = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        c.close()
        return bool(ok)
    except Exception:
        return False


def _find_restore():
    import glob
    for n in RESTORE_NAMES:
        p = os.path.join(ROOT, n)
        if os.path.exists(p):
            return p
    g = sorted(glob.glob(os.path.join(ROOT, "np-snapshot-*.tar.gz")))
    return g[-1] if g else None


def restore_if_present(db_path):
    """Разворачивание с другого сервера одним файлом. Если рядом с игрой лежит restore.tar.gz /
    restore.db(.gz) или np-snapshot-*.tar.gz — переносим базу (из снапшота ещё и загрузки web/u) на место,
    прежнюю базу сохраняем в backups, файл помечаем использованным. Запускается сам при старте."""
    src = _find_restore()
    if not src:
        return
    say(f"\nНайден файл переноса: {os.path.basename(src)} — разворачиваю состояние игры…")
    os.makedirs(DATA, exist_ok=True)
    web_u = os.path.join(ROOT, "web", "u")
    stamp = time.strftime("%Y-%m-%d-%H%M")
    staged = os.path.join(DATA, f".restore-{stamp}.db")
    got_db, n_up = False, 0
    try:
        if src.endswith((".tar.gz", ".tgz")):
            with tarfile.open(src, "r:gz") as tar:
                for m in tar.getmembers():
                    if not m.isfile():
                        continue
                    name = m.name.replace("\\", "/").lstrip("/")
                    if ".." in name.split("/"):        # защита от выхода за пределы папки
                        continue
                    fobj = tar.extractfile(m)
                    if fobj is None:
                        continue
                    data = fobj.read()
                    base = os.path.basename(name)
                    if base == "game.db":
                        open(staged, "wb").write(data)
                        got_db = True
                    elif base == "logs.db":
                        open(os.path.join(DATA, "logs.db"), "wb").write(data)
                    elif name.startswith("u/") or "/u/" in ("/" + name):   # загрузки (аватарки/баннеры)
                        rel = ("/" + name).split("/u/", 1)[1]
                        dst = os.path.join(web_u, rel)
                        os.makedirs(os.path.dirname(dst) or web_u, exist_ok=True)
                        open(dst, "wb").write(data)
                        n_up += 1
        else:   # голый game.db или game.db.gz (например, из «Экспорта» в админке)
            raw = open(src, "rb").read()
            if src.endswith(".gz"):
                raw = gzip.decompress(raw)
            open(staged, "wb").write(raw)
            got_db = True
        if got_db:
            if not _valid_db(staged):
                say("Файл переноса не похож на базу игры — импорт отменён, запускаюсь как есть.")
                os.path.exists(staged) and os.remove(staged)
                return
            if os.path.exists(db_path):
                backup(db_path)   # прежнюю базу — в data/backups на всякий случай
            src_db, dst_db = sqlite3.connect(staged), sqlite3.connect(db_path)
            src_db.backup(dst_db)   # перенос через backup API — целостно
            dst_db.close()
            src_db.close()
            users = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM users").fetchone()[0]
            say(f"База перенесена: {users} игроков" + (f", загрузок (аватарки/баннеры): {n_up}" if n_up else ""))
        elif n_up:
            say(f"Перенесены только загрузки: {n_up} файлов (базы game.db в архиве не было).")
        else:
            say("В файле переноса не нашлось ни базы, ни загрузок — пропускаю.")
        used = os.path.join(DATA, f"imported-{stamp}-{os.path.basename(src)}")
        os.replace(src, used)   # пометили использованным, чтобы не импортировать повторно при каждом старте
        say(f"Файл переноса убран в data/{os.path.basename(used)} — при следующем старте не тронется.")
    except Exception as e:
        say(f"Не удалось развернуть перенос ({e}) — запускаюсь с текущей базой.")
    finally:
        os.path.exists(staged) and os.remove(staged)


# ---------------- сервер ----------------
def serve():
    """Дочерний процесс: сам сервер игры (окружение готовит сторож)."""
    if sys.stdout is None or sys.stderr is None:   # Windows-автозапуск (pythonw): консоли нет — пишем в общий лог
        _log_to_file()
    server = os.path.join(ROOT, "server")
    os.chdir(server)
    sys.path.insert(0, server)
    import uvicorn
    tls = {"ssl_certfile": os.environ["SSL_CERT"], "ssl_keyfile": os.environ["SSL_KEY"]} if os.environ.get("SSL_CERT") else {}
    uvicorn.run("app:app", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ["PORT"]), workers=1,
                log_level="warning", **tls)


def supervise(env):
    """Сторож: туннель + сервер; сервер упал / завершился после импорта базы — поднимаем снова. Плюс бэкапы."""
    port = int(env.get("PORT") or 8795)
    fixed = env.get("PUBLIC_URL", "").rstrip("/")
    mode = (env.get("HTTPS") or "auto").lower()      # auto | ip | tunnel  (PUBLIC_URL — свой домен/прокси)
    tunnel, public, tls, ip = None, fixed, None, None
    if not fixed and mode in ("auto", "ip"):
        ip = public_ip()
        if ip:
            say(f"Публичный IP: {ip} — получаю сертификат Let's Encrypt на него (домен не нужен)…")
            tls = ip_cert(ip)
        if tls:
            public, port = f"https://{ip}", 443
            say("Сертификат готов — игра будет по постоянному адресу, туннель не нужен.")
        elif mode == "ip":
            sys.exit("Режим HTTPS=ip, но сертификат на IP получить не удалось (см. выше).")
        else:
            say("Без публичного IP — включаю бесплатный туннель Cloudflare (адрес будет меняться при перезапуске).")
    if not public:
        tunnel, public = start_tunnel(port)
    if not public:
        sys.exit("Не удалось поднять туннель Cloudflare. Проверь интернет и запусти снова.")
    os.makedirs(DATA, exist_ok=True)
    db_path = os.environ.get("DB_PATH") or os.path.join(DATA, "game.db")
    restore_if_present(db_path)   # перенос с другого сервера: restore.* / np-snapshot-*.tar.gz рядом с игрой
    child_env = {**os.environ, "BOT_TOKEN": env["BOT_TOKEN"], "BOT_USERNAME": env["BOT_USERNAME"],
                 "ADMIN_IDS": env.get("ADMIN_IDS", ""), "SERVE_WEB": "1", "WEB_DIR": os.path.join(ROOT, "web"),
                 "DB_PATH": db_path, "SETTINGS": os.path.join(ROOT, "settings.toml"), "PORT": str(port),
                 "PYTHONIOENCODING": "utf-8"}
    if tls:
        child_env.update(HOST="0.0.0.0", SSL_CERT=tls[0], SSL_KEY=tls[1])
    renew = {"at": time.time(), "busy": False}
    def renew_cert(child_ref):   # в фоне: lego может подождать; продлил — перезапускаем сервер с новым сертификатом
        before = os.path.getmtime(tls[0])
        try:
            if ip_cert(ip, quiet=True) and os.path.getmtime(tls[0]) != before:
                say("Сертификат продлён — перезапускаю сервер")
                child_ref[0].terminate()
        finally:
            renew["busy"] = False
    say("Собираю фронтенд…")
    subprocess.check_call([sys.executable, os.path.join(ROOT, "build.py")], **_no_window())
    last_backup, fails = time.time(), 0
    while True:
        child_env["APP_URL"] = public + "/np/"   # бот ставит кнопку «Играть» на этот адрес при каждом старте сервера
        say(f"\nИгра запущена: {public}/np/\nОткрой бота @{env['BOT_USERNAME']} в Telegram → кнопка «Играть».")
        if not HEADLESS:
            say("Окно не закрывай — пока оно открыто, игра работает (или включи автозапуск: python run.py --install). Ctrl+C — стоп.\n")
        started = time.time()
        child = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--serve"], env=child_env, **_no_window())
        ref = [child]
        while child.poll() is None:
            time.sleep(2)
            if tls and not renew["busy"] and time.time() - renew["at"] >= 12 * 3600:
                renew.update(at=time.time(), busy=True)
                threading.Thread(target=renew_cert, args=(ref,), daemon=True).start()
            if time.time() - last_backup >= BACKUP_EVERY:
                last_backup = time.time()
                try:
                    backup(db_path)
                except Exception as e:
                    say(f"Бэкап не удался: {e}")
            if tunnel and tunnel.poll() is not None:   # туннель умер — новый адрес, сервер перезапустим с ним
                say("Туннель оборвался — поднимаю заново…")
                tunnel, url = start_tunnel(port)
                if url:
                    public = url
                child.terminate()
        fails = fails + 1 if time.time() - started < 30 else 0
        wait = min(60, 3 * fails) or 2
        say(f"Сервер остановился (код {child.returncode}) — перезапуск через {wait} с…")
        time.sleep(wait)


# ---------------- автозапуск ----------------
def _python():
    """Python из venv; на Windows — pythonw (без окна)."""
    if SYSTEM == "windows":
        w = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
        return w if os.path.exists(w) else sys.executable
    v = os.path.join(ROOT, "venv", "bin", "python")
    return v if os.path.exists(v) else sys.executable


def _run(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True, **_no_window())
    if check and r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return r


def install():
    py, script, log = _python(), os.path.abspath(__file__), os.path.join(LOGS, "run.log")
    os.makedirs(LOGS, exist_ok=True)
    if SYSTEM == "linux":
        root = hasattr(os, "geteuid") and os.geteuid() == 0
        unit = (f"[Unit]\nDescription=NePridymal (Telegram Mini App)\nAfter=network-online.target\nWants=network-online.target\n\n"
                f"[Service]\nWorkingDirectory={ROOT}\nExecStart={py} {script}\nRestart=always\nRestartSec=5\n"
                f"StandardOutput=append:{log}\nStandardError=append:{log}\nEnvironment=PYTHONUNBUFFERED=1\n\n"
                f"[Install]\nWantedBy={'multi-user.target' if root else 'default.target'}\n")
        if root:
            path, ctl = f"/etc/systemd/system/{SERVICE}.service", ["systemctl"]
        else:
            path, ctl = os.path.expanduser(f"~/.config/systemd/user/{SERVICE}.service"), ["systemctl", "--user"]
        if os.path.exists(path) and f"WorkingDirectory={ROOT}\n" not in open(path).read():   # чужая служба с тем же именем
            raise RuntimeError(f"служба {SERVICE} уже есть ({path}) и запускает игру из другой папки — не трогаю её")
        if DRY:
            return f"[проверка] {path}:\n{unit}"
        if not shutil.which("systemctl"):
            raise RuntimeError("нет systemd — добавь в crontab строку: @reboot " + f"{py} {script} >> {log} 2>&1")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(unit)
        _run(ctl + ["daemon-reload"])
        _run(ctl + ["enable", "--now", SERVICE])
        if not root:   # чтобы пользовательская служба жила и без входа в систему
            _run(["loginctl", "enable-linger", os.environ.get("USER", "")], check=False)
        return f"служба systemd {SERVICE} ({path}); лог: {log}"
    if SYSTEM == "darwin":
        label = "com.nepridymal.game"
        path = os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist")
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key><array><string>{py}</string><string>{script}</string></array>
  <key>WorkingDirectory</key><string>{ROOT}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
  <key>EnvironmentVariables</key><dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
</dict></plist>
"""
        if DRY:
            return f"[проверка] {path}:\n{plist}"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _run(["launchctl", "unload", path], check=False)
        open(path, "w").write(plist)
        _run(["launchctl", "load", "-w", path])
        return f"агент launchd {label} ({path}); лог: {log}"
    if SYSTEM == "windows":
        # при входе в Windows, без окна; лог пишет сам run.py (pythonw без консоли)
        if DRY:
            return f'[проверка] schtasks /Create /F /TN NePridymal /SC ONLOGON /RL LIMITED /TR "\\"{py}\\" \\"{script}\\""'
        _run(["schtasks", "/Create", "/F", "/TN", "NePridymal", "/SC", "ONLOGON", "/RL", "LIMITED",
              "/TR", f'"{py}" "{script}"'])
        _run(["schtasks", "/Run", "/TN", "NePridymal"], check=False)
        return f"задача Планировщика «NePridymal» (при входе в Windows); лог: {log}"
    raise RuntimeError(f"автозапуск для {SYSTEM} не умею")


def uninstall():
    if SYSTEM == "linux":
        for ctl, path in ((["systemctl"], f"/etc/systemd/system/{SERVICE}.service"),
                          (["systemctl", "--user"], os.path.expanduser(f"~/.config/systemd/user/{SERVICE}.service"))):
            if os.path.exists(path):
                _run(ctl + ["disable", "--now", SERVICE], check=False)
                os.remove(path)
                _run(ctl + ["daemon-reload"], check=False)
    elif SYSTEM == "darwin":
        path = os.path.expanduser("~/Library/LaunchAgents/com.nepridymal.game.plist")
        if os.path.exists(path):
            _run(["launchctl", "unload", "-w", path], check=False)
            os.remove(path)
    elif SYSTEM == "windows":
        _run(["schtasks", "/End", "/TN", "NePridymal"], check=False)
        _run(["schtasks", "/Delete", "/F", "/TN", "NePridymal"], check=False)
    return "автозапуск выключен"


def status():
    if SYSTEM == "linux":
        for ctl in (["systemctl"], ["systemctl", "--user"]):
            r = _run(ctl + ["is-active", SERVICE], check=False) if shutil.which("systemctl") else None
            if r and r.stdout.strip() in ("active", "activating"):
                return f"работает ({' '.join(ctl)}); лог: {os.path.join(LOGS, 'run.log')}"
    elif SYSTEM == "darwin":
        if _run(["launchctl", "list", "com.nepridymal.game"], check=False).returncode == 0:
            return f"работает (launchd); лог: {os.path.join(LOGS, 'run.log')}"
    elif SYSTEM == "windows":
        if _run(["schtasks", "/Query", "/TN", "NePridymal"], check=False).returncode == 0:
            return f"включён (Планировщик Windows); лог: {os.path.join(LOGS, 'run.log')}"
    return "автозапуск не включён"


def _log_to_file():
    """В фоне (автозапуск на Windows — pythonw без консоли) пишем вывод в data/logs/run.log; больше 5 МБ — начинаем заново."""
    os.makedirs(LOGS, exist_ok=True)
    path = os.path.join(LOGS, "run.log")
    if os.path.exists(path) and os.path.getsize(path) > 5 * 1024 * 1024:
        os.replace(path, path + ".1")
    f = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f


def main():
    if sys.version_info < (3, 11):
        sys.exit("Нужен Python 3.11 или новее.")
    args = sys.argv[1:]
    if "--serve" in args:
        return serve()
    if "--install" in args or "--uninstall" in args or "--status" in args:
        try:
            say(install() if "--install" in args else uninstall() if "--uninstall" in args else status())
        except Exception as e:
            sys.exit(f"Не получилось: {e}")
        return
    if HEADLESS and (SYSTEM == "windows" or sys.stdout is None or not sys.stdout.isatty()):
        if SYSTEM == "windows":
            _log_to_file()
    try:
        env = setup(load_env())
    except EOFError:   # запуск без консоли (ввод из файла/NUL) — спросить токен некого
        sys.exit("Нужно ответить на пару вопросов (токен бота, твой ID): запусти start.bat двойным кликом или ./start.sh в терминале. "
                 "Либо впиши BOT_TOKEN и BOT_USERNAME в файл .env рядом с run.py.")
    if not HEADLESS and env.get("AUTOSTART_ASKED") != "1":
        env["AUTOSTART_ASKED"] = "1"
        save_env(env)
        if input("\nВключить автозапуск — игра сама стартует после перезагрузки и работает без открытого окна? [Y/n] ").strip().lower() in ("", "y", "д", "да", "yes"):
            try:
                say("Автозапуск включён: " + install())
                say("Игра уже работает в фоне — это окно можно закрыть.")
                return
            except Exception as e:
                say(f"Автозапуск не включился ({e}) — запускаю в этом окне.")
    supervise(env)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nОстановлено.")
