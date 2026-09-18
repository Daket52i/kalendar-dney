package org.djdancho.calendar

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Человек, чей календарь ведётся: имя и неизменный идентификатор. */
data class Person(val id: String, val name: String)

/**
 * Люди на одном телефоне: мама ведёт и свой календарь, и календарь дочери.
 *
 * У каждого своя папка, поэтому данные не могут перемешаться. Список людей и
 * все проверки имени живут в ядре на Python — здесь только папки и вызовы:
 * правила про имя обязаны быть одними и теми же на телефоне и на компьютере.
 */
object People {

    private const val FILE = "people.json"
    private const val DIR = "people"

    /** Файлы первой версии, когда календарь был один. */
    private val LEGACY = listOf(
        "periods.json", "diary.json", "settings.json", "notified.json", "spoken.json"
    )

    private fun listFile(context: Context) = File(context.filesDir, FILE)

    /**
     * Список людей как он лежит в файле.
     *
     * Если файла нет — приложение только что поставлено либо стояло ещё до
     * появления профилей. Тогда список создаёт ядро, а старые файлы переезжают
     * внутрь единственного человека: молча потерять чужую историю из-за
     * обновления нельзя.
     */
    fun document(context: Context): String {
        val file = listFile(context)
        runCatching {
            if (file.exists() && file.readText().isNotBlank()) return file.readText()
        }

        val answer = CycleEngine(context).people("")
        val current = answer.optString("current")
        val document = answer.optString("people")
        runCatching {
            val target = File(File(context.filesDir, DIR), current)
            target.mkdirs()
            LEGACY.forEach { name ->
                val legacy = File(context.filesDir, name)
                if (legacy.exists()) legacy.renameTo(File(target, name))
            }
            file.writeText(document)
        }
        return document
    }

    fun save(context: Context, document: String) {
        runCatching { listFile(context).writeText(document) }
    }

    /** Разобранный ответ ядра: люди, текущий, его имя. */
    fun parsed(context: Context, engine: CycleEngine): JSONObject =
        engine.people(document(context))

    fun people(context: Context, engine: CycleEngine): List<Person> {
        val array: JSONArray = parsed(context, engine).optJSONArray("people") ?: JSONArray()
        return (0 until array.length()).mapNotNull { index ->
            val item = array.optJSONObject(index) ?: return@mapNotNull null
            Person(item.optString("id"), item.optString("name"))
        }
    }

    fun currentId(context: Context): String = parsed(context, CycleEngine(context)).optString("current")

    fun currentName(context: Context): String = parsed(context, CycleEngine(context)).optString("name")

    /** Списка ещё нет — значит, приложение спросит имя при запуске. */
    fun isFirstRun(context: Context): Boolean {
        val file = listFile(context)
        return !file.exists() || file.readText().isBlank()
    }

    /**
     * Папка текущего человека. Создаётся при первом обращении.
     *
     * Папка, а не набор файлов с префиксом в имени: у человека бывает и
     * удаление целиком, и тогда стирать нужно ровно одну папку.
     */
    fun dir(context: Context): File = dirOf(context, currentId(context))

    /**
     * Папка конкретного человека по имени его идентификатора.
     *
     * Нужна фоновой проверке: напоминания надо посчитать про всех сразу, а не
     * только про открытого — иначе про дочку не напомнит, пока мама не
     * переключится на её календарь.
     */
    fun dirOf(context: Context, id: String): File {
        val folder = File(File(context.filesDir, DIR), id)
        if (!folder.exists()) folder.mkdirs()
        return folder
    }

    // ---------- Действия ----------

    /** Ответ ядра: либо ошибка словами, либо пустая строка. */
    private fun apply(context: Context, engine: CycleEngine, answer: JSONObject): String {
        if (!answer.optBoolean("ok", false)) {
            return answer.optString("error").ifBlank { "Не получилось." }
        }
        save(context, answer.optString("people"))
        return ""
    }

    private fun answer(context: Context, engine: CycleEngine, call: (String) -> JSONObject): String =
        apply(context, engine, call(document(context)))

    fun add(context: Context, engine: CycleEngine, name: String): String =
        answer(context, engine) { engine.personAdd(it, name) }

    fun rename(context: Context, engine: CycleEngine, id: String, name: String): String =
        answer(context, engine) { engine.personRename(it, id, name) }

    fun switch(context: Context, engine: CycleEngine, id: String): String =
        answer(context, engine) { engine.personSwitch(it, id) }

    /** Убирает человека из списка и стирает его папку со всеми данными. */
    fun remove(context: Context, engine: CycleEngine, id: String): String {
        val error = answer(context, engine) { engine.personRemove(it, id) }
        if (error.isEmpty()) runCatching { File(File(context.filesDir, DIR), id).deleteRecursively() }
        return error
    }
}
