import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# We need to ensure that __init__ starts correctly.
# Currently it looks like:
#        except Exception:
#            self.focus_chat_hotkey_signal.connect(self.focus_chat_from_hotkey)
# (wait, the error says: expected an indented block after 'except' statement on line 2976)

text = re.sub(
    r'(except Exception:\s*)self\.focus_chat_hotkey_signal\.connect',
    r'\1pass\n\n    def __init__(self):\n        super().__init__()\n        app = QApplication.instance()\n        app._overlay_instance = self\n        self.global_scroll_signal.connect(self.handle_global_scroll)\n        install_mouse_hook()\n        \n        self.hotkey_signal.connect(self.toggle_visibility_from_hotkey)\n        self.scan_hotkey_signal.connect(self.scan_screen)\n        self.inject_hotkey_signal.connect(self.inject_code)\n        self.inject_indexed_hotkey_signal.connect(self.inject_code)\n        self.send_hotkey_signal.connect(self.handle_chat)\n        self.focus_chat_hotkey_signal.connect',
    text
)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Regex fix applied")
