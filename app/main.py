"""SnapOCR 入口。运行：python entry.py"""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from app import config
from app.ui.main_window import MainWindow

# 单实例锁：多开会让两个进程各自持有一份历史快照互相覆盖，
# 还会各装一套全局键盘钩子（按一次热键弹出两个截图遮罩）。
_SERVER_NAME = "SnapOCR-single-instance"


def _notify_running_instance() -> bool:
    """已有实例在运行：请求它把窗口显示出来，本进程直接退出。"""
    sock = QLocalSocket()
    sock.connectToServer(_SERVER_NAME)
    if not sock.waitForConnected(300):
        return False
    sock.write(b"show\n")
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def _start_single_instance_server(window: MainWindow) -> QLocalServer:
    """监听本地套接字；第二个进程连上来时把已有窗口唤起。"""
    QLocalServer.removeServer(_SERVER_NAME)  # 清掉上次异常退出残留的名字
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    server.listen(_SERVER_NAME)

    def _on_new_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readAll()
            conn.disconnectFromServer()
            conn.deleteLater()
        window.show_from_second_instance()

    server.newConnection.connect(_on_new_connection)
    return server


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口仅隐藏到托盘

    # --smoke 用于自动化冒烟测试；--multi 显式允许多开（排查问题时用）
    single = "--smoke" not in sys.argv and "--multi" not in sys.argv
    if single and _notify_running_instance():
        sys.exit(0)

    window = MainWindow(preload="--smoke" not in sys.argv)
    if single:
        # 挂到 app 上保持引用，否则 server 被回收后套接字立刻失效
        app._single_instance_server = _start_single_instance_server(window)  # noqa: SLF001
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
