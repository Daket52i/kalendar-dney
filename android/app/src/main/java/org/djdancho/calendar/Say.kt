package org.djdancho.calendar

import android.app.Activity

/**
 * Произносимая фраза от имени открытого человека — одна точка на всё
 * приложение.
 *
 * Имя подставляет ядро на Python, а не оболочка: правило одно на телефон и на
 * Windows, и в новой фразе забыть про имя нельзя незаметно. На телефоне, где
 * ведут два календаря, фраза без имени — это фраза не пойми о ком: «сегодня
 * ожидаются месячные» одинаково звучит и про маму, и про дочь.
 *
 * Поэтому все голосовые ответы экранов идут через этот объект. Фраза, минувшая
 * его, прозвучит безымянно — и это будет ошибкой, а не мелочью.
 */
object Say {

    /**
     * Фраза с именем человека впереди.
     *
     * Если ядро почему-то недоступно, фраза звучит как есть: потерять имя
     * неприятно, потерять из-за этого ответ — хуже.
     */
    fun text(engine: CycleEngine, person: String, phrase: String): String = try {
        engine.signed(person, phrase)
    } catch (e: Exception) {
        phrase
    }

    /** Проговорить фразу вслух, назвав человека. */
    fun aloud(activity: Activity, engine: CycleEngine, person: String, phrase: String) {
        Speech.announce(activity, text(engine, person, phrase))
    }
}
