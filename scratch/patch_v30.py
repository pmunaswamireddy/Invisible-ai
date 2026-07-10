import re
import codecs

try:
    with codecs.open('d:/invisibleai/overlay.py', 'r', 'utf-8') as f:
        content = f.read()

    # 1. Update browser_btn connection
    content = content.replace(
        'self.browser_btn.clicked.connect(self.open_new_empty_browser_tab)',
        'self.browser_btn.clicked.connect(self.toggle_browser_visibility)'
    )

    # 2. Insert toggle_browser_visibility
    if 'def toggle_browser_visibility(self):' not in content:
        open_new_idx = content.find('def open_new_empty_browser_tab(self):')
        toggle_code = """
    def toggle_browser_visibility(self):
        # Toggle browser tab visibility
        if self.tab_widget.currentIndex() > 0:
            self.last_browser_idx = self.tab_widget.currentIndex()
            self.tab_widget.setCurrentIndex(0)
            self.tab_widget.tabBar().setVisible(False)
        else:
            last_idx = getattr(self, 'last_browser_idx', 1)
            if self.tab_widget.count() > 1:
                self.tab_widget.tabBar().setVisible(True)
                if 1 <= last_idx < self.tab_widget.count() and self.tab_widget.tabText(last_idx) != "+":
                    self.tab_widget.setCurrentIndex(last_idx)
                else:
                    self.tab_widget.setCurrentIndex(1)
            else:
                self.open_new_empty_browser_tab()
"""
        content = content[:open_new_idx] + toggle_code.strip() + '\n\n    ' + content[open_new_idx:]

    # 3. Modify WebBrowserTab.eventFilter
    event_filter_old = '''    def eventFilter(self, obj, event):
        """Handle horizontal swipe gestures for back/forward navigation."""
        if obj == self.browser:'''
        
    event_filter_new = '''    def eventFilter(self, obj, event):
        """Handle horizontal swipe gestures for back/forward navigation and command mode interception."""
        from PyQt5.QtCore import QEvent as _QE
        
        # Intercept keys from Chromium render widget if in command mode or ghost typing
        if event.type() == _QE.KeyPress:
            if getattr(self.parent_overlay, 'leader_active', False) or getattr(self.parent_overlay, 'ghost_active', False):
                self.parent_overlay.keyPressEvent(event)
                return True
                
        if obj == self.browser:'''
        
    content = content.replace(event_filter_old, event_filter_new)

    # 4. Check if X icon close browser entirely issue is fixed
    # We want X icon on the browser tab to not close the app. It already doesn't, it just calls close_tab.
    
    with codecs.open('d:/invisibleai/overlay.py', 'w', 'utf-8') as f:
        f.write(content)
        
    print("Patch applied successfully.")
except Exception as e:
    import traceback
    traceback.print_exc()
