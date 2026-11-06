"""SnapOCR 入口。运行：python entry.py"""
import ctypes
import os
import sys
import time

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from app import config
from app.ui.main_window import MainWindow

# 单实例锁：多开会让两个进程各自持有一份历史快照互相覆盖，
# 还会各装一套全局键盘钩子（按一次热键弹出两个截图遮罩）。
_SERVER_NAME = "SnapOCR-single-instance"
_MUTEX_NAME = "Local\\SnapOCR-single-instance"
_ERROR_ALREADY_EXISTS = 183


def _notify_running_instance() -> bool:
    """已有实例在运行：请求它把窗口显示出来，本进程直接退出。"""
    sock = QLocalSocket()
    sock.connectToServer(_SERVER_NAME)
    # 首个实例偶尔正忙于主线程操作（弹窗、保存），给足 0.8 秒再判定「没在跑」
    if not sock.waitForConnected(800):
        return False
    sock.write(b"show\n")
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def _acquire_instance_lock():
    """抢占进程级单实例锁，返回 (句柄, 是否拿到)。

    QLocalServer 只能「尽力」保证单实例：两个进程几乎同时启动时，双方都还没
    listen，互相探不到对方，于是双双起来（两套热键钩子、两份历史互相覆盖）。
    先抢一个内核互斥体 / 文件锁，这一步是原子的，才能确定性只留一个。

    互斥体随进程结束由内核释放，不会像锁文件那样在崩溃后残留。非 Windows
    平台用 QLockFile（同样带进程存活校验），拿不到就退化为「不阻断启动」。
    """
    if sys.platform == "win32":
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = ctypes.c_void_p
            k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            k32.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = k32.CreateMutexW(None, False, _MUTEX_NAME)
        except Exception:  # noqa: BLE001 拿不到也不该让程序起不来
            return None, True
        if not handle:
            return None, True
        if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
            k32.CloseHandle(handle)
            return None, False
        return handle, True

    lock = QLockFile(os.path.join(config.DATA_DIR, "snapocr.lock"))
    lock.setStaleLockTime(30000)
    if lock.tryLock(0):
        return lock, True
    return None, False


def _start_single_instance_server(get_window) -> QLocalServer:
    """监听本地套接字：第二个进程连上来时把已有窗口唤起。

    在创建主窗口之前就 listen，缩小「先抢到锁但还没准备好被唤起」的窗口期。
    """
    QLocalServer.removeServer(_SERVER_NAME)  # 清掉上次异常退出残留的名字
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(_SERVER_NAME):
        # 端口名被占用/权限异常：再清一次重试；仍失败也不影响主功能，
        # 只是唤起不了已有窗口（单实例由上面的锁保证）
        QLocalServer.removeServer(_SERVER_NAME)
        server.listen(_SERVER_NAME)

    def _on_new_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readAll()
            conn.disconnectFromServer()
            conn.deleteLater()
        window = get_window()
        if window is not None:
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
    if single:
        held, acquired = _acquire_instance_lock()
        app._instance_lock = held  # noqa: SLF001 必须活到进程结束
        if not acquired:
            # 已有实例：请它把窗口叫出来。对方可能还在启动，重试若干次
            for _ in range(12):
                if _notify_running_instance():
                    sys.exit(0)
                time.sleep(0.08)
            QMessageBox.information(
                None, config.APP_NAME,
                f"{config.APP_NAME} 已经在运行了。\n"
                "如果没看到窗口，请从任务栏托盘图标里打开它。",
            )
            sys.exit(0)

    holder: dict = {"window": None}
    if single:
        # 挂到 app 上保持引用，否则 server 被回收后套接字立刻失效
        app._single_instance_server = _start_single_instance_server(  # noqa: SLF001
            lambda: holder["window"]
        )

    window = MainWindow(preload="--smoke" not in sys.argv)
    holder["window"] = window
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

