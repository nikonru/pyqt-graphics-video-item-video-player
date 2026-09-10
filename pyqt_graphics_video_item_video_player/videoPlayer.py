import sys
import ctypes

import vlc

from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QKeySequence, QCursor
from PyQt5.QtWidgets import (
    QWidget,
    QGridLayout,
    QShortcut,
    QFrame,
)

from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

from pyqt_graphics_video_item_video_player.videoControlWidget import (
    VideoControlWidget
)


# ======================================================================
# Windows low-level mouse hook structures
# ======================================================================

class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


# ======================================================================
# Windows VLC double-click hook
# ======================================================================

class VLCMouseDoubleClickHook:
    """
    VLC renders the video into a native Windows HWND.

    Because of that, Qt mouse events are not reliable over the video
    surface. This hook listens to Windows mouse messages directly and
    detects a double left click over the VLC video.

    The hook itself NEVER calls Qt geometry methods from the Windows
    mouse callback.

    VideoPlayer periodically calculates the relevant screen rectangles
    and passes plain integer coordinates to this object. The Windows
    callback then only performs integer comparisons.

    The second WM_LBUTTONDOWN is swallowed so VLC does not process the
    double-click itself and attempt to enter VLC's own fullscreen mode.
    """

    WH_MOUSE_LL = 14
    HC_ACTION = 0

    WM_LBUTTONDOWN = 0x0201

    SPI_GETDOUBLECLICKWIDTH = 0x0024
    SPI_GETDOUBLECLICKHEIGHT = 0x0026

    def __init__(self, video_player):
        self.__video_player = video_player

        self.__hook = None
        self.__callback = None

        self.__last_click_time = 0
        self.__last_click_x = 0
        self.__last_click_y = 0

        self.__video_player_rect = (
            0,
            0,
            0,
            0,
        )

        self.__controls_rect = (
            0,
            0,
            0,
            0,
        )

        self.__user32 = ctypes.windll.user32

        # --------------------------------------------------------------
        # Explicit ctypes signatures.
        # --------------------------------------------------------------

        self.__user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]

        self.__user32.SetWindowsHookExW.restype = ctypes.c_void_p

        self.__user32.UnhookWindowsHookEx.argtypes = [
            ctypes.c_void_p,
        ]

        self.__user32.UnhookWindowsHookEx.restype = ctypes.c_int

        self.__user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]

        self.__user32.CallNextHookEx.restype = ctypes.c_ssize_t

        self.__user32.GetDoubleClickTime.argtypes = []

        self.__user32.GetDoubleClickTime.restype = ctypes.c_uint32

        self.__user32.SystemParametersInfoW.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]

        self.__user32.SystemParametersInfoW.restype = ctypes.c_int

        # --------------------------------------------------------------
        # Windows double-click settings.
        # --------------------------------------------------------------

        self.__double_click_time = (
            self.__user32.GetDoubleClickTime()
        )

        self.__double_click_width = 4
        self.__double_click_height = 4

        width = ctypes.c_uint(0)
        height = ctypes.c_uint(0)

        try:
            if self.__user32.SystemParametersInfoW(
                self.SPI_GETDOUBLECLICKWIDTH,
                0,
                ctypes.byref(width),
                0,
            ):
                self.__double_click_width = width.value

            if self.__user32.SystemParametersInfoW(
                self.SPI_GETDOUBLECLICKHEIGHT,
                0,
                ctypes.byref(height),
                0,
            ):
                self.__double_click_height = height.value

        except Exception:
            pass

        self.__install()

    # ==================================================================
    # Hook installation
    # ==================================================================

    def __install(self):
        if sys.platform != "win32":
            return

        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.c_int,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        )

        self.__callback = HOOKPROC(
            self.__mouse_proc
        )

        hook = self.__user32.SetWindowsHookExW(
            self.WH_MOUSE_LL,
            self.__callback,
            None,
            0,
        )

        if hook:
            self.__hook = hook

        else:
            self.__hook = None
            self.__callback = None

    # ==================================================================
    # Geometry
    # ==================================================================

    def updateGeometry(
        self,
        player_rect,
        controls_rect
    ):
        self.__video_player_rect = (
            player_rect
        )

        self.__controls_rect = (
            controls_rect
        )

    def __is_inside_video(self, x, y):
        player_rect = (
            self.__video_player_rect
        )

        if not (
            player_rect[0] <= x < player_rect[2]
            and
            player_rect[1] <= y < player_rect[3]
        ):
            return False

        controls_rect = (
            self.__controls_rect
        )

        if (
            controls_rect[0] <= x < controls_rect[2]
            and
            controls_rect[1] <= y < controls_rect[3]
        ):
            return False

        return True

    # ==================================================================
    # Windows hook
    # ==================================================================

    def __call_next(
        self,
        n_code,
        w_param,
        l_param
    ):
        return self.__user32.CallNextHookEx(
            self.__hook,
            n_code,
            w_param,
            l_param,
        )

    def __mouse_proc(
        self,
        n_code,
        w_param,
        l_param
    ):
        if n_code < 0:
            return self.__call_next(
                n_code,
                w_param,
                l_param,
            )

        if w_param == self.WM_LBUTTONDOWN:

            try:
                data = ctypes.cast(
                    l_param,
                    ctypes.POINTER(
                        MSLLHOOKSTRUCT
                    ),
                ).contents

                x = data.pt.x
                y = data.pt.y
                current_time = data.time

                if not self.__is_inside_video(
                    x,
                    y
                ):
                    return self.__call_next(
                        n_code,
                        w_param,
                        l_param,
                    )

                time_diff = (
                    current_time
                    - self.__last_click_time
                ) & 0xFFFFFFFF

                distance_x = abs(
                    x - self.__last_click_x
                )

                distance_y = abs(
                    y - self.__last_click_y
                )

                distance_ok = (
                    distance_x
                    <= self.__double_click_width
                    and
                    distance_y
                    <= self.__double_click_height
                )

                if (
                    self.__last_click_time != 0
                    and
                    time_diff
                    <= self.__double_click_time
                    and
                    distance_ok
                ):

                    self.__last_click_time = 0

                    try:
                        if self.__video_player is not None:

                            # Queue the fullscreen operation on
                            # Qt's event loop.
                            QtCore.QTimer.singleShot(
                                0,
                                self.__video_player.toggleFullscreen
                            )

                    except Exception as e:
                        print(
                            "[VLCMouseDoubleClickHook] "
                            f"toggleFullscreen error: {e}"
                        )

                    # Prevent VLC from handling the second click.
                    return 1

                self.__last_click_time = (
                    current_time
                )

                self.__last_click_x = x
                self.__last_click_y = y

            except Exception as e:
                print(
                    "[VLCMouseDoubleClickHook] "
                    f"mouse_proc error: {e}"
                )

        return self.__call_next(
            n_code,
            w_param,
            l_param,
        )

    # ==================================================================
    # Cleanup
    # ==================================================================

    def uninstall(self):
        hook = self.__hook

        self.__hook = None

        if hook:
            try:
                self.__user32.UnhookWindowsHookEx(
                    hook
                )
            except Exception:
                pass

        self.__video_player = None
        self.__callback = None
        self.__last_click_time = 0


