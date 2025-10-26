from datetime import datetime, date, time
import sys
import io

from PyQt6 import uic
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTreeWidget, QTreeWidgetItem


class SimplePlanner(QMainWindow):
    # создание окна
    def __init__(self):
        super().__init__()
        uic.loadUi('design_test.ui', self)
        self.setWindowTitle('Минипланировщик')
        self.events = []
        self.addEventBtn.clicked.connect(self.add)
        self.data = {}
        self.eventList.setColumnCount(2)
        self.eventList.setHeaderLabels(["Событие", "Время"])

    # добавление события
    def add(self):
        if self.eventName.text():
            # разделение времени
            event_day = datetime(self.calendarWidget.selectedDate().year(), self.calendarWidget.selectedDate().month(),
                                 self.calendarWidget.selectedDate().day())
            event_start = time(hour=self.timeStart.time().hour(), minute=self.timeStart.time().minute())
            event_end = time(hour=self.timeEnd.time().hour(), minute=self.timeEnd.time().minute())

            # проверка на корректность времени
            if event_end < event_start:
                QMessageBox(self).critical(self, "Ошибка",
                                           "Время окончания события не может быть раньше времени начала")
            else:
                if event_day in self.data:
                    self.data[event_day].append([self.eventName.text(), event_start, event_end])
                else:
                    self.data[event_day] = [[self.eventName.text(), event_start, event_end]]

                self.eventList.clear()

                # сортировка и добавление в виджет
                items = []
                for key, values in sorted(self.data.items(), key=lambda x: x[0]):
                    item = QTreeWidgetItem([key.strftime("%d.%m.%Y")])
                    for value in sorted(values, key=lambda x: x[1]):
                        name = value[0]
                        time_str = value[1].strftime("%H:%M") + " - " + value[2].strftime("%H:%M")
                        child = QTreeWidgetItem([name, time_str])
                        item.addChild(child)
                    items.append(item)

                self.eventList.insertTopLevelItems(0, items)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())
