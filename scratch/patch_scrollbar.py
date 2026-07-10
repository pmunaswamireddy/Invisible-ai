import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

old_code = r"""                    if hasattr\(self, 'tab_widget'\) and self\.tab_widget\.isVisible\(\):\r?\n                        tab_local = self\.tab_widget\.mapFromGlobal\(QPoint\(x, y\)\)\r?\n                        if self\.tab_widget\.rect\(\)\.contains\(tab_local\):\r?\n                            if self\.tab_widget\.currentIndex\(\) > 0:\r?\n                                is_solid = True"""

new_code = """                    if hasattr(self, 'tab_widget') and self.tab_widget.isVisible():
                        tab_local = self.tab_widget.mapFromGlobal(QPoint(x, y))
                        if self.tab_widget.rect().contains(tab_local):
                            if self.tab_widget.currentIndex() > 0:
                                is_solid = True
                                
                    if not is_solid and hasattr(self, 'chat_history') and self.chat_history.isVisible():
                        scrollbar = self.chat_history.verticalScrollBar()
                        if scrollbar and scrollbar.isVisible():
                            sb_local = scrollbar.mapFromGlobal(QPoint(x, y))
                            if scrollbar.rect().contains(sb_local):
                                is_solid = True
                                
                    if not is_solid and hasattr(self, 'slider') and self.slider.isVisible():
                        slider_local = self.slider.mapFromGlobal(QPoint(x, y))
                        if self.slider.rect().contains(slider_local):
                            is_solid = True"""

text, count = re.subn(old_code, new_code, text)
print(f"Patched WM_NCHITTEST for scrollbar {count} times.")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Scrollbar patch applied successfully.")
