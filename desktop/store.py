"""Где «Календарь дней» хранит данные на компьютере.

Отдельно от окон: так это можно проверить тестом, не поднимая ни одного окна,
и так же устроена версия для телефона — там файл лежит в папке приложения.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from cycle_core import diary, engine, journal

APP_DIR_NAME = "Календарь дней"

PERIODS_FILE = "history.json"
RECORDS_FILE = "diary.json"
SETTINGS_FILE = "settings.json"
SHOWN_FILE = "shown.json"
#: Настройки самой программы (сворачивать ли в трей, автозапуск) — не про
#: календарь, поэтому и файл отдельный: на телефоне этих вопросов нет.
PREFS_FILE = "prefs.json"

BACKUP_FORMAT = 1


def default_dir() -> Path:
    """Папка с данными: на Windows — в профиле пользователя (APPDATA)."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home()
    return root / APP_DIR_NAME


def _write_atomic(path: Path, text: str) -> None:
    """Пишет через временный файл: обрыв записи не должен съесть историю."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    )
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except OSError:
        # Запасной путь: если переименование не прошло, пишем напрямую.
        path.write_text(text, encoding="utf-8")
        try:
            os.unlink(handle.name)
        except OSError:
            pass


class Store:
    """Файлы с данными. Каталог передаётся снаружи — тесты дают свой."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory else default_dir()

    def _path(self, name: str) -> Path:
        return self.directory / name

    def _read(self, name: str) -> str:
        try:
            return self._path(name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Нет файла или он испорчен — приложение должно открыться с пустой
            # историей, а не показать ошибку при запуске.
            return ""

    def periods_text(self) -> str:
        return self._read(PERIODS_FILE) or "[]"

    def save_periods(self, text: str) -> None:
        _write_atomic(self._path(PERIODS_FILE), text)

    def records_text(self) -> str:
        return self._read(RECORDS_FILE) or "[]"

    def save_records(self, text: str) -> None:
        _write_atomic(self._path(RECORDS_FILE), text)

    def settings_text(self) -> str:
        return self._read(SETTINGS_FILE) or "{}"

    def save_settings(self, text: str) -> None:
        _write_atomic(self._path(SETTINGS_FILE), text)

    def prefs_text(self) -> str:
        return self._read(PREFS_FILE) or "{}"

    def save_prefs(self, text: str) -> None:
        _write_atomic(self._path(PREFS_FILE), text)

    def shown_keys(self) -> set[str]:
        """Какие напоминания уже показывали — чтобы не повторяться."""
        try:
            data = json.loads(self._read(SHOWN_FILE) or "[]")
        except (TypeError, ValueError):
            return set()
        return {str(item) for item in data} if isinstance(data, list) else set()

    def save_shown(self, keys: set[str]) -> None:
        _write_atomic(self._path(SHOWN_FILE), json.dumps(sorted(keys), ensure_ascii=False))

    def backup_text(self) -> str:
        """Вся история одним файлом — чтобы перенести на другой компьютер."""
        return json.dumps(
            {
                "format": BACKUP_FORMAT,
                "made_on": date.today().isoformat(),
                "periods": json.loads(self.periods_text() or "[]"),
                "diary": json.loads(self.records_text() or "[]"),
                "settings": json.loads(self.settings_text() or "{}"),
            },
            ensure_ascii=False,
            indent=2,
        )

    def restore_text(self, text: str) -> str:
        """Возвращает историю и дневник из копии. Строку с ошибкой не применяет."""
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            raise ValueError("Это не файл резервной копии.")
        if not isinstance(data, dict) or "periods" not in data:
            raise ValueError("Это не файл резервной копии «Календарь дней».")

        # Прогоняем через ядро: битые записи отсеются, годные — сохранятся.
        periods = journal.from_json(json.dumps(data.get("periods") or [], ensure_ascii=False))
        records = diary.from_json(json.dumps(data.get("diary") or [], ensure_ascii=False))
        if not periods and not records:
            raise ValueError("В копии нет ни одной записи.")

        self.save_periods(journal.to_json(periods))
        self.save_records(diary.to_json(records))
        settings = data.get("settings")
        if isinstance(settings, dict):
            merged = engine.settings_from_json(json.dumps(settings, ensure_ascii=False))
            self.save_settings(engine.settings_to_json(merged))
        return (
            f"Восстановлено: {len(periods)} отметок месячных, "
            f"{len(records)} записей дневника."
        )