# ======================================================================
# VLC video surface
# ======================================================================

class VLCVideoSurface(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFrameShape(
            QFrame.NoFrame
        )

        self.setFrameShadow(
            QFrame.Plain
        )

        self.setAttribute(
            Qt.WA_NativeWindow,
            True
        )

        self.setAttribute(
            Qt.WA_OpaquePaintEvent,
            True
        )

        self.setStyleSheet(
            "background: black;"
        )


# ======================================================================
# VLC player adapter
# ======================================================================

class VLCPlayerAdapter(QtCore.QObject):

    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    ended = pyqtSignal()

    # --------------------------------------------------------------
    # VLC callbacks execute on VLC's own thread.
    #
    # This signal transfers EOF handling back to this QObject's Qt
    # thread before any QTimer or Qt-owned state is touched.
    # --------------------------------------------------------------

    _endReachedSignal = pyqtSignal()

    def __init__(
        self,
        vlc_instance,
        parent=None
    ):
        super().__init__(parent)

        self._instance = vlc_instance

        self._player = (
            self._instance.media_player_new()
        )

        self._media = None

        self._volume = 100
        self._notify_interval = 50

        self._last_position = -1
        self._last_duration = -1

        self._media_loaded = False
        self._shutting_down = False

        self._state = (
            QMediaPlayer.StoppedState
        )

        self._media_status = (
            QMediaPlayer.NoMedia
        )

        self._ended = False

        self._timer = QTimer(self)

        self._timer.setInterval(
            self._notify_interval
        )

        self._timer.timeout.connect(
            self._update
        )

        # --------------------------------------------------------------
        # IMPORTANT:
        #
        # _on_end_reached() is called by VLC's thread.
        #
        # QueuedConnection guarantees that _handle_end_reached()
        # executes on this QObject's Qt thread.
        # --------------------------------------------------------------

        self._endReachedSignal.connect(
            self._handle_end_reached,
            QtCore.Qt.QueuedConnection
        )

        event_manager = (
            self._player.event_manager()
        )

        event_manager.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            self._on_end_reached
        )

    # ==================================================================
    # QMediaPlayer-compatible API
    # ==================================================================

    def setNotifyInterval(self, interval):
        self._notify_interval = max(
            20,
            int(interval)
        )

        self._timer.setInterval(
            self._notify_interval
        )

    def setVolume(self, volume):
        if self._shutting_down:
            return

        self._volume = max(
            0,
            min(100, int(volume))
        )

        if self._player is None:
            return

        try:
            self._player.audio_set_volume(
                self._volume
            )
        except Exception:
            pass

    def volume(self):
        if self._player is None:
            return self._volume

        try:
            value = (
                self._player.audio_get_volume()
            )

            if value is None or value < 0:
                return self._volume

            return int(value)

        except Exception:
            return self._volume

    def setMedia(self, media):
        if (
            self._shutting_down
            or self._player is None
        ):
            return

        filename = self._get_filename(
            media
        )

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

        self._state = (
            QMediaPlayer.StoppedState
        )

        self._media_status = (
            QMediaPlayer.NoMedia
        )

        try:
            self._media = (
                self._instance.media_new(
                    filename
                )
            )

            self._player.set_media(
                self._media
            )

            self._player.audio_set_volume(
                self._volume
            )

            self._media_loaded = True

            self._media_status = (
                QMediaPlayer.LoadedMedia
            )

        except Exception:
            self._media = None
            self._media_loaded = False

            self._media_status = (
                QMediaPlayer.NoMedia
            )

            return

        self._timer.start()

    def play(self):
        if (
            self._media is None
            or self._shutting_down
        ):
            return

        if self._ended:

            try:
                self._player.stop()

            except Exception:
                return

            self._ended = False

            self._state = (
                QMediaPlayer.StoppedState
            )

            QTimer.singleShot(
                0,
                self._restartFromBeginning
            )

            return

        try:
            result = (
                self._player.play()
            )

        except Exception:
            return

        if result == -1:
            return

        self._state = (
            QMediaPlayer.PlayingState
        )

        self._media_status = (
            QMediaPlayer.LoadedMedia
        )

        self._timer.start()

    def _restartFromBeginning(self):
        if (
            self._shutting_down
            or self._media is None
        ):
            return

        try:
            self._player.set_time(0)

        except Exception:
            return

        self._last_position = 0

        self.positionChanged.emit(0)

        try:
            result = (
                self._player.play()
            )

        except Exception:
            return

        if result == -1:
            return

        self._state = (
            QMediaPlayer.PlayingState
        )

        self._media_status = (
            QMediaPlayer.LoadedMedia
        )

        self._timer.start()

    def pause(self):
        if (
            self._media is None
            or self._shutting_down
        ):
            return

        try:
            self._player.pause()

        except Exception:
            return

        self._state = (
            QMediaPlayer.PausedState
        )

        self._timer.start()

    def stop(self):
        if (
            self._media is None
            or self._shutting_down
        ):
            return

        if (
            self._state
            == QMediaPlayer.StoppedState
            and not self._ended
        ):
            self.positionChanged.emit(0)
            return

        try:
            self._player.stop()

        except Exception:
            pass

        self._ended = False

        self._state = (
            QMediaPlayer.StoppedState
        )

        self._last_position = 0

        self.positionChanged.emit(0)

        self._timer.start()

    def setPosition(self, position):
        if (
            self._media is None
            or self._shutting_down
        ):
            return

        if self._last_duration > 0:

            position = max(
                0,
                min(
                    int(position),
                    self._last_duration
                )
            )

        else:

            position = max(
                0,
                int(position)
            )

        was_playing = (
            self._state
            == QMediaPlayer.PlayingState
        )

        try:
            self._player.set_time(
                position
            )

        except Exception:
            return

        self._ended = False

        self._last_position = position

        self.positionChanged.emit(
            position
        )

        if was_playing:

            self._state = (
                QMediaPlayer.PlayingState
            )

        else:

            self._state = (
                QMediaPlayer.PausedState
            )

        self._timer.start()

    def position(self):
        if (
            self._player is None
            or self._shutting_down
        ):
            return 0

        try:
            position = (
                self._player.get_time()
            )

            if (
                position is None
                or position < 0
            ):
                return 0

            return int(position)

        except Exception:
            return 0

    def duration(self):
        if (
            self._player is None
            or self._shutting_down
        ):
            return 0

        try:
            duration = (
                self._player.get_length()
            )

            if (
                duration is None
                or duration < 0
            ):
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
        if (
            self._player is None
            or self._shutting_down
        ):
            return QMediaPlayer.NoMedia

        if not self._media_loaded:
            return QMediaPlayer.NoMedia

        return self._media_status

    # ==================================================================
    # VLC events
    # ==================================================================

    def _on_end_reached(self, event):
        """
        VLC calls this from a VLC worker thread.

        DO NOT touch QTimer or other Qt-owned objects here.
        """

        if self._shutting_down:
            return

        # Transfer EOF processing to the Qt thread.
        self._endReachedSignal.emit()

    def _handle_end_reached(self):
        """
        Runs on the Qt thread.
        """

        if self._shutting_down:
            return

        self._ended = True

        self._state = (
            QMediaPlayer.StoppedState
        )

        self._media_status = (
            QMediaPlayer.LoadedMedia
        )

        if self._last_duration > 0:

            self._last_position = (
                self._last_duration
            )

            self.positionChanged.emit(
                self._last_duration
            )

        self.ended.emit()

        # Safe because this method runs on the Qt thread.
        self._timer.start()

    # ==================================================================
    # Polling
    # ==================================================================

    def _update(self):
        if (
            self._shutting_down
            or self._player is None
        ):
            return

        self._update_duration()

        if self._ended:
            return

        self._update_position()
        self._update_state()

    def _update_position(self):
        try:
            position = (
                self._player.get_time()
            )

            if (
                position is None
                or position < 0
            ):
                return

            position = int(position)

            if position != self._last_position:

                self._last_position = position

                self.positionChanged.emit(
                    position
                )

        except Exception:
            pass

    def _update_duration(self):
        try:
            duration = (
                self._player.get_length()
            )

            if (
                duration is None
                or duration <= 0
            ):
                return

            duration = int(duration)

            if duration != self._last_duration:

                self._last_duration = duration

                self.durationChanged.emit(
                    duration
                )

        except Exception:
            pass

    def _update_state(self):
        try:
            vlc_state = (
                self._player.get_state()
            )

            if vlc_state == vlc.State.Playing:

                self._state = (
                    QMediaPlayer.PlayingState
                )

                self._media_status = (
                    QMediaPlayer.LoadedMedia
                )

            elif vlc_state == vlc.State.Paused:

                self._state = (
                    QMediaPlayer.PausedState
                )

                self._media_status = (
                    QMediaPlayer.LoadedMedia
                )

            elif vlc_state == vlc.State.Ended:

                self._ended = True

                self._state = (
                    QMediaPlayer.StoppedState
                )

            elif vlc_state == vlc.State.Stopped:

                self._state = (
                    QMediaPlayer.StoppedState
                )

        except Exception:
            pass

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _get_filename(media):

        if isinstance(
            media,
            QMediaContent
        ):

            url = media.canonicalUrl()

            if url.isLocalFile():
                return url.toLocalFile()

            return url.toString()

        if isinstance(
            media,
            QtCore.QUrl
        ):

            if media.isLocalFile():
                return media.toLocalFile()

            return media.toString()

        if isinstance(
            media,
            str
        ):

            return media

        return str(media)

    # ==================================================================
    # Cleanup
    # ==================================================================

    def shutdown(self):
        if self._shutting_down:
            return

        self._shutting_down = True

        # The adapter is always shut down from the Qt thread.
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


