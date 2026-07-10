import codecs
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

bad = '''    def enterEvent(self, event):
            self.restore_bubble.setGeometry(0, 0, w, h)
            self.update_restore_bubble_style(hovered=True)
        super().enterEvent(event)'''

good = '''    def enterEvent(self, event):
        if getattr(self, 'is_hidden', False):
            self.update_restore_bubble_style(hovered=True)
        super().enterEvent(event)'''

text = text.replace(bad, good)

bad_leave = '''    def leaveEvent(self, event):
        if self.is_hidden: self.apply_dock()
        super().leaveEvent(event)'''

good_leave = '''    def leaveEvent(self, event):
        if getattr(self, 'is_hidden', False):
            self.update_restore_bubble_style(hovered=False)
        super().leaveEvent(event)'''

text = text.replace(bad_leave, good_leave)
text = text.replace('thickness = 8', 'thickness = 12')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Patched cleanly.")
