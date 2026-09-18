"""Проверки строкового моста: то, чем пользуются обе оболочки."""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cycle_core import engine, journal  # noqa: E402
from cycle_core.models import Period  # noqa: E402
from cycle_core.reminders import ReminderSettings  # noqa: E402

TODAY = "2026-03-20"


def _periods_json(*days: tuple[int, int, int]) -> str:
    periods = [Period(start=date(y, m, d)) for y, m, d in days]
    return journal.to_json(periods)


class SummaryBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = _periods_json((2026, 1, 1), (2026, 1, 29), (2026, 2, 26))

    def test_summary_is_a_sentence(self) -> None:
        text = engine.summary(self.periods, TODAY)
        self.assertIn("20 марта", text)
        self.assertIn("цикла", text)

    def test_broken_json_does_not_crash(self) -> None:
        self.assertIn("Записей пока нет", engine.summary("не json", TODAY))

    def test_broken_date_falls_back_to_today(self) -> None:
        self.assertEqual(engine.summary(self.periods, "вчера"), engine.summary(self.periods, ""))

    def test_month_returns_one_line_per_day(self) -> None:
        lines = json.loads(engine.month(self.periods, TODAY, 2026, 3))
        self.assertEqual(len(lines), 31)
        self.assertIn("1 марта", lines[0])
        self.assertIn("31 марта", lines[-1])

    def test_history_lists_cycles(self) -> None:
        self.assertIn("28 дней", engine.history(self.periods))

    def test_mark_start_appends_and_is_idempotent(self) -> None:
        once = engine.mark_start(self.periods, TODAY)
        twice = engine.mark_start(once, TODAY)
        self.assertEqual(json.loads(once), json.loads(twice))
        self.assertEqual(len(json.loads(once)), 4)

    def test_mark_end_closes_the_open_record(self) -> None:
        started = engine.mark_start(self.periods, "2026-03-26")
        closed = engine.mark_end(started, "2026-03-30")
        last = json.loads(closed)[-1]
        self.assertEqual(last["start"], "2026-03-26")
        self.assertEqual(last["end"], "2026-03-30")

    def test_state_describes_the_buttons(self) -> None:
        closed = journal.to_json(
            [
                Period(start=date(2026, 1, 1), end=date(2026, 1, 5)),
                Period(start=date(2026, 1, 29), end=date(2026, 2, 2)),
            ]
        )
        state = json.loads(engine.state(closed))
        self.assertEqual(
            state, {"open": False, "has_history": True, "open_day": 0, "cycles": 1}
        )

    def test_state_counts_the_day_of_open_period(self) -> None:
        # Незакрытая отметка, начавшаяся три дня назад: кнопка должна сказать,
        # какой это день, а не просто «месячные идут».
        started = date.today() - timedelta(days=2)
        state = json.loads(engine.state(journal.to_json([Period(start=started)])))
        self.assertTrue(state["open"])
        self.assertEqual(state["open_day"], 3)

    def test_medical_note_never_promises_protection(self) -> None:
        self.assertIn("не защищает от беременности", engine.medical_note())


class DiaryBridgeTest(unittest.TestCase):
    def test_save_then_read_back(self) -> None:
        saved = engine.diary_save(
            "[]", TODAY, pain=4, mood="усталое", temperature=36.6, pill=1, note="болит голова"
        )
        item = json.loads(engine.diary_day(saved, TODAY))
        self.assertEqual(item["pain"], 4)
        self.assertEqual(item["mood"], "усталое")
        self.assertEqual(item["temperature"], 36.6)
        self.assertTrue(item["pill"])
        self.assertEqual(item["note"], "болит голова")

    def test_empty_day_returns_empty_object(self) -> None:
        self.assertEqual(engine.diary_day("[]", TODAY), "{}")

    def test_zero_means_not_marked(self) -> None:
        saved = engine.diary_save("[]", TODAY)
        item = json.loads(engine.diary_day(saved, TODAY))
        self.assertNotIn("pain", item)
        self.assertNotIn("temperature", item)
        self.assertNotIn("pill", item)

    def test_pill_is_remembered_as_not_taken(self) -> None:
        saved = engine.diary_save("[]", TODAY, pill=0)
        self.assertFalse(json.loads(engine.diary_day(saved, TODAY))["pill"])

    def test_saving_twice_the_same_day_replaces_it(self) -> None:
        saved = engine.diary_save("[]", TODAY, pain=2)
        saved = engine.diary_save(saved, TODAY, pain=5)
        records = json.loads(saved)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["pain"], 5)

    def test_summary_and_history_are_spoken(self) -> None:
        records = engine.diary_save("[]", "2026-03-02", pain=5, flow="обильные")
        summary = engine.diary_summary(records, _periods_json((2026, 2, 26)))
        self.assertIn("Боль отмечена 1 раз", summary)
        history = engine.diary_history(records, _periods_json((2026, 2, 26)))
        self.assertIn("2 марта", history)
        self.assertIn("5-й день цикла", history)
        self.assertIn("обильные", history)

    def test_empty_diary_says_so(self) -> None:
        self.assertEqual(engine.diary_history("[]", "[]"), "Дневник пока пуст.")


