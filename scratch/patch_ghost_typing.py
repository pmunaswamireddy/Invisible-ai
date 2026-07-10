import codecs
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Route signals based on cursor hit testing
ghost_patch = '''
    def _get_ghost_target(self):
        # Determine the target for ghost keystrokes based on mouse position
        from PyQt5.QtGui import QCursor
        from PyQt5.QtCore import QPoint, QRect
        local_pos = self.mapFromGlobal(QCursor.pos())
        
        if hasattr(self, 'tab_widget') and self.tab_widget.isVisible():
            current_tab = self.tab_widget.currentWidget()
            if current_tab:
                # Check Address Bar
                if hasattr(current_tab, 'address_bar'):
                    addr_geo = current_tab.address_bar.geometry()
                    mapped_addr = QRect(current_tab.mapTo(self, addr_geo.topLeft()), addr_geo.size())
                    if mapped_addr.contains(local_pos):
                        return "address_bar", current_tab.address_bar
                        
                # Check Browser View
                if hasattr(current_tab, 'browser'):
                    browser_geo = current_tab.browser.geometry()
                    mapped_browser = QRect(current_tab.mapTo(self, browser_geo.topLeft()), browser_geo.size())
                    if mapped_browser.contains(local_pos):
                        return "browser", current_tab.browser
                        
        return "chat", self.chat_input

    def on_ghost_char(self, char):
        target_type, target = self._get_ghost_target()
        
        if target_type == "browser":
            from PyQt5.QtGui import QKeyEvent
            from PyQt5.QtCore import QEvent, Qt
            event = QKeyEvent(QEvent.KeyPress, 0, Qt.NoModifier, char)
            QApplication.postEvent(target.focusProxy() or target, event)
            event_release = QKeyEvent(QEvent.KeyRelease, 0, Qt.NoModifier, char)
            QApplication.postEvent(target.focusProxy() or target, event_release)
        elif target_type in ["chat", "address_bar"]:
            target.setText(target.text() + char)
        
    def on_ghost_backspace(self):
        target_type, target = self._get_ghost_target()
        
        if target_type == "browser":
            from PyQt5.QtGui import QKeyEvent
            from PyQt5.QtCore import QEvent, Qt
            event = QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier)
            QApplication.postEvent(target.focusProxy() or target, event)
            event_release = QKeyEvent(QEvent.KeyRelease, Qt.Key_Backspace, Qt.NoModifier)
            QApplication.postEvent(target.focusProxy() or target, event_release)
        elif target_type in ["chat", "address_bar"]:
            text = target.text()
            if text:
                target.setText(text[:-1])
                
    def on_ghost_enter(self):
        target_type, target = self._get_ghost_target()
        
        if target_type == "browser":
            from PyQt5.QtGui import QKeyEvent
            from PyQt5.QtCore import QEvent, Qt
            event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
            QApplication.postEvent(target.focusProxy() or target, event)
            event_release = QKeyEvent(QEvent.KeyRelease, Qt.Key_Return, Qt.NoModifier)
            QApplication.postEvent(target.focusProxy() or target, event_release)
        elif target_type == "address_bar":
            url = target.text()
            if url:
                if not url.startswith('http'):
                    url = 'https://www.google.com/search?q=' + url
                current_tab = self.tab_widget.currentWidget()
                current_tab.load_url(url)
        elif target_type == "chat":
            self.handle_chat()
'''

# 1. Replace the methods
import re
text = re.sub(r'    def on_ghost_char\(self, char\):.*?def on_ghost_typing_toggled', 
              ghost_patch.lstrip() + '\n    def on_ghost_typing_toggled', text, flags=re.DOTALL)

# 2. Hook up the enter signal correctly
text = text.replace('self.ghost_enter_signal.connect(self.handle_chat)', 'self.ghost_enter_signal.connect(self.on_ghost_enter)')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Ghost typing patched successfully.")
