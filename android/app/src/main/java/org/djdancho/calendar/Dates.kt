package org.djdancho.calendar

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * Даты в том виде, в каком их понимает ядро: ISO, «2026-09-18».
 *
 * Формат создаётся на каждый вызов намеренно. SimpleDateFormat не умеет
 * работать из нескольких потоков сразу, а мы зовём его и с главного, и с
 * фонового — общий экземпляр однажды вернул бы мусор вместо даты.
 */
object Dates {

    fun todayIso(): String = iso(Date())

    fun iso(date: Date): String = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(date)

    fun iso(calendar: Calendar): String = iso(calendar.time)

    /** Сегодняшний час, 0–23. По нему решаем, пора ли говорить. */
    fun hourNow(): Int = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)

    /** Дата на `days` дней раньше сегодняшней. */
    fun isoDaysAgo(days: Int): String {
        val calendar = Calendar.getInstance()
        calendar.add(Calendar.DAY_OF_MONTH, -days)
        return iso(calendar)
    }
}
