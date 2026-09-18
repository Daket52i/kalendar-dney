package org.djdancho.calendar

import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.util.concurrent.Executors

/**
 * Экран «Люди»: чей календарь открыт и как переключиться.
 *
 * Задуман для матери, которая ведёт и свой календарь, и календарь дочери:
 * календари лежат рядом и переключаются одной кнопкой, а данные между ними не
 * смешиваются.
 *
 * Правило доступности то же, что и везде: всё, что происходит, произносится
 * словами. Диалог с полем ввода TalkBack читает целиком — заголовок, поле и
 * кнопки, — поэтому имя спрашиваем диалогом, а не отдельным экраном.
 */
class PeopleActivity : AppCompatActivity() {

    private lateinit var nowText: TextView
    private lateinit var listText: TextView

    private val engine by lazy { CycleEngine(this) }

    /** Работа с ядром и файлами — в отдельном потоке: подъём Python на первом
     *  обращении занимает заметное время, и озвучка не должна его ждать. */
    private val worker = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_people)

        nowText = findViewById(R.id.peopleNow)
        listText = findViewById(R.id.peopleList)

        findViewById<Button>(R.id.btnChoose).setOnClickListener { choose() }
        findViewById<Button>(R.id.btnAdd).setOnClickListener { askName(add = true) }
        findViewById<Button>(R.id.btnRename).setOnClickListener { askName(add = false) }
        findViewById<Button>(R.id.btnRemove).setOnClickListener { confirmRemove() }
        findViewById<Button>(R.id.btnPeopleBack).setOnClickListener { finish() }
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    override fun onDestroy() {
        worker.shutdown()
        super.onDestroy()
    }

    // ---------- Показ ----------

    private fun refresh() {
        worker.execute {
            val name = try {
                People.currentName(this)
            } catch (e: Exception) {
                getString(R.string.error_people)
            }
            val people = try {
                People.people(this, engine)
            } catch (e: Exception) {
                emptyList()
            }
            runOnUiThread {
                nowText.text = getString(R.string.people_now, name)
                listText.text = if (people.size <= 1) {
                    getString(R.string.people_only_one, name)
                } else {
                    getString(R.string.people_all, people.joinToString(", ") { it.name })
                }
                // «Убрать» на единственном календаре нажимать нечего: показывать
                // нечего станет. Кнопку гасим, а не прячем — так понятно, что
                // она есть и почему выключена.
                findViewById<Button>(R.id.btnRemove).isEnabled = people.size > 1
            }
        }
    }

    private fun refreshAndAnnounce(phrase: String) {
        refresh()
        Speech.announce(this, phrase)
    }

    // ---------- Выбор ----------

    private fun choose() {
        worker.execute {
            val people = try {
                People.people(this, engine)
            } catch (e: Exception) {
                emptyList()
            }
            val current = try {
                People.currentId(this)
            } catch (e: Exception) {
                ""
            }
            if (people.isEmpty()) return@execute
            val names = people.map { person ->
                if (person.id == current) getString(R.string.people_current_mark, person.name)
                else person.name
            }.toTypedArray()

            runOnUiThread {
                MaterialAlertDialogBuilder(this)
                    .setTitle(getString(R.string.people_choose_title))
                    .setItems(names) { _, index ->
                        val person = people[index]
                        if (person.id == current) {
                            Speech.announce(this, getString(R.string.people_already, person.name))
                            return@setItems
                        }
                        switchTo(person)
                    }
                    .setNegativeButton(getString(R.string.people_cancel), null)
                    .show()
            }
        }
    }

    private fun switchTo(person: Person) {
        worker.execute {
            val error = try {
                People.switch(this, engine, person.id)
            } catch (e: Exception) {
                getString(R.string.error_people)
            }
            runOnUiThread {
                if (error.isNotEmpty()) {
                    Speech.announce(this, error)
                    return@runOnUiThread
                }
                refreshAndAnnounce(getString(R.string.people_opened, person.name))
            }
        }
    }

    // ---------- Добавить и переименовать ----------

    /**
     * Спрашивает имя диалогом. `add = true` — завести нового человека,
     * иначе — переименовать открытого.
     */
    private fun askName(add: Boolean) {
        val input = EditText(this)
        input.hint = getString(R.string.people_name_hint)
        input.minHeight = dp(56)
        input.isSingleLine = true

        // Диалог строится кодом, а не разметкой: поле ввода одно, и держать
        // ради него отдельный файл с одним EditText незачем.
        val field = LinearLayout(this)
        field.setPadding(dp(24), dp(8), dp(24), 0)
        field.addView(input, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ))

        val title = if (add) R.string.people_add_title else R.string.people_rename_title
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(getString(title))
            .setView(field)
            .setPositiveButton(getString(R.string.people_save_name)) { _, _ ->
                val name = input.text.toString()
                if (add) addPerson(name) else renamePerson(name)
            }
            .setNegativeButton(getString(R.string.people_cancel), null)
            .create()

        if (!add) {
            // Переименование начинается с нынешнего имени: не надо набирать
            // его заново, если меняется одна буква.
            worker.execute {
                val current = try {
                    People.currentName(this)
                } catch (e: Exception) {
                    ""
                }
                runOnUiThread { input.setText(current); input.setSelection(current.length) }
            }
        }
        dialog.show()
    }

    /** Плотность экрана в пикселях — разметку диалога считаем кодом. */
    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun addPerson(name: String) {
        worker.execute {
            val error = try {
                People.add(this, engine, name)
            } catch (e: Exception) {
                getString(R.string.error_people)
            }
            val current = try {
                People.currentName(this)
            } catch (e: Exception) {
                ""
            }
            runOnUiThread {
                if (error.isNotEmpty()) {
                    Speech.announce(this, error)
                    return@runOnUiThread
                }
                refreshAndAnnounce(getString(R.string.people_added, current))
            }
        }
    }

    private fun renamePerson(name: String) {
        worker.execute {
            val id = try {
                People.currentId(this)
            } catch (e: Exception) {
                ""
            }
            val error = try {
                People.rename(this, engine, id, name)
            } catch (e: Exception) {
                getString(R.string.error_people)
            }
            val current = try {
                People.currentName(this)
            } catch (e: Exception) {
                ""
            }
            runOnUiThread {
                if (error.isNotEmpty()) {
                    Speech.announce(this, error)
                    return@runOnUiThread
                }
                refreshAndAnnounce(getString(R.string.people_renamed, current))
            }
        }
    }

    // ---------- Убрать ----------

    private fun confirmRemove() {
        worker.execute {
            val name = try {
                People.currentName(this)
            } catch (e: Exception) {
                ""
            }
            runOnUiThread {
                MaterialAlertDialogBuilder(this)
                    .setTitle(getString(R.string.people_remove_title))
                    .setMessage(getString(R.string.people_remove_message, name))
                    .setPositiveButton(getString(R.string.people_remove_yes)) { _, _ ->
                        removePerson()
                    }
                    .setNegativeButton(getString(R.string.people_cancel), null)
                    .show()
            }
        }
    }

    private fun removePerson() {
        worker.execute {
            val id = try {
                People.currentId(this)
            } catch (e: Exception) {
                ""
            }
            val name = try {
                People.currentName(this)
            } catch (e: Exception) {
                ""
            }
            val error = try {
                People.remove(this, engine, id)
            } catch (e: Exception) {
                getString(R.string.error_people)
            }
            val left = try {
                People.currentName(this)
            } catch (e: Exception) {
                ""
            }
            runOnUiThread {
                if (error.isNotEmpty()) {
                    Speech.announce(this, error)
                    return@runOnUiThread
                }
                refreshAndAnnounce(getString(R.string.people_removed, name, left))
            }
        }
    }
}
