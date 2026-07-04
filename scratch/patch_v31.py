import codecs
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# 1. Add close_all_browser_tabs
if 'def close_all_browser_tabs(self):' not in text:
    target = 'def close_tab(self, index):'
    insertion = '''    def close_all_browser_tabs(self):
        """Completely destroys all browser tabs and returns to Chat."""
        for i in range(self.tab_widget.count() - 1, 0, -1):
            if self.tab_widget.tabText(i) != "+":
                self.close_tab(i)

'''
    idx = text.find(target)
    if idx != -1:
        text = text[:idx] + insertion + text[idx:]

# 2. Add Corner Widget to TabWidget
if 'self.close_all_tabs_btn = QPushButton' not in text:
    target2 = 'self.tab_widget.currentChanged.connect(self.on_tab_changed)'
    insertion2 = '''
        self.close_all_tabs_btn = QPushButton("✕ Close All")
        self.close_all_tabs_btn.setObjectName("action_btn")
        self.close_all_tabs_btn.setToolTip("Close all browser tabs")
        self.close_all_tabs_btn.clicked.connect(self.close_all_browser_tabs)
        self.close_all_tabs_btn.setStyleSheet("padding: 4px 8px; font-weight: bold; background: rgba(200, 50, 50, 0.4); border-radius: 4px;")
        self.tab_widget.setCornerWidget(self.close_all_tabs_btn, Qt.TopRightCorner)
        self.close_all_tabs_btn.setVisible(False)
'''
    idx2 = text.find(target2)
    if idx2 != -1:
        text = text[:idx2 + len(target2)] + insertion2 + text[idx2 + len(target2):]

# 3. Update toggle_browser_visibility to hide the close all button when hidden
if 'self.close_all_tabs_btn.setVisible' not in text:
    text = text.replace('self.tab_widget.tabBar().setVisible(False)', 'self.tab_widget.tabBar().setVisible(False)\n            self.close_all_tabs_btn.setVisible(False)')
    text = text.replace('self.tab_widget.tabBar().setVisible(True)', 'self.tab_widget.tabBar().setVisible(True)\n                self.close_all_tabs_btn.setVisible(True)')

# 4. Modify KeyPressEvent
old_bw = '''            elif vk == Qt.Key_B or vk == Qt.Key_W:
                self.toggle_browser_visibility()
                event.accept()
                return'''
new_bw = '''            elif vk == Qt.Key_B or vk == Qt.Key_W:
                if event.modifiers() & Qt.ShiftModifier:
                    self.close_all_browser_tabs()
                    self.add_system_message("⚙️ Action: Closed all browser tabs")
                else:
                    self.toggle_browser_visibility()
                event.accept()
                return'''
if old_bw in text:
    text = text.replace(old_bw, new_bw)

# 5. Add voice command for close all tabs
old_voice = 'click_verbs = ["click", "open", "toggle", "start", "press", "go to"]'
new_voice = 'click_verbs = ["click", "open", "toggle", "start", "press", "go to"]\n        if any(v in text_lower for v in ["close browser", "close all tabs", "close tabs"]):\n            self.close_all_browser_tabs()\n            self.add_command_message("⚙️ Action: Closed All Browser Tabs")\n            return'
if old_voice in text:
    text = text.replace(old_voice, new_voice)

# 6. Update system message text
old_msg = 'self.add_system_message("⚡ Command Mode Active (Press Space/H: Hide | S: Scan | I: Inject | 1-9: Indexed | P: Model | O: Voice | U: Voice Typist | M: Live Chat | L: Interview | V: Speaker | B/W: Browser | E: Focus Chat | Esc/Alt+Z: Exit)")'
new_msg = 'self.add_system_message("⚡ Command Mode Active (Press Space/H: Hide | S: Scan | I: Inject | 1-9: Indexed | P: Model | O: Voice | U: Voice Typist | M: Live Chat | L: Interview | V: Speaker | B/W: Toggle Browser | Shift+B/W: Close Browser | E: Focus Chat | Esc/Alt+Z: Exit)")'
if old_msg in text:
    text = text.replace(old_msg, new_msg)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Patch applied successfully.")
