from PyQt5.QtWidgets import QApplication
from pyqt_graphics_video_item_video_player.videoPlayer import VideoPlayer

if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    videoPlayer = VideoPlayer()
    videoPlayer.show()
    videoPlayer.setMedia("./4chan4evar.mp4")
    app.exec_()