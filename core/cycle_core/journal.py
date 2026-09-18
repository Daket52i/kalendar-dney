"""Правки истории: отметки начала и конца, сохранение, чтение.

Тоже чистая логика: список менструаций на входе, список на выходе. Оболочки
(Android и Windows) только сохраняют результат — так поведение отметок
одинаково на обеих платформах и проверяется тестами.
"""

from __future__ import annotations

import json
from datetime import date

from .models import Period, as_periods

DATE_FORMAT = "%Y-%m-%d"


def to_json(periods: list[Period]) -> str:
    """История в строку — её хранит оболочка у себя."""
    data = []
    for period in as_periods(periods):
        item: dict[str, str] = {"start": period.start.strftime(DATE_FORMAT)}
        if period.end is not None:
            item["end"] = period.end.strftime(DATE_FORMAT)
        data.append(item)
    return json.dumps(data, ensure_ascii=False)


def from_json(text: str) -> list[Period]:
    """Читает историю. Битые записи пропускает, а не роняет приложение.

    Терять весь календарь из-за одной испорченной строки нельзя; лучше
    показать остальное и дать поправить.
    """
    try:
        data = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    periods: list[Period] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # date.fromisoformat, а не strptime: он есть во всех версиях Python,
        # которые поддерживает Chaquopy, и не требует строки формата.
        try:
            start = date.fromisoformat(item["start"])
        except (KeyError, TypeError, ValueError):
            continue
        end: date | None = None
        try:
            if item.get("end"):
                end = date.fromisoformat(item["end"])
        except (TypeError, ValueError):
            end = None
        periods.append(Period(start=start, end=end, note=str(item.get("note", ""))))
    return as_periods(periods)


def open_period(periods: list[Period]) -> Period | None:
    """Последняя незакрытая менструация — у неё не отмечен конец."""
    for period in reversed(as_periods(periods)):
        if period.end is None:
            return period
    return None


def start_period(periods: list[Period], day: date) -> list[Period]:
    """Отмечает первый день месячных.

    Если в этот же день отметка уже есть, ничего не меняется — двойное
    нажатие не должно создавать второй цикл. Предыдущую незакрытую запись не
    трогаем: придумывать ей конец за пользовательницу нельзя, а на прогноз
    она не влияет (длины циклов считаются по началам).
    """
    ordered = as_periods(periods)
    if ordered and ordered[-1].start == day:
        return ordered
    ordered.append(Period(start=day))
    return as_periods(ordered)


def finish_period(periods: list[Period], day: date) -> list[Period]:
    """Отмечает последний день месячных у незакрытой записи.

    Если конец раньше начала (пользовательница поправила задним числом) —
    дни меняются местами, а не теряются.
    """
    target = open_period(periods)
    if target is None:
        return as_periods(periods)
    ordered = as_periods(periods)
    for index, period in enumerate(ordered):
        if period.start == target.start:
            ordered[index] = period.with_end(day)
            break
    return as_periods(ordered)


def set_period(periods: list[Period], start: date, end: date | None) -> list[Period]:
    """Правит уже отмеченный цикл — понадобится для ручной правки календаря."""
    ordered = as_periods(periods)
    for index, period in enumerate(ordered):
        if period.start == start:
            ordered[index] = period.with_end(end)
            break
    return as_periods(ordered)


def remove_period(periods: list[Period], start: date) -> list[Period]:
    """Убирает отметку целиком."""
    return [p for p in as_periods(periods) if p.start != start]
