package org.djdancho.calendar

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONArray
import org.json.JSONObject

/**
 * Одно напоминание: когда сказать и что именно.
 *
 * Текст приходит из ядра уже готовым — Kotlin его не сочиняет.
 */
data class Reminder(val day: String, val hour: Int, val kind: String, val text: String) {
    /** Ключ «это напоминание уже показывали»: день и вид. */
    val key: String get() = "$day:$kind"
}

/**
 * Мост к ядру календаря на Python.
 *
 * Все расчёты и все тексты живут в cycle_core — здесь только вызов. Логику в
 * Kotlin не дублируем: иначе телефон и компьютер разойдутся в поведении, и
 * проверять придётся дважды.
 */
class CycleEngine(context: Context) {

    private val appContext = context.applicationContext

    /** Python поднимается один раз на всё приложение, при первом обращении. */
    private fun start() {
        if (!Python.isStarted()) Python.start(AndroidPlatform(appContext))
    }

    private val module: PyObject by lazy {
        start()
        Python.getInstance().getModule("cycle_engine")
    }

    /** Ядро напрямую: часть вызовов в обёртку не попала, и дублировать её
     *  ради красоты не стоит — ядро и так одно на обе платформы. */
    private val core: PyObject by lazy {
        start()
        Python.getInstance().getModule("cycle_core.engine")
    }

    // ---------- Люди ----------

    /**
     * Список людей и кто выбран сейчас. Ответ всегда одной формы: годный
     * список, имя текущего и — если действие не прошло — ошибка словами.
     */
    fun people(document: String): JSONObject =
        JSONObject(module.callAttr("people_json", document).toString())

    fun personAdd(document: String, name: String): JSONObject =
        JSONObject(module.callAttr("person_add", document, name).toString())

    fun personRename(document: String, id: String, name: String): JSONObject =
        JSONObject(module.callAttr("person_rename", document, id, name).toString())

    fun personRemove(document: String, id: String): JSONObject =
        JSONObject(module.callAttr("person_remove", document, id).toString())

    fun personSwitch(document: String, id: String): JSONObject =
        JSONObject(module.callAttr("person_switch", document, id).toString())

    /**
     * Ставит перед фразой имя человека.
     *
     * Правило живёт в ядре, а не здесь: иначе оно разошлось бы с версией для
     * Windows, и одна из оболочек однажды заговорила бы безымянно.
     */
    fun signed(personName: String, text: String): String =
        module.callAttr("signed", personName, text).toString()

    /** Сводка для экрана «Сегодня». Имя человека — часть фразы, не украшение. */
    fun summary(periodsJson: String, todayIso: String, personName: String): String =
        module.callAttr("summary", periodsJson, todayIso, personName).toString()

    /** Дни месяца: по строке на день, каждая читается голосом целиком. */
    fun month(periodsJson: String, todayIso: String, year: Int, month: Int): List<String> {
        val raw = module.callAttr("month", periodsJson, todayIso, year, month).toString()
        val array = JSONArray(raw)
        return (0 until array.length()).map { array.getString(it) }
    }

    /** История циклов — то, что показывают врачу. */
    fun history(periodsJson: String, personName: String): String =
        module.callAttr("history", periodsJson, personName).toString()

    /** Отметка «начались». Возвращает новую историю. */
    fun markStart(periodsJson: String, dayIso: String): String =
        module.callAttr("mark_start", periodsJson, dayIso).toString()

    /** Отметка «закончились». Возвращает новую историю. */
    fun markEnd(periodsJson: String, dayIso: String): String =
        module.callAttr("mark_end", periodsJson, dayIso).toString()

    /** Убирает отметку, начавшуюся в этот день, — ошибиться может каждый. */
    fun unmark(periodsJson: String, dayIso: String): String =
        core.callAttr("unmark", periodsJson, dayIso).toString()

    /** Есть ли незакрытая отметка — от этого зависят подсказки на экране. */
    fun hasOpenPeriod(periodsJson: String): Boolean {
        val raw = module.callAttr("state", periodsJson).toString()
        return JSONObject(raw).optBoolean("open", false)
    }

