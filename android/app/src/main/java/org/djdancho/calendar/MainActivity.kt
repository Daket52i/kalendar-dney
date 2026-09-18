package org.djdancho.calendar

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.dialog.MaterialAlertDialogBuilder
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

    /** Имя открытого человека. Обновляется в onResume: с экрана «Люди» можно
     *  вернуться уже с другим календарём. Пишется из рабочего потока, читается
     *  из потока интерфейса — отсюда volatile. */
    @Volatile
    private var person: String = ""

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

        // Список людей спрашиваем до всего остального: любое обращение к
        // файлам создаёт папку первого человека, и после этого «первый запуск»
        // уже не отличить от обычного.
        val firstRun = People.isFirstRun(this)

        findViewById<Button>(R.id.btnPeople).setOnClickListener {
            startActivity(Intent(this, PeopleActivity::class.java))
        }
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

        // Диалог показываем после того, как экран отрисован: иначе TalkBack
        // начинает читать его поверх ещё не построенного окна.
        if (firstRun) findViewById<View>(R.id.todayText).post { askNameOnFirstRun() }
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
            // Имя перечитываем здесь же: с экрана «Люди» возвращаются уже с
            // другим календарём, и все фразы должны сменить имя вместе с ним.
            person = currentPerson()
            val text = try {
                engine.summary(store.read(), today, person)
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

    /** Имя открытого человека. Молчаливая пустая строка — лучше падения
     *  экрана: без имени фразы просто звучат как раньше. */
    private fun currentPerson(): String = try {
        People.currentName(this)
    } catch (e: Exception) {
        ""
    }

    /** Проговорить фразу от имени открытого человека — через Say, чтобы имя
     *  нельзя было забыть незаметно. */
    private fun say(text: String) = Say.aloud(this, engine, person, text)

    /**
     * Напоминания, которых человек ещё не слышал, — по всем календарям.
     *
     * Уведомление нарочно без подробностей, поэтому весь текст живёт здесь:
     * приложение говорит его вслух при открытии и помечает сказанным, чтобы
     * не повторяться. Каждое напоминание приходит из ядра уже с именем того,
     * чьё оно, — поэтому в одной фразе могут спокойно встретиться мама и дочь
     * и не перепутаться.
     *
     * Если одного и того же за день накопилось несколько (таблетка за три дня),
     * оставляем только самое свежее — по каждому человеку отдельно.
     */
    private fun dueToSpeak(today: String): String? {
        val cutoff = Dates.isoDaysAgo(Reminders.LOOK_BACK_DAYS)
        val hour = Dates.hourNow()
        val phrases = ArrayList<String>()

        Reminders.allByPerson(this, engine, People.people(this, engine)).forEach { belonging ->
            val store = Reminders.spoken(this, belonging.person.id)
            val due = Reminders.due(
                reminders = belonging.reminders,
                todayIso = today,
                hour = hour,
                notBeforeIso = cutoff,
                shown = store.read()
            )
            if (due.isEmpty()) return@forEach
            due.forEach { store.add(it.key, cutoff) }
            phrases += due.groupBy { it.kind }
                .map { it.value.last() }
                .sortedBy { it.day }
                .map { it.text }
        }

        return if (phrases.isEmpty()) null else phrases.joinToString(" ")
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
                    !saved -> say(getString(R.string.error_save))
                    unchanged -> say(getString(R.string.marked_start_twice))
                    else -> say(getString(R.string.marked_start))
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
                    !saved -> say(getString(R.string.error_save))
                    !open -> say(getString(R.string.marked_finish_none))
                    else -> say(getString(R.string.marked_finish))
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
            person = currentPerson()
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

    /**
     * Заголовок месяца. Имя человека здесь обязательно: дни месяца читаются
     * свайпом без имени в каждой строке, и без подписи в заголовке непонятно,
     * чей это календарь.
     */
    private fun monthTitle(year: Int, month: Int): String {
        val names = arrayOf(
            "январь", "февраль", "март", "апрель", "май", "июнь",
            "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
        )
        val title = "${names[month - 1]} $year"
        return if (person.isEmpty()) title else "$person — $title"
    }

    // ---------- Справочные экраны ----------

    private fun showHistory() {
        worker.execute {
            person = currentPerson()
            val text = try {
                engine.history(store.read(), person)
            } catch (e: Exception) {
                "Не получилось собрать историю: ${e.message}"
            }
            runOnUiThread {
                todayText.text = text
                say("История циклов.")
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
                // Предупреждение одно на всех — имя человека в нём было бы
                // шумом, который мешает слушать.
                Speech.announce(this, "Важное предупреждение.")
            }
        }
    }

    // ---------- Первый запуск ----------

    /**
     * Спрашивает имя при первом запуске и переименовывает единственный
     * календарь — новый не заводится.
     *
     * Так «Я» не остаётся навсегда рядом с настоящим именем: в первый раз
     * человек называет свой календарь, а второй заводит уже осознанно, с
     * экрана «Люди».
     */
    private fun askNameOnFirstRun() {
        val input = EditText(this)
        input.hint = getString(R.string.people_first_run_hint)
        input.isSingleLine = true
        val density = resources.displayMetrics.density
        val field = LinearLayout(this)
        field.setPadding((24 * density).toInt(), (8 * density).toInt(), (24 * density).toInt(), 0)
        field.addView(
            input,
            LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        )

        MaterialAlertDialogBuilder(this)
            .setTitle(getString(R.string.people_first_run_title))
            .setMessage(getString(R.string.people_first_run_message))
            .setView(field)
            .setPositiveButton(getString(R.string.people_first_run_save)) { _, _ ->
                renameTo(input.text.toString())
            }
            .setNegativeButton(getString(R.string.people_first_run_later), null)
            .show()
    }

    /** Отмены здесь нет: пустое имя ядро не примет, и это правильно — молча
     *  оставить человека без имени хуже, чем переспросить. */
    private fun renameTo(name: String) {
        worker.execute {
            val error = try {
                val id = People.currentId(this)
                People.rename(this, engine, id, name)
            } catch (e: Exception) {
                getString(R.string.error_people)
            }
            val current = currentPerson()
            runOnUiThread {
                if (error.isNotEmpty()) {
                    say(error)
                    return@runOnUiThread
                }
                say(getString(R.string.people_first_run_saved, current))
                refreshToday()
            }
        }
    }

}
