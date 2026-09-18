"""Мост между Android и ядром календаря.

Логики здесь нет вообще: все функции уже живут в cycle_core.engine, откуда их
берёт и версия для Windows. Этот файл нужен только затем, чтобы у Kotlin были
привычные имена вида mark_start вместо engine.mark_start.
"""

from __future__ import annotations

from cycle_core import engine

summary = engine.summary
month = engine.month
history = engine.history
mark_start = engine.mark_start
mark_end = engine.mark_end
state = engine.state
medical_note = engine.medical_note
