try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("[ERROR] 需要安装 pywin32: pip install pywin32")


def get_active_window():
    """获取当前活动窗口句柄"""
    if not HAS_WIN32:
        return None
    try:
        return win32gui.GetForegroundWindow()
    except Exception as e:
        print(f"[ERROR] 获取活动窗口失败: {e}")
        return None


def activate_window(window_handle):
    """激活指定窗口"""
    if not HAS_WIN32 or not window_handle:
        return False
    
    try:
        # 检查窗口是否仍然存在
        if not win32gui.IsWindow(window_handle):
            return False
            
        # 如果窗口最小化，先恢复
        if win32gui.IsIconic(window_handle):
            win32gui.ShowWindow(window_handle, win32con.SW_RESTORE)
        
        # 激活窗口
        win32gui.SetForegroundWindow(window_handle)
        return True
    except Exception as e:
        print(f"[ERROR] 激活窗口失败: {e}")
        return False