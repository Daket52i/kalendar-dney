"""Напоминания: что и когда сказать.

Ядро только считает, что и в какой день сказать, — а показывает и будит
система (WorkManager/AlarmManager на Android, таймер на Windows). Так одна и
та же логика напоминаний проверяется тестами, а не «на глазок» на телефоне.

Спорная вещь: напоминания о таблетке. Приложение не лечит и не назначает — оно
напоминает о том, что назначил врач, ровно теми словами, что записала
пользовательница.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from . import predict
from .models import CycleStats, DayRecord, Period
from .phrases import day_phrase, days_phrase, _range_phrase

# Сколько циклов вперёд имеет смысл считать. Дальше прогноз всё равно
# пересчитается после следующей отметки, и городить его заранее бессмысленно.
HORIZON_DAYS = 90

# Во сколько говорить про месячные, если это не таблетка и не задано иначе:
# утро, потому что отметку ставят утром.
DEFAULT_HOUR = 9


@dataclass
class ReminderSettings:
    """Настройки напоминаний. Всё включённое по умолчанию — можно выключить."""

    days_before: int = 2
    on_expected_day: bool = True
    delay_after: int = 3
    fertile_notice: bool = True
    pill_enabled: bool = False
    pill_hour: int = 21
    quiet_from: int = 22
    quiet_to: int = 8

    def quiet(self, hour: int) -> bool:
        """Тихие часы. Окно может переходить через полночь — 22 → 8."""
        if self.quiet_from == self.quiet_to:
            return False
        if self.quiet_from < self.quiet_to:
            return self.quiet_from <= hour < self.quiet_to
        return hour >= self.quiet_from or hour < self.quiet_to


@dataclass
class Reminder:
    day: date
    hour: int
    kind: str
    text: str


def _projected_starts(
    periods: list[Period], stats: CycleStats, until: date
) -> list[date]:
    """Будущие начала месячных: одно точное и дальше по среднему циклу.

    Дальние загадывать нечестно: после каждой отметки прогноз пересчитывается,
    поэтому за горизонтом держим только то, что успеет сбыться или отмениться.
    """
    first = predict.next_period_start(periods, stats)
    if first is None:
        return []
    starts = [first]
    length = max(int(round(stats.median_cycle)), 1)
    while starts[-1] + timedelta(days=length) <= until:
        starts.append(starts[-1] + timedelta(days=length))
    return starts


def events(
    periods: list[Period],
    stats: CycleStats,
    records: list[DayRecord],
    today: date,
    settings: ReminderSettings,
    horizon_days: int = HORIZON_DAYS,
) -> list[Reminder]:
    """Все напоминания на ближайшие `horizon_days` дней, по порядку."""
    until = today + timedelta(days=horizon_days)
    items: list[Reminder] = []

    def add(day: date, hour: int, kind: str, text: str) -> None:
        if day < today or day > until:
            return
        if settings.quiet(hour):
            return
        items.append(Reminder(day=day, hour=hour, kind=kind, text=text))

    starts = _projected_starts(periods, stats, until)

    # Предупреждаем только о ближайшем начале: остальные — тот же прогноз,
    # повторённый несколько раз, и на слух это превращается в шум.
    if starts:
        first = starts[0]
        if settings.days_before > 0:
            ahead = first - timedelta(days=settings.days_before)
            if ahead >= today:
                add(
                    ahead,
                    DEFAULT_HOUR,
                    "period_soon",
                    f"Через {days_phrase(settings.days_before)} ожидаются месячные — "
                    f"{day_phrase(first)}.",
                )
        if settings.on_expected_day:
            add(
                first,
                DEFAULT_HOUR,
                "period_today",
                f"Сегодня ожидаются месячные, {day_phrase(first)}. "
                "Отметь первый день, если начались.",
            )
        if settings.delay_after > 0:
            # Напоминание о задержке отменяется само: как только месячные
            # отмечены, следующее начало уезжает вперёд и дата меняется.
            add(
                first + timedelta(days=settings.delay_after),
                DEFAULT_HOUR,
                "period_late",
                f"Месячные ожидались {day_phrase(first)}, "
                f"задержка {days_phrase(settings.delay_after)}. "
                "Если так и не начались — это повод показаться врачу.",
            )

    if settings.fertile_notice:
        window = predict.fertile_window(periods, stats)
        if window is not None:
            add(
                window[0],
                DEFAULT_HOUR,
                "fertile",
                f"Начинаются фертильные дни: {_range_phrase(*window)}. "
                "Это прогноз, а не защита от беременности.",
            )

    if settings.pill_enabled:
        taken = {r.day for r in records if r.pill_taken}
        day = today
        while day <= until:
            # Если таблетка уже отмечена, напоминать не о чем: приложение
            # не должно спорить с тем, что ему только что сказали.
            if day not in taken:
                add(day, settings.pill_hour, "pill", "Напоминание: таблетка.")
            day += timedelta(days=1)

    items.sort(key=lambda r: (r.day, r.hour))
    return items


def next_event(reminders: list[Reminder], today: date) -> Reminder | None:
    """Ближайшее напоминание — чтобы показать его в главном экране."""
    for reminder in reminders:
        if reminder.day >= today:
            return reminder
    return None
