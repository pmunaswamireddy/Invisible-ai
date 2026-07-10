import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# 1. Remove mouse hook logic (top-level functions and globals)
text = re.sub(r'# --- Global Mouse Scroll Hook for Ghost Mode ---.*?_mouse_hook_handle = None\r?\n', '', text, flags=re.DOTALL)
text = re.sub(r'class MSLLHOOKSTRUCT.*?def uninstall_mouse_hook\(\):.*?    if _mouse_hook_handle:.*?        ctypes\.windll\.user32\.UnhookWindowsHookEx\(_mouse_hook_handle\)\r?\n', '', text, flags=re.DOTALL)

# 2. Remove hooks from __init__ and force_exit
text = re.sub(r'\s*install_mouse_hook\(\)\r?\n', '\n', text)
text = re.sub(r'\s*uninstall_mouse_hook\(\)\r?\n', '\n', text)
text = re.sub(r'\s*self\.global_scroll_signal\.connect\(self\.handle_global_scroll\)\r?\n', '\n', text)

# 3. Remove ghost typing methods
text = re.sub(r'    def stealth_type_text.*?finally:.*?        user32.SetWindowLongW\(hwnd, GWL_EXSTYLE, orig_ex\)\r?\n', '', text, flags=re.DOTALL)
text = re.sub(r'    def stealth_click\(\):.*?    mouse_event\(2, 0, 0, 0, 0\)\r?\n', '', text, flags=re.DOTALL)

# 4. Remove ghost char signals
text = re.sub(r'    ghost_char_signal = pyqtSignal\(str\)\r?\n', '', text)
text = re.sub(r'    ghost_backspace_signal = pyqtSignal\(\)\r?\n', '', text)
text = re.sub(r'    ghost_enter_signal = pyqtSignal\(\)\r?\n', '', text)
text = re.sub(r'    ghost_typing_signal = pyqtSignal\(bool\)\r?\n', '', text)
text = re.sub(r'        self\.ghost_char_signal\.connect\(self\.on_ghost_char\)\r?\n', '', text)
text = re.sub(r'        self\.ghost_backspace_signal\.connect\(self\.on_ghost_backspace\)\r?\n', '', text)
text = re.sub(r'        self\.ghost_enter_signal\.connect\(self\.on_ghost_enter\)\r?\n', '', text)
text = re.sub(r'        self\.ghost_typing_signal\.connect\(self\.toggle_ghost_typing\)\r?\n', '', text)

# 5. Remove on_ghost_char, ghost typing logic, and handle_global_scroll
text = re.sub(r'    def toggle_ghost_typing\(self, enabled\):.*?    def on_ghost_char\(self, char\):.*?    def on_ghost_backspace\(self\):.*?    def on_ghost_enter\(self\):.*?    def _is_caret_visible\(self\):.*?    def _get_ghost_target\(self\):.*?return None\r?\n', '', text, flags=re.DOTALL)
text = re.sub(r'    def handle_global_scroll\(self, x, y, delta\):.*?        super\(\)\.wheelEvent\(event\)\r?\n', '', text, flags=re.DOTALL)

# 6. Update toggle_focus_mode
new_focus = """    def toggle_focus_mode(self):
        hwnd = int(self.winId())
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20) # GWL_EXSTYLE
        try:
            self.focus_mode = 'Background' if getattr(self, 'focus_mode', 'Background') == 'Interactive' else 'Interactive'
            if self.focus_mode == 'Background':
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style & ~0x08000000 & ~0x00000020)
            self.add_system_message(f"⚡ Switched to {self.focus_mode} Mode.")
            self.update_style()
        except Exception:
            pass"""
text = re.sub(r'    def toggle_focus_mode\(self\):.*?        except Exception:\s*pass', new_focus, text, flags=re.DOTALL)

# 7. Update nativeEvent to include WM_NCHITTEST and WM_MOUSEACTIVATE
new_native = """    def nativeEvent(self, eventType, message):
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
                        
            # WM_HOTKEY
            elif msg.message == 0x0312: 
                hotkey_id = msg.wParam
                if hotkey_id == 1: # Alt + Z
                    self.toggle_leader_mode()
                    return True, 0
                elif hotkey_id == 2: # Alt + L
                    self.interview_btn.click()
                    return True, 0
                    
        return super().nativeEvent(eventType, message)"""
text = re.sub(r'    def nativeEvent\(self, eventType, message\):.*?        return super\(\)\.nativeEvent\(eventType, message\)', new_native, text, flags=re.DOTALL)

# 8. Update Key_K behavior
text = text.replace("self.ghost_typing_signal.emit(not getattr(self, 'ghost_active', False))", "self.add_system_message('💡 Ghost Typing is now 100% native! Click the browser search bar to type normally.'); self.toggle_leader_mode()")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("All patches completely rebuilt safely.")
