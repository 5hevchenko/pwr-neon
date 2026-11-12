#!/usr/bin/env bash
# NePridymal — запуск на Linux / macOS одним файлом: ./start.sh
# Сам ставит Python и venv, если их нет, создаёт окружение, ставит зависимости и запускает игру.
set -e
cd "$(dirname "$0")"

SUDO=""
if [ "$(id -u)" != "0" ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

PY=""
have_py() {   # найти python 3.11+ среди известных имён
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
      PY="$c"; return 0
    fi
  done
  return 1
}

pkg_install() {   # поставить пакеты через тот менеджер, что есть в системе (apt/dnf/yum/pacman/zypper/apk/brew)
  if   command -v apt-get >/dev/null 2>&1; then $SUDO apt-get update -y && $SUDO apt-get install -y "$@"
  elif command -v dnf     >/dev/null 2>&1; then $SUDO dnf install -y "$@"
  elif command -v yum     >/dev/null 2>&1; then $SUDO yum install -y "$@"
  elif command -v pacman  >/dev/null 2>&1; then $SUDO pacman -Sy --noconfirm "$@"
  elif command -v zypper  >/dev/null 2>&1; then $SUDO zypper install -y "$@"
  elif command -v apk     >/dev/null 2>&1; then $SUDO apk add "$@"
  elif command -v brew    >/dev/null 2>&1; then brew install "$@"
  else return 1; fi
}

if ! have_py; then
  echo "Python 3.11+ не найден — пробую установить сам…"
  if [ "$(uname)" = "Darwin" ]; then
    pkg_install python3 || pkg_install python || true
  else
    pkg_install python3 python3-venv python3-pip || pkg_install python3 || true
  fi
  have_py || { echo "Не получилось поставить Python автоматически.
Поставь вручную и запусти ещё раз:  Ubuntu/Debian: sudo apt install -y python3 python3-venv python3-pip   ·   macOS: brew install python   ·   Fedora: sudo dnf install -y python3"; exit 1; }
fi

if ! "$PY" -c 'import venv, ensurepip' 2>/dev/null; then   # на Debian/Ubuntu venv — отдельный пакет
  echo "Доустанавливаю модуль venv…"
  pkg_install python3-venv python3-pip || true
fi

if [ ! -x venv/bin/python ]; then
  echo "Создаю окружение Python (один раз)…"
  if ! "$PY" -m venv venv 2>/dev/null; then
    pkg_install python3-venv || true
    "$PY" -m venv venv || { echo "Не удалось создать venv. Поставь python3-venv вручную: sudo apt install -y python3-venv"; exit 1; }
  fi
fi

venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
exec venv/bin/python run.py
