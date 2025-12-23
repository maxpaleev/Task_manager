import sys
import datetime
import sqlite3
import requests
import json
from typing import Dict, List, Tuple
from requests.exceptions import RequestException, HTTPError

from plyer import notification

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate, QTime, QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QTreeWidgetItem, QMenu, QTreeWidget, QInputDialog, QColorDialog
)
from PyQt6.QtGui import QFont, QTextCharFormat, QColor

# SERVER_URL = "http://10.62.25.171:8000"
SERVER_URL = "http://127.0.0.1:8000"
DB_FILE = 'planner.db'
TASK_CATEGORIES = [
    "Срочно и важно",
    "Важно, но не срочно",
    "Срочно, но не важно",
    'Не срочно и не важно'
]


# --- НОВОЕ: Класс для безопасной работы с сетью ---
class NetworkWorker(QObject):
    finished = pyqtSignal(dict)  # Сигнал успеха
    error = pyqtSignal(str)  # Сигнал ошибки

    def __init__(self, url, method="POST", payload=None, token=None):
        super().__init__()
        self.url = url
        self.method = method
        self.payload = payload
        self.token = token

    # noinspection PyUnresolvedReferences
    def run(self):
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            if self.method == "POST":
                response = requests.post(self.url, json=self.payload, headers=headers)
            elif self.method == "DELETE":
                response = requests.delete(self.url, headers=headers, timeout=10)
            else:
                response = requests.get(self.url, headers=headers)

            response.raise_for_status()
            try:
                data = response.json()
            except:
                data = {}
            self.finished.emit(data)

        except HTTPError as http_err:
            try:
                detail = http_err.response.json().get('detail', http_err.response.text)
            except:
                detail = str(http_err)
            self.error.emit(f"Ошибка сервера: {detail}")
        except Exception as e:
            self.error.emit(f"Ошибка сети: {str(e)}")


