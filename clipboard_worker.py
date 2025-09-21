import time
import pyperclip
import threading

class ClipboardWorker(threading.Thread):
    def __init__(self, history_manager, poll_interval, daemon=True):
        super().__init__(daemon=daemon)
        self.history_manager = history_manager
        self.poll_interval = poll_interval
        self.running = True
        self.last_text = None

    def run(self):
        """后台轮询剪贴板"""
        while self.running:
            try:
                text = pyperclip.paste()
            except Exception:
                text = None

            if isinstance(text, str) and text != self.last_text:
                if text.strip() != "":
                    if self.history_manager.add_item(text):
                        self.history_manager.save()
                self.last_text = text
            time.sleep(self.poll_interval)

    def stop(self):
        """停止工作线程"""
        self.running = False