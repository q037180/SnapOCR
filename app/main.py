"""SnapOCR 入口。运行：python entry.py"""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app import config
from app.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口仅隐藏到托盘

    window = MainWindow(preload="--smoke" not in sys.argv)
    window.show()

    if "--smoke" in sys.argv:
        QTimer.singleShot(1500, app.quit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
