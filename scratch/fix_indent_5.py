import codecs
import re

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

# Fix unexpected indent
text = text.replace('        _mouse_hook_handle = None\n\nclass KeyBdInput', 'class KeyBdInput')

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Indentation fixed.")
