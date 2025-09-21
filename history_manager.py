import json
import os
import threading

class HistoryManager:
    def __init__(self, max_items, history_file):
        self.max_items = max_items
        self.history_file = history_file
        self.history = []
        self.history_lock = threading.Lock()
        self.version = 0  # 用于检测更新
        self.load()

    def load(self):
        """加载历史记录从文件"""
        try:
            if not os.path.exists(self.history_file):
                self.save()
                return
            
            if os.path.getsize(self.history_file) == 0:
                with open(self.history_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
                self.clear()
                return

            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    with self.history_lock:
                        self.history = data[:self.max_items]
                    self.version += 1
                else:
                    raise ValueError("历史文件格式错误")
        except Exception as e:
            print(f"[ERROR] 加载历史失败: {e}")
            self.clear()
            self.save()

    def save(self):
        """保存历史记录到文件"""
        try:
            with self.history_lock:
                data = self.history.copy()
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] 保存历史记录失败: {e}")

    def add_item(self, text):
        """添加新项到历史记录"""
        if not text or text.strip() == "":
            return False

        with self.history_lock:
            # 避免重复项
            if self.history and self.history[0] == text:
                return False
                
            self.history.insert(0, text)
            if len(self.history) > self.max_items:
                del self.history[self.max_items:]
            self.version += 1
        return True

    def clear(self):
        """清空历史记录"""
        with self.history_lock:
            self.history.clear()
            self.version += 1

    def get_copy(self):
        """获取历史记录副本"""
        with self.history_lock:
            return self.history.copy()

    def get_length(self):
        """获取历史记录长度"""
        with self.history_lock:
            return len(self.history)