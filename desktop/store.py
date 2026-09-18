"""Где «Календарь дней» хранит данные на компьютере.

Отдельно от окон: так это можно проверить тестом, не поднимая ни одного окна,
и так же устроена версия для телефона — там файл лежит в папке приложения.

Данных стало больше одного набора: у каждого человека свой календарь, свой
дневник и свои настройки напоминаний. Поэтому у человека своя папка, а в корне
лежит только список людей. Общего между календарями нет ничего — иначе мамина
история попала бы в дочкин прогноз.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

from cycle_core import diary, engine, journal, people as people_mod

APP_DIR_NAME = "Календарь дней"

PEOPLE_FILE = "people.json"
#: Папка, в которой лежит по папке на человека. Отдельным именем, потому что
#: рядом живёт сам список людей, и путать одно с другим нельзя.
PEOPLE_DIR = "people"

PERIODS_FILE = "history.json"
RECORDS_FILE = "diary.json"
SETTINGS_FILE = "settings.json"
SHOWN_FILE = "shown.json"
#: Настройки самой программы (сворачивать ли в трей, автозапуск) — не про
#: календарь, поэтому и файл отдельный: на телефоне этих вопросов нет.
PREFS_FILE = "prefs.json"

#: Первая версия копии — один календарь. Вторая — все календари сразу.
BACKUP_FORMAT = 2
BACKUP_FORMAT_SINGLE = 1


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
        self._document = ""
        self._current = ""
        self._first_run = False
        # Разбираем список людей один раз за запуск: он меняется только через
        # сам Store, а читается на каждое обновление экрана.
        self._reload()

    # ------------------------------------------------------------------ Люди

    def _reload(self) -> None:
        raw = self._read(PEOPLE_FILE)
        self._first_run = not raw.strip()
        people, current = people_mod.from_json(raw)
        self._current = current
        self._document = people_mod.to_json(people, current)
        if raw.strip():
            # Список уже есть. Приводим его к нормальному виду, только если он
            # отличается, — лишняя запись на диск при каждом запуске не нужна.
            if raw != self._document:
                self._write_people_file()
            return
        self._adopt_legacy_files()

    def _adopt_legacy_files(self) -> None:
        """Первый запуск: заводит единственный календарь и переносит старые файлы.

        Приложение вышло до того, как появились профили, и у кого-то уже лежит
        история в корне. Переносим её внутрь единственного человека: молча
        потерять чужую историю из-за обновления нельзя. Если в корне мусор от
        более поздней версии — он остаётся на месте, разбирать его не по чему.
        """
        legacy = [self.directory / name for name in (PERIODS_FILE, RECORDS_FILE, SETTINGS_FILE)]
        if any(path.exists() for path in legacy):
            target = self.directory / PEOPLE_DIR / self._current
            target.mkdir(parents=True, exist_ok=True)
            for path in legacy + [self.directory / SHOWN_FILE]:
                if path.exists():
                    try:
                        path.replace(target / path.name)
                    except OSError:
                        pass
        self._write_people_file()

    def _write_people_file(self) -> None:
        _write_atomic(self.directory / PEOPLE_FILE, self._document)

    @property
    def document(self) -> str:
        """Список людей как он есть — его передают в ядро."""
        return self._document

    def person_id(self) -> str:
        return self._current

    def is_first_run(self) -> bool:
        """Списка людей ещё нет — значит, приложение спрашивает имя.

        Спрашивает именно при запуске: до вопроса в списке стоит «Я», и любое
        добавленное имя встало бы рядом с ним вторым календарём. Переименование
        же оставляет человека одного.
        """
        return self._first_run

    def person_name(self) -> str:
        """Имя текущего человека. Пустая строка, только если список пуст —
        а он пустым не бывает."""
        people, _ = people_mod.from_json(self._document)
        return people_mod.name_of(people, self._current)

    def people(self) -> list[people_mod.Person]:
        return people_mod.from_json(self._document)[0]

    def _apply(self, answer_json: str) -> str:
        """Принимает ответ ядра и сохраняет его. Возвращает ошибку словами.

        Ошибка не бросается исключением: оболочка должна показать её голосом и
        продолжить работать, а не упасть.
        """
        answer = json.loads(answer_json)
        if not answer.get("ok"):
            return answer.get("error") or "Не получилось."
        self._document = answer["people"]
        self._current = answer["current"]
        self._write_people_file()
        return ""

    def add_person(self, name: str) -> str:
        return self._apply(engine.person_add(self._document, name))

    def rename_person(self, person_id: str, name: str) -> str:
        return self._apply(engine.person_rename(self._document, person_id, name))

    def switch_person(self, person_id: str) -> str:
        return self._apply(engine.person_switch(self._document, person_id))

    def remove_person(self, person_id: str) -> str:
        error = self._apply(engine.person_remove(self._document, person_id))
        if not error:
            self.forget_person(person_id)
        return error

    def forget_person(self, person_id: str) -> None:
        """Убирает папку человека со всеми его данными.

        Только после того, как он пропал из списка: если удаление файлов не
        удалось, календарь уже не открыть, но и список от этого не разъедется.
        """
        shutil.rmtree(self.directory / PEOPLE_DIR / person_id, ignore_errors=True)

    # --------------------------------------------------------------- Файлы

    def _path(self, name: str) -> Path:
        return self._path_of(self._current, name)

    def _path_of(self, person_id: str, name: str) -> Path:
        """Путь к файлу конкретного человека — не обязательно открытого."""
        return self.directory / PEOPLE_DIR / person_id / name

    def _read(self, name: str) -> str:
        try:
            return (self.directory / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Нет файла или он испорчен — приложение должно открыться с пустой
            # историей, а не показать ошибку при запуске.
            return ""

    def _read_at(self, person_id: str, name: str) -> str:
        try:
            return self._path_of(person_id, name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    def _read_person(self, name: str) -> str:
        return self._read_at(self._current, name)

    def person_data(self, person_id: str) -> tuple[str, str, str, set[str]]:
        """Отметки, дневник, настройки и показанное одного человека.

        Нужно проверке напоминаний: она идёт по всем людям сразу, а не только
        по открытому, и файлы ей нужны чужие, не текущего.
        """
        periods = self._read_at(person_id, PERIODS_FILE) or "[]"
        records = self._read_at(person_id, RECORDS_FILE) or "[]"
        settings = self._read_at(person_id, SETTINGS_FILE) or "{}"
        try:
            data = json.loads(self._read_at(person_id, SHOWN_FILE) or "[]")
        except (TypeError, ValueError):
            data = []
        shown = {str(item) for item in data} if isinstance(data, list) else set()
        return periods, records, settings, shown

    def save_shown_for(self, person_id: str, keys: set[str]) -> None:
        """Отметить показанное человеку, который сейчас даже не открыт."""
        _write_atomic(
            self._path_of(person_id, SHOWN_FILE),
            json.dumps(sorted(keys), ensure_ascii=False),
        )

    def periods_text(self) -> str:
        return self._read_person(PERIODS_FILE) or "[]"

    def save_periods(self, text: str) -> None:
        _write_atomic(self._path(PERIODS_FILE), text)

    def records_text(self) -> str:
        return self._read_person(RECORDS_FILE) or "[]"

    def save_records(self, text: str) -> None:
        _write_atomic(self._path(RECORDS_FILE), text)

    def settings_text(self) -> str:
        return self._read_person(SETTINGS_FILE) or "{}"

    def save_settings(self, text: str) -> None:
        _write_atomic(self._path(SETTINGS_FILE), text)

    def prefs_text(self) -> str:
        return self._read(PREFS_FILE) or "{}"

    def save_prefs(self, text: str) -> None:
        _write_atomic(self.directory / PREFS_FILE, text)

    def shown_keys(self) -> set[str]:
        """Какие напоминания уже показывали — чтобы не повторяться.

        У каждого человека свой список: у мамы с дочкой напоминания совпадают по
        датам, и общий список показал бы дочкино напоминание только один раз.
        """
        try:
            data = json.loads(self._read_person(SHOWN_FILE) or "[]")
        except (TypeError, ValueError):
            return set()
        return {str(item) for item in data} if isinstance(data, list) else set()

    def save_shown(self, keys: set[str]) -> None:
        _write_atomic(self._path(SHOWN_FILE), json.dumps(sorted(keys), ensure_ascii=False))

    # --------------------------------------------------------------- Копии

    def _person_backup(self, person) -> dict:
        folder = self.directory / PEOPLE_DIR / person.id

        def read(name: str, fallback: str) -> str:
            try:
                return (folder / name).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return fallback

        return {
            "id": person.id,
            "name": person.name,
            "periods": json.loads(read(PERIODS_FILE, "[]") or "[]"),
            "diary": json.loads(read(RECORDS_FILE, "[]") or "[]"),
            "settings": json.loads(read(SETTINGS_FILE, "{}") or "{}"),
        }

    def backup_text(self) -> str:
        """Все календари одним файлом — чтобы перенести на другой компьютер.

        Все, а не только открытый: человек, который сохраняет копию, не думает
        о том, чей календарь сейчас на экране, и потерять мамин дневник при
        переносе было бы худшим из возможных сюрпризов.
        """
        return json.dumps(
            {
                "format": BACKUP_FORMAT,
                "made_on": date.today().isoformat(),
                "current": self._current,
                "people": [self._person_backup(person) for person in self.people()],
            },
            ensure_ascii=False,
            indent=2,
        )

    def restore_text(self, text: str) -> str:
        """Возвращает календари из копии. Строку с ошибкой не применяет."""
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            raise ValueError("Это не файл резервной копии.")
        if not isinstance(data, dict):
            raise ValueError("Это не файл резервной копии «Календарь дней».")
        if "people" in data:
            return self._restore_all(data)
        if "periods" in data:
            return self._restore_single(data)
        raise ValueError("Это не файл резервной копии «Календарь дней».")

    def _clean(self, raw, kind: str) -> list:
        """Прогоняем через ядро: битые записи отсеются, годные — сохранятся."""
        payload = json.dumps(raw if isinstance(raw, list) else [], ensure_ascii=False)
        if kind == "periods":
            return journal.from_json(payload)
        return diary.from_json(payload)

    def _restore_all(self, data: dict) -> str:
        people = data.get("people")
        if not isinstance(people, list) or not people:
            raise ValueError("В копии нет ни одного календаря.")

        # Пустые календари тоже переносим: копия должна давать ровно то же, что
        # было, — включая дочкин профиль, который только что завели и ещё не
        # заполнили.
        prepared = []
        for index, item in enumerate(people):
            if not isinstance(item, dict):
                continue
            name = people_mod.clean_name(item.get("name") or "") or f"Календарь {index + 1}"
            prepared.append(
                (
                    name,
                    self._clean(item.get("periods"), "periods"),
                    self._clean(item.get("diary"), "diary"),
                    item.get("settings"),
                )
            )
        if not prepared:
            raise ValueError("В копии нет ни одной записи.")

        # Копия заменяет всё: так перенос на новый компьютер даёт ровно то же,
        # что было, а не смесь из двух устройств.
        shutil.rmtree(self.directory / PEOPLE_DIR, ignore_errors=True)
        people_list: list[people_mod.Person] = []
        for name, _, _, _ in prepared:
            people_list, _ = people_mod.add(people_list, name)
        self._document = people_mod.to_json(people_list, people_list[0].id)
        self._current = people_list[0].id
        self._write_people_file()

        marks = records_total = 0
        for person, (_, periods, records, settings) in zip(people_list, prepared):
            folder = self.directory / PEOPLE_DIR / person.id
            _write_atomic(folder / PERIODS_FILE, journal.to_json(periods))
            _write_atomic(folder / RECORDS_FILE, diary.to_json(records))
            if isinstance(settings, dict):
                merged = engine.settings_from_json(json.dumps(settings, ensure_ascii=False))
                _write_atomic(folder / SETTINGS_FILE, engine.settings_to_json(merged))
            marks += len(periods)
            records_total += len(records)

        if len(people_list) == 1:
            return (
                f"Восстановлено: {marks} отметок месячных, "
                f"{records_total} записей дневника."
            )
        return (
            f"Восстановлено календарей: {len(people_list)}. "
            f"Всего отметок месячных — {marks}, записей дневника — {records_total}."
        )

    def _restore_single(self, data: dict) -> str:
        """Копия первой версии: один календарь, без имён. Кладём его в текущий."""
        periods = self._clean(data.get("periods"), "periods")
        records = self._clean(data.get("diary"), "diary")
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
            f"{len(records)} записей дневника. Имя календаря — {self.person_name()}."
        )
