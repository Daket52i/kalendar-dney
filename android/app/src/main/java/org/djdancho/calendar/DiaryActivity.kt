package org.djdancho.calendar

import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ListView
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.util.Calendar
import java.util.concurrent.Executors

/**
 * Дневник самочувствия: запись на каждый день.
 *
 * Заполнять ничего не обязательно — пустой день это норма, а не пропуск.
 * Все значения уходят в ядро как есть; что с ними делать, решает Python, а
 * не этот экран. Тексты тоже приходят оттуда — здесь их не сочиняют.
 */
class DiaryActivity : AppCompatActivity() {

    private lateinit var dateLabel: TextView
    private lateinit var painSpinner: Spinner
    private lateinit var moodSpinner: Spinner
    private lateinit var flowSpinner: Spinner
    private lateinit var pillSpinner: Spinner
    private lateinit var tempOn: CheckBox
    private lateinit var tempValue: EditText
    private lateinit var noteValue: EditText
    private lateinit var summaryText: TextView
    private lateinit var formScroll: ScrollView
    private lateinit var listPanel: View
    private lateinit var listView: ListView
    private lateinit var listAdapter: ArrayAdapter<String>
    private val listLines = ArrayList<String>()

    private val store by lazy { DiaryStore(this) }
    private val periods by lazy { PeriodStore(this) }
    private val engine by lazy { CycleEngine(this) }
    private val worker = Executors.newSingleThreadExecutor()

    /** Открытый сейчас день. Время суток не нужно — только дата. */
    private val dayCursor: Calendar = Calendar.getInstance()

