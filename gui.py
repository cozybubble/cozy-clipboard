import tkinter as tk
import tkinter.messagebox as msgbox
import threading
import keyboard
import time
import pyperclip

from window_manager import activate_window

class ClipboardGUI:
    def __init__(self, root, history_manager, config):
        self.root = root
        self.history_manager = history_manager
        self.config = config
        self.cmd_queue = config.get('cmd_queue')
        self.previous_window = None
        self.displayed_version = 0
        self.top_window = None
        self.window_lock = threading.Lock()

        # 初始化主窗口
        self.root.withdraw()  # 隐藏主窗口
        self.setup_hotkey()

    def setup_hotkey(self):
        """注册全局热键"""
        keyboard.add_hotkey(
            self.config['hotkey'],
            self.on_hotkey
        )

    def on_hotkey(self):
        """热键回调"""
        self.previous_window = self.config['get_active_window']()
        try:
            self.cmd_queue.put_nowait("show")
        except Exception:
            pass

    def open_history_window(self):
        """打开历史记录窗口"""
        with self.window_lock:
            # 窗口已存在则刷新并置顶
            if self.top_window and self.top_window.winfo_exists():
                try:
                    self.top_window.deiconify()
                    self.top_window.lift()
                    self.top_window.focus_force()
                    if self.displayed_version != self.history_manager.version:
                        self.refresh_listbox()
                except Exception:
                    pass
                return

            # 创建新窗口
            top = tk.Toplevel(self.root)
            top.title(self.config['window_title'])
            top.geometry(self.config['window_size'])
            top.attributes("-topmost", True)

            # 窗口居中
            top.update_idletasks()
            width = top.winfo_width()
            height = top.winfo_height()
            x = (top.winfo_screenwidth() // 2) - (width // 2)
            y = (top.winfo_screenheight() // 2) - (height // 2)
            top.geometry(f"{width}x{height}+{x}+{y}")

            # 创建列表框和滚动条
            frame = tk.Frame(top)
            frame.pack(fill="both", expand=True)
            scrollbar = tk.Scrollbar(frame)
            scrollbar.pack(side="right", fill="y")
            listbox = tk.Listbox(
                frame, 
                font=self.config['font_setting'], 
                yscrollcommand=scrollbar.set
            )
            listbox.pack(side="left", fill="both", expand=True)
            scrollbar.config(command=listbox.yview)
            top.listbox = listbox

            # 填充初始数据
            for item in self.history_manager.get_copy():
                listbox.insert(tk.END, item)
            self.displayed_version = self.history_manager.version

            # 状态栏
            status_frame = tk.Frame(top)
            status_frame.pack(fill="x", padx=5, pady=2)
            self.status_label = tk.Label(
                status_frame, 
                text=f"历史记录: {self.history_manager.get_length()} 条",
                font=self.config['status_font'], 
                fg="gray"
            )
            self.status_label.pack(side="left")

            # 清空按钮
            clear_button = tk.Button(
                status_frame, 
                text="清空历史",
                command=lambda: self.clear_history_confirm(top),
                font=self.config['status_font']
            )
            clear_button.pack(side="right")

            # 绑定事件
            listbox.bind("<Double-Button-1>", self.select_and_copy)
            listbox.bind("<Return>", self.select_and_copy)
            listbox.bind("<KP_Enter>", self.select_and_copy)
            top.bind("<Escape>", lambda e: self.close_top_window())
            listbox.bind("<Escape>", lambda e: self.close_top_window())
            top.protocol("WM_DELETE_WINDOW", self.close_top_window)

            # 初始选中
            if listbox.size() > 0:
                listbox.selection_set(0)
                listbox.activate(0)
                listbox.focus_set()

            self.top_window = top

    def refresh_listbox(self):
        """刷新列表框内容"""
        with self.window_lock:
            if not self.top_window or not self.top_window.winfo_exists():
                return
            listbox = self.top_window.listbox

            # 保存当前选择
            sel_text = None
            try:
                sel_idx = listbox.curselection()[0] if listbox.curselection() else None
                if sel_idx is not None:
                    sel_text = listbox.get(sel_idx)
            except Exception:
                pass

            # 重新填充
            listbox.delete(0, tk.END)
            for item in self.history_manager.get_copy():
                listbox.insert(tk.END, item)

            # 更新状态栏
            self.status_label.config(
                text=f"历史记录: {self.history_manager.get_length()} 条"
            )

            # 恢复选择
            if listbox.size() > 0:
                if sel_text:
                    try:
                        idx = listbox.get(0, tk.END).index(sel_text)
                        listbox.selection_set(idx)
                        listbox.see(idx)
                    except ValueError:
                        listbox.selection_set(0)
                else:
                    listbox.selection_set(0)

            self.displayed_version = self.history_manager.version

    def select_and_copy(self, event):
        """处理选择和粘贴"""
        if not hasattr(self.top_window, 'listbox'):
            return
        listbox = self.top_window.listbox
        
        try:
            idx = listbox.curselection()[0] if listbox.curselection() else 0
            text = listbox.get(idx)
            self.paste_immediately(text)
        except Exception as e:
            print(f"[ERROR] 选择处理失败: {e}")

    def paste_immediately(self, text):
        """立即粘贴到活动窗口"""
        def do_paste():
            try:
                pyperclip.copy(text)
                
                # 激活之前的窗口
                if self.previous_window:
                    success = activate_window(self.previous_window)
                    if success:
                      time.sleep(0.1)  # 短暂等待窗口激活
                    else:
                        keyboard.press_and_release('alt+tab')
                        time.sleep(0.05)
                else:
                    keyboard.press_and_release('alt+tab')
                    time.sleep(0.05)
                
                # 执行粘贴
                keyboard.press_and_release('ctrl+v')
            except Exception as e:
                print(f"[ERROR] 粘贴失败: {e}")

        threading.Thread(target=do_paste, daemon=True).start()

    def clear_history_confirm(self, parent):
        """确认清空历史"""
        if msgbox.askyesno("确认", "确定要清空所有历史记录吗？", parent=parent):
            self.history_manager.clear()
            self.history_manager.save()
            self.refresh_listbox()

    def close_top_window(self):
        """关闭历史窗口"""
        with self.window_lock:
            if self.top_window and self.top_window.winfo_exists():
                try:
                    self.top_window.destroy()
                except Exception:
                    pass
            self.top_window = None

    def poll_queue(self):
        """轮询队列处理命令"""
        try:
            cmd = self.cmd_queue.get_nowait()
        except Exception:
            cmd = None

        if cmd == "show":
            self.open_history_window()

        # 检查历史更新
        if self.displayed_version != self.history_manager.version:
            self.refresh_listbox()

        self.root.after(self.config['queue_poll_ms'], self.poll_queue)