from PyQt5.QtWidgets import QSlider
from PyQt5.QtCore import Qt, pyqtSignal


def get_slider_style():
    return """
QSlider::groove:horizontal {
    margin: 2px 0;
    
	border: 0px solid #424242; 
	height: 10px; 
	border-radius: 4px;
}

QSlider::handle:horizontal {
    border-radius: 3px;
    
    background-color: red; 
	border: 2px solid red; 
	width: 16px; 
	height: 20px; 
	line-height: 20px; 
	margin-top: -5px; 
	margin-bottom: -5px; 
	border-radius: 10px; 
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