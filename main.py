import sys
import datetime
import sqlite3
from typing import Dict, List, Tuple

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate, QTime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QTreeWidgetItem, QMenu, QTreeWidget
)

TASK_CATEGORIES = [
    "Срочно и важно",
    "Важно, но не срочно",
    "Срочно, но не важно",
    'Не срочно и не важно'
]


class SimplePlanner(QMainWindow):

    def __init__(self):
        super().__init__()

        try:
            uic.loadUi('design_test.ui', self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить интерфейс (design_test.ui): {e}")
            sys.exit(1)

        self.setWindowTitle('Минипланировщик')

        self.events: Dict[datetime.date, List[Tuple[str, datetime.time, datetime.time]]] = {}
        self.tasks: Dict[str, List[Tuple[str, str]]] = {cat: [] for cat in TASK_CATEGORIES}

        self._init_db()
        self.load_data()

        self.current_importance = TASK_CATEGORIES[0]

        self._setup_tree_widgets()

        self.addEventBtn.clicked.connect(self.add_event)
        self.searchEvent.textChanged.connect(self.update_event_list)

        self.taskButton.clicked.connect(self.add_task)
        self.searchTask.textChanged.connect(self.update_task_list)
        self.importanceChoice.buttonClicked.connect(self._set_importance)
        self.taskDes.setMaxLength(100)

    def closeEvent(self, event):
        if self.db:
            self.db.close()
        event.accept()

    def _init_db(self):
        try:
            self.db = sqlite3.connect('planner.db')
            cursor = self.db.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                            CREATE TABLE IF NOT EXISTS tasks (
                                id INTEGER PRIMARY KEY,
                                name TEXT NOT NULL,
                                description TEXT,
                                category TEXT NOT NULL
                            )
                        ''')
            self.db.commit()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка БД", f"Не удалось инициализировать базу данных: {e}")
            sys.exit(1)

    def load_data(self):
        if not self.db:
            QMessageBox.warning(self, "Предупреждение", "База данных не инициализирована")
            return

        self.events.clear()
        for category in TASK_CATEGORIES:
            self.tasks[category] = []

        cursor = self.db.cursor()

        cursor.execute("SELECT name, event_date, time_start, time_end FROM events ORDER BY event_date, time_start")
        for name, event_date, time_start, time_end in cursor.fetchall():
            try:
                date = datetime.datetime.strptime(event_date, "%Y-%m-%d").date()
                time_start = datetime.datetime.strptime(time_start, "%H:%M:%S").time()
                time_end = datetime.datetime.strptime(time_end, "%H:%M:%S").time()

                if date not in self.events:
                    self.events[date] = []
                self.events[date].append((name, time_start, time_end))
            except ValueError:
                continue

        cursor.execute("SELECT name, description, category FROM tasks")
        for name, desc, cat in cursor.fetchall():
            if cat in self.tasks:
                self.tasks[cat].append((name, desc))

        cursor.close()

        self.update_event_list()
        self.update_task_list()

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
    # ЛОГИКА КОНТЕКСТНОГО МЕНЮ
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

        date_str = date_py.strftime("%Y-%m-%d")
        start_str = start_py.strftime("%H:%M:%S")
        end_str = end_py.strftime("%H:%M:%S")

        if end_py < start_py:
            QMessageBox.warning(self, "Ошибка", "Время окончания не может быть раньше начала")
            return

        try:
            cursor = self.db.cursor()
            cursor.execute('''INSERT INTO events (name, event_date, time_start, time_end) VALUES (?, ?, ?, ?)''',
                           (name, date_str, start_str, end_str))
            self.db.commit()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка БД", f"Ошибка добавления события: {e}")
            return

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
            date_key = item.parent().data(0, Qt.ItemDataRole.UserRole)
            ev_data = item.data(0, Qt.ItemDataRole.UserRole)
            name, start_time, end_time = ev_data

            date_str = date_key.strftime("%Y-%m-%d")
            start_str = start_time.strftime("%H:%M:%S")
            end_str = end_time.strftime("%H:%M:%S")

            try:
                cursor = self.db.cursor()
                cursor.execute('''
                    DELETE FROM events 
                    WHERE name = ? AND event_date = ? AND time_start = ? AND time_end = ?'''
                               , (name, date_str, start_str, end_str))
                self.db.commit()
            except sqlite3.Error as e:
                QMessageBox.critical(self, "Ошибка БД", f"Ошибка удаления события: {e}")
        else:
            date_key = item.data(0, Qt.ItemDataRole.UserRole)
            date_str = date_key.strftime("%Y-%m-%d")

            try:
                cursor = self.db.cursor()
                cursor.execute('''
                    DELETE FROM events 
                    WHERE event_date = ?''', (date_str,))
                self.db.commit()
            except sqlite3.Error as e:
                QMessageBox.critical(self, "Ошибка БД", f"Ошибка удаления события: {e}")

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

        try:
            cursor = self.db.cursor()
            cursor.execute('''INSERT INTO tasks (name, description, category) VALUES (?, ?, ?)''',
                           (name, desc, self.current_importance))
            self.db.commit()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Ошибка БД", f"Ошибка добавления задачи: {e}")

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
            cat = item.parent().data(0, Qt.ItemDataRole.UserRole)
            t_data = item.data(0, Qt.ItemDataRole.UserRole)

            try:
                cursor = self.db.cursor()
                cursor.execute('''
                    DELETE FROM tasks 
                    WHERE name = ? AND category = ?''', (t_data[0], cat))
                self.db.commit()
            except sqlite3.Error as e:
                QMessageBox.critical(self, "Ошибка БД", f"Ошибка удаления задачи: {e}")
        else:
            cat = item.data(0, Qt.ItemDataRole.UserRole)

            try:
                cursor = self.db.cursor()
                cursor.execute('''
                    DELETE FROM tasks 
                    WHERE category = ?''', (cat,))
                self.db.commit()
            except sqlite3.Error as e:
                QMessageBox.critical(self, "Ошибка БД", f"Ошибка удаления задачи: {e}")

        self.load_data()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())