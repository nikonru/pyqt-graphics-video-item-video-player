import sys

import vlc

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QWidget, QGridLayout, QShortcut, QFrame

from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

from pyqt_graphics_video_item_video_player.videoControlWidget import (
    VideoControlWidget
)
from pyqt_graphics_video_item_video_player.videoGraphicsView import (
    VideoGraphicsView
)


class VLCPlayerAdapter(QtCore.QObject):
    """
    Small QMediaPlayer-compatible interface used by VideoControlWidget.

    Internally everything is handled by libVLC.
    """

    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)

    def __init__(self, vlc_instance, video_widget):
        super().__init__(video_widget)

        self._instance = vlc_instance
        self._player = self._instance.media_player_new()

        self._video_widget = video_widget
        self._media = None

        self._volume = 100
        self._notify_interval = 50

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_position)

        # VLC events
        event_manager = self._player.event_manager()

        event_manager.event_attach(
            vlc.EventType.MediaPlayerLengthChanged,
            self._on_length_changed
        )

        event_manager.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            self._on_end_reached
        )

    # ------------------------------------------------------------------
    # QMediaPlayer-compatible API
    # ------------------------------------------------------------------

    def setNotifyInterval(self, interval):
        """
        QMediaPlayer compatibility.

        The original code sets this to 1 ms. Doing that with VLC would
        generate unnecessary Python/Qt events, so we clamp it.
        """
        self._notify_interval = max(20, int(interval))
        self._timer.setInterval(self._notify_interval)

    def setVolume(self, volume):
        self._volume = max(0, min(100, int(volume)))
        self._player.audio_set_volume(self._volume)

    def volume(self):
        return self._player.audio_get_volume()

    def setMedia(self, media):
        """
        Accept either QMediaContent or a filename/URL.
        """

        if isinstance(media, QMediaContent):
            url = media.canonicalUrl()

            if url.isLocalFile():
                filename = url.toLocalFile()
            else:
                filename = url.toString()

        elif isinstance(media, QtCore.QUrl):
            filename = (
                media.toLocalFile()
                if media.isLocalFile()
                else media.toString()
            )

        else:
            filename = str(media)

        self._media = self._instance.media_new(filename)

        self._player.set_media(self._media)

        self._player.audio_set_volume(self._volume)

        self._timer.stop()

    def play(self):
        result = self._player.play()

        if result == -1:
            return

        self._timer.start()

    def pause(self):
        self._player.pause()

    def stop(self):
        self._player.stop()
        self._timer.stop()

        self.positionChanged.emit(0)

    def setPosition(self, position):
        """
        QMediaPlayer uses milliseconds.
        VLC also uses milliseconds for get_time/set_time.
        """
        if self._player.get_media() is not None:
            self._player.set_time(int(position))

    def position(self):
        return self._player.get_time()

    def duration(self):
        return self._player.get_length()

    # ------------------------------------------------------------------
    # QMediaPlayer state compatibility
    # ------------------------------------------------------------------

    def state(self):
        if self._player.is_playing():
            return QMediaPlayer.PlayingState

        # VLC returns 1 for paused in some versions.
        state = self._player.get_state()

        if state == vlc.State.Paused:
            return QMediaPlayer.PausedState

        if self._player.get_media() is None:
            return QMediaPlayer.StoppedState

        return QMediaPlayer.StoppedState

    def mediaStatus(self):
        if self._player.get_media() is None:
            return QMediaPlayer.NoMedia

        state = self._player.get_state()

        if state in (
            vlc.State.NothingSpecial,
            vlc.State.Opening,
            vlc.State.Buffering,
            vlc.State.Playing,
            vlc.State.Paused,
        ):
            return QMediaPlayer.LoadedMedia

        return QMediaPlayer.NoMedia

    # ------------------------------------------------------------------
    # Position/duration updates
    # ------------------------------------------------------------------

    def _update_position(self):
        position = self._player.get_time()

        if position >= 0:
            self.positionChanged.emit(position)

        duration = self._player.get_length()

        if duration > 0:
            # This is harmless because durationChanged is cheap,
            # but only emit when it actually changes.
            if not hasattr(self, "_last_duration"):
                self._last_duration = -1

            if duration != self._last_duration:
                self._last_duration = duration
                self.durationChanged.emit(duration)

    # ------------------------------------------------------------------
    # VLC callbacks
    # ------------------------------------------------------------------

    def _on_length_changed(self, event):
        duration = self._player.get_length()

        if duration > 0:
            self.durationChanged.emit(duration)

    def _on_end_reached(self, event):
        self._timer.stop()
        self.positionChanged.emit(
            self._player.get_length()
        )


