"""Настройки игры из settings.toml (лежит рядом с папкой server; путь можно задать переменной SETTINGS).
Нет файла или параметра — берётся значение по умолчанию из кода. Читается один раз при запуске:
после правки файла перезапусти игру."""
import os
import tomllib

PATH = os.environ.get("SETTINGS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings.toml"))
try:
    with open(PATH, "rb") as _f:
        _S = tomllib.load(_f)
    print(f"settings: {PATH}", flush=True)
except FileNotFoundError:
    _S = {}
except tomllib.TOMLDecodeError as e:   # опечатка в файле — не падаем, работаем на значениях по умолчанию
    print(f"settings: ОШИБКА в {PATH}: {e} — использую значения по умолчанию", flush=True)
    _S = {}


def conf(key, default):
    """conf("games.edge", 0.96) → значение из [games] edge = …, иначе default. Тип приводится к типу default."""
    sec, _, name = key.partition(".")
    v = _S.get(sec, {}).get(name, default)
    try:
        if isinstance(default, bool):
            return bool(v)
        if isinstance(default, int):
            return int(v)
        if isinstance(default, float):
            return float(v)
        if isinstance(default, list) and isinstance(v, list):
            return [type(default[0])(x) for x in v] if default else v
        if isinstance(default, dict) and isinstance(v, dict):
            return {type(next(iter(default)))(k): x for k, x in v.items()} if default else v
        return v if type(v) is type(default) else default
    except (TypeError, ValueError):
        print(f"settings: неверное значение {key} = {v!r} — беру {default!r}", flush=True)
        return default


_LIVE = {}   # правки шансов из админки (вкладка «Шансы», хранятся в базе) — важнее файла, действуют сразу


def tuned(key, default):
    """Как conf, но с учётом правки из админки. Читать в момент раунда, а не при запуске."""
    v = _LIVE.get(key)
    return conf(key, default) if v is None else v
