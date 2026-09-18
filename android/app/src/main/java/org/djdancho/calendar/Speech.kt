package org.djdancho.calendar

import android.app.Activity
import android.content.Context
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityManager

/**
 * Проговорить текст вслух, не дожидаясь, пока до него дойдут свайпом.
 *
 * Это главный способ ответить вслепую: нажал — и сразу услышал, что вышло.
 * Если скринридер выключен, молчим: звук «в пустоту» только мешает.
 */
object Speech {

    fun announce(activity: Activity, phrase: String) {
        val manager = activity.getSystemService(Context.ACCESSIBILITY_SERVICE)
            as? AccessibilityManager ?: return
        if (!manager.isEnabled) return

        val event = AccessibilityEvent.obtain(AccessibilityEvent.TYPE_ANNOUNCEMENT)
        event.packageName = activity.packageName
        event.className = activity.javaClass.name
        // Отдельным вызовом, а не внутри apply: там имя text означало бы
        // собственное поле события, и список добавился бы сам в себя.
        event.text.add(phrase)
        manager.sendAccessibilityEvent(event)
    }
}
