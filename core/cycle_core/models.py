"""Модели календаря цикла.

Ядро ничего не знает про интерфейс: оно принимает даты и отдаёт выводы.
Так одна и та же логика работает и на Android, и на Windows.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import Enum


class Phase(str, Enum):
    """Фаза цикла. Строковые значения — чтобы сохранялись в базу как есть."""

    MENSTRUATION = "menstruation"
    FOLLICULAR = "follicular"
    OVULATION = "ovulation"
    LUTEAL = "luteal"

    @property
    def title(self) -> str:
        return {
            Phase.MENSTRUATION: "месячные",
            Phase.FOLLICULAR: "до овуляции",
            Phase.OVULATION: "овуляция",
            Phase.LUTEAL: "после овуляции",
        }[self]


@dataclass
class Period:
    """Одна менструация.

    `start` — первый день выделений, `end` — последний отмеченный день
    (None, пока месячные идут или пока конец не отмечен).
    """

    start: date
    end: date | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            self.start, self.end = self.end, self.start

    @property
    def length(self) -> int | None:
        """Сколько дней идут месячные. None, если конец ещё не отмечен."""
        if self.end is None:
            return None
        return (self.end - self.start).days + 1

    def covers(self, day: date) -> bool:
        """Попадает ли день в эту менструацию."""
        if day < self.start:
            return False
        if self.end is None:
            return day == self.start
        return day <= self.end

    def with_end(self, end: date | None) -> Period:
        return replace(self, end=end)


@dataclass
class DayRecord:
    """Дневниковая запись за день: самочувствие и заметки.

    Всё необязательное — заполнять заставлять нельзя.
    """

    day: date
    pain: int | None = None          # боль: 1..5
    mood: str = ""                   # настроение: свободное слово из списка
    flow: str = ""                   # выделения: "нет", "слабые", "обычные", "сильные"
    temperature: float | None = None  # базальная температура
    pill_taken: bool | None = None    # выпила таблетку — None, если учёт не ведётся
    note: str = ""

    def clamp(self) -> DayRecord:
        """Приводит боль к шкале 1..5: интерфейс мог прислать что угодно."""
        if self.pain is None:
            return self
        return replace(self, pain=min(5, max(1, int(self.pain))))


@dataclass
class CycleStats:
    """Сводка по истории: длины циклов, разброс, регулярность."""

    cycle_lengths: tuple[int, ...]
    period_lengths: tuple[int, ...]
    median_cycle: float
    median_period: float
    min_cycle: int
    max_cycle: int
    spread: int
    irregular: bool
    enough_data: bool

    @property
    def cycles_seen(self) -> int:
        return len(self.cycle_lengths)


def as_periods(items: list[Period]) -> list[Period]:
    """Сортирует историю по дате начала — вся остальная логика на это опирается."""
    return sorted(items, key=lambda p: p.start)


def days_between(a: date, b: date) -> int:
    return (b - a).days


def add_days(day: date, count: int) -> date:
    return day + timedelta(days=count)
