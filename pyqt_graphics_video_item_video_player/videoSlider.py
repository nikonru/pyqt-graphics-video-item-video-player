from PyQt5.QtWidgets import QSlider
from PyQt5.QtCore import Qt, pyqtSignal


def get_slider_style():
    return """
QSlider::groove:horizontal {
    border: 1px solid #999999;
    height: 3px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);
    margin: 2px 0;
}

QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b4b4b4, stop:1 #8f8f8f);
    border: 1px solid #5c5c5c;
    width: 6px;
    margin: -6px 0;
    border-radius: 3px; 
}"""


class VideoSlider(QSlider):
    seeked = pyqtSignal(int)
    updatePosition = pyqtSignal(int)

    def __init__(self, style=None):
        super().__init__()
        self.__pressed = None
        if not style:
            self.__initUi(get_slider_style())
        else:
            self.__initUi(style)

    def __initUi(self, style):
        self.setOrientation(Qt.Horizontal)
        self.setStyleSheet(style)
        self.setFixedHeight(20)

        self.setMouseTracking(True)

    def __setPositionAndGetValue(self, e):
        x = e.pos().x()
        if x >= self.maximum():
            return self.maximum()
        else:
            value = self.minimum() + (self.maximum() - self.minimum()) * x / self.width()
            # for preventing the error related to using Python3.10 (can't be float)
            self.setValue(int(value))
            return value

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.__pressed = True

    def mouseMoveEvent(self, e):
        if self.__pressed:
            e.accept()
            value = int(self.__setPositionAndGetValue(e))
            self.updatePosition.emit(value)
        return super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.__pressed = False
            e.accept()
            value = int(self.__setPositionAndGetValue(e))
            self.seeked.emit(value)
        return super().mouseReleaseEvent(e)