class VideoPlayer(QWidget):

    def __init__(
        self,
        control_alignment=Qt.AlignCenter,
        volume=True,
        style=None,
        spacing=(0, 0, 0, 30),
        max_height=75,
        show_control_on_spacebar=False,
        buttons_down=False
    ):
        super().__init__()

        self.__filename = None

        # --------------------------------------------------------------
        # VLC
        # --------------------------------------------------------------

        self.__vlc = vlc.Instance(
            "--no-video-title-show",
        )

        # --------------------------------------------------------------
        # UI
        # --------------------------------------------------------------

        self.__initUi(
            control_alignment,
            volume,
            style,
            spacing,
            max_height,
            show_control_on_spacebar,
            buttons_down
        )

        self.__vlcPlayer = VLCPlayerAdapter(
            self.__vlc,
            self.__view
        )

        self.__videoControlWidget.setPlayer(
            self.__vlcPlayer
        )

        self.__setupVideoOutput()

    def getControlWidget(self):
        return self.__vlcPlayer
    # ==================================================================
    # UI
    # ==================================================================

    def __initUi(
        self,
        control_alignment,
        volume,
        style,
        spacing,
        max_height,
        show_control_on_spacebar,
        buttons_down
    ):
        self.__view = VideoGraphicsView()

        self.__view.setFrameStyle(QFrame.NoFrame)
        self.__view.setMouseTracking(True)
        self.__view.setFocusPolicy(Qt.NoFocus)

        self.__view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.__view.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        # QGraphicsVideoItem is no longer used by VLC.
        # Avoid unnecessary QPainter processing.
        # self.__view.setRenderHints(0)

        self.__view.setMedia.connect(
            self.setMedia
        )

        self.__view.mouseMoveEvent = self.mouseMoveEvent

        # --------------------------------------------------------------
        # Controls
        # --------------------------------------------------------------

        self.__videoControlWidget = VideoControlWidget(
            volume,
            control_alignment=control_alignment,
            style=style,
            spacing=spacing,
            buttons_down=buttons_down
        )

        self.__videoControlWidget.played.connect(
            self.__initPlay
        )

        self.__videoControlWidget.seeked.connect(
            self.__seekPosition
        )

        self.__videoControlWidget.containsCursor.connect(
            self.__setRemainControlWidgetVisible
        )

        self.__videoControlWidget.setVisible(False)

        self.__videoControlWidget.setMaximumHeight(
            max_height
        )

        # --------------------------------------------------------------
        # Keyboard
        # --------------------------------------------------------------

        self.__shortcut = QShortcut(
            QKeySequence(Qt.Key_Space),
            self
        )

        def on_spacebar_pressed():
            self.__videoControlWidget.setVisible(
                show_control_on_spacebar
            )
            self.__togglePlayback()

        self.__shortcut.activated.connect(
            on_spacebar_pressed
        )

        # --------------------------------------------------------------
        # Layout
        # --------------------------------------------------------------

        lay = QGridLayout()

        lay.addWidget(
            self.__view,
            0,
            0,
            2,
            1
        )

        lay.addWidget(
            self.__videoControlWidget,
            1,
            0,
            1,
            1
        )

        lay.setContentsMargins(
            0,
            0,
            0,
            0
        )

        self.setLayout(lay)

        self.setMouseTracking(True)

        # --------------------------------------------------------------
        # Controls timer
        # --------------------------------------------------------------

        self.__hideShowInterval = 2000

        self.__timer = QTimer(self)

        self.__timer.setInterval(
            self.__hideShowInterval
        )

        self.__timer.timeout.connect(
            self.__bottomWidgetToggled
        )

    # ==================================================================
    # VLC video output
    # ==================================================================

    def __setupVideoOutput(self):
        """
        Give VLC the native window ID of the VideoGraphicsView.

        VLC renders directly into this window instead of going through
        QGraphicsVideoItem/QPainter.
        """

        self.__view.setAttribute(
            Qt.WA_NativeWindow,
            True
        )

        # Force creation of native window handle.
        self.__view.winId()

        self.__setVlcVideoOutput()

    def __setVlcVideoOutput(self):

        wid = int(self.__view.winId())

        if sys.platform.startswith("win"):
            self.__vlcPlayer._player.set_hwnd(wid)

        elif sys.platform.startswith("linux"):
            self.__vlcPlayer._player.set_xwindow(wid)

        elif sys.platform == "darwin":
            self.__vlcPlayer._player.set_nsobject(wid)

    # ==================================================================
    # Media
    # ==================================================================

    def setMedia(self, filename):
        self.__filename = filename

        # Let the adapter accept QMediaPlayer-style media.
        media = QMediaContent(
            QtCore.QUrl.fromLocalFile(filename)
        )

        self.__vlcPlayer.setMedia(media)

        self.__videoControlWidget.setMedia(
            filename
        )

    # ==================================================================
    # Playback
    # ==================================================================

    def play(self):
        self.__vlcPlayer.play()

    def stop(self):
        self.__videoControlWidget.stop()

    def __togglePlayback(self):
        if self.__vlcPlayer.mediaStatus() == QMediaPlayer.NoMedia:
            return

        if self.__vlcPlayer.state() == QMediaPlayer.PlayingState:
            self.__videoControlWidget.pause()
        else:
            self.__videoControlWidget.play()

    def __initPlay(self):
        self.play()

    # ==================================================================
    # Seeking
    # ==================================================================

    def __seekPosition(self, pos):
        self.__vlcPlayer.setPosition(
            int(pos)
        )

    # ==================================================================
    # Mouse controls
    # ==================================================================

    def __timerStart(self):
        self.__videoControlWidget.setVisible(True)

        self.__timer.start()

        self.setCursor(
            Qt.ArrowCursor
        )

    def __bottomWidgetToggled(self):
        self.__timer.stop()

        self.__videoControlWidget.setVisible(False)

        self.setCursor(
            Qt.BlankCursor
        )

    def __setRemainControlWidgetVisible(self, visible):
        try:
            self.__timer.timeout.disconnect()
        except TypeError:
            pass

        if not visible:
            self.__timer.timeout.connect(
                self.__bottomWidgetToggled
            )

    def enterEvent(self, e):
        self.__timerStart()

        return super().enterEvent(e)

    def mouseMoveEvent(self, e):
        self.__videoControlWidget.setVisible(True)

        if self.__timer.isActive():
            self.__timer.setInterval(
                self.__hideShowInterval
            )
        else:
            self.__timerStart()

        return super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self.__videoControlWidget.setVisible(False)

        return super().leaveEvent(e)

    # ==================================================================
    # Resize
    # ==================================================================

    def resizeEvent(self, e):
        """
        No QGraphicsVideoItem resizing.

        VLC handles the video scaling.
        """

        super().resizeEvent(e)

    # ==================================================================
    # Cleanup
    # ==================================================================

    def closeEvent(self, e):
        try:
            self.__vlcPlayer.stop()
            self.__vlcPlayer._player.release()
            self.__vlc.release()
        finally:
            super().closeEvent(e)
