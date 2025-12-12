import sys
import datetime
import sqlite3
import threading
import requests
import json
from typing import Dict, List, Tuple
import requests
from requests.exceptions import RequestException, HTTPError

from plyer import notification

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate, QTime, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QTreeWidgetItem, QMenu, QTreeWidget, QInputDialog
)

SERVER_URL = "http://127.0.0.1:8000"
DB_FILE = 'planner.db'
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
            uic.loadUi('Client/design_test.ui', self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить интерфейс (design_test.ui): {e}")
            sys.exit(1)

        self.setWindowTitle('Минипланировщик')

        # Инициализация переменных
        self.events: Dict[datetime.date, List[Tuple[str, datetime.time, datetime.time]]] = {}
        self.tasks: Dict[str, List[Tuple[str, str]]] = {cat: [] for cat in TASK_CATEGORIES}
        self.tg_enabled = False  # Использовано более понятное имя

        self._init_db()
        self.load_data()
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
        self.tgButton.clicked.connect(self.open_telegram_dialog)

    # -------------------------------------------------------------------
    # ОБЩИЙ МЕТОД ДЛЯ РАБОТЫ С БД
    # -------------------------------------------------------------------

    def _execute_query(self, query: str, params: Tuple = (), commit: bool = False, fetch_all: bool = False):
        """
        Централизованное выполнение запросов к БД.
        Создает и закрывает соединение при каждом вызове, что делает его потокобезопасным.
        """
        conn = None
        try:
            # СОЗДАЕМ НОВОЕ СОЕДИНЕНИЕ В ТЕКУЩЕМ ПОТОКЕ
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(query, params)

            if commit:
                conn.commit()

            if fetch_all:
                return cursor.fetchall()

            return cursor  # Возвращаем курсор для получения lastrowid

        except sqlite3.Error as e:
            # Для отладки в потоке:
            print(f"Ошибка БД в потоке {threading.get_ident()}: {e}")
            # ВАЖНО: Нельзя вызывать QMessageBox здесь, так как это не главный поток
            return None
        finally:
            if conn:
                conn.close()

    # -------------------------------------------------------------------
    # ЛОГИКА БД И НАСТРОЙКИ БОТА (Оптимизация)
    # -------------------------------------------------------------------

    def _init_db(self):
        """Инициализация локальной базы данных SQLite."""
        # Используем локальное соединение для инициализации
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            # Обновленная таблица EVENTS с server_id
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    server_id INTEGER NULL
                )
            ''')

            # Добавление server_id, если таблица существовала
            try:
                cursor.execute("ALTER TABLE events ADD COLUMN server_id INTEGER NULL")
            except sqlite3.OperationalError:
                pass

            queries = [
                '''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT NOT NULL
                )
                ''',
                '''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    tg_enabled INTEGER
                )
                '''
            ]
            for query in queries:
                conn.cursor().execute(query)  # Выполняем запросы

            conn.commit()

        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка БД", f"Не удалось инициализировать базу данных: {e}")
            sys.exit(1)
        finally:
            if conn:
                conn.close()

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

    def show_context_menu(self, tree_widget, position):
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
    # ЛОГИКА Telegram
    # -------------------------------------------------------------------

    def _get_api_token(self) -> str | None:
        """Извлекает сохраненный API токен из локальной БД."""
        query = "SELECT value FROM settings WHERE key = 'api_token'"
        cursor = self._execute_query(query, fetch_all=True)
        return cursor[0][0]

    def _save_api_token(self, token: str):
        """Сохраняет полученный API токен в локальной БД."""
        query = "INSERT OR REPLACE INTO settings (key, value) VALUES ('api_token', ?)"
        self._execute_query(query, (token,), commit=True)
        query = 'INSERT OR REPLACE INTO settings tg_enabled = 1 WHERE key = "api_token"'
        self.tg_enabled = True  # Флаг: теперь синхронизировано

    def open_telegram_dialog(self):
        code, ok = QInputDialog.getText(self, "Связывание Telegram",
                                        "Введите код, который вам прислал бот в Telegram:")
        if ok and code:
            threading.Thread(target=self._perform_link_request, args=(str(code),)).start()

    def _perform_link_request(self, code: str):
        """Отправляет код связывания на сервер и получает API-токен (в рабочем потоке)."""
        url = f"{SERVER_URL}/auth/link"

        try:
            response = requests.post(url, json={"code": code})
            response.raise_for_status()
            data = response.json()

            api_token = data.get("api_token")
            if api_token:
                self._save_api_token(api_token)  # БЕЗОПАСНЫЙ ВЫЗОВ
                # Использование QTimer.singleShot для обновления UI из главного потока
                QTimer.singleShot(0, lambda: [
                    QMessageBox.information(self, "Успех", "Устройство успешно связано с Telegram!"),
                    self.tgButton.setText("Telegram (Связан)")
                ])
            else:
                QTimer.singleShot(0, lambda: QMessageBox.critical(
                    self, "Ошибка связывания", "Сервер не вернул API-токен."))

        except HTTPError as http_err:
            try:
                error_detail = http_err.response.json().get('detail', http_err.response.text)
            except:
                error_detail = http_err.response.text
            QTimer.singleShot(0, lambda: QMessageBox.critical(
                self, "Ошибка связывания", f"Ошибка сервера (HTTP {http_err.response.status_code}): {error_detail}"))

        except RequestException as req_err:
            QTimer.singleShot(0, lambda: QMessageBox.critical(
                self, "Ошибка сети", f"Не удалось подключиться к серверу: {req_err}"))

    def _send_to_server_thread(self, payload: dict, local_id: int):
        """Выполняет запрос на сервер с авторизацией и сохранением server_id (в рабочем потоке)."""

        token = self._get_api_token()  # БЕЗОПАСНЫЙ ВЫЗОВ
        if not token:
            print("Telegram не настроен, пропускаем синхронизацию.")
            return

        headers = {'Authorization': f'Bearer {token}'}  # Используем Bearer токен
        url = f"{SERVER_URL}/events"

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            server_id = data.get('id')

            if server_id:
                # Обновляем локальную запись, используя локальный ID (БЕЗОПАСНЫЙ ВЫЗОВ)
                query = '''
                    UPDATE events 
                    SET server_id = ? 
                    WHERE id = ?
                '''
                params = (server_id, local_id)
                self._execute_query(query, params, commit=True)
                print(f"Событие синхронизировано, server_id: {server_id} для local_id: {local_id}")

        except RequestException as req_err:
            print(f"Не удалось подключиться к серверу для синхронизации local_id={local_id}: {req_err}")

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
                    self._send_windows_notification(name, start, end)

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

        # 1. Сохранение локально и получение local_id
        query = '''
                    INSERT INTO events (name, event_date, time_start, time_end, server_id) 
                    VALUES (?, ?, ?, ?, NULL)
                '''
        params = (name, date_str, start_str, end_str)
        cursor = self._execute_query(query, params, commit=True)
        local_id = cursor.lastrowid if cursor else None  # Получаем ID только что вставленной записи

        if not local_id:
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить событие локально.")
            return

        # 2. Подготовка и отправка на сервер (ТОЛЬКО если Telegram включен)
        query = 'SELECT tg_enabled FROM settings WHERE key = "api_token"'
        cursor = self._execute_query(query, fetch_all=True)
        self.tg_enabled = (cursor[0][0])
        if self.tg_enabled and self._get_api_token():

            selected_date: QDate = self.calendarWidget.selectedDate()
            selected_time_start: QTime = self.timeStart.time()

            py_datetime = datetime.datetime(
                selected_date.year(), selected_date.month(), selected_date.day(),
                selected_time_start.hour(), selected_time_start.minute(), selected_time_start.second()
            )
            notify_at_str = py_datetime.strftime("%Y-%m-%d %H:%M:%S")

            payload = {
                'text': f'У вас запланировано событие {name} на {start_str} - {end_str}',
                'notify_at_str': notify_at_str
            }

            # Запуск синхронизации в потоке
            threading.Thread(target=self._send_to_server_thread, args=(payload, local_id)).start()
        else:
            QMessageBox.information(self, "Сохранено",
                                    "Событие сохранено локально. Для синхронизации свяжите Telegram.")

        # 3. Обновление UI
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
