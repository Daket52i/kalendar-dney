package org.djdancho.calendar

import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import org.json.JSONObject
import java.util.concurrent.Executors

/**
 * Напоминания и настройки: что когда говорить.
 *
 * Настройки хранятся в том же виде, в каком их понимает ядро. Ничего не
 * считаем здесь: экран только показывает числа и складывает их в JSON,
 * а правила («за сколько дней», «тихие часы») живут в Python и проверены
 * тестами.
 */
class SettingsActivity : AppCompatActivity() {

    private lateinit var daysBefore: EditText
    private lateinit var onDay: CheckBox
    private lateinit var delay: EditText
    private lateinit var fertile: CheckBox
    private lateinit var pillOn: CheckBox
    private lateinit var pillHour: EditText
    private lateinit var quietFrom: EditText
    private lateinit var quietTo: EditText
    private lateinit var listText: TextView
    private lateinit var permissionButton: Button

    private val settingsStore by lazy { SettingsStore(this) }
    private val periods by lazy { PeriodStore(this) }
    private val diary by lazy { DiaryStore(this) }
    private val engine by lazy { CycleEngine(this) }
    private val worker = Executors.newSingleThreadExecutor()

    /** Чей календарь открыт. Настройки напоминаний у каждого человека свои,
     *  поэтому и фразы этого экрана обязаны называть, о ком они. */
    @Volatile
    private var person: String = ""

    /** Проговорить фразу от имени открытого человека — через Say. */
    private fun say(text: String) = Say.aloud(this, engine, person, text)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        daysBefore = findViewById(R.id.settingsDaysBefore)
        onDay = findViewById(R.id.settingsOnDay)
        delay = findViewById(R.id.settingsDelay)
        fertile = findViewById(R.id.settingsFertile)
        pillOn = findViewById(R.id.settingsPillOn)
        pillHour = findViewById(R.id.settingsPillHour)
        quietFrom = findViewById(R.id.settingsQuietFrom)
        quietTo = findViewById(R.id.settingsQuietTo)
        listText = findViewById(R.id.settingsList)
        permissionButton = findViewById(R.id.settingsNotifications)

        findViewById<Button>(R.id.settingsSave).setOnClickListener { save() }
        findViewById<Button>(R.id.settingsCheck).setOnClickListener { showUpcoming() }
        findViewById<Button>(R.id.settingsBack).setOnClickListener { finish() }
        permissionButton.setOnClickListener { askPermission() }

        showPermissionButton()
        load()
    }

    override fun onDestroy() {
        worker.shutdown()
        super.onDestroy()
    }

    // ---------- Настройки ----------

    private fun load() {
        worker.execute {
            person = try {
                People.currentName(this)
            } catch (e: Exception) {
                ""
            }
            val settings = try {
                engine.settings(settingsStore.read())
            } catch (e: Exception) {
                JSONObject()
            }
            runOnUiThread {
                daysBefore.setText(settings.optInt("days_before", 2).toString())
                onDay.isChecked = settings.optBoolean("on_expected_day", true)
                delay.setText(settings.optInt("delay_after", 3).toString())
                fertile.isChecked = settings.optBoolean("fertile_notice", true)
                pillOn.isChecked = settings.optBoolean("pill_enabled", false)
                pillHour.setText(settings.optInt("pill_hour", 21).toString())
                quietFrom.setText(settings.optInt("quiet_from", 22).toString())
                quietTo.setText(settings.optInt("quiet_to", 8).toString())
            }
        }
    }

    private fun save() {
        val days = number(daysBefore, MAX_DAYS) ?: return
        val late = number(delay, MAX_DAYS) ?: return
        val pill = number(pillHour, MAX_HOUR) ?: return
        val from = number(quietFrom, MAX_HOUR) ?: return
        val to = number(quietTo, MAX_HOUR) ?: return

        val raw = JSONObject().apply {
            put("days_before", days)
            put("on_expected_day", onDay.isChecked)
            put("delay_after", late)
            put("fertile_notice", fertile.isChecked)
            put("pill_enabled", pillOn.isChecked)
            put("pill_hour", pill)
            put("quiet_from", from)
            put("quiet_to", to)
        }

        worker.execute {
            // Прогоняем через ядро: чужие поля отпадут, битые заменятся
            // умолчаниями — и в файл ляжет ровно то, что понимает расчёт.
            val normalized = engine.settings(raw.toString())
            val ok = settingsStore.write(normalized.toString())
            runOnUiThread {
                say(if (ok) getString(R.string.settings_saved) else getString(R.string.error_save))
                // Проверку в фоне перезапускаем сразу: настройки могли
                // выключить напоминания, и ждать следующего открытия нельзя.
                ReminderScheduler.schedule(this)
                if (ok) load()
            }
        }
    }

    /**
     * Число из поля. Ноль — законное «не напоминать», поэтому отсутствие
     * ответа (null) отличается от нуля: пустое поле это ошибка, а не ноль.
     */
    private fun number(field: EditText, max: Int): Int? {
        val raw = field.text.toString().trim()
        val value = raw.toIntOrNull()
        if (value == null || value < 0 || value > max) {
            say(getString(R.string.settings_range))
            field.requestFocus()
            return null
        }
        return value
    }

    // ---------- Что напомнит дальше ----------

    private fun showUpcoming() {
        worker.execute {
            val lines = try {
                engine.reminderLines(
                    periods.read(), diary.read(), Dates.todayIso(),
                    settingsStore.read(), UPCOMING_LIMIT, person
                )
            } catch (e: Exception) {
                listOf("Не получилось посчитать: ${e.message}")
            }
            // Каждая строка уже пришла из ядра с именем человека — поэтому
            // список читается вслух как есть, без добавки в заголовке.
            runOnUiThread {
                val text = if (lines.isEmpty()) getString(R.string.reminders_empty)
                else lines.joinToString("\n")
                listText.text = text
                Speech.announce(this, text)
            }
        }
    }

    // ---------- Уведомления ----------

    private fun showPermissionButton() {
        permissionButton.visibility =
            if (Reminders.permissionNeeded(this)) View.VISIBLE else View.GONE
    }

    private fun askPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            showPermissionButton()
            return
        }
        ActivityCompat.requestPermissions(
            this, arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), PERMISSION_CODE
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != PERMISSION_CODE) return
        showPermissionButton()
        if (Reminders.allowed(this)) {
            Speech.announce(this, getString(R.string.settings_notifications_ok))
        } else {
            Speech.announce(this, getString(R.string.settings_permission))
        }
    }

    private companion object {
        const val MAX_HOUR = 23
        const val MAX_DAYS = 14
        const val UPCOMING_LIMIT = 10
        const val PERMISSION_CODE = 101
    }
}
