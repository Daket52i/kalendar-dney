"""Проверки ядра: расчёт цикла, прогноз и тексты для скринридера."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cycle_core import phrases, predict, stats as stats_mod  # noqa: E402
from cycle_core.models import DayRecord, Period, Phase  # noqa: E402


def p(year: int, month: int, day: int, length: int | None = None) -> Period:
    start = date(year, month, day)
    return Period(start=start, end=start + timedelta(days=length - 1) if length else None)


class StatsTest(unittest.TestCase):
    def test_cycle_lengths_counted_between_starts(self) -> None:
        periods = [p(2026, 1, 1), p(2026, 1, 29), p(2026, 2, 26)]
        self.assertEqual(stats_mod.cycle_lengths(periods), [28, 28])

    def test_empty_history_falls_back_to_defaults(self) -> None:
        s = stats_mod.compute([])
        self.assertEqual(s.median_cycle, stats_mod.DEFAULT_CYCLE)
        self.assertEqual(s.median_period, stats_mod.DEFAULT_PERIOD)
        self.assertFalse(s.enough_data)
        self.assertFalse(s.irregular)

    def test_two_points_are_not_enough_for_a_forecast(self) -> None:
        s = stats_mod.compute([p(2026, 1, 1), p(2026, 1, 29)])
        self.assertFalse(s.enough_data)

    def test_three_even_cycles_are_regular(self) -> None:
        periods = [p(2026, 1, 1), p(2026, 1, 29), p(2026, 2, 26), p(2026, 3, 26)]
        s = stats_mod.compute(periods)
        self.assertEqual(s.median_cycle, 28.0)
        self.assertFalse(s.irregular)
        self.assertTrue(s.enough_data)

    def test_wildly_varying_cycles_are_flagged_irregular(self) -> None:
        periods = [p(2026, 1, 1), p(2026, 1, 21), p(2026, 2, 20), p(2026, 3, 15)]
        s = stats_mod.compute(periods)
        self.assertTrue(s.irregular)
        self.assertGreater(s.spread, stats_mod.IRREGULAR_SPREAD)

    def test_forgotten_period_end_does_not_spoil_the_average(self) -> None:
        # Три обычные отметки и одна забытая («месячные» на 40 дней).
        periods = [
            p(2026, 1, 1, 5), p(2026, 1, 29, 5), p(2026, 2, 26, 40), p(2026, 3, 26, 5),
        ]
        s = stats_mod.compute(periods)
        self.assertEqual(s.median_period, 5.0)


class PredictTest(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [p(2026, 1, 1, 5), p(2026, 1, 29, 5), p(2026, 2, 26, 5)]
        self.stats = stats_mod.compute(self.periods)

    def test_day_of_cycle_starts_at_one(self) -> None:
        self.assertEqual(predict.day_of_cycle(self.periods, date(2026, 2, 26)), 1)
        self.assertEqual(predict.day_of_cycle(self.periods, date(2026, 3, 9)), 12)

    def test_day_of_cycle_is_none_before_the_first_record(self) -> None:
        self.assertIsNone(predict.day_of_cycle(self.periods, date(2025, 12, 31)))

    def test_ovulation_is_fourteen_days_before_the_next_period(self) -> None:
        # Цикл 28 дней, старт 26 февраля → овуляция 12 марта.
        self.assertEqual(predict.ovulation_date(self.periods, self.stats), date(2026, 3, 12))

    def test_fertile_window_wraps_ovulation(self) -> None:
        start, end = predict.fertile_window(self.periods, self.stats)
        self.assertEqual(start, date(2026, 3, 7))
        self.assertEqual(end, date(2026, 3, 13))
        self.assertTrue(predict.is_fertile_day(self.periods, self.stats, date(2026, 3, 12)))
        self.assertFalse(predict.is_fertile_day(self.periods, self.stats, date(2026, 3, 20)))

    def test_phase_changes_across_the_cycle(self) -> None:
        self.assertIs(predict.phase(self.periods, self.stats, date(2026, 2, 27)), Phase.MENSTRUATION)
        self.assertIs(predict.phase(self.periods, self.stats, date(2026, 3, 5)), Phase.FOLLICULAR)
        self.assertIs(predict.phase(self.periods, self.stats, date(2026, 3, 12)), Phase.OVULATION)
        self.assertIs(predict.phase(self.periods, self.stats, date(2026, 3, 20)), Phase.LUTEAL)

    def test_next_period_range_uses_shortest_and_longest_cycle(self) -> None:
        start, end = predict.next_period_range(self.periods, self.stats)
        self.assertEqual(start, date(2026, 3, 26))
        self.assertEqual(end, date(2026, 3, 26))
        self.assertEqual(predict.next_period_start(self.periods, self.stats), date(2026, 3, 26))

    def test_delay_counts_days_after_the_expected_date(self) -> None:
        self.assertEqual(predict.delay_days(self.periods, self.stats, date(2026, 3, 26)), 0)
        self.assertEqual(predict.delay_days(self.periods, self.stats, date(2026, 3, 30)), 4)

    def test_no_history_gives_no_forecast(self) -> None:
        empty = stats_mod.compute([])
        self.assertIsNone(predict.next_period_start([], empty))
        self.assertIsNone(predict.ovulation_date([], empty))
        self.assertIsNone(predict.phase([], empty, date(2026, 5, 1)))

    def test_irregular_cycle_widens_the_range(self) -> None:
        periods = [p(2026, 1, 1), p(2026, 1, 21), p(2026, 2, 20), p(2026, 3, 15)]
        s = stats_mod.compute(periods)
        start, end = predict.next_period_range(periods, s)
        self.assertLess(start, end)
        self.assertEqual((end - start).days, s.spread)

    def test_short_cycle_reports_no_delay_on_the_expected_day(self) -> None:
        # Цикл 20 дней: прогноз на 21 января, проверяем границу.
        periods = [p(2026, 1, 1), p(2026, 1, 21), p(2026, 2, 10)]
        s = stats_mod.compute(periods)
        self.assertEqual(predict.delay_days(periods, s, date(2026, 3, 2)), 0)


class PhrasesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [p(2026, 1, 1, 5), p(2026, 1, 29, 5), p(2026, 2, 26, 5)]
        self.stats = stats_mod.compute(self.periods)

    def test_plural_agreement(self) -> None:
        self.assertEqual(phrases.days_phrase(1), "1 день")
        self.assertEqual(phrases.days_phrase(2), "2 дня")
        self.assertEqual(phrases.days_phrase(5), "5 дней")
        self.assertEqual(phrases.days_phrase(11), "11 дней")
        self.assertEqual(phrases.days_phrase(21), "21 день")
        self.assertEqual(phrases.cycles_phrase(3), "3 цикла")

    def test_date_is_spoken_naturally(self) -> None:
        self.assertEqual(phrases.day_phrase(date(2026, 9, 14)), "14 сентября")

    def test_summary_without_history_invites_a_first_mark(self) -> None:
        text = phrases.today_summary([], stats_mod.compute([]), date(2026, 9, 14))
        self.assertIn("Записей пока нет", text)

    def test_summary_names_the_day_phase_and_next_period(self) -> None:
        text = phrases.today_summary(self.periods, self.stats, date(2026, 3, 9))
        self.assertIn("9 марта", text)
        self.assertIn("12-й день цикла", text)
        self.assertIn("до овуляции", text)
        self.assertIn("26 марта", text)
        self.assertIn("12 марта", text)

    def test_first_day_of_period_is_spoken_naturally(self) -> None:
        text = phrases.today_summary(self.periods, self.stats, date(2026, 2, 26))
        self.assertIn("Идут месячные, первый день", text)

    def test_summary_reports_a_delay(self) -> None:
        text = phrases.today_summary(self.periods, self.stats, date(2026, 3, 30))
        self.assertIn("задержка 4 дня", text)

    def test_summary_warns_about_an_irregular_cycle(self) -> None:
        periods = [p(2026, 1, 1, 5), p(2026, 1, 21, 5), p(2026, 2, 20, 5), p(2026, 3, 15, 5)]
        s = stats_mod.compute(periods)
        text = phrases.today_summary(periods, s, date(2026, 3, 26))
        self.assertIn("Цикл нерегулярный", text)

    def test_summary_marks_a_preliminary_forecast(self) -> None:
        periods = [p(2026, 1, 1, 5), p(2026, 1, 29, 5)]
        s = stats_mod.compute(periods)
        text = phrases.today_summary(periods, s, date(2026, 2, 5))
        self.assertIn("предварительный", text)

    def test_month_day_line_is_complete(self) -> None:
        # Старт цикла 26 февраля, овуляция 12 марта — это 15-й день.
        text = phrases.describe_month_day(self.periods, self.stats, date(2026, 3, 12))
        self.assertIn("12 марта", text)
        self.assertIn("15-й день цикла", text)
        self.assertIn("овуляция", text)
        self.assertNotIn("ожидается овуляция", text)

    def test_fertile_day_is_marked_without_repeating_ovulation(self) -> None:
        text = phrases.describe_month_day(self.periods, self.stats, date(2026, 3, 9))
        self.assertIn("фертильный день", text)

    def test_month_day_before_first_mark_is_honest(self) -> None:
        text = phrases.describe_month_day(self.periods, self.stats, date(2025, 12, 20))
        self.assertIn("до первой отметки", text)

    def test_history_lists_cycles(self) -> None:
        text = phrases.cycle_history(self.periods)
        self.assertIn("28 дней", text)
        self.assertIn("1 января", text)

    def test_medical_note_forbids_using_it_as_contraception(self) -> None:
        self.assertIn("не защищает от беременности", phrases.MEDICAL_NOTE)


class DayRecordTest(unittest.TestCase):
    def test_pain_scale_is_clamped(self) -> None:
        self.assertEqual(DayRecord(day=date(2026, 1, 1), pain=9).clamp().pain, 5)
        self.assertEqual(DayRecord(day=date(2026, 1, 1), pain=0).clamp().pain, 1)

    def test_period_end_before_start_is_swapped(self) -> None:
        period = Period(start=date(2026, 1, 10), end=date(2026, 1, 7))
        self.assertEqual(period.start, date(2026, 1, 7))
        self.assertEqual(period.length, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
