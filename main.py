import datetime
import sys
import io

from PyQt6 import uic
from PyQt6.QtWidgets import QApplication, QMainWindow



class DiaryEvent():
    def __init__(self, datetime, title):
        self.datetime = datetime
        self.title = title

    def to_str(self):
        return "{} - {}".format(self.datetime, self.title)

    def __str__(self):
        return self.to_str()


class SimplePlanner(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('design.ui', self)
        self.setWindowTitle('Минипланировщик')
        self.events = []
        self.addEventBtn.clicked.connect(self.add)

    def add(self):
        if self.lineEdit.text():
            t = datetime.datetime(self.calendarWidget.selectedDate().year(), self.calendarWidget.selectedDate().month(),
                                  self.calendarWidget.selectedDate().day(), self.timeEdit.time().hour(),
                                  self.timeEdit.time().minute())

            my_event = DiaryEvent(t, self.lineEdit.text())
            self.events.append(my_event)

            self.events = sorted(self.events, key=lambda x: x.datetime)
            self.eventList.clear()

            self.eventList.addItems([i.to_str() for i in self.events])


if __name__ == '__main__':
    app = QApplication(sys.argv)
    form = SimplePlanner()
    form.show()
    sys.exit(app.exec())
