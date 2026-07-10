import codecs
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

import re
text = re.sub(
    r"    try:\r?\n        signal\.signal\(signal\.SIGINT, signal\.SIG_DFL\)\r?\n        app = QApplication\(sys\.argv\)",
    "    try:\n        signal.signal(signal.SIGINT, signal.SIG_DFL)\n        QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)\n        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)\n        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)\n        app = QApplication(sys.argv)",
    text
)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Replaced successfully.")