    /** Что уже записано за этот день: по нему заполняются поля. */
    private var current: JSONObject = JSONObject()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_diary)

        dateLabel = findViewById(R.id.diaryDate)
        painSpinner = findViewById(R.id.diaryPain)
        moodSpinner = findViewById(R.id.diaryMood)
        flowSpinner = findViewById(R.id.diaryFlow)
        pillSpinner = findViewById(R.id.diaryPill)
        tempOn = findViewById(R.id.diaryTempOn)
        tempValue = findViewById(R.id.diaryTemp)
        noteValue = findViewById(R.id.diaryNote)
        summaryText = findViewById(R.id.diarySummaryText)
        formScroll = findViewById(R.id.diaryScroll)
        listPanel = findViewById(R.id.diaryListPanel)
        listView = findViewById(R.id.diaryList)

        listAdapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, listLines)
        listView.adapter = listAdapter

        fill(painSpinner, R.array.diary_pain_choices)
        fill(moodSpinner, R.array.diary_mood_choices)
        fill(flowSpinner, R.array.diary_flow_choices)
        fill(pillSpinner, R.array.diary_pill_choices)

        tempOn.setOnCheckedChangeListener { _, checked ->
            tempValue.isEnabled = checked
            if (!checked) tempValue.setText("")
        }

        findViewById<Button>(R.id.diaryPrevDay).setOnClickListener { shiftDay(-1) }
        findViewById<Button>(R.id.diaryNextDay).setOnClickListener { shiftDay(1) }
        findViewById<Button>(R.id.diaryToday).setOnClickListener { goToday() }
        findViewById<Button>(R.id.diarySave).setOnClickListener { save() }
        findViewById<Button>(R.id.diaryClear).setOnClickListener { clear() }
        findViewById<Button>(R.id.diarySummaryBtn).setOnClickListener { showSummary() }
        findViewById<Button>(R.id.diaryShowList).setOnClickListener { showList() }
        findViewById<Button>(R.id.diaryBack).setOnClickListener { hideList() }

        load()
    }

    override fun onDestroy() {
        worker.shutdown()
        super.onDestroy()
    }

    // ---------- Заполнение полей ----------

    private fun fill(spinner: Spinner, arrayId: Int) {
        val adapter = ArrayAdapter(
            this, android.R.layout.simple_spinner_item,
            resources.getStringArray(arrayId).toList()
        )
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinner.adapter = adapter
    }

    /**
     * Читает запись за открытый день и раскладывает её по полям.
     *
     * `announceDay` выключается после сохранения: там уже сказано «запись
     * сохранена», и вторая фраза про дату только перебила бы первую.
     */
    private fun load(announceDay: Boolean = true) {
        val day = Dates.iso(dayCursor)
        worker.execute {
            try {
                val label = engine.dayLabel(day)
                val record = engine.diaryDay(store.read(), day)
                runOnUiThread {
                    current = record
                    dateLabel.text = label
                    if (announceDay) Speech.announce(this, label)
                    showFields(record)
                }
            } catch (e: Exception) {
                runOnUiThread {
                    Speech.announce(this, "Не получилось открыть день: ${e.message}")
                }
            }
        }
    }

    private fun showFields(record: JSONObject) {
        // Списки выбора уже заполнены; если адаптер почему-то пуст, лучше
        // оставить поля как есть, чем упасть на выборе пункта.
        if (painSpinner.count == 0) return

        painSpinner.setSelection(record.optInt("pain", 0).coerceIn(0, painSpinner.count - 1))
        moodSpinner.setSelection(positionOf(moodSpinner, record.optString("mood")))
        flowSpinner.setSelection(positionOf(flowSpinner, record.optString("flow")))
        pillSpinner.setSelection(
            when {
                !record.has("pill") -> 0
                record.optBoolean("pill") -> 1
                else -> 2
            }
        )

        val temperature = if (record.has("temperature")) record.optDouble("temperature") else 0.0
        tempOn.isChecked = temperature > 0
        tempValue.isEnabled = temperature > 0
        tempValue.setText(if (temperature > 0) String.format(java.util.Locale.US, "%.2f", temperature) else "")

        noteValue.setText(record.optString("note"))
    }

    /** Номер выбранного пункта по его слову. Ноль — «не отмечено». */
    private fun positionOf(spinner: Spinner, word: String): Int {
        if (word.isEmpty()) return 0
        for (index in 0 until spinner.count) {
            if (spinner.getItemAtPosition(index).toString() == word) return index
        }
        return 0
    }

    // ---------- Листание дней ----------

    private fun shiftDay(delta: Int) {
        val next = dayCursor.clone() as Calendar
        next.add(Calendar.DAY_OF_MONTH, delta)

        // Сравниваем даты строками, а не временем: в ISO-виде «2026-09-18»
        // старше «2026-09-19» и как текст, а со временем суток легко
        // ошибиться вечером и не пустить в сегодняшний день.
        if (Dates.iso(next) > Dates.todayIso()) {
            // Записывать «наперёд» нечего: дневник — про то, что уже было.
            Speech.announce(this, getString(R.string.diary_no_future))
            return
        }
        dayCursor.time = next.time
        load()
    }

    private fun goToday() {
        dayCursor.time = Calendar.getInstance().time
        load()
    }

    // ---------- Сохранение ----------

    private fun save() {
        // Значения читаем на главном потоке: поля экрана из чужого потока
        // читать нельзя.
        val temperature = temperature()
        if (temperature < 0) {
            Speech.announce(this, getString(R.string.error_temperature))
            return
        }

        val day = Dates.iso(dayCursor)
        val pain = painSpinner.selectedItemPosition
        val mood = word(moodSpinner)
        val flow = word(flowSpinner)
        val note = noteValue.text.toString().trim()
        val pill = when (pillSpinner.selectedItemPosition) {
            1 -> 1
            2 -> 0
            else -> -1
        }

        worker.execute {
            val saved = engine.diarySave(
                store.read(), day, pain, mood, flow, temperature, pill, note
            )
            val ok = store.write(saved)
            runOnUiThread {
                Speech.announce(
                    this,
                    if (ok) getString(R.string.diary_saved) else getString(R.string.error_save)
                )
                if (ok) load(announceDay = false)
            }
        }
    }

    /**
     * Температура из поля. Ноль — «не измеряла», минус единица — «написано
     * что-то непонятное»: молча потерять число хуже, чем переспросить.
     */
    private fun temperature(): Double {
        if (!tempOn.isChecked) return 0.0
        val raw = tempValue.text.toString().trim().replace(',', '.')
        if (raw.isEmpty()) return 0.0
        val value = raw.toDoubleOrNull() ?: return -1.0
        return if (value in 34.0..42.0) value else -1.0
    }

    /** Слово выбранного пункта; у первого пункта («не отмечено») слова нет. */
    private fun word(spinner: Spinner): String =
        if (spinner.selectedItemPosition == 0) "" else spinner.selectedItem.toString()

    private fun clear() {
        val day = Dates.iso(dayCursor)
        val wasEmpty = current.length() == 0
        worker.execute {
            val cleared = engine.diaryClear(store.read(), day)
            val ok = store.write(cleared)
            runOnUiThread {
                val phrase = when {
                    !ok -> getString(R.string.error_save)
                    wasEmpty -> getString(R.string.diary_nothing_to_clear)
                    else -> getString(R.string.diary_cleared)
                }
                Speech.announce(this, phrase)
                if (ok) load(announceDay = false)
            }
        }
    }

    // ---------- Итоги и список ----------

    private fun showSummary() {
        worker.execute {
            val text = try {
                engine.diarySummary(store.read(), periods.read())
            } catch (e: Exception) {
                "Не получилось посчитать: ${e.message}"
            }
            runOnUiThread {
                summaryText.text = text
                Speech.announce(this, text)
            }
        }
    }

    private fun showList() {
        worker.execute {
            val lines = try {
                engine.diaryHistoryLines(store.read(), periods.read())
            } catch (e: Exception) {
                listOf("Не получилось собрать записи: ${e.message}")
            }
            runOnUiThread {
                listLines.clear()
                listLines.addAll(lines)
                listAdapter.notifyDataSetChanged()
                formScroll.visibility = View.GONE
                listPanel.visibility = View.VISIBLE
                findViewById<TextView>(R.id.diaryListTitle).requestFocus()
            }
        }
    }

    private fun hideList() {
        listPanel.visibility = View.GONE
        formScroll.visibility = View.VISIBLE
        dateLabel.requestFocus()
    }
}
