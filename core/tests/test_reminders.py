"""Проверки напоминаний: что, когда и чего говорить не надо."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cycle_core import stats as stats_mod  # noqa: E402
from cycle_core.models import DayRecord, Period  # noqa: E402
from cycle_core.reminders import (  # noqa: E402
    ReminderSettings,
    events,
    next_event,
)


def p(year: int, month: int, day: int, length: int | None = None) -> Period:
    start = date(year, month, day)
    return Period(start=start, end=start + timedelta(days=length - 1) if length else None)


def on(reminders, kind: str) -> list:
    return [r for r in reminders if r.kind == kind]


class EventsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [p(2026, 1, 1, 5), p(2026, 1, 29, 5), p(2026, 2, 26, 5)]
        self.stats = stats_mod.compute(self.periods)
        self.settings = ReminderSettings()

    def test_warning_two_days_before_the_expected_day(self) -> None:
        items = events(self.periods, self.stats, [], date(2026, 3, 20), self.settings)
        soon = on(items, "period_soon")
        self.assertEqual(len(soon), 1)
        self.assertEqual(soon[0].day, date(2026, 3, 24))
        self.assertIn("Через 2 дня", soon[0].text)
        self.assertIn("26 марта", soon[0].text)

    def test_reminder_on_the_expected_day(self) -> None:
        items = events(self.periods, self.stats, [], date(2026, 3, 26), self.settings)
        today_items = on(items, "period_today")
        self.assertEqual(len(today_items), 1)
        self.assertIn("26 марта", today_items[0].text)

    def test_warning_is_silent_when_the_day_is_already_today(self) -> None:
        # Наступило — предупреждать «через 2 дня» уже поздно и неверно.
        items = events(self.periods, self.stats, [], date(2026, 3, 25), self.settings)
        self.assertEqual(on(items, "period_soon"), [])

    def test_delay_reminder_after_the_expected_day(self) -> None:
        items = events(self.periods, self.stats, [], date(2026, 3, 26), self.settings)
        late = on(items, "period_late")
        self.assertEqual(len(late), 1)
        self.assertEqual(late[0].day, date(2026, 3, 29))
        self.assertIn("задержка 3 дня", late[0].text)

    def test_marking_the_period_moves_the_forecast_and_the_reminders(self) -> None:
        marked = self.periods + [p(2026, 3, 26, 5)]
        s = stats_mod.compute(marked)
        items = events(marked, s, [], date(2026, 3, 27), self.settings)
        # Ни одного напоминания про старое ожидание: отметка сдвинула прогноз,
        # и следующий цикл считается уже от 26 марта.
        self.assertNotIn("26 марта", " ".join(r.text for r in items))
        self.assertIn(date(2026, 4, 23), [r.day for r in on(items, "period_today")])

    def test_fertile_window_is_announced_once(self) -> None:
        items = events(self.periods, self.stats, [], date(2026, 3, 1), self.settings)
        fertile = on(items, "fertile")
        self.assertEqual(len(fertile), 1)
        self.assertEqual(fertile[0].day, date(2026, 3, 7))
        self.assertIn("с 7 по 13 марта", fertile[0].text)
        self.assertIn("не защита от беременности", fertile[0].text)

    def test_past_events_are_not_repeated(self) -> None:
        items = events(self.periods, self.stats, [], date(2026, 3, 20), self.settings)
        self.assertTrue(all(r.day >= date(2026, 3, 20) for r in items))

    def test_empty_history_gives_no_forecast_reminders(self) -> None:
        empty = stats_mod.compute([])
        items = events([], empty, [], date(2026, 3, 20), ReminderSettings())
        self.assertEqual(items, [])

    def test_settings_can_switch_everything_off(self) -> None:
        quiet = ReminderSettings(
            days_before=0, on_expected_day=False, delay_after=0, fertile_notice=False
        )
        items = events(self.periods, self.stats, [], date(2026, 3, 20), quiet)
        self.assertEqual(items, [])

    def test_next_event_is_the_nearest(self) -> None:
        items = events(self.periods, self.stats, [], date(2026, 3, 1), self.settings)
        nearest = next_event(items, date(2026, 3, 1))
        self.assertIsNotNone(nearest)
        self.assertEqual(nearest.day, date(2026, 3, 7))
        self.assertIsNone(next_event([], date(2026, 3, 1)))


class PillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [p(2026, 1, 1, 5), p(2026, 1, 29, 5), p(2026, 2, 26, 5)]
        self.stats = stats_mod.compute(self.periods)
        self.settings = ReminderSettings(pill_enabled=True)

    def test_one_reminder_per_day(self) -> None:
        items = events(
            self.periods, self.stats, [], date(2026, 3, 20), self.settings, horizon_days=3
        )
        pills = on(items, "pill")
        self.assertEqual(len(pills), 4)
        self.assertEqual(pills[0].hour, 21)
        self.assertEqual(pills[0].text, "Напоминание: таблетка.")

    def test_a_marked_pill_is_not_reminded_again(self) -> None:
        records = [DayRecord(day=date(2026, 3, 20), pill_taken=True)]
        items = events(
            self.periods, self.stats, records, date(2026, 3, 20), self.settings, horizon_days=3
        )
        self.assertEqual(len(on(items, "pill")), 3)

    def test_an_unmarked_day_still_gets_the_reminder(self) -> None:
        records = [DayRecord(day=date(2026, 3, 20), pill_taken=False)]
        items = events(
            self.periods, self.stats, records, date(2026, 3, 20), self.settings, horizon_days=3
        )
        self.assertEqual(len(on(items, "pill")), 4)

    def test_pill_can_be_switched_off(self) -> None:
        settings = ReminderSettings(pill_enabled=False)
        items = events(self.periods, self.stats, [], date(2026, 3, 20), settings)
        self.assertEqual(on(items, "pill"), [])


class QuietHoursTest(unittest.TestCase):
    def test_window_through_midnight(self) -> None:
        settings = ReminderSettings(quiet_from=22, quiet_to=8)
        self.assertTrue(settings.quiet(22))
        self.assertTrue(settings.quiet(23))
        self.assertTrue(settings.quiet(7))
        self.assertFalse(settings.quiet(8))
        self.assertFalse(settings.quiet(21))

    def test_daytime_window(self) -> None:
        settings = ReminderSettings(quiet_from=13, quiet_to=15)
        self.assertTrue(settings.quiet(14))
        self.assertFalse(settings.quiet(15))

    def test_equal_bounds_mean_no_quiet_hours(self) -> None:
        settings = ReminderSettings(quiet_from=10, quiet_to=10)
        self.assertFalse(settings.quiet(10))

    def test_pill_reminder_respects_quiet_hours(self) -> None:
        periods = [p(2026, 1, 1, 5), p(2026, 1, 29, 5), p(2026, 2, 26, 5)]
        s = stats_mod.compute(periods)
        settings = ReminderSettings(
            pill_enabled=True, pill_hour=23, quiet_from=22, quiet_to=8
        )
        items = events(periods, s, [], date(2026, 3, 20), settings, horizon_days=0)
        self.assertEqual(on(items, "pill"), [])
        # Тот же вечер, но вне тихих часов — напоминание на месте.
        settings.pill_hour = 20
        items = events(periods, s, [], date(2026, 3, 20), settings, horizon_days=0)
        self.assertEqual(len(on(items, "pill")), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
