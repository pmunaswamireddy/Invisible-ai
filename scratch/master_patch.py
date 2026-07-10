import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# 1. apply_initial_focus_styles
old_initial = r"""            if getattr\(self, 'focus_mode', 'Background'\) == 'Background':\r?\n                ctypes\.windll\.user32\.SetWindowLongW\(hwnd, GWL_EXSTYLE, ex_style \| WS_EX_NOACTIVATE \| WS_EX_TRANSPARENT\)"""
new_initial = """            if getattr(self, 'focus_mode', 'Background') == 'Background':
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex_style | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT)"""
text, c1 = re.subn(old_initial, new_initial, text)
print(f"Patched apply_initial_focus_styles: {c1}")

# 2. changeEvent
old_change = r"""                  if self\.focus_mode == 'Background':\r?\n                      hwnd = int\(self\.winId\(\)\)\r?\n                      GWL_EXSTYLE = -20\r?\n                      WS_EX_NOACTIVATE = 0x08000000\r?\n                      WS_EX_TRANSPARENT = 0x00000020\r?\n                      ex_style = ctypes\.windll\.user32\.GetWindowLongW\(hwnd, GWL_EXSTYLE\)\r?\n                      ctypes\.windll\.user32\.SetWindowLongW\(hwnd, GWL_EXSTYLE, ex_style \| WS_EX_NOACTIVATE \| WS_EX_TRANSPARENT\)"""
new_change = """                  if self.focus_mode == 'Background':
                      hwnd = int(self.winId())
                      GWL_EXSTYLE = -20
                      WS_EX_NOACTIVATE = 0x08000000
                      WS_EX_TRANSPARENT = 0x00000020
                      ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                      ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex_style | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT)"""
text, c2 = re.subn(old_change, new_change, text)
print(f"Patched changeEvent: {c2}")

# 3. toggle_focus_mode
old_toggle = r"""            # Add WS_EX_NOACTIVATE and WS_EX_TRANSPARENT \S+ suppress focus and intercept clicks at hook level\r?\n\s*ex_style = ctypes\.windll\.user32\.GetWindowLongW\(hwnd, GWL_EXSTYLE\)\r?\n\s*ctypes\.windll\.user32\.SetWindowLongW\(hwnd, GWL_EXSTYLE, ex_style \| WS_EX_NOACTIVATE \| WS_EX_TRANSPARENT\)"""
new_toggle = """            # Use WM_NCHITTEST for selective click-through instead of WS_EX_TRANSPARENT
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex_style | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT)"""
text, c3 = re.subn(old_toggle, new_toggle, text)
print(f"Patched toggle_focus_mode: {c3}")

# 4. nativeEvent
old_native = r"""    def nativeEvent\(self, eventType, message\):\r?\n        if eventType == "windows_generic_MSG":\r?\n            msg = ctypes\.wintypes\.MSG\.from_address\(int\(message\)\)\r?\n            \r?\n            if msg\.message == 0x0312: # WM_HOTKEY"""
new_native = """    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            
            if msg.message == 0x0084: # WM_NCHITTEST
                if getattr(self, 'focus_mode', '') == 'Background' or getattr(self, 'is_hidden', False):
                    x = msg.lParam & 0xFFFF
                    if x > 32767: x -= 65536
                    y = (msg.lParam >> 16) & 0xFFFF
                    if y > 32767: y -= 65536
                    from PyQt5.QtCore import QPoint
                    is_solid = False
                    
                    if hasattr(self, 'tab_widget') and self.tab_widget.isVisible():
                        tab_local = self.tab_widget.mapFromGlobal(QPoint(x, y))
                        if self.tab_widget.rect().contains(tab_local):
                            if self.tab_widget.currentIndex() > 0:
                                is_solid = True
                                
                    if not is_solid and hasattr(self, 'slider') and self.slider.isVisible():
                        slider_local = self.slider.mapFromGlobal(QPoint(x, y))
                        if self.slider.rect().adjusted(-20, -20, 20, 20).contains(slider_local):
                            is_solid = True
                            
                    if not is_solid and hasattr(self, 'chat_history') and self.chat_history.isVisible():
                        win_local = self.mapFromGlobal(QPoint(x, y))
                        if win_local.x() >= self.width() - 50 and win_local.y() > 50:
                            is_solid = True
                        else:
                            chat_local = self.chat_history.mapFromGlobal(QPoint(x, y))
                            if self.chat_history.rect().adjusted(-10, -10, 10, 10).contains(chat_local):
                                viewport_local = self.chat_history.viewport().mapFromGlobal(QPoint(x, y))
                                url = self.chat_history.anchorAt(viewport_local)
                                if url:
                                    is_solid = True
                                    
                    if not is_solid:
                        return True, -1 # HTTRANSPARENT
                        
            elif msg.message == 0x0021: # WM_MOUSEACTIVATE
                if getattr(self, 'focus_mode', '') == 'Background' or getattr(self, 'is_hidden', False):
                    import win32api
                    x, y = win32api.GetCursorPos()
                    from PyQt5.QtCore import QPoint
                    if hasattr(self, 'tab_widget') and self.tab_widget.isVisible():
                        tab_local = self.tab_widget.mapFromGlobal(QPoint(x, y))
                        if self.tab_widget.rect().contains(tab_local):
                            if self.tab_widget.currentIndex() > 0:
                                return True, 1 # MA_ACTIVATE
                    return True, 3 # MA_NOACTIVATE
            
            if msg.message == 0x0312: # WM_HOTKEY"""
text, c4 = re.subn(old_native, new_native, text)
print(f"Patched nativeEvent: {c4}")

# 5. Command mode buffer
old_cmd = r"""            elif Qt\.Key_1 <= vk <= Qt\.Key_9:\r?\n                self\.inject_indexed_hotkey_signal\.emit\(vk - Qt\.Key_0\)\r?\n                event\.accept\(\)\r?\n                return"""
new_cmd = """            elif Qt.Key_0 <= vk <= Qt.Key_9:
                if not hasattr(self, 'cmd_number_buffer'):
                    self.cmd_number_buffer = ""
                self.cmd_number_buffer += chr(vk)
                
                if hasattr(self, 'cmd_number_timer'):
                    self.cmd_number_timer.stop()
                else:
                    from PyQt5.QtCore import QTimer
                    self.cmd_number_timer = QTimer()
                    self.cmd_number_timer.setSingleShot(True)
                    def flush_buffer():
                        if getattr(self, 'cmd_number_buffer', ""):
                            idx = int(self.cmd_number_buffer)
                            self.inject_indexed_hotkey_signal.emit(idx)
                            self.cmd_number_buffer = ""
                    self.cmd_number_timer.timeout.connect(flush_buffer)
                
                self.cmd_number_timer.start(400)
                event.accept()
                return"""
text, c5 = re.subn(old_cmd, new_cmd, text)
print(f"Patched Command Mode: {c5}")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Master patch applied.")
