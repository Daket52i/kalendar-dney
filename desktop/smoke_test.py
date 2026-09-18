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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as main_module  # noqa: E402
import prefs  # noqa: E402
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
        check(window.diary_view.toPlainText().strip() == "Дневник пока пуст.",
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
