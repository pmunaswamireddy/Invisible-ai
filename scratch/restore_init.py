import codecs

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Fix the broken __init__
broken_chunk = """        except Exception:
            pass
        self.focus_chat_hotkey_signal.connect(self.focus_chat_from_hotkey)
        self.app_log_signal.connect(self.append_log)"""

fixed_chunk = """        except Exception:
            pass

    def __init__(self):
        super().__init__()
        app = QApplication.instance()
        app._overlay_instance = self
        self.global_scroll_signal.connect(self.handle_global_scroll)
        install_mouse_hook()
        
        self.hotkey_signal.connect(self.toggle_visibility_from_hotkey)
        self.scan_hotkey_signal.connect(self.scan_screen)
        self.inject_hotkey_signal.connect(self.inject_code)
        self.inject_indexed_hotkey_signal.connect(self.inject_code)
        self.send_hotkey_signal.connect(self.handle_chat)
        self.focus_chat_hotkey_signal.connect(self.focus_chat_from_hotkey)
        self.app_log_signal.connect(self.append_log)"""

text = text.replace(broken_chunk, fixed_chunk)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("init restored and patched")
