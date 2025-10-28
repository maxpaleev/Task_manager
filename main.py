from datetime import datetime, time
import sys

from PyQt6 import uic
from PyQt6.QtCore import QTime, Qt, QDate
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTreeWidgetItem, QTreeWidget, QMenu


class SimplePlanner(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            uic.loadUi('design_test.ui', self)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить интерфейс: {e}")
            sys.exit(1)

        self.setWindowTitle('Минипланировщик')

        self.addEventBtn.clicked.connect(self.event_add)
        self.taskButton.clicked.connect(self.task_add)

        self.data = {}
        self.eventList.setColumnCount(2)
        self.eventList.setHeaderLabels(["Событие", "Время"])
        self.eventList.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.eventList.customContextMenuRequested.connect(self.event_context_menu)

        self.tasks = {"Срочно и важно": [], "Важно, но не срочно": [], "Срочно, но не важно": [],
                      'Не срочно и не важно': []}
        self.taskDes.setMaxLength(100)
        self.importanceChoice.buttonClicked.connect(self.get_importance)
        self.taskList.setColumnCount(2)
        self.taskList.setHeaderLabels(["Название", "Описание"])

    def event_add(self):
        if not self.eventName.text():
            QMessageBox.warning(self, "Предупреждение", "Введите название события")
            return

        selected_date = self.calendarWidget.selectedDate()
        event_day = datetime(selected_date.year(), selected_date.month(), selected_date.day())
        event_start = time(hour=self.timeStart.time().hour(), minute=self.timeStart.time().minute())
        event_end = time(hour=self.timeEnd.time().hour(), minute=self.timeEnd.time().minute())

        if event_end < event_start:
            QMessageBox.warning(self, "Ошибка", "Время окончания события не может быть раньше времени начала")
            return

        if event_day in self.data:
            self.data[event_day].append((self.eventName.text(), event_start, event_end))
        else:
            self.data[event_day] = [(self.eventName.text(), event_start, event_end)]

        self.eventName.clear()
        self.timeStart.setTime(QTime(0, 0))
        self.timeEnd.setTime(QTime(0, 0))

        self.update_event_list()

    def update_event_list(self):
        self.eventList.clear()
        items = []
        for key, values in sorted(self.data.items(), key=lambda x: x[0]):
            item = QTreeWidgetItem([key.strftime("%d.%m.%Y")])
            for value in sorted(values, key=lambda x: x[1]):
                name = value[0]
                time_str = f"{value[1].strftime('%H:%M')} - {value[2].strftime('%H:%M')}"
                child = QTreeWidgetItem([name, time_str])
                item.addChild(child)
            items.append(item)
        self.eventList.insertTopLevelItems(0, items)

    def delete_event(self, item):
        if not item.parent():
            key = datetime.strptime(item.text(0), "%d.%m.%Y")
            del self.data[key]
            self.update_event_list()
        elif item.parent():
            key = datetime.strptime(item.parent().text(0), "%d.%m.%Y")
            date = self.data[key]
            for i in date:
                if i[0] == item.text(0):
                    date.remove(i)
                    self.update_event_list()
                    break

    def edit_event(self, item):
        event_day = datetime.strptime(item.parent().text(0), "%d.%m.%Y")
        event_start = time(hour=int(item.text(1).split('-')[0].split(':')[0]),
                           minute=int(item.text(1).split('-')[0].split(':')[1]))
        event_end = time(hour=int(item.text(1).split('-')[1].split(':')[0]),
                         minute=int(item.text(1).split('-')[1].split(':')[1]))
        event_name = item.text(0)

        self.delete_event(item)

        self.timeStart.setTime(QTime(event_start.hour, event_start.minute))
        self.timeEnd.setTime(QTime(event_end.hour, event_end.minute))
        self.calendarWidget.setSelectedDate(QDate(event_day.year, event_day.month, event_day.day))
        self.eventName.setText(event_name)

    def event_context_menu(self, position):
        item = self.eventList.itemAt(position)
        menu = QMenu(self)

        action_del = menu.addAction("Удалить")
        action_edit = menu.addAction("Редактировать")

        if not item.parent():
            action_del.setEnabled(True)
            action_edit.setEnabled(False)

        action = menu.exec(self.eventList.mapToGlobal(position))

        if action == action_del:
            self.delete_event(item)
        elif action == action_edit:
            self.edit_event(item)

    def get_importance(self, button):
        self.importance = button.text()

    def task_add(self):
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
        self.taskList.clear()
        items = []
        for category, tasks in self.tasks.items():
            item = QTreeWidgetItem([category])
            for task in tasks:
                name, desc = task
                child = QTreeWidgetItem([name, desc])
                item.addChild(child)
            items.append(item)
        self.taskList.insertTopLevelItems(0, items)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())
