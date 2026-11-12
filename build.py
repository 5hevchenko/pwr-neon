"""Сборка фронтенда: склеивает стили и скрипты из web/index.src.html в bundle.css / bundle.js
(порядок сохраняется), версия = хэш содержимого, web/index.html генерируется заново.
Править нужно исходники (web/*.js, web/*.css, web/index.src.html), потом запускать этот скрипт (run.py делает это сам)."""
import hashlib
import os
import re

WEB = os.environ.get("WEB_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
rd = lambda f: open(os.path.join(WEB, f), encoding="utf-8").read()
src = rd("index.src.html")
css = re.findall(r'<link rel="stylesheet" href="([a-z0-9]+\.css)\?v=[^"]*">', src)
js = re.findall(r'<script src="([a-z0-9]+\.js)\?v=[^"]*"></script>', src)
cb = "\n".join(rd(f) for f in css)
jb = "\n;\n".join(rd(f) for f in js)
hc, hj = hashlib.md5(cb.encode()).hexdigest()[:10], hashlib.md5(jb.encode()).hexdigest()[:10]
out = re.sub(r'(<link rel="stylesheet" href="[a-z0-9]+\.css\?v=[^"]*">\n?)+', f'<link rel="stylesheet" href="bundle.css?v={hc}">\n', src)
out = re.sub(r'(<script src="[a-z0-9]+\.js\?v=[^"]*"></script>\n?)+', f'<script src="bundle.js?v={hj}"></script>\n', out)
for name, data in (("bundle.css", cb), ("bundle.js", jb), ("index.html", out)):
    with open(os.path.join(WEB, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(data)
print(f"css: {len(css)} файлов ({len(cb) // 1024} КБ); js: {len(js)} файлов ({len(jb) // 1024} КБ)")
