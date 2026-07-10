import codecs
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

bad_enter = '''    def enterEvent(self, event):
        if self.is_hidden:
            rect = self.geometry()
            expansion = 10
            x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
            if self.dock_edge == 'left': w += expansion
            elif self.dock_edge == 'right': x -= expansion; w += expansion
            elif self.dock_edge == 'top': h += expansion
            elif self.dock_edge == 'bottom': y -= expansion; h += expansion
            self.setGeometry(x, y, w, h)
            self.restore_bubble.setGeometry(0, 0, w, h)
            self.update_restore_bubble_style(hovered=True)
        super().enterEvent(event)'''

good_enter = '''    def enterEvent(self, event):
        if getattr(self, 'is_hidden', False):
            self.update_restore_bubble_style(hovered=True)
        super().enterEvent(event)'''

bad_leave = '''    def leaveEvent(self, event):
        if self.is_hidden: self.apply_dock()
        super().leaveEvent(event)'''

good_leave = '''    def leaveEvent(self, event):
        if getattr(self, 'is_hidden', False):
            self.update_restore_bubble_style(hovered=False)
        super().leaveEvent(event)'''

if bad_enter in text and bad_leave in text:
    text = text.replace(bad_enter, good_enter)
    text = text.replace(bad_leave, good_leave)
    text = text.replace('thickness = 8', 'thickness = 12')
    with codecs.open(path, 'w', 'utf-8') as f:
        f.write(text)
    print("Patched successfully.")
else:
    print("Could not find exact text match.")
