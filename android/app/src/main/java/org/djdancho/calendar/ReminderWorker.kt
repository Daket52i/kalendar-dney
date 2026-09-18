package org.djdancho.calendar

import android.content.Context
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/**
 * Фоновая проверка: не пора ли напомнить.
 *
 * Работает по расписанию системы, не чаще раза в пятнадцать минут — это не
 * будильник «секунда в секунду», но для «сегодня напомнить про таблетку»
 * точности хватает с запасом. Показываем нейтральное уведомление; всё
 * личное человек услышит внутри приложения.
 */
class ReminderWorker(context: Context, params: WorkerParameters) :
    Worker(context, params) {

    override fun doWork(): Result {
        val context = applicationContext
        return try {
            val today = Dates.todayIso()
            val cutoff = Dates.isoDaysAgo(Reminders.LOOK_BACK_DAYS)
            val due = Reminders.due(
                reminders = Reminders.all(context, CycleEngine(context)),
                todayIso = today,
                hour = Dates.hourNow(),
                notBeforeIso = cutoff,
                shown = Reminders.notified(context).read()
            )
            if (due.isNotEmpty()) {
                Reminders.show(context)
                // Помечаем все должные сразу: иначе следующая проверка через
                // пятнадцать минут сообщила бы про то же самое ещё раз.
                val store = Reminders.notified(context)
                due.forEach { store.add(it.key, cutoff) }
            }
            Result.success()
        } catch (e: Exception) {
            // Ядро не поднялось или файл не прочитался — это не повод слать
            // системе ошибку и повторять немедленно: следующая проверка
            // придёт сама через пятнадцать минут.
            Result.success()
        }
    }
}

/** Ставит периодическую проверку. Повторный вызов безвреден. */
object ReminderScheduler {

    private const val WORK_NAME = "cycle-reminders"

    fun schedule(context: Context) {
        val request = PeriodicWorkRequestBuilder<ReminderWorker>(
            Reminders.CHECK_MINUTES, TimeUnit.MINUTES
        ).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WORK_NAME,
            // KEEP, а не REPLACE: иначе каждое открытие настроек сбрасывало бы
            // отсчёт заново, и проверка могла не случиться никогда.
            ExistingPeriodicWorkPolicy.KEEP,
            request
        )
    }
}
