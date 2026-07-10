import codecs
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

bad_block = '''    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
        app = QApplication(sys.argv)'''

good_block = '''    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        # OpenGL removed to fix 60-second initialization conflict with Chromium GPU flags
        app = QApplication(sys.argv)'''

text = text.replace(bad_block, good_block)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Removed OpenGL flags successfully.")
