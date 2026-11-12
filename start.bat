@echo off
chcp 65001 >nul
rem NePridymal — запуск на Windows: двойной клик по start.bat
cd /d "%~dp0"
setlocal
set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul && set "PY=python"
if not defined PY (
  where winget >nul 2>nul || (
    echo Python 3.11+ не найден, и winget тоже нет.
    echo Поставь Python вручную: https://www.python.org/downloads/  ^(галочку "Add python.exe to PATH" при установке^)
    echo Потом запусти start.bat ещё раз.
    pause
    exit /b 1
  )
  echo Python 3.11+ не найден. Ставлю через winget...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo Python установлен. Закрой это окно и запусти start.bat ещё раз.
  pause
  exit /b 1
)
if not exist venv\Scripts\python.exe (
  echo Создаю окружение Python, один раз...
  %PY% -m venv venv || (echo Не удалось создать venv & pause & exit /b 1)
)
venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt || (echo Не удалось поставить зависимости & pause & exit /b 1)
venv\Scripts\python.exe run.py
pause
