"""Тексты для скринридера.

Это половина смысла приложения: то, что зрячий видит на картинке — кольце,
полосках, сердечке, — здесь должно быть сказано словами и без запинок.
Поэтому все формулировки живут в одном месте и проверяются тестами.
"""

from __future__ import annotations

from datetime import date

from . import predict
from .models import CycleStats, Period, Phase

MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

# Порядок как у date.weekday(): понедельник — нулевой.
WEEKDAYS = (
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
)


def signed(name: str, text: str) -> str:
    """Ставит перед фразой имя того, чей это календарь.

    Одна точка на всё приложение, а не двадцать: имя обязано быть в каждой
    произносимой фразе, а двадцать мест — это двадцать способов его забыть.

    Имя получает только первая строка. У многострочного текста имя относится ко
    всему тексту целиком, и повторять его в каждой строке значило бы превратить
    чтение в считалку.
    """
    if not name or not text:
        return text
    return f"{name}: {text}"


def plural(n: int, one: str, few: str, many: str) -> str:
    """Русское согласование: 1 день, 2 дня, 5 дней."""
    n = abs(int(n)) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def days_phrase(n: int) -> str:
    return f"{n} {plural(n, 'день', 'дня', 'дней')}"


def cycles_phrase(n: int) -> str:
    return f"{n} {plural(n, 'цикл', 'цикла', 'циклов')}"


def day_phrase(day: date, with_year: bool = False) -> str:
    """«14 сентября» — так дата читается голосом естественнее, чем 14.09."""
    text = f"{day.day} {MONTHS_GENITIVE[day.month - 1]}"
    return f"{text} {day.year} года" if with_year else text


def hour_phrase(hour: int) -> str:
    """«в 9 утра», «в 9 вечера» — время суток вслепую читается только так.

    Цифры «21:00» скринридер произносит как придётся, и «21 час 00 минут» на
    слух — это отчёт, а не разговорная речь.
    """
    hour = int(hour) % 24
    if hour == 0:
        return "в 12 ночи"
    if hour == 12:
        return "в 12 дня"
    if hour < 5:
        return f"в {hour} ночи"
    if hour < 12:
        return f"в {hour} утра"
    if hour < 18:
        return f"в {hour - 12} дня"
    return f"в {hour - 12} вечера"


def reminder_line(day: date, hour: int, text: str) -> str:
    """Одно напоминание одной строкой — так его читает скринридер в списке."""
    return f"{day_phrase(day)}, {hour_phrase(hour)}: {text}"


def day_label(day: date) -> str:
    """«пятница, 18 сентября 2026 года» — заголовок выбранного дня.

    День недели здесь не для красоты: листая дневник кнопками, на слух
    трудно удержать, куда ты ушёл, и название дня это чинит.
    """
    return f"{WEEKDAYS[day.weekday()]}, {day_phrase(day, with_year=True)}"


def day_of_cycle_phrase(n: int) -> str:
    """«12-й день цикла».

    Окончание всегда «-й»: скринридер читает «12-й» как «двенадцатый»,
    а попытка согласовать («2-ой», «3-ий») на слух звучит хуже.
    """
    return f"{n}-й день цикла"


def _range_phrase(start: date, end: date) -> str:
    if start == end:
        return day_phrase(start)
    if (start.year, start.month) == (end.year, end.month):
        return f"с {start.day} по {end.day} {MONTHS_GENITIVE[end.month - 1]}"
    return f"с {day_phrase(start)} по {day_phrase(end)}"


def disclaimer(stats: CycleStats) -> str:
    """Честная оговорка. Молчать о ней нельзя, но и надоедать ею — тоже."""
    if not stats.cycle_lengths:
        return "Прогноза пока нет: нужен хотя бы один отмеченный цикл целиком."
    if stats.irregular:
        return (
            f"Цикл нерегулярный: разброс {days_phrase(stats.spread)}. "
            "Прогноз примерный, полагаться на него как на точную дату нельзя."
        )
    if not stats.enough_data:
        return (
            f"Отмечено пока {cycles_phrase(stats.cycles_seen)} — прогноз "
            "предварительный, точнее станет после третьего."
        )
    return ""


