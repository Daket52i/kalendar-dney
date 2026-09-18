"""Прогноз: день цикла, фаза, месячные, овуляция, фертильное окно.

Все функции чистые: принимают историю и дату, возвращают значения. Никакого
ввода-вывода — так ядро одинаково работает и на телефоне, и на компьютере,
и его можно проверить тестами без экрана.
"""

from __future__ import annotations

from datetime import date

from .models import CycleStats, Period, Phase, add_days
from .stats import DEFAULT_CYCLE

# Лютеиновая фаза (после овуляции) держится почти постоянной — 12–14 дней,
# в отличие от первой половины цикла, которая и гуляет. Отсюда стандартный
# способ считать овуляцию: длина цикла минус 14.
LUTEAL_DAYS = 14

# Фертильное окно: сперматозоиды живут до пяти дней, яйцеклетка — около суток.
FERTILE_BEFORE_OVULATION = 5
FERTILE_AFTER_OVULATION = 1


def last_period(periods: list[Period]) -> Period | None:
    """Последняя по дате начала менструация."""
    if not periods:
        return None
    return max(periods, key=lambda p: p.start)


def expected_cycle_length(stats: CycleStats) -> float:
    return stats.median_cycle if stats.cycle_lengths else DEFAULT_CYCLE


def day_of_cycle(periods: list[Period], today: date) -> int | None:
    """Какой сегодня день цикла (первый день месячных — первый)."""
    last = last_period(periods)
    if last is None or today < last.start:
        return None
    return (today - last.start).days + 1


def is_period_day(periods: list[Period], today: date) -> bool:
    return any(p.covers(today) for p in periods)


def ovulation_date(periods: list[Period], stats: CycleStats) -> date | None:
    """Ожидаемая овуляция в текущем цикле."""
    last = last_period(periods)
    if last is None:
        return None
    return add_days(last.start, int(round(expected_cycle_length(stats))) - LUTEAL_DAYS)


def fertile_window(periods: list[Period], stats: CycleStats) -> tuple[date, date] | None:
    ov = ovulation_date(periods, stats)
    if ov is None:
        return None
    return (
        add_days(ov, -FERTILE_BEFORE_OVULATION),
        add_days(ov, FERTILE_AFTER_OVULATION),
    )


def is_fertile_day(periods: list[Period], stats: CycleStats, day: date) -> bool:
    window = fertile_window(periods, stats)
    return window is not None and window[0] <= day <= window[1]


def next_period_start(periods: list[Period], stats: CycleStats) -> date | None:
    """Лучшая оценка первого дня следующих месячных."""
    last = last_period(periods)
    if last is None:
        return None
    return add_days(last.start, int(round(expected_cycle_length(stats))))


def next_period_range(periods: list[Period], stats: CycleStats) -> tuple[date, date] | None:
    """Тот же прогноз, но диапазоном — по самому короткому и самому длинному циклу.

    Одна дата врёт всегда; диапазон честнее и на слух понятнее: «ожидаются
    между третьим и пятым октября».
    """
    last = last_period(periods)
    if last is None:
        return None
    if not stats.cycle_lengths:
        day = next_period_start(periods, stats)
        return (day, day)
    return (
        add_days(last.start, stats.min_cycle),
        add_days(last.start, stats.max_cycle),
    )


def delay_days(periods: list[Period], stats: CycleStats, today: date) -> int:
    """Сколько дней задержка. Ноль — задержки нет или прогноза ещё не хватает."""
    if is_period_day(periods, today):
        return 0
    expected = next_period_start(periods, stats)
    if expected is None or today <= expected:
        return 0
    return (today - expected).days


def phase(periods: list[Period], stats: CycleStats, today: date) -> Phase | None:
    """Фаза цикла на дату."""
    if is_period_day(periods, today):
        return Phase.MENSTRUATION

    ov = ovulation_date(periods, stats)
    if ov is None or day_of_cycle(periods, today) is None:
        return None

    if today == ov:
        return Phase.OVULATION
    if today < ov:
        return Phase.FOLLICULAR
    return Phase.LUTEAL


def cycle_number(periods: list[Period]) -> int:
    """Сколько циклов уже отмечено — для экрана истории."""
    return max(0, len(periods) - 1)
