"""«Календарь дней» для Windows.

Окно — тонкая оболочка над ядром: все фразы, расчёты и напоминания приходят
из cycle_core, поэтому версия для компьютера говорит ровно то же самое, что
версия для телефона.

Главное правило вёрстки: каждое действие — одна кнопка с внятной подписью,
а результат действия попадает в поле «Что произошло» и туда же переводится
фокус. Так программа-экранный диктор (NVDA, JAWS) обязательно его прочитает:
окно не может «озвучить» что-то само, но диктор читает то, на что встал фокус.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

# Ядро лежит рядом с оболочкой — в core/. После сборки в один exe оно
# распаковывается во временную папку PyInstaller, поэтому путей два.
_HERE = Path(__file__).resolve().parent
for candidate in (_HERE / "core", _HERE.parent / "core", Path(getattr(sys, "_MEIPASS", ".")) / "core"):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        break

from cycle_core import engine  # noqa: E402
from cycle_core.reminders import ReminderSettings  # noqa: E402

from PySide6.QtCore import QDate, QRectF, QTimer, QUrl, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QAccessible,
    QAccessibleEvent,
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPainter,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import prefs  # noqa: E402
from store import Store  # noqa: E402

NORMAL_FONT_POINT_SIZE = 12
LARGE_FONT_POINT_SIZE = 16

# Свои названия месяцев, а не calendar.month_name: тот зависит от локали
# системы, и на чужой локали заголовок календаря стал бы английским.
MONTHS_NOMINATIVE = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)

PAIN_CHOICES = (
    ("не отмечено", 0),
    ("1 — почти не болит", 1),
    ("2 — слабая", 2),
    ("3 — заметная", 3),
    ("4 — сильная", 4),
    ("5 — очень сильная", 5),
)
MOOD_CHOICES = (
    "", "спокойное", "радостное", "обычное", "усталое",
    "раздражённое", "тревожное", "плаксивое", "болит голова",
)
FLOW_CHOICES = ("не отмечено", "нет", "слабые", "обычные", "сильные")
PILL_CHOICES = (("не отмечено", -1), ("выпила", 1), ("не выпила", 0))

REMINDER_CHECK_INTERVAL_MS = 60_000


def _read_aloud(widget: QWidget, text: str) -> None:
    """Просит диктора сказать текст прямо сейчас, не дожидаясь перехода фокуса.

    Работает не во всех версиях Windows и не со всеми дикторами, поэтому это
    только дополнение: основной способ — поле «Что произошло», на которое
    переводится фокус.
    """
    try:
        event = QAccessibleEvent(QAccessible.Event.Alert, widget)
        event.setMessage(text)
        QAccessible.updateAccessibility(event)
    except Exception:
        pass


def _to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _from_qdate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


ICON_BACKGROUND = "#5A2A4F"
ICON_HEADER = "#E0725F"

# Рисунок значка повторяет тот, что на телефоне (там он собран из вектора
# ic_launcher_foreground.xml). Координаты — в холсте 108 на 108, как в том
# векторе: так оба значка остаются одним и тем же календариком.
ICON_PAGE = (28.0, 30.0, 80.0, 82.0)
ICON_HEADER_BOTTOM = 46.0
ICON_RINGS = ((40.0, 22.0, 34.0), (68.0, 22.0, 34.0))
ICON_DOTS = tuple(
    (x, y)
    for y in (58.0, 70.0)
    for x in (40.0, 54.0, 68.0)
)


def _app_icon() -> QIcon:
    """Значок программы: рисуется кодом, а не читается из файла.

    После сборки в один exe лишняя картинка легко теряется, а значок нужен
    всегда — он же висит в трее рядом с часами, и по нему программа
    открывается заново, когда окно закрыто.
    """
    canvas = 108.0
    size = 256
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    scale = size / canvas

    def box(x1: float, y1: float, x2: float, y2: float) -> QRectF:
        return QRectF(x1 * scale, y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale)

    painter.setBrush(QColor(ICON_BACKGROUND))
    painter.drawRoundedRect(box(0, 0, canvas, canvas), 20 * scale, 20 * scale)

    left, top, right, bottom = ICON_PAGE
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(box(left, top, right, bottom), 6 * scale, 6 * scale)

    # Шапка листа: скруглённая сверху и прямая снизу — рисуем её скруглённой
    # целиком и закрашиваем нижнюю половину тем же цветом.
    header_middle = (top + ICON_HEADER_BOTTOM) / 2
    painter.setBrush(QColor(ICON_HEADER))
    painter.drawRoundedRect(box(left, top, right, ICON_HEADER_BOTTOM), 6 * scale, 6 * scale)
    painter.drawRect(box(left, header_middle, right, ICON_HEADER_BOTTOM))

    painter.setBrush(QColor("#FFFFFF"))
    for x, ring_top, ring_bottom in ICON_RINGS:
        painter.drawRoundedRect(
            box(x - 2, ring_top, x + 2, ring_bottom), 2 * scale, 2 * scale
        )

    painter.setBrush(QColor(ICON_BACKGROUND))
    for x, y in ICON_DOTS:
        painter.drawEllipse(box(x - 3.5, y - 3.5, x + 3.5, y + 3.5))

    painter.end()

    icon = QIcon()
    for side in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(pixmap.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return icon


class MainWindow(QMainWindow):
    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self.periods = store.periods_text()
        self.records = store.records_text()
        self.settings = engine.settings_from_json(store.settings_text())
        self.shown = store.shown_keys()
        self.prefs = prefs.load(store)
        self.quitting = False
        self.month_year = date.today().year
        self.month_number = date.today().month

        self.setWindowTitle("Календарь дней")
        self.setWindowIcon(_app_icon())
        self.resize(760, 720)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_today(), "Сегодня")
        self.tabs.addTab(self._build_calendar(), "Календарь")
        self.tabs.addTab(self._build_diary(), "Дневник")
        self.tabs.addTab(self._build_history(), "История")
        self.tabs.addTab(self._build_settings(), "Настройки")
        self.setCentralWidget(self.tabs)

        self.refresh_all()

        # Напоминания проверяем раз в минуту. Пока программа работает — а она
        # продолжает работать и с закрытым окном, если так решено в
        # настройках, — напоминание не потеряется.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_reminders)
        self.timer.start(REMINDER_CHECK_INTERVAL_MS)
        QTimer.singleShot(1500, self.check_reminders)

        self.tray = self._build_tray()
        if self.tray is not None:
            # Закрытие окна больше не значит «выход»: программа остаётся в
            # трее и продолжает напоминать. Выход — только через «Выход» в
            # меню значка, и он закрывает всё разом.
            QApplication.instance().setQuitOnLastWindowClosed(False)

    # -------------------------------------------------------------------- Трей

    def _build_tray(self) -> QSystemTrayIcon | None:
        """Значок рядом с часами: через него программа открывается заново.

        Без него закрытое окно означало бы конец программы — а вместе с ним и
        напоминаний. Если трея в системе нет (так бывает на некоторых
        сборках), возвращаем None: тогда окно закрывается по-настоящему, и
        лучше так, чем обещать работу, которой не будет.
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None

        tray = QSystemTrayIcon(_app_icon(), self)
        tray.setToolTip("Календарь дней")

        menu = QMenu()
        show_action = QAction("Открыть окно", menu)
        show_action.triggered.connect(self._show_from_tray)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction("Выход", menu)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)

        tray.activated.connect(self._on_tray_clicked)
        tray.show()
        return tray

    def _on_tray_clicked(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.tabs.setFocus()

    def _quit_from_tray(self) -> None:
        self.quitting = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 — имя задано Qt
        """Закрытие окна. По умолчанию программа остаётся работать."""
        if self.prefs["keep_running"] and not self.quitting and self.tray is not None:
            self.hide()
            event.ignore()
            self.tray.showMessage(
                "Календарь дней",
                "Программа продолжает работать: напоминания придут. Открыть окно — "
                "двойной щелчок по значку рядом с часами.",
                QSystemTrayIcon.Information,
                10_000,
            )
            return
        event.accept()
        QApplication.instance().quit()

    # ---------------------------------------------------------------- Сегодня

    def _build_today(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setAccessibleName("Сегодня")
        self.summary.setMinimumHeight(150)
        layout.addWidget(self.summary)

        self.button_period_start = QPushButton("Отметить первый день месячных")
        self.button_period_start.setMinimumHeight(48)
        self.button_period_start.clicked.connect(self.mark_period_start)
        layout.addWidget(self.button_period_start)

        self.button_period_end = QPushButton("Отметить последний день месячных")
        self.button_period_end.setMinimumHeight(48)
        self.button_period_end.clicked.connect(self.mark_period_end)
        layout.addWidget(self.button_period_end)

        hint = QLabel(
            "Если месячные ещё идут, вторую кнопку нажимать не нужно — "
            "нажми её в последний день."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.message = QPlainTextEdit()
        self.message.setReadOnly(True)
        self.message.setAccessibleName("Что произошло")
        self.message.setMinimumHeight(90)
        layout.addWidget(self.message)

        layout.addStretch(1)
        return page

    def say(self, text: str) -> None:
        """Пишет в поле сообщения и переводит туда фокус — так диктор прочитает."""
        self.message.setPlainText(text)
        self.message.moveCursor(QTextCursor.MoveOperation.Start)
        self.message.setFocus()
        _read_aloud(self.message, text)

    def mark_period_start(self) -> None:
        today = date.today().isoformat()
        updated = engine.mark_start(self.periods, today)
        if updated == self.periods:
            self.say("Первый день месячных на сегодня уже отмечен.")
            return
        self.periods = updated
        self.store.save_periods(self.periods)
        self.refresh_all()
        self.say("Отмечен первый день месячных. " + self._summary_line())

    def mark_period_end(self) -> None:
        today = date.today().isoformat()
        state = json.loads(engine.state(self.periods))
        if not state["open"]:
            self.say(
                "Незакрытой отметки нет. Сначала отметь первый день месячных — "
                "тогда эта кнопка закроет их в последний день."
            )
            return
        self.periods = engine.mark_end(self.periods, today)
        self.store.save_periods(self.periods)
        self.refresh_all()
        self.say("Отмечен последний день месячных. " + self._summary_line())

    def _summary_line(self) -> str:
        return engine.summary(self.periods, date.today().isoformat())

    # -------------------------------------------------------------- Календарь

    def _build_calendar(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.month_title = QLabel()
        self.month_title.setAccessibleName("Месяц")
        layout.addWidget(self.month_title)

        row = QHBoxLayout()
        self.button_prev_month = QPushButton("Предыдущий месяц")
        self.button_prev_month.clicked.connect(lambda: self.shift_month(-1))
        self.button_next_month = QPushButton("Следующий месяц")
        self.button_next_month.clicked.connect(lambda: self.shift_month(1))
        self.button_now_month = QPushButton("Текущий месяц")
        self.button_now_month.clicked.connect(self.go_current_month)
        for button in (self.button_prev_month, self.button_next_month, self.button_now_month):
            button.setMinimumHeight(40)
            row.addWidget(button)
        layout.addLayout(row)

        self.month_list = QListWidget()
        self.month_list.setAccessibleName("Дни месяца")
        layout.addWidget(self.month_list, 1)

        for caption, slot in (
            ("Отметить начало месячных в выбранный день", self.mark_selected_start),
            ("Убрать отметку, начавшуюся в выбранный день", self.unmark_selected),
        ):
            button = QPushButton(caption)
            button.setMinimumHeight(40)
            button.clicked.connect(slot)
            layout.addWidget(button)

        return page

    def shift_month(self, delta: int) -> None:
        month = self.month_number + delta
        year = self.month_year
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        self.month_year, self.month_number = year, month
        self.refresh_month()

    def go_current_month(self) -> None:
        today = date.today()
        self.month_year, self.month_number = today.year, today.month
        self.refresh_month()

    def refresh_month(self) -> None:
        title = f"{MONTHS_NOMINATIVE[self.month_number - 1]} {self.month_year}"
        self.month_title.setText(title)
        lines = json.loads(
            engine.month(self.periods, date.today().isoformat(), self.month_year, self.month_number)
        )
        self.month_list.clear()
        for number, line in enumerate(lines, start=1):
            item = QListWidgetItem(line)
            item.setData(Qt.ItemDataRole.UserRole, f"{self.month_year:04d}-{self.month_number:02d}-{number:02d}")
            self.month_list.addItem(item)
        # Курсор сразу на сегодняшний день: листать месяц с первого числа
        # каждый раз — лишняя работа.
        today = date.today()
        if (today.year, today.month) == (self.month_year, self.month_number):
            self.month_list.setCurrentRow(today.day - 1)

    def selected_day(self) -> str | None:
        item = self.month_list.currentItem()
        if item is None:
            self.say("Сначала выбери день в списке.")
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))

    def mark_selected_start(self) -> None:
        day = self.selected_day()
        if day is None:
            return
        updated = engine.mark_start(self.periods, day)
        if updated == self.periods:
            self.say("Начало месячных в этот день уже отмечено.")
            return
        self.periods = updated
        self.store.save_periods(self.periods)
        self.refresh_all()
        self.say(f"Отмечено начало месячных. {_spoken(day)}.")

    def unmark_selected(self) -> None:
        day = self.selected_day()
        if day is None:
            return
        updated = engine.unmark(self.periods, day)
        if updated == self.periods:
            self.say(f"Отметки, начавшейся {_spoken(day)}, нет.")
            return
        self.periods = updated
        self.store.save_periods(self.periods)
        self.refresh_all()
        self.say(f"Отметка за {_spoken(day)} убрана.")

    # ----------------------------------------------------------------- Дневник

    def _build_diary(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)

        form = QFormLayout()
        self.diary_date = QDateEdit(_to_qdate(date.today()))
        self.diary_date.setDisplayFormat("dd.MM.yyyy")
        self.diary_date.setCalendarPopup(False)
        self.diary_date.dateChanged.connect(self.load_diary_day)
        form.addRow("Дата", self.diary_date)

        self.diary_pain = QComboBox()
        for caption, value in PAIN_CHOICES:
            self.diary_pain.addItem(caption, value)
        form.addRow("Боль", self.diary_pain)

        self.diary_mood = QComboBox()
        self.diary_mood.setEditable(True)
        for caption in MOOD_CHOICES:
            self.diary_mood.addItem(caption, caption)
        form.addRow("Настроение", self.diary_mood)

        self.diary_flow = QComboBox()
        for caption in FLOW_CHOICES:
            self.diary_flow.addItem(caption, "" if caption == "не отмечено" else caption)
        form.addRow("Выделения", self.diary_flow)

        self.diary_temp_on = QCheckBox("Измеряла базальную температуру")
        self.diary_temp_on.toggled.connect(self._toggle_temperature)
        form.addRow("", self.diary_temp_on)

        self.diary_temp = QDoubleSpinBox()
        self.diary_temp.setRange(34.00, 42.00)
        self.diary_temp.setSingleStep(0.05)
        self.diary_temp.setDecimals(2)
        self.diary_temp.setValue(36.60)
        self.diary_temp.setEnabled(False)
        form.addRow("Температура", self.diary_temp)

        self.diary_pill = QComboBox()
        for caption, value in PILL_CHOICES:
            self.diary_pill.addItem(caption, value)
        form.addRow("Таблетка", self.diary_pill)

        self.diary_note = QLineEdit()
        self.diary_note.setPlaceholderText("Например: болела голова, пила обезболивающее")
        form.addRow("Заметка", self.diary_note)

        layout.addLayout(form)

        row = QHBoxLayout()
        button_save = QPushButton("Сохранить запись")
        button_save.setMinimumHeight(44)
        button_save.clicked.connect(self.save_diary_day)
        button_clear = QPushButton("Очистить этот день")
        button_clear.setMinimumHeight(44)
        button_clear.clicked.connect(self.clear_diary_day)
        button_summary = QPushButton("Что видно по дневнику")
        button_summary.setMinimumHeight(44)
        button_summary.clicked.connect(self.show_diary_summary)
        for button in (button_save, button_clear, button_summary):
            row.addWidget(button)
        layout.addLayout(row)

        self.diary_view = QPlainTextEdit()
        self.diary_view.setReadOnly(True)
        self.diary_view.setAccessibleName("Записи дневника")
        self.diary_view.setMinimumHeight(180)
        layout.addWidget(self.diary_view)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    def _toggle_temperature(self, enabled: bool) -> None:
        self.diary_temp.setEnabled(enabled)

    def load_diary_day(self) -> None:
        """Показывает, что уже отмечено за выбранный день."""
        day = _from_qdate(self.diary_date.date()).isoformat()
        item = json.loads(engine.diary_day(self.records, day))
        pain = int(item.get("pain") or 0)
        self.diary_pain.setCurrentIndex(max(0, self.diary_pain.findData(pain)))

        mood = str(item.get("mood") or "")
        index = self.diary_mood.findData(mood)
        if index >= 0:
            self.diary_mood.setCurrentIndex(index)
        else:
            self.diary_mood.setEditText(mood)

        flow = str(item.get("flow") or "")
        self.diary_flow.setCurrentIndex(max(0, self.diary_flow.findData(flow)))

        temperature = item.get("temperature")
        self.diary_temp_on.setChecked(temperature is not None)
        if temperature is not None:
            self.diary_temp.setValue(float(temperature))

        pill = item.get("pill")
        self.diary_pill.setCurrentIndex(
            max(0, self.diary_pill.findData(-1 if pill is None else int(bool(pill))))
        )
        self.diary_note.setText(str(item.get("note") or ""))
        self.refresh_diary_view()

    def save_diary_day(self) -> None:
        day = _from_qdate(self.diary_date.date()).isoformat()
        pill = self.diary_pill.currentData()
        self.records = engine.diary_save(
            self.records,
            day,
            pain=int(self.diary_pain.currentData() or 0),
            mood=self.diary_mood.currentText().strip(),
            flow=str(self.diary_flow.currentData() or ""),
            temperature=self.diary_temp.value() if self.diary_temp_on.isChecked() else 0.0,
            pill=int(pill) if pill is not None else -1,
            note=self.diary_note.text().strip(),
        )
        self.store.save_records(self.records)
        self.refresh_diary_view()
        self.say(f"Запись за {_spoken(day)} сохранена.")

    def clear_diary_day(self) -> None:
        day = _from_qdate(self.diary_date.date()).isoformat()
        self.records = engine.diary_clear(self.records, day)
        self.store.save_records(self.records)
        self.load_diary_day()
        self.say(f"Запись за {_spoken(day)} убрана.")

    def show_diary_summary(self) -> None:
        text = engine.diary_summary(self.records, self.periods)
        self.say(text)

    def refresh_diary_view(self) -> None:
        self.diary_view.setPlainText(engine.diary_history(self.records, self.periods))

    # ------------------------------------------------------------------ История

    def _build_history(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.history_view = QPlainTextEdit()
        self.history_view.setReadOnly(True)
        self.history_view.setAccessibleName("История циклов")
        layout.addWidget(self.history_view, 1)

        button_note = QPushButton("Что приложение не делает")
        button_note.setMinimumHeight(44)
        button_note.clicked.connect(self.show_medical_note)
        layout.addWidget(button_note)

        return page

    def show_medical_note(self) -> None:
        text = engine.medical_note()
        self.say(text)
        QMessageBox.information(self, "Важно", text)

    # ----------------------------------------------------------------- Настройки

    def _build_settings(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)

        box = QGroupBox("Напоминания")
        form = QFormLayout(box)

        self.set_days_before = QSpinBox()
        self.set_days_before.setRange(0, 14)
        self.set_days_before.setSuffix(" дней заранее")
        form.addRow("Предупреждать о месячных", self.set_days_before)

        self.set_on_day = QCheckBox("Напоминать в ожидаемый день")
        form.addRow("", self.set_on_day)

        self.set_delay = QSpinBox()
        self.set_delay.setRange(0, 14)
        self.set_delay.setSuffix(" дней задержки")
        form.addRow("Напоминать при задержке", self.set_delay)

        self.set_fertile = QCheckBox("Сообщать о начале фертильных дней")
        form.addRow("", self.set_fertile)

        self.set_pill_on = QCheckBox("Напоминать про таблетку")
        form.addRow("", self.set_pill_on)

        self.set_pill_hour = QSpinBox()
        self.set_pill_hour.setRange(0, 23)
        self.set_pill_hour.setSuffix(" часов")
        form.addRow("Время напоминания о таблетке", self.set_pill_hour)

        self.set_quiet_from = QSpinBox()
        self.set_quiet_from.setRange(0, 23)
        self.set_quiet_from.setSuffix(" часов")
        form.addRow("Тихие часы с", self.set_quiet_from)

        self.set_quiet_to = QSpinBox()
        self.set_quiet_to.setRange(0, 23)
        self.set_quiet_to.setSuffix(" часов")
        form.addRow("Тихие часы до", self.set_quiet_to)

        layout.addWidget(box)

        button_save = QPushButton("Сохранить настройки")
        button_save.setMinimumHeight(44)
        button_save.clicked.connect(self.save_settings)
        layout.addWidget(button_save)

        self.settings_view = QPlainTextEdit()
        self.settings_view.setReadOnly(True)
        self.settings_view.setAccessibleName("Что настроено")
        self.settings_view.setMinimumHeight(90)
        layout.addWidget(self.settings_view)

        text_box = QGroupBox("Показывать")
        text_form = QFormLayout(text_box)
        self.set_large_font = QCheckBox("Крупный шрифт")
        self.set_large_font.toggled.connect(self.apply_font)
        text_form.addRow("", self.set_large_font)
        layout.addWidget(text_box)

        program_box = QGroupBox("Работа программы")
        program_form = QFormLayout(program_box)

        self.set_keep_running = QCheckBox("Продолжать работу, когда окно закрыто")
        self.set_keep_running.setToolTip(
            "Напоминания будут приходить и с закрытым окном. Открыть окно заново — "
            "двойной щелчок по значку рядом с часами."
        )
        self.set_keep_running.toggled.connect(self.save_window_prefs)
        program_form.addRow("", self.set_keep_running)

        self.set_autostart = QCheckBox("Запускать вместе с Windows")
        self.set_autostart.setToolTip(
            "Программа будет ждать в трее с самого включения компьютера, и первое "
            "же напоминание не потеряется."
        )
        self.set_autostart.toggled.connect(self.save_window_prefs)
        if not prefs.autostart_supported():
            # На других системах этой настройки нет; в списке оставляем, но
            # выключенной — чтобы не выглядело, будто она что-то делает.
            self.set_autostart.setEnabled(False)
        program_form.addRow("", self.set_autostart)

        layout.addWidget(program_box)

        data_box = QGroupBox("Данные")
        data_layout = QVBoxLayout(data_box)
        self.data_label = QLabel(f"Файлы лежат в папке: {self.store.directory}")
        self.data_label.setWordWrap(True)
        data_layout.addWidget(self.data_label)

        button_open = QPushButton("Открыть папку с данными")
        button_open.clicked.connect(self.open_data_folder)
        data_layout.addWidget(button_open)

        button_backup = QPushButton("Сохранить резервную копию")
        button_backup.clicked.connect(self.save_backup)
        data_layout.addWidget(button_backup)

        button_restore = QPushButton("Восстановить из копии")
        button_restore.clicked.connect(self.restore_backup)
        data_layout.addWidget(button_restore)
        layout.addWidget(data_box)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return page

    def _load_settings_into_widgets(self) -> None:
        settings = self.settings
        self.set_days_before.setValue(settings.days_before)
        self.set_on_day.setChecked(settings.on_expected_day)
        self.set_delay.setValue(settings.delay_after)
        self.set_fertile.setChecked(settings.fertile_notice)
        self.set_pill_on.setChecked(settings.pill_enabled)
        self.set_pill_hour.setValue(settings.pill_hour)
        self.set_quiet_from.setValue(settings.quiet_from)
        self.set_quiet_to.setValue(settings.quiet_to)

        # Настройки окна лежат отдельно от напоминаний и живут в своих
        # переключателях. Сигналы глушим: заполнение полей — не решение
        # пользовательницы, сохранять его не нужно.
        for widget, value in (
            (self.set_keep_running, self.prefs["keep_running"]),
            (self.set_autostart, prefs.is_autostart_on()),
        ):
            blocked = widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(blocked)

    def save_window_prefs(self) -> None:
        """Настройки окна сохраняются сразу — у них нет своей кнопки.

        Проверить автозапуск важнее, чем сохранить галочку: если Windows не
        дала прописать себя в автозагрузку, честнее вернуть переключатель
        назад и сказать об этом, чем показывать включённым то, чего нет.
        """
        wanted = self.set_autostart.isChecked()
        if wanted != prefs.is_autostart_on():
            try:
                prefs.set_autostart(wanted)
            except OSError as error:
                blocked = self.set_autostart.blockSignals(True)
                self.set_autostart.setChecked(not wanted)
                self.set_autostart.blockSignals(blocked)
                _read_aloud(self.set_autostart, f"Не получилось: {error}")
                return

        self.prefs["keep_running"] = self.set_keep_running.isChecked()
        self.prefs["autostart"] = wanted
        prefs.save(self.store, self.prefs)

        left_running = self.prefs["keep_running"]
        _read_aloud(
            self.set_keep_running,
            "Сохранила. " + (
                "Окно можно закрывать: напоминания всё равно придут, а открыть "
                "программу заново — двойной щелчок по значку рядом с часами."
                if left_running
                else "Закрытие окна выключает программу, и напоминания до "
                     "следующего запуска молчат."
            ),
        )

    def save_settings(self) -> None:
        self.settings = ReminderSettings(
            days_before=self.set_days_before.value(),
            on_expected_day=self.set_on_day.isChecked(),
            delay_after=self.set_delay.value(),
            fertile_notice=self.set_fertile.isChecked(),
            pill_enabled=self.set_pill_on.isChecked(),
            pill_hour=self.set_pill_hour.value(),
            quiet_from=self.set_quiet_from.value(),
            quiet_to=self.set_quiet_to.value(),
        )
        self.store.save_settings(engine.settings_to_json(self.settings))
        self.refresh_settings_view()
        self.say("Настройки сохранены. " + self._next_reminder_line())

    def refresh_settings_view(self) -> None:
        self.settings_view.setPlainText(self._next_reminder_line())

    def _next_reminder_line(self) -> str:
        items = json.loads(
            engine.reminders_json(
                self.periods,
                self.records,
                date.today().isoformat(),
                engine.settings_to_json(self.settings),
                horizon_days=30,
            )
        )
        if not items:
            return "Напоминаний пока не будет: либо всё выключено, либо мало данных для прогноза."
        first = items[0]
        return f"Ближайшее напоминание — {_spoken(first['day'])}: {first['text']}"

    def apply_font(self, large: bool) -> None:
        size = LARGE_FONT_POINT_SIZE if large else NORMAL_FONT_POINT_SIZE
        font = QFont()
        font.setPointSize(size)
        QApplication.instance().setFont(font)

    def open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.directory)))

    def save_backup(self) -> None:
        default_name = f"Календарь дней — копия {date.today().isoformat()}.json"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить копию", default_name, "Файлы копий (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(self.store.backup_text(), encoding="utf-8")
        except OSError as error:
            self.say(f"Не удалось сохранить копию: {error}")
            return
        self.say(f"Копия сохранена в файл {path}")

    def restore_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать копию", "", "Файлы копий (*.json)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            report = self.store.restore_text(text)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            self.say(f"Копия не подошла: {error}")
            return
        self.periods = self.store.periods_text()
        self.records = self.store.records_text()
        self.settings = engine.settings_from_json(self.store.settings_text())
        self.refresh_all()
        self.say(report)

    # ------------------------------------------------------------ Напоминания

    def check_reminders(self) -> None:
        """Показывает напоминания, время которых уже пришло."""
        today = date.today().isoformat()
        hour = datetime.now().hour
        items = json.loads(
            engine.reminders_json(
                self.periods,
                self.records,
                today,
                engine.settings_to_json(self.settings),
                horizon_days=1,
            )
        )
        for item in items:
            if item["key"] in self.shown or item["day"] != today or hour < item["hour"]:
                continue
            self.shown.add(item["key"])
            self.store.save_shown(self.shown)
            if not self.isVisible():
                # Окно свёрнуто в трей: напоминание поднимает его обратно.
                # Иначе окно с сообщением оказалось бы без родителя на экране,
                # и диктор мог его не прочитать.
                self._show_from_tray()
            self.say(item["text"])
            QMessageBox.information(self, "Напоминание", item["text"])

    # -------------------------------------------------------------- Обновление

    def refresh_all(self) -> None:
        self.summary.setPlainText(self._summary_line())
        state = json.loads(engine.state(self.periods))
        self.button_period_end.setEnabled(bool(state["open"]))
        self.history_view.setPlainText(engine.history(self.periods))
        self.refresh_month()
        self.load_diary_day()
        self.refresh_diary_view()
        self._load_settings_into_widgets()
        self.refresh_settings_view()


def _spoken(iso: str) -> str:
    """«26 марта» вместо «2026-03-26» — так дата читается диктором понятнее."""
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        return iso
    months = (
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    return f"{day.day} {months[day.month - 1]}"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Календарь дней")
    app.setWindowIcon(_app_icon())
    font = QFont()
    font.setPointSize(NORMAL_FONT_POINT_SIZE)
    app.setFont(font)

    window = MainWindow(Store())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
