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
    else:
        # 先让首帧画出来，再注册全局热键、预热识别模型：
        # 窗口秒开，这两件重活挪到用户看到界面之后
        QTimer.singleShot(150, window.start_services)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
