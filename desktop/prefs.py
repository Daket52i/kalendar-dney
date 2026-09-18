"""Настройки самой программы на компьютере.

Здесь то, что касается жизни окна, а не женского календаря: продолжать ли
работу после закрытия окна и запускаться ли вместе с Windows. Ядро об этих
настройках не знает и знать не должно — на телефоне те же вопросы решает
система, и другие.

Модуль намеренно без единого импорта из Qt: его можно проверить тестом, не
поднимая ни одного окна.
"""

from __future__ import annotations

import json
import os
import sys

# Имя записи в автозапуске Windows. Видно пользовательнице в списке
# «Автозагрузка» в диспетчере задач, поэтому по-русски.
AUTOSTART_NAME = "Календарь дней"

#: Ключ автозапуска для текущей пользовательницы — без прав администратора.
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

DEFAULTS = {
    #: Закрыли окно — программа продолжает работать и напоминать.
    "keep_running": True,
    #: Запускаться вместе с Windows, чтобы напоминания не ждали открытия окна.
    "autostart": False,
}


def load(store) -> dict:
    """Настройки окна из файла. Чего нет — берётся по умолчанию."""
    prefs = dict(DEFAULTS)
    try:
        data = json.loads(store.prefs_text() or "{}")
    except (TypeError, ValueError):
        return prefs
    if isinstance(data, dict):
        for key in DEFAULTS:
            if isinstance(data.get(key), bool):
                prefs[key] = data[key]
    return prefs


def save(store, prefs: dict) -> None:
    kept = {key: bool(prefs.get(key, DEFAULTS[key])) for key in DEFAULTS}
    store.save_prefs(json.dumps(kept, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------ Автозапуск


def autostart_supported() -> bool:
    """Автозапуск умеет только Windows."""
    return sys.platform == "win32"


def launch_command() -> str:
    """Команда, которой Windows должна запускать программу.

    Собранная в exe — это сам exe. Запущенная из исходников — pythonw без
    чёрного окна консоли: консоль поверх программы незрячему пользователю
    только мешает.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    python = sys.executable or "python"
    for candidate in ("pythonw.exe", "pythonw"):
        folder = os.path.dirname(python)
        if folder and os.path.exists(os.path.join(folder, candidate)):
            return f'"{os.path.join(folder, candidate)}" "{script}"'
    return f'"{python}" "{script}"'


def _winreg():
    import winreg

    return winreg


def is_autostart_on() -> bool:
    if not autostart_supported():
        return False
    try:
        with _winreg().OpenKey(_winreg().HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            value, _ = _winreg().QueryValueEx(key, AUTOSTART_NAME)
    except OSError:
        return False
    return bool(value)


def set_autostart(on: bool) -> None:
    """Включает или выключает запуск вместе с Windows.

    Ошибку не глотаем: если система не дала записать, пользовательница должна
    узнать об этом сразу, а не обнаружить пропажу напоминаний через неделю.
    """
    if not autostart_supported():
        raise OSError("Автозапуск настроен только для Windows.")
    registry = _winreg()
    with registry.CreateKeyEx(
        registry.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, registry.KEY_SET_VALUE
    ) as key:
        if on:
            registry.SetValueEx(key, AUTOSTART_NAME, 0, registry.REG_SZ, launch_command())
        else:
            try:
                registry.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
