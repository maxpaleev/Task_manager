import sys
import datetime
from typing import Dict, List, Tuple

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate, QTime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QTreeWidgetItem, QMenu, QTreeWidget
)

# Названия категорий вынесены в константу
TASK_CATEGORIES = [
    "Срочно и важно",
    "Важно, но не срочно",
    "Срочно, но не важно",
    'Не срочно и не важно'
]


class SimplePlanner(QMainWindow):
    def __init__(self):
        super().__init__()

        # --- 1. Загрузка интерфейса ---
        try:
            uic.loadUi('design_test.ui', self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить интерфейс (design_test.ui): {e}")
            sys.exit(1)

        self.setWindowTitle('Минипланировщик')

        self.events: Dict[datetime.date, List[Tuple[str, datetime.time, datetime.time]]] = {}

        self.tasks: Dict[str, List[Tuple[str, str]]] = {cat: [] for cat in TASK_CATEGORIES}

        self.current_importance = TASK_CATEGORIES[0]

        # --- 3. Настройка UI компонентов ---
        self._setup_tree_widgets()

        # --- 4. Подключение сигналов (Events) ---
        self.addEventBtn.clicked.connect(self.add_event)
        self.searchEvent.textChanged.connect(self.update_event_list)

        # --- 5. Подключение сигналов (Tasks) ---
        self.taskButton.clicked.connect(self.add_task)
        self.searchTask.textChanged.connect(self.update_task_list)
        self.importanceChoice.buttonClicked.connect(self._set_importance)
        self.taskDes.setMaxLength(100)

    def _setup_tree_widgets(self):
        """Настройка заголовков и меню для таблиц."""
        # Настройка списка событий
        self.eventList.setColumnCount(2)
        self.eventList.setHeaderLabels(["Событие", "Время"])
        self.eventList.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.eventList.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(self.eventList, pos)
        )

        # Настройка списка задач
        self.taskList.setColumnCount(2)
        self.taskList.setHeaderLabels(["Название", "Описание"])
        self.taskList.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.taskList.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(self.taskList, pos)
        )

    # ===================================================================
    # 				ЛОГИКА КОНТЕКСТНОГО МЕНЮ
    # ===================================================================
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

        # Редактировать можно только элементы, но не заголовки (категории/даты)
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
            # --- Редактирование события ---
            event_date = parent.data(0, Qt.ItemDataRole.UserRole)
            event_data = item.data(0, Qt.ItemDataRole.UserRole)  # (name, start, end)

            self._delete_event_logic(item)

            # Заполняем поля
            name, start, end = event_data
            self.eventName.setText(name)
            self.timeStart.setTime(QTime(start.hour, start.minute))
            self.timeEnd.setTime(QTime(end.hour, end.minute))
            self.calendarWidget.setSelectedDate(QDate(event_date.year, event_date.month, event_date.day))

        elif tree_widget is self.taskList:
            # --- Редактирование задачи ---
            category_name = parent.data(0, Qt.ItemDataRole.UserRole)
            task_data = item.data(0, Qt.ItemDataRole.UserRole)  # (name, desc)

            # Удаляем старое
            self._delete_task_logic(item)

            # Заполняем поля
            name, desc = task_data
            self.taskName.setText(name)
            self.taskDes.setText(desc)

            # Переключаем радио-кнопку
            self.current_importance = category_name
            for btn in self.importanceChoice.buttons():
                if btn.text() == category_name:
                    btn.setChecked(True)
                    break

    # ===================================================================
    # 				ЛОГИКА СОБЫТИЙ (Events)
    # ===================================================================
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

        new_event = (name, start_py, end_py)

        if date_py not in self.events:
            self.events[date_py] = []

        # Простое добавление
        self.events[date_py].append(new_event)

        # Очистка и обновление
        self.eventName.clear()
        self.timeStart.setTime(QTime(0, 0))
        self.timeEnd.setTime(QTime(0, 0))
        self.update_event_list()

    def update_event_list(self):
        """Перерисовка дерева событий."""
        search = self.searchEvent.text().lower()
        self.eventList.clear()

        items = []
        # Сортируем даты по возрастанию
        for date_key in sorted(self.events.keys()):
            events_list = self.events[date_key]

            # Фильтрация
            if search:
                matching = [e for e in events_list if search in e[0].lower()]
            else:
                matching = events_list

            if matching:
                root_item = QTreeWidgetItem([date_key.strftime("%d.%m.%Y")])
                root_item.setData(0, Qt.ItemDataRole.UserRole, date_key)

                # Сортируем события внутри дня по времени начала
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
        """Удаление события из структуры данных."""
        if item.parent():
            # Удаляем конкретное событие
            date_key = item.parent().data(0, Qt.ItemDataRole.UserRole)
            ev_data = item.data(0, Qt.ItemDataRole.UserRole)

            if date_key in self.events and ev_data in self.events[date_key]:
                self.events[date_key].remove(ev_data)
                # Если список событий на этот день пуст, удаляем сам день
                if not self.events[date_key]:
                    del self.events[date_key]
        else:
            # Удаляем весь день (родительский узел)
            date_key = item.data(0, Qt.ItemDataRole.UserRole)
            if date_key in self.events:
                del self.events[date_key]

        self.update_event_list()

    # ==================================================================
    # 				ЛОГИКА ЗАДАЧ (Tasks)
    # ==================================================================
    def _set_importance(self, button):
        self.current_importance = button.text()

    def add_task(self):
        name = self.taskName.text().strip()
        desc = self.taskDes.text().strip()

        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return

        self.tasks[self.current_importance].append((name, desc))

        self.taskName.clear()
        self.taskDes.clear()
        self.update_task_list()

    def update_task_list(self):
        """Перерисовка дерева задач."""
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
        """Удаление задачи из структуры данных."""
        if item.parent():
            # Удаляем конкретную задачу
            cat = item.parent().data(0, Qt.ItemDataRole.UserRole)
            t_data = item.data(0, Qt.ItemDataRole.UserRole)
            if cat in self.tasks and t_data in self.tasks[cat]:
                self.tasks[cat].remove(t_data)
        else:
            # Очищаем всю категорию
            cat = item.data(0, Qt.ItemDataRole.UserRole)
            if cat in self.tasks:
                self.tasks[cat].clear()

        self.update_task_list()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())