
import os.path

from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtMultimediaWidgets import QVideoWidget


class VideoGraphicsView(QVideoWidget):
    setMedia = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__filename = ''
        self.__ext = ['.mp4']

        self.setAcceptDrops(True)
        self.setStyleSheet('background: #000;')

    def setFileName(self, filename):
        self.__filename = filename

    def getItem(self):
        # Keep compatibility with existing player setup.
        return self

    def initPlay(self):
        # QVideoWidget automatically handles resizing.
        pass

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            filename = e.mimeData().urls()[0].toLocalFile()
            ext = os.path.splitext(filename)[-1].lower()

            if ext in self.__ext:
                e.acceptProposedAction()
                return

        e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            filename = e.mimeData().urls()[0].toLocalFile()
            self.setMedia.emit(filename)
            e.acceptProposedAction()
        else:
            e.ignore()
    
    def sizeHint(self):
        return QSize(640, 360)

    def minimumSizeHint(self):
        return QSize(0, 0)
