package org.djdancho.calendar

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

/**
 * Напоминания: что уже пора показать, как об этом сказать и когда проверять.
 *
 * Общая часть для фоновой проверки и для экранов. Правила «пора» и «уже
 * показывали» обязаны быть одними и теми же: иначе уведомление и голос
 * разойдутся, и одно и то же прозвучит дважды.
 */
object Reminders {

    /** Чаще пятнадцати минут WorkManager не умеет — да и не нужно:
     *  напоминания живут в масштабе часов, а не секунд. */
    const val CHECK_MINUTES = 15L

    /** Насколько назад оглядываемся, если телефон лежал выключенным. */
    const val LOOK_BACK_DAYS = 2

    /** Насколько вперёд считаем напоминания. */
    const val HORIZON_DAYS = 90

    private const val CHANNEL_ID = "reminders"
    private const val NOTIFICATION_ID = 1

    /** Ключи, о которых уже сказали уведомлением. Файл у каждого свой. */
    fun notified(context: Context, personId: String? = null): KeyStore =
        KeyStore(context, "notified.json", personId)

    /** Ключи, которые уже проговорили голосом внутри приложения. */
    fun spoken(context: Context, personId: String? = null): KeyStore =
        KeyStore(context, "spoken.json", personId)

    /**
     * Все напоминания одного человека на ближайшие дни.
     *
     * Имя подставляется в каждое: на телефоне, где ведут два календаря,
     * напоминание без имени не понять — «сегодня ожидаются месячные» одинаково
     * звучит и про маму, и про дочь.
     */
    fun all(context: Context, engine: CycleEngine, person: Person): List<Reminder> =
        engine.reminders(
            PeriodStore(context, person.id).read(),
            DiaryStore(context, person.id).read(),
            Dates.todayIso(),
            SettingsStore(context, person.id).read(),
            HORIZON_DAYS,
            person.name
        )

    /** Напоминания одного человека: кому они и что именно. */
    data class Belonging(val person: Person, val reminders: List<Reminder>)

    /**
     * Напоминания всех людей сразу.
     *
     * Проверка идёт по всем календарям, а не только по открытому: мама должна
     * получить напоминание про дочку и тогда, когда у неё открыт свой. Иначе
     * второй календарь молчал бы, пока в него не переключатся, — то есть ровно
     * тогда, когда он и нужен, он бы не работал.
     *
     * Сбой на одном человеке не отменяет остальных: испорченный файл у дочки
     * не должен лишать маму её собственных напоминаний.
     */
    fun allByPerson(
        context: Context,
        engine: CycleEngine,
        people: List<Person>
    ): List<Belonging> = people.mapNotNull { person ->
        try {
            Belonging(person, all(context, engine, person))
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Что уже пора показать: день наступил, час наступил, и об этом ещё не
     * говорили. Напоминания старше `notBeforeIso` отбрасываем — говорить
     * сегодня «завтра ожидаются месячные» про позавчера бессмысленно.
     */
    fun due(
        reminders: List<Reminder>,
        todayIso: String,
        hour: Int,
        notBeforeIso: String,
        shown: Set<String>
    ): List<Reminder> = reminders.filter { reminder ->
        reminder.day >= notBeforeIso &&
            reminder.day <= todayIso &&
            (reminder.day < todayIso || reminder.hour <= hour) &&
            reminder.key !in shown
    }

    /** Канал уведомлений. Повторный вызов ничего не портит. */
    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            context.getString(R.string.app_name),
            NotificationManager.IMPORTANCE_DEFAULT
        )
        channel.description = context.getString(R.string.settings_title)
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        manager.createNotificationChannel(channel)
    }

    /**
     * Уведомление без единого личного слова: только название приложения и
     * приглашение открыть его. Текст напоминания проговаривается внутри —
     * уведомление может увидеть кто угодно, и повод для этого давать нельзя.
     */
    fun show(context: Context) {
        if (!allowed(context)) return
        ensureChannel(context)

        val intent = Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val pending = PendingIntent.getActivity(context, 0, intent, flags)

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(context.getString(R.string.notify_text))
            .setContentIntent(pending)
            .setAutoCancel(true)
            .build()

        NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, notification)
    }

    /** Разрешены ли уведомления. До Android 13 разрешение не спрашивают. */
    fun allowed(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED
    }

    /** Нужно ли вообще спрашивать разрешение — от этого зависит кнопка. */
    fun permissionNeeded(context: Context): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !allowed(context)
}
