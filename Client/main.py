import os
import sys
import datetime
import sqlite3

import requests
from datetime import datetime
from typing import Dict, List, Tuple
from plyer import notification

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate, QTime, QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QTreeWidgetItem, QMenu, QTreeWidget, QInputDialog, QColorDialog,
    QSystemTrayIcon, QStyle
)
from PyQt6.QtGui import QFont, QTextCharFormat, QColor, QAction, QIcon

# --- ГЛОБАЛЬНЫЕ КОНСТАНТЫ ---
# SERVER_URL = "http://10.62.25.171:8000"
SERVER_URL = "http://127.0.0.1:8000"
DB_FILE = 'planner.db'
TASK_CATEGORIES = [
    "Срочно и важно",
    "Важно, но не срочно",
    "Срочно, но не важно",
    'Не срочно и не важно'
]


# ===================================================================
# БЛОК 1: СЕТЕВАЯ ИНФРАСТРУКТУРА (МНОГОПОТОЧНОСТЬ)
# ===================================================================

class NetworkWorker(QObject):
    finished = pyqtSignal(object)  # Сигнал успеха с данными
    error = pyqtSignal(str)  # Сигнал ошибки с текстом

    def __init__(self, url: str, method="POST", payload: dict = None, token: str = None):
        super().__init__()
        self.url = url
        self.method = method
        self.payload = payload
        self.headers = {'Authorization': f'Bearer {token}'} if token else {}

    def run(self):
        try:
            if self.method == "POST":
                resp = requests.post(self.url, json=self.payload, headers=self.headers)
            elif self.method == "DELETE":
                resp = requests.delete(self.url, headers=self.headers)
            elif self.method == "PATCH":
                resp = requests.patch(self.url, json=self.payload, headers=self.headers)
            elif self.method == "GET":
                resp = requests.get(self.url, headers=self.headers)

            resp.raise_for_status()
            data = resp.json() if resp.content else {}
            self.finished.emit(data)

        except requests.exceptions.RequestException as e:
            self.error.emit(f"Ошибка сети: {str(e)}")
        except Exception as e:
            self.error.emit(f"Ошибка: {str(e)}")


# ===================================================================
# БЛОК 2: ОСНОВНОЕ ПРИЛОЖЕНИЕ
# ===================================================================

