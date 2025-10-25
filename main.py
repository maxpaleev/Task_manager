from datetime import datetime, date, time
import sys
import io

from PyQt6 import uic
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox


class SimplePlanner(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('design.ui', self)
        self.setWindowTitle('Минипланировщик')
        self.events = []
        self.addEventBtn.clicked.connect(self.add)

    def add(self):
        if self.lineEdit.text():
            event_date = datetime(self.calendarWidget.selectedDate().year(), self.calendarWidget.selectedDate().month(),
                         self.calendarWidget.selectedDate().day(), self.timeStart.time().hour(),
                         self.timeStart.time().minute())
            event_start = time(hour=self.timeStart.time().hour(), minute=self.timeStart.time().minute())
            event_end = time(hour=self.timeEnd.time().hour(), minute=self.timeEnd.time().minute())

            if event_end < event_start:
                QMessageBox(self).critical(self, "Ошибка", "Время окончания события не может быть раньше времени начала")
            else:
                my_event = [event_date, event_end, self.lineEdit.text()]
                self.events.append(my_event)

                self.events = sorted(self.events, key=lambda x: x[0])
                self.eventList.clear()

                for i in self.events:
                    self.eventList.addItem(i[0].strftime("%d.%m.%Y %H:%M") + " - " + i[1].strftime("%H:%M") + " : " + i[2])


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())
