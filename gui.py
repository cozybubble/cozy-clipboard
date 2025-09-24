import sys
import time
import threading
import pyperclip
import keyboard
import base64
import pythoncom
from pynput.mouse import Listener  # 新增导入

try:
    import win32clipboard
    import win32con
    from PIL import Image
    import io
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    print("win32clipboard 不可用，将使用Qt剪贴板")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QTextEdit, QSplitter, QStackedWidget
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal

from window_manager import activate_window


class ClipboardGUI(QMainWindow):
    # 添加自定义信号用于线程间通信
    paste_signal = pyqtSignal(object)
    
    def __init__(self, history_manager, config):
        super().__init__()
        # 主线程中初始化COM环境
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        except:
            pythoncom.CoInitialize()
            
        self.history_manager = history_manager
        self.config = config
        self.cmd_queue = config.get("cmd_queue")

        self.full_history = []
        self.filtered_items = []
        self.previous_window = None
        self.current_window = None
        self.displayed_version = 0
        self.mouse_listener = None  # 新增：鼠标监听器实例

        # === 窗口设置 ===
        self.setWindowTitle(config.get("window_title", "剪贴板历史"))
        self.resize(*[int(x) for x in config.get("window_size", "500x1000").split("x")])
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        # === 主布局 (左右分栏) ===
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 创建水平分隔条
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # ---------- 左边区域 ----------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)

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
        self.list_widget.currentItemChanged.connect(self.update_preview)
        self.list_widget.setIconSize(QSize(256, 256))
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        left_layout.addWidget(self.list_widget)

        # 底部栏
        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("历史记录: 0 条")
        clear_history_btn = QPushButton("清空历史")
        clear_history_btn.setObjectName("clearButton")
        clear_history_btn.clicked.connect(self.clear_history_confirm)
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(clear_history_btn)
        left_layout.addLayout(bottom_layout)

        # ---------- 右边预览 ----------
        self.preview_stack = QStackedWidget()
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("选中一个条目后在此预览完整内容...")

        self.preview_image = QLabel()
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_stack.addWidget(self.preview_text)
        self.preview_stack.addWidget(self.preview_image)

        # ---------- 将左右部件添加到分隔条 ----------
        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(self.preview_stack)

        self.splitter.setSizes([300, 400])

        # === 热键注册 ===
        keyboard.add_hotkey(self.config["hotkey"], self.on_hotkey)

        # === 定时器轮询队列 ===
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.poll_queue)
        self.queue_timer.start(self.config.get("queue_poll_ms", 200))

        # 初始加载
        self.refresh_listbox()
        
        # 连接粘贴信号到槽函数
        self.paste_signal.connect(self.handle_paste_in_main_thread)

    # ---------------- 功能逻辑 ----------------

   
    def closeEvent(self, event):
        # 关闭窗口时停止鼠标监听
        if self.mouse_listener and self.mouse_listener.is_alive():
            self.mouse_listener.stop()
        # 清理COM环境
        try:
            pythoncom.CoUninitialize()
        except:
            pass
        event.ignore()
        self.hide()

    # 以下方法保持不变...
    def update_preview(self, current, previous):
        if not current:
            self.preview_text.clear()
            self.preview_stack.setCurrentWidget(self.preview_text)
            return

        entry = current.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, dict) and entry.get("type") == "image":
            pixmap = QPixmap()
            pixmap.loadFromData(base64.b64decode(entry["data"]))
            self.preview_image.setPixmap(pixmap.scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation))
            self.preview_stack.setCurrentWidget(self.preview_image)
        else:
            text = entry["data"] if isinstance(entry, dict) else str(entry)
            self.preview_text.setPlainText(text)
            self.preview_stack.setCurrentWidget(self.preview_text)

    def on_hotkey(self):
        # 热键按下时也更新一次窗口信息
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

    def refresh_listbox(self):
        self.full_history = self.history_manager.get_copy()
        self.filter_list(self.search_entry.text())
        self.status_label.setText(f"历史记录: {len(self.full_history)} 条")
        self.displayed_version = self.history_manager.version

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            self.list_widget.setFocus()

    def filter_list(self, text):
        text = text.strip().lower()
        self.list_widget.clear()
        self.filtered_items = []

        for entry in self.full_history:
            match_text = ""
            if isinstance(entry, dict):
                if entry.get("type") == "text":
                    match_text = entry["data"]
                elif entry.get("type") == "image":
                    match_text = "[图片]"
            else:
                match_text = str(entry)

            if text in match_text.lower():
                lw_item = QListWidgetItem()
                if isinstance(entry, dict) and entry.get("type") == "image":
                    pixmap = QPixmap()
                    pixmap.loadFromData(base64.b64decode(entry["data"]))
                    
                    # 设置更大的图片尺寸，并确保不超过列表宽度
                    available_width = self.list_widget.width() - 40  # 减去边距和滚动条空间
                    target_size = min(available_width, 150)  # 最大150px，或适应列表宽度
                    
                    scaled_pixmap = pixmap.scaled(
                        128,100,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    
                    lw_item.setIcon(QIcon(scaled_pixmap))
                    lw_item.setText("[图片]")
                    
                    # 设置列表项尺寸以适应图片
                    item_height = max(scaled_pixmap.height() + 32, 80)  # 至少80px高
                    lw_item.setSizeHint(QSize(available_width, item_height))
                    
                else:
                    lw_item.setText(self.format_item_text(match_text))
                    # 文本项使用默认高度
                    lw_item.setSizeHint(QSize(-1, 60))
                    
                lw_item.setData(Qt.ItemDataRole.UserRole, entry)
                self.list_widget.addItem(lw_item)
                self.filtered_items.append(entry)

        if not text:
            self.status_label.setText(f"历史记录: {len(self.full_history)} 条")
        else:
            self.status_label.setText(
                f"找到 {len(self.filtered_items)}/{len(self.full_history)} 条匹配记录"
            )

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

            
    def select_and_copy(self, item):
        entry = item.data(Qt.ItemDataRole.UserRole)
        self.paste_immediately(entry)

    def paste_immediately(self, entry):
        """发射信号，在主线程中处理剪贴板操作"""
        self.paste_signal.emit(entry)

    def handle_paste_in_main_thread(self, entry):
        """在主线程中处理剪贴板设置和粘贴"""
        def do_paste():
            try:
                print(f"处理粘贴: {entry}")
                
                if isinstance(entry, dict) and entry.get("type") == "image":
                    # 尝试使用Windows API设置图片到剪贴板
                    if WIN32_AVAILABLE:
                        success = self.set_image_to_clipboard_win32(entry["data"])
                        if not success:
                            # 如果Windows API失败，尝试Qt方式
                            success = self.set_image_to_clipboard_qt(entry["data"])
                    else:
                        # 使用Qt方式
                        success = self.set_image_to_clipboard_qt(entry["data"])
                    
                    if not success:
                        print("设置图片到剪贴板失败")
                        return
                else:
                    # 处理文本粘贴
                    text = entry["data"] if isinstance(entry, dict) else str(entry)
                    clipboard = QApplication.clipboard()
                    clipboard.clear()
                    QApplication.processEvents()
                    time.sleep(0.05)
                    
                    clipboard.setText(text)
                    QApplication.processEvents()
                    print(f"文本已设置到剪贴板: {text[:50]}...")

                # 短暂延迟确保剪贴板设置完成
                time.sleep(0.15)

                # 窗口激活处理
                if self.previous_window:
                    success = activate_window(self.previous_window)
                    if success:
                        time.sleep(0.15)
                    else:
                        keyboard.press_and_release("alt+tab")
                        time.sleep(0.1)
                else:
                    keyboard.press_and_release("alt+tab")
                    time.sleep(0.1)

                # 执行粘贴操作
                keyboard.press_and_release("ctrl+v")
                print("粘贴操作完成")

            except Exception as e:
                print(f"[ERROR] 粘贴失败: {str(e)}")
                import traceback
                print(f"[ERROR] 异常堆栈: {traceback.format_exc()}")

        # 延迟执行粘贴操作，确保UI操作完成
        QTimer.singleShot(100, do_paste)

    def set_image_to_clipboard_win32(self, base64_data):
        """使用Windows API设置图片到剪贴板"""
        try:
            image_data = base64.b64decode(base64_data)
            image = Image.open(io.BytesIO(image_data))
            
            # 转换为BMP格式
            output = io.BytesIO()
            image.save(output, format='BMP')
            data = output.getvalue()[14:]  # 移除BMP文件头
            
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, data)
            win32clipboard.CloseClipboard()
            
            print("使用Windows API设置图片到剪贴板成功")
            return True
            
        except Exception as e:
            print(f"Windows API设置图片失败: {e}")
            try:
                win32clipboard.CloseClipboard()
            except:
                pass
            return False

    def set_image_to_clipboard_qt(self, base64_data):
        """使用Qt API设置图片到剪贴板"""
        try:
            clipboard = QApplication.clipboard()
            pixmap = QPixmap()
            image_data = base64.b64decode(base64_data)
            load_success = pixmap.loadFromData(image_data)
            
            if load_success:
                clipboard.clear()
                QApplication.processEvents()
                time.sleep(0.05)
                
                clipboard.setPixmap(pixmap)
                QApplication.processEvents()
                
                # 验证剪贴板内容
                test_pixmap = clipboard.pixmap()
                if not test_pixmap.isNull():
                    print(f"使用Qt设置图片到剪贴板成功，尺寸: {test_pixmap.size()}")
                    return True
                else:
                    print("Qt设置图片后剪贴板为空")
                    return False
            else:
                print("Qt加载图片失败")
                return False
                
        except Exception as e:
            print(f"Qt设置图片失败: {e}")
            return False

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

    def format_item_text(self, text):
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
    sys.exit(app.exec())