class SettingsBridgeTest(unittest.TestCase):
    def test_defaults_survive_empty_input(self) -> None:
        self.assertEqual(engine.settings_from_json("{}"), ReminderSettings())
        self.assertEqual(engine.settings_from_json("мусор"), ReminderSettings())

    def test_unknown_fields_are_ignored(self) -> None:
        settings = engine.settings_from_json('{"pill_enabled": true, "чужое": 5}')
        self.assertTrue(settings.pill_enabled)

    def test_broken_values_fall_back_to_defaults(self) -> None:
        settings = engine.settings_from_json('{"pill_hour": "вечером"}')
        self.assertEqual(settings.pill_hour, ReminderSettings().pill_hour)

    def test_round_trip(self) -> None:
        original = ReminderSettings(pill_enabled=True, pill_hour=8, quiet_from=23, quiet_to=7)
        self.assertEqual(
            engine.settings_from_json(engine.settings_to_json(original)), original
        )


class DayLabelBridgeTest(unittest.TestCase):
    def test_label_names_the_weekday(self) -> None:
        # 18 сентября 2026 — пятница.
        self.assertEqual(engine.day_label("2026-09-18"), "пятница, 18 сентября 2026 года")

    def test_a_broken_date_falls_back_to_today(self) -> None:
        self.assertEqual(engine.day_label("не дата"), engine.day_label(date.today().isoformat()))


class DiaryHistoryBridgeTest(unittest.TestCase):
    def test_lines_and_text_agree(self) -> None:
        records = engine.diary_save("[]", "2026-03-19", pain=2, note="болела голова")
        records = engine.diary_save(records, "2026-03-20", mood="спокойное")
        lines = json.loads(engine.diary_history_json(records, "[]"))
        self.assertEqual(len(lines), 2)
        self.assertEqual("\n".join(lines), engine.diary_history(records, "[]"))

    def test_empty_diary_says_so_in_one_line(self) -> None:
        self.assertEqual(json.loads(engine.diary_history_json("[]", "[]")),
                         ["Дневник пока пуст."])


class ReminderLinesBridgeTest(unittest.TestCase):
    def test_lines_are_spoken_in_words(self) -> None:
        periods = _periods_json((2026, 1, 1), (2026, 1, 29), (2026, 2, 26))
        settings = engine.settings_to_json(ReminderSettings(pill_enabled=True))
        lines = json.loads(engine.reminders_lines(periods, "[]", TODAY, settings, limit=10))
        # «в 9 утра», а не «09:00»: вслепую время читается только словами.
        self.assertTrue(all("," in line and ":" in line for line in lines))
        self.assertTrue(any("утра" in line for line in lines))
        self.assertTrue(any("вечера" in line for line in lines))

    def test_limit_holds(self) -> None:
        periods = _periods_json((2026, 1, 1), (2026, 1, 29), (2026, 2, 26))
        settings = engine.settings_to_json(ReminderSettings(pill_enabled=True))
        lines = json.loads(engine.reminders_lines(periods, "[]", TODAY, settings, limit=1))
        self.assertEqual(len(lines), 1)

    def test_no_reminders_is_an_empty_list(self) -> None:
        periods = _periods_json((2026, 1, 1), (2026, 1, 29), (2026, 2, 26))
        settings = engine.settings_to_json(
            ReminderSettings(days_before=0, on_expected_day=False, delay_after=0,
                             fertile_notice=False)
        )
        self.assertEqual(json.loads(engine.reminders_lines(periods, "[]", TODAY, settings)), [])


class RemindersBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = _periods_json((2026, 1, 1), (2026, 1, 29), (2026, 2, 26))

    def test_reminders_have_keys_for_deduplication(self) -> None:
        items = json.loads(engine.reminders_json(self.periods, "[]", TODAY))
        self.assertTrue(items)
        keys = [item["key"] for item in items]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(item["text"] for item in items))

    def test_reminders_can_be_switched_off(self) -> None:
        settings = engine.settings_to_json(
            ReminderSettings(days_before=0, on_expected_day=False, delay_after=0,
                             fertile_notice=False)
        )
        items = json.loads(engine.reminders_json(self.periods, "[]", TODAY, settings))
        self.assertEqual(items, [])

    def test_a_marked_pill_removes_that_day(self) -> None:
        settings = engine.settings_to_json(ReminderSettings(pill_enabled=True))
        records = engine.diary_save("[]", TODAY, pill=1)
        items = json.loads(
            engine.reminders_json(self.periods, records, TODAY, settings, horizon_days=1)
        )
        pills = [i for i in items if i["kind"] == "pill"]
        self.assertEqual(len(pills), 1)
        self.assertEqual(pills[0]["day"], (date.fromisoformat(TODAY) + timedelta(days=1)).isoformat())


if __name__ == "__main__":
    unittest.main(verbosity=2)