    /** Важное предупреждение: приложение не защищает от беременности. */
    fun medicalNote(): String = module.callAttr("medical_note").toString()

    // ---------- Дневник ----------

    /** Название дня словами: «пятница, 18 сентября 2026 года». */
    fun dayLabel(dayIso: String): String =
        core.callAttr("day_label", dayIso).toString()

    /** Что уже отмечено за день. Пустой объект — день не заполнен. */
    fun diaryDay(recordsJson: String, dayIso: String): JSONObject =
        JSONObject(core.callAttr("diary_day", recordsJson, dayIso).toString())

    /**
     * Сохраняет день. Ноль и пустая строка означают «не отмечено» —
     * так договорились с ядром, чтобы не передавать через границу пустоту.
     */
    fun diarySave(
        recordsJson: String,
        dayIso: String,
        pain: Int,
        mood: String,
        flow: String,
        temperature: Double,
        pill: Int,
        note: String
    ): String = core.callAttr(
        "diary_save", recordsJson, dayIso, pain, mood, flow, temperature, pill, note
    ).toString()

    /** Убирает запись за день целиком. */
    fun diaryClear(recordsJson: String, dayIso: String): String =
        core.callAttr("diary_clear", recordsJson, dayIso).toString()

    /** Записи списком, свежие сверху. */
    fun diaryHistory(recordsJson: String, periodsJson: String, personName: String): String =
        core.callAttr("diary_history", recordsJson, periodsJson, HISTORY_LIMIT, personName)
            .toString()

    /**
     * То же списком по строкам: каждая запись — отдельная строка экрана.
     *
     * Имени здесь нет намеренно: строки листают свайпом одну за другой, и
     * «Настя» в начале каждой — это сорок одинаковых слов подряд. Имя несёт
     * заголовок списка.
     */
    fun diaryHistoryLines(recordsJson: String, periodsJson: String): List<String> {
        val raw = core.callAttr(
            "diary_history_json", recordsJson, periodsJson, HISTORY_LIMIT
        ).toString()
        val array = JSONArray(raw)
        return (0 until array.length()).map { array.getString(it) }
    }

    /** Что видно по дневнику за всё время. */
    fun diarySummary(recordsJson: String, periodsJson: String, personName: String): String =
        core.callAttr("diary_summary", recordsJson, periodsJson, personName).toString()

    // ---------- Настройки и напоминания ----------

    /** Приводит настройки к известному виду: чужие поля отбрасываются,
     *  битые значения заменяются умолчаниями. */
    fun settings(raw: String): JSONObject {
        val normalized = core.callAttr("settings_from_json", raw)
        val json = core.callAttr("settings_to_json", normalized).toString()
        return JSONObject(json)
    }

    /** Напоминания на ближайшие дни. */
    fun reminders(
        periodsJson: String,
        recordsJson: String,
        todayIso: String,
        settingsJson: String,
        horizonDays: Int,
        personName: String
    ): List<Reminder> {
        val raw = core.callAttr(
            "reminders_json", periodsJson, recordsJson, todayIso, settingsJson, horizonDays,
            personName
        ).toString()
        val array = JSONArray(raw)
        return (0 until array.length()).map { index ->
            val item = array.getJSONObject(index)
            Reminder(
                day = item.getString("day"),
                hour = item.getInt("hour"),
                kind = item.getString("kind"),
                text = item.getString("text")
            )
        }
    }

    /** Те же напоминания строками — по строке на напоминание, для экрана. */
    fun reminderLines(
        periodsJson: String,
        recordsJson: String,
        todayIso: String,
        settingsJson: String,
        limit: Int,
        personName: String
    ): List<String> {
        val raw = core.callAttr(
            "reminders_lines", periodsJson, recordsJson, todayIso, settingsJson, limit,
            personName
        ).toString()
        val array = JSONArray(raw)
        return (0 until array.length()).map { array.getString(it) }
    }

    private companion object {
        /** Сколько записей дневника показывать. Больше всё равно не листают. */
        const val HISTORY_LIMIT = 60
    }
}
