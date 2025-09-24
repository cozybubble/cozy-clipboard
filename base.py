import win32clipboard
import win32con

# Windows剪贴板标准格式映射
STANDARD_FORMATS = {
    1: "CF_TEXT",
    2: "CF_BITMAP", 
    3: "CF_METAFILEPICT",
    4: "CF_SYLK",
    5: "CF_DIF",
    6: "CF_TIFF",
    7: "CF_OEMTEXT",
    8: "CF_DIB",
    9: "CF_PALETTE",
    10: "CF_PENDATA",
    11: "CF_RIFF",
    12: "CF_WAVE",
    13: "CF_UNICODETEXT",
    14: "CF_ENHMETAFILE",
    15: "CF_HDROP",
    16: "CF_LOCALE",
    17: "CF_DIBV5"
}

def get_clipboard_formats():
    """获取当前剪贴板中所有数据格式"""
    try:
        win32clipboard.OpenClipboard()
        formats = []
        format_id = 0
        
        while True:
            format_id = win32clipboard.EnumClipboardFormats(format_id)
            if format_id == 0:
                break
            formats.append(format_id)
        
        return formats
    finally:
        win32clipboard.CloseClipboard()

def get_format_name(format_id):
    """获取格式名称"""
    if format_id in STANDARD_FORMATS:
        return STANDARD_FORMATS[format_id]
    else:
        try:
            return win32clipboard.GetClipboardFormatName(format_id)
        except:
            return f"自定义格式_{format_id}"

def analyze_clipboard():
    """分析剪贴板内容"""
    formats = get_clipboard_formats()
    
    print("=== 当前剪贴板中的数据格式 ===")
    if not formats:
        print("剪贴板为空")
        return
    
    for fmt in formats:
        format_name = get_format_name(fmt)
        print(f"格式ID: {fmt:2d} - {format_name}")
        
        # 对于图片格式，显示一些额外信息
        if fmt == 2:  # CF_BITMAP
            print("    → 这是位图句柄格式")
        elif fmt == 8:  # CF_DIB  
            print("    → 这是设备无关位图格式")
        elif fmt == 17:  # CF_DIBV5
            print("    → 这是增强设备无关位图格式")
        elif fmt in [1, 13]:  # 文本格式
            try:
                win32clipboard.OpenClipboard()
                if fmt == 1:
                    text = win32clipboard.GetClipboardData(win32con.CF_TEXT)
                else:
                    text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
                
                preview = text[:100] + "..." if len(text) > 100 else text
                print(f"    → 文本预览: {repr(preview)}")
            except:
                print("    → 无法读取文本内容")
    
    print("\n=== 分析结果 ===")
    
    # 检查是否包含图片
    image_formats = [f for f in formats if f in [2, 8, 17]]
    if image_formats:
        print("✅ 剪贴板包含图片数据")
        for fmt in image_formats:
            print(f"   - {get_format_name(fmt)}")
    
    # 检查是否包含文本
    text_formats = [f for f in formats if f in [1, 13]]
    if text_formats:
        print("✅ 剪贴板包含文本数据") 
        for fmt in text_formats:
            print(f"   - {get_format_name(fmt)}")
    
    # 检查是否可能包含base64
    if text_formats:
        try:
            win32clipboard.OpenClipboard()
            text = ""
            if 13 in formats:  # 优先使用Unicode文本
                text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            elif 1 in formats:
                text = win32clipboard.GetClipboardData(win32con.CF_TEXT).decode('utf-8', errors='ignore')
            win32clipboard.CloseClipboard()
            
            # 简单检查是否像base64
            if len(text) > 100 and text.replace('+', '').replace('/', '').replace('=', '').isalnum():
                print("⚠️  文本内容可能包含base64编码数据")
            else:
                print("ℹ️  文本内容不像base64编码")
                
        except Exception as e:
            print(f"⚠️  无法分析文本内容: {e}")

def test_image_copy():
    """测试：先复制一张图片，再分析剪贴板"""
    print("请先复制一张图片（从文件管理器、网页或其他程序），然后按Enter继续...")
    input()
    analyze_clipboard()

if __name__ == "__main__":
    print("剪贴板分析工具")
    print("=" * 50)
    
    # 直接分析当前剪贴板
    analyze_clipboard()
    
    print("\n" + "=" * 50)
    print("想要测试图片复制吗? (y/n): ", end="")
    if input().lower().startswith('y'):
        test_image_copy()