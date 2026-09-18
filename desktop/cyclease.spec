# -*- mode: python ; coding: utf-8 -*-
"""Сборка «Календаря дней» в один запускаемый файл под Windows.

Запуск из папки desktop:

    pyinstaller cyclease.spec

Готовое лежит в dist/KalendarDney/. Ядро (core/cycle_core) попадает внутрь
через pathex — отдельной копии кода для Windows нет, она общая с телефоном.
"""

from pathlib import Path

root = Path(SPECPATH).parent
core = root / "core"
# Путь к значку собираем от самого файла сборки, а не от текущего каталога:
# сборка запускается и из папки desktop, и с сервера — работать должно в обоих
# случаях.
icon_path = Path(SPECPATH) / "cyclease.ico"

a = Analysis(
    ["main.py"],
    pathex=[str(core)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # Тесты и мусор внутрь не тащим: сборка должна быть про приложение.
    excludes=["tkinter", "unittest", "pydoc", "doctest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KalendarDney",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # окно консоли ни к чему: всё в самом приложении
    disable_windowed_traceback=False,
    # Значок для exe. Тот же календарик, что на телефоне; рисуется скриптом
    # tools/make_icons.py из общего с Android рисунка.
    icon=str(icon_path),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KalendarDney",
)
