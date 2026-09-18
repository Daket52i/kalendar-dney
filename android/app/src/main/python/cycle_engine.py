"""Мост между Android и ядром календаря.

Логики здесь нет вообще: все функции уже живут в cycle_core.engine, откуда их
берёт и версия для Windows. Этот файл нужен только затем, чтобы у Kotlin были
привычные имена вида mark_start вместо engine.mark_start.
"""

from __future__ import annotations

from cycle_core import engine, phrases

summary = engine.summary
month = engine.month
history = engine.history
mark_start = engine.mark_start
mark_end = engine.mark_end
state = engine.state
medical_note = engine.medical_note

# Люди: у каждого свой календарь, дневник и напоминания. Файлы раскладывает
# Kotlin, а список людей, имена и проверки — здесь: правила про имя одни и те же
# на телефоне и на компьютере.
people_json = engine.people_json
person_add = engine.person_add
person_rename = engine.person_rename
person_remove = engine.person_remove
person_switch = engine.person_switch

# Имя перед фразой ставит ядро, а не оболочка: правило одно на телефон и на
# компьютер, и забыть про имя в новой фразе нельзя незаметно.
signed = phrases.signed
