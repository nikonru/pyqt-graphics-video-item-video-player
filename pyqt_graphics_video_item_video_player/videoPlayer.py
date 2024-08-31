from PyQt5 import QtCore
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import QUrl, QTimer, Qt
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtWidgets import QWidget, QGridLayout, QShortcut, QFrame

from pyqt_graphics_video_item_video_player.videoControlWidget import VideoControlWidget
from pyqt_graphics_video_item_video_player.videoGraphicsView import VideoGraphicsView


class VideoPlayer(QWidget):

    def __init__(self, control_alignment=Qt.AlignCenter, volume=True, style=None, spacing=(0, 0, 0, 30), max_height=75,
                 show_control_on_spacebar=False, buttons_down=False):
        super().__init__()
        self.__initUi(control_alignment, volume, style, spacing, max_height, show_control_on_spacebar, buttons_down)

    def __initUi(self, control_alignment, volume, style, spacing, max_height, show_control_on_spacebar, buttons_down):
        self.__mediaPlayer = QMediaPlayer()
        self.__view = VideoGraphicsView()
        self.__view.setFrameStyle(QFrame.NoFrame)
        self.__view.setMouseTracking(True)
        self.__view.setMedia.connect(self.setMedia)
        self.__view.mouseMoveEvent = self.mouseMoveEvent
        self.__view.setFocusPolicy(Qt.NoFocus)

        self.__view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.__view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        def video_ends(status):
            if status == QMediaPlayer.EndOfMedia:
                self.stop()

        self.__mediaPlayer.mediaStatusChanged.connect(video_ends)


        self.__mediaPlayer.setVideoOutput(self.__view.getItem())
        self.__hideShowInterval = 2000

        self.__videoControlWidget = VideoControlWidget(volume, control_alignment=control_alignment, style=style,
                                                       spacing=spacing, buttons_down=buttons_down)
        self.__videoControlWidget.setPlayer(self.__mediaPlayer)
        self.__videoControlWidget.played.connect(self.__initPlay)
        self.__videoControlWidget.seeked.connect(self.__seekPosition)
        self.__videoControlWidget.containsCursor.connect(self.__setRemainControlWidgetVisible)

        self.__videoControlWidget.setVisible(False)
        self.__videoControlWidget.setMaximumHeight(max_height)

        self.__shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)

        def on_spacebar_pressed():
            self.__videoControlWidget.setVisible(show_control_on_spacebar)
            self.__videoControlWidget.togglePlayback()

        self.__shortcut.activated.connect(on_spacebar_pressed)

        lay = QGridLayout()
        lay.addWidget(self.__view, 0, 0, 2, 1)
        lay.addWidget(self.__videoControlWidget, 1, 0, 1, 1)
        lay.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lay)

        self.setMouseTracking(True)

        self.__timerInit()

    def resizeEvent(self, e):
        self.__view.resize(e.size())
        self.__view.setSceneRect(QtCore.QRectF(0.0, 0.0, self.__view.size().width(), self.__view.size().height()))
        return super().resizeEvent(e)

    def getControlWidget(self):
        return self.__videoControlWidget

    def setMedia(self, filename):
        mediaContent = QMediaContent(QUrl.fromLocalFile(filename))
        self.__mediaPlayer.setMedia(mediaContent)
        self.__videoControlWidget.setMedia(filename)

    def stop(self):
        self.__videoControlWidget.stop()

    def play(self):
        self.__videoControlWidget.play()

    def __timerInit(self):
        self.__timer = QTimer()
        self.__timer.setInterval(self.__hideShowInterval)
        self.__timer.timeout.connect(self.__bottomWidgetToggled)

    def __bottomWidgetToggled(self):
        self.__timer.stop()
        self.__videoControlWidget.setVisible(False)
        self.setCursor(Qt.BlankCursor)

    def __timerStart(self):
        self.__videoControlWidget.setVisible(True)
        self.__timer.start()
        self.setCursor(Qt.ArrowCursor)

    def __seekPosition(self, pos):
        self.__mediaPlayer.setPosition(pos)

    def enterEvent(self, e):
        self.__timerStart()
        return super().enterEvent(e)

    def mouseMoveEvent(self, e):
        self.__videoControlWidget.setVisible(True)
        if self.__timer.isActive():
            self.__timer.setInterval(self.__hideShowInterval)
        else:
            self.__timerStart()
        return super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self.__videoControlWidget.setVisible(False)
        return super().leaveEvent(e)

    def __initPlay(self):
        self.__view.initPlay()

    def __setRemainControlWidgetVisible(self, f):
        if f:
            try:
                self.__timer.timeout.disconnect()
            except TypeError:
                pass
        else:
            self.__timer.timeout.connect(self.__bottomWidgetToggled)