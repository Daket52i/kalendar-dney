"""Люди, чьи календари ведёт приложение.

Одно устройство — несколько человек: мама ведёт и свой календарь, и календарь
дочери, и переключается между ними. У каждого свои отметки, свой дневник и свои
напоминания, и ничего общего между ними нет.

Идентификатор человека намеренно не связан с именем. Имя можно поменять в любой
момент, и данные при этом остаются на месте — в файлах лежит идентификатор.
Именно поэтому «p1», а не слаг из имени: переименование не должно выглядеть как
потеря истории.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

#: Длина имени ограничена не ради экономии, а ради интерфейса: имя подставляется
#: в начало каждой произносимой фразы, и длинная фраза на слух превращается в
#: кашу. Сорока знаков хватает на «Настя» и на «Мария Петровна».
MAX_NAME = 40

#: Имя по умолчанию — когда человек не назвался. Не «Настя» и не пусто: пустое
#: имя сломало бы правило «каждая фраза называет, чей это календарь».
DEFAULT_NAME = "Я"


@dataclass(frozen=True)
class Person:
    """Человек, чей календарь ведётся. `id` неизменен, `name` — нет."""

    id: str
    name: str


def clean_name(raw: str) -> str:
    """Приводит имя к тому виду, в котором его не стыдно произнести вслух.

    Убираем управляющие символы и переносы строк — имя подставляется в одну
    строку сообщения, и перевод строки в нём развалил бы вывод. Лишние пробелы
    схлопываем, длину ограничиваем.
    """
    if not raw:
        return ""
    text = "".join(" " if character.isspace() else character for character in str(raw))
    text = "".join(character for character in text if character.isprintable())
    return " ".join(text.split())[:MAX_NAME].strip()


def _default() -> Person:
    return Person(id="p1", name=DEFAULT_NAME)


def make_id(taken: set[str]) -> str:
    """Свободный идентификатор. Номер, а не имя: переименование не должно
    терять данные, а два человека могут назваться одинаково."""
    number = 1
    while f"p{number}" in taken:
        number += 1
    return f"p{number}"


def from_json(raw: str) -> tuple[list[Person], str]:
    """Читает список людей и того, кто выбран сейчас.

    Возвращает пару: люди и идентификатор текущего. Пустой или испорченный файл
    даёт одного человека по умолчанию — приложение должно открыться, а не
    показать ошибку. Человек без имени получает имя по умолчанию по той же
    причине: безымянный календарь нельзя ни показать, ни произнести.
    """
    people: list[Person] = []
    current = ""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        data = {}

    if isinstance(data, dict):
        items = data.get("people")
        current = str(data.get("current") or "")
    elif isinstance(data, list):
        # Так выглядел бы список людей в первой версии формата. Читаем и его:
        # терять чужую историю из-за смены обёртки нельзя.
        items = data
    else:
        items = None

    if isinstance(items, list):
        seen: set[str] = set()
        for item in items:
            if isinstance(item, str):
                item = {"name": item}
            if not isinstance(item, dict):
                continue
            person_id = str(item.get("id") or "").strip()
            if not person_id or person_id in seen:
                person_id = make_id(seen)
            seen.add(person_id)
            name = clean_name(item.get("name") or "") or DEFAULT_NAME
            people.append(Person(id=person_id, name=name))

    if not people:
        people = [_default()]

    if current not in {person.id for person in people}:
        current = people[0].id
    return people, current


def to_json(people: list[Person], current: str) -> str:
    return json.dumps(
        {
            "current": current,
            "people": [{"id": person.id, "name": person.name} for person in people],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def get(people: list[Person], person_id: str) -> Person | None:
    for person in people:
        if person.id == person_id:
            return person
    return None


def name_of(people: list[Person], person_id: str) -> str:
    """Имя человека для подстановки во фразы. Незнакомый идентификатор даёт
    пустую строку, а не падение: подставить чужое имя хуже, чем не подставить
    никакого."""
    person = get(people, person_id)
    return person.name if person is not None else ""


def add(people: list[Person], name: str) -> tuple[list[Person], Person]:
    """Заводит человека. Имя обязательно: безымянный профиль не отличить от
    другого безымянного, и мама не поймёт, чей календарь открыт."""
    cleaned = clean_name(name)
    if not cleaned:
        raise ValueError("Имя не может быть пустым.")
    person = Person(id=make_id({item.id for item in people}), name=cleaned)
    return people + [person], person


def rename(people: list[Person], person_id: str, name: str) -> list[Person]:
    """Меняет имя, не трогая данные: в файлах лежит идентификатор."""
    cleaned = clean_name(name)
    if not cleaned:
        raise ValueError("Имя не может быть пустым.")
    if get(people, person_id) is None:
        raise ValueError("Такого человека нет.")
    return [
        Person(id=person.id, name=cleaned) if person.id == person_id else person
        for person in people
    ]


def remove(people: list[Person], person_id: str) -> list[Person]:
    """Убирает человека из списка.

    Последнего не убираем: приложение без единого календаря не имеет смысла, и
    показать было бы нечего. Что делать с его файлами, решает оболочка — ядро
    про файлы ничего не знает.
    """
    if get(people, person_id) is None:
        raise ValueError("Такого человека нет.")
    if len(people) <= 1:
        raise ValueError("Единственный календарь убрать нельзя.")
    return [person for person in people if person.id != person_id]


def next_after_removal(people: list[Person], current: str, person_id: str) -> str:
    """Кто станет текущим, если убрать этого человека. Нужно оболочке, чтобы
    после удаления открылся чей-то календарь, а не пустота."""
    remaining = [person for person in people if person.id != person_id]
    if not remaining:
        return ""
    if current != person_id:
        return current
    return remaining[0].id
