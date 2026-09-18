"""Проверки дневника самочувствия."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cycle_core import diary  # noqa: E402
from cycle_core.models import DayRecord, Period  # noqa: E402


def p(year: int, month: int, day: int, length: int | None = None) -> Period:
    start = date(year, month, day)
    return Period(start=start, end=start + timedelta(days=length - 1) if length else None)


class DiaryStorageTest(unittest.TestCase):
    def test_round_trip_keeps_every_field(self) -> None:
        original = [
            DayRecord(
                day=date(2026, 3, 9),
                pain=3,
                mood="спокойное",
                flow="скудные",
                temperature=36.4,
                pill_taken=True,
                note="болела голова",
            )
        ]
        restored = diary.from_json(diary.to_json(original))
        self.assertEqual(restored, original)

    def test_empty_fields_are_not_written(self) -> None:
        # Дневник не должен пухнуть от пустых полей: отметка только о боли
        # занимает одну короткую строку.
        text = diary.to_json([DayRecord(day=date(2026, 3, 9), pain=2)])
        self.assertEqual(text, '[{"day": "2026-03-09", "pain": 2}]')

    def test_broken_lines_are_skipped_not_fatal(self) -> None:
        text = (
            '[{"day": "2026-03-09", "pain": 2},'
            ' {"нет даты": 1},'
            ' {"day": "не дата"},'
            ' "просто строка"]'
        )
        records = diary.from_json(text)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].day, date(2026, 3, 9))

    def test_a_bad_number_keeps_the_day_but_drops_the_number(self) -> None:
        # День записан верно, а температура — мусор («36,7» с запятой).
        # Терять из-за этого всю отметку нельзя.
        records = diary.from_json('[{"day": "2026-03-10", "temperature": "36,7"}]')
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].temperature)

    def test_garbage_input_gives_empty_diary(self) -> None:
        self.assertEqual(diary.from_json(""), [])
        self.assertEqual(diary.from_json("не json"), [])
        self.assertEqual(diary.from_json('{"a": 1}'), [])

    def test_upsert_replaces_the_same_day(self) -> None:
        day = date(2026, 3, 9)
        records = [DayRecord(day=day, pain=1), DayRecord(day=date(2026, 3, 10), pain=2)]
        records = diary.upsert(records, DayRecord(day=day, pain=4))
        self.assertEqual(len(records), 2)
        self.assertEqual(diary.for_day(records, day).pain, 4)

    def test_values_are_clamped_on_read(self) -> None:
        records = diary.from_json('[{"day": "2026-03-09", "pain": 99}]')
        self.assertEqual(records[0].pain, 5)

    def test_range_selection(self) -> None:
        records = [
            DayRecord(day=date(2026, 3, 1)),
            DayRecord(day=date(2026, 3, 9)),
            DayRecord(day=date(2026, 3, 20)),
        ]
        found = diary.in_range(records, date(2026, 3, 5), date(2026, 3, 10))
        self.assertEqual([r.day for r in found], [date(2026, 3, 9)])


class TemperatureTest(unittest.TestCase):
    def test_sustained_rise_is_found(self) -> None:
        start = date(2026, 3, 1)
        temps = [36.4, 36.5, 36.4, 36.5, 36.4, 36.8, 36.9, 37.0]
        records = [
            DayRecord(day=start + timedelta(days=i), temperature=t)
            for i, t in enumerate(temps)
        ]
        self.assertEqual(diary.temperature_rise(records), date(2026, 3, 6))

    def test_single_spike_is_not_a_rise(self) -> None:
        start = date(2026, 3, 1)
        temps = [36.4, 36.5, 37.1, 36.4, 36.5, 36.4]
        records = [
            DayRecord(day=start + timedelta(days=i), temperature=t)
            for i, t in enumerate(temps)
        ]
        self.assertIsNone(diary.temperature_rise(records))

    def test_gap_inside_the_rise_breaks_it(self) -> None:
        # Три высоких значения, но одно измерение пропущено — подъёмом это
        # называть нельзя: неизвестно, что было в пропущенный день.
        records = [
            DayRecord(day=date(2026, 3, 1), temperature=36.4),
            DayRecord(day=date(2026, 3, 2), temperature=36.4),
            DayRecord(day=date(2026, 3, 3), temperature=36.4),
            DayRecord(day=date(2026, 3, 7), temperature=36.9),
            DayRecord(day=date(2026, 3, 8), temperature=36.9),
            DayRecord(day=date(2026, 3, 10), temperature=36.9),
        ]
        self.assertIsNone(diary.temperature_rise(records))

    def test_too_few_measurements_give_no_conclusion(self) -> None:
        records = [DayRecord(day=date(2026, 3, 1), temperature=36.4)]
        self.assertIsNone(diary.temperature_rise(records))
        self.assertEqual(diary.temperature_summary(records).count("подъёма"), 1)


class SummaryTest(unittest.TestCase):
    def test_empty_diary_is_not_an_error(self) -> None:
        text = diary.symptom_summary([], [])
        self.assertIn("Дневник пока пуст", text)

    def test_summary_names_average_pain_and_the_usual_day(self) -> None:
        periods = [p(2026, 3, 1, 5), p(2026, 3, 29, 5)]
        records = [
            DayRecord(day=date(2026, 3, 1), pain=5),
            DayRecord(day=date(2026, 3, 2), pain=5),
            DayRecord(day=date(2026, 3, 10), pain=1),
            DayRecord(day=date(2026, 3, 29), pain=5),
            DayRecord(day=date(2026, 3, 30), pain=5),
            DayRecord(day=date(2026, 4, 5), pain=2),
        ]
        text = diary.symptom_summary(records, periods)
        self.assertIn("Боль отмечена 6 раз", text)
        self.assertIn("3.8 из пяти", text)
        self.assertIn("Сильная боль чаще всего", text)

    def test_flow_is_listed_once_per_kind(self) -> None:
        records = [
            DayRecord(day=date(2026, 3, 1), flow="обильные"),
            DayRecord(day=date(2026, 3, 2), flow="обильные"),
            DayRecord(day=date(2026, 3, 3), flow="скудные"),
        ]
        text = diary.symptom_summary(records, [])
        self.assertIn("Выделения: обильные, скудные.", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
