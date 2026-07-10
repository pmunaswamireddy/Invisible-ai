import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Fix the coordinate mapping in nativeEvent for WM_NCHITTEST and WM_MOUSEACTIVATE
old_nchittest = r"""                    from PyQt5\.QtCore import QPoint\r?\n                    local_pos = self\.mapFromGlobal\(QPoint\(x, y\)\)\r?\n                    \r?\n                    is_solid = False\r?\n                    if hasattr\(self, 'tab_widget'\) and self\.tab_widget\.isVisible\(\) and self\.tab_widget\.geometry\(\)\.contains\(local_pos\):\r?\n                        if self\.tab_widget\.currentIndex\(\) > 0:\r?\n                            is_solid = True"""

new_nchittest = """                    from PyQt5.QtCore import QPoint
                    is_solid = False
                    if hasattr(self, 'tab_widget') and self.tab_widget.isVisible():
                        tab_local = self.tab_widget.mapFromGlobal(QPoint(x, y))
                        if self.tab_widget.rect().contains(tab_local):
                            if self.tab_widget.currentIndex() > 0:
                                is_solid = True"""

text, count1 = re.subn(old_nchittest, new_nchittest, text)
print(f"Patched WM_NCHITTEST {count1} times.")

old_mouseactivate = r"""                    from PyQt5\.QtCore import QPoint\r?\n                    local_pos = self\.mapFromGlobal\(QPoint\(x, y\)\)\r?\n                    if hasattr\(self, 'tab_widget'\) and self\.tab_widget\.isVisible\(\) and self\.tab_widget\.geometry\(\)\.contains\(local_pos\):\r?\n                        if self\.tab_widget\.currentIndex\(\) > 0:"""

new_mouseactivate = """                    from PyQt5.QtCore import QPoint
                    if hasattr(self, 'tab_widget') and self.tab_widget.isVisible():
                        tab_local = self.tab_widget.mapFromGlobal(QPoint(x, y))
                        if self.tab_widget.rect().contains(tab_local):
                            if self.tab_widget.currentIndex() > 0:"""

text, count2 = re.subn(old_mouseactivate, new_mouseactivate, text)
print(f"Patched WM_MOUSEACTIVATE {count2} times.")

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Coordinate patch applied successfully.")
