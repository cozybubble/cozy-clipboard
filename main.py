import sys
import queue
from PyQt6.QtWidgets import QApplication

from config import (
    MAX_ITEMS,
    POLL_INTERVAL,
    QUEUE_POLL_MS,
    HISTORY_FILE,
    HOTKEY,
    WINDOW_TITLE,
    WINDOW_SIZE,
    FONT_SETTING,
    STATUS_FONT
)
from history_manager import HistoryManager
from clipboard_worker import ClipboardWorker
from gui import ClipboardGUI
from window_manager import get_active_window, HAS_WIN32


def main():
    if not HAS_WIN32:
        print("请安装 pywin32 后重试: pip install pywin32")
        sys.exit(1)

    # 初始化组件
    cmd_queue = queue.Queue()
    history_manager = HistoryManager(MAX_ITEMS, HISTORY_FILE)

    # 配置参数
    config = {
        "hotkey": HOTKEY,
        "window_title": WINDOW_TITLE,
        "window_size": WINDOW_SIZE,
        "font_setting": FONT_SETTING,
        "status_font": STATUS_FONT,
        "queue_poll_ms": QUEUE_POLL_MS,
        "cmd_queue": cmd_queue,
        "get_active_window": get_active_window,
    }

    # 启动剪贴板监听线程
    worker = ClipboardWorker(history_manager, POLL_INTERVAL)
    worker.start()

    # 启动 Qt 应用
    app = QApplication(sys.argv)
    gui = ClipboardGUI(history_manager, config)
    # 加载 QSS 样式
    with open("style.qss", "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    gui.show()

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        worker.stop()
        print("退出中...")


if __name__ == "__main__":
    main()