class SimplePlanner(QMainWindow):

    def __init__(self):
        super().__init__()

        # Загрузка интерфейса из файла

        try:
            uic.loadUi('Client/design_test.ui', self)
        except Exception as e:
            # Если папка Client не найдена, ищем рядом
            try:
                uic.loadUi('design_test.ui', self)
            except:
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить интерфейс: {e}")
                sys.exit(1)

        self.setWindowTitle('Минипланировщик')

        # Инициализация переменных (ТВОЙ КОД)
        self.events: Dict[datetime.date, List[Tuple[str, datetime.date, datetime.time, datetime.time, int]]] = {}
        self.tasks: Dict[str, List[Tuple[str, str, int]]] = {cat: [] for cat in TASK_CATEGORIES}
        self.tg_enabled = False
        self.color = QColor('#FF7F50')
        self.current_date = 1
        self._init_db()
        self.global_font = QFont('Segoe UI', 8)
        app.setFont(self.global_font)

        self.load_data()
        self.current_importance = TASK_CATEGORIES[0]

        self._setup_tree_widgets()

        # Инициализация таймера (ТВОЙ КОД)
        self.last_alert_minute = -1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_alerts)
        self.timer.start(5000)

        # Соединение сигналов (ТВОЙ КОД)
        self.addEventBtn.clicked.connect(self.add_event)
        self.calendarWidget.clicked.connect(self.date_changed_widget)
        self.searchEvent.textChanged.connect(self.update_event_list)
        self.taskButton.clicked.connect(self.add_task)
        self.searchTask.textChanged.connect(self.update_task_list)
        self.importanceChoice.buttonClicked.connect(self._set_importance)
        self.taskDes.setMaxLength(100)
        self.tgButton.clicked.connect(self.open_telegram_dialog)
        self.fontsize.valueChanged.connect(self.change_font_size)
        self.fontBox.currentTextChanged.connect(self.change_font)
        self.colorButton.clicked.connect(self.change_color)
        self.reset_colorButton.clicked.connect(self.reset_color)

    def change_font_size(self):
        size = self.fontsize.value()
        font = self.fontBox.currentText()
        self.global_font.setPointSize(size)
        app.setFont(self.global_font)
        query = "INSERT OR REPLACE INTO settings (id, font_size, font) VALUES (1, ?, ?)"
        self._execute_query(query, (size, font,), commit=True)

    def change_font(self):
        size = self.fontsize.value()
        font = self.fontBox.currentText()
        self.global_font.setFamily(font)
        app.setFont(self.global_font)
        query = "INSERT OR REPLACE INTO settings (id, font, font_size) VALUES (1, ?, ?)"
        self._execute_query(query, (font, size,), commit=True)

    def change_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.color = color
            self.update_event_list()
            query = "INSERT OR REPLACE INTO settings (id, color) VALUES (1, ?)"
            self._execute_query(query, (color.name(),), commit=True)

    def reset_color(self):
        if self.color.isValid():
            self.color = QColor('#FF7F50')
            self.update_event_list()
            query = "INSERT OR REPLACE INTO settings (id, color) VALUES (1, ?)"
            self._execute_query(query, ('#FF7F50',), commit=True)

    def date_changed_widget(self):
        if self.calendarWidget.selectedDate() and self.current_date == 1:
            self.dateStart.setDate(self.calendarWidget.selectedDate())
            self.dateEnd.setDate(self.calendarWidget.selectedDate())
            self.current_date = 2
        elif self.calendarWidget.selectedDate() and self.current_date == 2:
            self.dateEnd.setDate(self.calendarWidget.selectedDate())
            self.current_date = 1

    # -------------------------------------------------------------------
    # ОБЩИЙ МЕТОД ДЛЯ РАБОТЫ С БД
    # -------------------------------------------------------------------

    def _execute_query(self, query: str, params: Tuple = (), commit: bool = False, fetch_all: bool = False):
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(query, params)

            if commit:
                conn.commit()

            if fetch_all:
                return cursor.fetchall()

            return cursor

        except sqlite3.Error as e:
            print(f"Ошибка БД: {e}")
            return None
        finally:
            if conn:
                conn.close()

    # -------------------------------------------------------------------
    # ЛОГИКА БД
    # -------------------------------------------------------------------

    def _init_db(self):
        """Инициализация локальной базы данных SQLite."""
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    is_completed INTEGER DEFAULT 0,
                    server_id INTEGER NULL
                )
            ''')

            queries = [
                '''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT NOT NULL,
                    is_completed INTEGER DEFAULT 0
                )
                ''',
                '''
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    value TEXT,
                    tg_enabled INTEGER,
                    font_size INTEGER DEFAULT 8,
                    font TEXT DEFAULT 'Segoe UI',
                    color TEXT DEFAULT '#FF7F50'
                )
                '''
            ]
            for query in queries:
                cursor.execute(query)

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

        event_rows = self._execute_query(
            "SELECT name, start_date, end_date, time_start, time_end, is_completed FROM events ORDER BY start_date, "
            "time_start",
            fetch_all=True
        )
        if event_rows:
            for name, start_date, end_date, time_start, time_end, is_completed in event_rows:
                try:
                    date_start_obj = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
                    date_end_obj = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
                    time_start_obj = datetime.datetime.strptime(time_start, "%H:%M").time()
                    time_end_obj = datetime.datetime.strptime(time_end, "%H:%M").time()

                    if date_start_obj not in self.events:
                        self.events[date_start_obj] = []
                    self.events[date_start_obj].append((name, date_end_obj, time_start_obj, time_end_obj, is_completed))
                except ValueError:
                    self.QMessageBox.warning(self, "Ошибка", "Некорректные данные в базе данных")

        task_rows = self._execute_query(
            "SELECT name, description, category, is_completed FROM tasks",
            fetch_all=True
        )
        if task_rows:
            for name, desc, cat, is_completed in task_rows:
                if cat in self.tasks:
                    self.tasks[cat].append((name, desc, is_completed))

        self.tg_enabled = self._execute_query('SELECT tg_enabled FROM settings', fetch_all=True)
        if self.tg_enabled:
            if self.tg_enabled[0][0] == 1:
                self.tgButton.setText('Связано')

        size = self._execute_query('SELECT font_size FROM settings', fetch_all=True)
        font = self._execute_query('SELECT font FROM settings', fetch_all=True)
        color = self._execute_query('SELECT color FROM settings', fetch_all=True)
        if size:
            self.fontsize.setValue(size[0][0])
            self.global_font.setPointSize(size[0][0])
            app.setFont(self.global_font)
        if font:
            self.fontBox.setCurrentText(font[0][0])
            self.global_font.setFamily(font[0][0])
            app.setFont(self.global_font)
        if color != '#FF7F50':
            if color:
                self.color = QColor(color[0][0])
                self.update_event_list()

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

    def show_context_menu(self, tree_widget, position):
        item = tree_widget.itemAt(position)
        if not item:
            return

        menu = QMenu(self)

        # Новые действия
        action_toggle_done = None

        # Проверяем, что это список событий и это само событие (а не дата)
        if tree_widget is self.eventList and item.parent():
            # Получаем данные, чтобы понять, какой текст показать
            ev_data = item.data(0, Qt.ItemDataRole.UserRole)
            is_completed = ev_data[4]  # 4-й элемент
            text = "Отменить выполнение" if is_completed else "Выполнить"
            action_toggle_done = menu.addAction(text)
            menu.addSeparator()

        if tree_widget is self.taskList and item.parent():
            task_data = item.data(0, Qt.ItemDataRole.UserRole)
            is_completed = task_data[2]
            text = "Отменить выполнение" if is_completed else "Выполнить"
            action_toggle_done = menu.addAction(text)
            menu.addSeparator()

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

        # Обработка нового действия
        if action == action_toggle_done:
            if tree_widget is self.taskList:
                self._toggle_task_completion(item)
            elif tree_widget is self.eventList:
                self._toggle_event_completion(item)
        elif action == action_del:
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

            name, end_date, start, end, _ = event_data
            self.eventName.setText(name)
            self.timeStart.setTime(QTime(start.hour, start.minute))
            self.timeEnd.setTime(QTime(end.hour, end.minute))
            self.dateStart.setDate(QDate(event_date.year, event_date.month, event_date.day))
            self.dateEnd.setDate(QDate(end_date.year, end_date.month, end_date.day))
            self.calendarWidget.setSelectedDate(QDate(event_date.year, event_date.month, event_date.day))

        elif tree_widget is self.taskList:
            category_name = parent.data(0, Qt.ItemDataRole.UserRole)
            task_data = item.data(0, Qt.ItemDataRole.UserRole)

            self._delete_task_logic(item)

            name, desc, _ = task_data
            self.taskName.setText(name)
            self.taskDes.setText(desc)

            self.current_importance = category_name
            for btn in self.importanceChoice.buttons():
                if btn.event_name() == category_name:
                    btn.setChecked(True)
                    break

    # -------------------------------------------------------------------
    # ЛОГИКА Telegram
    # -------------------------------------------------------------------

    def _get_api_token(self) -> str | None:
        query = "SELECT value FROM settings WHERE id = 1"
        cursor = self._execute_query(query, fetch_all=True)
        return cursor[0][0] if cursor else None

    def _save_api_token(self, token: str):
        query = "INSERT OR REPLACE INTO settings (id, value) VALUES ('1', ?)"
        self._execute_query(query, (token,), commit=True)
        # Доп запрос для флага, если нужно
        self._execute_query("UPDATE settings SET tg_enabled = 1 WHERE id = 1", commit=True)
        self.tg_enabled = True

    def _run_worker(self, url, payload, on_success):
        """Вспомогательный метод для запуска потока"""
        self.thread = QThread()
        self.worker = NetworkWorker(url, payload=payload)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(on_success)
        self.worker.error.connect(lambda err: QMessageBox.warning(self, "Ошибка сети", err))

        # Очистка
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def open_telegram_dialog(self):
        code, ok = QInputDialog.getText(self, "Связывание Telegram",
                                        "Напишите боту(@MaxPal_bot) '/start' и введите код, полученный  от него")
        if ok and code:
            self.tgButton.setEnabled(False)
            self.tgButton.setText("Загрузка...")

            # ЗАПУСК ЧЕРЕЗ WORKER (вместо threading)
            self._run_worker(
                url=f"{SERVER_URL}/auth/link",
                payload={"code": str(code)},
                on_success=self._on_link_success
            )

    def _on_link_success(self, data):
        """Слот при успешном связывании"""
        api_token = data.get("api_token")
        if api_token:
            self._save_api_token(api_token)
            QMessageBox.information(self, "Успех", "Устройство успешно связано с Telegram!")
            self.tgButton.setText("Telegram (Связан)")
        else:
            QMessageBox.critical(self, "Ошибка", "Сервер не вернул токен.")
        self.tgButton.setEnabled(True)

    # -------------------------------------------------------------------
    # ЛОГИКА УВЕДОМЛЕНИЙ
    # -------------------------------------------------------------------

    def check_alerts(self):
        current_time = datetime.datetime.now().time()
        current_date = datetime.date.today()

        if self.last_alert_minute == current_time.minute:
            return

        self.last_alert_minute = current_time.minute

        if current_date in self.events:
            for event in self.events[current_date]:
                name, _, start, end, _ = event
                if start.hour == current_time.hour and start.minute == current_time.minute:
                    self._send_windows_notification(name, start, end)

    def _send_windows_notification(self, title, time_s, time_e):
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
    # ЛОГИКА СОБЫТИЙ
    # -------------------------------------------------------------------

    def add_event(self):
        name = self.eventName.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название события")
            return
        date_start = self.dateStart.date().toPyDate()
        date_end = self.dateEnd.date().toPyDate()
        start_py = self.timeStart.time().toPyTime()
        end_py = self.timeEnd.time().toPyTime()

        if end_py < start_py and date_start <= date_end:
            QMessageBox.warning(self, "Ошибка", "Время окончания не может быть раньше начала")
            return

        date_start_str = date_start.strftime("%Y-%m-%d")
        date_end_str = date_end.strftime("%Y-%m-%d")
        start_str = start_py.strftime("%H:%M")
        end_str = end_py.strftime("%H:%M")

        # 1. Сохранение локально (ТВОЙ КОД)
        query = '''
                    INSERT INTO events (name, start_date, end_date, time_start, time_end, server_id, is_completed) 
                    VALUES (?, ?, ?, ?, ?, NULL, 0)
                '''
        params = (name, date_start_str, date_end_str, start_str, end_str)
        cursor = self._execute_query(query, params, commit=True)
        local_id = cursor.lastrowid if cursor else None

        if not local_id:
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить событие локально.")
            return

        # 2. Подготовка и отправка на сервер (ЧЕРЕЗ WORKER)
        token = self._get_api_token()
        if token:
            # Получаем полный datetime для сервера
            start_date = self.dateStart.date().toPyDate()
            end_date = self.dateEnd.date().toPyDate()
            selected_time_start = self.timeStart.time()
            start_str = datetime.datetime.combine(start_date, selected_time_start.toPyTime())
            # Внимание: здесь используем тот формат, который ждет твой schema.py
            notify_at_str = start_str.strftime("%Y-%m-%d %H:%M")

            payload = {
                'event_name': f'Событие: {name}',
                'event_start': start_date.strftime("%Y-%m-%d"),
                'event_end': end_date.strftime("%Y-%m-%d"),
                'time_start': start_str.strftime("%H:%M"),
                'time_end': end_str.strftime("%H:%M"),
                'notify_at': notify_at_str
            }

            # Создаем поток для отправки события
            self.event_thread = QThread()
            self.event_worker = NetworkWorker(f"{SERVER_URL}/events", payload=payload, token=token)
            self.event_worker.moveToThread(self.event_thread)

            # При успехе обновляем server_id в БД
            self.event_thread.started.connect(self.event_worker.run)
            self.event_worker.finished.connect(lambda res: self._on_event_sent(res, local_id))

            # Очистка
            self.event_worker.finished.connect(self.event_thread.quit)
            self.event_worker.finished.connect(self.event_worker.deleteLater)
            self.event_thread.finished.connect(self.event_thread.deleteLater)
            self.event_thread.start()

        else:
            QMessageBox.information(self, "Сохранено", "Событие сохранено локально.")

        # 3. Обновление UI (ТВОЙ КОД)
        self.eventName.clear()
        self.dateStart.setDate(QDate.currentDate())
        self.dateEnd.setDate(QDate.currentDate())
        self.timeStart.setTime(QTime(0, 0))
        self.timeEnd.setTime(QTime(0, 0))
        self.load_data()

    def _on_event_sent(self, response, local_id):
        """Обновляем server_id после успешной отправки"""
        server_id = response.get('id')
        if server_id:
            query = "UPDATE events SET server_id = ? WHERE id = ?"
            self._execute_query(query, (server_id, local_id), commit=True)
            print(f"Синхронизировано: local={local_id}, server={server_id}")

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

                date = QDate(date_key.year, date_key.month, date_key.day)
                fmt = QTextCharFormat()
                fmt.setBackground(self.color)
                self.calendarWidget.setDateTextFormat(date, fmt)
                # Устанавливаем формат даты в календаре idget
                root_item.setData(0, Qt.ItemDataRole.UserRole, date_key)

                for ev in sorted(matching, key=lambda x: (x[1], x[3])):
                    name, date_end, start, end, is_completed = ev
                    if date_end == date:
                        time_str = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
                    else:
                        time_str = f"{datetime.datetime.combine(date_key, start).strftime('%d.%m.%Y %H:%M')} - {datetime.datetime.combine(date_end, end).strftime('%d.%m.%Y %H:%M')}"
                    child = QTreeWidgetItem([name, time_str])
                    child.setData(0, Qt.ItemDataRole.UserRole, ev)
                    if is_completed:
                        fmt.clearBackground()
                        self.calendarWidget.setDateTextFormat(date, fmt)
                        # Шрифт зачеркнутый
                        font = child.font(0)
                        font.setStrikeOut(True)
                        child.setFont(0, font)
                        child.setFont(1, font)

                        # Цвет серый
                        gray_brush = QColor('gray')
                        child.setForeground(0, gray_brush)
                        child.setForeground(1, gray_brush)
                    root_item.addChild(child)

                items.append(root_item)

        self.eventList.insertTopLevelItems(0, items)
        if search:
            self.eventList.expandAll()

    def _delete_event_logic(self, item):
        if item.parent():
            # --- Удаление конкретного события ---

            # Получаем данные события
            date_key = item.parent().data(0, Qt.ItemDataRole.UserRole)
            ev_data = item.data(0, Qt.ItemDataRole.UserRole)
            name, date_end, start_time, end_time, _ = ev_data

            date_str = date_key.strftime("%Y-%m-%d")
            date_end_str = date_end.strftime("%Y-%m-%d")
            start_str = start_time.strftime("%H:%M")
            end_str = end_time.strftime("%H:%M")

            # 1. Получаем server_id из локальной БД (ДО удаления!)
            query_select = '''
                SELECT server_id FROM events 
                WHERE name = ? AND start_date = ? AND end_date = ? AND time_start = ? AND time_end = ?
            '''
            params_select = (name, date_str, date_end_str, start_str, end_str)

            result = self._execute_query(query_select, params_select, fetch_all=True)

            # Извлекаем server_id
            server_id_to_delete = result[0][0] if result and result[0] and result[0][0] else None

            # 2. Локальное удаление
            query_delete = '''
                DELETE FROM events 
                WHERE name = ? AND start_date = ? AND end_date = ? AND time_start = ? AND time_end = ?
            '''
            self._execute_query(query_delete, params_select, commit=True)
            date = QDate(date_key.year, date_key.month, date_key.day)
            fmt = QTextCharFormat()
            fmt.clearBackground()
            self.calendarWidget.setDateTextFormat(date, fmt)
            self.load_data()  # Обновляем UI сразу же, чтобы удаление казалось мгновенным

            # 3. Если есть server_id и токен, запускаем синхронизацию на сервере
            token = self._get_api_token()
            if server_id_to_delete and token:
                # Блокируем кнопку, чтобы избежать повторного нажатия (опционально)
                # ВАЖНО: Создаем НОВЫЕ worker и thread, как в вашем стиле,
                # но для безопасности используем локальные переменные
                self.thread = QThread()
                self.worker = NetworkWorker(
                    url=f"{SERVER_URL}/events/{server_id_to_delete}",
                    method="DELETE",  # Используем метод DELETE
                    token=token
                )

                self.worker.moveToThread(self.thread)
                self.thread.started.connect(self.worker.run)

                # Безопасная очистка (как в предыдущих рекомендациях)
                self.worker.finished.connect(self.thread.quit)
                self.worker.finished.connect(self.worker.deleteLater)
                self.thread.finished.connect(self.thread.deleteLater)
                self.worker.error.connect(self.thread.quit)  # Очистка при ошибке
                self.worker.error.connect(self.worker.deleteLater)
                self.thread.finished.connect(self.thread.deleteLater)

                self.thread.start()

        else:
            # --- Удаление всех событий за день (без синхронизации) ---
            QMessageBox.information(self, "Внимание", "При удалении целого дня, удаление происходит только локально.")
            date_key = item.data(0, Qt.ItemDataRole.UserRole)
            date_str = date_key.strftime("%Y-%m-%d")
            date = QDate(date_key.year, date_key.month, date_key.day)
            fmt = QTextCharFormat()
            fmt.clearBackground()
            self.calendarWidget.setDateTextFormat(date, fmt)

            query_delete_all = '''DELETE FROM events WHERE event_date = ?'''
            self._execute_query(query_delete_all, (date_str,), commit=True)
            self.load_data()

    def _toggle_event_completion(self, item):
        data_key = item.parent().data(0, Qt.ItemDataRole.UserRole)
        ev_data = item.data(0, Qt.ItemDataRole.UserRole)
        name, date_end, start_time, end_time, is_completed = ev_data

        date_str = data_key.strftime("%Y-%m-%d")
        date_end_str = date_end.strftime("%Y-%m-%d")
        start_str = start_time.strftime("%H:%M")
        end_str = end_time.strftime("%H:%M")

        new_status = 0 if is_completed else 1

        query = '''
                    UPDATE events 
                    SET is_completed = ? 
                    WHERE name = ? AND start_date = ? AND end_date = ? AND time_start = ? AND time_end = ?
                '''
        params = (new_status, name, date_str, date_end_str, start_str, end_str)
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
            '''INSERT INTO tasks (name, description, category, is_completed) VALUES (?, ?, ?, 0)''',
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

                for t in sorted(matching, key=lambda x: x[2]):
                    name, desc, is_completed = t
                    child = QTreeWidgetItem([name, desc])
                    child.setData(0, Qt.ItemDataRole.UserRole, t)
                    if is_completed:
                        font = child.font(0)
                        font.setStrikeOut(True)
                        child.setFont(0, font)
                        child.setFont(1, font)

                        gray_brush = QColor('gray')
                        child.setForeground(0, gray_brush)
                        child.setForeground(1, gray_brush)
                    root.addChild(child)

                items.append(root)

        self.taskList.insertTopLevelItems(0, items)
        if search:
            self.taskList.expandAll()

    def _delete_task_logic(self, item):
        if item.parent():
            cat = item.parent().data(0, Qt.ItemDataRole.UserRole)
            t_data = item.data(0, Qt.ItemDataRole.UserRole)

            query = '''DELETE FROM tasks WHERE name = ? AND description = ? AND category = ?'''
            params = (t_data[0], t_data[1], cat)
        else:
            cat = item.data(0, Qt.ItemDataRole.UserRole)
            query = '''DELETE FROM tasks WHERE category = ?'''
            params = (cat,)

        self._execute_query(query, params, commit=True)
        self.load_data()

    def _toggle_task_completion(self, item):
        """Переключает статус выполнения события"""
        cat = item.parent().data(0, Qt.ItemDataRole.UserRole)
        task = item.data(0, Qt.ItemDataRole.UserRole)
        name, desc, is_completed = task

        # Инвертируем статус (1-0 или 0-1)
        new_status = 0 if is_completed else 1

        query = '''
            UPDATE tasks 
            SET is_completed = ? 
            WHERE name = ? AND description = ? AND category = ?
        '''
        params = (new_status, name, desc, cat)

        self._execute_query(query, params, commit=True)
        self.load_data()  # Перезагружаем интерфейс


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())
