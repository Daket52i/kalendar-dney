"""Сводка по истории циклов: средние длины, разброс, регулярность."""

from __future__ import annotations

import statistics

from .models import CycleStats, Period

# Сколько последних циклов берём в расчёт. Ранние данные хуже: цикл меняется
# после родов, гормональных перемен, смены образа жизни.
RECENT_WINDOW = 6

# Порог регулярности. Цикл считается нерегулярным, если разброс между самым
# коротким и самым длинным (по последним циклам) больше восьми дней. Восемь —
# граница из медицинских памяток: в пределах недели колебания считаются
# нормальными, дальше прогноз по средней уже врёт.
IRREGULAR_SPREAD = 8

# Прогноз показываем как «примерный», пока не набралось три цикла. По двум
# точкам среднее считать можно, но это статистика ни о чём.
MIN_CYCLES_FOR_FORECAST = 3

# Значения, когда истории нет вовсе: средний цикл по популяции и обычная
# длительность месячных. Нужны, чтобы экран «Сегодня» не был пустым.
DEFAULT_CYCLE = 28.0
DEFAULT_PERIOD = 5.0


def cycle_lengths(periods: list[Period]) -> list[int]:
    """Длины циклов: от первого дня месячных до первого дня следующих."""
    ordered = sorted(periods, key=lambda p: p.start)
    return [
        (ordered[i + 1].start - ordered[i].start).days
        for i in range(len(ordered) - 1)
    ]


def period_lengths(periods: list[Period]) -> list[int]:
    """Длительности месячных — только там, где отмечен последний день."""
    return [p.length for p in periods if p.length is not None]


def compute(periods: list[Period]) -> CycleStats:
    """Считает сводку. На пустой истории отдаёт значения по умолчанию."""
    cycles = [c for c in cycle_lengths(periods) if c > 0]
    recent = cycles[-RECENT_WINDOW:]

    mens = period_lengths(periods)[-RECENT_WINDOW:]
    # Длительность месячных считаем только по «нормальным» записям: одна
    # случайно забытая отметка конца даёт двадцать дней и ломает среднее.
    mens = [m for m in mens if 1 <= m <= 15]

    if recent:
        median_cycle = float(statistics.median(recent))
        min_cycle, max_cycle = min(recent), max(recent)
        spread = max_cycle - min_cycle
        irregular = spread > IRREGULAR_SPREAD
    else:
        median_cycle = DEFAULT_CYCLE
        min_cycle = max_cycle = int(DEFAULT_CYCLE)
        spread = 0
        irregular = False

    median_period = float(statistics.median(mens)) if mens else DEFAULT_PERIOD

    return CycleStats(
        cycle_lengths=tuple(cycles),
        period_lengths=tuple(period_lengths(periods)),
        median_cycle=median_cycle,
        median_period=median_period,
        min_cycle=min_cycle,
        max_cycle=max_cycle,
        spread=spread,
        irregular=irregular,
        enough_data=len(cycles) >= MIN_CYCLES_FOR_FORECAST,
    )
