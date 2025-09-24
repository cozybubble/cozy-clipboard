import time
import threading
import base64
import pyperclip
import win32clipboard
from PIL import ImageGrab
import io

class ClipboardWorker(threading.Thread):
    def __init__(self, history_manager, poll_interval, daemon=True):
        super().__init__(daemon=daemon)
        self.history_manager = history_manager
        self.poll_interval = poll_interval
        self.running = True
        self.last_data = None

    def get_clipboard_image(self):
        """尝试读取剪贴板里的图片，返回 base64 编码 PNG"""
        try:
            img = ImageGrab.grabclipboard()
            if img:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            print(f"[ERROR] 读取图片失败: {e}")
        return None

    def run(self):
        """后台轮询剪贴板"""
        while self.running:
            try:
                entry = None

                # 先检测是否是图片
                image_data = self.get_clipboard_image()
                if image_data:
                    entry = {"type": "image", "data": image_data}

                else:
                    # 否则检查文本
                    text = pyperclip.paste()
                    if isinstance(text, str) and text.strip():
                        entry = {"type": "text", "data": text}

                if entry and entry != self.last_data:
                    if self.history_manager.add_item(entry):
                        self.history_manager.save()
                    self.last_data = entry

            except Exception as e:
                print(f"[ERROR] 剪贴板读取失败: {e}")

            time.sleep(self.poll_interval)

    def stop(self):
        """停止工作线程"""
        self.running = False