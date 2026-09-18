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
            val hour = Dates.hourNow()
            val engine = CycleEngine(context)

            // Проходим по всем календарям: у каждого свои отметки, настройки и
            // свой файл «уже показывали». Хватает одного должного напоминания
            // у кого угодно, чтобы показать уведомление.
            var anythingDue = false
            Reminders.allByPerson(context, engine, People.people(context, engine))
                .forEach { belonging ->
                    val store = Reminders.notified(context, belonging.person.id)
                    val due = Reminders.due(
                        reminders = belonging.reminders,
                        todayIso = today,
                        hour = hour,
                        notBeforeIso = cutoff,
                        shown = store.read()
                    )
                    if (due.isNotEmpty()) {
                        anythingDue = true
                        // Помечаем все должные сразу: иначе следующая проверка
                        // через пятнадцать минут сообщила бы о том же снова.
                        due.forEach { store.add(it.key, cutoff) }
                    }
                }

            if (anythingDue) Reminders.show(context)
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
