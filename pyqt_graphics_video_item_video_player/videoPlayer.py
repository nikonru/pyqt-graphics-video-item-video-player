import sys

import vlc

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QKeySequence, QCursor
from PyQt5.QtWidgets import (
    QWidget,
    QGridLayout,
    QShortcut,
    QFrame,
    QApplication,
)

from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

from pyqt_graphics_video_item_video_player.videoControlWidget import (
    VideoControlWidget
)


class VLCVideoSurface(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFrameShape(QFrame.NoFrame)
        self.setFrameShadow(QFrame.Plain)

        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

        self.setStyleSheet("background: black;")


class VLCPlayerAdapter(QtCore.QObject):

    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    ended = pyqtSignal()

    def __init__(self, vlc_instance, parent=None):
        super().__init__(parent)

        self._instance = vlc_instance
        self._player = self._instance.media_player_new()
        self._media = None

        self._volume = 100
        self._notify_interval = 50

        self._last_position = -1
        self._last_duration = -1

        self._media_loaded = False
        self._shutting_down = False

        self._state = QMediaPlayer.StoppedState
        self._media_status = QMediaPlayer.NoMedia

        # True only when VLC actually reached EOF.
        self._ended = False

        self._timer = QTimer(self)
        self._timer.setInterval(self._notify_interval)
        self._timer.timeout.connect(self._update)

        event_manager = self._player.event_manager()

        event_manager.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            self._on_end_reached
        )

    # ==================================================================
    # QMediaPlayer-compatible API
    # ==================================================================

    def setNotifyInterval(self, interval):
        self._notify_interval = max(20, int(interval))
        self._timer.setInterval(self._notify_interval)

    def setVolume(self, volume):
        if self._shutting_down:
            return

        self._volume = max(0, min(100, int(volume)))

        if self._player is None:
            return

        try:
            self._player.audio_set_volume(self._volume)
        except Exception:
            pass

    def volume(self):
        if self._player is None:
            return self._volume

        try:
            value = self._player.audio_get_volume()

            if value is None or value < 0:
                return self._volume

            return int(value)

        except Exception:
            return self._volume

    def setMedia(self, media):
        if self._shutting_down or self._player is None:
            return

        filename = self._get_filename(media)

        if not filename:
            return

        self._timer.stop()

        try:
            self._player.stop()
        except Exception:
            pass

        if self._media is not None:
            try:
                self._media.release()
            except Exception:
                pass

            self._media = None

        self._media_loaded = False

        self._last_position = -1
        self._last_duration = -1

        self._ended = False
        self._state = QMediaPlayer.StoppedState
        self._media_status = QMediaPlayer.NoMedia

        try:
            self._media = self._instance.media_new(filename)

            self._player.set_media(self._media)
            self._player.audio_set_volume(self._volume)

            self._media_loaded = True
            self._media_status = QMediaPlayer.LoadedMedia

        except Exception:
            self._media = None
            self._media_loaded = False
            self._media_status = QMediaPlayer.NoMedia
            return

        self._timer.start()

    def play(self):
        if self._media is None or self._shutting_down:
            return

        # --------------------------------------------------------------
        # Restart after EOF.
        #
        # VLC cannot always transition directly from Ended -> Playing
        # with set_time(0) + play(). Stop the player first, then seek to
        # zero and start it again.
        # --------------------------------------------------------------

        if self._ended:
            try:
                self._player.stop()
            except Exception:
                return

            self._ended = False
            self._state = QMediaPlayer.StoppedState

            # Let VLC finish transitioning from Ended -> Stopped before
            # changing the playback position.
            QTimer.singleShot(
                0,
                self._restartFromBeginning
            )

            return

        try:
            result = self._player.play()
        except Exception:
            return

        if result == -1:
            return

        self._state = QMediaPlayer.PlayingState
        self._media_status = QMediaPlayer.LoadedMedia
        self._timer.start()
    
    def _restartFromBeginning(self):
        if self._shutting_down or self._media is None:
            return

        try:
            self._player.set_time(0)
        except Exception:
            return

        self._last_position = 0
        self.positionChanged.emit(0)

        try:
            result = self._player.play()
        except Exception:
            return

        if result == -1:
            return

        self._state = QMediaPlayer.PlayingState
        self._media_status = QMediaPlayer.LoadedMedia
        self._timer.start()

    def pause(self):
        if self._media is None or self._shutting_down:
            return

        try:
            self._player.pause()
        except Exception:
            return

        self._state = QMediaPlayer.PausedState
        self._timer.start()

    def stop(self):
        if self._media is None or self._shutting_down:
            return

        # Do not repeatedly call VLC stop().
        #
        # VLC stop() flushes the decoder. Repeated stop/start cycles are
        # one of the things that can produce H264 decoder warnings.
        if self._state == QMediaPlayer.StoppedState and not self._ended:
            self.positionChanged.emit(0)
            return

        try:
            self._player.stop()
        except Exception:
            pass

        self._ended = False
        self._state = QMediaPlayer.StoppedState

        self._last_position = 0
        self.positionChanged.emit(0)

        self._timer.start()

    def setPosition(self, position):
        if self._media is None or self._shutting_down:
            return

        if self._last_duration > 0:
            position = max(
                0,
                min(int(position), self._last_duration)
            )
        else:
            position = max(0, int(position))

        was_playing = (
            self._state == QMediaPlayer.PlayingState
        )

        try:
            self._player.set_time(position)
        except Exception:
            return

        # Seeking means we are no longer at EOF.
        self._ended = False

        self._last_position = position
        self.positionChanged.emit(position)

        # Preserve the playback state.
        if was_playing:
            self._state = QMediaPlayer.PlayingState
            self._timer.start()
        else:
            self._state = QMediaPlayer.PausedState
            self._timer.start()

    def position(self):
        if self._player is None or self._shutting_down:
            return 0

        try:
            position = self._player.get_time()

            if position is None or position < 0:
                return 0

            return int(position)

        except Exception:
            return 0

    def duration(self):
        if self._player is None or self._shutting_down:
            return 0

        try:
            duration = self._player.get_length()

            if duration is None or duration < 0:
                return 0

            return int(duration)

        except Exception:
            return 0

    # ==================================================================
    # State compatibility
    # ==================================================================

    def state(self):
        return self._state

    def mediaStatus(self):
        if self._player is None or self._shutting_down:
            return QMediaPlayer.NoMedia

        if not self._media_loaded:
            return QMediaPlayer.NoMedia

        return self._media_status

    # ==================================================================
    # VLC events
    # ==================================================================

    def _on_end_reached(self, event):
        if self._shutting_down:
            return

        self._ended = True
        self._state = QMediaPlayer.StoppedState
        self._media_status = QMediaPlayer.LoadedMedia

        if self._last_duration > 0:
            self._last_position = self._last_duration
            self.positionChanged.emit(self._last_duration)

        self.ended.emit()

        # Keep polling alive so seeking continues to work.
        self._timer.start()

    # ==================================================================
    # Polling
    # ==================================================================

    def _update(self):
        if self._shutting_down or self._player is None:
            return

        self._update_duration()

        # Do not allow the normal polling code to overwrite EOF state.
        if self._ended:
            return

        self._update_position()
        self._update_state()

    def _update_position(self):
        try:
            position = self._player.get_time()

            if position is None or position < 0:
                return

            position = int(position)

            if position != self._last_position:
                self._last_position = position
                self.positionChanged.emit(position)

        except Exception:
            pass

    def _update_duration(self):
        try:
            duration = self._player.get_length()

            if duration is None or duration <= 0:
                return

            duration = int(duration)

            if duration != self._last_duration:
                self._last_duration = duration
                self.durationChanged.emit(duration)

        except Exception:
            pass

    def _update_state(self):
        try:
            vlc_state = self._player.get_state()

            if vlc_state == vlc.State.Playing:
                self._state = QMediaPlayer.PlayingState
                self._media_status = QMediaPlayer.LoadedMedia

            elif vlc_state == vlc.State.Paused:
                self._state = QMediaPlayer.PausedState
                self._media_status = QMediaPlayer.LoadedMedia

            elif vlc_state == vlc.State.Ended:
                # EndReached normally handles this.
                #
                # Do not duplicate EOF handling here.
                self._ended = True
                self._state = QMediaPlayer.StoppedState

            elif vlc_state == vlc.State.Stopped:
                self._state = QMediaPlayer.StoppedState

        except Exception:
            pass

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _get_filename(media):
        if isinstance(media, QMediaContent):
            url = media.canonicalUrl()

            if url.isLocalFile():
                return url.toLocalFile()

            return url.toString()

        if isinstance(media, QtCore.QUrl):
            if media.isLocalFile():
                return media.toLocalFile()

            return media.toString()

        if isinstance(media, str):
            return media

        return str(media)

    # ==================================================================
    # Cleanup
    # ==================================================================

    def shutdown(self):
        if self._shutting_down:
            return

        self._shutting_down = True
        self._timer.stop()

        player = self._player
        media = self._media
        instance = self._instance

        self._player = None
        self._media = None
        self._media_loaded = False

        if player is not None:
            try:
                player.stop()
            except Exception:
                pass

            try:
                player.event_manager().event_detach(
                    vlc.EventType.MediaPlayerEndReached,
                    self._on_end_reached
                )
            except Exception:
                pass

            try:
                player.set_media(None)
            except Exception:
                pass

        if media is not None:
            try:
                media.release()
            except Exception:
                pass

        if player is not None:
            try:
                player.release()
            except Exception:
                pass

        if instance is not None:
            try:
                instance.release()
            except Exception:
                pass


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
        self.__shutting_down = False

        self.__vlc = vlc.Instance(
            "--no-video-title-show"
        )

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
            self
        )

        self.__videoControlWidget.setPlayer(
            self.__vlcPlayer
        )

        # EOF -> restore Play button.
        self.__vlcPlayer.ended.connect(
            self.__onPlaybackEnded
        )

        self.__setupVideoOutput()

        # --------------------------------------------------------------
        # Fullscreen support.
        #
        # The VLC surface is a native child window, so the containing
        # QMainWindow does not reliably receive double-click events.
        # Listen at QApplication level instead.
        # --------------------------------------------------------------

        self.__lastClickTime = 0
        self.__lastClickPosition = None

        app = QApplication.instance()

        if app is not None:
            app.installEventFilter(self)
            self.__app = app
        else:
            self.__app = None

    # ==================================================================
    # Public API
    # ==================================================================

    def shutdown(self):
        if self.__shutting_down:
            return

        self.__shutting_down = True

        if self.__app is not None:
            try:
                self.__app.removeEventFilter(self)
            except Exception:
                pass

        self.__mouseTimer.stop()
        self.__timer.stop()

        self.__videoControlWidget.setVisible(False)

        self.__vlcPlayer.shutdown()

    def getControlWidget(self):
        return self.__videoControlWidget

    # ==================================================================
    # EOF UI
    # ==================================================================

    def __onPlaybackEnded(self):
        if self.__shutting_down:
            return

        # VideoControlWidget does not expose a public method for changing
        # the button icon without changing playback state.
        #
        # We only change the icon here; actual playback state remains in
        # VLCPlayerAdapter.
        button = getattr(
            self.__videoControlWidget,
            "_VideoControlWidget__playBtn",
            None
        )

        if button is not None:
            button.setIcon("ico/play.svg")

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
        self.__view = VLCVideoSurface(self)

        self.__videoControlWidget = VideoControlWidget(
            volume,
            control_alignment=control_alignment,
            style=style,
            spacing=spacing,
            buttons_down=buttons_down
        )

        self.__videoControlWidget.setMaximumHeight(
            max_height
        )

        self.__videoControlWidget.seeked.connect(
            self.__seekPosition
        )

        self.__controlsContainer = QFrame(self)

        self.__controlsContainer.setFrameShape(
            QFrame.NoFrame
        )

        self.__controlsContainer.setFixedHeight(
            max_height
        )

        self.__controlsContainer.setStyleSheet(
            "background: transparent;"
        )

        controlsLayout = QGridLayout(
            self.__controlsContainer
        )

        controlsLayout.setContentsMargins(
            0, 0, 0, 0
        )

        controlsLayout.setHorizontalSpacing(0)
        controlsLayout.setVerticalSpacing(0)

        controlsLayout.addWidget(
            self.__videoControlWidget,
            0,
            0
        )

        self.__videoControlWidget.setVisible(False)

        self.__shortcut = QShortcut(
            QKeySequence(Qt.Key_Space),
            self
        )

        def on_spacebar_pressed():
            if self.__shutting_down:
                return

            if show_control_on_spacebar:
                self.__showControls()

            self.__togglePlayback()

        self.__shortcut.activated.connect(
            on_spacebar_pressed
        )

        lay = QGridLayout()

        lay.setContentsMargins(
            0,
            0,
            0,
            0
        )

        lay.setHorizontalSpacing(0)
        lay.setVerticalSpacing(0)

        lay.addWidget(
            self.__view,
            0,
            0
        )

        lay.addWidget(
            self.__controlsContainer,
            1,
            0
        )

        lay.setRowStretch(0, 1)
        lay.setRowStretch(1, 0)

        self.setLayout(lay)

        self.__hideShowInterval = 2000

        self.__timer = QTimer(self)
        self.__timer.setSingleShot(True)
        self.__timer.timeout.connect(
            self.__bottomWidgetToggled
        )

        self.__lastMousePosition = QCursor.pos()

        self.__mouseTimer = QTimer(self)
        self.__mouseTimer.setInterval(50)
        self.__mouseTimer.timeout.connect(
            self.__checkMousePosition
        )
        self.__mouseTimer.start()

    # ==================================================================
    # VLC output
    # ==================================================================

    def __setupVideoOutput(self):
        self.__view.winId()
        self.__setVlcVideoOutput()

    def __setVlcVideoOutput(self):
        if self.__shutting_down:
            return

        if self.__vlcPlayer._player is None:
            return

        wid = int(self.__view.winId())

        try:
            if sys.platform.startswith("win"):
                self.__vlcPlayer._player.set_hwnd(wid)

            elif sys.platform.startswith("linux"):
                self.__vlcPlayer._player.set_xwindow(wid)

            elif sys.platform == "darwin":
                self.__vlcPlayer._player.set_nsobject(wid)

        except Exception:
            pass

    # ==================================================================
    # Media
    # ==================================================================

    def setMedia(self, filename):
        if self.__shutting_down:
            return

        self.__filename = filename

        self.__videoControlWidget.setMedia(
            filename
        )

    # ==================================================================
    # Playback
    # ==================================================================

    def play(self):
        if self.__shutting_down:
            return

        self.__videoControlWidget.play()

    def stop(self):
        if self.__shutting_down:
            return

        self.__videoControlWidget.stop()

    def __togglePlayback(self):
        if self.__shutting_down:
            return

        if (
            self.__vlcPlayer.mediaStatus()
            == QMediaPlayer.NoMedia
        ):
            return

        if (
            self.__vlcPlayer.state()
            == QMediaPlayer.PlayingState
        ):
            self.__videoControlWidget.pause()

        else:
            self.__videoControlWidget.play()

    # ==================================================================
    # Seeking
    # ==================================================================

    def __seekPosition(self, position):
        if self.__shutting_down:
            return

        self.__vlcPlayer.setPosition(
            int(position)
        )

    # ==================================================================
    # Fullscreen
    # ==================================================================

    def eventFilter(self, obj, event):
        if self.__shutting_down:
            return super().eventFilter(obj, event)

        if event.type() == QtCore.QEvent.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:

                position = QCursor.pos()

                if self.__isInsideVideo(position):
                    window = self.window()

                    if window is not None:
                        if window.isFullScreen():
                            window.showNormal()
                        else:
                            window.showFullScreen()

                        return True

        return super().eventFilter(obj, event)

    # ==================================================================
    # Global mouse handling
    # ==================================================================

    def __getGlobalRect(self, widget):
        top_left = widget.mapToGlobal(
            widget.rect().topLeft()
        )

        return widget.rect().translated(
            top_left
        )

    def __isInsidePlayer(self, position):
        return self.__getGlobalRect(
            self
        ).contains(position)

    def __isInsideVideo(self, position):
        return self.__getGlobalRect(
            self.__view
        ).contains(position)

    def __isInsideControls(self, position):
        if not self.__videoControlWidget.isVisible():
            return False

        return self.__getGlobalRect(
            self.__videoControlWidget
        ).contains(position)

    def __checkMousePosition(self):
        if self.__shutting_down:
            return

        position = QCursor.pos()

        moved = (
            position != self.__lastMousePosition
        )

        self.__lastMousePosition = position

        if not self.__isInsidePlayer(position):
            self.__timer.stop()
            self.__videoControlWidget.setVisible(False)
            self.unsetCursor()
            return

        if self.__isInsideControls(position):
            self.__timer.stop()
            self.__videoControlWidget.setVisible(True)
            self.unsetCursor()
            return

        if self.__isInsideVideo(position):
            if moved:
                self.__showControls()

            return

        if moved:
            self.__showControls()

    # ==================================================================
    # Control visibility
    # ==================================================================

    def __showControls(self):
        if self.__shutting_down:
            return

        self.__videoControlWidget.setVisible(True)

        self.__timer.stop()
        self.__timer.start(
            self.__hideShowInterval
        )

        self.unsetCursor()

    def __bottomWidgetToggled(self):
        if self.__shutting_down:
            return

        position = QCursor.pos()

        if self.__isInsideControls(position):
            self.__timer.stop()
            return

        if self.__isInsidePlayer(position):
            self.__videoControlWidget.setVisible(False)

        self.unsetCursor()

    # ==================================================================
    # Qt events
    # ==================================================================

    def enterEvent(self, event):
        if not self.__shutting_down:
            self.__showControls()

        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.__shutting_down:
            position = QCursor.pos()

            if not self.__isInsideControls(position):
                self.__timer.stop()
                self.__videoControlWidget.setVisible(False)

        super().leaveEvent(event)

    # ==================================================================
    # Cleanup
    # ==================================================================

    def closeEvent(self, event):
        self.shutdown()
        event.accept()

    def __del__(self):
        pass