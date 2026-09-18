"""Проверки отметок и хранения истории."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cycle_core import journal  # noqa: E402
from cycle_core.models import Period  # noqa: E402


class StartPeriodTest(unittest.TestCase):
    def test_first_mark_creates_an_open_period(self) -> None:
        periods = journal.start_period([], date(2026, 9, 14))
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0].start, date(2026, 9, 14))
        self.assertIsNone(periods[0].end)

    def test_double_press_does_not_create_a_second_cycle(self) -> None:
        periods = journal.start_period([], date(2026, 9, 14))
        periods = journal.start_period(periods, date(2026, 9, 14))
        self.assertEqual(len(periods), 1)

    def test_new_mark_keeps_history_ordered(self) -> None:
        periods = [Period(start=date(2026, 10, 12), end=date(2026, 10, 16))]
        periods = journal.start_period(periods, date(2026, 9, 14))
        self.assertEqual([p.start for p in periods], [date(2026, 9, 14), date(2026, 10, 12)])

    def test_previous_open_period_is_left_alone(self) -> None:
        # Конец прошлых месячных так и не отметили — придумывать его нельзя.
        periods = journal.start_period([], date(2026, 8, 1))
        periods = journal.start_period(periods, date(2026, 8, 29))
        self.assertEqual(len(periods), 2)
        self.assertIsNone(periods[0].end)


class FinishPeriodTest(unittest.TestCase):
    def test_finish_closes_the_open_period(self) -> None:
        periods = journal.start_period([], date(2026, 9, 14))
        periods = journal.finish_period(periods, date(2026, 9, 18))
        self.assertEqual(periods[0].length, 5)

    def test_finish_without_open_period_changes_nothing(self) -> None:
        periods = [Period(start=date(2026, 9, 14), end=date(2026, 9, 18))]
        self.assertEqual(journal.finish_period(periods, date(2026, 9, 20)), periods)

    def test_end_before_start_swaps_instead_of_losing_days(self) -> None:
        periods = journal.start_period([], date(2026, 9, 14))
        periods = journal.finish_period(periods, date(2026, 9, 12))
        self.assertEqual(periods[0].start, date(2026, 9, 12))
        self.assertEqual(periods[0].length, 3)


class StorageTest(unittest.TestCase):
    def test_round_trip_keeps_the_history(self) -> None:
        original = [
            Period(start=date(2026, 9, 14), end=date(2026, 9, 18)),
            Period(start=date(2026, 10, 12)),
        ]
        restored = journal.from_json(journal.to_json(original))
        self.assertEqual(journal.to_json(original), journal.to_json(restored))

    def test_broken_json_does_not_lose_everything(self) -> None:
        text = '[{"start": "2026-09-14", "end": "2026-09-18"}, {"start": "не дата"}, {"нет": "поля"}]'
        periods = journal.from_json(text)
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0].start, date(2026, 9, 14))

    def test_garbage_instead_of_json_gives_empty_history(self) -> None:
        self.assertEqual(journal.from_json("не json вовсе"), [])
        self.assertEqual(journal.from_json(""), [])

    def test_open_period_found_for_a_hint(self) -> None:
        periods = [
            Period(start=date(2026, 9, 14), end=date(2026, 9, 18)),
            Period(start=date(2026, 10, 12)),
        ]
        self.assertEqual(journal.open_period(periods).start, date(2026, 10, 12))
        self.assertIsNone(journal.open_period(periods[:1]))

    def test_remove_and_edit(self) -> None:
        periods = [Period(start=date(2026, 9, 14))]
        periods = journal.set_period(periods, date(2026, 9, 14), date(2026, 9, 17))
        self.assertEqual(periods[0].length, 4)
        self.assertEqual(journal.remove_period(periods, date(2026, 9, 14)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
