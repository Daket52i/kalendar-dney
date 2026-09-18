package org.djdancho.calendar

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.util.Calendar
import java.util.concurrent.Executors

/**
 * Экран «Сегодня» и календарь месяца.
 *
 * Правило доступности, по которому всё сделано: любой вывод приложения —
 * это текст, который TalkBack читает целиком. Цвета и картинки ничего не
 * значат, потому что их здесь нет. Расчёты и формулировки приходят из ядра
 * на Python, экран только показывает и озвучивает.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var todayText: TextView
    private lateinit var monthTitle: TextView
    private lateinit var monthPanel: LinearLayout
    private lateinit var contentScroll: ScrollView
    private lateinit var monthList: ListView
    private lateinit var monthAdapter: ArrayAdapter<String>
    private val monthLines = ArrayList<String>()

    private val store by lazy { PeriodStore(this) }
    private val engine by lazy { CycleEngine(this) }

    /** Работа с ядром — в отдельном потоке: даже быстрый вызов не должен
     *  подвешивать озвучку интерфейса. */
    private val worker = Executors.newSingleThreadExecutor()

    private val monthCursor: Calendar = Calendar.getInstance()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        todayText = findViewById(R.id.todayText)
        monthPanel = findViewById(R.id.monthPanel)
        monthTitle = findViewById(R.id.monthTitle)
        contentScroll = findViewById(R.id.contentScroll)
        monthList = findViewById(R.id.monthList)

        monthAdapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, monthLines)
        monthList.adapter = monthAdapter

        findViewById<Button>(R.id.btnStart).setOnClickListener { markStart() }
        findViewById<Button>(R.id.btnFinish).setOnClickListener { markFinish() }
        findViewById<Button>(R.id.btnMonth).setOnClickListener { showMonth() }
        findViewById<Button>(R.id.btnDiary).setOnClickListener {
            startActivity(Intent(this, DiaryActivity::class.java))
        }
        findViewById<Button>(R.id.btnSettings).setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        findViewById<Button>(R.id.btnHistory).setOnClickListener { showHistory() }
        findViewById<Button>(R.id.btnNote).setOnClickListener { showMedicalNote() }
        findViewById<Button>(R.id.btnPrevMonth).setOnClickListener { shiftMonth(-1) }
        findViewById<Button>(R.id.btnNextMonth).setOnClickListener { shiftMonth(1) }
        findViewById<Button>(R.id.btnBack).setOnClickListener { hideMonth() }

        // Проверка напоминаний ставится при каждом запуске: так она переживёт
        // перезагрузку телефона, а повторный вызов ничего не ломает.
        ReminderScheduler.schedule(this)
    }

    override fun onResume() {
        super.onResume()
        // Сводку считаем здесь, а не в onCreate: onResume приходит и после
        // возвращения с дневника или настроек, где данные могли поменяться.
        refreshToday()
    }

    override fun onDestroy() {
        worker.shutdown()
        super.onDestroy()
    }

    // ---------- Экран «Сегодня» ----------

    private fun refreshToday() {
        val today = Dates.todayIso()
        worker.execute {
            val text = try {
                engine.summary(store.read(), today)
            } catch (e: Exception) {
                "Не получилось посчитать: ${e.message}"
            }
            val reminder = try {
                dueToSpeak(today)
            } catch (e: Exception) {
                null
            }
            runOnUiThread {
                // Напоминание — первым: сводка ляжет в живой регион и
                // дочитается сама, а напоминание ждать не должно.
                if (reminder != null) Speech.announce(this, reminder)
                todayText.text = text
            }
        }
    }

    /**
     * Напоминание, которое человек ещё не слышал.
     *
     * Уведомление нарочно без подробностей, поэтому весь текст живёт здесь:
     * приложение говорит его вслух при открытии и помечает сказанным, чтобы
     * не повторяться. Если одного и того же за день накопилось несколько
     * (таблетка за три дня), оставляем только самое свежее.
     */
    private fun dueToSpeak(today: String): String? {
        val cutoff = Dates.isoDaysAgo(Reminders.LOOK_BACK_DAYS)
        val due = Reminders.due(
            reminders = Reminders.all(this, engine),
            todayIso = today,
            hour = Dates.hourNow(),
            notBeforeIso = cutoff,
            shown = Reminders.spoken(this).read()
        )
        if (due.isEmpty()) return null

        val store = Reminders.spoken(this)
        due.forEach { store.add(it.key, cutoff) }
        val freshest = due.groupBy { it.kind }.map { it.value.last() }.sortedBy { it.day }
        return freshest.joinToString(" ") { it.text }
    }

    private fun markStart() {
        val today = Dates.todayIso()
        worker.execute {
            val before = store.read()
            val after = engine.markStart(before, today)
            val saved = store.write(after)
            val unchanged = after == before
            runOnUiThread {
                when {
                    !saved -> Speech.announce(this, getString(R.string.error_save))
                    unchanged -> Speech.announce(this, getString(R.string.marked_start_twice))
                    else -> Speech.announce(this, getString(R.string.marked_start))
                }
                refreshToday()
            }
        }
    }

    private fun markFinish() {
        val today = Dates.todayIso()
        worker.execute {
            val before = store.read()
            val open = engine.hasOpenPeriod(before)
            val after = engine.markEnd(before, today)
            val saved = store.write(after)
            runOnUiThread {
                when {
                    !saved -> Speech.announce(this, getString(R.string.error_save))
                    !open -> Speech.announce(this, getString(R.string.marked_finish_none))
                    else -> Speech.announce(this, getString(R.string.marked_finish))
                }
                refreshToday()
            }
        }
    }

    // ---------- Календарь месяца ----------

    private fun showMonth() {
        val today = Dates.todayIso()
        val year = monthCursor.get(Calendar.YEAR)
        val month = monthCursor.get(Calendar.MONTH) + 1
        worker.execute {
            val lines = try {
                engine.month(store.read(), today, year, month)
            } catch (e: Exception) {
                listOf("Не получилось показать календарь: ${e.message}")
            }
            runOnUiThread {
                monthLines.clear()
                monthLines.addAll(lines)
                monthAdapter.notifyDataSetChanged()
                monthTitle.text = monthTitle(year, month)
                monthPanel.visibility = View.VISIBLE
                contentScroll.visibility = View.GONE
                monthTitle.requestFocus()
            }
        }
    }

    private fun shiftMonth(delta: Int) {
        monthCursor.add(Calendar.MONTH, delta)
        showMonth()
    }

    private fun hideMonth() {
        monthPanel.visibility = View.GONE
        contentScroll.visibility = View.VISIBLE
        todayText.requestFocus()
        refreshToday()
    }

    private fun monthTitle(year: Int, month: Int): String {
        val names = arrayOf(
            "январь", "февраль", "март", "апрель", "май", "июнь",
            "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
        )
        return "${names[month - 1]} $year"
    }

    // ---------- Справочные экраны ----------

    private fun showHistory() {
        worker.execute {
            val text = try {
                engine.history(store.read())
            } catch (e: Exception) {
                "Не получилось собрать историю: ${e.message}"
            }
            runOnUiThread {
                todayText.text = text
                Speech.announce(this, "История циклов.")
            }
        }
    }

    private fun showMedicalNote() {
        worker.execute {
            val text = try {
                engine.medicalNote()
            } catch (e: Exception) {
                "Не получилось прочитать предупреждение: ${e.message}"
            }
            runOnUiThread {
                todayText.text = text
                Speech.announce(this, "Важное предупреждение.")
            }
        }
    }

}
