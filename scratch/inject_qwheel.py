import codecs
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

if 'QWheelEvent' not in text:
    text = text.replace('from PyQt5.QtGui import ', 'from PyQt5.QtGui import QWheelEvent, ')
    with codecs.open(path, 'w', 'utf-8') as f:
        f.write(text)
    print("Imported QWheelEvent")
