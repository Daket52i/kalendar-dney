package org.djdancho.calendar

import android.content.Context
import org.json.JSONArray
import java.io.File
import java.io.IOException

/**
 * Один файл с данными внутри приложения: история, дневник, настройки.
 *
 * Пишем через временный файл и переименование — если запись оборвётся
 * (телефон выключится), старая версия файла останется целой. Переименование
 * на некоторых прошивках не срабатывает, поэтому есть запасной путь: писать
 * напрямую. Лучше записать без атомарности, чем потерять данные.
 *
 * Наружу ничего не уходит: у приложения нет даже разрешения на интернет.
 */
class JsonStore(context: Context, private val fileName: String) {

    private val file = File(context.filesDir, fileName)
    private val temp = File(context.filesDir, "$fileName.tmp")

    /** Содержимое файла. Нет файла или он испорчен — пустой ответ. */
    fun readOr(empty: String): String = try {
        if (file.exists()) file.readText() else empty
    } catch (e: IOException) {
        empty
    }

    /** Записывает. Возвращает false, если записать не удалось. */
    fun write(json: String): Boolean = try {
        temp.writeText(json)
        if (!temp.renameTo(file)) {
            file.writeText(json)
            temp.delete()
        }
        true
    } catch (e: IOException) {
        false
    }
}

/** История отметок: тот же файл, что и раньше, — обновление ничего не теряет. */
class PeriodStore(context: Context) {

    private val store = JsonStore(context, "periods.json")

    fun read(): String = store.readOr("[]")

    fun write(json: String): Boolean = store.write(json)
}

/** Дневник самочувствия. Пустой файл — «[]», то есть ни одной записи. */
class DiaryStore(context: Context) {

    private val store = JsonStore(context, "diary.json")

    fun read(): String = store.readOr("[]")

    fun write(json: String): Boolean = store.write(json)
}

/** Настройки напоминаний. Пустой файл — «{}», то есть всё по умолчанию. */
class SettingsStore(context: Context) {

    private val store = JsonStore(context, "settings.json")

    fun read(): String = store.readOr("{}")

    fun write(json: String): Boolean = store.write(json)
}

/**
 * Ключи напоминаний, которые уже показали: «день:вид».
 *
 * Нужен в двух местах и с разным смыслом — уведомление показываем один раз
 * (`notified.json`), голосом внутри приложения говорим тоже один раз
 * (`spoken.json`). Один и тот же файл для обоих не годится: тогда уведомление
 * съедало бы текст, который человек ещё не слышал.
 *
 * Старые ключи выбрасываем на каждой записи: иначе файл рос бы годами.
 * Даты в ISO сравниваются как строки, поэтому отбор простой.
 */
class KeyStore(context: Context, fileName: String) {

    private val store = JsonStore(context, fileName)

    fun read(): Set<String> = try {
        val array = JSONArray(store.readOr("[]"))
        (0 until array.length()).map { array.getString(it) }.toSet()
    } catch (e: Exception) {
        emptySet()
    }

    /** Добавляет ключ и заодно чистит всё, что старше `keepFromIso`. */
    fun add(key: String, keepFromIso: String) {
        val kept = read().filter { it.substringBefore(':') >= keepFromIso }.toMutableSet()
        kept.add(key)
        store.write(JSONArray(kept.toList()).toString())
    }
}
