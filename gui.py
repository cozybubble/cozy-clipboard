import sys
import time
import threading
import pyperclip
import keyboard

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QTextEdit, QSplitter  
)
from PyQt6.QtCore import Qt, QTimer

from window_manager import activate_window


class ClipboardGUI(QMainWindow):
    def __init__(self, history_manager, config):
        super().__init__()
        self.history_manager = history_manager
        self.config = config
        self.cmd_queue = config.get("cmd_queue")

        self.full_history = []
        self.filtered_items = []
        self.previous_window = None
        self.current_window = None
        self.displayed_version = 0

        # === 窗口设置 ===
        self.setWindowTitle(config.get("window_title", "剪贴板历史"))
        self.resize(*[int(x) for x in config.get("window_size", "500x1000").split("x")])
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        # === 主布局 (左右分栏) ===
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)  # 去除边距，让分隔条贴边

        # 创建水平分隔条
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)


        # ---------- 左边区域 ----------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)  # 添加适当的内边距

        # 搜索栏
        search_layout = QHBoxLayout()
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("搜索...")
        self.search_entry.textChanged.connect(self.filter_list)
        clear_btn = QPushButton("×")
        clear_btn.setFixedWidth(30)
        clear_btn.clicked.connect(lambda: self.search_entry.clear())
        search_layout.addWidget(QLabel("搜索:"))
        search_layout.addWidget(self.search_entry)
        search_layout.addWidget(clear_btn)
        left_layout.addLayout(search_layout)

        # 列表
        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.itemDoubleClicked.connect(self.select_and_copy)
        self.list_widget.currentItemChanged.connect(self.update_preview)  # 选中项改变时更新右侧预览
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 确保列表可以获得焦点
        left_layout.addWidget(self.list_widget)

        # 底部栏
        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("历史记录: 0 条")
        clear_history_btn = QPushButton("清空历史")
        clear_history_btn.setObjectName("clearButton")  # 方便 QSS 单独美化
        clear_history_btn.clicked.connect(self.clear_history_confirm)
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(clear_history_btn)
        left_layout.addLayout(bottom_layout)

        # ---------- 右边预览 ----------
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("选中一个条目后在此预览完整内容...")
        #self.preview.setStyleSheet("background:#fafafa; border:1px solid #cccccc; border-radius:6px;")

        # ---------- 将左右部件添加到分隔条 ----------
        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(self.preview)

        # 设置初始比例（可根据需要调整）
        self.splitter.setSizes([300, 400])  # 左边300，右边400

        # === 热键注册 ===
        keyboard.add_hotkey(self.config["hotkey"], self.on_hotkey)

        # === 定时器轮询队列 ===
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.poll_queue)
        self.queue_timer.start(self.config.get("queue_poll_ms", 200))

        # 初始加载
        self.refresh_listbox()

    # ---------------- 功能逻辑 ----------------

    def closeEvent(self, event):
        """重写关闭事件，改为隐藏窗口而非退出程序"""
        event.ignore()  # 忽略默认关闭行为
        self.hide()     # 隐藏窗口

    def update_preview(self, current, previous):
        """更新右侧预览区"""
        if current:
            text = current.data(Qt.ItemDataRole.UserRole)
            self.preview.setPlainText(text)
        else:
            self.preview.clear()

    def on_hotkey(self):
        if self.current_window and self.current_window != self.previous_window:
            self.previous_window = self.current_window
        try:
            self.cmd_queue.put_nowait("show")
        except Exception:
            pass

    def open_history_window(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.refresh_listbox()
        # self.search_entry.setFocus()

    def refresh_listbox(self):
        self.full_history = self.history_manager.get_copy()
        self.filter_list(self.search_entry.text())
        self.status_label.setText(f"历史记录: {len(self.full_history)} 条")
        self.displayed_version = self.history_manager.version

        # 确保列表有项时选中第一项并让列表获得焦点
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            self.list_widget.setFocus()  # 让列表获得焦点，光标不在搜索框

    def filter_list(self, text):
        text = text.strip().lower()
        self.list_widget.clear()
        self.filtered_items = []

        for item in self.full_history:
            if text in item.lower():
                lw_item = QListWidgetItem(self.format_item_text(item))
                lw_item.setData(Qt.ItemDataRole.UserRole, item)
                self.list_widget.addItem(lw_item)
                self.filtered_items.append(item)

        if not text:
            self.status_label.setText(f"历史记录: {len(self.full_history)} 条")
        else:
            self.status_label.setText(
                f"找到 {len(self.filtered_items)}/{len(self.full_history)} 条匹配记录"
            )

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def select_and_copy(self, item):
        text = item.data(Qt.ItemDataRole.UserRole)
        self.paste_immediately(text)

    def paste_immediately(self, text):
        def do_paste():
            try:
                pyperclip.copy(text)
                if self.previous_window:
                    success = activate_window(self.previous_window)
                    if success:
                        time.sleep(0.1)
                    else:
                        keyboard.press_and_release("alt+tab")
                        time.sleep(0.05)
                else:
                    keyboard.press_and_release("alt+tab")
                    time.sleep(0.05)

                keyboard.press_and_release("ctrl+v")
            except Exception as e:
                print(f"[ERROR] 粘贴失败: {e}")

        threading.Thread(target=do_paste, daemon=True).start()

    def clear_history_confirm(self):
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有历史记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.history_manager.clear()
            self.history_manager.save()
            self.refresh_listbox()

    def poll_queue(self):
        try:
            cmd = self.cmd_queue.get_nowait()
        except Exception:
            cmd = None

        if cmd == "show":
            self.open_history_window()

        if self.displayed_version != self.history_manager.version:
            self.refresh_listbox()

    # ---------------- 文本格式化 ----------------

    def format_item_text(self, text):
        """格式化：一行最多 20 字符，最多三行"""
        if not text:
            return ""
        text = text.strip()
        if len(text) <= 20:
            return text

        lines, current_line = [], ""
        words = text.split()

        for word in words:
            if len(current_line) + len(word) + (1 if current_line else 0) <= 20:
                current_line += (" " if current_line else "") + word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
                if len(lines) >= 3:
                    if len(current_line) > 17:
                        current_line = current_line[:17] + "..."
                    else:
                        current_line += "..."
                    lines.append(current_line)
                    break

        if current_line and len(lines) < 3:
            lines.append(current_line)
        elif current_line and len(lines) >= 3:
            last_line = lines[-1]
            lines[-1] = (last_line[:17] + "...") if len(last_line) > 17 else last_line + "..."

        return "\n".join(lines)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # ⚠️ 需要你传入 history_manager 和 config
    # 示例：
    # window = ClipboardGUI(history_manager, config)
    # window.show()
    sys.exit(app.exec())
