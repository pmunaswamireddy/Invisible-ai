import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Fix apply_initial_focus_styles
old_initial = r"""    def apply_initial_focus_styles\(self\):\r?\n        try:\r?\n            hwnd = int\(self\.winId\(\)\)\r?\n            GWL_EXSTYLE = -20\r?\n            WS_EX_NOACTIVATE = 0x08000000\r?\n            WS_EX_TRANSPARENT = 0x00000020\r?\n            ex_style = ctypes\.windll\.user32\.GetWindowLongW\(hwnd, GWL_EXSTYLE\)\r?\n            if getattr\(self, 'focus_mode', 'Background'\) == 'Background':\r?\n                ctypes\.windll\.user32\.SetWindowLongW\(hwnd, GWL_EXSTYLE, ex_style \| WS_EX_NOACTIVATE \| WS_EX_TRANSPARENT\)\r?\n            else:\r?\n                ctypes\.windll\.user32\.SetWindowLongW\(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT\)"""

new_initial = """    def apply_initial_focus_styles(self):
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if getattr(self, 'focus_mode', 'Background') == 'Background':
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex_style | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT)
            else:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_NOACTIVATE & ~WS_EX_TRANSPARENT)"""

text, count1 = re.subn(old_initial, new_initial, text)
print(f"Patched apply_initial_focus_styles {count1} times.")

# Fix changeEvent
old_changeEvent = r"""                  if self\.focus_mode == 'Background':\r?\n                      hwnd = int\(self\.winId\(\)\)\r?\n                      GWL_EXSTYLE = -20\r?\n                      WS_EX_NOACTIVATE = 0x08000000\r?\n                      WS_EX_TRANSPARENT = 0x00000020\r?\n                      ex_style = ctypes\.windll\.user32\.GetWindowLongW\(hwnd, GWL_EXSTYLE\)\r?\n                      ctypes\.windll\.user32\.SetWindowLongW\(hwnd, GWL_EXSTYLE, ex_style \| WS_EX_NOACTIVATE \| WS_EX_TRANSPARENT\)"""

new_changeEvent = """                  if self.focus_mode == 'Background':
                      hwnd = int(self.winId())
                      GWL_EXSTYLE = -20
                      WS_EX_NOACTIVATE = 0x08000000
                      WS_EX_TRANSPARENT = 0x00000020
                      ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                      ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex_style | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT)"""

text, count2 = re.subn(old_changeEvent, new_changeEvent, text)
print(f"Patched changeEvent {count2} times.")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("State patches applied successfully.")
