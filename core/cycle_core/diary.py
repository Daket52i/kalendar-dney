"""Дневник самочувствия: хранение записей и выжимка из них.

Записи необязательные. Пустой день — это норма, а не пробел в данных: нельзя
делать вид, что приложение сломано, если пользовательница ничего не отметила.
"""

from __future__ import annotations

import json
import statistics
from datetime import date

from .models import DayRecord, Period, as_periods

# Насколько температура должна подняться над своим обычным уровнем, чтобы
# это считалось сдвигом после овуляции. Полградуса — общепринятая граница,
# но у нас порог мягче: важнее не пропустить подъём, чем ошибиться на день.
TEMPERATURE_RISE = 0.2

# Сколько дней подряд температура должна держаться выше, чтобы мы поверили,
# что это сдвиг, а не случайное измерение.
RISE_DAYS = 3

MIN_TEMPERATURE_DAYS = 5


def to_json(records: list[DayRecord]) -> str:
    data = []
    for record in sorted(records, key=lambda r: r.day):
        item: dict[str, object] = {"day": record.day.isoformat()}
        if record.pain is not None:
            item["pain"] = record.pain
        if record.mood:
            item["mood"] = record.mood
        if record.flow:
            item["flow"] = record.flow
        if record.temperature is not None:
            item["temperature"] = record.temperature
        if record.pill_taken is not None:
            item["pill"] = record.pill_taken
        if record.note:
            item["note"] = record.note
        data.append(item)
    return json.dumps(data, ensure_ascii=False)


def from_json(text: str) -> list[DayRecord]:
    """Читает дневник. Испорченные строки пропускает — как и историю."""
    try:
        data = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    records: list[DayRecord] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            day = date.fromisoformat(str(item["day"]))
        except (KeyError, TypeError, ValueError):
            continue
        temperature: float | None = None
        try:
            if item.get("temperature") is not None:
                temperature = float(item["temperature"])
        except (TypeError, ValueError):
            temperature = None
        pain: int | None = None
        try:
            if item.get("pain") is not None:
                pain = int(item["pain"])
        except (TypeError, ValueError):
            pain = None
        pill = item.get("pill")
        records.append(
            DayRecord(
                day=day,
                pain=pain,
                mood=str(item.get("mood", "")),
                flow=str(item.get("flow", "")),
                temperature=temperature,
                pill_taken=pill if isinstance(pill, bool) else None,
                note=str(item.get("note", "")),
            ).clamp()
        )
    return sorted(records, key=lambda r: r.day)


def upsert(records: list[DayRecord], record: DayRecord) -> list[DayRecord]:
    """Записывает день: старая запись за тот же день заменяется целиком."""
    others = [r for r in records if r.day != record.day]
    others.append(record.clamp())
    return sorted(others, key=lambda r: r.day)


def for_day(records: list[DayRecord], day: date) -> DayRecord | None:
    for record in records:
        if record.day == day:
            return record
    return None


def in_range(records: list[DayRecord], start: date, end: date) -> list[DayRecord]:
    return [r for r in records if start <= r.day <= end]


def temperature_rise(records: list[DayRecord]) -> date | None:
    """Первый день устойчивого подъёма базальной температуры.

    Это единственный способ узнать по числам, что овуляция уже прошла, — но
    только задним числом. Поэтому функция и называется «был подъём», а не
    «будет овуляция».
    """
    temps = [(r.day, r.temperature) for r in records if r.temperature is not None]
    if len(temps) < MIN_TEMPERATURE_DAYS:
        return None

    temps.sort()
    median = statistics.median(t for _, t in temps)
    threshold = median + TEMPERATURE_RISE

    for index in range(len(temps) - RISE_DAYS + 1):
        window = temps[index:index + RISE_DAYS]
        # Дни должны идти подряд: пропуск в измерениях — не подъём, а разрыв.
        contiguous = all(
            (window[i + 1][0] - window[i][0]).days == 1 for i in range(len(window) - 1)
        )
        if contiguous and all(t > threshold for _, t in window):
            return window[0][0]
    return None


def temperature_summary(records: list[DayRecord]) -> str:
    """Фраза про температуру — вместо графика, которого у нас нет."""
    rise = temperature_rise(records)
    temps = [r.temperature for r in records if r.temperature is not None]
    if not temps:
        return ""
    if rise is None:
        return (
            f"Температура отмечена {len(temps)} раз, но подъёма пока не видно. "
            "Так бывает, если измерять не сразу после сна или не каждый день."
        )
    return (
        f"По температуре овуляция, похоже, была {rise.day} числа — "
        "с этого дня температура держалась выше обычной."
    )


def symptom_summary(records: list[DayRecord], periods: list[Period]) -> str:
    """Что видно по дневнику за всё время — простыми словами."""
    if not records:
        return "Дневник пока пуст. Записывать необязательно — но по записям видны закономерности."

    pains = [r.pain for r in records if r.pain is not None]
    parts: list[str] = []

    if pains:
        average = sum(pains) / len(pains)
        parts.append(f"Боль отмечена {len(pains)} раз, в среднем {average:.1f} из пяти.")
        worst = [r for r in records if r.pain is not None and r.pain >= 4]
        if worst:
            # Смотрим, на какие дни цикла приходятся сильные боли: это то,
            # ради чего дневник вообще ведут.
            days: list[int] = []
            for period in as_periods(periods):
                for record in worst:
                    if record.day >= period.start:
                        days.append((record.day - period.start).days + 1)
            if days:
                common = statistics.median(days)
                parts.append(
                    f"Сильная боль чаще всего на {int(common)}-й день цикла."
                )

    flows = [r.flow for r in records if r.flow]
    if flows:
        parts.append("Выделения: " + ", ".join(sorted(set(flows))) + ".")

    temperature = temperature_summary(records)
    if temperature:
        parts.append(temperature)

    return " ".join(parts)
