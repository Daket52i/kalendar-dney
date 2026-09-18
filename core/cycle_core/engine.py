"""Строковый интерфейс ядра: строки и JSON на входе, строки и JSON на выходе.

Нужен, чтобы оболочки были тонкими. Kotlin не умеет вызывать Python-функции
с датами и структурами — только со строками; PySide6 умеет всё, но тоже
говорит с ядром через этот слой, чтобы поведение на телефоне и на компьютере
было буквально одним и тем же кодом, а не двумя похожими.
"""

from __future__ import annotations

import calendar
import json
from datetime import date

from . import diary, journal, phrases, predict, reminders
from . import stats as stats_mod
from .reminders import DEFAULT_HOUR, ReminderSettings


def _day(value: str) -> date:
    """Дата из строки. Непонятную строку считаем сегодняшним днём."""
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return date.today()


def _periods(raw: str) -> list:
    return journal.from_json(raw)


def _records(raw: str) -> list:
    return diary.from_json(raw)


def _stats(periods: list):
    return stats_mod.compute(periods)


def summary(periods_json: str, today_iso: str) -> str:
    """Главная строка — то, что приложение говорит при открытии."""
    periods = _periods(periods_json)
    return phrases.today_summary(periods, _stats(periods), _day(today_iso))


def month(periods_json: str, today_iso: str, year: int, month_number: int) -> str:
    """Все дни месяца по строкам — календарь читается как список."""
    periods = _periods(periods_json)
    account = _stats(periods)
    last_day = calendar.monthrange(year, month_number)[1]
    lines = [
        phrases.describe_month_day(periods, account, date(year, month_number, d))
        for d in range(1, last_day + 1)
    ]
    return json.dumps(lines, ensure_ascii=False)


def history(periods_json: str) -> str:
    """История циклов — то, что показывают врачу."""
    return phrases.cycle_history(_periods(periods_json))


def mark_start(periods_json: str, day_iso: str) -> str:
    """Отметка «начались». Возвращает новую историю строкой."""
    return journal.to_json(journal.start_period(_periods(periods_json), _day(day_iso)))


def mark_end(periods_json: str, day_iso: str) -> str:
    """Отметка «закончились»."""
    return journal.to_json(journal.finish_period(_periods(periods_json), _day(day_iso)))


def unmark(periods_json: str, day_iso: str) -> str:
    """Убирает отметку, начавшуюся в этот день. Ошибиться может каждый."""
    return journal.to_json(journal.remove_period(_periods(periods_json), _day(day_iso)))


def state(periods_json: str) -> str:
    """Состояние для кнопок: идут ли месячные и есть ли незакрытая отметка."""
    periods = _periods(periods_json)
    open_period = journal.open_period(periods)
    return json.dumps(
        {
            "open": open_period is not None,
            "has_history": bool(periods),
            # Сколько дней уже идут месячные — чтобы кнопка говорила «Закончились
            # сегодня, третий день», а не просто «Закончились».
            "open_day": (date.today() - open_period.start).days + 1 if open_period else 0,
            "cycles": predict.cycle_number(periods),
        },
        ensure_ascii=False,
    )


def medical_note() -> str:
    return phrases.MEDICAL_NOTE


def day_label(day_iso: str) -> str:
    """Название дня словами — заголовок в дневнике, когда листаешь даты."""
    return phrases.day_label(_day(day_iso))


def diary_day(records_json: str, day_iso: str) -> str:
    """Запись за один день — чтобы показать, что уже отмечено."""
    record = diary.for_day(_records(records_json), _day(day_iso))
    if record is None:
        return "{}"
    item = json.loads(diary.to_json([record]))[0]
    return json.dumps(item, ensure_ascii=False)


def diary_save(
    records_json: str,
    day_iso: str,
    pain: int = 0,
    mood: str = "",
    flow: str = "",
    temperature: float = 0.0,
    pill: int = -1,
    note: str = "",
) -> str:
    """Записывает день. Ноль и пустая строка означают «не отмечено».

    Ноль как «не отмечено» — вынужденное соглашение: через границу с Kotlin
    неудобно передавать отсутствие числа. Дневник от этого не страдает:
    боль 0 в жизни не встречается, температура 0 — тем более.
    """
    records = _records(records_json)
    record = diary.DayRecord(
        day=_day(day_iso),
        pain=pain if pain > 0 else None,
        mood=mood or "",
        flow=flow or "",
        temperature=temperature if temperature > 0 else None,
        pill_taken=None if pill < 0 else bool(pill),
        note=note or "",
    )
    return diary.to_json(diary.upsert(records, record))


