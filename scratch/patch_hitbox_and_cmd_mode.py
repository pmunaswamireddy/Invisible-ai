import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# 1. Patch hitboxes in WM_NCHITTEST
old_hitbox = r"""                    if not is_solid and hasattr\(self, 'chat_history'\) and self\.chat_history\.isVisible\(\):\r?\n                        scrollbar = self\.chat_history\.verticalScrollBar\(\)\r?\n                        if scrollbar and scrollbar\.isVisible\(\):\r?\n                            sb_local = scrollbar\.mapFromGlobal\(QPoint\(x, y\)\)\r?\n                            if scrollbar\.rect\(\)\.contains\(sb_local\):\r?\n                                is_solid = True\r?\n                                \r?\n                    if not is_solid and hasattr\(self, 'slider'\) and self\.slider\.isVisible\(\):\r?\n                        slider_local = self\.slider\.mapFromGlobal\(QPoint\(x, y\)\)\r?\n                        if self\.slider\.rect\(\)\.contains\(slider_local\):\r?\n                            is_solid = True"""

new_hitbox = """                    if not is_solid and hasattr(self, 'slider') and self.slider.isVisible():
                        slider_local = self.slider.mapFromGlobal(QPoint(x, y))
                        if self.slider.rect().adjusted(-10, -10, 10, 10).contains(slider_local):
                            is_solid = True
                            
                    if not is_solid and hasattr(self, 'chat_history') and self.chat_history.isVisible():
                        chat_local = self.chat_history.mapFromGlobal(QPoint(x, y))
                        if self.chat_history.rect().contains(chat_local):
                            if chat_local.x() >= self.chat_history.width() - 30:
                                is_solid = True
                            else:
                                url = self.chat_history.anchorAt(chat_local)
                                if url:
                                    is_solid = True"""

text, count = re.subn(old_hitbox, new_hitbox, text)
print(f"Patched hitboxes {count} times.")

# 2. Patch Command Mode 1-9 logic
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

text, count2 = re.subn(old_cmd, new_cmd, text)
print(f"Patched command mode buffer {count2} times.")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Patch applied successfully.")