def today_summary(periods: list[Period], stats: CycleStats, today: date) -> str:
    """То, что приложение говорит при открытии. Первое и главное."""
    if not periods:
        return (
            "Записей пока нет. Отметь первый день месячных — и я начну считать "
            "цикл, предупреждать о следующих месячных и об овуляции."
        )

    parts: list[str] = []
    number = predict.day_of_cycle(periods, today)
    head = f"Сегодня {day_phrase(today)}"
    if number is not None:
        head += f", {day_of_cycle_phrase(number)}"
    parts.append(head + ".")

    current = predict.phase(periods, stats, today)
    last = predict.last_period(periods)
    if current is Phase.MENSTRUATION:
        gone = (today - last.start).days + 1 if last is not None else 1
        # «1 день» звучит как отчёт, «первый день» — как живая речь
        parts.append("Идут месячные, первый день." if gone == 1
                     else f"Идут месячные, {days_phrase(gone)}.")
    elif current is not None:
        parts.append(f"Фаза — {current.title}.")

    delay = predict.delay_days(periods, stats, today)
    window = predict.next_period_range(periods, stats)
    if delay > 0:
        expected = predict.next_period_start(periods, stats)
        parts.append(f"Месячные ожидались {day_phrase(expected)}, задержка {days_phrase(delay)}.")
    elif window is not None and current is not Phase.MENSTRUATION:
        parts.append(f"Следующие месячные ожидаются {_range_phrase(*window)}.")

    # Про овуляцию говорим всё время, кроме самих месячных: и «ожидается через
    # четыре дня», и «была двенадцатого» одинаково полезны на слух.
    ov = predict.ovulation_date(periods, stats)
    if ov is not None and current is not None and current is not Phase.MENSTRUATION:
        if today == ov:
            parts.append("Сегодня ожидается овуляция.")
        elif today < ov:
            parts.append(
                f"Овуляция ожидается {day_phrase(ov)}, через {days_phrase((ov - today).days)}."
            )
        else:
            parts.append(f"Овуляция была {day_phrase(ov)}.")

    note = disclaimer(stats)
    if note:
        parts.append(note)

    return " ".join(parts)


def describe_month_day(periods: list[Period], stats: CycleStats, day: date) -> str:
    """Один день календаря словами — для листания месяца по строкам."""
    head = day_phrase(day)
    if predict.is_period_day(periods, day):
        return f"{head}: месячные."
    number = predict.day_of_cycle(periods, day)
    if number is None:
        return f"{head}: до первой отметки."
    current = predict.phase(periods, stats, day)
    marks = [day_of_cycle_phrase(number)]
    if current is not None:
        marks.append(current.title)
    # «Ожидается овуляция» отдельно говорить не нужно: в день овуляции фаза
    # уже названа словом «овуляция», а повтор на слух читается как сбой.
    if current is not Phase.OVULATION and predict.is_fertile_day(periods, stats, day):
        marks.append("фертильный день")
    return f"{head}: " + ", ".join(marks) + "."


def cycle_history(periods: list[Period]) -> str:
    """История циклов списком — то, что показывают врачу."""
    ordered = sorted(periods, key=lambda p: p.start)
    if len(ordered) < 2:
        return "История пока короткая: отмечено меньше двух циклов."

    lines: list[str] = []
    for i in range(len(ordered) - 1):
        length = (ordered[i + 1].start - ordered[i].start).days
        length_text = days_phrase(length)
        if ordered[i].length is not None:
            length_text += f", месячные {days_phrase(ordered[i].length)}"
        lines.append(f"{day_phrase(ordered[i].start)} — цикл {length_text}.")
    return "\n".join(lines)


MEDICAL_NOTE = (
    "Приложение не защищает от беременности и не заменяет врача. "
    "Если цикл сбился надолго или появилась боль, которой раньше не было, — "
    "это повод показаться врачу."
)
