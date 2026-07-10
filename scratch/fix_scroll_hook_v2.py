import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Normalize line endings
text = text.replace('\\r\\n', '\\n')

# 1. Add global_scroll_signal
if 'global_scroll_signal =' not in text:
    text = text.replace('class TransparentOverlay(QFrame):', 'class TransparentOverlay(QFrame):\\n    global_scroll_signal = pyqtSignal(int, int, int)')

# 2. Add handle_global_scroll method
scroll_method = '''
    def handle_global_scroll(self, x, y, delta):
        if getattr(self, 'is_hidden', False): return
        
        # We are in Ghost Mode. Route the scroll event to the appropriate widget based on global coordinates.
        from PyQt5.QtCore import QPoint, QRect, Qt
        from PyQt5.QtGui import QWheelEvent
        from PyQt5.QtWidgets import QApplication
        
        local_pos = self.mapFromGlobal(QPoint(x, y))
        
        # 1. Check Transparency Slider (if visible)
        if hasattr(self, 'controls_widget') and self.controls_widget.isVisible():
            if self.slider.geometry().contains(self.controls_widget.mapFromParent(local_pos)):
                # Adjust transparency
                step = 5 if delta > 0 else -5
                new_val = max(10, min(100, self.slider.value() + step))
                self.change_opacity(new_val)
                return
                
        # 2. Check Chat History
        if hasattr(self, 'chat_history') and self.chat_history.isVisible():
            # Calculate hit rect in local TransparentOverlay coordinates
            # map chat_history's top-left to local
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
                    # QtWebEngine requires precise wheel event routing
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

if 'def handle_global_scroll' not in text:
    text = text.replace('    def toggle_visibility_from_hotkey(self):', scroll_method + '\\n    def toggle_visibility_from_hotkey(self):')


# 3. Register overlay instance and start hook
init_injection = '''        # --- Mouse Hook Registration ---
        QApplication.instance()._overlay_instance = self
        self.global_scroll_signal.connect(self.handle_global_scroll)
        install_mouse_hook()
'''
if 'install_mouse_hook()' not in text:
    text = text.replace('    def __init__(self):\\n        super().__init__()', '    def __init__(self):\\n        super().__init__()\\n' + init_injection)

# 4. Uninstall mouse hook on close
close_injection = '''        uninstall_mouse_hook()
'''
if 'uninstall_mouse_hook()' not in text:
    text = text.replace('    def force_exit(self):', '    def force_exit(self):\\n' + close_injection)

with codecs.open(path, 'w', 'utf-8') as f:
    # write back with system line endings
    f.write(text.replace('\\n', '\\r\\n'))
print("Methods patched successfully.")
