"""Проверка оболочки без экрана: окно собирается и кнопки работают.

Запуск (Linux, где нет дисплея):

    QT_QPA_PLATFORM=offscreen LD_LIBRARY_PATH=... python3 desktop/smoke_test.py

На Windows запускается обычным python: desktop\\smoke_test.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Консоль Windows умеет быть не в UTF-8, и тогда первый же русский текст в
# выводе валит проверку ошибкой кодировки — обидно, когда проверка по сути
# прошла. Просим UTF-8, а если поток его не принимает, теряем буквы, но не
# результат.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as main_module  # noqa: E402
import prefs  # noqa: E402
from cycle_core import engine  # noqa: E402
from main import MainWindow  # noqa: E402
from store import Store  # noqa: E402

failures: list[str] = []


def check(condition: bool, what: str) -> None:
    if condition:
        print(f"  ок: {what}")
    else:
        print(f"  ПЛОХО: {what}")
        failures.append(what)


def main() -> int:
    app = QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        store = Store(Path(folder))
        window = MainWindow(store)
        window.show()

        print("Сегодня")
        check("Записей пока нет" in window.summary.toPlainText(), "пустой календарь приглашает отметить день")
        check(not window.button_period_end.isEnabled(), "кнопка «последний день» выключена без отметки")

        window.mark_period_start()
        check("Идут месячные" in window.summary.toPlainText(), "после отметки видны месячные")
        check("первый день" in window.summary.toPlainText(), "первый день назван словом")
        check(window.button_period_end.isEnabled(), "кнопка «последний день» включилась")
        check("Отмечен первый день" in window.message.toPlainText(), "первое нажатие отмечено и сказано")
        check(store.periods_text() != "[]", "отметка сохранена в файл")

        window.mark_period_start()
        check("уже отмечен" in window.message.toPlainText(), "повторное нажатие не создаёт второй цикл")
        check(len(json.loads(store.periods_text())) == 1, "в истории по-прежнему один цикл")

        window.mark_period_end()
        check("Отмечен последний день" in window.message.toPlainText(), "месячные закрылись")
        check(not window.button_period_end.isEnabled(), "после закрытия кнопка снова выключена")

        print("Календарь")
        window.refresh_month()
        check(window.month_list.count() in (28, 29, 30, 31), "в месяце столько дней, сколько в календаре")
        check("до первой отметки" in window.month_list.item(0).text(),
              "день до первой отметки честно об этом говорит")
        today_line = window.month_list.item(date.today().day - 1).text()
        check("месячные" in today_line, "отмеченный день назван месячными")
        first_row = window.month_list.currentRow()
        window.shift_month(1)
        check(window.month_list.count() > 0, "следующий месяц открывается")
        window.shift_month(-2)
        check(window.month_list.count() > 0, "предыдущий месяц открывается")
        window.go_current_month()
        check(window.month_list.currentRow() == first_row, "возврат к текущему месяцу ставит курсор на сегодня")

        print("Дневник")
        window.diary_pain.setCurrentIndex(4)
        window.diary_flow.setCurrentIndex(3)
        window.diary_temp_on.setChecked(True)
        window.diary_temp.setValue(36.7)
        window.diary_pill.setCurrentIndex(1)
        window.diary_note.setText("болела голова")
        window.save_diary_day()
        check("сохранена" in window.message.toPlainText(), "запись дневника сохранена")
        view = window.diary_view.toPlainText()
        check("болела голова" in view, "заметка видна в списке записей")
        check("температура 36.7" in view, "температура видна в списке записей")
        check("1-й день цикла" in view, "день цикла посчитан")

        window.show_diary_summary()
        check("Боль отмечена" in window.message.toPlainText(), "сводка по дневнику говорит словами")

        window.clear_diary_day()
        check(window.diary_view.toPlainText().strip().endswith("Дневник пока пуст."),
              "запись можно убрать целиком")

        print("Настройки")
        window.set_pill_on.setChecked(True)
        window.set_pill_hour.setValue(21)
        window.save_settings()
        check("Настройки сохранены" in window.message.toPlainText(), "настройки сохраняются")
        check("Ближайшее напоминание" in window.settings_view.toPlainText(),
              "в настройках видно ближайшее напоминание")

        print("Копии")
        backup = store.backup_text()
        check("format" in backup, "копия собирается")
        store.save_periods("[]")
        store.save_records("[]")
        report = store.restore_text(backup)
        check("Восстановлено" in report, "копия восстанавливается")
        check(json.loads(store.periods_text()) != [], "отметки вернулись из копии")
        for broken in ("не json", "{}", '{"periods": []}'):
            try:
                store.restore_text(broken)
                check(False, f"мусор вместо копии отвергается: {broken}")
            except ValueError:
                check(True, f"мусор вместо копии отвергается: {broken}")

        print("Напоминания")
        # Окно с напоминанием ждёт нажатия «Окей», поэтому в тесте подменяем
        # показ окна на запись: иначе тест просто завис бы навсегда.
        boxes: list[str] = []
        main_module.QMessageBox.information = staticmethod(
            lambda parent, title, text, *args, **kwargs: boxes.append(text)
        )

        # Две отметки в прошлом: прогноз должен появиться, а напоминание
        # о месячных — всплыть, когда время пришло.
        first = date.today() - timedelta(days=56)
        second = date.today() - timedelta(days=28)
        window.periods = json.dumps(
            [
                {"start": first.isoformat(), "end": (first + timedelta(days=4)).isoformat()},
                {"start": second.isoformat(), "end": (second + timedelta(days=4)).isoformat()},
            ]
        )
        window.refresh_all()
        check("цикла" in window.summary.toPlainText(), "прогноз появился после истории")
        window.shown = set()
        window.check_reminders()
        check(bool(boxes), "напоминание показано, когда пришло его время")
        check("месячные" in boxes[0], "напоминание говорит про месячные")
        check(window.shown, "показанное напоминание запомнено")
        boxes.clear()
        window.check_reminders()
        check(not boxes, "второй раз то же напоминание не всплывает")

        print("Люди")
        check(window.person == "Я", "на свежей установке календарь подписан именем по умолчанию")
        check("Календарь: Я" in window.today_person.text(), "экран «Сегодня» говорит, чей календарь открыт")
        check("Я —" in window.month_title.text(), "заголовок календаря называет человека")
        check(window.summary.toPlainText().startswith("Я: "), "сводка начинается с имени")

        # Заводим дочь и убеждаемся, что календари не смешиваются: иначе мамины
        # отметки попали бы в дочкин прогноз, и это была бы не косметика, а
        # неверный прогноз.
        window.periods = json.dumps(
            [{"start": (date.today() - timedelta(days=28)).isoformat()}]
        )
        window.store.save_periods(window.periods)
        window.refresh_all()

        window._ask_name = lambda label, initial="": "Настя"
        window.add_person()
        check(window.person == "Настя", "заведённый человек сразу открыт")
        check("Заведён календарь: Настя" in window.message.toPlainText(),
              "заведение календаря сказано словами")
        check(len(window.store.people()) == 2, "календарей стало два")
        check("Записей пока нет" in window.summary.toPlainText(),
              "у нового человека свой пустой календарь")
        check(json.loads(window.periods) == [], "у нового человека нет чужих отметок")

        window.mark_period_start()
        check("Отмечен первый день месячных" in window.message.toPlainText(),
              "отметка ставится в открытый календарь")
        check(window.message.toPlainText().startswith("Настя: "),
              "что произошло — тоже с именем")

        window.records = engine.diary_save(
            window.records, date.today().isoformat(), pain=2, note="дочкина запись"
        )
        window.store.save_records(window.records)

        left = window.store.people()[0].id
        window.open_person(left)
        check(window.person == "Я", "возврат к первому человеку")
        check(json.loads(window.periods) != [], "мамины отметки на месте")
        check("дочкина запись" not in window.diary_view.toPlainText(),
              "дочкин дневник маме в её календаре не показывается")
        window.open_person(window.store.people()[1].id)
        check("дочкина запись" in window.diary_view.toPlainText(),
              "а в своём календаре запись на месте")

        window._ask_name = lambda label, initial="": "Анастасия"
        window.rename_person()
        check(window.person == "Анастасия", "переименование меняет имя")
        check(json.loads(window.periods) != [], "переименование не потеряло отметки")

        # Напоминание обязано называть человека: на телефоне с двумя
        # календарями безымянное «ожидаются месячные» не понять.
        first = date.today() - timedelta(days=56)
        second = date.today() - timedelta(days=28)
        window.periods = json.dumps(
            [
                {"start": first.isoformat(), "end": (first + timedelta(days=4)).isoformat()},
                {"start": second.isoformat(), "end": (second + timedelta(days=4)).isoformat()},
            ]
        )
        window.store.save_periods(window.periods)
        window.refresh_all()
        window.shown = set()
        items = json.loads(
            engine.reminders_json(
                window.periods,
                window.records,
                date.today().isoformat(),
                engine.settings_to_json(window.settings),
                horizon_days=45,
                person_name=window.person,
            )
        )
        check(bool(items), "у второго человека появились напоминания")
        check(all(item["text"].startswith("Анастасия: ") for item in items),
              "каждое напоминание называет человека")

        # Напоминания обязаны приходить про всех, а не только про открытого:
        # иначе второй календарь молчал бы ровно тогда, когда он и нужен, —
        # пока в него не переключатся.
        daughter = window.store.people()[1].id
        window.open_person(window.store.people()[0].id)
        check(window.person == "Я", "открыт мамин календарь")
        # Стираем «показанное» обоим: иначе дочкино напоминание уже было бы
        # съедено раньше и проверять стало бы нечего.
        window.shown = set()
        window.store.save_shown(window.shown)
        window.store.save_shown_for(daughter, set())
        boxes.clear()
        window.check_reminders()
        check(any("Анастасия" in box for box in boxes),
              "напоминание про закрытый календарь всё равно всплывает")
        window.open_person(daughter)

        main_module.QMessageBox.question = staticmethod(
            lambda *args, **kwargs: main_module.QMessageBox.StandardButton.Yes
        )
        removed = window.store.person_id()
        window.remove_person()
        check(len(window.store.people()) == 1, "человек убран из списка")
        check(window.person == "Я", "после удаления открыт оставшийся календарь")
        check(not (Path(folder) / "people" / removed).exists(),
              "папка удалённого человека стёрта")
        check("убран" in window.message.toPlainText(), "удаление сказано словами")

        # Последнего человека убрать нельзя: показывать станет нечего. Проверяем
        # на отдельной папке, чтобы не трогать окно.
        single = Store(Path(folder) / "единственный")
        check(single.remove_person(single.person_id()) != "",
              "единственный календарь убрать нельзя")
        check(len(single.people()) == 1, "он и остался единственным")

        backup = json.loads(store.backup_text())
        check(len(backup["people"]) == 1, "в копии лежат все календари")
        check(backup["people"][0]["periods"] != [], "в копии есть отметки человека")
        store.save_periods("[]")
        report = store.restore_text(json.dumps(backup, ensure_ascii=False))
        check("Восстановлено" in report, "копия со всеми календарями восстанавливается")
        check(json.loads(store.periods_text()) != [], "отметки вернулись из копии")
        check(store.person_name() != "", "после восстановления открыт именованный календарь")

        print("Работа программы")
        check(not window.windowIcon().isNull(), "у окна есть значок")
        check(not main_module._app_icon().pixmap(32, 32).isNull(), "значок рисуется")
        check(window.set_keep_running.isChecked(),
              "по умолчанию программа продолжает работать с закрытым окном")
        check(not window.set_autostart.isChecked(), "автозапуск по умолчанию выключен")

        # Решение про закрытое окно должно пережить перезапуск: иначе после
        # каждого обновления напоминания молча пропадали бы.
        window.set_keep_running.setChecked(False)
        saved = json.loads(store.prefs_text() or "{}")
        check(saved.get("keep_running") is False, "решение про закрытие окна сохранено")
        check(prefs.load(store)["keep_running"] is False,
              "решение переживает перезапуск программы")
        window.set_keep_running.setChecked(True)

        check(prefs.load(Store(Path(folder) / "пусто"))["keep_running"] is True,
              "без файла настроек берётся «продолжать работу»")
        store.save_prefs("не json")
        check(prefs.load(store)["keep_running"] is True,
              "испорченный файл настроек не мешает программе открыться")

        window.quitting = True
        window.close()

    if failures:
        print(f"\nПровалено: {len(failures)}")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nВсё в порядке.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
