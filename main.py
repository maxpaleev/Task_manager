import sys

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate, QTime
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTreeWidgetItem, QMenu


class SimplePlanner(QMainWindow):
    def __init__(self):
        super().__init__()

        # Загрузка UI из файла .ui
        try:
            uic.loadUi('design_test.ui', self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить интерфейс: {e}")
            sys.exit(1)

        self.setWindowTitle('Минипланировщик')

        # --- Категории задач ---
        self.TASK_CATEGORIES = [
            "Срочно и важно",
            "Важно, но не срочно",
            "Срочно, но не важно",
            'Не срочно и не важно'
        ]

        # --- Инициализация Событий ---
        self.data = {}
        self.addEventBtn.clicked.connect(self.event_add)
        self.searchEvent.textChanged.connect(self.update_event_list)

        # Настройка QTreeWidget
        self.eventList.setColumnCount(2)
        self.eventList.setHeaderLabels(["Событие", "Время"])
        # Включаем политику кастомного меню, чтобы работал правый клик
        self.eventList.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.eventList.customContextMenuRequested.connect(lambda pos: self.show_context_menu(self.eventList, pos))

        # --- Инициализация Задач ---
        self.tasks = {category: [] for category in self.TASK_CATEGORIES}
        self.importance = self.TASK_CATEGORIES[0]
        self.searchTask.textChanged.connect(self.update_task_list)

        # Подключение кнопок
        self.taskButton.clicked.connect(self.task_add)
        self.taskDes.setMaxLength(100)
        self.importanceChoice.buttonClicked.connect(self.get_importance)

        # Настройка QTreeWidget для задач
        self.taskList.setColumnCount(2)
        self.taskList.setHeaderLabels(["Название", "Описание"])
        self.taskList.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.taskList.customContextMenuRequested.connect(lambda pos: self.show_context_menu(self.taskList, pos))

    # ===================================================================
    # 				ЛОГИКА КОНТЕКСТНОГО МЕНЮ (context_menu)
    # ===================================================================
    def show_context_menu(self, tree_widget, position):
        item = tree_widget.itemAt(position)
        if not item:
            return

        menu = QMenu(self)

        action_del = menu.addAction("Удалить")
        action_edit = menu.addAction("Редактировать")
        action_expand = menu.addAction("Раскрыть все")
        action_collapse = menu.addAction("Свернуть все")

        if not item.parent():
            action_edit.setEnabled(False)

        action = menu.exec(tree_widget.viewport().mapToGlobal(position))

        if action == action_del:
            if tree_widget is self.eventList:
                self.delete_event(item)
            elif tree_widget is self.taskList:
                self.delete_task(item)

        elif action == action_edit:
            if tree_widget is self.eventList:
                self.edit(item)
            elif tree_widget is self.taskList:
                self.edit(item)

        elif action == action_expand:
            tree_widget.expandAll()

        elif action == action_collapse:
            tree_widget.collapseAll()

    def edit(self, item):
        if item.parent().text(0) in self.TASK_CATEGORIES or item.text(0) in self.TASK_CATEGORIES:
            category_name = item.parent().data(0, Qt.ItemDataRole.UserRole)
            task_data = item.data(0, Qt.ItemDataRole.UserRole)
            name, desc = task_data
            self.delete_task(item)

            self.taskName.setText(name)
            self.taskDes.setText(desc)
            self.importance = category_name
            for button in self.importanceChoice.buttons():
                if button.text() == category_name:
                    button.setChecked(True)
                    break
        else:
            event_day_date = item.parent().data(0, Qt.ItemDataRole.UserRole)
            event_data = item.data(0, Qt.ItemDataRole.UserRole)
            event_name, event_start, event_end = event_data

            self.delete_event(item)

            # Заполняем поля ввода
            self.timeStart.setTime(QTime(event_start.hour, event_start.minute))
            self.timeEnd.setTime(QTime(event_end.hour, event_end.minute))
            self.calendarWidget.setSelectedDate(QDate(event_day_date.year, event_day_date.month, event_day_date.day))
            self.eventName.setText(event_name)

    # ===================================================================
    # 				ЛОГИКА СОБЫТИЙ (Events)
    # ===================================================================

    def event_add(self):
        """Добавление нового события в календарь."""
        if not self.eventName.text():
            QMessageBox.warning(self, "Предупреждение", "Введите название события")
            return

        event_day = self.calendarWidget.selectedDate().toPyDate()
        event_start = self.timeStart.time().toPyTime()
        event_end = self.timeEnd.time().toPyTime()

        if event_end < event_start:
            QMessageBox.warning(self, "Ошибка", "Время окончания события не может быть раньше времени начала")
            return

        event_tuple = (self.eventName.text(), event_start, event_end)

        # Добавляем в словарь
        if event_day in self.data:
            if event_tuple not in self.data[event_day]:
                self.data[event_day].append(event_tuple)
        else:
            self.data[event_day] = [event_tuple]

        # Очистка полей ввода
        self.eventName.clear()
        self.timeStart.setTime(QTime(0, 0))
        self.timeEnd.setTime(QTime(0, 0))

        self.update_event_list()  # Обновляем дерево

    def update_event_list(self):
        """Обновление дерева событий (eventList) на основе данных self.data."""
        self.eventList.clear()
        items = []
        # Сортируем по дате
        for key_date, values in sorted(self.data.items(), key=lambda x: x[0]):
            if self.searchEvent.text():
                for i in values:
                    if self.searchEvent.text().lower() in i[0].lower():
                        item = QTreeWidgetItem([key_date.strftime("%d.%m.%Y")])

                        item.setData(0, Qt.ItemDataRole.UserRole, key_date)

                        # Сортируем события по времени начала
                        for value_tuple in sorted(values, key=lambda x: x[1]):
                            name = value_tuple[0]
                            if self.searchEvent.text().lower() in name.lower():
                                time_str = f"{value_tuple[1].strftime('%H:%M')} - {value_tuple[2].strftime('%H:%M')}"
                                child = QTreeWidgetItem([name, time_str])
                                child.setData(0, Qt.ItemDataRole.UserRole, value_tuple)
                                item.addChild(child)
                        items.append(item)
                        break
            else:
                item = QTreeWidgetItem([key_date.strftime("%d.%m.%Y")])

                item.setData(0, Qt.ItemDataRole.UserRole, key_date)

                # Сортируем события по времени начала
                for value_tuple in sorted(values, key=lambda x: x[1]):
                    name = value_tuple[0]
                    time_str = f"{value_tuple[1].strftime('%H:%M')} - {value_tuple[2].strftime('%H:%M')}"
                    child = QTreeWidgetItem([name, time_str])
                    child.setData(0, Qt.ItemDataRole.UserRole, value_tuple)
                    item.addChild(child)
                items.append(item)
        self.eventList.insertTopLevelItems(0, items)
        if self.searchEvent.text():
            self.eventList.expandAll()

    def delete_event(self, item):
        """Удаление события (или целого дня, если удаляется родитель)."""
        if not item.parent():
            key = item.data(0, Qt.ItemDataRole.UserRole)
            if key in self.data:
                del self.data[key]
        elif item.parent():
            key = item.parent().data(0, Qt.ItemDataRole.UserRole)
            event_data = item.data(0, Qt.ItemDataRole.UserRole)

            if key in self.data and event_data in self.data[key]:
                self.data[key].remove(event_data)
                if not self.data[key]:
                    del self.data[key]

        self.update_event_list()

    # ==================================================================
    # 				ЛОГИКА ЗАДАЧ (Tasks)
    # ==================================================================
    def get_importance(self, button):
        """Получение категории важности из QButtonGroup (радиокнопки)."""
        self.importance = button.text()

    def task_add(self):
        """Добавление новой задачи."""
        task_name = self.taskName.text()
        task_desc = self.taskDes.text()
        if not task_name:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return
        self.tasks[self.importance].append((task_name, task_desc))
        self.taskName.clear()
        self.taskDes.clear()
        self.update_task_list()

    def update_task_list(self):
        """Обновление (перерисовка) дерева задач (taskList) на основе данных self.tasks."""
        search_text = self.searchTask.text()
        self.taskList.clear()
        items = []
        for category in self.TASK_CATEGORIES:
            if search_text:
                tasks = self.tasks[category]
                if not tasks:
                    continue
                for i in tasks:
                    if search_text.lower() in i[0].lower():
                        item = QTreeWidgetItem([category])
                        item.setData(0, Qt.ItemDataRole.UserRole, category)

                        for task_tuple in tasks:
                            name, desc = task_tuple
                            if search_text.lower() in name.lower():
                                child = QTreeWidgetItem([name, desc])
                                child.setData(0, Qt.ItemDataRole.UserRole, task_tuple)
                                item.addChild(child)
                        items.append(item)
                        break
            else:
                tasks = self.tasks[category]
                if not tasks:
                    continue

                item = QTreeWidgetItem([category])
                item.setData(0, Qt.ItemDataRole.UserRole, category)

                for task_tuple in tasks:
                    name, desc = task_tuple
                    child = QTreeWidgetItem([name, desc])
                    child.setData(0, Qt.ItemDataRole.UserRole, task_tuple)
                    item.addChild(child)
                items.append(item)
        self.taskList.insertTopLevelItems(0, items)
        if search_text:
            self.taskList.expandAll()

    def delete_task(self, item):
        """Удаление задачи или очистка категории."""
        if not item.parent():
            category_name = item.data(0, Qt.ItemDataRole.UserRole)
            if category_name in self.tasks:
                self.tasks[category_name].clear()
        elif item.parent():

            category_name = item.parent().data(0, Qt.ItemDataRole.UserRole)
            task_data = item.data(0, Qt.ItemDataRole.UserRole)
            if category_name in self.tasks and task_data in self.tasks[category_name]:
                self.tasks[category_name].remove(task_data)
        self.update_task_list()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())