# ======================================================================
# VideoPlayer
# ======================================================================

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

        self.__vlcPlayer.ended.connect(
            self.__onPlaybackEnded
        )

        self.__mouseHook = None

    # ==================================================================
    # Fullscreen
    # ==================================================================

    def toggleFullscreen(self):

        if self.__shutting_down:
            return

        window = self.window()

        if window is None:
            return

        try:

            if window.isFullScreen():
                window.showNormal()

            else:
                window.showFullScreen()

        except Exception as e:

            print(
                "[VideoPlayer] "
                f"toggleFullscreen error: {e}"
            )

    # ==================================================================
    # Mouse hook lifecycle
    # ==================================================================

    def showEvent(self, event):
        super().showEvent(event)

        if self.__shutting_down:
            return

        if sys.platform == "win32":

            QTimer.singleShot(
                0,
                self.__setupVideoOutput
            )

            QTimer.singleShot(
                0,
                self.__installMouseHook
            )

    def __installMouseHook(self):
        if self.__shutting_down:
            return

        if sys.platform != "win32":
            return

        if self.__mouseHook is not None:
            return

        self.__mouseHook = (
            VLCMouseDoubleClickHook(
                self
            )
        )

        self.__updateMouseHookGeometry()

    def hideEvent(self, event):

        self.__uninstallMouseHook()

        super().hideEvent(event)

    def __uninstallMouseHook(self):

        if self.__mouseHook is None:
            return

        hook = self.__mouseHook

        self.__mouseHook = None

        try:
            hook.uninstall()
        except Exception:
            pass

    # ==================================================================
    # Public API
    # ==================================================================

    def shutdown(self):

        if self.__shutting_down:
            return

        self.__shutting_down = True

        # --------------------------------------------------------------
        # Stop the global mouse hook first.
        # --------------------------------------------------------------

        self.__uninstallMouseHook()

        # --------------------------------------------------------------
        # Stop VideoPlayer timers from the Qt thread.
        # --------------------------------------------------------------

        self.__mouseTimer.stop()
        self.__timer.stop()


        self.__videoControlWidget.setVisible(
            False
        )

        # --------------------------------------------------------------
        # VLCPlayerAdapter.shutdown() also runs on this Qt thread.
        # --------------------------------------------------------------

        self.__vlcPlayer.shutdown()

    def getControlWidget(self):
        return self.__videoControlWidget

    def getVideoSurface(self):
        return self.__view

    # ==================================================================
    # EOF UI
    # ==================================================================

    def __onPlaybackEnded(self):

        if self.__shutting_down:
            return

        button = getattr(
            self.__videoControlWidget,
            "_VideoControlWidget__playBtn",
            None
        )

        if button is not None:

            button.setIcon(
                "ico/play.svg"
            )

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
        self.__view = VLCVideoSurface(
            self
        )

        self.__videoControlWidget = (
            VideoControlWidget(
                volume,
                control_alignment=control_alignment,
                style=style,
                spacing=spacing,
                buttons_down=buttons_down
            )
        )

        self.__videoControlWidget.setMaximumHeight(
            max_height
        )

        self.__videoControlWidget.seeked.connect(
            self.__seekPosition
        )

        self.__controlsContainer = QFrame(
            self
        )

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
            0,
            0,
            0,
            0
        )

        controlsLayout.setHorizontalSpacing(
            0
        )

        controlsLayout.setVerticalSpacing(
            0
        )

        controlsLayout.addWidget(
            self.__videoControlWidget,
            0,
            0
        )

        self.__videoControlWidget.setVisible(
            False
        )

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

        lay.setHorizontalSpacing(
            0
        )

        lay.setVerticalSpacing(
            0
        )

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

        lay.setRowStretch(
            0,
            1
        )

        lay.setRowStretch(
            1,
            0
        )

        self.setLayout(
            lay
        )

        self.__hideShowInterval = 2000

        self.__timer = QTimer(
            self
        )

        self.__timer.setSingleShot(
            True
        )

        self.__timer.timeout.connect(
            self.__bottomWidgetToggled
        )

        self.__lastMousePosition = (
            QCursor.pos()
        )

        self.__mouseTimer = QTimer(
            self
        )

        self.__mouseTimer.setInterval(
            50
        )

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

        wid = int(
            self.__view.winId()
        )

        try:

            if sys.platform.startswith("win"):

                self.__vlcPlayer._player.set_hwnd(
                    wid
                )

            elif sys.platform.startswith("linux"):

                self.__vlcPlayer._player.set_xwindow(
                    wid
                )

            elif sys.platform == "darwin":

                self.__vlcPlayer._player.set_nsobject(
                    wid
                )

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
    # Global mouse-hook geometry
    # ==================================================================

    def __updateMouseHookGeometry(self):

        if self.__shutting_down:
            return

        if self.__mouseHook is None:
            return

        try:

            player_qrect = self.__getGlobalRect(
                self
            )

            player_rect = (
                player_qrect.left(),
                player_qrect.top(),
                player_qrect.left()
                + player_qrect.width(),
                player_qrect.top()
                + player_qrect.height(),
            )

            if self.__videoControlWidget.isVisible():

                controls_qrect = self.__getGlobalRect(
                    self.__videoControlWidget
                )

                controls_rect = (
                    controls_qrect.left(),
                    controls_qrect.top(),
                    controls_qrect.left()
                    + controls_qrect.width(),
                    controls_qrect.top()
                    + controls_qrect.height(),
                )

            else:

                controls_rect = (
                    0,
                    0,
                    0,
                    0,
                )

            self.__mouseHook.updateGeometry(
                player_rect,
                controls_rect
            )

        except Exception as exc:
            print(
                "[VideoPlayer] Mouse hook geometry error:",
                exc
            )

    # ==================================================================
    # Global mouse handling
    # ==================================================================

    def __getGlobalRect(self, widget):
        if widget is None:
            return QtCore.QRect()

        try:
            rect = widget.rect()
            current = widget

            while current is not self:
                parent = current.parentWidget()

                if parent is None:
                    return QtCore.QRect()

                rect.translate(current.pos())
                current = parent

            window = self.window()
            base = window.geometry().topLeft() + self.geometry().topLeft()

            rect.translate(base)

            return rect

        except Exception as exc:
            print(
                "[VideoPlayer] Global rect error:",
                exc
            )
            return QtCore.QRect()

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

        window = self.window()

        self.__updateMouseHookGeometry()

        position = QCursor.pos()

        inside_player = self.__isInsidePlayer(position)
        inside_controls = self.__isInsideControls(position)

        # --------------------------------------------------------------
        # Completely outside VideoPlayer
        # --------------------------------------------------------------

        if not inside_player:

            self.__timer.stop()

            if self.__videoControlWidget.isVisible():
                self.__videoControlWidget.setVisible(False)
                self.__updateMouseHookGeometry()

            self.unsetCursor()
            return

        # --------------------------------------------------------------
        # Mouse is over the controls.
        #
        # IMPORTANT: keep them visible and do NOT start the hide timer.
        # --------------------------------------------------------------

        if inside_controls:
            self.__timer.stop()

        # --------------------------------------------------------------
        # Mouse is inside the video/player but not over controls.
        # --------------------------------------------------------------

        if not self.__videoControlWidget.isVisible():

            self.__videoControlWidget.setVisible(True)
            self.__updateMouseHookGeometry()

        self.__timer.stop()
        self.__timer.start(self.__hideShowInterval)

        self.unsetCursor()
    # ==================================================================
    # Control visibility
    # ==================================================================

    def __showControls(self):

        if self.__shutting_down:
            return

        self.__videoControlWidget.setVisible(
            True
        )

        self.__updateMouseHookGeometry()

        self.__timer.stop()

        self.__timer.start(
            self.__hideShowInterval
        )

        self.unsetCursor()

    def __bottomWidgetToggled(self):

        if self.__shutting_down:
            return

        position = QCursor.pos()

        # Never hide controls while the cursor is over them.
        if self.__isInsideControls(position):
            self.__timer.stop()
            return

        # Hide only when the cursor is inside the player but not
        # over the controls.
        if self.__isInsidePlayer(position):
            self.__videoControlWidget.setVisible(False)
            self.__updateMouseHookGeometry()

        self.unsetCursor()

    # ==================================================================
    # Qt events
    # ==================================================================

    def enterEvent(self, event):

        if not self.__shutting_down:
            self.__showControls()

        super().enterEvent(
            event
        )

    def leaveEvent(self, event):

        if not self.__shutting_down:

            position = QCursor.pos()

            if not self.__isInsideControls(
                position
            ):

                self.__timer.stop()

                self.__videoControlWidget.setVisible(
                    False
                )

                self.__updateMouseHookGeometry()

        super().leaveEvent(
            event
        )

    # ==================================================================
    # Cleanup
    # ==================================================================

    def closeEvent(self, event):

        self.shutdown()

        event.accept()

    def __del__(self):
        pass
