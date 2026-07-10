import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Normalize line endings
text = text.replace('\\r\\n', '\\n')

# 2. Add handle_global_scroll method
scroll_method = '''
    def handle_global_scroll(self, x, y, delta):
        # Only handle global scrolls if the app is unclickable (Background mode or Hidden/Ghost mode)
        if getattr(self, 'focus_mode', '') != 'Background' and not getattr(self, 'is_hidden', False): 
            return
            
        from PyQt5.QtCore import QPoint, QRect, Qt
        from PyQt5.QtGui import QWheelEvent
        from PyQt5.QtWidgets import QApplication
        
        local_pos = self.mapFromGlobal(QPoint(x, y))
        
        # 1. Check Transparency Slider (if visible)
        if hasattr(self, 'controls_widget') and self.controls_widget.isVisible():
            if self.slider.geometry().contains(self.controls_widget.mapFromParent(local_pos)):
                step = 5 if delta > 0 else -5
                new_val = max(10, min(100, self.slider.value() + step))
                self.change_opacity(new_val)
                return
                
        # 2. Check Chat History
        if hasattr(self, 'chat_history') and self.chat_history.isVisible():
            chat_top_left = self.chat_history.mapTo(self, QPoint(0,0))
            chat_size = self.chat_history.size()
            hit_geo = QRect(chat_top_left.x(), chat_top_left.y(), chat_size.width() + 30, chat_size.height())
            
            if hit_geo.contains(local_pos):
                self.scroll_chat(delta)
                return
                
        # 3. Check Browser Tabs
        if hasattr(self, 'tab_widget') and self.tab_widget.isVisible():
            current_browser = self.tab_widget.currentWidget()
            if current_browser and hasattr(current_browser, 'browser'):
                browser_top_left = current_browser.browser.mapTo(self, QPoint(0,0))
                browser_size = current_browser.browser.size()
                browser_rect = QRect(browser_top_left.x(), browser_top_left.y(), browser_size.width(), browser_size.height())
                
                if browser_rect.contains(local_pos):
                    wheel_event = QWheelEvent(
                        current_browser.browser.mapFromGlobal(QPoint(x, y)),
                        QPoint(x, y),
                        QPoint(0, delta),
                        QPoint(0, delta),
                        delta,
                        Qt.Vertical,
                        Qt.NoButton,
                        Qt.NoModifier
                    )
                    QApplication.postEvent(current_browser.browser.focusProxy() or current_browser.browser, wheel_event)
                return
'''

# Replace the existing handle_global_scroll method
text = re.sub(
    r'    def handle_global_scroll\(self, x, y, delta\):.*?return\s+',
    scroll_method.lstrip() + '\\n',
    text,
    flags=re.DOTALL
)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text.replace('\\n', '\\r\\n'))
print("handle_global_scroll updated successfully for Background mode.")
