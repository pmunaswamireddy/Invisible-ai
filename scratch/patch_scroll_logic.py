import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# 1. Add global_scroll_signal
if 'global_scroll_signal =' not in text:
    text = text.replace('class TransparentOverlay(QMainWindow):', 'class TransparentOverlay(QMainWindow):\n    global_scroll_signal = pyqtSignal(int, int, int)')

# 2. Add handle_global_scroll method
scroll_method = '''
    def handle_global_scroll(self, x, y, delta):
        if not getattr(self, 'is_hidden', False): return
        
        # We are in Ghost Mode. Route the scroll event to the appropriate widget based on global coordinates.
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
            # Check if mouse is over the chat container or right-side scrollbar area
            chat_geo = self.chat_history.geometry()
            hit_geo = QRect(chat_geo.x(), chat_geo.y(), chat_geo.width() + 30, chat_geo.height())
            if hit_geo.contains(self.input_frame.mapFromParent(local_pos)):
                self.scroll_chat(delta)
                return
                
        # 3. Check Browser Tabs
        if hasattr(self, 'tab_widget') and self.tab_widget.isVisible():
            if self.tab_widget.geometry().contains(local_pos):
                current_browser = self.tab_widget.currentWidget()
                if current_browser:
                    # QtWebEngine requires precise wheel event routing
                    wheel_event = QWheelEvent(
                        current_browser.mapFromGlobal(QPoint(x, y)),
                        QPoint(x, y),
                        QPoint(0, delta),
                        QPoint(0, delta),
                        delta,
                        Qt.Vertical,
                        Qt.NoButton,
                        Qt.NoModifier
                    )
                    QApplication.postEvent(current_browser, wheel_event)
                return
'''
if 'def handle_global_scroll' not in text:
    text = text.replace('    def toggle_hidden(self):', scroll_method + '\n    def toggle_hidden(self):')


# 3. Register overlay instance and start hook
init_injection = '''        # --- Mouse Hook Registration ---
        QApplication.instance()._overlay_instance = self
        self.global_scroll_signal.connect(self.handle_global_scroll)
        install_mouse_hook()
'''
if 'install_mouse_hook()' not in text:
    text = text.replace('self.installEventFilter(self)', 'self.installEventFilter(self)\n' + init_injection)

# 4. Uninstall mouse hook on close
close_injection = '''        uninstall_mouse_hook()
'''
if 'uninstall_mouse_hook()' not in text:
    text = text.replace('def closeEvent(self, event):', 'def closeEvent(self, event):\n' + close_injection)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Methods patched successfully.")
