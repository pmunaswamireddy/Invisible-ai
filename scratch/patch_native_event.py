import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# 1. Patch toggle_focus_mode
text = text.replace('ex_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT', 'ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT')

# 2. Patch nativeEvent
native_old = """    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312: # WM_HOTKEY"""
            
native_new = """    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            
            # WM_NCHITTEST for Smart Ghost Mode
            if msg.message == 0x0084: 
                if getattr(self, 'focus_mode', '') == 'Background' or getattr(self, 'is_hidden', False):
                    x = msg.lParam & 0xFFFF
                    if x > 32767: x -= 65536
                    y = (msg.lParam >> 16) & 0xFFFF
                    if y > 32767: y -= 65536
                    
                    from PyQt5.QtCore import QPoint, QRect
                    local_pos = self.mapFromGlobal(QPoint(x, y))
                    is_solid = False
                    
                    if hasattr(self, 'controls_widget') and self.controls_widget.isVisible() and self.controls_widget.geometry().contains(local_pos):
                        is_solid = True
                    elif hasattr(self, 'tab_widget') and self.tab_widget.isVisible() and self.tab_widget.geometry().contains(local_pos):
                        is_solid = True
                    elif hasattr(self, 'chat_history') and self.chat_history.isVisible():
                        chat_geo = QRect(self.chat_history.mapTo(self, QPoint(0,0)), self.chat_history.size())
                        if chat_geo.contains(local_pos):
                            is_solid = True
                    
                    if not is_solid:
                        return True, -1
                        
            # WM_MOUSEACTIVATE to selectively steal focus
            elif msg.message == 0x0021:
                if getattr(self, 'focus_mode', '') == 'Background' or getattr(self, 'is_hidden', False):
                    import win32api
                    x, y = win32api.GetCursorPos()
                    from PyQt5.QtCore import QPoint
                    local_pos = self.mapFromGlobal(QPoint(x, y))
                    if hasattr(self, 'tab_widget') and self.tab_widget.isVisible() and self.tab_widget.geometry().contains(local_pos):
                        return True, 1 # MA_ACTIVATE
                    else:
                        return True, 3 # MA_NOACTIVATE
                        
            elif msg.message == 0x0312: # WM_HOTKEY"""

if native_old in text:
    text = text.replace(native_old, native_new)
else:
    print("WARNING: nativeEvent pattern not found!")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Patch applied successfully.")