class SimplePlanner(QMainWindow):

    def __init__(self):
        super().__init__()
        try:
            uic.loadUi('Client/design_test.ui', self)
        except Exception as e:
            try:
                uic.loadUi('design_test.ui', self)
            except:
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить интерфейс: {e}")
                sys.exit(1)

        self.setWindowTitle('Секретарь')

        # --- Состояние данных ---
        self.events: Dict[datetime.date, List[Tuple[str, datetime.date, datetime.time, datetime.time, int]]] = {}
        self.tasks: Dict[str, List[Tuple[str, str, int]]] = {cat: [] for cat in TASK_CATEGORIES}
        self.tg_enabled = False
        self.color = QColor('#FF7F50')
        self.past_color = QColor('#FF9F7C')
        self.current_date = 1
        self.current_importance = TASK_CATEGORIES[0]
        self.global_font = QFont('Segoe UI', 8)

        # --- Настройка системы ---
        self._init_db()
        self.load_data()
        self.sync_all()
        self._setup_tree_widgets()
        app.setFont(self.global_font)

        # --- Настройка таймера для уведомлений ---
        self.last_alert_minute = -1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_alerts)
        self.timer.start(60000)

        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self.sync_all)
        self.sync_timer.start(300000)  # 5 минут

        # --- Подключение сигналов (Events) ---
        self.addEventBtn.clicked.connect(self.add_event)
        self.calendarWidget.clicked.connect(self.date_changed_widget)
        self.searchEvent.textChanged.connect(self.update_event_list)

        # --- Подключение сигналов (Tasks) ---
        self.taskButton.clicked.connect(self.add_task)
        self.searchTask.textChanged.connect(self.update_task_list)
        self.importanceChoice.buttonClicked.connect(self._set_importance)
        self.taskDes.setMaxLength(100)
        # --- Настройки и Внешний вид ---
        self.tgButton.clicked.connect(self.open_telegram_dialog)
        self.fontsize.valueChanged.connect(self.change_font_size)
        self.fontBox.currentTextChanged.connect(self.change_font)
        self.colorButton.clicked.connect(self.change_color)
        self.reset_colorButton.clicked.connect(self.reset_color)
        self.syncButton.clicked.connect(self.sync_all)
        self._setup_tray_icon()

    # -------------------------------------------------------------------
    # БЛОК 3: РАБОТА С БАЗОЙ ДАННЫХ
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

    def _init_db(self):
        conn = None
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            queries = [
                '''
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
                ''',
                '''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT NOT NULL,
                    is_completed INTEGER DEFAULT 0,
                    server_id INTEGER NULL
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

        # Загрузка событий
        event_rows = self._execute_query(
            "SELECT name, start_date, end_date, time_start, time_end, is_completed FROM events ORDER BY start_date, time_start",
            fetch_all=True
        )
        if event_rows:
            for name, start_date, end_date, time_start, time_end, is_completed in event_rows:
                try:
                    date_start_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                    date_end_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                    time_start_obj = datetime.strptime(time_start, "%H:%M").time()
                    time_end_obj = datetime.strptime(time_end, "%H:%M").time()
                    if date_start_obj not in self.events:
                        self.events[date_start_obj] = []
                    self.events[date_start_obj].append((name, date_end_obj, time_start_obj, time_end_obj, is_completed))
                except ValueError:
                    print("Ошибка парсинга даты/времени")

        # Загрузка задач
        task_rows = self._execute_query("SELECT name, description, category, is_completed FROM tasks", fetch_all=True)
        if task_rows:
            for name, desc, cat, is_completed in task_rows:
                if cat in self.tasks:
                    self.tasks[cat].append((name, desc, is_completed))

        # Загрузка настроек
        settings_res = self._execute_query('SELECT tg_enabled, font_size, font, color FROM settings WHERE id = 1',
                                           fetch_all=True)
        if settings_res:
            tg_en, size, font, color = settings_res[0]
            if tg_en == 1: self.tgButton.setText('Связано')
            if size:
                self.fontsize.setValue(size)
                self.global_font.setPointSize(size)
            if font:
                self.fontBox.setCurrentText(font)
                self.global_font.setFamily(font)
            if color and color != '#FF7F50':
                self.color = QColor(color)
            app.setFont(self.global_font)

        self.update_event_list()
        self.update_task_list()

    # -------------------------------------------------------------------
    # БЛОК 4: ИНТЕРФЕЙС СПИСКОВ (TreeWidgets) И КОНТЕКСТНЫЕ МЕНЮ
    # -------------------------------------------------------------------

    def _setup_tree_widgets(self):
        """Первоначальная настройка QTreeWidget"""
        for tw, labels in [(self.eventList, ["Событие", "Время"]), (self.taskList, ["Название", "Описание"])]:
            tw.setColumnCount(2)
            tw.setHeaderLabels(labels)
            tw.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tw.customContextMenuRequested.connect(lambda pos, widget=tw: self.show_context_menu(widget, pos))

    def show_context_menu(self, tree_widget, position):
        item = tree_widget.itemAt(position)
        if not item: return

        menu = QMenu(self)
        action_toggle_done = None

        if tree_widget is self.eventList and item.parent():
            ev_data = item.data(0, Qt.ItemDataRole.UserRole)
            is_completed = ev_data[4]
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
                if btn.text() == category_name:
                    btn.setChecked(True)
                    break

    # -------------------------------------------------------------------
    # БЛОК 5: ЛОГИКА ТЕЛЕГРАМ И СЕТИ
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
                                        "Напишите боту(@MaxPal_bot) '/start' и введите код, полученный  от него. Предыдущие записи не будут привязаны(используйте редактировать чтобы пересоздать)")
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
    # БЛОК 6: ЛОГИКА УВЕДОМЛЕНИЙ (Windows Notifications)
    # -------------------------------------------------------------------

    def check_alerts(self):
        print('check')
        current_time = datetime.now().time()
        current_date = datetime.today().date()

        if self.last_alert_minute == current_time.minute:
            return

        self.last_alert_minute = current_time.minute

        if current_date in self.events.keys():
            for event in self.events[current_date]:
                print(event)
                name, date_start, date_end, time_start, time_end, _ = 0,0,0,0,0,0
                if len(event) == 5:
                    name, date_start, time_start, time_end, _ = event
                    date_end = date_start
                else:
                    name, date_start, date_end, time_start, time_end, _ = event
                date_start = datetime.combine(date_start, time_start)
                date_end = datetime.combine(date_end, time_end)
                if time_start.hour == current_time.hour and time_start.minute == current_time.minute:
                    self._send_windows_notification(name, date_start, date_end)

    def _send_windows_notification(self, title, date_start, date_end):
        print('notification')
        time_s_str = date_start.strftime("%Y-%m-%d %H:%M")
        time_e_str = date_start.strftime("%Y-%m-%d %H:%M")
        try:
            notification.notify(
                title=f"Событие: {title}",
                message=f"Запланировано событие на время: \n{time_s_str} - {time_e_str}",
                app_name="Минипланировщик",
                timeout=10
            )
        except Exception as e:
            print(f"Не удалось отправить Windows уведомление: {e}")

    # -------------------------------------------------------------------
    # БЛОК 7: УПРАВЛЕНИЕ СОБЫТИЯМИ (Events)
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

        if datetime.combine(date_start, start_py) > datetime.combine(date_end, end_py):
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
            start_str = datetime.combine(date_start, start_py)
            notify_at_str = start_str.strftime("%Y-%m-%d %H:%M")

            payload = {
                'event_name': name,
                'start_date': date_start.strftime("%Y-%m-%d"),
                'end_date': date_end.strftime("%Y-%m-%d"),
                'time_start': start_py.strftime("%H:%M"),
                'time_end': end_py.strftime("%H:%M"),
                'is_completed': 0,
                'notify_at': notify_at_str
            }
            print(payload)

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

        # --- 1. ОЧИСТКА И РАСЧЕТ ЦВЕТОВ КАЛЕНДАРЯ ---
        # Инициализируем множество покрашенных дат, если его нет (для очистки при следующем обновлении)
        if not hasattr(self, 'painted_dates'):
            self.painted_dates = set()

        # Сбрасываем форматирование для ранее покрашенных дат
        clean_fmt = QTextCharFormat()
        for d in self.painted_dates:
            self.calendarWidget.setDateTextFormat(d, clean_fmt)
        self.painted_dates.clear()

        # Словарь статусов дней: 2 - Активно (нужен цвет), 1 - Выполнено (без цвета или серый)
        day_status_map: Dict[QDate, int] = {}

        # Проходим по всем событиям, чтобы определить статус каждого дня
        for date_key, events_list in self.events.items():
            for ev in events_list:
                _, date_end_obj, _, _, is_completed = ev
                if is_completed:
                    continue

                # Правильный цикл по датам (с учетом перехода месяцев)
                d_start = QDate(date_key.year, date_key.month, date_key.day)
                d_end = QDate(date_end_obj.year, date_end_obj.month, date_end_obj.day)

                curr_date = d_start
                while curr_date <= d_end:
                    # Приоритет: Активное событие (2) важнее выполненного (1)
                    is_boundary = (curr_date == d_start or curr_date == d_end)
                    new_status = 2 if is_boundary else 1

                    current_status = day_status_map.get(curr_date, 0)
                    if new_status > current_status:
                        day_status_map[curr_date] = new_status

                    curr_date = curr_date.addDays(1)

        # Применяем цвета только для Активных дней (status == 2)
        fmt_active = QTextCharFormat()
        fmt_active.setBackground(self.color)

        fmt_intermediate = QTextCharFormat()
        # Делаем промежуточный цвет бледнее (добавляем прозрачность или осветляем)  # Значение от 0 до 255 (100 — полупрозрачный)
        fmt_intermediate.setBackground(QColor('#FF9F7C'))

        for q_date, status in day_status_map.items():
            if status == 2:
                self.calendarWidget.setDateTextFormat(q_date, fmt_active)
            elif status == 1:
                self.calendarWidget.setDateTextFormat(q_date, fmt_intermediate)
            self.painted_dates.add(q_date)

        # --- 2. ЗАПОЛНЕНИЕ СПИСКА (TREE WIDGET) ---
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

                for ev in sorted(matching, key=lambda x: (x[4], x[2])):
                    name, date_end, start, end, is_completed = ev

                    # Формирование строки времени
                    if date_key == date_end:
                        time_str = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
                    else:
                        time_str = f"{datetime.combine(date_key, start).strftime('%d.%m.%Y %H:%M')} - {datetime.combine(date_end, end).strftime('%d.%m.%Y %H:%M')}"

                    child = QTreeWidgetItem([name, time_str])
                    child.setData(0, Qt.ItemDataRole.UserRole, ev)

                    if is_completed:
                        font = child.font(0)
                        font.setStrikeOut(True)
                        child.setFont(0, font)
                        child.setFont(1, font)

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
            date_key = item.parent().data(0, Qt.ItemDataRole.UserRole)
            ev_data = item.data(0, Qt.ItemDataRole.UserRole)
            name, date_end, start_time, end_time, _ = ev_data

            date_str = date_key.strftime("%Y-%m-%d")
            date_end_str = date_end.strftime("%Y-%m-%d")
            start_str = start_time.strftime("%H:%M")
            end_str = end_time.strftime("%H:%M")

            # 1. Получаем server_id
            query_select = '''
                SELECT server_id FROM events 
                WHERE name = ? AND start_date = ? AND end_date = ? AND time_start = ? AND time_end = ?
            '''
            params_select = (name, date_str, date_end_str, start_str, end_str)
            result = self._execute_query(query_select, params_select, fetch_all=True)
            server_id_to_delete = result[0][0] if result and result[0] else None

            # 2. Локальное удаление
            query_delete = '''
                DELETE FROM events 
                WHERE name = ? AND start_date = ? AND end_date = ? AND time_start = ? AND time_end = ?
            '''
            self._execute_query(query_delete, params_select, commit=True)

            # 3. Синхронизация с сервером
            token = self._get_api_token()
            if server_id_to_delete and token:
                self.thread = QThread()
                self.worker = NetworkWorker(
                    url=f"{SERVER_URL}/events/{server_id_to_delete}",
                    method="DELETE",
                    token=token
                )
                self.worker.moveToThread(self.thread)
                self.thread.started.connect(self.worker.run)
                self.worker.finished.connect(self.thread.quit)
                self.worker.finished.connect(self.worker.deleteLater)
                self.thread.finished.connect(self.thread.deleteLater)
                self.thread.start()

            # Обновляем UI (автоматически перерисует календарь)
            self.load_data()

        else:
            # --- Удаление всех событий за день ---
            date_key = item.data(0, Qt.ItemDataRole.UserRole)
            date_str = date_key.strftime("%Y-%m-%d")

            # Получаем ID для удаления с сервера
            server_id_to = 'SELECT server_id FROM events WHERE start_date = ?'
            res = self._execute_query(server_id_to, (date_str,), fetch_all=True)

            # Локальное удаление
            query_delete = "DELETE FROM events WHERE start_date = ?"
            self._execute_query(query_delete, (date_str,), commit=True)

            token = self._get_api_token()
            if token and res:
                ids = [i[0] for i in res if i[0]]
                if ids:
                    ids_str = '_'.join(map(str, ids))
                    self.thread = QThread()
                    self.worker = NetworkWorker(
                        url=f"{SERVER_URL}/events/{ids_str}",
                        method="DELETE",
                        token=token
                    )
                    self.worker.moveToThread(self.thread)
                    self.thread.started.connect(self.worker.run)
                    self.worker.finished.connect(self.thread.quit)
                    self.worker.finished.connect(self.worker.deleteLater)
                    self.thread.finished.connect(self.thread.deleteLater)
                    self.thread.start()

            # Обновляем UI
            self.load_data()

    def _toggle_event_completion(self, item):
        data_key = item.parent().data(0, Qt.ItemDataRole.UserRole)
        ev_data = item.data(0, Qt.ItemDataRole.UserRole)
        name, date_end, start_time, end_time, is_completed = ev_data

        date_str = data_key.strftime("%Y-%m-%d")
        date_end_str = date_end.strftime("%Y-%m-%d")
        start_str = start_time.strftime("%H:%M")
        end_str = end_time.strftime("%H:%M")

        query_sel = 'SELECT server_id FROM events WHERE name = ? AND start_date = ? AND end_date = ? AND time_start = ? AND time_end = ?'
        res = self._execute_query(query_sel, (name, date_str, date_end_str, start_str, end_str), fetch_all=True)
        server_id = res[0][0] if res and res[0] else None

        new_status = 0 if is_completed else 1

        query = '''
                    UPDATE events 
                    SET is_completed = ? 
                    WHERE name = ? AND start_date = ? AND end_date = ? AND time_start = ? AND time_end = ?
                '''
        params = (new_status, name, date_str, date_end_str, start_str, end_str)
        self._execute_query(query, params, commit=True)
        self.load_data()
        if server_id:
            token = self._get_api_token()
            if token:
                payload = {'is_completed': new_status}
                self.patch_worker = NetworkWorker(f"{SERVER_URL}/events/{server_id}", payload=payload, token=token,
                                                  method='PATCH')
                self.patch_thread = QThread()
                self.patch_worker.moveToThread(self.patch_thread)
                self.patch_thread.started.connect(self.patch_worker.run)
                self.patch_worker.finished.connect(self.patch_thread.quit)
                self.patch_worker.finished.connect(self.patch_worker.deleteLater)
                self.patch_thread.finished.connect(self.patch_thread.deleteLater)
                self.patch_thread.start()

    # -------------------------------------------------------------------
    # БЛОК 8: УПРАВЛЕНИЕ ЗАДАЧАМИ (Tasks)
    # -------------------------------------------------------------------

    def _set_importance(self, button):
        self.current_importance = button.text()

    def add_task(self):
        name = self.taskName.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return
        desc = self.taskDes.text().strip()
        category = self.current_importance
        print(name, desc, category)

        query = 'INSERT INTO tasks (name, description, category, is_completed) VALUES (?, ?, ?, 0)'
        params = (name, desc, category)

        cursor = self._execute_query(query, params, commit=True)
        local_id = cursor.lastrowid if cursor else None

        token = self._get_api_token()
        if token:
            payload = {
                'name': name,
                'description': desc,
                'category': category,
                'is_completed': 0
            }
            print(payload)
            self.task_thread = QThread()
            self.task_worker = NetworkWorker(f"{SERVER_URL}/tasks", payload=payload, token=token)
            self.task_worker.moveToThread(self.task_thread)

            self.task_thread.started.connect(self.task_worker.run)
            self.task_worker.finished.connect(lambda res: self._on_task_sent(res, local_id))

            self.task_worker.finished.connect(self.task_thread.quit)
            self.task_worker.finished.connect(self.task_worker.deleteLater)
            self.task_thread.finished.connect(self.task_thread.deleteLater)
            self.task_thread.start()
        self.taskName.clear()
        self.taskDes.clear()
        self.load_data()

    def _on_task_sent(self, response, local_id):
        server_id = response.get('id')
        if server_id:
            query = "UPDATE tasks SET server_id = ? WHERE id = ?"
            self._execute_query(query, (server_id, local_id), commit=True)
            print(f"Синхронизировано: local={local_id}, server={server_id}")

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
            query_select = '''
                SELECT server_id FROM tasks
                WHERE name = ? AND description = ? AND category = ?
            '''
            params = (t_data[0], t_data[1], cat)
            result = self._execute_query(query_select, params, fetch_all=True)
            server_id = result[0][0] if result and result[0] else None

            query = '''DELETE FROM tasks WHERE name = ? AND description = ? AND category = ?'''
            params = (t_data[0], t_data[1], cat)
            self._execute_query(query, params, commit=True)
            if server_id:
                token = self._get_api_token()
                if token:
                    self.del_task_worker = NetworkWorker(f"{SERVER_URL}/tasks/{server_id}", method="DELETE",
                                                         token=token)
                    self.del_thread = QThread()
                    self.del_task_worker.moveToThread(self.del_thread)
                    self.del_thread.started.connect(self.del_task_worker.run)
                    self.del_task_worker.finished.connect(self.del_thread.quit)
                    self.del_task_worker.finished.connect(self.del_thread.deleteLater)
                    self.del_thread.finished.connect(self.del_thread.deleteLater)
                    self.del_thread.start()
            self.load_data()
        else:
            cats = {'Срочно и важно': 'UaI', 'Важно, но не срочно': 'IbnN', 'Срочно, но не важно': 'UbnI',
                    'Не срочно и не важно': 'NUanI'}
            cat = item.data(0, Qt.ItemDataRole.UserRole)
            query = '''DELETE FROM tasks WHERE category = ?'''
            params = (cat,)
            self._execute_query(query, params, commit=True)
            self.load_data()

            token = self._get_api_token()
            if token and cats[cat]:
                self.thread = QThread()
                self.worker = NetworkWorker(f"{SERVER_URL}/tasks/{cats[cat]}", method="DELETE",
                                            token=token)
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

    def _toggle_task_completion(self, item):
        """Переключает статус выполнения события"""
        cat = item.parent().data(0, Qt.ItemDataRole.UserRole)
        task = item.data(0, Qt.ItemDataRole.UserRole)
        name, desc, is_completed = task

        query_sel = 'SELECT server_id FROM tasks WHERE name = ? AND description = ? AND category = ?'
        res = self._execute_query(query_sel, (name, desc, cat), fetch_all=True)
        server_id = res[0][0] if res else None
        # Инвертируем статус (1-0 или 0-1)
        new_status = 0 if is_completed else 1

        query = '''
            UPDATE tasks 
            SET is_completed = ? 
            WHERE name = ? AND description = ? AND category = ?
        '''
        params = (new_status, name, desc, cat)

        self._execute_query(query, params, commit=True)
        self.load_data()

        if server_id:
            token = self._get_api_token()
            if token:
                payload = {'is_completed': new_status}
                self.patch_worker = NetworkWorker(f"{SERVER_URL}/tasks/{server_id}", payload=payload, token=token,
                                                  method='PATCH')
                self.patch_thread = QThread()
                self.patch_worker.moveToThread(self.patch_thread)
                self.patch_thread.started.connect(self.patch_worker.run)
                self.patch_thread.start()

    # -------------------------------------------------------------------
    # БЛОК 9: НАСТРОЙКИ UI И ЦВЕТА
    # -------------------------------------------------------------------

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

    def _setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(current_dir, 'calendar.ico')
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            # Если ваша иконка не найдена, ставим запасную системную
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
            print(f"Предупреждение: Иконка по пути {icon_path} не найдена")

        tray_menu = QMenu()

        show_action = QAction("Показать", self)
        show_action.triggered.connect(self.showNormal)

        quit_action = QAction("Выход", self)
        quit_action.triggered.connect(QApplication.instance().quit)

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
        self.tray_icon.show()

    def _on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()

    def closeEvent(self, event):
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()

    # -------------------------------------------------------------------
    # БЛОК 10: ПОЛНАЯ СИНХРОНИЗАЦИЯ
    # -------------------------------------------------------------------

    def sync_all(self):
        token = self._get_api_token()
        if not token:
            return

        # Настройка потока событий
        # 1. Загрузка событий с сервера
        self.sync_events_worker = NetworkWorker(f"{SERVER_URL}/events", method="GET", token=token)
        self.sync_thread_ev = QThread()
        self.sync_events_worker.moveToThread(self.sync_thread_ev)
        self.sync_events_worker.finished.connect(self._process_server_events)
        self.sync_thread_ev.started.connect(self.sync_events_worker.run)
        # Очистка потоков
        self.sync_events_worker.finished.connect(self.sync_thread_ev.quit)
        self.sync_events_worker.finished.connect(self.sync_events_worker.deleteLater)
        self.sync_thread_ev.finished.connect(self.sync_thread_ev.deleteLater)
        self.sync_thread_ev.start()
        # 2. Загрузка задач с сервера (аналогично)
        self.sync_tasks_worker = NetworkWorker(f"{SERVER_URL}/tasks", method="GET", token=token)
        self.sync_thread_task = QThread()
        self.sync_tasks_worker.moveToThread(self.sync_thread_task)
        self.sync_tasks_worker.finished.connect(self._process_server_tasks)
        self.sync_thread_task.started.connect(self.sync_tasks_worker.run)
        # Очистка потоков
        self.sync_tasks_worker.finished.connect(self.sync_thread_task.quit)
        self.sync_tasks_worker.finished.connect(self.sync_tasks_worker.deleteLater)
        self.sync_thread_task.finished.connect(self.sync_thread_task.deleteLater)
        self.sync_thread_task.start()

    def _process_server_events(self, events_data):
        if not isinstance(events_data, list):
            return
        for ev in events_data:
            server_id = ev['id']
            check_query = "SELECT id FROM events WHERE server_id = ?"
            res = self._execute_query(check_query, (server_id,), fetch_all=True)
            if res:
                query = '''
                        UPDATE events SET
                        name = ?, start_date = ?, end_date = ?, time_start = ?, time_end = ?, is_completed = ?
                        WHERE server_id = ?
                '''
                t_start = ev['time_start'][:5]
                t_end = ev['time_end'][:5]
                params = (ev['event_name'], ev['start_date'], ev['end_date'], t_start, t_end, ev['is_completed'],
                          server_id)
                self._execute_query(query, params, commit=True)
            else:
                query = '''
                    INSERT INTO events (name, start_date, end_date, time_start, time_end, is_completed, server_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                '''
                t_start = ev['time_start'][:5]
                t_end = ev['time_end'][:5]
                params = (ev['event_name'], ev['start_date'], ev['end_date'], t_start, t_end, ev['is_completed'],
                          server_id)
                self._execute_query(query, params, commit=True)
            self.load_data()

    def _process_server_tasks(self, tasks_data):
        if not isinstance(tasks_data, list):
            return
        for task in tasks_data:
            server_id = task['id']
            check_query = "SELECT id FROM tasks WHERE server_id = ?"
            res = self._execute_query(check_query, (server_id,), fetch_all=True)
            if res:
                query = "UPDATE tasks SET name=?, description=?, category=?, is_completed=? WHERE server_id=?"
                params = (task['name'], task['description'], task['category'], task['is_completed'], server_id)
                self._execute_query(query, params, commit=True)
            else:
                query = "INSERT INTO tasks (name, description, category, is_completed, server_id) VALUES (?, ?, ?, ?, ?)"
                params = (task['name'], task['description'], task['category'], task['is_completed'], server_id)
                self._execute_query(query, params, commit=True)
        self.load_data()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())