def diary_clear(records_json: str, day_iso: str) -> str:
    """Убирает запись за день целиком — вместе с ошибочными отметками."""
    day = _day(day_iso)
    kept = [record for record in _records(records_json) if record.day != day]
    return diary.to_json(kept)


def diary_summary(records_json: str, periods_json: str) -> str:
    """Что видно по дневнику за всё время."""
    return diary.symptom_summary(_records(records_json), _periods(periods_json))


def diary_history_lines(records_json: str, periods_json: str, limit: int = 60) -> list[str]:
    """Записи дневника списком, свежие сверху — по строке на запись.

    Списком, а не одной простыней: оболочка показывает их строками, и каждая
    строка читается голосом целиком. Склеивать их в текст нельзя — заметка
    когда-нибудь да окажется с переносом строки, и список поедет.
    """
    records = _records(records_json)
    periods = _periods(periods_json)
    account = _stats(periods)
    lines: list[str] = []
    for record in sorted(records, key=lambda r: r.day, reverse=True)[:limit]:
        parts = [phrases.day_phrase(record.day)]
        number = predict.day_of_cycle(periods, record.day)
        if number is not None:
            parts.append(phrases.day_of_cycle_phrase(number))
        if record.pain is not None:
            parts.append(f"боль {record.pain} из пяти")
        if record.mood:
            parts.append(record.mood)
        if record.flow:
            parts.append(record.flow)
        if record.temperature is not None:
            parts.append(f"температура {record.temperature:.1f}")
        if record.pill_taken is not None:
            parts.append("таблетка отмечена" if record.pill_taken else "таблетка не отмечена")
        if record.note:
            parts.append(record.note)
        lines.append(": ".join([parts[0], ", ".join(parts[1:])]) if len(parts) > 1
                     else parts[0] + ": запись без подробностей.")
    if not lines:
        return ["Дневник пока пуст."]
    return lines


def diary_history(records_json: str, periods_json: str, limit: int = 60) -> str:
    """Те же записи одной строкой — для тех, кто показывает их текстом."""
    return "\n".join(diary_history_lines(records_json, periods_json, limit))


def diary_history_json(records_json: str, periods_json: str, limit: int = 60) -> str:
    """Записи дневника списком в JSON — оболочка разложит их по строкам."""
    return json.dumps(
        diary_history_lines(records_json, periods_json, limit), ensure_ascii=False
    )


def settings_from_json(raw: str) -> ReminderSettings:
    """Настройки из JSON. Незнакомые поля игнорируем, битые — заменяем умолчанием."""
    defaults = ReminderSettings()
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return defaults
    if not isinstance(data, dict):
        return defaults

    values = {}
    for field_name, default in defaults.__dict__.items():
        value = data.get(field_name, default)
        if isinstance(default, bool):
            values[field_name] = bool(value)
        else:
            try:
                values[field_name] = int(value)
            except (TypeError, ValueError):
                values[field_name] = default
    return ReminderSettings(**values)


def settings_to_json(settings: ReminderSettings) -> str:
    return json.dumps(settings.__dict__, ensure_ascii=False, sort_keys=True)


def reminders_json(
    periods_json: str,
    records_json: str,
    today_iso: str,
    settings_json: str = "{}",
    horizon_days: int = 30,
) -> str:
    """Напоминания на ближайшие дни — оболочка решает, как их показать."""
    periods = _periods(periods_json)
    settings = settings_from_json(settings_json)
    items = reminders.events(
        periods,
        _stats(periods),
        _records(records_json),
        _day(today_iso),
        settings,
        horizon_days=horizon_days,
    )
    return json.dumps(
        [
            {
                "day": item.day.isoformat(),
                "hour": item.hour,
                "kind": item.kind,
                "text": item.text,
                # Ключ для «уже показывали»: без него одно и то же напоминание
                # всплывало бы при каждом запуске.
                "key": f"{item.day.isoformat()}:{item.kind}",
            }
            for item in items
        ],
        ensure_ascii=False,
    )


def reminders_lines(
    periods_json: str,
    records_json: str,
    today_iso: str,
    settings_json: str = "{}",
    limit: int = 10,
) -> str:
    """Ближайшие напоминания строками — то, что читается на экране настроек.

    Формулировку даёт phrases, а не оболочка: иначе телефон и компьютер
    сказали бы об одном и том же разными словами.
    """
    items = json.loads(reminders_json(periods_json, records_json, today_iso, settings_json))
    lines = [
        phrases.reminder_line(date.fromisoformat(item["day"]), item["hour"], item["text"])
        for item in items[:limit]
    ]
    return json.dumps(lines, ensure_ascii=False)


DEFAULT_REMINDER_HOUR = DEFAULT_HOUR
