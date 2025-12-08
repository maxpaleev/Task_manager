import sys
import datetime
import sqlite3
import threading
from typing import Dict, List, Tuple

from plyer import notification

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate, QTime, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QTreeWidgetItem, QMenu, QTreeWidget, QInputDialog
)

# Импортируем run_bot_thread для запуска и send_notification (переименован) для отправки
from tg_bot import run_bot_thread, send_notification as send_telegram_notification

TASK_CATEGORIES = [
    "Срочно и важно",
    "Важно, но не срочно",
    "Срочно, но не важно",
    'Не срочно и не важно'
]


class SimplePlanner(QMainWindow):

    def __init__(self):
        super().__init__()

        # Загрузка интерфейса из файла
        try:
            uic.loadUi('design_test.ui', self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить интерфейс (design_test.ui): {e}")
            sys.exit(1)

        self.setWindowTitle('Минипланировщик')

        # Инициализация переменных
        self.events: Dict[datetime.date, List[Tuple[str, datetime.time, datetime.time]]] = {}
        self.tasks: Dict[str, List[Tuple[str, str]]] = {cat: [] for cat in TASK_CATEGORIES}
        self.db = None
        self.tg_enabled = False  # Использовано более понятное имя

        self._init_db()
        self.load_data()
        self._setup_bot_configuration()  # Настройка токена и запуск потока бота

        self.current_importance = TASK_CATEGORIES[0]

        self._setup_tree_widgets()

        # Инициализация таймера для проверки уведомлений
        self.last_alert_minute = -1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_alerts)
        self.timer.start(5000)  # Проверка каждые 5 секунд

        # Соединение сигналов
        self.addEventBtn.clicked.connect(self.add_event)
        self.searchEvent.textChanged.connect(self.update_event_list)
        self.taskButton.clicked.connect(self.add_task)
        self.searchTask.textChanged.connect(self.update_task_list)
        self.importanceChoice.buttonClicked.connect(self._set_importance)
        self.taskDes.setMaxLength(100)

    # -------------------------------------------------------------------
    # ОБЩИЙ МЕТОД ДЛЯ РАБОТЫ С БД
    # -------------------------------------------------------------------

    def _execute_query(self, query: str, params: Tuple = (), commit: bool = False, fetch_all: bool = False):
        """Централизованное выполнение запросов к БД (planner.db) с обработкой ошибок."""
        if not self.db:
            QMessageBox.warning(self, "Предупреждение", "База данных (planner.db) не инициализирована.")
            return

        try:
            cursor = self.db.cursor()
            cursor.execute(query, params)

            if commit:
                self.db.commit()

            if fetch_all:
                return cursor.fetchall()

            return True

        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка БД", f"Ошибка выполнения запроса:\n{e}")
            return False

    # -------------------------------------------------------------------
    # ЛОГИКА БД И НАСТРОЙКИ БОТА (Оптимизация)
    # -------------------------------------------------------------------

    def closeEvent(self, event):
        if self.db:
            self.db.close()
        event.accept()

    def _init_db(self):
        """Инициализация обеих баз данных: planner.db и settings.db."""
        try:
            # 1. planner.db
            self.db = sqlite3.connect('planner.db')
            queries = [
                '''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL
                )
                ''',
                '''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT NOT NULL
                )
                '''
            ]
            for query in queries:
                self._execute_query(query, commit=True)

            # 2. settings.db
            db_s = sqlite3.connect('settings.db')
            cur_s = db_s.cursor()
            cur_s.execute('''
                            CREATE TABLE IF NOT EXISTS settings (
                                id INTEGER PRIMARY KEY,
                                tg_true TEXT NOT NULL,
                                bot_token TEXT,
                                telegram_id INTEGER
                            )
                            ''')
            db_s.commit()
            db_s.close()

        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка БД", f"Не удалось инициализировать базу данных: {e}")
            sys.exit(1)

    def _setup_bot_configuration(self):
        """Проверка токена бота, запрос у пользователя и запуск потока."""
        db = sqlite3.connect('settings.db')
        cur = db.cursor()
        settings = cur.execute("SELECT bot_token, tg_true FROM settings").fetchone()

        if not settings:
            # Первый запуск: запрашиваем токен
            token, ok = QInputDialog.getText(self, 'Настройка Telegram',
                                             'Введите токен бота (@BotFather), если хотите уведомления. Оставьте пустым, если не хотите.')

            if ok:
                # Определяем статус (1 или 0)
                tg_status = '1' if token.strip() else '0'
                try:
                    # Запись настроек
                    cur.execute('INSERT INTO settings (bot_token, tg_true, telegram_id) VALUES (?, ?, ?)',
                                (token.strip(), tg_status, None))
                    db.commit()
                    if tg_status == '1':
                        QMessageBox.information(self, 'Успех',
                                                'Токен сохранен. Для активации уведомлений напишите боту /start.')
                    else:
                        QMessageBox.information(self, 'Настройки', 'Telegram уведомления отключены.')
                except sqlite3.Error:
                    QMessageBox.warning(self, 'Ошибка', 'Не удалось сохранить токен.')

                self.tg_enabled = int(tg_status)
            else:
                # Если нажата отмена, считать, что Telegram отключен
                self.tg_enabled = 0
        else:
            # Настройки уже есть
            token, tg_status = settings
            self.tg_enabled = int(tg_status)

        db.close()

        # Запуск бота:
        if self.tg_enabled:
            # Используем run_bot_thread, который сам загрузит токен и ID
            self.bot_thread = threading.Thread(target=run_bot_thread, daemon=True)
            self.bot_thread.start()

    def load_data(self):
        self.events.clear()
        for category in TASK_CATEGORIES:
            self.tasks[category] = []

        # Загрузка событий
        event_rows = self._execute_query(
            "SELECT name, event_date, time_start, time_end FROM events ORDER BY event_date, time_start",
            fetch_all=True
        )
        if event_rows:
            for name, event_date, time_start, time_end in event_rows:
                try:
                    date = datetime.datetime.strptime(event_date, "%Y-%m-%d").date()
                    time_start_obj = datetime.datetime.strptime(time_start, "%H:%M:%S").time()
                    time_end_obj = datetime.datetime.strptime(time_end, "%H:%M:%S").time()

                    if date not in self.events:
                        self.events[date] = []
                    self.events[date].append((name, time_start_obj, time_end_obj))
                except ValueError:
                    continue

        # Загрузка задач
        task_rows = self._execute_query(
            "SELECT name, description, category FROM tasks",
            fetch_all=True
        )
        if task_rows:
            for name, desc, cat in task_rows:
                if cat in self.tasks:
                    self.tasks[cat].append((name, desc))

        self.update_event_list()
        self.update_task_list()

    # -------------------------------------------------------------------
    # ЛОГИКА ДЕРЕВЬЕВ
    # -------------------------------------------------------------------

    def _setup_tree_widgets(self):
        self.eventList.setColumnCount(2)
        self.eventList.setHeaderLabels(["Событие", "Время"])
        self.eventList.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.eventList.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(self.eventList, pos)
        )

        self.taskList.setColumnCount(2)
        self.taskList.setHeaderLabels(["Название", "Описание"])
        self.taskList.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.taskList.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(self.taskList, pos)
        )

    # -------------------------------------------------------------------
    # ЛОГИКА КОНТЕКСТНОГО МЕНЮ (Осталась без изменений)
    # -------------------------------------------------------------------

    def show_context_menu(self, tree_widget: QTreeWidget, position):
        item = tree_widget.itemAt(position)
        if not item:
            return

        menu = QMenu(self)
        action_del = menu.addAction("Удалить")
        action_edit = menu.addAction("Редактировать")
        menu.addSeparator()
        action_expand = menu.addAction("Раскрыть все")
        action_collapse = menu.addAction("Свернуть все")

        if not item.parent():
            action_edit.setEnabled(False)

        action = menu.exec(tree_widget.viewport().mapToGlobal(position))

        if not action:
            return

        if action == action_del:
            self._delete_item(tree_widget, item)
        elif action == action_edit:
            self._edit_item(tree_widget, item)
        elif action == action_expand:
            tree_widget.expandAll()
        elif action == action_collapse:
            tree_widget.collapseAll()

    def _delete_item(self, tree_widget, item):
        if tree_widget is self.eventList:
            self._delete_event_logic(item)
        elif tree_widget is self.taskList:
            self._delete_task_logic(item)

    def _edit_item(self, tree_widget, item):
        parent = item.parent()
        if not parent:
            return

        if tree_widget is self.eventList:
            event_date = parent.data(0, Qt.ItemDataRole.UserRole)
            event_data = item.data(0, Qt.ItemDataRole.UserRole)

            self._delete_event_logic(item)

            name, start, end = event_data
            self.eventName.setText(name)
            self.timeStart.setTime(QTime(start.hour, start.minute))
            self.timeEnd.setTime(QTime(end.hour, end.minute))
            self.calendarWidget.setSelectedDate(QDate(event_date.year, event_date.month, event_date.day))

        elif tree_widget is self.taskList:
            category_name = parent.data(0, Qt.ItemDataRole.UserRole)
            task_data = item.data(0, Qt.ItemDataRole.UserRole)

            self._delete_task_logic(item)

            name, desc = task_data
            self.taskName.setText(name)
            self.taskDes.setText(desc)

            self.current_importance = category_name
            for btn in self.importanceChoice.buttons():
                if btn.text() == category_name:
                    btn.setChecked(True)
                    break

    # -------------------------------------------------------------------
    # ЛОГИКА УВЕДОМЛЕНИЙ (Обновлено)
    # -------------------------------------------------------------------

    def check_alerts(self):
        current_time = datetime.datetime.now().time()
        current_date = datetime.date.today()

        if self.last_alert_minute == current_time.minute:
            return

        self.last_alert_minute = current_time.minute

        if current_date in self.events:
            for event in self.events[current_date]:
                name, start, end = event
                if start.hour == current_time.hour and start.minute == current_time.minute:

                    # 1. Отправка Windows-уведомления
                    self._send_windows_notification(name, start, end)

                    # 2. Отправка Telegram-уведомления с проверкой статуса
                    if self.tg_enabled:
                        # Проверяем статус отправки
                        if not send_telegram_notification(name, start, end):
                            QMessageBox.warning(self, "Ошибка Telegram",
                                                f"Не удалось отправить уведомление о событии '{name}' в Telegram. "
                                                "Возможно, вы не запустили бота командой /start.")

    def _send_windows_notification(self, title, time_s, time_e):
        """Отправка системного уведомления Windows."""
        time_s_str = time_s.strftime("%H:%M")
        time_e_str = time_e.strftime("%H:%M")
        try:
            notification.notify(
                title=f"Событие: {title}",
                message=f"Запланировано событие на время: {time_s_str} - {time_e_str}",
                app_name="Минипланировщик",
                timeout=10
            )
        except Exception as e:
            print(f"Не удалось отправить Windows уведомление: {e}")

    # -------------------------------------------------------------------
    # ЛОГИКА СОБЫТИЙ (Events)
    # -------------------------------------------------------------------

    def add_event(self):
        name = self.eventName.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название события")
            return

        date_py = self.calendarWidget.selectedDate().toPyDate()
        start_py = self.timeStart.time().toPyTime()
        end_py = self.timeEnd.time().toPyTime()

        if end_py < start_py:
            QMessageBox.warning(self, "Ошибка", "Время окончания не может быть раньше начала")
            return

        date_str = date_py.strftime("%Y-%m-%d")
        start_str = start_py.strftime("%H:%M:%S")
        end_str = end_py.strftime("%H:%M:%S")

        success = self._execute_query(
            '''INSERT INTO events (name, event_date, time_start, time_end) VALUES (?, ?, ?, ?)''',
            (name, date_str, start_str, end_str),
            commit=True
        )

        if success:
            self.eventName.clear()
            self.timeStart.setTime(QTime(0, 0))
            self.timeEnd.setTime(QTime(0, 0))
            self.load_data()

    def update_event_list(self):
        search = self.searchEvent.text().lower()
        self.eventList.clear()

        items = []
        for date_key in sorted(self.events.keys()):
            events_list = self.events[date_key]

            if search:
                matching = [e for e in events_list if search in e[0].lower()]
            else:
                matching = events_list

            if matching:
                root_item = QTreeWidgetItem([date_key.strftime("%d.%m.%Y")])
                root_item.setData(0, Qt.ItemDataRole.UserRole, date_key)

                for ev in sorted(matching, key=lambda x: x[1]):
                    name, start, end = ev
                    time_str = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
                    child = QTreeWidgetItem([name, time_str])
                    child.setData(0, Qt.ItemDataRole.UserRole, ev)
                    root_item.addChild(child)

                items.append(root_item)

        self.eventList.insertTopLevelItems(0, items)
        if search:
            self.eventList.expandAll()

    def _delete_event_logic(self, item):
        if item.parent():
            # Удаление конкретного события
            date_key = item.parent().data(0, Qt.ItemDataRole.UserRole)
            ev_data = item.data(0, Qt.ItemDataRole.UserRole)
            name, start_time, end_time = ev_data

            date_str = date_key.strftime("%Y-%m-%d")
            start_str = start_time.strftime("%H:%M:%S")
            end_str = end_time.strftime("%H:%M:%S")

            query = '''DELETE FROM events WHERE name = ? AND event_date = ? AND time_start = ? AND time_end = ?'''
            params = (name, date_str, start_str, end_str)
        else:
            # Удаление всех событий за день
            date_key = item.data(0, Qt.ItemDataRole.UserRole)
            date_str = date_key.strftime("%Y-%m-%d")

            query = '''DELETE FROM events WHERE event_date = ?'''
            params = (date_str,)

        self._execute_query(query, params, commit=True)
        self.load_data()

    # ------------------------------------------------------------------
    # ЛОГИКА ЗАДАЧ (Tasks)
    # ------------------------------------------------------------------

    def _set_importance(self, button):
        self.current_importance = button.text()

    def add_task(self):
        name = self.taskName.text().strip()
        desc = self.taskDes.text().strip()

        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return

        success = self._execute_query(
            '''INSERT INTO tasks (name, description, category) VALUES (?, ?, ?)''',
            (name, desc, self.current_importance),
            commit=True
        )

        if success:
            self.taskName.clear()
            self.taskDes.clear()
            self.load_data()

    def update_task_list(self):
        search = self.searchTask.text().lower()
        self.taskList.clear()
        items = []

        for category in TASK_CATEGORIES:
            tasks_list = self.tasks[category]

            if search:
                matching = [t for t in tasks_list if search in t[0].lower()]
            else:
                matching = tasks_list

            if matching:
                root = QTreeWidgetItem([category])
                root.setData(0, Qt.ItemDataRole.UserRole, category)

                for t in matching:
                    name, desc = t
                    child = QTreeWidgetItem([name, desc])
                    child.setData(0, Qt.ItemDataRole.UserRole, t)
                    root.addChild(child)

                items.append(root)

        self.taskList.insertTopLevelItems(0, items)
        if search:
            self.taskList.expandAll()

    def _delete_task_logic(self, item):
        if item.parent():
            # Удаление конкретной задачи
            cat = item.parent().data(0, Qt.ItemDataRole.UserRole)
            t_data = item.data(0, Qt.ItemDataRole.UserRole)

            query = '''DELETE FROM tasks WHERE name = ? AND description = ? AND category = ?'''
            params = (t_data[0], t_data[1], cat)
        else:
            # Удаление всех задач в категории
            cat = item.data(0, Qt.ItemDataRole.UserRole)

            query = '''DELETE FROM tasks WHERE category = ?'''
            params = (cat,)

        self._execute_query(query, params, commit=True)
        self.load_data()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())