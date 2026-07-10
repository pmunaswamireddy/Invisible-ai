import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# 1. Patch toggle_focus_mode to NOT use WS_EX_TRANSPARENT in Background mode
# Find the specific block in toggle_focus_mode:
#            # Add WS_EX_NOACTIVATE and WS_EX_TRANSPARENT ?" suppress focus and intercept clicks at hook level
#            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
#            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)

old_toggle = r"""            # Add WS_EX_NOACTIVATE and WS_EX_TRANSPARENT \S+ suppress focus and intercept clicks at hook level\r?\n\s*ex_style = ctypes\.windll\.user32\.GetWindowLongW\(hwnd, GWL_EXSTYLE\)\r?\n\s*ctypes\.windll\.user32\.SetWindowLongW\(hwnd, GWL_EXSTYLE, ex_style \| WS_EX_NOACTIVATE \| WS_EX_TRANSPARENT\)"""

new_toggle = """            # Use WM_NCHITTEST for selective click-through instead of WS_EX_TRANSPARENT
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex_style | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT)"""

text, count = re.subn(old_toggle, new_toggle, text)
print(f"Patched toggle_focus_mode {count} times.")

# 2. Patch nativeEvent to add WM_NCHITTEST and WM_MOUSEACTIVATE
native_old = r'    def nativeEvent\(self, eventType, message\):\s*if eventType == "windows_generic_MSG":\s*msg = ctypes\.wintypes\.MSG\.from_address\(int\(message\)\)\s*if msg\.message == 0x0312: # WM_HOTKEY'

native_new = """    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            
            if msg.message == 0x0084: # WM_NCHITTEST
                if getattr(self, 'focus_mode', '') == 'Background' or getattr(self, 'is_hidden', False):
                    x = msg.lParam & 0xFFFF
                    if x > 32767: x -= 65536
                    y = (msg.lParam >> 16) & 0xFFFF
                    if y > 32767: y -= 65536
                    from PyQt5.QtCore import QPoint
                    local_pos = self.mapFromGlobal(QPoint(x, y))
                    
                    is_solid = False
                    if hasattr(self, 'tab_widget') and self.tab_widget.isVisible() and self.tab_widget.geometry().contains(local_pos):
                        if self.tab_widget.currentIndex() > 0:
                            is_solid = True
                            
                    if not is_solid:
                        return True, -1 # HTTRANSPARENT
                        
            elif msg.message == 0x0021: # WM_MOUSEACTIVATE
                if getattr(self, 'focus_mode', '') == 'Background' or getattr(self, 'is_hidden', False):
                    import win32api
                    x, y = win32api.GetCursorPos()
                    from PyQt5.QtCore import QPoint
                    local_pos = self.mapFromGlobal(QPoint(x, y))
                    if hasattr(self, 'tab_widget') and self.tab_widget.isVisible() and self.tab_widget.geometry().contains(local_pos):
                        if self.tab_widget.currentIndex() > 0:
                            return True, 1 # MA_ACTIVATE
                    return True, 3 # MA_NOACTIVATE
            
            if msg.message == 0x0312: # WM_HOTKEY"""

text, count2 = re.subn(native_old, native_new, text)
print(f"Patched nativeEvent {count2} times.")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Patch applied successfully.")
