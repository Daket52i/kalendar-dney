"""Проверки людей: несколько календарей на одном устройстве.

Главное, что здесь проверяется, — два правила. Первое: переименование не теряет
данные, потому что в файлах лежит идентификатор, а не имя. Второе: любую фразу,
которую приложение произносит вслух, можно опознать — она называет, чей это
календарь.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cycle_core import engine, journal, people  # noqa: E402
from cycle_core.models import Period  # noqa: E402

from datetime import date  # noqa: E402

TODAY = "2026-03-20"


def _periods_json(*days: tuple[int, int, int]) -> str:
    return journal.to_json([Period(start=date(y, m, d)) for y, m, d in days])


class ParsingTest(unittest.TestCase):
    def test_empty_gives_one_person(self) -> None:
        people_list, current = people.from_json("")
        self.assertEqual(len(people_list), 1)
        self.assertEqual(people_list[0].id, current)

    def test_broken_json_gives_one_person(self) -> None:
        people_list, current = people.from_json("не json")
        self.assertEqual(len(people_list), 1)
        self.assertEqual(people_list[0].name, people.DEFAULT_NAME)

    def test_round_trip(self) -> None:
        document = people.to_json([people.Person("p1", "Настя")], "p1")
        people_list, current = people.from_json(document)
        self.assertEqual(current, "p1")
        self.assertEqual(people_list[0].name, "Настя")

    def test_current_pointing_nowhere_falls_back_to_first(self) -> None:
        document = '{"current": "p9", "people": [{"id": "p1", "name": "Настя"}]}'
        _, current = people.from_json(document)
        self.assertEqual(current, "p1")

    def test_person_without_name_gets_default(self) -> None:
        document = '{"people": [{"id": "p1", "name": "   "}]}'
        people_list, _ = people.from_json(document)
        self.assertEqual(people_list[0].name, people.DEFAULT_NAME)

    def test_duplicate_ids_are_split(self) -> None:
        document = '{"people": [{"id": "p1", "name": "Настя"}, {"id": "p1", "name": "Мама"}]}'
        people_list, _ = people.from_json(document)
        self.assertEqual(len({item.id for item in people_list}), 2)

    def test_plain_list_of_names_is_readable(self) -> None:
        people_list, current = people.from_json('["Настя", "Мама"]')
        self.assertEqual([item.name for item in people_list], ["Настя", "Мама"])
        self.assertEqual(current, people_list[0].id)


class NameTest(unittest.TestCase):
    def test_newlines_and_tabs_do_not_get_into_the_name(self) -> None:
        self.assertEqual(people.clean_name("Нас\nтя\tИванова"), "Нас тя Иванова")

    def test_long_name_is_cut(self) -> None:
        self.assertEqual(len(people.clean_name("я" * 100)), people.MAX_NAME)

    def test_empty_name_is_rejected(self) -> None:
        people_list = [people.Person("p1", "Настя")]
        with self.assertRaises(ValueError):
            people.add(people_list, "   ")

    def test_add_gives_a_free_id(self) -> None:
        people_list, first = people.add([], "Настя")
        people_list, second = people.add(people_list, "Мама")
        self.assertNotEqual(first.id, second.id)
        self.assertEqual([item.name for item in people_list], ["Настя", "Мама"])

    def test_rename_keeps_the_id(self) -> None:
        people_list, person = people.add([], "Настя")
        renamed = people.rename(people_list, person.id, "Анастасия")
        self.assertEqual(renamed[0].id, person.id)
        self.assertEqual(renamed[0].name, "Анастасия")

    def test_rename_of_unknown_person_fails(self) -> None:
        with self.assertRaises(ValueError):
            people.rename([people.Person("p1", "Настя")], "p9", "Мама")

    def test_last_person_cannot_be_removed(self) -> None:
        with self.assertRaises(ValueError):
            people.remove([people.Person("p1", "Настя")], "p1")

    def test_removal_picks_a_new_current(self) -> None:
        people_list = [people.Person("p1", "Настя"), people.Person("p2", "Мама")]
        self.assertEqual(people.next_after_removal(people_list, "p2", "p2"), "p1")

    def test_removal_keeps_current_when_it_is_another_person(self) -> None:
        people_list = [people.Person("p1", "Настя"), people.Person("p2", "Мама")]
        self.assertEqual(people.next_after_removal(people_list, "p2", "p1"), "p2")

    def test_name_of_unknown_person_is_empty(self) -> None:
        self.assertEqual(people.name_of([people.Person("p1", "Настя")], "p9"), "")


def _first_run(name: str) -> str:
    """Первый запуск: единственный календарь получает имя хозяйки.

    Так это и происходит в жизни: свежая установка даёт одного человека с именем
    по умолчанию, и оболочка спрашивает имя — переименованием, а не вторым
    профилем. Иначе рядом с «Настей» всегда висело бы пустое «Я».
    """
    document = json.loads(engine.people_json(""))
    return json.loads(engine.person_rename(document, document["current"], name))["people"]


class BridgeTest(unittest.TestCase):
    def test_adding_switches_to_the_new_person(self) -> None:
        answer = json.loads(engine.person_add(_first_run("Настя"), "Мама"))
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["name"], "Мама")
        self.assertEqual(answer["names"], ["Настя", "Мама"])

    def test_first_run_renames_the_only_person(self) -> None:
        answer = json.loads(engine.people_json(_first_run("Настя")))
        self.assertEqual(answer["names"], ["Настя"])
        self.assertTrue(answer["ok"])

    def test_empty_name_is_an_error_not_a_failure(self) -> None:
        answer = json.loads(engine.person_add(engine.people_json(""), "  "))
        self.assertFalse(answer["ok"])
        self.assertTrue(answer["error"])
        self.assertEqual(answer["names"], [people.DEFAULT_NAME])

    def test_removing_the_last_person_is_refused(self) -> None:
        document = engine.people_json("")
        answer = json.loads(engine.person_remove(document, json.loads(document)["current"]))
        self.assertFalse(answer["ok"])
        self.assertTrue(answer["names"])

    def test_switch_to_unknown_person_is_refused(self) -> None:
        answer = json.loads(engine.person_switch(engine.people_json(""), "p9"))
        self.assertFalse(answer["ok"])

    def test_document_survives_a_round_trip_through_the_bridge(self) -> None:
        second = json.loads(engine.person_add(_first_run("Настя"), "Мама"))
        again = json.loads(engine.people_json(second["people"]))
        self.assertEqual(again["names"], ["Настя", "Мама"])
        self.assertEqual(again["name"], "Мама")

    def test_removing_switches_to_the_one_that_is_left(self) -> None:
        document = json.loads(engine.person_add(_first_run("Настя"), "Мама"))
        answer = json.loads(engine.person_remove(document["people"], document["current"]))
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["names"], ["Настя"])
        self.assertEqual(answer["name"], "Настя")


class SpokenNameTest(unittest.TestCase):
    """Ни одна произносимая фраза не должна терять имя человека."""

    def setUp(self) -> None:
        self.periods = _periods_json((2026, 1, 1), (2026, 1, 29), (2026, 2, 26))
        self.records = engine.diary_save(
            "[]", "2026-03-05", pain=3, flow="обычные", temperature=36.7, note="болела голова"
        )
        self.settings = engine.settings_to_json(engine.settings_from_json("{}"))

    def test_summary_is_signed(self) -> None:
        text = engine.summary(self.periods, TODAY, "Настя")
        self.assertTrue(text.startswith("Настя: "), text)

    def test_summary_without_history_is_signed(self) -> None:
        text = engine.summary("[]", TODAY, "Настя")
        self.assertTrue(text.startswith("Настя: "), text)

    def test_history_is_signed(self) -> None:
        self.assertTrue(engine.history(self.periods, "Настя").startswith("Настя: "))

    def test_diary_summary_is_signed(self) -> None:
        text = engine.diary_summary(self.records, self.periods, "Настя")
        self.assertTrue(text.startswith("Настя: "), text)

    def test_diary_history_is_signed(self) -> None:
        text = engine.diary_history(self.records, self.periods, person_name="Настя")
        self.assertTrue(text.startswith("Настя: "), text)

    def test_diary_history_signs_only_the_first_line(self) -> None:
        text = engine.diary_history(self.records, self.periods, person_name="Настя")
        self.assertNotIn("Настя", "\n".join(text.splitlines()[1:]))

    def test_every_reminder_is_signed(self) -> None:
        items = json.loads(
            engine.reminders_json(
                self.periods, self.records, TODAY, self.settings, person_name="Настя"
            )
        )
        self.assertTrue(items)
        for item in items:
            self.assertTrue(item["text"].startswith("Настя: "), item["text"])

    def test_reminder_lines_are_signed(self) -> None:
        lines = json.loads(
            engine.reminders_lines(
                self.periods, self.records, TODAY, self.settings, person_name="Настя"
            )
        )
        self.assertTrue(lines)
        for line in lines:
            self.assertIn("Настя: ", line)

    def test_reminder_key_does_not_depend_on_the_name(self) -> None:
        """Ключ «уже показывали» считается внутри одного календаря, поэтому имя
        в него не входит: иначе переименование показало бы старые напоминания
        заново."""
        with_name = json.loads(
            engine.reminders_json(self.periods, self.records, TODAY, self.settings,
                                  person_name="Настя")
        )
        without = json.loads(
            engine.reminders_json(self.periods, self.records, TODAY, self.settings)
        )
        self.assertEqual([item["key"] for item in with_name],
                         [item["key"] for item in without])

    def test_missing_name_changes_nothing_else(self) -> None:
        """Без имени фраза та же самая — только без подписи."""
        signed = engine.summary(self.periods, TODAY, "Настя")
        self.assertEqual(signed, "Настя: " + engine.summary(self.periods, TODAY))


if __name__ == "__main__":
    unittest.main()
